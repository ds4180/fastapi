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
        os.makedirs(thumb_dir, exist_ok=True)
        
        # 파일명에서 UUID 추출 (IMG_uuid.JPG -> uuid)
        base_name = os.path.basename(asset.file_path)
        unique_id = base_name.replace(config.PREFIX['IMAGE'], "").split('.')[0]
        
        if img.mode in ("P", "CMYK"):
            img = img.convert("RGB")
            
        # MD, LG 사이즈 비동기 생성
        for key in ["MD", "LG"]:
            cfg = config.MEDIA_THUMB_CONFIG[key]
            t_img = img.copy()
            t_img.thumbnail(cfg["size"], Image.Resampling.LANCZOS)
            
            # TMB_{uuid}_{SIZE}.WEBP
            t_filename = f"{config.PREFIX['THUMB']}{unique_id}_{cfg['suffix']}.WEBP"
            t_abs_path = os.path.join(thumb_dir, t_filename)
            t_rel_path = os.path.join(os.path.dirname(asset.file_path), config.THUMB_FOLDER_NAME, t_filename).replace("\\", "/")
            
            t_img.save(t_abs_path, "WEBP", quality=config.WEBP_QUALITY)
            meta_info["thumbs"][key.lower()] = t_rel_path

        asset.meta_info = meta_info
        db.commit()
    
    task.progress_pct = 100
    logger.info(f"🎨 고해상도 썸네일 생성 완료: {asset.id}")
    return {"status": "success", "asset_id": asset_id}

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
