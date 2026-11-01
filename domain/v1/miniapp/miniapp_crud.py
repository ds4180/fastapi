"""
============================================================================
[미니앱 단일 텍스트 통합 엔진 CRUD (miniapp_crud.py)]
============================================================================
"""

from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from models.miniapp import MiniappItem
from models.user import User
from domain.v1.miniapp.miniapp_schema import MiniappItemCreate, MiniappItemUpdate


def get_user_miniapp_counts(db: Session, user_id: int) -> Dict[str, int]:
    """
    [상단 헤더 뱃지 및 슬라이더 뱃지 실시간 계산]
    - NOTIFICATION: 미확인 전사/개인 알림 (status == 'PENDING')
    - INSTRUCTION : 미완료 지시사항 (status != 'COMPLETED')
    - MESSAGE     : 안 읽은 메시지 (status == 'PENDING')
    - MEMO        : 미완료 개인 메모 (status != 'COMPLETED')
    - ALARM       : 대기 중인 알람 (status != 'COMPLETED')
    - TOTAL       : 위 5대 미결 항목의 총합 (상단 헤더 🔴 뱃지용)
    """
    # 1. 알림 (NOTIFICATION)
    noti_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "NOTIFICATION",
        or_(MiniappItem.receiver_id == user_id, MiniappItem.receiver_id.is_(None)),
        MiniappItem.status == "PENDING"
    ).scalar() or 0

    # 2. 지시사항 (INSTRUCTION)
    inst_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "INSTRUCTION",
        MiniappItem.receiver_id == user_id,
        MiniappItem.status != "COMPLETED"
    ).scalar() or 0

    # 3. 메시징 (MESSAGE)
    msg_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "MESSAGE",
        MiniappItem.receiver_id == user_id,
        MiniappItem.status == "PENDING"
    ).scalar() or 0

    # 4. 메모 (MEMO)
    memo_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "MEMO",
        MiniappItem.sender_id == user_id,
        MiniappItem.status != "COMPLETED"
    ).scalar() or 0

    # 5. 알람 (ALARM)
    alarm_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "ALARM",
        MiniappItem.sender_id == user_id,
        MiniappItem.status != "COMPLETED"
    ).scalar() or 0

    total = noti_count + inst_count + msg_count + memo_count + alarm_count

    return {
        "NOTIFICATION": noti_count,
        "INSTRUCTION": inst_count,
        "MESSAGE": msg_count,
        "MEMO": memo_count,
        "ALARM": alarm_count,
        "TOTAL": total,
    }


def get_user_miniapp_items(
    db: Session,
    user_id: int,
    category: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[MiniappItem]:
    """
    사용자가 열람할 수 있는 미니앱 피드 목록 조회:
    - 내가 수신자인 아이템
    - 수신자가 NULL인 전사 알림
    - 내가 발신한 개인 메모 및 알람
    """
    query = db.query(MiniappItem).filter(
        or_(
            MiniappItem.receiver_id == user_id,
            and_(MiniappItem.category == "NOTIFICATION", MiniappItem.receiver_id.is_(None)),
            and_(MiniappItem.sender_id == user_id, MiniappItem.receiver_id == user_id)
        )
    )

    if category:
        query = query.filter(MiniappItem.category == category)
    if status:
        query = query.filter(MiniappItem.status == status)

    return query.order_by(MiniappItem.created_at.desc()).offset(skip).limit(limit).all()


def create_miniapp_item(db: Session, sender: User, item_in: MiniappItemCreate) -> MiniappItem:
    """
    [미니앱 단일 아이템 생성]
    발신자-수신자 관계 공식에 따라 카테고리를 보정하고 영속화합니다.
    """
    receiver_id = item_in.receiver_id
    cat = (item_in.category or "MEMO").upper()

    # 1. 보내는 사람과 받는 사람이 같거나 수신자가 명시되지 않은 경우
    if receiver_id is None or receiver_id == sender.id:
        receiver_id = sender.id
        if cat not in ("MEMO", "ALARM"):
            cat = "MEMO"

    # 2. 보내는 사람과 받는 사람이 다른 경우
    else:
        if cat in ("MEMO", "ALARM"):
            cat = "MESSAGE"  # 타인에게 보낼 때는 기본적으로 메시지

    new_item = MiniappItem(
        sender_id=sender.id,
        receiver_id=receiver_id,
        category=cat,
        title=item_in.title,
        content=item_in.content,
        status="PENDING",
        target_time=item_in.target_time,
        link=item_in.link,
        extra_payload=item_in.extra_payload or {}
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


def update_miniapp_item(
    db: Session,
    item_id: int,
    user_id: int,
    item_update: MiniappItemUpdate
) -> Optional[MiniappItem]:
    """
    미니앱 아이템 상태 또는 내용 변경 (권한: 수신자 또는 발신자)
    """
    item = db.query(MiniappItem).filter(MiniappItem.id == item_id).first()
    if not item:
        return None

    # 수신자이거나 작성자인 경우에만 수정 가능
    if item.receiver_id != user_id and item.sender_id != user_id and item.receiver_id is not None:
        return None

    if item_update.status is not None:
        item.status = item_update.status
    if item_update.title is not None:
        item.title = item_update.title
    if item_update.content is not None:
        item.content = item_update.content
    if item_update.target_time is not None:
        item.target_time = item_update.target_time
    if item_update.extra_payload is not None:
        item.extra_payload = item_update.extra_payload

    db.commit()
    db.refresh(item)
    return item


def delete_miniapp_item(db: Session, item_id: int, user_id: int) -> bool:
    """
    미니앱 아이템 삭제 (권한: 작성자 또는 수신자)
    """
    item = db.query(MiniappItem).filter(MiniappItem.id == item_id).first()
    if not item:
        return False

    if item.sender_id != user_id and item.receiver_id != user_id:
        return False

    db.delete(item)
    db.commit()
    return True
