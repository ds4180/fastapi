from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from models import Post, BoardConfig, User, PostRead, Comment, PostReaction
from typing import List, Optional

def get_post_list(db: Session, board_id: int, skip: int = 0, limit: int = 10, user: User = None, keyword: str = ""):
    # 1. 기본 쿼리: 특정 게시판의 삭제되지 않은 글들
    query = db.query(Post).filter(
        Post.board_id == board_id,
        Post.is_deleted == False
    )

    # 2. 키워드 검색 (제목, 내용, 작성자 이름)
    if keyword:
        search = f"%%{keyword}%%"
        query = query.outerjoin(User).filter(
            or_(
                Post.title.ilike(search),
                Post.content.ilike(search),
                User.username.ilike(search),
                User.real_name.ilike(search)
            )
        ).distinct()

    # 3. 전체 개수 카운트
    total = query.count()

    # 4. 페이징 및 정렬
    posts = query.order_by(Post.create_date.desc()).offset(skip).limit(limit).all()

    # 5. M2M 정보 보정 (읽음 여부, 좋아요 수, 댓글 수 등)
    result_posts = []
    for post in posts:
        # Pydantic 모델로 변환하기 위한 데이터 구성
        post_data = {
            "id": post.id,
            "title": post.title,
            "content_json": post.content_json,
            "extra_data": post.extra_data,
            "status": post.status,
            "view_count": post.view_count,
            "create_date": post.create_date,
            "user_name": post.user.real_name or post.user.username if post.user else "탈퇴한 사용자",
            "is_read": False,
            "like_count": 0, # PostReaction 모델 추가 시 반영
            "comment_count": len(post.comments)
        }
        
        # 로그인 사용자의 경우 읽음 상태 체크
        if user:
            is_read = db.query(PostRead).filter(
                PostRead.post_id == post.id,
                PostRead.user_id == user.id
            ).first()
            post_data["is_read"] = True if is_read else False

        result_posts.append(post_data)

    return total, result_posts
