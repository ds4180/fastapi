"""
============================================================================
[자율신경계 비동기 태스크 & 반복 Cron 스케줄러 검증 테스트 (tests/test_system_task.py)]
============================================================================
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.base import Base
from models.system import SystemTask
from domain.system.task_service import enqueue_task, calculate_next_scheduled_at
from domain.system.task_worker import process_next_task, register_handler, TASK_HANDLERS


@pytest.fixture
def db_session():
    """SQLite 인메모리 테스트 DB 세션 (to_thread 워커 스레드 호환: StaticPool 공유)"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SystemTask.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session
    session.close()


# --- 테스트용 모의 핸들러 등록 ---
@register_handler("TEST_SUCCESS")
async def _handle_test_success(task: SystemTask, db):
    return {"message": "정상 처리 완료", "input": task.payload}


@register_handler("TEST_FAIL")
async def _handle_test_fail(task: SystemTask, db):
    raise RuntimeError("의도적인 핸들러 에러 발생!")


def test_enqueue_task_and_process_success(db_session):
    """단발성 태스크 등록 및 성공 완료 검증"""
    asyncio.run(_async_test_enqueue_task_and_process_success(db_session))


async def _async_test_enqueue_task_and_process_success(db_session):
    # 1. 태스크 등록
    task = enqueue_task(
        db=db_session,
        task_type="TEST_SUCCESS",
        payload={"data": 123},
        priority=3
    )
    db_session.commit()
    assert task.id is not None
    assert task.status == "PENDING"

    # 2. 워커 실행
    processed = await process_next_task(db_session, worker_id="test-worker-1")
    assert processed is True

    # 3. 결과 확인
    db_session.refresh(task)
    assert task.status == "SUCCESS"
    assert task.progress_pct == 100
    assert task.worker_id == "test-worker-1"
    assert task.completed_at is not None
    assert task.result.get("message") == "정상 처리 완료"


def test_exponential_backoff_and_failed(db_session):
    """작업 실패 시 지수 백오프 연기 및 최대 재시도 초과 시 FAILED 확정 검증"""
    asyncio.run(_async_test_exponential_backoff_and_failed(db_session))


async def _async_test_exponential_backoff_and_failed(db_session):
    # 1. 실패 유발 태스크 등록 (max_retries=2)
    task = enqueue_task(
        db=db_session,
        task_type="TEST_FAIL",
        payload={},
        max_retries=2
    )
    db_session.commit()
    task_id = task.id

    now_before = datetime.now()

    # 2. 1차 실행 -> 실패 (지수 백오프 적용되어 미래로 연기, status=PENDING 유지)
    processed = await process_next_task(db_session, worker_id="test-worker-2")
    assert processed is True

    task = db_session.query(SystemTask).filter_by(id=task_id).first()
    assert task.status == "PENDING"
    assert task.retry_count == 1
    assert "의도적인 핸들러 에러" in task.error_log
    # 1차 실패 백오프(2^1 * 10초 = 20초 뒤)로 scheduled_at이 연기되었는지 확인
    assert task.scheduled_at > now_before + timedelta(seconds=15)

    # 3. 2차 실행을 위해 scheduled_at을 현재로 당겨서 즉시 처리 가능하게 설정
    task.scheduled_at = datetime.now() - timedelta(seconds=1)
    db_session.commit()

    processed_2 = await process_next_task(db_session, worker_id="test-worker-2")
    assert processed_2 is True

    task = db_session.query(SystemTask).filter_by(id=task_id).first()
    # max_retries(2)에 도달했으므로 FAILED로 확정
    assert task.status == "FAILED"
    assert task.retry_count == 2
    assert task.completed_at is not None


def test_self_reissuing_recurring_task(db_session):
    """반복 태스크(Interval / Cron) 완료 시 차기 작업 자율 재발행(Self-Reissuing) 검증"""
    asyncio.run(_async_test_self_reissuing_recurring_task(db_session))


async def _async_test_self_reissuing_recurring_task(db_session):
    # 1. 60초 간격 반복 태스크 등록
    task = enqueue_task(
        db=db_session,
        task_type="TEST_SUCCESS",
        payload={"job": "periodic_cleanup"},
        repeat_interval=60
    )
    db_session.commit()
    initial_id = task.id

    # 2. 워커 1회 실행
    processed = await process_next_task(db_session, worker_id="test-worker-loop")
    assert processed is True

    # 3. 원본 태스크 상태 확인 (SUCCESS로 보존)
    task_original = db_session.query(SystemTask).filter_by(id=initial_id).first()
    assert task_original.status == "SUCCESS"
    assert task_original.completed_at is not None

    # 4. 차기 태스크가 자동으로 발행되었는지 확인
    next_task = db_session.query(SystemTask).filter(
        SystemTask.parent_id == initial_id
    ).first()

    assert next_task is not None
    assert next_task.id != initial_id
    assert next_task.task_type == "TEST_SUCCESS"
    assert next_task.status == "PENDING"
    assert next_task.repeat_interval == 60
    assert next_task.payload.get("job") == "periodic_cleanup"
    # 차기 시각이 현재보다 약 60초 뒤로 스케줄링되었는지 검증
    assert next_task.scheduled_at > datetime.now() + timedelta(seconds=50)


def test_future_scheduled_task_not_picked_early(db_session):
    """미래 시점으로 예약된 태스크는 조기 실행되지 않고 대기하는지 검증"""
    asyncio.run(_async_test_future_scheduled_task_not_picked_early(db_session))


async def _async_test_future_scheduled_task_not_picked_early(db_session):
    # 미래(1시간 뒤)로 예약된 태스크 등록
    future_time = datetime.now() + timedelta(hours=1)
    task = enqueue_task(
        db=db_session,
        task_type="TEST_SUCCESS",
        payload={"future": True},
        scheduled_at=future_time
    )
    db_session.commit()

    # 워커 실행 시도 -> 현재 시각 기준 실행 대상이 없으므로 False 반환
    processed = await process_next_task(db_session, worker_id="test-worker-idle")
    assert processed is False

    # 상태는 계속 PENDING 유지
    db_session.refresh(task)
    assert task.status == "PENDING"
    assert task.worker_id is None


def test_bootstrap_default_cron_tasks(db_session):
    """자율신경계 필수 Cron 태스크 자동 시드(부트스트랩) 및 중복 등록 방지 검증"""
    from domain.system.task_service import bootstrap_default_cron_tasks
    
    # 1. 최초 시드: 6대 핵심 태스크 등록
    count1 = bootstrap_default_cron_tasks(db_session)
    assert count1 == 6

    tasks = db_session.query(SystemTask).all()
    assert len(tasks) == 6
    task_types = {t.task_type for t in tasks}
    assert "DYNAMIC_GROUP_REFRESH" in task_types
    assert "SYSTEM_WATCHDOG_INSPECTION" in task_types
    assert "DATA_RETENTION_GC" in task_types
    assert "MEDIA_GC" in task_types
    assert "CHECK_MINIAPP_ALARMS" in task_types
    assert "DISPATCH_AUTO_ANNOUNCE" in task_types

    # 2. 재실행 시 멱등성 검증 (이미 PENDING 상태이므로 0건 추가 등록)
    count2 = bootstrap_default_cron_tasks(db_session)
    assert count2 == 0
    assert db_session.query(SystemTask).count() == 6


def test_recurring_task_self_heals_on_permanent_failure(db_session):
    """반복 태스크가 max_retries 초과로 FAILED 마감되어도 차기 스케줄이 자동 예약(자가치유)되는지 검증"""
    asyncio.run(_async_test_recurring_task_self_heals_on_permanent_failure(db_session))


async def _async_test_recurring_task_self_heals_on_permanent_failure(db_session):
    task = enqueue_task(
        db=db_session,
        task_type="TEST_FAIL",
        payload={"job": "critical_cron"},
        repeat_interval=120,
        unique_key="cron:critical_cron:20261127070000",
        max_retries=2,
        timeout_sec=180,
    )
    db_session.commit()
    initial_id = task.id

    # 1차 실패 -> 백오프 재시도 대기
    assert await process_next_task(db_session, worker_id="test-worker-heal") is True
    t1 = db_session.query(SystemTask).filter_by(id=initial_id).first()
    assert t1.status == "PENDING"
    assert t1.retry_count == 1

    # 2차 실패 -> max_retries 도달하여 FAILED 마감 + 차기 회차 자동 발행!
    t1.scheduled_at = datetime.now() - timedelta(seconds=1)
    db_session.commit()
    assert await process_next_task(db_session, worker_id="test-worker-heal") is True

    t_failed = db_session.query(SystemTask).filter_by(id=initial_id).first()
    assert t_failed.status == "FAILED"
    assert t_failed.retry_count == 2
    assert t_failed.completed_at is not None

    next_task = db_session.query(SystemTask).filter(SystemTask.parent_id == initial_id).first()
    assert next_task is not None
    assert next_task.status == "PENDING"
    assert next_task.task_type == "TEST_FAIL"
    assert next_task.repeat_interval == 120
    assert next_task.max_retries == 2
    assert next_task.timeout_sec == 180
    assert next_task.payload == {"job": "critical_cron"}
    assert next_task.unique_key.startswith("cron:critical_cron:")
    assert next_task.scheduled_at > datetime.now() + timedelta(seconds=100)


def test_dynamic_group_refresh_handler_imports_rd(db_session, monkeypatch):
    """DYNAMIC_GROUP_REFRESH 핸들러가 redis_config.rd를 정상 임포트하여 실행하는지 검증"""
    import domain.system.group_service as group_service

    called = {}

    def fake_refresh(db, rd):
        called["rd"] = rd
        return {"today_working": 10}

    monkeypatch.setattr(group_service, "calculate_and_refresh_dynamic_groups", fake_refresh)

    task = enqueue_task(db=db_session, task_type="DYNAMIC_GROUP_REFRESH", payload={})
    db_session.commit()

    processed = asyncio.run(process_next_task(db_session, worker_id="test-worker-dyn"))
    assert processed is True

    refreshed = db_session.query(SystemTask).filter_by(id=task.id).first()
    assert refreshed.status == "SUCCESS"
    assert refreshed.result.get("results") == {"today_working": 10}
    assert "rd" in called


@register_handler("TEST_BLOCKING_SYNC")
def _handle_test_blocking_sync(task: SystemTask, db):
    import time
    time.sleep(0.25)
    return {"blocked_ok": True}


def test_sync_handler_does_not_block_event_loop(db_session):
    """무거운 동기(def) 핸들러가 실행되는 동안에도 메인 asyncio 이벤트 루프가 멈추지 않는지 검증"""
    async def _run():
        import time

        task = enqueue_task(db=db_session, task_type="TEST_BLOCKING_SYNC", payload={})
        db_session.commit()

        ticks = []

        async def heartbeat():
            for _ in range(4):
                await asyncio.sleep(0.05)
                ticks.append(time.monotonic())

        t0 = time.monotonic()
        worker_coro = asyncio.create_task(process_next_task(db_session, worker_id="test-worker-thread"))
        hb_coro = asyncio.create_task(heartbeat())

        processed, _ = await asyncio.gather(worker_coro, hb_coro)
        assert processed is True
        # 0.25초 블로킹 작업 중에도 0.05초 주기의 하트비트가 최소 3회 이상 정상 실행되었는지 확인
        assert len(ticks) == 4
        assert (ticks[0] - t0) < 0.15

        refreshed = db_session.query(SystemTask).filter_by(id=task.id).first()
        assert refreshed.status == "SUCCESS"
        assert refreshed.result == {"blocked_ok": True}

    asyncio.run(_run())


def test_retention_gc_handles_parent_id_chain_and_cancelled_tasks():
    """만료 부모 태스크 삭제 시 생존 자식 태스크의 parent_id가 NULL로 안전 해제되고 FK 오류가 없는지 검증"""
    from sqlalchemy import event
    from models.system import SystemConfig
    from models.user import User, UserSession
    from models.audit import AuditLog
    from domain.system.retention_service import run_data_retention_gc

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite에서도 실제 PostgreSQL처럼 외래키(FK) 제약을 강제 활성화하여 테스트
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    for tbl in (User.__table__, SystemConfig.__table__, SystemTask.__table__, UserSession.__table__, AuditLog.__table__):
        tbl.create(engine)

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        now = datetime.now()
        old_parent = SystemTask(
            task_type="CHECK_MINIAPP_ALARMS",
            status="SUCCESS",
            completed_at=now - timedelta(days=35),
            created_at=now - timedelta(days=35),
        )
        db.add(old_parent)
        db.flush()

        surviving_child = SystemTask(
            task_type="CHECK_MINIAPP_ALARMS",
            status="SUCCESS",
            parent_id=old_parent.id,
            completed_at=now - timedelta(days=5),
            created_at=now - timedelta(days=5),
        )
        old_cancelled = SystemTask(
            task_type="THUMB_GEN",
            status="CANCELLED",
            completed_at=None,
            created_at=now - timedelta(days=35),
        )
        db.add_all([surviving_child, old_cancelled])
        db.commit()

        surviving_id = surviving_child.id
        old_parent_id = old_parent.id
        old_cancelled_id = old_cancelled.id

        report = run_data_retention_gc(db, rd=None)
        assert report["status"] == "SUCCESS"
        assert report["deleted_tasks"] == 2

        assert db.query(SystemTask).filter_by(id=old_parent_id).first() is None
        assert db.query(SystemTask).filter_by(id=old_cancelled_id).first() is None

        kept = db.query(SystemTask).filter_by(id=surviving_id).first()
        assert kept is not None
        assert kept.parent_id is None
    finally:
        db.close()


@register_handler("TEST_SLOW_HANG")
async def _handle_test_slow_hang(task: SystemTask, db):
    await asyncio.sleep(5)
    return {"unreachable": True}


def test_task_execution_timeout_enforced(db_session):
    """timeout_sec 초과 시 asyncio.wait_for로 강제 중단되어 재시도/실패 처리되는지 검증"""
    async def _run():
        import time

        task = enqueue_task(
            db=db_session,
            task_type="TEST_SLOW_HANG",
            payload={},
            timeout_sec=1,
            max_retries=1,
            repeat_interval=60,
        )
        db_session.commit()
        tid = task.id

        t0 = time.monotonic()
        processed = await process_next_task(db_session, worker_id="test-worker-timeout")
        elapsed = time.monotonic() - t0

        assert processed is True
        assert elapsed < 2.5

        db_session.expire_all()
        failed = db_session.query(SystemTask).filter_by(id=tid).first()
        assert failed.status == "FAILED"
        assert "타임아웃 초과" in (failed.error_log or "")
        assert failed.worker_id is None

        # 반복 태스크였으므로 타임아웃 영구 실패 시에도 차기 스케줄이 자동 자가치유 예약되었는지 검증
        next_task = db_session.query(SystemTask).filter(SystemTask.parent_id == tid).first()
        assert next_task is not None
        assert next_task.status == "PENDING"

    asyncio.run(_run())


def test_finalize_success_rejects_lost_ownership(db_session):
    """이미 회수되어 소유권을 상실한 좀비 작업이 뒤늦게 완료되어도 SUCCESS 덮어쓰기 및 중복 크론 발행을 차단하는지 검증"""
    from domain.system.task_worker import _finalize_task_success_sync

    task = enqueue_task(
        db=db_session,
        task_type="TEST_SUCCESS",
        payload={},
        repeat_interval=60,
    )
    task.status = "PENDING"
    task.worker_id = None
    db_session.commit()

    applied = _finalize_task_success_sync(db_session, task.id, "stale-worker-1", {"ok": True})
    assert applied is False

    db_session.refresh(task)
    assert task.status == "PENDING"
    assert db_session.query(SystemTask).filter(SystemTask.parent_id == task.id).count() == 0


def test_admin_retry_blocks_duplicate_recurring_and_bulk_clear(db_session):
    """활성 차기 회차가 있는 정기 태스크 재시도 409 차단 및 벌크 일괄 정리 검증"""
    from fastapi import HTTPException
    from domain.system.task_admin_service import retry_task_by_id, clear_tasks_by_status

    old_done = SystemTask(
        task_type="CHECK_MINIAPP_ALARMS",
        status="SUCCESS",
        repeat_interval=60,
        unique_key="cron:check_miniapp_alarms:20261127080000",
    )
    db_session.add(old_done)
    db_session.flush()

    active_next = SystemTask(
        task_type="CHECK_MINIAPP_ALARMS",
        status="PENDING",
        repeat_interval=60,
        parent_id=old_done.id,
        unique_key="cron:check_miniapp_alarms:20261127080100",
    )
    db_session.add(active_next)
    db_session.commit()

    # 1. 활성 차기 회차가 이미 존재하므로 옛날 SUCCESS 행 재시도는 409로 차단되어야 함
    with pytest.raises(HTTPException) as exc_info:
        retry_task_by_id(db_session, old_done.id, "admin")
    assert exc_info.value.status_code == 409

    # 2. SUCCESS 일괄 벌크 삭제 시 FK 오류 없이 삭제되고 생존 PENDING 자식의 parent_id가 NULL 해제됨
    deleted = clear_tasks_by_status(db_session, "SUCCESS")
    assert deleted == 1
    db_session.expire_all()
    kept = db_session.query(SystemTask).filter_by(id=active_next.id).first()
    assert kept is not None
    assert kept.parent_id is None


@register_handler("TEST_CANCELLED")
def _handle_test_cancelled(task: SystemTask, db):
    return {"status": "cancelled", "reason": "원본 파일 없음"}


def test_handler_cancelled_status_is_preserved(db_session):
    """핸들러가 status='cancelled'를 반환하면 SUCCESS로 덮어쓰지 않고 CANCELLED로 마감되는지 검증"""
    task = enqueue_task(db=db_session, task_type="TEST_CANCELLED", payload={})
    db_session.commit()

    processed = asyncio.run(process_next_task(db_session, worker_id="test-worker-cancel"))
    assert processed is True

    db_session.expire_all()
    refreshed = db_session.query(SystemTask).filter_by(id=task.id).first()
    assert refreshed.status == "CANCELLED"
    assert refreshed.result.get("reason") == "원본 파일 없음"
