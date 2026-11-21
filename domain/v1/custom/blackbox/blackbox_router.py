"""
============================================================================
[블랙박스 비디오 관리 라우터 (domain/v1/custom/blackbox/blackbox_router.py)]
============================================================================

💡 역할:
- 운전기사(현장): 차량별 현재 비디오 위치/본체 스펙 조회, 비디오 교체 요청 및 내 요청 확인
- 관리자(운영): 비디오 장부, 2자리 display_num 중복방지, 차량 본체(led_count 포함) 관리,
  장착/교체/회수 원클릭 처리, 비디오↔차량 사용기간 양방향 역조회
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from core.deps import get_current_user, require_app_permission
from core.audit import safe_log_audit
from models import BlackboxDevice, BlackboxVideo, BlackboxRequest, User

from . import blackbox_schema as schema
from . import blackbox_crud as crud

router = APIRouter(prefix="/v1/custom/blackbox", tags=["Custom Blackbox"])

check_blackbox_read = require_app_permission("blackbox", action="read")
check_blackbox_write = require_app_permission("blackbox", action="write")


# ============================================================================
# 1. 운전기사(사용자) 전용 엔드포인트 (/v1/custom/blackbox 화면)
# ============================================================================
@router.get("/my-status")
def get_driver_blackbox_status(
    vehicle_no: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """차량 풀 목록, 선택 차량의 현재 장착 비디오 및 본체 스펙을 조회합니다."""
    vehicles = crud.get_vehicle_pool()
    devices = crud.list_devices(db)
    videos = crud.list_videos(db, location_type="VEHICLE", include_disposed=False)

    device_by_vno = {d["vehicle_no"]: d for d in devices}
    video_by_vno = {v["current_vehicle_no"]: v for v in videos if v.get("current_vehicle_no")}

    target_vno = vehicle_no.strip() if vehicle_no else None
    return {
        "vehicles": vehicles,
        "device_by_vehicle": device_by_vno,
        "video_by_vehicle": video_by_vno,
        "selected_vehicle_no": target_vno,
        "selected_device": device_by_vno.get(target_vno) if target_vno else None,
        "selected_video": video_by_vno.get(target_vno) if target_vno else None,
    }


@router.get("/requests/me")
def list_my_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """로그인한 운전기사의 블랙박스 교체 요청 내역을 조회합니다."""
    rows = (
        db.query(BlackboxRequest)
        .filter(BlackboxRequest.requester_id == current_user.id, BlackboxRequest.is_deleted == False)
        .order_by(BlackboxRequest.created_at.desc(), BlackboxRequest.id.desc())
        .limit(100)
        .all()
    )
    return {"requests": [crud.serialize_request(r) for r in rows]}


@router.post("/requests")
def submit_driver_request(
    payload: schema.DriverRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """운전기사가 사무실에 블랙박스 비디오 교체를 요청합니다."""
    req = crud.create_driver_request(db, current_user, payload)
    safe_log_audit(
        db=db,
        app_id="blackbox",
        log_type="CHANGE",
        action="BLACKBOX_REQUEST_CREATED",
        title=f"[블랙박스] {req.vehicle_no}호 비디오 교체 요청 (#{req.id})",
        user=current_user,
        resource_type="blackbox_request",
        resource_id=str(req.id),
        message=f"'{req.requester_name}' 기사님이 {req.vehicle_no}호 비디오 교체를 요청했습니다. ({req.reason_type})",
    )

    # 🔔 [Web Push] 블랙박스 확인/교체 요청 접수 시 사무실/담당 직원에게 푸시 발송
    try:
        from domain.push.push_service import (
            is_push_domain_enabled,
            dispatch_push_async,
            send_push_to_app_users,
        )
        if is_push_domain_enabled(db, "blackbox_request"):
            dispatch_push_async(
                send_push_to_app_users,
                app_id="blackbox",
                title=f"[블랙박스] {req.vehicle_no}호 영상 확인/교체 요청",
                body=f"{req.requester_name} 기사님이 {req.vehicle_no}호 요청을 접수했습니다. ({req.reason_type})",
                url="/v1/admin/blackbox",
                action="read",
                exclude_user_id=current_user.id,
            )
    except Exception:
        pass

    return {"message": "교체 요청이 접수되었습니다.", "request": crud.serialize_request(req)}


# ============================================================================
# 2. 관리자 관제 엔드포인트 (/v1/admin/blackbox 화면)
# ============================================================================
@router.get("/admin/summary")
def get_admin_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_read),
):
    all_videos = db.query(BlackboxVideo).filter(BlackboxVideo.is_deleted == False).all()
    active_videos = [v for v in all_videos if v.disposal_date is None]
    office_count = sum(1 for v in active_videos if v.location_type == "OFFICE")
    vehicle_count = sum(1 for v in active_videos if v.location_type == "VEHICLE")
    disposed_count = sum(1 for v in all_videos if v.disposal_date is not None)
    pending_requests = (
        db.query(BlackboxRequest)
        .filter(BlackboxRequest.status == "PENDING", BlackboxRequest.is_deleted == False)
        .count()
    )
    device_count = db.query(BlackboxDevice).filter(BlackboxDevice.is_deleted == False).count()
    return {
        "total_videos": len(all_videos),
        "active_videos": len(active_videos),
        "office_count": office_count,
        "vehicle_count": vehicle_count,
        "disposed_count": disposed_count,
        "pending_requests": pending_requests,
        "device_count": device_count,
        "vehicles": crud.get_vehicle_pool(),
    }


@router.get("/admin/videos")
def admin_list_videos(
    location_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    include_disposed: bool = Query(True),
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_read),
):
    return {
        "videos": crud.list_videos(
            db,
            location_type=location_type,
            search=search,
            include_disposed=include_disposed,
        )
    }


@router.post("/admin/videos")
def admin_create_video(
    payload: schema.VideoCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    obj = crud.create_video(db, payload)
    safe_log_audit(
        db=db,
        app_id="blackbox",
        log_type="CHANGE",
        action="BLACKBOX_VIDEO_CREATED",
        title=f"[블랙박스] 비디오 등록 {obj.video_no} (#{obj.display_num})",
        user=admin,
        resource_type="blackbox_video",
        resource_id=str(obj.id),
    )
    return {"message": "등록 완료", "video": crud.serialize_video(obj)}


@router.patch("/admin/videos/{video_id}")
def admin_update_video(
    video_id: int,
    payload: schema.VideoUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    obj = crud.update_video(db, video_id, payload)
    return {"message": "수정 완료", "video": crud.serialize_video(obj)}


@router.delete("/admin/videos/{video_id}")
def admin_delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    crud.delete_video(db, video_id)
    return {"message": "삭제 완료", "id": video_id}


@router.post("/admin/videos/{video_id}/mount")
def admin_mount_video(
    video_id: int,
    payload: schema.VideoMountReq,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    video = (
        db.query(BlackboxVideo)
        .filter(BlackboxVideo.id == video_id, BlackboxVideo.is_deleted == False)
        .first()
    )
    if not video:
        raise HTTPException(status_code=404, detail="비디오를 찾을 수 없습니다.")
    crud.mount_video_to_vehicle(
        db,
        video,
        vehicle_no=payload.vehicle_no,
        mounted_at=payload.mounted_at,
        notes=payload.notes,
        auto_swap=payload.auto_swap,
    )
    db.commit()
    db.refresh(video)
    safe_log_audit(
        db=db,
        app_id="blackbox",
        log_type="CHANGE",
        action="BLACKBOX_VIDEO_MOUNTED",
        title=f"[블랙박스] {video.video_no}(#{video.display_num}) → {video.current_vehicle_no}호 장착",
        user=admin,
        resource_type="blackbox_video",
        resource_id=str(video.id),
    )
    return {"message": "차량 장착 완료", "video": crud.serialize_video(video)}


@router.post("/admin/videos/{video_id}/unmount")
def admin_unmount_video(
    video_id: int,
    payload: schema.VideoUnmountReq,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    video = (
        db.query(BlackboxVideo)
        .filter(BlackboxVideo.id == video_id, BlackboxVideo.is_deleted == False)
        .first()
    )
    if not video:
        raise HTTPException(status_code=404, detail="비디오를 찾을 수 없습니다.")
    prev_vno = video.current_vehicle_no
    crud.unmount_video_to_office(
        db,
        video,
        removed_at=payload.removed_at,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(video)
    safe_log_audit(
        db=db,
        app_id="blackbox",
        log_type="CHANGE",
        action="BLACKBOX_VIDEO_UNMOUNTED",
        title=f"[블랙박스] {video.video_no}(#{video.display_num}) {prev_vno or ''}호 → 사무실 회수",
        user=admin,
        resource_type="blackbox_video",
        resource_id=str(video.id),
    )
    return {"message": "사무실 회수 완료", "video": crud.serialize_video(video)}


def _parse_optional_date(val: Optional[str], field_name: str) -> Optional[date]:
    s = (val or "").strip()
    if not s or s.lower() in {"undefined", "null"}:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"올바른 날짜 형식이 아닙니다 ({field_name}): {val}")


@router.get("/admin/usages")
def admin_reverse_lookup_usages(
    video_query: Optional[str] = Query(None),
    vehicle_no: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_read),
):
    """비디오 번호 또는 차량번호·기간 기준 사용기간 역조회"""
    clean_vq = None if not video_query or video_query.strip().lower() in {"undefined", "null"} else video_query.strip()
    clean_vno = None if not vehicle_no or vehicle_no.strip().lower() in {"undefined", "null"} else vehicle_no.strip()
    s_date = _parse_optional_date(start_date, "start_date")
    e_date = _parse_optional_date(end_date, "end_date")
    return {
        "usages": crud.reverse_lookup_usages(
            db,
            video_query=clean_vq,
            vehicle_no=clean_vno,
            start_date=s_date,
            end_date=e_date,
            limit=limit,
        )
    }


@router.get("/admin/devices")
def admin_list_devices(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_read),
):
    return {"devices": crud.list_devices(db, search=search)}


@router.post("/admin/devices")
def admin_create_device(
    payload: schema.DeviceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    obj = crud.create_device(db, payload)
    return {"message": "본체 등록 완료", "device": crud.serialize_device(obj)}


@router.patch("/admin/devices/{device_id}")
def admin_update_device(
    device_id: int,
    payload: schema.DeviceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    obj = crud.update_device(db, device_id, payload)
    return {"message": "본체 수정 완료", "device": crud.serialize_device(obj)}


@router.delete("/admin/devices/{device_id}")
def admin_delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    crud.delete_device(db, device_id)
    return {"message": "본체 삭제 완료", "id": device_id}


@router.get("/admin/requests")
def admin_list_requests(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_read),
):
    q = db.query(BlackboxRequest).filter(BlackboxRequest.is_deleted == False)
    if status:
        q = q.filter(BlackboxRequest.status == status.strip().upper())
    rows = q.order_by(BlackboxRequest.created_at.desc(), BlackboxRequest.id.desc()).limit(200).all()
    return {"requests": [crud.serialize_request(r) for r in rows]}


@router.post("/admin/requests/{req_id}/process")
def admin_process_request(
    req_id: int,
    payload: schema.AdminRequestProcess,
    db: Session = Depends(get_db),
    admin: User = Depends(check_blackbox_write),
):
    req = crud.process_driver_request(db, req_id, payload, admin)
    safe_log_audit(
        db=db,
        app_id="blackbox",
        log_type="CHANGE",
        action="BLACKBOX_REQUEST_PROCESSED",
        title=f"[블랙박스] 교체 요청 #{req.id} {req.status} ({req.vehicle_no}호)",
        user=admin,
        resource_type="blackbox_request",
        resource_id=str(req.id),
    )
    return {"message": "요청 처리 완료", "request": crud.serialize_request(req)}
