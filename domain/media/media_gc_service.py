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
        self.gc_del_root = os.path.join(config.MEDIA_ROOT, f"DEL_GC_{self.today_str}")

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
            5: ("EMPTY_FOLDERS", self.cleanup_empty_folders)
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
                # 썸네일 폴더 등 특수 폴더 제외
                if config.THUMB_FOLDER_NAME in root: continue

                for f in files:
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
        """
        dangling_count = 0
        assets = self.db.query(MediaAsset).filter(MediaAsset.is_deleted == False).all()
        
        for asset in assets:
            abs_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
            if not os.path.exists(abs_path):
                # 파일이 없음! 삭제 플래그 처리
                asset.is_deleted = True
                asset.deleted_at = datetime.now()
                dangling_count += 1
        
        self.db.commit()
        return {"status": "success", "flagged_count": dangling_count}

    def cleanup_orphan_thumbnails(self):
        """
        [작업 3] 고립된 썸네일 정리
        UUID 매칭을 통해 원본이 사라진 썸네일 파일 삭제
        """
        deleted_count = 0
        thumb_dir = os.path.join(config.MEDIA_ROOT, config.THUMB_FOLDER_NAME)
        if not os.path.exists(thumb_dir): return {"status": "skipped", "message": "No thumb dir"}

        # 모든 유효한 자산 UUID 집합
        valid_uuids = set()
        for asset in self.db.query(MediaAsset.id).all():
            valid_uuids.add(str(asset.id))

        for f in os.listdir(thumb_dir):
            if not f.startswith("TMB_"): continue
            
            # 파일명 규칙: TMB_{uuid}_{SIZE}.WEBP
            try:
                parts = f.split("_")
                if len(parts) < 3: continue
                uuid_part = parts[1]
                
                if uuid_part not in valid_uuids:
                    os.remove(os.path.join(thumb_dir, f))
                    deleted_count += 1
            except: continue
            
        return {"status": "success", "deleted_count": deleted_count}

    def cleanup_retention(self, days=30):
        """
        [작업 4] 보관 기한 만료 폴더 영구 삭제
        DEL_ 폴더 중 설정 기간이 지난 폴더 삭제
        """
        deleted_folders = []
        limit_date = datetime.now() - timedelta(days=days)

        for item in os.listdir(config.MEDIA_ROOT):
            item_path = os.path.join(config.MEDIA_ROOT, item)
            if not os.path.isdir(item_path): continue
            
            if item.startswith("DEL_"):
                # 생성 시간 또는 이름의 날짜 기반 체크
                mtime = datetime.fromtimestamp(os.path.getmtime(item_path))
                if mtime < limit_date:
                    shutil.rmtree(item_path)
                    deleted_folders.append(item)
        
        return {"status": "success", "deleted_folders": deleted_folders}

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
