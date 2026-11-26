import asyncio
import inspect
import logging
import shutil
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

@register_handler("DISPATCH_AUTO_ANNOUNCE")
def handle_dispatch_auto_announce(task: SystemTask, db: Session):
    """명일 배차 자동 고지 시각(D-1 xx:yy)을 감시하여 자동 확정 및 알림/웹푸시를 발송합니다."""
    from domain.v1.dispatch.dispatch_service import check_and_run_auto_announce

    res = check_and_run_auto_announce(db)
    task.progress_pct = 100
    return res


@register_handler("MEDIA_ISOLATE")
def handle_media_isolate(task: SystemTask, db: Session):
    """
    [v3.5] 미디어 격리 처리기 (원본 + 썸네일 세트 격리, has_original=False 복제본 대응)
    규칙: .DEL_{YYYYMMDD}_{기존파일명}
    """
    file_path = task.payload.get("file_path")
    asset_id = task.payload.get("asset_id")
    if not file_path:
        raise FileNotFoundError("file_path가 비어 있습니다.")

    today_str = datetime.now().strftime("%Y%m%d")
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    isolated_count = 0

    # 1. 원본 파일 격리 (복제본 등 원본 미포함 자산은 건너뜀)
    if os.path.exists(file_path):
        if not base_name.startswith(config.PREFIX['DELETE']):
            new_name = f"{config.PREFIX['DELETE']}{today_str}_{base_name}"
            new_path = os.path.join(dir_name, new_name)
            os.rename(file_path, new_path)
            isolated_count += 1
            logger.info(f"🛡️ 원본 격리 완료: {new_name}")

    # 2. 썸네일 세트 격리 (IMG_ 접두사 제거 후 UUID 매칭)
    thumb_dir = os.path.join(dir_name, config.THUMB_FOLDER_NAME)
    if os.path.exists(thumb_dir):
        uuid_key = os.path.splitext(base_name)[0]
        if uuid_key.startswith(config.PREFIX['IMAGE']):
            uuid_key = uuid_key[len(config.PREFIX['IMAGE']):]
        for t_file in os.listdir(thumb_dir):
            if uuid_key and uuid_key in t_file and not t_file.startswith(config.PREFIX['DELETE']):
                old_t_path = os.path.join(thumb_dir, t_file)
                new_t_path = os.path.join(thumb_dir, f"{config.PREFIX['DELETE']}{today_str}_{t_file}")
                os.rename(old_t_path, new_t_path)
                isolated_count += 1
        if isolated_count > 0:
            logger.info(f"🛡️ 썸네일 세트 격리 완료 (asset_id={asset_id})")

    task.progress_pct = 100
    return {"status": "isolated" if isolated_count > 0 else "already_absent", "isolated_count": isolated_count, "date": today_str}

@register_handler("THUMB_GEN")
def handle_thumb_gen(task: SystemTask, db: Session):
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

    # 이미지 처리 (동적 정책 해상도 및 WebP 품질 반영)
    from domain.media.media_policy_service import get_media_settings, get_thumb_specs_from_settings
    from domain.media.media_explorer_service import extract_asset_uuid

    settings = get_media_settings(db)
    thumb_specs = get_thumb_specs_from_settings(settings)
    webp_quality = int(settings.get("webp_quality", config.WEBP_QUALITY))

    with Image.open(abs_file_path) as img:
        meta_info = asset.meta_info or {}
        if "thumbs" not in meta_info:
            meta_info["thumbs"] = {}

        dir_name = os.path.dirname(abs_file_path)
        thumb_dir = os.path.join(dir_name, config.THUMB_FOLDER_NAME)
        media_service.safe_makedirs(thumb_dir)

        unique_id = extract_asset_uuid(asset.file_path)

        if img.mode in ("P", "CMYK"):
            img = img.convert("RGB")

        # SM, MD, LG 사이즈 비동기 생성 (전체 복구 지원)
        for key in ("SM", "MD", "LG"):
            cfg = thumb_specs[key]
            t_img = img.copy()
            t_img.thumbnail(cfg["size"], Image.Resampling.LANCZOS)

            t_filename = f"{config.PREFIX['THUMB']}{unique_id}_{cfg['suffix']}.WEBP"
            t_abs_path = os.path.join(thumb_dir, t_filename)
            t_rel_path = os.path.join(os.path.dirname(asset.file_path), config.THUMB_FOLDER_NAME, t_filename).replace("\\", "/")

            t_img.save(t_abs_path, "WEBP", quality=webp_quality)
            os.chmod(t_abs_path, 0o644)
            meta_info["thumbs"][key.lower()] = t_rel_path

            if key == "SM":
                asset.thumbnail_path = t_rel_path

        asset.meta_info = meta_info
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(asset, "meta_info")
        db.commit()
    
    task.progress_pct = 100
    logger.info(f"🎨 고해상도 썸네일 생성 완료: {asset.id}")
    return {"status": "success", "asset_id": asset_id}

@register_handler("MEDIA_BACKUP")
def handle_media_backup(task: SystemTask, db: Session):
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
    
    from domain.media.media_explorer_service import resolve_best_fallback_abs

    assets = db.query(MediaAsset).filter(MediaAsset.id.in_(asset_ids)).all()
    for asset in assets:
        try:
            src_path, resolved_display, used_fallback_thumb = resolve_best_fallback_abs(asset)
            if not src_path:
                errors.append(f"Source not found: {asset.original_name}")
                continue

            category_dir = "IMAGE" if asset.category == "image" else "DOCUMENT"
            target_dir = os.path.join(backup_root, category_dir)
            media_service.safe_makedirs(target_dir)

            backup_uuid = str(uuid.uuid4())
            if asset.category == "image":
                ext = ".WEBP" if used_fallback_thumb else (os.path.splitext(src_path)[1].upper() or ".JPG")
                dst_filename = f"{config.PREFIX['IMAGE']}{backup_uuid}{ext}"
                orig_display = resolved_display
            else:
                orig_stem, orig_ext = os.path.splitext(asset.original_name)
                ext = (orig_ext or os.path.splitext(src_path)[1]).upper()
                dst_filename = f"{config.PREFIX['DOC']}{backup_uuid[:8]}_{orig_stem or 'backup'}{ext}"
                orig_display = asset.original_name

            dst_path = os.path.join(target_dir, dst_filename)
            shutil.copy2(src_path, dst_path)
            os.chmod(dst_path, 0o644) # [v3.2] 백업 파일 읽기 권한 보장

            actual_size = os.path.getsize(dst_path)
            actual_mime = "image/webp" if used_fallback_thumb else asset.mime_type

            # DB 레코드 생성
            new_asset = MediaAsset(
                user_id=user_id,
                access_level="PRIVATE",
                app_id="admin_backup",
                target_id=today_str,
                original_name=orig_display,
                file_path=os.path.join("PRIVATE", backup_sub_path, category_dir, dst_filename).replace("\\", "/"),
                file_size=actual_size,
                mime_type=actual_mime,
                category=asset.category,
                meta_info={
                    "original_name": orig_display,
                    "backed_up_from": asset.id,
                    "has_original": True,
                }
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
def handle_media_gc(task: SystemTask, db: Session):
    """
    [v3.2] 시스템 가비지 컬렉션(GC) 핸들러
    """
    from domain.media.media_gc_service import MediaGCService

    service = MediaGCService(db)
    task_indices = task.payload.get("indices") or service.settings.get("default_gc_indices", [1, 2, 3, 4, 5, 6])
    logger.info(f"🧹 시스템 정리를 시작합니다 (작업: {task_indices})")

    results = service.run_tasks(task_indices)
    
    return {"status": "finished", "results": results}

@register_handler("DYNAMIC_GROUP_REFRESH")
def handle_dynamic_group_refresh(task: SystemTask, db: Session):
    """
    [자율신경계 스케줄러] 휴무자, 근무자, 노선별 배차 실 비즈니스 동적 그룹 자동 연산 갱신
    """
    from redis_config import rd
    from domain.system.group_service import calculate_and_refresh_dynamic_groups

    logger.info("👥 동적 타겟 그룹 실시간 자동 연산을 시작합니다...")
    results = calculate_and_refresh_dynamic_groups(db, rd)
    task.progress_pct = 100
    return {"status": "finished", "results": results}

@register_handler("SYSTEM_WATCHDOG_INSPECTION")
def handle_watchdog_inspection(task: SystemTask, db: Session):
    """
    [자율신경계 Watchdog] 시스템 이상 징후 종합 점검 및 자동 경보 루틴
    """
    from domain.system.watchdog_service import run_watchdog_inspection
    logger.info("⚡ 시스템 Watchdog 자율 점검을 수행합니다...")
    report = run_watchdog_inspection(db)
    task.progress_pct = 100
    return report

@register_handler("DATA_RETENTION_GC")
def handle_data_retention_gc(task: SystemTask, db: Session):
    """
    [자율신경계 GC] 시스템 데이터 보존 기간 초과 데이터 및 Redis 메모리 자동 정리 (STD-SYS-009)
    """
    from redis_config import rd
    from domain.system.retention_service import run_data_retention_gc
    logger.info("🧹 시스템 데이터 가비지 컬렉션(GC)을 수행합니다...")
    report = run_data_retention_gc(db, rd)
    task.progress_pct = 100
    return report


def _process_pending_miniapp_alarms_sync(db: Session) -> tuple[int, list[int], datetime]:
    """미니앱 알람 DB 조회 + 동기 Web Push 발송 + 커밋 (워커 스레드풀에서 실행)"""
    from models.miniapp import MiniappItem
    from domain.push.push_service import send_push_to_user
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
    notified_user_ids: set[int] = set()
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
        notified_user_ids.add(int(target_user_id))

    if triggered_count > 0:
        db.commit()

    return triggered_count, sorted(notified_user_ids), now


@register_handler("CHECK_MINIAPP_ALARMS")
async def handle_check_miniapp_alarms(task: SystemTask, db: Session):
    """
    [자율신경계 알람 스케줄러] 미니앱 예약 알람 1분 주기 감시 및 백그라운드 Web Push / WebSocket 실시간 발송
    - 동기 DB/Web Push 구간은 asyncio.to_thread로 격리하여 메인 이벤트 루프 블로킹을 원천 차단합니다.
    - WebSocket 갱신 신호는 알람 대상 사원에게만 정밀 타겟 전송(send_to_users)합니다.
    """
    from domain.ws.ws_service import manager

    triggered_count, notified_user_ids, now = await asyncio.to_thread(_process_pending_miniapp_alarms_sync, db)

    if triggered_count > 0 and notified_user_ids:
        # 3. 알람 대상 사원에게만 실시간 WebSocket 갱신 신호 타겟 전송
        try:
            await manager.send_to_users(
                notified_user_ids,
                {
                    "type": "MINIAPP_UPDATE",
                    "category": "ALARM",
                    "triggered_count": triggered_count,
                },
            )
        except Exception as we:
            logger.warning(f"⚠️ [알람 웹소켓 타겟 전송 실패]: {we}")

    logger.info(f"⏰ 미니앱 알람 정기 감시 완료: {triggered_count}건 발송 처리됨 (기준시각: {now.strftime('%H:%M:%S')})")
    task.progress_pct = 100
    return {"status": "finished", "triggered_count": triggered_count, "checked_at": now.isoformat()}

# --- [핵심 엔진] 단일 태스크 처리기 & 워커 루프 ---

def _schedule_next_recurrence(
    db: Session,
    task: SystemTask,
    base_time: datetime | None = None,
    reason: str = "완료",
) -> SystemTask | None:
    """
    [반복 태스크 자율 재발행 헬퍼 (Self-Reissuing Loop)]
    성공(SUCCESS)·영구실패(FAILED)·고착회수(Stuck FAILED) 어느 경로로 마감되더라도
    정기 스케줄(cron_expression / repeat_interval)이 영구 단절되지 않도록 차기 회차를 예약합니다.
    """
    if not (task.cron_expression or task.repeat_interval):
        return None

    ref_time = base_time or datetime.now()
    next_time = calculate_next_scheduled_at(
        cron_expr=task.cron_expression,
        interval_sec=task.repeat_interval,
        base_time=ref_time,
    )
    if not next_time:
        return None

    # 차기 회차 고유키 발급 (기존 static 키로 인한 DB UNIQUE 충돌 및 차기 생성 누락 방지)
    next_unique_key = None
    if task.unique_key:
        base_parts = task.unique_key.split(":")
        base_key = ":".join(base_parts[:2]) if len(base_parts) >= 2 else task.unique_key
        next_unique_key = f"{base_key}:{next_time.strftime('%Y%m%d%H%M%S')}"

    next_task = enqueue_task(
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
        timeout_sec=task.timeout_sec,
    )
    logger.info(
        f"🔄 [자가치유/{reason}] 반복 태스크 차기 발행 완료: "
        f"ID={task.id} ({task.task_type}) -> 차기 예약={next_time} (Key: {next_unique_key})"
    )
    return next_task


def reclaim_stuck_tasks(db: Session) -> int:
    """
    [워커락 자동 회수기 (Stuck Task Auto-Reclaim)]
    워커 프로세스 비정상 종료(컨테이너 재시작, OOM 등)로 인해
    장시간 RUNNING 상태로 고착된 태스크를 감지하여 자동 복구합니다.
    """
    from domain.system.task_policy_service import get_cached_task_settings

    settings = get_cached_task_settings(db)
    default_timeout = int(settings.get("default_timeout_sec", 300))
    now = datetime.now()
    running_tasks = db.query(SystemTask).filter(SystemTask.status == "RUNNING").all()
    reclaimed_count = 0

    for task in running_tasks:
        timeout_sec = task.timeout_sec or default_timeout
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
                _schedule_next_recurrence(db, task, base_time=now, reason="고착 실패")
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


def _claim_next_task_sync(db: Session, worker_id: str) -> tuple[SystemTask | None, int | None, str | None, int]:
    """다음 실행 대기 태스크를 안전하게 선점(SKIP LOCKED)하고 RUNNING으로 전환합니다. (워커 스레드 실행)"""
    from domain.system.task_policy_service import get_cached_task_settings

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
        return None, None, None, 300

    cfg = get_cached_task_settings(db)
    default_timeout = int(cfg.get("default_timeout_sec", 300))
    eff_timeout = max(1, int(task.timeout_sec or default_timeout))

    task.status = "RUNNING"
    task.started_at = datetime.now()
    task.worker_id = worker_id
    db.commit()
    return task, task.id, task.task_type, eff_timeout


def _mark_missing_handler_sync(db: Session, task: SystemTask, task_id: int, task_type: str) -> None:
    task.status = "FAILED"
    task.completed_at = datetime.now()
    task.error_log = f"처리기를 찾을 수 없는 작업 타입입니다: {task_type}"
    db.commit()
    logger.error(f"❌ 작업 타입 미존재 오류: {task_id} ({task_type})")


def _finalize_task_success_sync(db: Session, task_id: int, worker_id: str, result_data) -> bool:
    """
    태스크 성공 마감 전 소유권(status=='RUNNING' & worker_id 일치)을 재확인합니다.
    이미 타임아웃/회수되어 소유권을 상실한 좀비 실행이 뒤늦게 완료된 경우,
    SUCCESS 덮어쓰기 및 중복 반복 스케줄 발행을 차단합니다.
    """
    fresh_task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not fresh_task or fresh_task.status != "RUNNING" or fresh_task.worker_id != worker_id:
        logger.warning(
            f"⚠️ [소유권 상실 무시] 이미 회수되었거나 다른 워커가 점유한 태스크 완료 결과 폐기: "
            f"ID={task_id}, expected_worker={worker_id}, "
            f"actual_status={getattr(fresh_task, 'status', None)}, actual_worker={getattr(fresh_task, 'worker_id', None)}"
        )
        return False

    is_cancelled = isinstance(result_data, dict) and result_data.get("status") == "cancelled"
    fresh_task.status = "CANCELLED" if is_cancelled else "SUCCESS"
    fresh_task.result = result_data or {}
    fresh_task.completed_at = datetime.now()
    fresh_task.progress_pct = 100
    if is_cancelled:
        logger.info(f"🚫 작업 취소 마감: {fresh_task.id} ({fresh_task.task_type})")
    else:
        logger.info(f"✅ 작업 완료: {fresh_task.id} ({fresh_task.task_type})")

    # 🔄 반복 태스크인 경우 자율 재발행 (Self-Reissuing Loop)
    if not is_cancelled:
        _schedule_next_recurrence(db, fresh_task, base_time=datetime.now(), reason="정상 완료")
    db.commit()
    return True


def _finalize_task_failure_sync(db: Session, task_id: int, error_tb: str) -> None:
    db.rollback()
    # 🌟 세션 롤백 후 깨끗한 상태에서 태스크를 새로 조회(reload)하여 detached 에러 및 상태 유실 방어
    failed_task = db.query(SystemTask).filter(SystemTask.id == task_id).first()
    if not failed_task:
        return

    failed_task.retry_count += 1
    failed_task.error_log = error_tb
    failed_task.worker_id = None
    if failed_task.retry_count >= failed_task.max_retries:
        now_failed = datetime.now()
        failed_task.status = "FAILED"
        failed_task.completed_at = now_failed
        logger.error(f"❌ 작업 영구 실패 (최대 재시도 초과): {failed_task.id} ({failed_task.task_type})")

        # 🌟 반복 스케줄은 일시 장애로 영구 실패하더라도 다음 회차가 끊기지 않도록 자가치유 예약!
        try:
            _schedule_next_recurrence(db, failed_task, base_time=now_failed, reason="오류 마감")
        except Exception as re_err:
            logger.error(f"🚨 [자가치유 실패] 차기 반복 태스크 예약 오류 (ID={failed_task.id}): {re_err}")

        db.commit()
        try:
            from domain.system.watchdog_service import check_and_alert_task_failure
            check_and_alert_task_failure(db, failed_task_id=failed_task.id)
        except Exception as we:
            logger.warning(f"⚠️ Watchdog 경보 트리거 오류: {we}")
    else:
        # 동적 정책 기반 지수 백오프 적용
        from domain.system.task_policy_service import get_cached_task_settings

        cfg = get_cached_task_settings(db)
        base_sec = int(cfg.get("retry_backoff_base_sec", 10))
        max_sec = int(cfg.get("retry_backoff_max_sec", 300))
        delay_sec = min(max_sec, (2 ** failed_task.retry_count) * base_sec)
        failed_task.scheduled_at = datetime.now() + timedelta(seconds=delay_sec)
        failed_task.status = "PENDING"
        logger.warning(
            f"⚠️ 작업 재시도 예약 (시도 {failed_task.retry_count}/{failed_task.max_retries}, "
            f"{delay_sec}초 후): ID={failed_task.id}"
        )
        db.commit()


def _finalize_timeout_isolated_sync(bind, task_id: int, timeout_msg: str) -> None:
    """
    타임아웃 시 기존 db 세션을 건드리지 않고 독립 세션을 열어 실패/재시도를 안전 기록합니다.
    (백그라운드 스레드가 기존 db를 아직 점유 중일 수 있는 레이스 컨디션 원천 차단)
    """
    from sqlalchemy.orm import sessionmaker

    isolated_db = sessionmaker(autocommit=False, autoflush=False, bind=bind)() if bind is not None else SessionLocal()
    try:
        _finalize_task_failure_sync(isolated_db, task_id, timeout_msg)
    finally:
        isolated_db.close()


async def process_next_task(db: Session, worker_id: str) -> bool:
    """
    [단일 태스크 안전 선점 및 실행기]
    - 분산 환경 안전 선점 (PostgreSQL: FOR UPDATE SKIP LOCKED)
    - 동기(def) 핸들러 및 모든 동기 DB 작업은 asyncio.to_thread로 격리 실행하여
      FastAPI 메인 이벤트 루프 프리징을 원천 차단합니다.
    - asyncio.wait_for로 태스크별 timeout_sec 실행 제한을 강제하여 단일 루프 데드락을 방지합니다.
    - 성공 시: 소유권 검증 후 SUCCESS 처리 및 자율 순환 루프(Cron/Interval 차기 작업 자동 발행)
    - 실패/타임아웃 시: 지수 백오프(Exponential Backoff) 기반 scheduled_at 연기 또는 FAILED 마감(+반복 작업 차기 예약 자가치유)
    - 반환값: 작업을 하나라도 처리했으면 True, 처리할 작업이 없었으면 False
    """
    task, task_id, task_type, eff_timeout = await asyncio.to_thread(_claim_next_task_sync, db, worker_id)
    if not task or task_id is None or task_type is None:
        return False

    logger.info(f"⚙️  작업 시작 [{worker_id}]: {task_type} (ID: {task_id}, timeout={eff_timeout}s)")

    handler = TASK_HANDLERS.get(task_type)
    if not handler:
        await asyncio.to_thread(_mark_missing_handler_sync, db, task, task_id, task_type)
        return True

    try:
        if inspect.iscoroutinefunction(handler):
            coro = handler(task, db)
        else:
            coro = asyncio.to_thread(handler, task, db)

        result_data = await asyncio.wait_for(coro, timeout=eff_timeout)
        await asyncio.to_thread(_finalize_task_success_sync, db, task_id, worker_id, result_data)
        return True

    except asyncio.TimeoutError:
        timeout_msg = f"태스크 실행 타임아웃 초과 (제한: {eff_timeout}초, 워커: {worker_id}, 타입: {task_type})"
        logger.error(f"⏱️ [타임아웃 강제 중단] ID={task_id} ({task_type}) - {eff_timeout}초 초과")
        bind = db.get_bind() if hasattr(db, "get_bind") else db.bind
        await asyncio.to_thread(_finalize_timeout_isolated_sync, bind, task_id, timeout_msg)
        return True

    except Exception:
        error_tb = traceback.format_exc()
        await asyncio.to_thread(_finalize_task_failure_sync, db, task_id, error_tb)
        return True


def _startup_reclaim_sync() -> int:
    init_db = SessionLocal()
    try:
        return reclaim_stuck_tasks(init_db)
    finally:
        init_db.close()


def _poll_preflight_sync(do_reclaim: bool) -> dict:
    """동적 설정 조회 및 주기적 고착 태스크 회수 (단기 세션 오픈 후 즉시 반납)"""
    from domain.system.task_policy_service import get_cached_task_settings

    db = SessionLocal()
    try:
        cfg = get_cached_task_settings(db)
        if do_reclaim:
            reclaim_stuck_tasks(db)
        return {
            "worker_enabled": bool(cfg.get("worker_enabled", True)),
            "poll_sleep_sec": max(1, int(cfg.get("worker_poll_interval_sec", 2))),
            "reclaim_interval_sec": max(10, int(cfg.get("reclaim_check_interval_sec", 60))),
        }
    finally:
        db.close()


async def run_task_worker():
    """[워커 엔진] 동적 정책(가동/일시정지, 폴링 주기, 고착 감시 주기)에 따라 동작하는 자율 루프"""
    worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    logger.info(f"🚀 시스템 태스크 워커(v3.6 스레드풀 격리) 가동 시작! (Worker ID: {worker_id})")

    try:
        recovered = await asyncio.to_thread(_startup_reclaim_sync)
        if recovered > 0:
            logger.info(f"✨ [워커 기동 회수] 잔여 고착 태스크 {recovered}건 안전 복구 완료")
    except Exception as ie:
        logger.warning(f"⚠️ 초기 고착 태스크 회수 실패: {ie}")

    last_reclaim_check = datetime.now()
    reclaim_interval_sec = 60

    while True:
        poll_sleep_sec = 2
        try:
            now_check = datetime.now()
            do_reclaim = (now_check - last_reclaim_check).total_seconds() >= reclaim_interval_sec
            if do_reclaim:
                last_reclaim_check = now_check

            preflight = await asyncio.to_thread(_poll_preflight_sync, do_reclaim)
            poll_sleep_sec = preflight["poll_sleep_sec"]
            reclaim_interval_sec = preflight["reclaim_interval_sec"]

            # 일시정지(worker_enabled=False) 상태면 DB 커넥션을 점유하지 않고 대기
            if not preflight["worker_enabled"]:
                await asyncio.sleep(max(2, poll_sleep_sec))
                continue

            db = SessionLocal()
            try:
                processed = await process_next_task(db, worker_id)
            finally:
                db.close()

            if not processed:
                await asyncio.sleep(poll_sleep_sec)
                continue
        except Exception as global_e:
            logger.error(f"🚨 워커 엔진 오류: {str(global_e)}")
            await asyncio.sleep(5)

        await asyncio.sleep(0.1)
