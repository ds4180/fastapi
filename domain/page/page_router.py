from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from domain.page import page_schema, page_crud
from domain.user.user_router import get_current_user, get_current_user_optional, check_rank
from core.deps import require_app_permission
from core.permission import can_access_page
from models import User
from typing import List, Optional
from datetime import datetime

router = APIRouter(
    prefix="/v1/page",
    tags=["page"]
)

# 🏛️ AppRegistry 거버넌스 연동 실시간 권한 가드 (CUSTOM 'page' 앱)
check_page_admin = require_app_permission("page", action="read")
check_page_admin_write = require_app_permission("page", action="write")

# --- [관리자용 API] ---

@router.get("/admin/list", response_model=List[page_schema.PageSimpleResponse])
def admin_list_pages(
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_page_admin)
):
    """관리자용 전체 페이지 목록"""
    return page_crud.get_page_list(db)

@router.post("/admin/create", response_model=page_schema.PageResponse)
def admin_create_page(
    page_in: page_schema.PageCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_page_admin_write)
):
    """신규 페이지 생성 (슬러그 중복 체크 포함)"""
    existing = page_crud.get_page_by_slug(db, page_in.slug)
    if existing:
        raise HTTPException(status_code=400, detail="이미 존재하는 슬러그입니다.")
    return page_crud.create_page(db, page_in)

@router.put("/admin/update", response_model=page_schema.PageResponse)
def admin_update_page(
    page_in: page_schema.PageUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_page_admin_write)
):
    """기존 페이지 수정"""
    db_page = page_crud.get_page_by_id(db, page_in.id)
    if not db_page:
        raise HTTPException(status_code=404, detail="페이지를 찾을 수 없습니다.")
    
    # 슬러그 변경 시 중복 체크
    if db_page.slug != page_in.slug:
        existing = page_crud.get_page_by_slug(db, page_in.slug)
        if existing:
            raise HTTPException(status_code=400, detail="이미 사용 중인 슬러그입니다.")
            
    return page_crud.update_page(db, db_page, page_in)

@router.delete("/admin/delete/{page_id}")
def admin_delete_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_page_admin_write)
):
    """페이지 삭제"""
    db_page = page_crud.get_page_by_id(db, page_id)
    if not db_page:
        raise HTTPException(status_code=404, detail="페이지를 찾을 수 없습니다.")
    page_crud.delete_page(db, db_page)
    return {"message": "success"}

# --- [사용자용 API] ---

@router.get("/public/list", response_model=List[page_schema.PageSimpleResponse])
def get_public_pages(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """사용자용 공개 페이지 목록 조회 (발행 상태 및 4단계 권한 필터링 적용)"""
    all_published = page_crud.get_public_page_list(db)
    # 로그인 유저 랭크 및 권한 기반 필터링
    allowed = [p for p in all_published if can_access_page(current_user, p, action="read")]
    return allowed

@router.get("/detail/{slug}", response_model=page_schema.PageResponse)
def get_page_detail(
    slug: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """사용자용 페이지 상세 조회 (게시일시, 활성화, 4단계 권한 체크 포함)"""
    db_page = page_crud.get_page_by_slug(db, slug)
    if not db_page:
        raise HTTPException(status_code=404, detail="존재하지 않는 페이지입니다.")
    
    # 🛡️ [정책재정의.md 4단계 권한 입구 검문: 1.root ➔ 2.deny ➔ 3.allow ➔ 4.min_rank]
    if not can_access_page(current_user, db_page, action="read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"'{db_page.title}' 페이지 열람 권한이 없습니다."
        )
    
    # 🚨 [보안 보강] 시스템 활성화 여부 체크
    if not db_page.is_active:
        if db_page.redirect_url:
            raise HTTPException(status_code=307, detail={"redirect": db_page.redirect_url})
        raise HTTPException(status_code=403, detail="현재 비활성화된 페이지입니다.")

    # 공개 상태 체크
    if db_page.status != "PUBLISHED":
        raise HTTPException(status_code=403, detail="아직 공개되지 않은 페이지입니다.")
    
    # 게시 일시 체크
    if db_page.published_at > datetime.now():
        raise HTTPException(status_code=403, detail="공개 예정인 페이지입니다.")
        
    # 조회수 증가
    page_crud.increment_view_count(db, db_page)
    
    return db_page
