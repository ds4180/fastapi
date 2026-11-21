"""
============================================================================
[미니앱 단일 텍스트 통합 엔진 API 라우터 (miniapp_router.py)]
============================================================================
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from core.deps import get_current_user
from models.user import User
from domain.v1.miniapp import miniapp_schema, miniapp_crud

router = APIRouter(
    prefix="/v1/miniapps",
    tags=["MiniApp"]
)


def _serialize_miniapp_item(item, computed_status: str, confirmed_at) -> miniapp_schema.MiniappItemResponse:
    sender_name = None
    if item.sender:
        sender_name = getattr(item.sender, "real_name", None) or getattr(item.sender, "name", None) or getattr(item.sender, "username", None)

    extra_payload = dict(item.extra_payload or {})
    if confirmed_at and "confirmed_at" not in extra_payload:
        extra_payload["confirmed_at"] = confirmed_at.isoformat() if hasattr(confirmed_at, "isoformat") else str(confirmed_at)

    return miniapp_schema.MiniappItemResponse(
        id=item.id,
        sender_id=item.sender_id,
        sender_name=sender_name,
        receiver_id=item.receiver_id,
        category=item.category,
        title=item.title,
        content=item.content,
        status=computed_status,
        target_time=item.target_time,
        link=item.link,
        extra_payload=extra_payload,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/counts", response_model=miniapp_schema.MiniappCountsResponse)
def get_miniapp_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [상단 헤더 뱃지 & 동적 폼 슬라이더 미결 카운트 API]
    """
    counts = miniapp_crud.get_user_miniapp_counts(db, current_user.id)
    return miniapp_schema.MiniappCountsResponse(**counts)


@router.get("/summary", response_model=miniapp_schema.MiniappSummaryResponse)
def get_miniapp_summary(
    category: Optional[str] = Query(None, description="MEMO, ALARM, INSTRUCTION, MESSAGE, NOTIFICATION"),
    status: Optional[str] = Query(None, description="PENDING, ONGOING, COMPLETED, READ"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [미니앱 카운트 + 피드 목록 단일 통합 조회]
    - 1회 DB 세션 및 1회 HTTP 요청으로 카운트와 피드 목록을 동시에 반환해 부하를 줄입니다.
    """
    counts = miniapp_crud.get_user_miniapp_counts(db, current_user.id)
    items_with_status = miniapp_crud.get_user_miniapp_items(
        db=db,
        user_id=current_user.id,
        category=category,
        status=status,
        skip=skip,
        limit=limit,
    )
    items = [_serialize_miniapp_item(item, st, cat) for item, st, cat in items_with_status]
    return miniapp_schema.MiniappSummaryResponse(
        counts=miniapp_schema.MiniappCountsResponse(**counts),
        items=items,
    )


@router.get("", response_model=List[miniapp_schema.MiniappItemResponse])
def get_miniapp_items(
    category: Optional[str] = Query(None, description="MEMO, ALARM, INSTRUCTION, MESSAGE, NOTIFICATION"),
    status: Optional[str] = Query(None, description="PENDING, ONGOING, COMPLETED, READ"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [미니앱 단일 액션 피드 목록 조회 (SQL 1:N 확인 서명 격리 반영)]
    """
    items_with_status = miniapp_crud.get_user_miniapp_items(
        db=db,
        user_id=current_user.id,
        category=category,
        status=status,
        skip=skip,
        limit=limit
    )

    return [_serialize_miniapp_item(item, computed_status, confirmed_at) for item, computed_status, confirmed_at in items_with_status]


@router.post("", response_model=miniapp_schema.MiniappItemResponse, status_code=status.HTTP_201_CREATED)
def create_miniapp_item(
    item_in: miniapp_schema.MiniappItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [미니앱 아이템 생성 (메모/알람/메시지/지시사항)]
    - 보내는 사람 == 받는 사람 ➔ 메모 또는 알람으로 자동 처리
    - 타인에게 보낼 때 ➔ 메시지 또는 업무 지시사항으로 처리
    """
    item = miniapp_crud.create_miniapp_item(db, sender=current_user, item_in=item_in)
    sender_name = getattr(current_user, "name", None) or getattr(current_user, "username", None)
    
    return miniapp_schema.MiniappItemResponse(
        id=item.id,
        sender_id=item.sender_id,
        sender_name=sender_name,
        receiver_id=item.receiver_id,
        category=item.category,
        title=item.title,
        content=item.content,
        status=item.status,
        target_time=item.target_time,
        link=item.link,
        extra_payload=item.extra_payload or {},
        created_at=item.created_at,
        updated_at=item.updated_at
    )


@router.patch("/{item_id}", response_model=miniapp_schema.MiniappItemResponse)
def update_miniapp_item(
    item_id: int,
    item_update: miniapp_schema.MiniappItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [미니앱 상태 변경 (지시사항 완료, 메모 완료, 읽음 처리)]
    - 전사 공지(receiver_id IS NULL)인 경우 MiniappRead 테이블에 현재 사원의 확인 서명을 기록하고 사원별 status를 반환합니다.
    """
    res = miniapp_crud.update_miniapp_item(
        db=db,
        item_id=item_id,
        user_id=current_user.id,
        item_update=item_update
    )
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="아이템을 찾을 수 없거나 수정 권한이 없습니다."
        )

    item, computed_status, confirmed_at = res

    sender_name = None
    if item.sender:
        sender_name = getattr(item.sender, "name", None) or getattr(item.sender, "username", None)

    extra_payload = dict(item.extra_payload or {})
    if confirmed_at and "confirmed_at" not in extra_payload:
        extra_payload["confirmed_at"] = confirmed_at.isoformat() if hasattr(confirmed_at, "isoformat") else str(confirmed_at)

    return miniapp_schema.MiniappItemResponse(
        id=item.id,
        sender_id=item.sender_id,
        sender_name=sender_name,
        receiver_id=item.receiver_id,
        category=item.category,
        title=item.title,
        content=item.content,
        status=computed_status,
        target_time=item.target_time,
        link=item.link,
        extra_payload=extra_payload,
        created_at=item.created_at,
        updated_at=item.updated_at
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_miniapp_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    [미니앱 아이템 삭제 (메모 삭제, 관리자 공지 강제 삭제)]
    """
    success = miniapp_crud.delete_miniapp_item(db=db, item_id=item_id, user=current_user)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="아이템을 찾을 수 없거나 삭제 권한이 없습니다."
        )
    return None
