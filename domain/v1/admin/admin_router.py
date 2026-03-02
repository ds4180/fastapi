from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import User, UserProfile, BoardConfig, Post, Menu
from domain.user.user_router import get_current_user

router = APIRouter(
    prefix="/v1/admin",
    tags=["admin_v1"]
)

def check_admin(current_user: User = Depends(get_current_user)):
    """최고 관리자(Rank 3)인지 체크하는 공통 의존성"""
    if current_user.rank < 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="최고 관리자 권한이 필요합니다."
        )
    return current_user

@router.get("/dashboard")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(check_admin)
):
    """관리자 대시보드 요약 정보"""
    user_count = db.query(User).count()
    board_count = db.query(BoardConfig).count()
    post_count = db.query(Post).count()
    
    return {
        "user_count": user_count,
        "board_count": board_count,
        "post_count": post_count,
        "admin_name": admin.real_name or admin.username
    }
