from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from domain.page import page_schema, page_crud
from domain.user.user_router import get_current_user, check_rank
from models import User
from typing import List
from datetime import datetime

router = APIRouter(
    prefix="/v1/page",
    tags=["page"]
)

# 관리자 권한 체크 (Rank 4 이상)
check_admin = check_rank(required_rank=4)

# --- [관리자용 API] ---

@router.get("/admin/list", response_model=List[page_schema.PageSimpleResponse])
def admin_list_pages(
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin)
):
    """관리자용 전체 페이지 목록"""
    return page_crud.get_page_list(db)

@router.post("/admin/create", response_model=page_schema.PageResponse)
def admin_create_page(
    page_in: page_schema.PageCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin)
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
    current_admin: User = Depends(check_admin)
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
    current_admin: User = Depends(check_admin)
):
    """페이지 삭제"""
    db_page = page_crud.get_page_by_id(db, page_id)
    if not db_page:
        raise HTTPException(status_code=404, detail="페이지를 찾을 수 없습니다.")
    page_crud.delete_page(db, db_page)
    return {"message": "success"}

# --- [사용자용 API] ---

@router.get("/detail/{slug}", response_model=page_schema.PageResponse)
def get_page_detail(
    slug: str,
    db: Session = Depends(get_db)
):
    """사용자용 페이지 상세 조회 (게시일시, 활성화, 권한 체크 포함)"""
    db_page = page_crud.get_page_by_slug(db, slug)
    if not db_page:
        raise HTTPException(status_code=404, detail="존재하지 않는 페이지입니다.")
    
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
