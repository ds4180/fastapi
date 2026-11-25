"""
[블랙박스 비디오 관리 CRUD & 비즈니스 로직 (blackbox_crud.py)]
"""

from datetime import datetime, date, time
import re
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import BlackboxDevice, BlackboxVideo, BlackboxUsage, BlackboxRequest, User
from domain.v1.dispatch.dispatch_builder import load_vehicles_metadata


def get_vehicle_pool() -> List[Dict[str, str]]:
    """vehicles.json에 등록된 전체 차량 목록({vehicle_no, route})을 반환합니다."""
    raw = load_vehicles_metadata() or {}
    items: List[Dict[str, str]] = []
    seen = set()
    for route_name, vlist in raw.items():
        if not isinstance(vlist, list):
            continue
        for v in vlist:
            vno = str(v).strip()
            if not vno or vno in seen:
                continue
            seen.add(vno)
            items.append({"vehicle_no": vno, "route": str(route_name)})
    return sorted(items, key=lambda x: x["vehicle_no"])


def serialize_device(d: BlackboxDevice) -> Dict[str, Any]:
    return {
        "id": d.id,
        "vehicle_no": d.vehicle_no,
        "manufacturer": d.manufacturer,
        "model_name": d.model_name,
        "channels": d.channels,
        "led_count": d.led_count,
        "serial_no": d.serial_no,
        "installed_date": d.installed_date.isoformat() if d.installed_date else None,
        "status": d.status,
        "notes": d.notes,
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else None,
        "updated_at": d.updated_at.strftime("%Y-%m-%d %H:%M") if d.updated_at else None,
    }


def _calc_days_since(dt: Optional[datetime]) -> Optional[int]:
    if not dt:
        return None
    delta = datetime.now().date() - dt.date()
    return max(0, delta.days)


def serialize_video(v: BlackboxVideo) -> Dict[str, Any]:
    days_elapsed = _calc_days_since(v.mounted_at) if v.location_type == "VEHICLE" else None
    if v.location_type == "VEHICLE" and v.current_vehicle_no:
        if days_elapsed is not None:
            location_label = f"{v.current_vehicle_no}번에 {days_elapsed}일전부터 위치함"
        else:
            location_label = f"{v.current_vehicle_no}번 차량 장착중"
    else:
        location_label = "사무실 보관"

    return {
        "id": v.id,
        "video_no": v.video_no,
        "display_num": v.display_num,
        "manufacturer": v.manufacturer,
        "spec": v.spec,
        "serial_no": v.serial_no,
        "purchase_date": v.purchase_date.isoformat() if v.purchase_date else None,
        "disposal_date": v.disposal_date.isoformat() if v.disposal_date else None,
        "is_disposed": v.disposal_date is not None,
        "location_type": v.location_type,
        "current_vehicle_no": v.current_vehicle_no,
        "mounted_at": v.mounted_at.strftime("%Y-%m-%d %H:%M") if v.mounted_at else None,
        "days_elapsed": days_elapsed,
        "location_label": location_label,
        "notes": v.notes,
        "created_at": v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else None,
    }


def serialize_usage(u: BlackboxUsage) -> Dict[str, Any]:
    return {
        "id": u.id,
        "video_id": u.video_id,
        "video_no": u.video_no,
        "display_num": u.display_num,
        "vehicle_no": u.vehicle_no,
        "started_at": u.started_at.strftime("%Y-%m-%d %H:%M") if u.started_at else None,
        "ended_at": u.ended_at.strftime("%Y-%m-%d %H:%M") if u.ended_at else None,
        "is_active": u.ended_at is None,
        "notes": u.notes,
    }


def serialize_request(r: BlackboxRequest) -> Dict[str, Any]:
    return {
        "id": r.id,
        "requester_id": r.requester_id,
        "requester_name": r.requester_name,
        "vehicle_no": r.vehicle_no,
        "current_video_id": r.current_video_id,
        "current_video_no": r.current_video_no,
        "current_display_num": r.current_display_num,
        "reason_type": r.reason_type,
        "reason_detail": r.reason_detail,
        "incident_date": r.incident_date.strftime("%Y-%m-%d %H:%M") if r.incident_date else None,
        "status": r.status,
        "replacement_video_id": r.replacement_video_id,
        "replacement_video_no": r.replacement_video_no,
        "replacement_display_num": r.replacement_display_num,
        "admin_note": r.admin_note,
        "processed_by": r.processed_by,
        "processed_at": r.processed_at.strftime("%Y-%m-%d %H:%M") if r.processed_at else None,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else None,
    }


# ============================================================================
# 차량 본체 (Device) CRUD
# ============================================================================
def list_devices(db: Session, search: Optional[str] = None) -> List[Dict[str, Any]]:
    q = db.query(BlackboxDevice).filter(BlackboxDevice.is_deleted == False)
    if search:
        kw = f"%{search.strip()}%"
        q = q.filter(
            or_(
                BlackboxDevice.vehicle_no.ilike(kw),
                BlackboxDevice.manufacturer.ilike(kw),
                BlackboxDevice.model_name.ilike(kw),
            )
        )
    rows = q.order_by(BlackboxDevice.vehicle_no.asc()).all()
    return [serialize_device(r) for r in rows]


def create_device(db: Session, payload: Any) -> BlackboxDevice:
    vno = payload.vehicle_no.strip()
    dup = (
        db.query(BlackboxDevice)
        .filter(BlackboxDevice.vehicle_no == vno, BlackboxDevice.is_deleted == False)
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail=f"차량번호 '{vno}'의 본체가 이미 등록되어 있습니다.")
    obj = BlackboxDevice(
        vehicle_no=vno,
        manufacturer=payload.manufacturer,
        model_name=payload.model_name,
        channels=payload.channels,
        led_count=payload.led_count,
        serial_no=payload.serial_no,
        installed_date=payload.installed_date,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_device(db: Session, device_id: int, payload: Any) -> BlackboxDevice:
    obj = (
        db.query(BlackboxDevice)
        .filter(BlackboxDevice.id == device_id, BlackboxDevice.is_deleted == False)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="블랙박스 본체를 찾을 수 없습니다.")

    data = payload.model_dump(exclude_unset=True)
    if "vehicle_no" in data and data["vehicle_no"]:
        new_vno = data["vehicle_no"].strip()
        dup = (
            db.query(BlackboxDevice)
            .filter(
                BlackboxDevice.vehicle_no == new_vno,
                BlackboxDevice.is_deleted == False,
                BlackboxDevice.id != device_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(status_code=400, detail=f"차량번호 '{new_vno}'의 본체가 이미 존재합니다.")
        data["vehicle_no"] = new_vno

    for k, val in data.items():
        setattr(obj, k, val)
    obj.updated_at = datetime.now()
    db.commit()
    db.refresh(obj)
    return obj


def delete_device(db: Session, device_id: int) -> None:
    obj = (
        db.query(BlackboxDevice)
        .filter(BlackboxDevice.id == device_id, BlackboxDevice.is_deleted == False)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="블랙박스 본체를 찾을 수 없습니다.")
    obj.is_deleted = True
    obj.updated_at = datetime.now()
    db.commit()


# ============================================================================
# 비디오 장부 (Video) + 위치/교체/사용기간 트랜잭션
# ============================================================================
def _generate_next_video_no(db: Session) -> str:
    rows = db.query(BlackboxVideo.video_no).filter(BlackboxVideo.is_deleted == False).all()
    max_num = 0
    for (vno,) in rows:
        m = re.search(r"(\d+)$", str(vno or ""))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"BB-{max_num + 1:04d}"


def _ensure_video_unique(
    db: Session,
    video_no: str,
    display_num: str,
    exclude_id: Optional[int] = None,
    check_display_num: bool = True,
) -> None:
    q_vno = db.query(BlackboxVideo).filter(
        BlackboxVideo.video_no == video_no, BlackboxVideo.is_deleted == False
    )
    if exclude_id is not None:
        q_vno = q_vno.filter(BlackboxVideo.id != exclude_id)

    if q_vno.first():
        raise HTTPException(status_code=400, detail=f"관리번호 '{video_no}'가 이미 존재합니다.")

    if check_display_num:
        q_disp = db.query(BlackboxVideo).filter(
            BlackboxVideo.display_num == display_num,
            BlackboxVideo.is_deleted == False,
            BlackboxVideo.disposal_date == None,
        )
        if exclude_id is not None:
            q_disp = q_disp.filter(BlackboxVideo.id != exclude_id)
        if q_disp.first():
            raise HTTPException(status_code=400, detail=f"식별번호 '{display_num}'는 현재 운용 중인 다른 비디오에 부여되어 있습니다. (폐기 후 재사용 가능)")


def _close_open_usages(db: Session, video_id: int, end_dt: datetime, notes: Optional[str] = None) -> None:
    open_rows = (
        db.query(BlackboxUsage)
        .filter(
            BlackboxUsage.video_id == video_id,
            BlackboxUsage.ended_at == None,
            BlackboxUsage.is_deleted == False,
        )
        .all()
    )
    for row in open_rows:
        row.ended_at = end_dt
        if notes:
            row.notes = f"{row.notes} / {notes}".strip(" /") if row.notes else notes


def mount_video_to_vehicle(
    db: Session,
    video: BlackboxVideo,
    vehicle_no: str,
    mounted_at: Optional[datetime] = None,
    notes: Optional[str] = None,
    auto_swap: bool = True,
) -> BlackboxVideo:
    if video.disposal_date is not None:
        raise HTTPException(status_code=400, detail="폐기 처리된 비디오는 차량에 장착할 수 없습니다.")

    vno = vehicle_no.strip()
    action_dt = mounted_at or datetime.now()

    # 1) 대상 차량에 이미 장착된 다른 비디오가 있으면 사무실로 회수 & 사용이력 마감
    if auto_swap:
        prev_videos = (
            db.query(BlackboxVideo)
            .filter(
                BlackboxVideo.location_type == "VEHICLE",
                BlackboxVideo.current_vehicle_no == vno,
                BlackboxVideo.id != video.id,
                BlackboxVideo.is_deleted == False,
            )
            .all()
        )
        for pv in prev_videos:
            _close_open_usages(db, pv.id, action_dt, notes="교체 회수")
            pv.location_type = "OFFICE"
            pv.current_vehicle_no = None
            pv.mounted_at = None
            pv.updated_at = datetime.now()

    # 2) 이 비디오가 다른 차량에 장착 중이었다면 기존 사용이력 마감
    _close_open_usages(db, video.id, action_dt)

    # 3) 신규 차량 장착 및 사용기간 행 오픈
    video.location_type = "VEHICLE"
    video.current_vehicle_no = vno
    video.mounted_at = action_dt
    video.updated_at = datetime.now()

    usage = BlackboxUsage(
        video_id=video.id,
        video_no=video.video_no,
        display_num=video.display_num,
        vehicle_no=vno,
        started_at=action_dt,
        ended_at=None,
        notes=notes,
    )
    db.add(usage)
    return video


def unmount_video_to_office(
    db: Session,
    video: BlackboxVideo,
    removed_at: Optional[datetime] = None,
    notes: Optional[str] = None,
) -> BlackboxVideo:
    action_dt = removed_at or datetime.now()
    _close_open_usages(db, video.id, action_dt, notes=notes)
    video.location_type = "OFFICE"
    video.current_vehicle_no = None
    video.mounted_at = None
    video.updated_at = datetime.now()
    return video


def list_videos(
    db: Session,
    location_type: Optional[str] = None,
    search: Optional[str] = None,
    include_disposed: bool = True,
) -> List[Dict[str, Any]]:
    q = db.query(BlackboxVideo).filter(BlackboxVideo.is_deleted == False)
    if location_type in {"OFFICE", "VEHICLE"}:
        q = q.filter(BlackboxVideo.location_type == location_type)
    if not include_disposed:
        q = q.filter(BlackboxVideo.disposal_date == None)
    if search:
        kw = f"%{search.strip()}%"
        q = q.filter(
            or_(
                BlackboxVideo.video_no.ilike(kw),
                BlackboxVideo.display_num.ilike(kw),
                BlackboxVideo.current_vehicle_no.ilike(kw),
                BlackboxVideo.manufacturer.ilike(kw),
                BlackboxVideo.spec.ilike(kw),
            )
        )
    rows = q.order_by(BlackboxVideo.display_num.asc(), BlackboxVideo.id.asc()).all()
    return [serialize_video(r) for r in rows]


def create_video(db: Session, payload: Any) -> BlackboxVideo:
    video_no = (payload.video_no or "").strip() or _generate_next_video_no(db)
    _ensure_video_unique(
        db,
        video_no,
        payload.display_num,
        check_display_num=(payload.disposal_date is None),
    )

    obj = BlackboxVideo(
        video_no=video_no,
        display_num=payload.display_num,
        manufacturer=payload.manufacturer,
        spec=payload.spec,
        serial_no=payload.serial_no,
        purchase_date=payload.purchase_date,
        disposal_date=payload.disposal_date,
        location_type="OFFICE",
        current_vehicle_no=None,
        mounted_at=None,
        notes=payload.notes,
    )
    db.add(obj)
    db.flush()

    if payload.location_type == "VEHICLE":
        if not payload.current_vehicle_no or not payload.current_vehicle_no.strip():
            raise HTTPException(status_code=400, detail="차량(VEHICLE) 위치 선택 시 차량번호를 입력해야 합니다.")
        mount_video_to_vehicle(
            db,
            obj,
            payload.current_vehicle_no.strip(),
            mounted_at=payload.mounted_at,
            notes="초기 등록 장착",
            auto_swap=True,
        )

    db.commit()
    db.refresh(obj)
    return obj


def update_video(db: Session, video_id: int, payload: Any) -> BlackboxVideo:
    obj = (
        db.query(BlackboxVideo)
        .filter(BlackboxVideo.id == video_id, BlackboxVideo.is_deleted == False)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="비디오를 찾을 수 없습니다.")

    data = payload.model_dump(exclude_unset=True)
    new_vno = data.get("video_no", obj.video_no)
    new_disp = data.get("display_num", obj.display_num)
    new_disposal = data["disposal_date"] if "disposal_date" in data else obj.disposal_date
    if new_vno:
        new_vno = new_vno.strip()
        data["video_no"] = new_vno

    _ensure_video_unique(
        db,
        new_vno,
        new_disp,
        exclude_id=video_id,
        check_display_num=(new_disposal is None),
    )

    for k, val in data.items():
        setattr(obj, k, val)

    # 폐기일 입력 시 차량 장착 중이었으면 사무실 회수 및 사용이력 마감
    if obj.disposal_date is not None and obj.location_type == "VEHICLE":
        unmount_video_to_office(db, obj, removed_at=datetime.combine(obj.disposal_date, time.min), notes="폐기 회수")

    # 번호 스냅샷 동기화
    db.query(BlackboxUsage).filter(BlackboxUsage.video_id == obj.id).update(
        {"video_no": obj.video_no, "display_num": obj.display_num}
    )

    obj.updated_at = datetime.now()
    db.commit()
    db.refresh(obj)
    return obj


def delete_video(db: Session, video_id: int) -> None:
    obj = (
        db.query(BlackboxVideo)
        .filter(BlackboxVideo.id == video_id, BlackboxVideo.is_deleted == False)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="비디오를 찾을 수 없습니다.")
    if obj.location_type == "VEHICLE":
        unmount_video_to_office(db, obj, notes="장부 삭제")
    obj.is_deleted = True
    obj.updated_at = datetime.now()
    db.commit()


# ============================================================================
# 사용기간 양방향 역조회 (Usage Reverse Lookup)
# ============================================================================
def reverse_lookup_usages(
    db: Session,
    video_query: Optional[str] = None,
    vehicle_no: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 300,
) -> List[Dict[str, Any]]:
    q = db.query(BlackboxUsage).filter(BlackboxUsage.is_deleted == False)

    if video_query and video_query.strip():
        kw = video_query.strip()
        like_kw = f"%{kw}%"
        q = q.filter(
            or_(
                BlackboxUsage.video_no.ilike(like_kw),
                BlackboxUsage.display_num == str(int(kw)) if kw.isdigit() and len(kw) <= 3 else BlackboxUsage.display_num.ilike(like_kw),
            )
        )

    if vehicle_no and vehicle_no.strip():
        q = q.filter(BlackboxUsage.vehicle_no.ilike(f"%{vehicle_no.strip()}%"))

    if start_date:
        s_dt = datetime.combine(start_date, time.min)
        q = q.filter(or_(BlackboxUsage.ended_at == None, BlackboxUsage.ended_at >= s_dt))
    if end_date:
        e_dt = datetime.combine(end_date, time.max)
        q = q.filter(BlackboxUsage.started_at <= e_dt)

    rows = q.order_by(BlackboxUsage.started_at.desc(), BlackboxUsage.id.desc()).limit(limit).all()
    return [serialize_usage(r) for r in rows]


# ============================================================================
# 운전기사 교체 요청 (Request)
# ============================================================================
def create_driver_request(db: Session, user: User, payload: Any) -> BlackboxRequest:
    vno = payload.vehicle_no.strip()
    current_video = (
        db.query(BlackboxVideo)
        .filter(
            BlackboxVideo.location_type == "VEHICLE",
            BlackboxVideo.current_vehicle_no == vno,
            BlackboxVideo.is_deleted == False,
        )
        .first()
    )
    requester_name = getattr(user, "real_name", None) or user.username
    obj = BlackboxRequest(
        requester_id=user.id,
        requester_name=requester_name,
        vehicle_no=vno,
        current_video_id=current_video.id if current_video else None,
        current_video_no=current_video.video_no if current_video else None,
        current_display_num=current_video.display_num if current_video else None,
        reason_type=payload.reason_type,
        reason_detail=payload.reason_detail,
        incident_date=payload.incident_date,
        status="PENDING",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def process_driver_request(
    db: Session,
    req_id: int,
    payload: Any,
    admin: User,
) -> BlackboxRequest:
    req = (
        db.query(BlackboxRequest)
        .filter(BlackboxRequest.id == req_id, BlackboxRequest.is_deleted == False)
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="교체 요청을 찾을 수 없습니다.")
    if req.status not in ("PENDING", "PREPARING"):
        raise HTTPException(status_code=400, detail="이미 처리 완료된 요청입니다.")

    admin_name = getattr(admin, "real_name", None) or admin.username
    if payload.status == "COMPLETED" and payload.replacement_video_id:
        rep_video = (
            db.query(BlackboxVideo)
            .filter(BlackboxVideo.id == payload.replacement_video_id, BlackboxVideo.is_deleted == False)
            .first()
        )
        if not rep_video:
            raise HTTPException(status_code=404, detail="교체 투입할 비디오를 찾을 수 없습니다.")
        mount_video_to_vehicle(
            db,
            rep_video,
            req.vehicle_no,
            notes=f"기사 요청 #{req.id} 교체",
            auto_swap=True,
        )
        req.replacement_video_id = rep_video.id
        req.replacement_video_no = rep_video.video_no
        req.replacement_display_num = rep_video.display_num

    req.status = payload.status
    req.admin_note = payload.admin_note
    req.processed_by = admin_name
    req.processed_at = datetime.now()
    db.commit()
    db.refresh(req)
    return req
