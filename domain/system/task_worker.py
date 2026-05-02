import asyncio
import logging
import traceback
import os
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models import SystemTask, MediaAsset
from database import SessionLocal
from domain.media import media_config as config
from PIL import Image
from domain.media import media_service # [v3.2] safe_makedirs 사용을 위해 임포트

# 로깅 설정
logger = logging.getLogger("task_worker")
logger.setLevel(logging.INFO)

# --- [재사용성 포인트] 태스크 핸들러 등록소 ---
TASK_HANDLERS = {}

def register_handler(task_type: str):
    def decorator(func):
        TASK_HANDLERS[task_type] = func
        return func
    return decorator

# --- [실제 작업 처리기] ---

@register_handler("MEDIA_ISOLATE")
async def handle_media_isolate(task: SystemTask, db: Session):
    """
    [v3.1] 미디어 격리 처리기 (원본 + 썸네일 세트 격리)
    규칙: DEL_{YYYYMMDD}_{기존파일명}
    """
    file_path = task.payload.get("file_path")
    asset_id = task.payload.get("asset_id")
    
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    today_str = datetime.now().strftime("%Y%m%d")

    # 1. 원본 파일 격리
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    
    if not base_name.startswith(config.PREFIX['DELETE']):
        new_name = f"{config.PREFIX['DELETE']}{today_str}_{base_name}"
        new_path = os.path.join(dir_name, new_name)
        os.rename(file_path, new_path)
        logger.info(f"🛡️ 원본 격리 완료: {new_name}")

    # 2. 썸네일 세트 격리 (이미지인 경우)
    thumb_dir = os.path.join(dir_name, config.THUMB_FOLDER_NAME)
    if os.path.exists(thumb_dir):
        unique_id = os.path.splitext(base_name)[0]
        for t_file in os.listdir(thumb_dir):
            # 해당 원본의 썸네일들만 골라서 격리
            if unique_id in t_file and not t_file.startswith(config.PREFIX['DELETE']):
                old_t_path = os.path.join(thumb_dir, t_file)
                new_t_path = os.path.join(thumb_dir, f"{config.PREFIX['DELETE']}{today_str}_{t_file}")
                os.rename(old_t_path, new_t_path)
        logger.info(f"🛡️ 썸네일 세트 격리 완료")

    task.progress_pct = 100
    return {"status": "isolated", "date": today_str}

@register_handler("THUMB_GEN")
async def handle_thumb_gen(task: SystemTask, db: Session):
    """
    [v3.1] 고해상도 썸네일(MD, LG) 비동기 생성 핸들러
    규칙: THUMB/TMB_{uuid}_{SIZE}.WEBP
    """
    asset_id = task.payload.get("asset_id")
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        raise ValueError(f"자산을 찾을 수 없습니다: {asset_id}")

    abs_file_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
    if not os.path.exists(abs_file_path):
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {abs_file_path}")

    # 이미지 처리
    with Image.open(abs_file_path) as img:
        meta_info = asset.meta_info or {}
        if "thumbs" not in meta_info: meta_info["thumbs"] = {}
        
        dir_name = os.path.dirname(abs_file_path)
        thumb_dir = os.path.join(dir_name, config.THUMB_FOLDER_NAME)
        media_service.safe_makedirs(thumb_dir)
        
        # 파일명에서 UUID 추출 (IMG_uuid.JPG -> uuid)
        base_name = os.path.basename(asset.file_path)
        unique_id = base_name.replace(config.PREFIX['IMAGE'], "").split('.')[0]
        
        if img.mode in ("P", "CMYK"):
            img = img.convert("RGB")
            
        # SM, MD, LG 사이즈 비동기 생성 (전체 복구 지원)
        for key in ["SM", "MD", "LG"]:
            cfg = config.MEDIA_THUMB_CONFIG[key]
            t_img = img.copy()
            t_img.thumbnail(cfg["size"], Image.Resampling.LANCZOS)
            
            # TMB_{uuid}_{SIZE}.WEBP
            t_filename = f"{config.PREFIX['THUMB']}{unique_id}_{cfg['suffix']}.WEBP"
            t_abs_path = os.path.join(thumb_dir, t_filename)
            t_rel_path = os.path.join(os.path.dirname(asset.file_path), config.THUMB_FOLDER_NAME, t_filename).replace("\\", "/")
            
            t_img.save(t_abs_path, "WEBP", quality=config.WEBP_QUALITY)
            os.chmod(t_abs_path, 0o644) # [v3.2] 비동기 썸네일 읽기 권한 보장
            meta_info["thumbs"][key.lower()] = t_rel_path
            
            # SM 사이즈인 경우 레거시 필드인 thumbnail_path도 함께 업데이트
            if key == "SM":
                asset.thumbnail_path = t_rel_path

        asset.meta_info = meta_info
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(asset, "meta_info")
        db.commit()
    
    task.progress_pct = 100
    logger.info(f"🎨 고해상도 썸네일 생성 완료: {asset.id}")
    return {"status": "success", "asset_id": asset_id}

import shutil
from domain.system.task_service import enqueue_task

@register_handler("MEDIA_BACKUP")
async def handle_media_backup(task: SystemTask, db: Session):
    """
    [v3.2] 미디어 비동기 백업 핸들러
    원본 파일을 PRIVATE 계층으로 복사하고 새 DB 레코드를 생성합니다.
    """
    asset_ids = task.payload.get("asset_ids", [])
    user_id = task.payload.get("target_user_id")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    backup_sub_path = f"USERS/{user_id}/ADMIN_BACKUPS/{today_str}"
    backup_root = os.path.join(config.MEDIA_ROOT, "PRIVATE", backup_sub_path)
    
    success_count = 0
    errors = []
    
    assets = db.query(MediaAsset).filter(MediaAsset.id.in_(asset_ids)).all()
    for asset in assets:
        try:
            src_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
            if not os.path.exists(src_path):
                errors.append(f"Source not found: {asset.original_name}")
                continue
                
            category_dir = "IMAGE" if asset.category == "image" else "DOCUMENT"
            target_dir = os.path.join(backup_root, category_dir)
            media_service.safe_makedirs(target_dir)
            
            dst_path = os.path.join(target_dir, asset.original_name)
            # 중복 회피
            counter = 1
            name, ext = os.path.splitext(asset.original_name)
            while os.path.exists(dst_path):
                dst_path = os.path.join(target_dir, f"{name}({counter}){ext}")
                counter += 1
                
            shutil.copy2(src_path, dst_path)
            os.chmod(dst_path, 0o644) # [v3.2] 백업 파일 읽기 권한 보장
            
            # DB 레코드 생성
            new_asset = MediaAsset(
                user_id=user_id,
                access_level="PRIVATE",
                app_id="admin_backup",
                target_id=today_str,
                original_name=os.path.basename(dst_path),
                file_path=os.path.join("PRIVATE", backup_sub_path, category_dir, os.path.basename(dst_path)),
                file_size=asset.file_size,
                mime_type=asset.mime_type,
                category=asset.category,
                meta_info={} 
            )
            db.add(new_asset)
            db.flush() # ID 확보
            
            # 이미지인 경우 썸네일 생성 예약
            if asset.category == "image":
                enqueue_task(
                    db=db,
                    task_type="THUMB_GEN",
                    payload={"asset_id": new_asset.id},
                    unique_key=f"thumb-gen-{new_asset.id}",
                    priority=7
                )
            
            success_count += 1
        except Exception as e:
            errors.append(f"Backup failed for {asset.id}: {str(e)}")

    db.commit()
    logger.info(f"💾 백업 완료 (ID: {task.id}): {success_count}개 성공, {len(errors)}개 실패")
    return {"status": "finished", "success_count": success_count, "errors": errors}

@register_handler("MEDIA_GC")
async def handle_media_gc(task: SystemTask, db: Session):
    """
    [v3.2] 시스템 가비지 컬렉션(GC) 핸들러
    """
    from domain.media.media_gc_service import MediaGCService
    
    # payload에서 실행할 작업 인덱스 목록을 가져옴 (기본값: [1,2,3,4,5] 전체)
    task_indices = task.payload.get("indices", [1, 2, 3, 4, 5])
    
    service = MediaGCService(db)
    logger.info(f"🧹 시스템 정리를 시작합니다 (작업: {task_indices})")
    
    results = service.run_tasks(task_indices)
    
    return {"status": "finished", "results": results}

# --- [핵심 엔진] 워커 루프 ---

async def run_task_worker():
    """[워커 엔진] PENDING 상태인 작업을 찾아 하나씩 처리하는 무한 루프"""
    logger.info("🚀 시스템 태스크 워커(v3.1) 가동 시작!")
    
    while True:
        db = SessionLocal()
        try:
            # 지금 해야 할 일 조회 (우선순위 및 예약시간 고려)
            task = db.query(SystemTask).filter(
                and_(
                    SystemTask.status == "PENDING",
                    SystemTask.scheduled_at <= datetime.now()
                )
            ).order_by(SystemTask.priority.asc(), SystemTask.created_at.asc()).first()

            if not task:
                await asyncio.sleep(2)
                continue

            # 작업 점유
            task.status = "RUNNING"
            task.started_at = datetime.now()
            task.worker_id = "main_worker"
            db.commit()

            logger.info(f"⚙️  작업 시작: {task.task_type} (ID: {task.id})")

            handler = TASK_HANDLERS.get(task.task_type)
            if not handler:
                raise Exception(f"처리기를 찾을 수 없는 작업 타입입니다: {task.task_type}")

            try:
                result_data = await handler(task, db)
                task.status = "SUCCESS"
                task.result = result_data
                task.completed_at = datetime.now()
                task.progress_pct = 100
                logger.info(f"✅ 작업 완료: {task.id}")
            except Exception as e:
                db.rollback()
                task.retry_count += 1
                task.error_log = traceback.format_exc()
                if task.retry_count >= task.max_retries:
                    task.status = "FAILED"
                    logger.error(f"❌ 작업 영구 실패: {task.id}")
                else:
                    task.status = "PENDING"
                    logger.warning(f"⚠️ 작업 재시도 예정: {task.id}")

            db.commit()

        except Exception as global_e:
            logger.error(f"🚨 워커 엔진 오류: {str(global_e)}")
            await asyncio.sleep(5)
        finally:
            db.close()

        await asyncio.sleep(0.1)
