"""
============================================================================
[차량 배차 설정·리소스·자동고지 라우터 (domain/v1/dispatch/dispatch_router.py)]
============================================================================
"""

from datetime import date
from typing import Any, Dict
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from core.deps import get_current_user, require_app_permission
from core.audit import safe_log_audit
from models import User
from . import dispatch_service as service

admin_router = APIRouter(prefix="/v1/admin/dispatch", tags=["Admin Dispatch Settings"])
custom_router = APIRouter(prefix="/v1/custom/dispatch", tags=["Custom Dispatch Settings"])

check_dispatch_admin = require_app_permission("dispatch", action="read")
check_dispatch_admin_write = require_app_permission("dispatch", action="write")


@admin_router.get("/settings")
def get_admin_dispatch_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin),
):
    settings = service.get_dispatch_settings(db)
    return {
        "settings": settings,
        "preview_window": service.compute_preview_window(settings),
    }


@admin_router.put("/settings")
def update_admin_dispatch_settings(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin_write),
):
    saved = service.save_dispatch_settings(db, payload)
    safe_log_audit(
        db=db,
        app_id="dispatch",
        log_type="CHANGE",
        action="DISPATCH_SETTINGS_UPDATE",
        title="배차 앱 전역 설정 변경",
        user=admin,
        resource_type="system_config",
        resource_id=service.DISPATCH_SETTINGS_KEY,
    )
    return {
        "message": "배차 설정이 저장되었습니다.",
        "settings": saved,
        "preview_window": service.compute_preview_window(saved),
    }


@admin_router.get("/resources")
def get_admin_dispatch_resources(
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin),
):
    """차량 풀, 기사 목록 및 현재 배차 설정을 통합 반환합니다."""
    return service.get_dispatch_resources(db)


@admin_router.get("/driver-stats")
def get_admin_dispatch_driver_stats(
    target_date: date = Query(..., description="조회 기준일 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin),
):
    """기사별 월간/주간/야간 운행 통계 및 당일 결근·병가·징계 현황을 반환합니다."""
    return service.build_driver_work_stats(db, target_date)


@admin_router.get("/driver-detail")
def get_admin_dispatch_driver_detail(
    driver_name: str = Query(..., description="기사명"),
    target_date: date = Query(..., description="조회 기준일 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin),
):
    """기사 상세 모달용 결근계 내역, 최근 노선 운행 내역 및 당일/명일 투입 여부를 반환합니다."""
    return service.get_driver_dispatch_detail(db, driver_name, target_date)


@admin_router.get("/publish-status")
def get_admin_dispatch_publish_status(
    target_date: date = Query(..., description="조회 날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin),
):
    """특정 날짜의 배차 공개(배포) 상태 및 저장 건수를 반환합니다."""
    from domain.v1.admin.admin_router import query_active_routes_for_date
    from models import Dispatch, RouteTimetable

    date_key = target_date.isoformat()
    pub_map = service.get_published_dates_map(db)
    active_routes = query_active_routes_for_date(db, target_date)
    route_ids = [r["id"] for r in active_routes if isinstance(r, dict) and r.get("id")]
    total_count = 0
    saved_count = 0
    if route_ids:
        tt_ids = [
            tid
            for (tid,) in db.query(RouteTimetable.id)
            .filter(RouteTimetable.route_master_id.in_(route_ids))
            .all()
        ]
        total_count = len(tt_ids)
        if tt_ids:
            saved_count = (
                db.query(Dispatch.id)
                .filter(Dispatch.target_date == target_date, Dispatch.timetable_id.in_(tt_ids))
                .count()
            )
    return {
        "target_date": date_key,
        "published": service.is_date_published(db, target_date),
        "meta": pub_map.get(date_key),
        "saved_count": saved_count,
        "total_count": total_count,
    }


@admin_router.post("/publish-status")
def update_admin_dispatch_publish_status(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin_write),
):
    """특정 날짜의 배차 공개(배포) 여부를 설정하거나 해제합니다."""
    raw_date = str(payload.get("target_date") or "").strip()
    try:
        parsed_date = date.fromisoformat(raw_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="유효한 날짜(YYYY-MM-DD)를 입력해 주세요.")

    published = bool(payload.get("published", False))
    res = service.set_date_published(db, parsed_date, published, mode="manual")
    safe_log_audit(
        db=db,
        app_id="dispatch",
        log_type="CHANGE",
        action="DISPATCH_PUBLISH_STATUS",
        title=f"배차 공개 상태 변경 ({raw_date}: {'공개' if published else '비공개'})",
        user=admin,
        resource_type="dispatch",
        resource_id=raw_date,
    )
    return {
        "message": f"{raw_date} 배차가 {'공개(배포)' if published else '비공개(공개 취소)'} 처리되었습니다.",
        **res,
    }


@admin_router.post("/announce-now")
def trigger_announce_tomorrow_dispatch(
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin_write),
):
    """관리자가 명일 배차 고지 및 알림·웹푸시를 즉시 실행합니다."""
    res = service.announce_tomorrow_dispatch(db, force=True, trigger_user=admin)
    safe_log_audit(
        db=db,
        app_id="dispatch",
        log_type="CHANGE",
        action="DISPATCH_ANNOUNCE_NOW",
        title=f"명일 배차 즉시 고지 ({res.get('target_date')})",
        user=admin,
        resource_type="dispatch",
        resource_id=str(res.get("target_date")),
    )
    return {
        "message": f"{res.get('target_date')} 명일 배차가 고지되었습니다.",
        **res,
    }


@custom_router.get("/settings")
def get_custom_dispatch_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """사용자 배차 뷰에서 필요한 예고 범위, 표시 옵션 및 차량 풀을 반환합니다."""
    res = service.get_dispatch_resources(db)
    settings = res["settings"]
    return {
        "preview_window": service.compute_preview_window(settings),
        "show_substitute_columns": settings.get("show_substitute_columns", True),
        "route_fleet_rules": settings.get("route_fleet_rules", []),
        "vehicles_by_group": res["vehicles_by_group"],
        "confirm_d_day_always_open": settings.get("confirm_d_day_always_open", True),
        "confirm_d1_require_announced": settings.get("confirm_d1_require_announced", True),
        "preview_allow_draft": settings.get("preview_allow_draft", True),
    }
