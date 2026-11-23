from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import RouteMaster, RouteTimetable, Dispatch, User, DayOff
from core.deps import get_current_user
from domain.v1.admin import admin_schema
from domain.v1.admin.admin_router import (
    query_active_routes_for_date,
    build_daily_dispatch_rows,
)
from typing import List, Optional
from datetime import date, datetime, timedelta, time
import models

router = APIRouter(
    prefix="/v1/custom",
    tags=["CustomDispatch"]
)

def verify_timeline_access(target_date: date, db: Session):
    """
    일반 임직원 및 기사용 배차 정보 공개 타임라인 보안 검증 필터 (설정 기반 동적 검증)
    """
    from domain.v1.dispatch.dispatch_service import verify_custom_preview_access
    verify_custom_preview_access(db, target_date)


@router.get("/my-dispatch-briefing")
def get_my_dispatch_briefing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    로그인한 운전원 본인의 당일 및 명일(17시 이후) 배차 브리핑 조회
    - 본인(real_name/username)에게 배정된 당일·명일 배차만 최소 정보로 반환합니다.
    """
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    is_after_17 = now.hour >= 17
    now_hhmm = now.strftime("%H:%M")

    candidate_names = {
        str(n).strip()
        for n in (getattr(current_user, "real_name", None), getattr(current_user, "username", None))
        if n and str(n).strip()
    }

    from domain.v1.dispatch.dispatch_service import build_timetable_rotation_resolver
    resolve_tt, _ = build_timetable_rotation_resolver(db)

    def _serialize(rows: List[Dispatch]) -> List[dict]:
        items = []
        for d in rows:
            tt = d.timetable
            ref_t = resolve_tt(d.timetable_id, d.target_date) if d.timetable_id and d.target_date else None
            s_time = (d.start_time or (ref_t["start_time"] if ref_t else (tt.start_time if tt else "")) or "").strip()
            items.append({
                "id": d.id,
                "route_name": (ref_t["route_name"] if ref_t else (tt.route_name if tt else "-")),
                "seq": (ref_t["seq"] if ref_t else (tt.seq if tt else 0)),
                "vehicle_no": d.vehicle_no or "-",
                "start_time": s_time,
                "end_time": (ref_t["end_time"] if ref_t else (tt.end_time if tt else "")) or "",
                "start_location": (ref_t["start_location"] if ref_t else (tt.start_location if tt else "-")) or "-",
                "end_location": (ref_t["end_location"] if ref_t else (tt.end_location if tt else "-")) or "-",
                "status": d.status or "DRAFT",
            })
        items.sort(key=lambda x: (x["start_time"], x["seq"]))
        return items

    today_dispatches = []
    tomorrow_dispatches = []

    if candidate_names:
        today_rows = (
            db.query(Dispatch)
            .options(joinedload(Dispatch.timetable))
            .filter(
                Dispatch.target_date == today,
                Dispatch.driver_name.in_(candidate_names),
            )
            .all()
        )
        today_dispatches = _serialize(today_rows)

        if is_after_17:
            tomorrow_rows = (
                db.query(Dispatch)
                .options(joinedload(Dispatch.timetable))
                .filter(
                    Dispatch.target_date == tomorrow,
                    Dispatch.driver_name.in_(candidate_names),
                )
                .all()
            )
            tomorrow_dispatches = _serialize(tomorrow_rows)

    # 오늘 / 내일 본인 승인(APPROVED) 휴무 조회 -> 근무일 / 휴무일 구분용
    dayoff_rows = (
        db.query(DayOff)
        .filter(
            DayOff.user_id == current_user.id,
            DayOff.is_deleted == False,
            DayOff.status == "APPROVED",
            DayOff.date.in_([today, tomorrow]),
        )
        .all()
    )
    today_dayoff_obj = next((d for d in dayoff_rows if d.date == today), None)
    tomorrow_dayoff_obj = next((d for d in dayoff_rows if d.date == tomorrow), None)

    def _serialize_dayoff(d: Optional[DayOff]) -> Optional[dict]:
        if not d:
            return None
        return {
            "id": d.id,
            "date": str(d.date),
            "type": d.type,
            "status": d.status,
            "memo": d.memo,
        }

    today_dayoff = _serialize_dayoff(today_dayoff_obj)
    tomorrow_dayoff = _serialize_dayoff(tomorrow_dayoff_obj) if is_after_17 else None

    if today_dayoff:
        today_work_status = "DAYOFF"      # 휴무일
    elif today_dispatches:
        today_work_status = "WORK"        # 근무일 (배차 있음)
    else:
        today_work_status = "UNASSIGNED"  # 배차 미배정/대기

    return {
        "today": str(today),
        "tomorrow": str(tomorrow),
        "now_hhmm": now_hhmm,
        "is_after_17": is_after_17,
        "driver_name": getattr(current_user, "real_name", None) or current_user.username,
        "today_work_status": today_work_status,
        "today_dayoff": today_dayoff,
        "tomorrow_dayoff": tomorrow_dayoff,
        "today_dispatches": today_dispatches,
        "tomorrow_dispatches": tomorrow_dispatches,
    }


@router.get("/dispatch/active-routes", response_model=List[dict])
def get_custom_active_routes(
    target_date: date,
    db: Session = Depends(get_db)
):
    """
    일반 임직원용 특정 날짜 기준 활성 노선 목록 조회
    - 날짜 기반 타임라인 보안 정책을 통과해야 조회 가능합니다.
    """
    # 🔒 보안 타임라인 필터 검증
    verify_timeline_access(target_date, db)

    try:
        return query_active_routes_for_date(db, target_date)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [CustomDispatch] Error listing active routes: {e}")
        raise HTTPException(status_code=500, detail="활성 노선 정보를 조회하는 중 오류가 발생하였습니다.")


@router.get("/dispatch", response_model=List[admin_schema.DispatchRowResponse])
def get_custom_daily_dispatch(
    target_date: date,
    route_master_id: int,
    db: Session = Depends(get_db)
):
    """
    일반 임직원 및 기사용 날짜별 배차 목록 조회
    - 날짜 기반 타임라인 보안 정책을 통과해야 조회 가능합니다.
    - 당연근무 연속 탑승, 어제 기사 자동 상속 로직 등이 포함된 최종 완성본을 반환합니다.
    """
    # 🔒 보안 타임라인 필터 검증
    verify_timeline_access(target_date, db)

    try:
        from domain.v1.dispatch.dispatch_service import filter_custom_dispatch_rows

        rows = build_daily_dispatch_rows(db, target_date, route_master_id)
        return filter_custom_dispatch_rows(db, target_date, rows)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [CustomDispatch] Error fetching daily dispatch: {e}")
        raise HTTPException(status_code=500, detail="배차 정보를 조회하는 중 오류가 발생하였습니다.")
