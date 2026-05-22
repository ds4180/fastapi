import sys
from datetime import date
from database import SessionLocal
from models import RouteMaster, RouteTimetable, Dispatch

# 가상 기사/차량 정적 리스트 정의 (MOC)
MOC_DRIVERS = [
    {"id": 1, "name": "김기사", "is_active": True},
    {"id": 2, "name": "이기사", "is_active": True},
    {"id": 3, "name": "박기사", "is_active": True},
    {"id": 4, "name": "최기사", "is_active": True},
    {"id": 5, "name": "정기사", "is_active": True},
]

MOC_VEHICLES = [
    {"id": 1, "vehicle_no": "제주70아1234", "is_active": True},
    {"id": 2, "vehicle_no": "제주70아5678", "is_active": True},
    {"id": 3, "vehicle_no": "제주70아9012", "is_active": True},
    {"id": 4, "vehicle_no": "제주70아3456", "is_active": True},
    {"id": 5, "vehicle_no": "제주70아7890", "is_active": True},
]

def run_verification():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("🚐 [검증 개시] 노선 버저닝 및 Dispatch 이력 보존 시뮬레이션")
        print("=" * 60)

        # 0. 깨끗한 검증 환경을 위해 기존 데이터 삭제
        print("\n🧹 1. 기존 데이터 정리 중...")
        db.query(Dispatch).delete()
        db.query(RouteTimetable).delete()
        db.query(RouteMaster).delete()
        db.commit()
        print("   -> 정리 완료.")

        # 1. 100번 노선 마스터 생성
        print("\n📌 2. 100번 노선 마스터 생성 (v1, v2 버저닝)")
        # v1: 5월 1일 ~ 5월 20일 (정규노선, 차량 5대)
        master_v1 = RouteMaster(
            route_name="100번",
            route_type="REGULAR",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 20),
            vehicle_count=5,
            version="v1"
        )
        # v2: 5월 21일 ~ 진행형 (정규노선, 차량 6대 - 증차)
        master_v2 = RouteMaster(
            route_name="100번",
            route_type="REGULAR",
            start_date=date(2026, 5, 21),
            end_date=None,
            vehicle_count=6,
            version="v2"
        )
        db.add_all([master_v1, master_v2])
        db.commit()
        db.refresh(master_v1)
        db.refresh(master_v2)
        print(f"   -> RouteMaster v1 등록 완료 (ID: {master_v1.id}, 유형: {master_v1.route_type})")
        print(f"   -> RouteMaster v2 등록 완료 (ID: {master_v2.id}, 유형: {master_v2.route_type})")

        # 2. 버전에 따른 상세 시간표 슬롯 등록
        print("\n🕒 3. 버전별 상세 시간표 매핑 등록")
        # v1 상세 시간표 (2개 운행 슬롯)
        v1_timetable = [
            RouteTimetable(route_master_id=master_v1.id, route_name="100번", seq=1, start_time="05:00", end_time="06:30", start_location="제주시", end_location="서귀포시", version="v1"),
            RouteTimetable(route_master_id=master_v1.id, route_name="100번", seq=2, start_time="05:30", end_time="07:00", start_location="제주시", end_location="서귀포시", version="v1")
        ]
        # v2 상세 시간표 (3개 운행 슬롯 - 증차 반영)
        v2_timetable = [
            RouteTimetable(route_master_id=master_v2.id, route_name="100번", seq=1, start_time="05:00", end_time="06:30", start_location="제주시", end_location="서귀포시", version="v2"),
            RouteTimetable(route_master_id=master_v2.id, route_name="100번", seq=2, start_time="05:15", end_time="06:45", start_location="제주시", end_location="서귀포시", version="v2"),
            RouteTimetable(route_master_id=master_v2.id, route_name="100번", seq=3, start_time="05:30", end_time="07:00", start_location="제주시", end_location="서귀포시", version="v2")
        ]
        db.add_all(v1_timetable + v2_timetable)
        db.commit()
        print(f"   -> 시간표 세팅 완료 (v1: {len(v1_timetable)}개 회차, v2: {len(v2_timetable)}개 회차)")

        # 3. 날짜 기준 자동 도면 탐색 엔진 시뮬레이션
        print("\n🔍 4. 날짜 기준 도면 자동 전환 테스트")
        
        # Test Case A: 2026년 5월 20일 (v1 조회되어야 함)
        target_date_a = date(2026, 5, 20)
        active_master_a = db.query(RouteMaster).filter(
            RouteMaster.route_name == "100번",
            RouteMaster.start_date <= target_date_a,
            (RouteMaster.end_date == None) | (RouteMaster.end_date >= target_date_a)
        ).first()
        
        assert active_master_a is not None, "5/20에 해당하는 활성 마스터가 있어야 합니다."
        assert active_master_a.version == "v1", f"5/20은 v1이어야 하지만 {active_master_a.version}가 조회되었습니다."
        
        timetables_a = db.query(RouteTimetable).filter(RouteTimetable.route_master_id == active_master_a.id).order_by(RouteTimetable.seq).all()
        assert len(timetables_a) == 2, f"v1 시간표는 2개여야 하지만 {len(timetables_a)}개입니다."
        print(f"   🟢 [통과] 2026-05-20 조회: {active_master_a.version} ({active_master_a.route_type}) - 총 {len(timetables_a)}개 시간표 슬롯 확인.")

        # Test Case B: 2026년 5월 21일 (v2 조회되어야 함)
        target_date_b = date(2026, 5, 21)
        active_master_b = db.query(RouteMaster).filter(
            RouteMaster.route_name == "100번",
            RouteMaster.start_date <= target_date_b,
            (RouteMaster.end_date == None) | (RouteMaster.end_date >= target_date_b)
        ).first()
        
        assert active_master_b is not None, "5/21에 해당하는 활성 마스터가 있어야 합니다."
        assert active_master_b.version == "v2", f"5/21은 v2여야 하지만 {active_master_b.version}가 조회되었습니다."
        
        timetables_b = db.query(RouteTimetable).filter(RouteTimetable.route_master_id == active_master_b.id).order_by(RouteTimetable.seq).all()
        assert len(timetables_b) == 3, f"v2 시간표는 3개여야 하지만 {len(timetables_b)}개입니다."
        print(f"   🟢 [통과] 2026-05-21 조회: {active_master_b.version} ({active_master_b.route_type}) - 총 {len(timetables_b)}개 시간표 슬롯 확인.")

        # 4. 당일 배정 및 물리 스냅샷 영속화 테스트
        print("\n💾 5. MOC 리스트 기반 당일 배정 및 스냅샷 보존 테스트")
        
        # 5/20 v1의 1회차(seq=1) 시간표 슬롯에 기사/차량 배정
        slot_to_assign = timetables_a[0]
        
        # 정적 MOC 리스트에서 기사 및 차량 할당 시뮬레이션
        assigned_driver = MOC_DRIVERS[1] # 이기사
        assigned_vehicle = MOC_VEHICLES[0] # 제주70아1234
        
        # Dispatch 객체 생성 및 스냅샷 기록
        dispatch_entry = Dispatch(
            target_date=target_date_a,
            timetable_id=slot_to_assign.id,
            driver_name=assigned_driver["name"],
            vehicle_no=assigned_vehicle["vehicle_no"],
            start_time=slot_to_assign.start_time,
            status="CONFIRMED",
            memo="정상 정기 배차 완료"
        )
        db.add(dispatch_entry)
        db.commit()
        db.refresh(dispatch_entry)
        print(f"   -> 5/20 배차 기록 완료: 기사={dispatch_entry.driver_name}, 차량={dispatch_entry.vehicle_no}, 출발시간={dispatch_entry.start_time}")

        # 5. 마스터 수정 시 과거 이력 왜곡 방지(영속성) 검증
        print("\n🛡️ 6. 마스터 수정 시 과거 이력 보존성(Snapshot) 최종 검증")
        # 마스터의 해당 시간표 출발 시간을 변경해본다. (05:00 -> 05:45)
        slot_to_assign.start_time = "05:45"
        db.commit()
        print("   -> [시뮬레이션] 마스터의 원래 시간표를 05:00에서 05:45로 수정하였습니다.")

        # 배차 레코드를 다시 쿼리해서 확인
        verified_dispatch = db.query(Dispatch).filter(Dispatch.id == dispatch_entry.id).one()
        assert verified_dispatch.start_time == "05:00", f"마스터가 수정되자 과거 배차의 출발 시간도 {verified_dispatch.start_time}로 오염되었습니다!"
        print(f"   🟢 [통과] 마스터 수정 후 배차 재확인: 출발시간={verified_dispatch.start_time} (이력 왜곡 차단 성공)")

        print("\n" + "=" * 60)
        print("🎉 [검증 성공] 모든 시나리오 테스트를 완벽히 통과하였습니다!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ [검증 실패] 오류가 발생했습니다: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_verification()
