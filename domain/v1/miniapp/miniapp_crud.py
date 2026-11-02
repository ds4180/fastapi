"""
============================================================================
[미니앱 단일 텍스트 통합 엔진 CRUD (miniapp_crud.py)]
============================================================================
"""

from typing import Optional, List, Dict, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, case
from models.miniapp import MiniappItem, MiniappRead
from models.user import User
from domain.v1.miniapp.miniapp_schema import MiniappItemCreate, MiniappItemUpdate


def get_user_miniapp_counts(db: Session, user_id: int) -> Dict[str, int]:
    """
    [상단 헤더 뱃지 및 슬라이더 뱃지 실시간 계산 (방안 B 1:N 확인 서명 모델 반영)]
    - 전사 공지(receiver_id IS NULL)는 MiniappRead 서명 테이블에 현재 사원의 확인 기록이 없는 경우에만 미결 카운트에 산입합니다.
    - NOTIFICATION: 미확인 전사/개인 알림
    - INSTRUCTION : 미완료 전사/개인 지시사항
    - MESSAGE     : 안 읽은 메시지 (status == 'PENDING')
    - MEMO        : 미완료 개인 메모 (status != 'COMPLETED')
    - ALARM       : 대기 중인 알람 (status != 'COMPLETED')
    - TOTAL       : 위 5대 미결 항목의 총합 (상단 헤더 🔴 뱃지용)
    """
    # 📌 현재 사원이 이미 확인(읽음) 또는 삭제한 전사 공지/지시 item_id 서브쿼리
    read_item_ids_subquery = db.query(MiniappRead.item_id).filter(
        MiniappRead.user_id == user_id,
        MiniappRead.status.in_(["READ", "CONFIRMED", "COMPLETED", "DELETED"])
    ).subquery()

    # 1. 알림 및 공지 (NOTIFICATION, NOTICE, URGENT_NOTICE 포괄, DELETED 제외)
    noti_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category.in_(["NOTIFICATION", "NOTICE", "URGENT_NOTICE"]),
        MiniappItem.status != "DELETED",
        or_(
            and_(MiniappItem.receiver_id == user_id, MiniappItem.status == "PENDING"),
            and_(
                MiniappItem.receiver_id.is_(None),
                MiniappItem.status == "PENDING",
                ~MiniappItem.id.in_(read_item_ids_subquery)
            )
        )
    ).scalar() or 0

    # 2. 지시사항 (INSTRUCTION, DELETED 제외)
    inst_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "INSTRUCTION",
        MiniappItem.status != "DELETED",
        or_(
            and_(MiniappItem.receiver_id == user_id, MiniappItem.status.notin_(["CONFIRMED", "COMPLETED"])),
            and_(
                MiniappItem.receiver_id.is_(None),
                MiniappItem.status.notin_(["CONFIRMED", "COMPLETED"]),
                ~MiniappItem.id.in_(read_item_ids_subquery)
            )
        )
    ).scalar() or 0

    # 3. 메시징 (MESSAGE, DELETED 제외)
    msg_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "MESSAGE",
        MiniappItem.receiver_id == user_id,
        MiniappItem.status == "PENDING"
    ).scalar() or 0

    # 4. 메모 (MEMO, DELETED 제외)
    memo_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "MEMO",
        MiniappItem.sender_id == user_id,
        MiniappItem.status.notin_(["COMPLETED", "DELETED"])
    ).scalar() or 0

    # 5. 알람 (ALARM, DELETED 제외)
    alarm_count = db.query(func.count(MiniappItem.id)).filter(
        MiniappItem.category == "ALARM",
        MiniappItem.sender_id == user_id,
        MiniappItem.status.notin_(["COMPLETED", "DELETED"])
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
) -> List[Tuple[MiniappItem, str, Optional[datetime]]]:
    """
    사용자가 열람할 수 있는 미니앱 피드 목록 조회 (SQL 1:N LEFT JOIN 모델):
    - 내가 수신자인 아이템 (receiver_id == user_id)
    - 수신자가 NULL인 전사 공지/지시사항 (receiver_id IS NULL)
    - 내가 발신한 개인 메모 및 알람 (sender_id == user_id AND receiver_id == user_id)
    
    반환 형태: List of (MiniappItem, computed_status, confirmed_at)
    전사 공지의 경우 MiniappRead를 LEFT JOIN하여 현재 로그인 사원의 확인 여부에 따라 status를 동적으로 결정합니다.
    """
    # 📌 사원 관점의 계산된 status:
    # 전사 공지(receiver_id IS NULL)일 때는 MiniappRead.status가 존재하면 그 값을, 없으면 'PENDING'을 부여.
    # 개인 수신일 때는 MiniappItem.status를 그대로 사용.
    computed_status_expr = case(
        (
            MiniappItem.receiver_id.is_(None),
            func.coalesce(MiniappRead.status, "PENDING")
        ),
        else_=MiniappItem.status
    ).label("computed_status")

    query = db.query(
        MiniappItem,
        computed_status_expr,
        MiniappRead.confirmed_at
    ).outerjoin(
        MiniappRead,
        and_(
            MiniappRead.item_id == MiniappItem.id,
            MiniappRead.user_id == user_id
        )
    ).filter(
        MiniappItem.status != "DELETED",  # 🛡️ 관리자/작성자가 논리 삭제한 원본 제외
        computed_status_expr != "DELETED",  # 🛡️ 사원이 본인 피드에서 삭제(숨김)한 아이템 제외
        or_(
            MiniappItem.receiver_id == user_id,
            MiniappItem.receiver_id.is_(None),
            and_(MiniappItem.sender_id == user_id, MiniappItem.receiver_id == user_id)
        )
    )

    if category:
        if category in ("NOTIFICATION", "NOTICE", "URGENT_NOTICE"):
            query = query.filter(MiniappItem.category.in_(["NOTIFICATION", "NOTICE", "URGENT_NOTICE"]))
        else:
            query = query.filter(MiniappItem.category == category)

    if status:
        query = query.filter(computed_status_expr == status)

    rows = query.order_by(MiniappItem.created_at.desc()).offset(skip).limit(limit).all()
    return rows


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
) -> Optional[Tuple[MiniappItem, str, Optional[datetime]]]:
    """
    미니앱 아이템 상태 또는 내용 변경 (방안 B 1:N 확인 서명 격리 반영):
    - 전사 공지(receiver_id IS NULL)인 경우:
      원본 MiniappItem은 수정하지 않고, MiniappRead 테이블에 현재 사원의 확인 서명(status, confirmed_at)을 UPSERT 기록합니다.
    - 개인 아이템인 경우:
      기존대로 MiniappItem.status를 직접 변경하고 extra_payload['confirmed_at']을 기록합니다.
    - 반환: (MiniappItem, 사원별_status, confirmed_at)
    """
    item = db.query(MiniappItem).filter(MiniappItem.id == item_id).first()
    if not item:
        return None

    # 1. 📢 전사 공지/지시사항(receiver_id IS NULL)의 상태 변경 처리 (방안 B)
    if item.receiver_id is None:
        if item_update.status is not None:
            read_rec = db.query(MiniappRead).filter(
                MiniappRead.item_id == item_id,
                MiniappRead.user_id == user_id
            ).first()

            now_dt = datetime.now()
            if not read_rec:
                read_rec = MiniappRead(
                    item_id=item_id,
                    user_id=user_id,
                    status=item_update.status,
                    confirmed_at=now_dt
                )
                db.add(read_rec)
            else:
                read_rec.status = item_update.status
                read_rec.confirmed_at = now_dt

            db.commit()
            db.refresh(read_rec)
            return (item, read_rec.status, read_rec.confirmed_at)
        return (item, "PENDING", None)

    # 2. 👤 1:1 수신자 또는 작성자 권한 검증
    if item.receiver_id != user_id and item.sender_id != user_id:
        return None

    confirmed_at = None
    if item_update.status is not None:
        item.status = item_update.status
        # [양방향 수신확인] CONFIRMED/COMPLETED/READ 상태 전환 시 confirmed_at 타임스탬프 기록
        if item_update.status in ("CONFIRMED", "COMPLETED", "READ"):
            payload = dict(item.extra_payload or {})
            if "confirmed_at" not in payload:
                payload["confirmed_at"] = datetime.now().isoformat()
            item.extra_payload = payload
            try:
                confirmed_at = datetime.fromisoformat(payload["confirmed_at"])
            except Exception:
                confirmed_at = datetime.now()
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(item, "extra_payload")

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
    return (item, item.status, confirmed_at)


def delete_miniapp_item(db: Session, item_id: int, user: User) -> bool:
    """
    미니앱 아이템 Soft Delete (논리 삭제 표준 준수):
    - 절대 물리 삭제(db.delete)를 수행하지 않고 이력과 무결성을 영구 보존합니다.
    - 관리자가 이미 삭제해서 DB에 없거나 조회가 되지 않는 경우에도 에러 없이 자연스럽게 제외(True)합니다.
    - 1. 관리자(rank >= 8): 원본 MiniappItem.status = 'DELETED' 처리 (전사 피드 비노출)
    - 2. 일반 사원:
         - 본인 작성 메모/알람, 본인 수신 메시지: MiniappItem.status = 'DELETED' 처리
         - 전사 공지(receiver_id IS NULL): 원본은 유지하고 사원별 MiniappRead.status = 'DELETED' 기록 (해당 사원 피드에서만 제외)
    """
    item = db.query(MiniappItem).filter(MiniappItem.id == item_id).first()
    # 🛡️ 이미 물리적으로 삭제되었거나 존재하지 않는 경우에도 성공 처리(피드에서 조용히 소거)
    if not item:
        return True

    user_rank = user.rank() if callable(getattr(user, "rank", None)) else getattr(user, "rank", 0)
    is_admin = int(user_rank or 0) >= 8

    from sqlalchemy.orm.attributes import flag_modified
    now_iso = datetime.now().isoformat()

    # 1. 👑 관리자 권한 삭제: 원본 soft delete (모든 일반 피드에서 비노출)
    if is_admin:
        item.status = "DELETED"
        payload = dict(item.extra_payload or {})
        payload["deleted_at"] = now_iso
        payload["deleted_by"] = user.id
        payload["delete_type"] = "ADMIN_SOFT_DELETE"
        item.extra_payload = payload
        flag_modified(item, "extra_payload")
        db.commit()
        return True

    # 2. 👤 일반 사원 삭제:
    # 2-1. 본인이 작성자이거나 수신자인 1:1 아이템 (메모, 알람, 메시지) -> 원본 status를 DELETED로 변경
    if item.sender_id == user.id or item.receiver_id == user.id:
        item.status = "DELETED"
        payload = dict(item.extra_payload or {})
        payload["deleted_at"] = now_iso
        payload["deleted_by"] = user.id
        payload["delete_type"] = "USER_SOFT_DELETE"
        item.extra_payload = payload
        flag_modified(item, "extra_payload")
        db.commit()
        return True

    # 2-2. 전사 공지/지시사항(receiver_id IS NULL)인 경우 -> 사원별 MiniappRead에 'DELETED' 기록
    if item.receiver_id is None:
        read_rec = db.query(MiniappRead).filter(
            MiniappRead.item_id == item_id,
            MiniappRead.user_id == user.id
        ).first()

        now_dt = datetime.now()
        if not read_rec:
            read_rec = MiniappRead(
                item_id=item_id,
                user_id=user.id,
                status="DELETED",
                confirmed_at=now_dt
            )
            db.add(read_rec)
        else:
            read_rec.status = "DELETED"
            read_rec.confirmed_at = now_dt

        db.commit()
        return True

    # 2-3. 타인의 1:1 아이템인 경우 삭제 불가
    return False
