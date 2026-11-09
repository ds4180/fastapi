import os
import shutil
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, not_
from models import MediaAsset
from domain.media import media_config as config

logger = logging.getLogger("media_gc")
logger.setLevel(logging.INFO)

class MediaGCService:
    def __init__(self, db: Session):
        self.db = db
        self.today_str = datetime.now().strftime("%Y%m%d")
        self.gc_del_root = os.path.join(config.MEDIA_ROOT, f".DEL_GC_{self.today_str}")

    def run_tasks(self, task_indices: list[int]):
        """
        요청된 인덱스에 해당하는 GC 작업들을 순차적으로 실행
        """
        results = {}
        
        task_map = {
            1: ("ORPHAN_FILES", self.cleanup_orphan_files),
            2: ("DANGLING_RECORDS", self.cleanup_dangling_records),
            3: ("ORPHAN_THUMBS", self.cleanup_orphan_thumbnails),
            4: ("RETENTION_CLEANUP", self.cleanup_retention),
            5: ("EMPTY_FOLDERS", self.cleanup_empty_folders),
            6: ("ORIGINAL_EXPIRY_GC", self.cleanup_expired_originals)
        }

        for idx in sorted(task_indices):
            if idx in task_map:
                name, func = task_map[idx]
                logger.info(f"START GC TASK [{idx}]: {name}")
                try:
                    results[name] = func()
                except Exception as e:
                    logger.error(f"GC TASK [{idx}] FAIL: {str(e)}")
                    results[name] = {"status": "error", "message": str(e)}
        
        return results

    def cleanup_orphan_files(self):
        """
        [작업 1] DB 기록 없는 고립 파일 정리
        실제 디스크에는 있으나 DB에는 없는 파일을 DEL_GC 폴더로 이동
        """
        moved_count = 0
        # 대상 티어 정의
        tiers = ["PUBLIC", "SYSTEM", "PROTECTED", "PRIVATE"]
        
        # DB에 등록된 모든 파일 경로 가져오기 (메모리 효율을 위해 set 사용)
        db_paths = set()
        for asset in self.db.query(MediaAsset.file_path).filter(MediaAsset.is_deleted == False).all():
            db_paths.add(asset.file_path)

        for tier in tiers:
            tier_root = os.path.join(config.MEDIA_ROOT, tier)
            if not os.path.exists(tier_root): continue

            for root, dirs, files in os.walk(tier_root):
                # 썸네일 폴더 및 숨김 폴더('.' 시작) 제외
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != config.THUMB_FOLDER_NAME]
                if config.THUMB_FOLDER_NAME in root: continue

                for f in files:
                    if f.startswith('.'): continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, config.MEDIA_ROOT)
                    
                    if rel_path not in db_paths:
                        # 고립 파일 발견! DEL_GC로 이동
                        dst_path = os.path.join(self.gc_del_root, rel_path)
                        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                        shutil.move(full_path, dst_path)
                        moved_count += 1
        
        return {"status": "success", "moved_count": moved_count, "location": self.gc_del_root if moved_count > 0 else None}

    def cleanup_dangling_records(self):
        """
        [작업 2] 유령 DB 기록 정리
        DB에는 있으나 실제 파일이 없는 기록을 찾아 삭제 대기 상태로 변경
        [v3.5 대원칙 반영]:
        - 이미지 자산:
          1) 원본 파일(file_path)이 디스크에 있으면 정상 자산.
          2) 원본이 없더라도, 썸네일 3종(SM, MD, LG) 중 하나라도 디스크에 물리 존재하면 정상 자산(복제본 또는 원본 시한부 파기본)!
          3) 원본 파일도 없고, 썸네일도 단 1개도 없는 경우에만 '유령 레코드'로 판정하여 is_deleted=True 처리!
        - 문서/기타 자산:
          원본 파일이 디스크에 없으면 유령 레코드로 판정.
        """
        dangling_count = 0
        assets = self.db.query(MediaAsset).filter(MediaAsset.is_deleted == False).all()
        
        for asset in assets:
            abs_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
            
            # 1. 원본 파일이 실제로 존재하면 정상
            if os.path.exists(abs_path):
                continue
                
            # 2. 이미지 카테고리인 경우: 썸네일 3종 물리 존재 여부 확인
            if asset.category == config.MEDIA_CATEGORIES["IMAGE"]:
                meta = asset.meta_info or {}
                has_valid_thumb = False
                
                # 메타데이터 thumbs 확인
                thumbs = meta.get("thumbs", {})
                for t_rel in thumbs.values():
                    if t_rel and os.path.exists(os.path.join(config.MEDIA_ROOT, t_rel)):
                        has_valid_thumb = True
                        break
                
                # 메타데이터에 없더라도 디렉토리 내 TMB_ 파일이 있는지 역추적
                if not has_valid_thumb:
                    asset_dir = os.path.dirname(abs_path)
                    thumb_sub_dir = os.path.join(asset_dir, config.THUMB_FOLDER_NAME)
                    if os.path.exists(thumb_sub_dir):
                        base_name = os.path.basename(asset.file_path)
                        uuid_candidate = base_name.replace(config.PREFIX['IMAGE'], "").split('.')[0]
                        for tf in os.listdir(thumb_sub_dir):
                            if tf.startswith(config.PREFIX['THUMB']) and uuid_candidate in tf:
                                has_valid_thumb = True
                                break
                
                # 썸네일이 살아있으면 유효한 자산 (복제본이거나 원본 시한부 파기본)
                if has_valid_thumb:
                    continue
            
            # 원본도 없고 썸네일도 전혀 없는 경우 ➔ 유령 레코드 처리
            asset.is_deleted = True
            asset.deleted_at = datetime.now()
            dangling_count += 1
        
        self.db.commit()
        return {"status": "success", "flagged_count": dangling_count}

    def cleanup_orphan_thumbnails(self):
        """
        [작업 3] 고립된 썸네일 정리
        [v3.5 대원칙 반영]:
        - DB에 등록되어 살아있는 자산(is_deleted=False)의 썸네일은 원본 파일의 존재 여부와 무관하게 영구 보존!
        - DB 자산 자체가 완전히 삭제되었거나 매칭되는 MediaAsset 기록이 전혀 없는 썸네일만 고립(Orphan)으로 판정하여 삭제.
        - 전체 티어(PUBLIC, PROTECTED, PRIVATE, SYSTEM) 하위의 모든 THUMB 폴더를 재귀 순회하여 정리.
        """
        deleted_count = 0
        tiers = ["PUBLIC", "SYSTEM", "PROTECTED", "PRIVATE"]

        # 모든 유효한 활성 자산의 식별자(UUID 및 썸네일 상대경로) 집합 수집
        valid_uuids = set()
        valid_thumb_rel_paths = set()
        
        active_assets = self.db.query(MediaAsset).filter(MediaAsset.is_deleted == False).all()
        for asset in active_assets:
            base_name = os.path.basename(asset.file_path)
            clean_uuid = base_name.replace(config.PREFIX['IMAGE'], "").split('.')[0]
            if clean_uuid:
                valid_uuids.add(clean_uuid.lower())
            
            meta = asset.meta_info or {}
            thumbs = meta.get("thumbs", {})
            for t_rel in thumbs.values():
                if t_rel:
                    valid_thumb_rel_paths.add(t_rel.replace("\\", "/"))

        for tier in tiers:
            tier_root = os.path.join(config.MEDIA_ROOT, tier)
            if not os.path.exists(tier_root): continue

            for root, dirs, files in os.walk(tier_root):
                if os.path.basename(root) != config.THUMB_FOLDER_NAME:
                    continue

                for f in files:
                    if not f.startswith(config.PREFIX['THUMB']):
                        continue
                    
                    full_thumb_path = os.path.join(root, f)
                    rel_thumb_path = os.path.relpath(full_thumb_path, config.MEDIA_ROOT).replace("\\", "/")
                    
                    # 1. 메타데이터 썸네일 경로 집합에 등록되어 있으면 안전 보존
                    if rel_thumb_path in valid_thumb_rel_paths:
                        continue
                        
                    # 2. 파일명 TMB_{uuid}_{size}.WEBP 에서 uuid 추출 매칭
                    parts = f.split("_")
                    if len(parts) >= 3:
                        thumb_uuid = parts[1].lower()
                        if thumb_uuid in valid_uuids:
                            continue
                            
                    # 매칭되는 DB 자산이 전혀 없는 진짜 고립 썸네일 ➔ 안전 삭제
                    try:
                        os.remove(full_thumb_path)
                        deleted_count += 1
                        logger.info(f"🗑️ [고립 썸네일 정리] 매칭 자산 없는 썸네일 삭제: {rel_thumb_path}")
                    except Exception as e:
                        logger.error(f"고립 썸네일 삭제 실패 ({full_thumb_path}): {e}")

        return {"status": "success", "deleted_count": deleted_count}

    def cleanup_retention(self, days=30):
        """
        [작업 4] 보관 기한 만료 폴더 및 개별 격리 파일 영구 삭제
        DEL_ 폴더 및 하위 격리 파일 중 설정 기간(기본 30일)이 지난 항목 영구 파기
        """
        deleted_folders = []
        deleted_files = []
        limit_date = datetime.now() - timedelta(days=days)

        # 1. 루트 레벨의 .DEL_ / DEL_ 격리 폴더 영구 삭제
        for item in os.listdir(config.MEDIA_ROOT):
            item_path = os.path.join(config.MEDIA_ROOT, item)
            if not os.path.isdir(item_path): continue
            
            if item.startswith(".DEL_") or item.startswith("DEL_"):
                # 생성 시간 또는 이름의 날짜 기반 체크
                mtime = datetime.fromtimestamp(os.path.getmtime(item_path))
                if mtime < limit_date:
                    shutil.rmtree(item_path)
                    deleted_folders.append(item)

        # 2. 하위 티어 내 보관 기한이 지난 개별 격리 파일(.DEL_ / DEL_) 영구 삭제
        tiers = ["PUBLIC", "SYSTEM", "PROTECTED", "PRIVATE"]
        for tier in tiers:
            tier_root = os.path.join(config.MEDIA_ROOT, tier)
            if not os.path.exists(tier_root): continue

            for root, dirs, files in os.walk(tier_root):
                for f in files:
                    if f.startswith(".DEL_") or f.startswith("DEL_"):
                        f_path = os.path.join(root, f)
                        is_expired = False
                        
                        # 2-1. 파일명 날짜 기반 체크 (.DEL_YYYYMMDD_... 또는 .DEL_ORIG_YYYYMMDD_...)
                        clean_name = f.lstrip(".")
                        parts = clean_name.split("_")
                        try:
                            file_date = None
                            if len(parts) >= 4 and parts[1] == "ORIG" and len(parts[2]) == 8 and parts[2].isdigit():
                                file_date = datetime.strptime(parts[2], "%Y%m%d")
                            elif len(parts) >= 3 and len(parts[1]) == 8 and parts[1].isdigit():
                                file_date = datetime.strptime(parts[1], "%Y%m%d")
                            
                            if file_date and file_date < limit_date:
                                is_expired = True
                        except Exception:
                            pass
                        
                        # 2-2. 파일명 날짜 파싱 불가 시 수정시간(mtime) 체크
                        if not is_expired:
                            try:
                                mtime = datetime.fromtimestamp(os.path.getmtime(f_path))
                                if mtime < limit_date:
                                    is_expired = True
                            except Exception:
                                pass
                        
                        if is_expired:
                            try:
                                os.remove(f_path)
                                rel = os.path.relpath(f_path, config.MEDIA_ROOT)
                                deleted_files.append(rel)
                                logger.info(f"🗑️ [보관 만료 파기] 격리 파일 영구 삭제: {f_path}")
                            except Exception as e:
                                logger.error(f"격리 파일 삭제 실패 ({f_path}): {e}")

        # 3. DB에서 30일 이상 지난 소프트 삭제(is_deleted=True) 자산 레코드 영구 정리
        purged_db_records = 0
        try:
            from sqlalchemy import or_
            expired_assets = self.db.query(MediaAsset).filter(
                MediaAsset.is_deleted == True,
                or_(
                    MediaAsset.deleted_at <= limit_date,
                    and_(MediaAsset.deleted_at.is_(None), MediaAsset.created_at <= limit_date)
                )
            ).all()

            for asset in expired_assets:
                # 연결된 파일이 물리적으로 없는지 확인 후 안전하게 삭제
                abs_f = os.path.join(config.MEDIA_ROOT, asset.file_path)
                if not os.path.exists(abs_f):
                    self.db.delete(asset)
                    purged_db_records += 1

            if purged_db_records > 0:
                self.db.commit()
                logger.info(f"🧹 [보관 만료 파기] 만료된 소프트 삭제 DB 레코드 {purged_db_records}건 영구 정리 완료")
        except Exception as e:
            logger.error(f"DB 만료 레코드 정리 중 오류: {e}")
            self.db.rollback()

        return {
            "status": "success",
            "deleted_folders": deleted_folders,
            "deleted_files_count": len(deleted_files),
            "deleted_files": deleted_files[:50],
            "purged_db_records": purged_db_records
        }

    def cleanup_empty_folders(self):
        """
        [작업 5] 빈 폴더 삭제
        내용물이 없는 폴더를 하위에서부터 상위로 올라오며 삭제
        """
        removed_count = 0
        tiers = ["PUBLIC", "SYSTEM", "PROTECTED", "PRIVATE"]
        
        for tier in tiers:
            tier_root = os.path.join(config.MEDIA_ROOT, tier)
            if not os.path.exists(tier_root): continue

            for root, dirs, files in os.walk(tier_root, topdown=False):
                if root == tier_root: continue # 티어 루트는 삭제 금지
                
                # 디렉토리가 비어있으면 삭제 (hidden 파일 제외)
                if not os.listdir(root):
                    os.rmdir(root)
                    removed_count += 1
        
        return {"status": "success", "removed_count": removed_count}

    def cleanup_expired_originals(self, soft_days=60):
        """
        [작업 6] 원본 이미지(IMG_) 시한부 수명주기 관리 - 소프트 격리 전담
        - 60일 경과: 원본 파일명을 .DEL_ORIG_{오늘날짜}_{파일명}으로 격리, has_original=False (소프트 삭제)
        - 격리된 .DEL_ORIG_ 파일의 최종 물리 영구 파기는 [작업 4] 보관 기한 만료 GC(cleanup_retention)가
          격리일로부터 30일(총 90일) 경과 시 알아서 단일 책임으로 영구 삭제합니다 (중복 명령 제거).
        - 썸네일 3종(SM, MD, LG)은 절대 삭제하지 않고 영구 보존!
        """
        from sqlalchemy.orm.attributes import flag_modified

        now = datetime.now()
        soft_limit_date = now - timedelta(days=soft_days)
        soft_isolated_count = 0

        # 소프트 격리 대상: created_at <= 60일 전인 정상 이미지 자산
        assets = self.db.query(MediaAsset).filter(
            MediaAsset.category == "image",
            MediaAsset.is_deleted == False,
            MediaAsset.created_at <= soft_limit_date
        ).all()

        for asset in assets:
            meta = asset.meta_info or {}
            # 이미 원본이 처리되었거나 없는 경우 건너뜀
            if meta.get("has_original") is False or meta.get("original_purged") is True:
                continue

            orig_abs_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
            if os.path.exists(orig_abs_path):
                dir_name = os.path.dirname(orig_abs_path)
                file_name = os.path.basename(orig_abs_path)
                # 이미 .DEL_ORIG_ 접두어가 붙어있지 않은 경우 격리
                if not file_name.startswith(".DEL_ORIG_"):
                    today_str = now.strftime("%Y%m%d")
                    new_file_name = f".DEL_ORIG_{today_str}_{file_name}"
                    new_abs_path = os.path.join(dir_name, new_file_name)
                    try:
                        os.rename(orig_abs_path, new_abs_path)
                        meta["has_original"] = False
                        meta["original_isolated_at"] = now.isoformat()
                        asset.meta_info = meta
                        flag_modified(asset, "meta_info")
                        soft_isolated_count += 1
                        logger.info(f"📦 [원본 소프트 격리] 60일 경과 원본 격리: {new_file_name}")
                    except Exception as e:
                        logger.error(f"[GC Error] Soft isolate failed for {orig_abs_path}: {e}")

        self.db.commit()

        return {
            "status": "success",
            "soft_isolated_count": soft_isolated_count
        }
