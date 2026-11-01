"""
============================================================================
[전역 통합 알림 단일 디스패처 파사드 (core/notify.py)]
============================================================================

💡 이 파일의 역할:
어떤 도메인 앱(배차, 차량, 휴무, 게시판 등)이나 시스템 관제탑이든
단 한 줄의 함수(`core.notify` 또는 `core.safe_notify`) 호출만으로:
1. 미니앱 단일 DB(`miniapp_items`) 개인별 인박스 보존
2. WebSocket 0.1초 실시간 상단 헤더 뱃지(🔴) 갱신
3. 브라우저 백그라운드 Web Push (L3 이상) 자동 발송
4. 레거시 팝업 모달(Alert) 호환성을 100% 한 번에 처리합니다.
"""

from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any, Set
from sqlalchemy.orm import Session
from sqlalchemy import or_

logger = logging.getLogger("core.notify")


def resolve_target_user_ids(
    db: Session,
    target_user_ids: Optional[List[int]] = None,
    target_groups: Optional[List[str]] = None
) -> Set[int]:
    """
    [수신 대상 사원 ID 자동 분해 및 합집합 연산]
    명시적 유저 ID 목록과 타겟 그룹(부서/직무/노선) 코드를 결합하여
    실제 알림을 수신할 중복 없는 사원 ID Set을 반환합니다.
    """
    resolved_ids: Set[int] = set()

    if target_user_ids:
        resolved_ids.update(target_user_ids)

    if target_groups and len(target_groups) > 0:
        from models.user import UserProfile
        # 주그룹(primary_group) 일치 사원 조회
        profiles = db.query(UserProfile).filter(
            UserProfile.primary_group.in_(target_groups)
        ).all()
        for p in profiles:
            resolved_ids.add(p.user_id)

        # 부그룹(secondary_groups JSONB) 일치 사원 보강
        all_profiles = db.query(UserProfile).filter(
            UserProfile.secondary_groups.isnot(None)
        ).all()
        for p in all_profiles:
            sec_groups = p.secondary_groups or []
            if any(g in target_groups for g in sec_groups):
                resolved_ids.add(p.user_id)

    return resolved_ids


def notify(
    db: Session,
    *,
    category: str = "NOTIFICATION",
    title: Optional[str] = None,
    message: str,
    sender: Optional[Any] = None,
    target_user_ids: Optional[List[int]] = None,
    target_groups: Optional[List[str]] = None,
    level: int = 1,
    link: Optional[str] = None,
    background_tasks: Optional[Any] = None,
    extra_payload: Optional[Dict[str, Any]] = None
) -> List[Any]:
    """
    [전역 통합 알림 단일 디스패치 함수]
    
    :param db: SQLAlchemy DB 세션
    :param category: 'NOTIFICATION' | 'INSTRUCTION' | 'MESSAGE' | 'ALARM'
    :param title: 알림 또는 업무 지시 제목
    :param message: 핵심 텍스트 본문 (필수)
    :param sender: 발신 User 인스턴스 (None이면 시스템 발송)
    :param target_user_ids: 수신 사원 ID 리스트
    :param target_groups: 수신 그룹 코드 리스트 (예: ['운수1팀', '기사'])
    :param level: 알림 심각도 (1: 일반, 2: 성공토스트, 3: 중요공지+웹푸시, 4: 경보모달, 5: 비상락)
    :param link: 클릭 시 바로 이동할 업무 화면 URL
    :param background_tasks: FastAPI BackgroundTasks (비동기 푸시 예약용)
    :param extra_payload: 추가 메타데이터 dict
    """
    from models.miniapp import MiniappItem
    from models.alert import Alert

    sender_id = getattr(sender, "id", None) if sender else None
    resolved_uids = resolve_target_user_ids(db, target_user_ids, target_groups)
    created_items: List[MiniappItem] = []

    payload = extra_payload or {}
    payload["level"] = level

    # --------------------------------------------------------------------------
    # 1. 미니앱 단일 DB (miniapp_items) 적재
    # --------------------------------------------------------------------------
    if len(resolved_uids) > 0:
        # 개별 대상 사원들에게 각각 1:1 인박스 레코드 생성
        for uid in resolved_uids:
            item = MiniappItem(
                sender_id=sender_id,
                receiver_id=uid,
                category=category,
                title=title,
                content=message,
                status="PENDING",
                link=link,
                extra_payload=payload
            )
            db.add(item)
            created_items.append(item)
    else:
        # 대상이 전혀 지정되지 않은 경우: 전사 브로드캐스트 공지 (receiver_id is None)
        item = MiniappItem(
            sender_id=sender_id,
            receiver_id=None,
            category=category,
            title=title or "[전사공지] 시스템 안내",
            content=message,
            status="PENDING",
            link=link,
            extra_payload=payload
        )
        db.add(item)
        created_items.append(item)

    # --------------------------------------------------------------------------
    # 2. 레거시 팝업/모달 호환성 (Level >= 4 이거나 Alert 등록 시)
    # --------------------------------------------------------------------------
    if level >= 4:
        db_alert = Alert(
            message=f"{f'[{title}] ' if title else ''}{message}",
            level=level,
            style="warning" if level == 4 else "error",
            position="modal",
            redirect_url=link,
            user_id=sender_id or 1
        )
        db.add(db_alert)

    db.commit()

    # --------------------------------------------------------------------------
    # 3. 실시간 WebSocket 브로드캐스트 (상단 헤더 🔴 뱃지 0.1초 점등)
    # --------------------------------------------------------------------------
    try:
        from domain.ws.ws_service import manager
        ws_msg = {
            "type": "MINIAPP_UPDATE",
            "category": category,
            "title": title,
            "message": message,
            "level": level
        }
        if background_tasks:
            background_tasks.add_task(manager.broadcast, ws_msg)
        else:
            # 동기 환경에서는 asyncio 이벤트 루프가 있을 때 비동기 전송 시도
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(manager.broadcast(ws_msg))
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"⚠️ [core.notify] WebSocket 브로드캐스트 실패 (무시됨): {e}")

    # --------------------------------------------------------------------------
    # 4. 백그라운드 Web Push 발송 (Level >= 3 중요 공지 이상)
    # --------------------------------------------------------------------------
    if level >= 3:
        try:
            from domain.push.push_service import send_push_to_all
            push_title = title or ("🚨 [긴급 공지]" if level >= 4 else "📢 [업무 알림]")
            if background_tasks:
                background_tasks.add_task(
                    send_push_to_all,
                    title=push_title,
                    body=message,
                    url=link or "/"
                )
        except Exception as e:
            logger.warning(f"⚠️ [core.notify] Web Push 발송 예약 실패 (무시됨): {e}")

    logger.info(f"🔔 [core.notify] {len(created_items)}명에게 알림 디스패치 완료 (category={category}, level={level})")
    return created_items


def safe_notify(
    db: Session,
    *,
    category: str = "NOTIFICATION",
    title: Optional[str] = None,
    message: str,
    sender: Optional[Any] = None,
    target_user_ids: Optional[List[int]] = None,
    target_groups: Optional[List[str]] = None,
    level: int = 1,
    link: Optional[str] = None,
    background_tasks: Optional[Any] = None,
    extra_payload: Optional[Dict[str, Any]] = None
) -> List[Any]:
    """
    [안전 격리 알림 디스패처]
    알림 발송 도중 예기치 못한 에러가 발생해도 주 비즈니스 트랜잭션이 롤백되지 않도록
    try-except로 보호합니다.
    """
    try:
        return notify(
            db=db,
            category=category,
            title=title,
            message=message,
            sender=sender,
            target_user_ids=target_user_ids,
            target_groups=target_groups,
            level=level,
            link=link,
            background_tasks=background_tasks,
            extra_payload=extra_payload
        )
    except Exception as e:
        logger.error(f"❌ [safe_notify] 알림 발송 중 오류 발생 (비즈니스 정상 유지): {e}", exc_info=True)
        return []
