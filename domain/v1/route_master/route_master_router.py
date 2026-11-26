"""
[노선 마스터 및 구간 관리 라우터 (domain/v1/route_master/route_master_router.py)]
"""

from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import get_db
from core.deps import require_app_permission
from domain.v1.admin import admin_schema
from models import Dispatch, RouteMaster, RouteSegment, RouteTimetable, User

router = APIRouter(tags=["Admin Route Master"])

check_route_master_admin = require_app_permission("route_master", action="read")
check_route_master_admin_write = require_app_permission("route_master", action="write")


@router.get("/route-masters")
def list_route_masters(
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin),
):
    """모든 노선 마스터 및 소속 버전별 시간표 상세 정보를 조회합니다."""
    try:
        masters = (
            db.query(RouteMaster)
            .options(joinedload(RouteMaster.timetables))
            .order_by(RouteMaster.route_name.asc(), RouteMaster.version.asc())
            .all()
        )

        result = []
        for m in masters:
            sorted_timetables = sorted(m.timetables, key=lambda x: x.seq)
            result.append(
                {
                    "id": m.id,
                    "route_name": m.route_name,
                    "route_type": m.route_type,
                    "start_date": str(m.start_date),
                    "end_date": str(m.end_date) if m.end_date else None,
                    "vehicle_count": m.vehicle_count,
                    "version": m.version,
                    "is_regular_duty": m.is_regular_duty,
                    "start_turn_seq": getattr(m, "start_turn_seq", 1) or 1,
                    "timetables": [
                        {
                            "id": t.id,
                            "route_master_id": t.route_master_id,
                            "route_name": t.route_name,
                            "seq": t.seq,
                            "start_time": t.start_time,
                            "end_time": t.end_time,
                            "start_location": t.start_location,
                            "end_location": t.end_location,
                            "version": t.version,
                            "start_garage": t.start_garage,
                            "end_garage": t.end_garage,
                            "is_regular_duty": t.is_regular_duty,
                        }
                        for t in sorted_timetables
                    ],
                }
            )
        return result
    except Exception as e:
        print(f"❌ [AdminRouteMaster] Error listing route masters: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 조회하는 중 서버 오류가 발생하였습니다.")


@router.post("/route-masters")
def create_route_master(
    payload: admin_schema.RouteMasterCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write),
):
    """새로운 노선 마스터 및 관련 상세 시간표를 일괄 등록합니다."""
    try:
        db_master = RouteMaster(
            route_name=payload.route_name,
            route_type=payload.route_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            vehicle_count=payload.vehicle_count,
            version=payload.version,
            is_regular_duty=payload.is_regular_duty,
            start_turn_seq=max(1, payload.start_turn_seq or 1),
        )
        db.add(db_master)
        db.flush()

        for t in payload.timetables:
            db.add(
                RouteTimetable(
                    route_master_id=db_master.id,
                    route_name=payload.route_name,
                    seq=t.seq,
                    start_time=t.start_time,
                    end_time=t.end_time,
                    start_location=t.start_location,
                    end_location=t.end_location,
                    version=payload.version,
                    start_garage=t.start_garage,
                    end_garage=t.end_garage,
                    is_regular_duty=t.is_regular_duty,
                )
            )

        db.commit()
        db.refresh(db_master)
        try:
            from domain.v1.dispatch.dispatch_service import invalidate_timetable_rotation_cache
            invalidate_timetable_rotation_cache()
        except Exception:
            pass
        return {"message": "success", "id": db_master.id}
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteMaster] Error creating route master: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 생성하는 중 오류가 발생하였습니다.")


@router.put("/route-masters/{master_id}")
def update_route_master(
    master_id: int,
    payload: admin_schema.RouteMasterUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write),
):
    """노선 마스터 및 상세 시간표를 수정합니다."""
    try:
        db_master = db.query(RouteMaster).filter(RouteMaster.id == master_id).first()
        if not db_master:
            raise HTTPException(status_code=404, detail="해당 노선 마스터를 찾을 수 없습니다.")

        if payload.route_name is not None:
            db_master.route_name = payload.route_name
        if payload.route_type is not None:
            db_master.route_type = payload.route_type
        if payload.start_date is not None:
            db_master.start_date = payload.start_date
        if payload.end_date is not None:
            db_master.end_date = payload.end_date
        if payload.vehicle_count is not None:
            db_master.vehicle_count = payload.vehicle_count
        if payload.version is not None:
            db_master.version = payload.version
        if payload.is_regular_duty is not None:
            db_master.is_regular_duty = payload.is_regular_duty
        if payload.start_turn_seq is not None:
            db_master.start_turn_seq = max(1, payload.start_turn_seq)

        if payload.timetables is not None:
            db.query(RouteTimetable).filter(RouteTimetable.route_master_id == master_id).delete()
            for t in payload.timetables:
                db.add(
                    RouteTimetable(
                        route_master_id=db_master.id,
                        route_name=db_master.route_name,
                        seq=t.seq,
                        start_time=t.start_time,
                        end_time=t.end_time,
                        start_location=t.start_location,
                        end_location=t.end_location,
                        version=db_master.version,
                        start_garage=t.start_garage,
                        end_garage=t.end_garage,
                        is_regular_duty=t.is_regular_duty,
                    )
                )

        db.commit()
        try:
            from domain.v1.dispatch.dispatch_service import invalidate_timetable_rotation_cache
            invalidate_timetable_rotation_cache()
        except Exception:
            pass
        return {"message": "success"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteMaster] Error updating route master: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 수정하는 중 오류가 발생하였습니다.")


@router.delete("/route-masters/{master_id}")
def delete_route_master(
    master_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write),
):
    """미래 적용 예정(start_date > 오늘)인 노선 마스터만 영구 삭제할 수 있습니다."""
    try:
        from domain.v1.dispatch.dispatch_service import _now_kst

        db_master = db.query(RouteMaster).filter(RouteMaster.id == master_id).first()
        if not db_master:
            raise HTTPException(status_code=404, detail="해당 노선 마스터를 찾을 수 없습니다.")

        today_kst = _now_kst().date()
        if db_master.start_date <= today_kst:
            raise HTTPException(
                status_code=400,
                detail="이미 적용되었거나 지난 로번은 과거 배차 이력 보존을 위해 삭제할 수 없습니다. 미래 적용 예정 로번만 삭제 가능합니다.",
            )

        db.delete(db_master)
        db.commit()
        try:
            from domain.v1.dispatch.dispatch_service import invalidate_timetable_rotation_cache
            invalidate_timetable_rotation_cache()
        except Exception:
            pass
        return {"message": "success"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteMaster] Error deleting route master: {e}")
        raise HTTPException(status_code=500, detail="노선 정보를 삭제하는 중 오류가 발생하였습니다.")


@router.post("/route-masters/append-roster")
def append_route_roster(
    payload: admin_schema.RouteRosterAppend,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write),
):
    """[Append-Only] 노선의 날짜별 로번(시간표 버전)을 덮어쓰기 없이 추가합니다."""
    try:
        existing_versions = (
            db.query(RouteMaster)
            .filter(RouteMaster.route_name == payload.route_name)
            .order_by(RouteMaster.start_date.asc(), RouteMaster.id.asc())
            .all()
        )

        prev_day = payload.start_date - timedelta(days=1)
        same_day_master = None

        for prev in existing_versions:
            if prev.start_date < payload.start_date and (
                prev.end_date is None or prev.end_date >= payload.start_date
            ):
                prev.end_date = prev_day
            elif prev.start_date == payload.start_date:
                # 동일 (route_name, start_date)는 항상 1개 로번만 유지 (배차 참조가 있어도 seq 기준 제자리 갱신)
                if same_day_master is None:
                    same_day_master = prev
                else:
                    # 혹시 과거에 중복 생성된 잉여 당일 행이 있다면 배차 미참조 건만 정리
                    dup_tt_ids = [
                        tid
                        for (tid,) in db.query(RouteTimetable.id)
                        .filter(RouteTimetable.route_master_id == prev.id)
                        .all()
                    ]
                    has_disp = (
                        bool(dup_tt_ids)
                        and db.query(Dispatch.id)
                        .filter(Dispatch.timetable_id.in_(dup_tt_ids))
                        .first()
                        is not None
                    )
                    if not has_disp:
                        db.query(RouteTimetable).filter(
                            RouteTimetable.route_master_id == prev.id
                        ).delete(synchronize_session=False)
                        db.delete(prev)

        if same_day_master is not None:
            db_master = same_day_master
            db_master.route_type = payload.route_type
            db_master.end_date = payload.end_date
            db_master.vehicle_count = payload.vehicle_count
            db_master.is_regular_duty = payload.is_regular_duty
            db_master.start_turn_seq = max(1, payload.start_turn_seq or 1)
            next_version = db_master.version or f"v{len(existing_versions)}"

            # 기존 시간표를 seq 기준으로 매칭해 ID를 보존한 채 제자리(In-place) 갱신 -> 기존 Dispatch 참조 100% 유지
            existing_tts = (
                db.query(RouteTimetable)
                .filter(RouteTimetable.route_master_id == db_master.id)
                .all()
            )
            tt_by_seq = {tt.seq: tt for tt in existing_tts}
            incoming_seqs = set()

            for t in payload.timetables:
                incoming_seqs.add(t.seq)
                tt = tt_by_seq.get(t.seq)
                if tt:
                    tt.start_time = t.start_time
                    tt.end_time = t.end_time
                    tt.start_location = t.start_location
                    tt.end_location = t.end_location
                    tt.version = next_version
                    tt.start_garage = t.start_garage
                    tt.end_garage = t.end_garage
                    tt.is_regular_duty = t.is_regular_duty
                else:
                    db.add(
                        RouteTimetable(
                            route_master_id=db_master.id,
                            route_name=payload.route_name,
                            seq=t.seq,
                            start_time=t.start_time,
                            end_time=t.end_time,
                            start_location=t.start_location,
                            end_location=t.end_location,
                            version=next_version,
                            start_garage=t.start_garage,
                            end_garage=t.end_garage,
                            is_regular_duty=t.is_regular_duty,
                        )
                    )

            # 삭제된 회차(seq)는 배차 참조가 없는 경우에만 제거
            for seq_val, tt in tt_by_seq.items():
                if seq_val not in incoming_seqs:
                    used = (
                        db.query(Dispatch.id)
                        .filter(Dispatch.timetable_id == tt.id)
                        .first()
                        is not None
                    )
                    if not used:
                        db.delete(tt)
        else:
            next_version = (payload.version or "").strip() or f"v{len(existing_versions) + 1}"
            db_master = RouteMaster(
                route_name=payload.route_name,
                route_type=payload.route_type,
                start_date=payload.start_date,
                end_date=payload.end_date,
                vehicle_count=payload.vehicle_count,
                version=next_version,
                is_regular_duty=payload.is_regular_duty,
                start_turn_seq=max(1, payload.start_turn_seq or 1),
            )
            db.add(db_master)
            db.flush()

            for t in payload.timetables:
                db.add(
                    RouteTimetable(
                        route_master_id=db_master.id,
                        route_name=payload.route_name,
                        seq=t.seq,
                        start_time=t.start_time,
                        end_time=t.end_time,
                        start_location=t.start_location,
                        end_location=t.end_location,
                        version=next_version,
                        start_garage=t.start_garage,
                        end_garage=t.end_garage,
                        is_regular_duty=t.is_regular_duty,
                    )
                )

        db.commit()
        db.refresh(db_master)
        try:
            from domain.v1.dispatch.dispatch_service import invalidate_timetable_rotation_cache

            invalidate_timetable_rotation_cache()
        except Exception:
            pass
        return {"message": "success", "id": db_master.id, "version": next_version}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteMaster] Error appending roster: {e}")
        raise HTTPException(status_code=500, detail="로번 버전 추가 중 오류가 발생하였습니다.")


@router.get("/route-segments", response_model=List[admin_schema.RouteSegmentSchema])
def list_route_segments(
    route_name: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin),
):
    q = db.query(RouteSegment)
    if route_name:
        q = q.filter(RouteSegment.route_name == route_name)
    return q.order_by(RouteSegment.route_name.asc(), RouteSegment.seq.asc()).all()


@router.put("/route-segments", response_model=List[admin_schema.RouteSegmentSchema])
def save_route_segments(
    payload: admin_schema.RouteSegmentBulkSave,
    db: Session = Depends(get_db),
    admin: User = Depends(check_route_master_admin_write),
):
    try:
        db.query(RouteSegment).filter(RouteSegment.route_name == payload.route_name).delete()
        created = []
        for idx, seg in enumerate(payload.segments, start=1):
            row = RouteSegment(
                route_name=payload.route_name,
                route_master_id=payload.route_master_id,
                seq=seg.seq or idx,
                segment_name=seg.segment_name,
                start_stop=seg.start_stop,
                end_stop=seg.end_stop,
                duration_min=max(0, int(seg.duration_min or 0)),
                distance_km=seg.distance_km,
                memo=seg.memo,
            )
            db.add(row)
            created.append(row)
        db.commit()
        for row in created:
            db.refresh(row)
        return created
    except Exception as e:
        db.rollback()
        print(f"❌ [AdminRouteSegments] Error saving segments: {e}")
        raise HTTPException(status_code=500, detail="구간 시간 저장 중 오류가 발생하였습니다.")
