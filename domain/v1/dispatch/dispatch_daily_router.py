"""
[일일 배차 조회·저장·작업률 관리자 라우터 (domain/v1/dispatch/dispatch_daily_router.py)]
"""

from datetime import date, datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
from database import get_db
from core.deps import require_app_permission
from domain.v1.admin import admin_schema
from domain.v1.dispatch.dispatch_builder import (
    build_daily_dispatch_rows,
    build_dispatch_work_rates,
    load_drivers_metadata,
    query_active_routes_for_date,
)
from models import User

router = APIRouter(tags=["Admin Dispatch Daily"])

check_admin = require_app_permission("dashboard", action="read")
check_dispatch_admin = require_app_permission("dispatch", action="read")
check_dispatch_admin_write = require_app_permission("dispatch", action="write")


@router.get("/dispatch/work-rates", response_model=List[dict])
def get_dispatch_work_rates(
    days: int = 10,
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin),
):
    """D+1 ~ D+10 향후 배차 작업률(%)을 반환합니다."""
    try:
        return build_dispatch_work_rates(db, datetime.now().date(), days=days)
    except Exception as e:
        print(f"❌ [AdminDispatch] Error calculating dispatch work rates: {e}")
        raise HTTPException(status_code=500, detail="배차 작업률 통계를 계산하는 중 오류가 발생하였습니다.")


@router.get("/dispatch/active-routes", response_model=List[dict])
def list_active_routes_for_date(
    target_date: date,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin),
):
    """지정된 날짜(target_date) 기준으로 운행(활성) 중인 노선 마스터 목록을 조회합니다."""
    try:
        return query_active_routes_for_date(db, target_date)
    except Exception as e:
        print(f"❌ [AdminDispatch] Error listing active routes: {e}")
        raise HTTPException(status_code=500, detail="활성 노선 정보를 조회하는 중 오류가 발생하였습니다.")


@router.get("/dispatch", response_model=List[admin_schema.DispatchRowResponse])
def get_daily_dispatch(
    target_date: date,
    route_master_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin),
):
    """지정된 날짜와 노선 마스터 ID에 해당하는 배차 목록을 조회합니다."""
    try:
        return build_daily_dispatch_rows(db, target_date, route_master_id)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [AdminDispatch] Error fetching dispatch data with rotation: {e}")
        raise HTTPException(status_code=500, detail="배차 정보를 조회하는 중 오류가 발생하였습니다.")


@router.post("/dispatch")
def save_daily_dispatch(
    payload: admin_schema.DispatchSavePayload,
    db: Session = Depends(get_db),
    admin: User = Depends(check_dispatch_admin_write),
):
    """일괄 배차 정보(금일 및 익일)를 생성하거나 업데이트(Upsert) 합니다."""
    try:
        from domain.v1.dispatch.dispatch_service import _now_kst, is_date_published

        today_kst = _now_kst().date()
        tomorrow_kst = today_kst + timedelta(days=1)
        if payload.target_date < today_kst:
            raise HTTPException(
                status_code=400,
                detail="과거 날짜(어제 이전)의 배차 데이터는 수정·저장할 수 없습니다.",
            )

        # 🔒 [상태 머신 규칙]
        # 1) 미래 예고 날짜(D+2 이상): 언제든 DRAFT 저장 가능, 확정/배포 불가
        if payload.target_date > tomorrow_kst and payload.status in ("CONFIRMED", "ANNOUNCED"):
            raise HTTPException(
                status_code=400,
                detail="배차 확정 및 배포는 운행 전날(D-1)에만 수행할 수 있습니다. 미래 날짜는 저장(DRAFT)만 가능합니다.",
            )
        # 2) 전날(D-1) 현재 배포(공개) 중인 상태에서 DRAFT/CONFIRMED 강등 시도 차단
        if (
            payload.target_date == tomorrow_kst
            and payload.status in ("DRAFT", "CONFIRMED")
            and is_date_published(db, tomorrow_kst)
        ):
            raise HTTPException(
                status_code=409,
                detail="현재 배포(공개) 중인 배차는 확정 변경·취소할 수 없습니다. 먼저 '공개 취소'를 실행해 주세요.",
            )

        # 🔒 [동시성 제어] 동일 날짜 동시 배차 저장 시 UniqueConstraint 충돌 방지 (PostgreSQL Advisory Lock)
        tomorrow_date = payload.target_date + timedelta(days=1)
        if db.bind and db.bind.dialect.name == "postgresql":
            from sqlalchemy import text
            for lock_d in (payload.target_date, tomorrow_date):
                db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                    {"k": f"dispatch_save_{lock_d.isoformat()}"},
                )

        # 🛡️ [익일 보호] 익일 배차가 이미 배포(공개) 중이거나 확정된 행은 금일 저장 시 자동 덮어쓰기/삭제를 차단
        tomorrow_is_published = is_date_published(db, tomorrow_date)

        role_map, vehicle_map, _ = load_drivers_metadata()

        for r in payload.rows:
            db_dispatch = (
                db.query(models.Dispatch)
                .filter(
                    models.Dispatch.target_date == payload.target_date,
                    models.Dispatch.timetable_id == r.timetable_id,
                )
                .first()
            )

            if db_dispatch:
                db_dispatch.driver_name = r.driver_name
                db_dispatch.vehicle_no = r.vehicle_no
                db_dispatch.start_time = r.start_time
                db_dispatch.status = payload.status
                db_dispatch.memo = r.memo
            else:
                db_dispatch = models.Dispatch(
                    target_date=payload.target_date,
                    timetable_id=r.timetable_id,
                    driver_name=r.driver_name,
                    vehicle_no=r.vehicle_no,
                    start_time=r.start_time,
                    status=payload.status,
                    memo=r.memo,
                )
                db.add(db_dispatch)

            if tomorrow_is_published:
                continue

            db_dispatch_tomorrow = (
                db.query(models.Dispatch)
                .filter(
                    models.Dispatch.target_date == tomorrow_date,
                    models.Dispatch.timetable_id == r.timetable_id,
                )
                .first()
            )

            # 이미 확정/배포된 익일 슬롯은 금일 배차 저장을 통한 간접 수정·삭제에서 보호
            if db_dispatch_tomorrow and db_dispatch_tomorrow.status in ("CONFIRMED", "ANNOUNCED"):
                continue

            if r.tomorrow_driver_name and r.tomorrow_driver_name.strip():
                tomorrow_driver = r.tomorrow_driver_name.strip()
                tomorrow_vehicle = (
                    r.vehicle_no if tomorrow_driver == r.driver_name else vehicle_map.get(tomorrow_driver)
                )

                if db_dispatch_tomorrow:
                    db_dispatch_tomorrow.driver_name = tomorrow_driver
                    if (
                        not db_dispatch_tomorrow.vehicle_no
                        or db_dispatch_tomorrow.vehicle_no.strip() == ""
                        or tomorrow_driver != r.driver_name
                    ):
                        if tomorrow_vehicle:
                            db_dispatch_tomorrow.vehicle_no = tomorrow_vehicle
                else:
                    db_dispatch_tomorrow = models.Dispatch(
                        target_date=tomorrow_date,
                        timetable_id=r.timetable_id,
                        driver_name=tomorrow_driver,
                        vehicle_no=tomorrow_vehicle or r.vehicle_no,
                        status="DRAFT",
                        memo="",
                    )
                    db.add(db_dispatch_tomorrow)
            else:
                if db_dispatch_tomorrow:
                    db_dispatch_tomorrow.driver_name = None

        db.commit()

        try:
            from domain.v1.dispatch.dispatch_service import invalidate_driver_work_stats_cache
            invalidate_driver_work_stats_cache()
        except Exception:
            pass

        return {"message": "success"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminDispatch] Error saving dispatch data: {e}")
        raise HTTPException(status_code=500, detail="배차 정보를 저장하는 중 오류가 발생하였습니다.")
