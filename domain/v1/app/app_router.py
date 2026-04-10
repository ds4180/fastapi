from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import AppRegistry, ServiceInstance, BoardConfig, Post, Page
from domain.v1.admin.service_service import resolve_service_instance
from domain.user.user_router import get_current_user_optional
from typing import Optional, Any, Dict

router = APIRouter(prefix="/v1/app", tags=["App Engine"])

@router.get("/data/{app_id}/{slug:path}")
def get_app_data(
    app_id: str,
    slug: str,
    page: int = 0,
    size: int = 10,
    keyword: str = "",
    db: Session = Depends(get_db),
    current_user: Optional[Any] = Depends(get_current_user_optional)
):
    """
    [Data-Driven] 범용 앱 데이터 제공 API
    AppRegistry의 설정에 따라 동적으로 모델을 탐색하고 서비스 바인딩을 조립합니다.
    """
    # 1. 앱 레지스트리 정보 확인
    app_info = db.query(AppRegistry).filter(AppRegistry.app_id == app_id).first()
    if not app_info:
        raise HTTPException(status_code=404, detail="App not registered")

    # 2. 경로 분석 (slug: board_slug/id or just id)
    parts = slug.split('/')
    
    # 3. 데이터 조립용 결과 객체
    result = {
        "app_info": app_info,
        "instance": None,
        "parent_config": None,
        "bindings": []
    }

    # 4. 하드코딩 Zero 기반 동적 로딩 로직 (현재는 Board/Page에 대해 시범 적용)
    # TODO: 향후 config_schema의 instance_info 메타데이터를 100% 활용하도록 고도화
    
    try:
        if app_id == "board" or app_id == "boards":
            # 1. 경로 분석 (slug: board_slug/id or just board_slug)
            board_slug = parts[0]
            board = db.query(BoardConfig).filter(BoardConfig.slug == board_slug).first()
            if not board:
                return result # 인스턴스 없음 반환

            result["parent_config"] = board
            
            # 2. 목록 vs 상세 분기
            if len(parts) >= 2 and parts[1].isdigit():
                # 상세 조회 모드
                post_id = int(parts[1])
                post = db.query(Post).filter(Post.id == post_id, Post.board_id == board.id).first()
                if post:
                    result["instance"] = post
                    # 서비스 바인딩 해결
                    if board.service_instance_id:
                        result["bindings"] = resolve_service_instance(db, board.service_instance_id)
            else:
                # 목록 조회 모드 (전달받은 앱 쿼리 파라미터 적용)
                from domain.v1.board import board_crud
                total, posts = board_crud.get_post_list(db, board_id=board.id, skip=page*size, limit=size, keyword=keyword)
                result["instance"] = {"posts": posts, "total": total}
                # 목록에서도 바인딩이 필요하다면 추가 (필요시)
                if board.service_instance_id:
                    result["bindings"] = resolve_service_instance(db, board.service_instance_id)

        elif app_id == "page" or app_id == "pages":
            # 페이지 로직: slug = "about-us"
            page_slug = parts[0]
            page = db.query(Page).filter(Page.slug == page_slug).first()
            if page:
                result["instance"] = page
                # 페이지는 아직 서비스 바인딩 필드가 없으므로 bindings=[]

    except Exception as e:
        print(f"❌ [AppRouter] Dynamic Loading Error: {e}")
        raise HTTPException(status_code=500, detail="Internal data resolution error")

    return result
