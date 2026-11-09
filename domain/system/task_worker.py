import asyncio
import logging
import traceback
import os
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models import SystemTask, MediaAsset
from database import SessionLocal
from domain.media import media_config as config
from PIL import Image
from domain.media import media_service # [v3.2] safe_makedirs 사용을 위해 임포트
from domain.system.task_service import enqueue_task, calculate_next_scheduled_at

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
        logger.warning(f"⚠️ [THUMB_GEN] 자산 부재로 작업 취소: asset_id={asset_id}")
        task.status = "CANCELLED"
        task.progress_pct = 100
        return {"status": "cancelled", "reason": f"자산을 찾을 수 없습니다: {asset_id}"}

    abs_file_path = os.path.join(config.MEDIA_ROOT, asset.file_path)
    if not os.path.exists(abs_file_path):
        logger.warning(f"⚠️ [THUMB_GEN] 원본 파일 부재로 작업 취소: {abs_file_path}")
        task.status = "CANCELLED"
        task.progress_pct = 100
        return {"status": "cancelled", "reason": f"원본 파일을 찾을 수 없습니다: {abs_file_path}"}

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
    
    # payload에서 실행할 작업 인덱스 목록을 가져옴 (기본값: [1,2,3,4,5,6] 전체)
    task_indices = task.payload.get("indices", [1, 2, 3, 4, 5, 6])
    
    service = MediaGCService(db)
    logger.info(f"🧹 시스템 정리를 시작합니다 (작업: {task_indices})")
    
    results = service.run_tasks(task_indices)
    
    return {"status": "finished", "results": results}

@register_handler("DYNAMIC_GROUP_REFRESH")
async def handle_dynamic_group_refresh(task: SystemTask, db: Session):
    """
    [자율신경계 스케줄러] 휴무자, 근무자, 노선별 배차 실 비즈니스 동적 그룹 자동 연산 갱신
    """
    from redis_config import redis_client
    from domain.system.group_service import calculate_and_refresh_dynamic_groups
    
    logger.info("👥 동적 타겟 그룹 실시간 자동 연산을 시작합니다...")
    results = calculate_and_refresh_dynamic_groups(db, redis_client)
    task.progress_pct = 100
    return {"status": "finished", "results": results}

@register_handler("SYSTEM_WATCHDOG_INSPECTION")
async def handle_watchdog_inspection(task: SystemTask, db: Session):
    """
    [자율신경계 Watchdog] 시스템 이상 징후 종합 점검 및 자동 경보 루틴
    """
    from domain.system.watchdog_service import run_watchdog_inspection
    logger.info("⚡ 시스템 Watchdog 자율 점검을 수행합니다...")
    report = run_watchdog_inspection(db)
    task.progress_pct = 100
    return report

@register_handler("DATA_RETENTION_GC")
async def handle_data_retention_gc(task: SystemTask, db: Session):
    """
    [자율신경계 GC] 시스템 데이터 보존 기간 초과 데이터 및 Redis 메모리 자동 정리 (STD-SYS-009)
    """
    from redis_config import rd
    from domain.system.retention_service import run_data_retention_gc
    logger.info("🧹 시스템 데이터 가비지 컬렉션(GC)을 수행합니다...")
    report = run_data_retention_gc(db, rd)
    task.progress_pct = 100
    return report

@register_handler("CHECK_MINIAPP_ALARMS")
async def handle_check_miniapp_alarms(task: SystemTask, db: Session):
    """
    [자율신경계 알람 스케줄러] 미니앱 예약 알람 1분 주기 감시 및 백그라운드 Web Push / WebSocket 실시간 발송
    - target_time <= NOW() 이고 status == 'PENDING'인 ALARM 조회
    - 대상 사원 브라우저로 백그라운드 Web Push 발송 (브라우저 창을 닫아도 모바일/PC OS 팝업 수신)
    - 실시간 WebSocket 미니앱 갱신 신호 브로드캐스트 (접속 중인 화면 즉시 동기화)
    - 중복 울림 방지를 위해 extra_payload['triggered_at'] 기록
    """
    from models.miniapp import MiniappItem
    from domain.push.push_service import send_push_to_user
    from domain.ws.ws_service import manager
    from sqlalchemy.orm.attributes import flag_modified

    now = datetime.now()

    # 📌 target_time이 도래했으나 아직 울리지 않은 PENDING 상태의 ALARM 조회
    pending_alarms = db.query(MiniappItem).filter(
        MiniappItem.category == "ALARM",
        MiniappItem.status == "PENDING",
        MiniappItem.target_time.is_not(None),
        MiniappItem.target_time <= now
    ).all()

    triggered_count = 0
    for alarm in pending_alarms:
        ep = dict(alarm.extra_payload or {})
        # 이미 울린 알람은 건너뜀 (중복 발송 방지)
        if ep.get("triggered_at"):
            continue

        target_user_id = alarm.receiver_id or alarm.sender_id
        if not target_user_id:
            continue

        alarm_title = alarm.title or "리마인더 알람"
        if not alarm_title.startswith("⏰"):
            alarm_title = f"⏰ [리마인더] {alarm_title}"

        # 1. 대상 사원에게 백그라운드 Web Push 발송 (브라우저 창 닫아도 OS 팝업 수신!)
        try:
            send_push_to_user(
                user_id=target_user_id,
                title=alarm_title,
                body=alarm.content,
                url=alarm.link or "/v1/pages/miniapps?tab=alarm",
                db=db
            )
        except Exception as pe:
            logger.warning(f"⚠️ [알람 푸시 실패] user={target_user_id}: {pe}")

        # 2. 울림 완료 타임스탬프 기록 (중복 발송 방지)
        ep["triggered_at"] = now.isoformat()
        alarm.extra_payload = ep
        flag_modified(alarm, "extra_payload")
        triggered_count += 1

    if triggered_count > 0:
        db.commit()
        # 3. 실시간 WebSocket 갱신 브로드캐스트 (접속 중인 화면 뱃지/목록 즉시 갱신)
        try:
            await manager.broadcast({
                "type": "MINIAPP_UPDATE",
                "category": "ALARM",
                "triggered_count": triggered_count
            })
        except Exception as we:
            logger.warning(f"⚠️ [알람 웹소켓 브로드캐스트 실패]: {we}")

    logger.info(f"⏰ 미니앱 알람 정기 감시 완료: {triggered_count}건 발송 처리됨 (기준시각: {now.strftime('%H:%M:%S')})")
    task.progress_pct = 100
    return {"status": "finished", "triggered_count": triggered_count, "checked_at": now.isoformat()}

# --- [핵심 엔진] 단일 태스크 처리기 & 워커 루프 ---

def reclaim_stuck_tasks(db: Session) -> int:
    """
    [워커락 자동 회수기 (Stuck Task Auto-Reclaim)]
    워커 프로세스 비정상 종료(컨테이너 재시작, OOM 등)로 인해
    장시간 RUNNING 상태로 고착된 태스크를 감지하여 자동 복구합니다.
    """
    now = datetime.now()
    running_tasks = db.query(SystemTask).filter(SystemTask.status == "RUNNING").all()
    reclaimed_count = 0

    for task in running_tasks:
        timeout_sec = task.timeout_sec or 300
        task_timeout = timedelta(seconds=timeout_sec)
        started = task.started_at or task.scheduled_at or now
        elapsed = now - started

        if elapsed > task_timeout:
            logger.warning(
                f"🚨 [워커락 감지] 고착된 RUNNING 태스크 회수: ID={task.id} ({task.task_type}), "
                f"경과={int(elapsed.total_seconds())}초, 타임아웃={timeout_sec}초"
            )
            task.retry_count += 1
            if task.retry_count >= task.max_retries:
                task.status = "FAILED"
                task.completed_at = now
                task.error_log = f"워커 비정상 종료 또는 타임아웃 초과로 고착됨 (경과: {int(elapsed.total_seconds())}초)"
                logger.error(f"❌ [워커락 회수] 최대 재시도 초과로 FAILED 마감: ID={task.id}")

                # 🌟 반복 작업인 경우 시스템 순환 루프가 멈추지 않도록 차기 회차 예약 자동 발행!
                if task.cron_expression or task.repeat_interval:
                    next_time = calculate_next_scheduled_at(
                        cron_expr=task.cron_expression,
                        interval_sec=task.repeat_interval,
                        base_time=now
                    )
                    if next_time:
                        next_unique_key = None
                        if task.unique_key:
                            base_parts = task.unique_key.split(":")
                            base_key = ":".join(base_parts[:2]) if len(base_parts) >= 2 else task.unique_key
                            next_unique_key = f"{base_key}:{next_time.strftime('%Y%m%d%H%M%S')}"
                        enqueue_task(
                            db=db,
                            task_type=task.task_type,
                            payload=task.payload,
                            priority=task.priority,
                            scheduled_at=next_time,
                            cron_expression=task.cron_expression,
                            repeat_interval=task.repeat_interval,
                            unique_key=next_unique_key,
                            parent_id=task.id,
                            tags=task.tags
                        )
                        logger.info(f"🔄 [자가치유] 고착 실패 후 차기 스케줄 발행 완료: ID={task.id} -> 차기 예약={next_time}")
            else:
                task.status = "PENDING"
                task.worker_id = None
                task.scheduled_at = now
                task.error_log = f"워커 비정상 종료 감지로 인한 자동 재시도 예약 (시도 {task.retry_count}/{task.max_retries})"
                logger.info(f"🔄 [워커락 회수] PENDING 복귀 및 즉시 재실행 예약: ID={task.id}")

            reclaimed_count += 1

    if reclaimed_count > 0:
        db.commit()

    return reclaimed_count


async def process_next_task(db: Session, worker_id: str) -> bool:
    """
    [단일 태스크 안전 선점 및 실행기]
    - 분산 환경 안전 선점 (PostgreSQL: FOR UPDATE SKIP LOCKED)
    - 핸들러 실행
    - 성공 시: SUCCESS 처리 및 자율 순환 루프(Cron/Interval 차기 작업 자동 발행)
    - 실패 시: 지수 백오프(Exponential Backoff) 기반 scheduled_at 연기 또는 FAILED 마감
    - 반환값: 작업을 하나라도 처리했으면 True, 처리할 작업이 없었으면 False
    """
    query = db.query(SystemTask).filter(
        and_(
            SystemTask.status == "PENDING",
            SystemTask.scheduled_at <= datetime.now()
        )
    ).order_by(SystemTask.priority.asc(), SystemTask.created_at.asc())

    # PostgreSQL 다중 워커 환경에서는 SKIP LOCKED 적용
    if db.bind and db.bind.dialect.name == "postgresql":
        task = query.with_for_update(skip_locked=True).first()
    else:
        task = query.first()

    if not task:
        return False

    # 작업 점유
    task.status = "RUNNING"
    task.started_at = datetime.now()
    task.worker_id = worker_id
    db.commit()

    logger.info(f"⚙️  작업 시작 [{worker_id}]: {task.task_type} (ID: {task.id})")

    handler = TASK_HANDLERS.get(task.task_type)
    if not handler:
        task.status = "FAILED"
        task.completed_at = datetime.now()
        task.error_log = f"처리기를 찾을 수 없는 작업 타입입니다: {task.task_type}"
        db.commit()
        logger.error(f"❌ 작업 타입 미존재 오류: {task.id} ({task.task_type})")
        return True

    try:
        result_data = await handler(task, db)
        task.status = "SUCCESS"
        task.result = result_data or {}
        task.completed_at = datetime.now()
        task.progress_pct = 100
        logger.info(f"✅ 작업 완료: {task.id} ({task.task_type})")

        # 🔄 반복 태스크인 경우 자율 재발행 (Self-Reissuing Loop)
        if task.cron_expression or task.repeat_interval:
            next_time = calculate_next_scheduled_at(
                cron_expr=task.cron_expression,
                interval_sec=task.repeat_interval,
                base_time=datetime.now()
            )
            if next_time:
                # 🌟 차기 회차 고유키 발급 (기존 static 키로 인한 DB UNIQUE 충돌 및 차기 생성 누락 방지)
                next_unique_key = None
                if task.unique_key:
                    base_parts = task.unique_key.split(":")
                    base_key = ":".join(base_parts[:2]) if len(base_parts) >= 2 else task.unique_key
                    next_unique_key = f"{base_key}:{next_time.strftime('%Y%m%d%H%M%S')}"

                enqueue_task(
                    db=db,
                    task_type=task.task_type,
                    payload=task.payload,
                    priority=task.priority,
                    scheduled_at=next_time,
                    cron_expression=task.cron_expression,
                    repeat_interval=task.repeat_interval,
                    unique_key=next_unique_key,
                    parent_id=task.id,
                    created_by=task.created_by,
                    tags=task.tags,
                    max_retries=task.max_retries,
                    timeout_sec=task.timeout_sec
                )
                logger.info(f"🔄 반복 태스크 차기 발행 완료: ID={task.id} -> 차기 예약={next_time} (Key: {next_unique_key})")

        db.commit()
        return True

    except Exception as e:
        task_id = task.id
        db.rollback()
        # 🌟 세션 롤백 후 깨끗한 상태에서 태스크를 새로 조회(reload)하여 detached 에러 및 상태 유실 방어
        failed_task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
        if failed_task:
            failed_task.retry_count += 1
            failed_task.error_log = traceback.format_exc()
            if failed_task.retry_count >= failed_task.max_retries:
                failed_task.status = "FAILED"
                failed_task.completed_at = datetime.now()
                logger.error(f"❌ 작업 영구 실패 (최대 재시도 초과): {failed_task.id}")
                db.commit()
                try:
                    from domain.system.watchdog_service import check_and_alert_task_failure
                    check_and_alert_task_failure(db, failed_task_id=failed_task.id)
                except Exception as we:
                    logger.warning(f"⚠️ Watchdog 경보 트리거 오류: {we}")
                return True
            else:
                # 지수 백오프 적용 (1차: 10초, 2차: 40초, 3차: 80초, 최대 300초)
                delay_sec = min(300, (2 ** failed_task.retry_count) * 10)
                failed_task.scheduled_at = datetime.now() + timedelta(seconds=delay_sec)
                failed_task.status = "PENDING"
                logger.warning(f"⚠️ 작업 재시도 예약 (시도 {failed_task.retry_count}/{failed_task.max_retries}, {delay_sec}초 후): ID={failed_task.id}")
                db.commit()

        return True


async def run_task_worker():
    """[워커 엔진] PENDING 상태인 작업을 찾아 하나씩 안전하게 처리하는 무한 루프"""
    worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    logger.info(f"🚀 시스템 태스크 워커(v3.2 자율신경계) 가동 시작! (Worker ID: {worker_id})")
    
    # 🛡️ 워커 최초 기동 시: 이전 프로세스 비정상 종료로 고착된 RUNNING 태스크 즉각 회수
    init_db = SessionLocal()
    try:
        recovered = reclaim_stuck_tasks(init_db)
        if recovered > 0:
            logger.info(f"✨ [워커 기동 회수] 잔여 고착 태스크 {recovered}건 안전 복구 완료")
    except Exception as ie:
        logger.warning(f"⚠️ 초기 고착 태스크 회수 실패: {ie}")
    finally:
        init_db.close()

    last_reclaim_check = datetime.now()

    while True:
        db = SessionLocal()
        try:
            # 🛡️ 60초마다 워커락(고착 RUNNING) 정기 감시 및 자동 치유
            now_check = datetime.now()
            if (now_check - last_reclaim_check).total_seconds() >= 60:
                last_reclaim_check = now_check
                reclaim_stuck_tasks(db)

            processed = await process_next_task(db, worker_id)
            if not processed:
                await asyncio.sleep(2)
                continue
        except Exception as global_e:
            logger.error(f"🚨 워커 엔진 오류: {str(global_e)}")
            await asyncio.sleep(5)
        finally:
            db.close()

        await asyncio.sleep(0.1)
