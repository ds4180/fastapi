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

from models.base import Base
from models.system import SystemTask
from domain.system.task_service import enqueue_task, calculate_next_scheduled_at
from domain.system.task_worker import process_next_task, register_handler, TASK_HANDLERS


@pytest.fixture
def db_session():
    """SQLite 인메모리 테스트 DB 세션"""
    engine = create_engine("sqlite:///:memory:")
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
