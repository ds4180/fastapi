from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import BoardConfig, Post
from domain.v1.board import board_schema

router = APIRouter(
    prefix="/v1/board",
    tags=["CMS v1 Board"]
)

@router.get("/landing", response_model=board_schema.LandingPageResponse)
def get_landing_page_config(db: Session = Depends(get_db)):
    """
    CMS v1 대문(Landing Page) 정보를 조회합니다.
    - layout_type='landing'인 BoardConfig를 찾습니다.
    - 해당 보드에 속한 첫 번째 포스트를 대문 콘텐츠로 가져옵니다.
    """
    # 1. 대문용 보드 설정 조회
    landing_config = db.query(BoardConfig).filter(
        BoardConfig.layout_type == "landing",
        BoardConfig.is_active == True
    ).first()

    if not landing_config:
        # 설정이 없을 경우 기본 빈 값 반환 (프런트에서 기본값 처리)
        return {"config": None, "post": None, "message": "Landing config not found"}

    # 2. 대문용 포스트 조회 (최신순 1개)
    landing_post = db.query(Post).filter(
        Post.board_id == landing_config.id,
        Post.status == "published"
    ).order_by(Post.create_date.desc()).first()

    return {
        "config": landing_config,
        "post": landing_post,
        "message": "success"
    }
