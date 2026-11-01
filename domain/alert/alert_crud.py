"""
============================================================================
[사내 전역 공지 및 업무 지시 알림 비즈니스 로직 (domain/alert/alert_crud.py)]
============================================================================

💡 이 파일의 역할:
사내 알림 데이터베이스 CRUD 작업 및 실시간 통신(웹소켓 브로드캐스트, L5 웹푸시)을
처리하는 핵심 서비스 계층입니다.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from models import Alert, User
from domain.alert.alert_schema import AlertCreate, AlertUpdate
from domain.ws.ws_service import manager
from domain.push.push_service import send_push_to_all


def get_alert_list(db: Session) -> List[Alert]:
    """
    모든 알림 목록 조회 (관리자용 히스토리)
    """
    return db.query(Alert).order_by(Alert.create_date.desc()).all()


def get_active_alerts(db: Session, user: Optional[User] = None) -> List[Alert]:
    """
    현재 활성화된 알림 목록 조회 (로그인 사용자용 필터링)
    - 🔒 핵심 보안 규칙: 로그인하지 않은 비회원/손님(user is None)에게는 사내 업무 공지가 일체 반환되지 않습니다.
    - 활성 상태(`is_active == True`) 및 노출 기간(`start_date` ~ `end_date`) 일치 여부 확인
    - 특정 대상 유저(`target_users`)가 설정된 경우 해당 사용자에게만 필터링하여 노출
    """
    # 🛡️ [비로그인 차단] 로그인 세션이 없으면 즉시 빈 목록 반환 (사내 정보 유출 원천 차단)
    if not user:
        return []

    now = datetime.now()
    query = db.query(Alert).filter(
        Alert.is_active == True,
        (Alert.start_date == None) | (Alert.start_date <= now),
        (Alert.end_date == None) | (Alert.end_date >= now)
    )
    all_active = query.all()

    filtered_alerts: List[Alert] = []
    current_user_id_str = str(user.id)

    # Redis 클라이언트 로드 (타겟 그룹 실시간 판별용)
    rd_client = None
    try:
        from redis_config import rd
        rd_client = rd
    except Exception:
        pass

    for a in all_active:
        # DB 컬럼 누락 방어
        if not hasattr(a, 'position') or a.position is None:
            a.position = 'top'

        is_matched = False

        # 🎯 1. Redis 타겟 그룹 필터링 (target-group 앱 연산 출력물)
        if hasattr(a, 'target_group') and a.target_group and a.target_group.strip():
            tg_name = a.target_group.strip()
            if rd_client:
                try:
                    if rd_client.sismember(f"group:data:{tg_name}", current_user_id_str):
                        is_matched = True
                except Exception:
                    pass

        # 🎯 2. 특정 타겟 유저 필터링
        if not is_matched and a.target_users and a.target_users.strip():
            target_ids = [uid.strip() for uid in a.target_users.split(',') if uid.strip()]
            if current_user_id_str in target_ids:
                is_matched = True

        # 🎯 3. 그룹이나 개별 대상이 지정되지 않은 경우 전사 전체 공지로 노출
        has_group = bool(hasattr(a, 'target_group') and a.target_group and a.target_group.strip())
        has_users = bool(a.target_users and a.target_users.strip())
        if not has_group and not has_users:
            is_matched = True

        if is_matched:
            filtered_alerts.append(a)

    return filtered_alerts


async def create_alert(
    db: Session,
    alert_create: AlertCreate,
    user: User,
    background_tasks: BackgroundTasks
) -> Alert:
    """
    새로운 알림 생성
    - Level 5(시스템 락 / 비상 공지)의 경우 전 사용자에게 백그라운드 Web Push 자동 발송 (HIST-007 표준)
    - 실시간 WebSocket 브로드캐스트로 접속 중인 모든 클라이언트 즉각 갱신 유도
    """
    db_alert = Alert(
        message=alert_create.message,
        level=alert_create.level,
        style=alert_create.style,
        position=alert_create.position or 'top',
        category=alert_create.category or 'NOTIFICATION',
        target_group=alert_create.target_group,
        route=alert_create.route,
        redirect_url=alert_create.redirect_url,
        start_date=alert_create.start_date,
        end_date=alert_create.end_date,
        target_users=alert_create.target_users,
        confirm_text=alert_create.confirm_text,
        reset_sec=alert_create.reset_sec,
        create_date=datetime.now(),
        user=user
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)

    # 📱 [전역 통합 알림 단일화 core.notify 호출]
    cat = alert_create.category or ("INSTRUCTION" if alert_create.position == "modal" else "NOTIFICATION")
    target_uids = []
    if alert_create.target_users and alert_create.target_users.strip():
        for uid_s in alert_create.target_users.split(","):
            if uid_s.strip().isdigit():
                target_uids.append(int(uid_s.strip()))

    from core.notify import safe_notify
    safe_notify(
        db=db,
        category=cat,
        title=f"[{cat}] 사내 공지/지시",
        message=alert_create.message,
        sender=user,
        target_user_ids=target_uids if target_uids else None,
        target_groups=[alert_create.target_group] if alert_create.target_group else None,
        level=alert_create.level,
        link=alert_create.redirect_url,
        background_tasks=background_tasks,
        extra_payload={"alert_id": db_alert.id, "target_group": alert_create.target_group}
    )

    # 🔔 실시간 웹소켓 갱신 신호 브로드캐스트 (기존 레거시 팝업/토스트 화면 동기화)
    background_tasks.add_task(manager.broadcast, {"type": "new_alert"})

    return db_alert


def delete_alert(db: Session, db_alert: Alert):
    """
    알림 삭제
    """
    db.delete(db_alert)
    db.commit()


def get_alert(db: Session, alert_id: int) -> Optional[Alert]:
    """
    특정 알림 단건 조회
    """
    return db.query(Alert).filter(Alert.id == alert_id).first()


async def toggle_alert(db: Session, db_alert: Alert) -> Alert:
    """
    알림 활성/비활성 상태 전환
    - 상태 변경 후 실시간 웹소켓으로 클라이언트 화면 동기화
    """
    db_alert.is_active = not db_alert.is_active
    db.commit()
    db.refresh(db_alert)

    # 활성 상태가 변경되었으므로 클라이언트에 즉시 갱신 신호 발송
    try:
        await manager.broadcast({"type": "new_alert"})
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")

    return db_alert


def update_alert(db: Session, db_alert: Alert, alert_update: AlertUpdate) -> Alert:
    """
    알림 수정
    """
    for key, value in alert_update.model_dump(exclude_unset=True).items():
        setattr(db_alert, key, value)
    db.commit()
    db.refresh(db_alert)
    return db_alert
