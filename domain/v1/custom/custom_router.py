from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import RouteMaster, RouteTimetable, Dispatch
from domain.v1.admin import admin_schema
from domain.v1.admin.admin_router import load_drivers_metadata, load_vehicles_metadata
from typing import List, Optional
from datetime import date, datetime, timedelta, time
import models

router = APIRouter(
    prefix="/v1/custom",
    tags=["CustomDispatch"]
)

def verify_timeline_access(target_date: date, db: Session):
    """
    일반 임직원 및 기사용 배차 정보 공개 타임라인 보안 검증 필터 (Timeline Logic)
    - 오늘 기준 +3일 뒤부터 +7일 뒤 범위만 공개를 허용하며, 이외의 범위는 조회를 완전 차단합니다.
    """
    today = datetime.now().date()
    delta_days = (target_date - today).days

    if not (3 <= delta_days <= 7):
        raise HTTPException(
            status_code=403,
            detail="배차 정보는 오늘 기준 +3일부터 +7일까지의 기간만 조회 가능합니다."
        )


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
        masters = db.query(RouteMaster).filter(
            RouteMaster.start_date <= target_date,
            (RouteMaster.end_date == None) | (RouteMaster.end_date >= target_date)
        ).order_by(RouteMaster.route_name.asc()).all()

        return [
            {
                "id": m.id,
                "route_name": m.route_name,
                "route_type": m.route_type,
                "start_date": str(m.start_date),
                "end_date": str(m.end_date) if m.end_date else None,
                "vehicle_count": m.vehicle_count,
                "version": m.version,
                "is_regular_duty": m.is_regular_duty
            }
            for m in masters
        ]
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
        master = db.query(RouteMaster).filter(RouteMaster.id == route_master_id).first()
        if not master:
            raise HTTPException(status_code=404, detail="해당 노선 마스터를 찾을 수 없습니다.")

        timetables = db.query(RouteTimetable).filter(
            RouteTimetable.route_master_id == route_master_id
        ).order_by(RouteTimetable.seq.asc()).all()

        if not timetables:
            return []

        N = len(timetables)
        delta_days = (target_date - master.start_date).days
        if delta_days < 0:
            delta_days = 0

        # 드라이버 및 차량 메타데이터 로드
        role_map, vehicle_map, vehicle_drivers = load_drivers_metadata()
        vehicles_dict = load_vehicles_metadata()

        # 노선별 기본 전담차량 풀 구성
        route_name = master.route_name or ""
        target_fleet = []
        if "121" in route_name or "122" in route_name:
            target_fleet = vehicles_dict.get("121/122", [])
        elif "291" in route_name or "292" in route_name or "293" in route_name:
            target_fleet = vehicles_dict.get("291/292/293", [])
        else:
            target_fleet = vehicles_dict.get("121/122", []) + vehicles_dict.get("291/292/293", [])

        # 대상 시간표 ID 필터로 금일 배차 맵 구하기
        timetable_ids = [t.id for t in timetables]
        existing_dispatches = db.query(models.Dispatch).filter(
            models.Dispatch.target_date == target_date,
            models.Dispatch.timetable_id.in_(timetable_ids)
        ).all()
        dispatch_map = {d.timetable_id: d for d in existing_dispatches}

        # 내일 날짜 산출 및 배차 맵 구하기
        tomorrow_date = target_date + timedelta(days=1)
        tomorrow_dispatches = db.query(models.Dispatch).filter(
            models.Dispatch.target_date == tomorrow_date,
            models.Dispatch.timetable_id.in_(timetable_ids)
        ).all()
        tomorrow_map = {td.timetable_id: td for td in tomorrow_dispatches}

        # 어제 날짜 산출 및 배차 맵 구하기
        yesterday_date = target_date - timedelta(days=1)
        yesterday_dispatches = db.query(models.Dispatch).filter(
            models.Dispatch.target_date == yesterday_date,
            models.Dispatch.timetable_id.in_(timetable_ids)
        ).all()
        yesterday_map = {yd.timetable_id: yd for yd in yesterday_dispatches}

        # 1단계: 오늘 각 물리적 행에 대응하는 기사 정보 pre-calculation (동일 물리적 행에서의 승계 처리)
        today_drivers = []
        for i, t in enumerate(timetables):
            shifted_index = (i + delta_days) % N
            ref_t = timetables[shifted_index]

            # 어제(전일) 이 물리적 행에 대응되었던 시간표의 당연근무 여부 산출
            yesterday_shifted_index = (i + delta_days - 1) % N
            ref_t_yesterday = timetables[yesterday_shifted_index]
            is_yesterday_regular_duty = ref_t_yesterday.is_regular_duty

            # 어제 동일 행의 배차 조회
            yesterday_disp = yesterday_map.get(t.id)
            yesterday_driver_name = yesterday_disp.driver_name if (yesterday_disp and yesterday_disp.driver_name) else None

            d = dispatch_map.get(t.id)
            driver_name = ""
            is_inherited = False

            if d is not None:
                driver_name = d.driver_name or ""
                is_inherited = False
            else:
                # 오늘 배차 레코드가 없는 경우, 어제 당연근무(1로번)에 해당했다면 어제 동일 행의 기사명을 상속 (연속 근무)
                if is_yesterday_regular_duty:
                    if yesterday_driver_name:
                        driver_name = yesterday_driver_name
                        is_inherited = True

            today_drivers.append({
                "driver_name": driver_name,
                "is_inherited": is_inherited,
                "yesterday_driver_name": yesterday_driver_name,
                "is_yesterday_regular_duty": is_yesterday_regular_duty
            })

        # 2단계: 내일 당연근무를 수행할 기사 예측을 포함한 최종 결과 목록 구성
        result = []
        for i, t in enumerate(timetables):
            shifted_index = (i + delta_days) % N
            ref_t = timetables[shifted_index]

            # 내일 날짜의 shifted_index 및 당연근무 여부 산출
            tomorrow_shifted_index = (i + delta_days + 1) % N
            ref_t_tomorrow = timetables[tomorrow_shifted_index]
            is_tomorrow_regular_duty = ref_t_tomorrow.is_regular_duty

            default_vehicle = target_fleet[i] if i < len(target_fleet) else ""

            today_info = today_drivers[i]
            driver_name = today_info["driver_name"]
            is_inherited = today_info["is_inherited"]
            yesterday_driver_name = today_info["yesterday_driver_name"]

            d = dispatch_map.get(t.id)
            vehicle_no = default_vehicle
            if d and d.vehicle_no:
                vehicle_no = d.vehicle_no

            # 3단계: 내일 날짜 기사 및 상속 여부 결정
            td_d = tomorrow_map.get(t.id)
            tomorrow_driver_name = ""
            is_tomorrow_inherited = False

            if td_d and td_d.driver_name and td_d.driver_name.strip():
                tomorrow_driver_name = td_d.driver_name
                is_tomorrow_inherited = False
            else:
                if ref_t.is_regular_duty:
                    if driver_name and driver_name.strip():
                        tomorrow_driver_name = driver_name
                        is_tomorrow_inherited = True

            result.append({
                "id": d.id if d else None,
                "timetable_id": t.id,
                "seq": ref_t.seq,
                "start_time": (d.start_time if d else None) or ref_t.start_time,
                "end_time": ref_t.end_time,
                "start_location": ref_t.start_location,
                "end_location": ref_t.end_location,
                "driver_name": driver_name,
                "tomorrow_driver_name": tomorrow_driver_name,
                "yesterday_driver_name": yesterday_driver_name,
                "vehicle_no": vehicle_no,
                "status": d.status if d else "DRAFT",
                "memo": (d.memo if d else "") or "",
                "is_regular_duty": ref_t.is_regular_duty,
                "is_tomorrow_regular_duty": is_tomorrow_regular_duty,
                "is_yesterday_regular_duty": today_info["is_yesterday_regular_duty"],
                "is_inherited": is_inherited,
                "is_tomorrow_inherited": is_tomorrow_inherited
            })

        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [CustomDispatch] Error fetching daily dispatch: {e}")
        raise HTTPException(status_code=500, detail="배차 정보를 조회하는 중 오류가 발생하였습니다.")
