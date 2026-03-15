from sqlalchemy.orm import Session
from models import Page
from domain.page.page_schema import PageCreate, PageUpdate
from datetime import datetime

def get_page_list(db: Session):
    """전체 페이지 목록 조회 (삭제되지 않은 것만)"""
    return db.query(Page).filter(Page.is_deleted == False).order_by(Page.created_at.desc()).all()

def get_page_by_id(db: Session, page_id: int):
    """ID로 페이지 상세 조회"""
    return db.query(Page).filter(Page.id == page_id, Page.is_deleted == False).first()

def get_page_by_slug(db: Session, slug: str):
    """슬러그(주소)로 페이지 상세 조회 (사용자 화면용)"""
    return db.query(Page).filter(Page.slug == slug, Page.is_deleted == False).first()

def create_page(db: Session, page_in: PageCreate):
    """신규 페이지 생성"""
    db_page = Page(
        slug=page_in.slug,
        title=page_in.title,
        content=page_in.content,
        content_json=page_in.content_json,
        status=page_in.status,
        is_active=page_in.is_active,
        min_rank=page_in.min_rank,
        published_at=page_in.published_at,
        expired_at=page_in.expired_at,
        redirect_url=page_in.redirect_url
    )
    db.add(db_page)
    db.commit()
    db.refresh(db_page)
    return db_page

def update_page(db: Session, db_page: Page, page_in: PageUpdate):
    """기존 페이지 수정"""
    update_data = page_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_page, key, value)
    
    db_page.updated_at = datetime.now()
    db.commit()
    db.refresh(db_page)
    return db_page

def delete_page(db: Session, db_page: Page):
    """페이지 삭제 (Soft Delete 정책 반영)"""
    db_page.is_deleted = True
    db_page.delete_date = datetime.now()
    db.commit()

def increment_view_count(db: Session, db_page: Page):
    """조회수 증가"""
    db_page.view_count += 1
    db.commit()
    return db_page
