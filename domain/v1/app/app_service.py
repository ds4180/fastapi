"""
============================================================================
[범용 앱 데이터 오케스트레이션 서비스 (domain/v1/app/app_service.py)]
============================================================================
💡 역할:
- AppRegistry 기반 앱 활성/권한 검문 및 앱 타입별(board, page 등) 데이터 조립을
  라우터로부터 분리하여 단일 서비스 계층에서 처리합니다.
"""

from typing import Optional, Any, Dict, Callable
from fastapi import Request
from sqlalchemy.orm import Session

from models import AppRegistry, BoardConfig, Post, Page
from domain.v1.admin.service_service import resolve_board_services
from domain.v1.board import board_crud
from core.permission import can_access_app, can_access_board, can_access_page
from core.exceptions import AccessDeniedError, ResourceNotFoundError
from core.view_counter import should_count_view


def _load_board_app_data(
    db: Session,
    request: Request,
    current_user: Optional[Any],
    parts: list[str],
    page: int,
    size: int,
    keyword: str,
    sort: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """게시판(board) 인스턴스 목록 또는 상세 데이터 및 서비스 바인딩 조립"""
    board_slug = parts[0]
    board = db.query(BoardConfig).filter(BoardConfig.slug == board_slug).first()
    if not board:
        return result

    if not can_access_board(current_user, board, action="read"):
        raise AccessDeniedError(
            f"해당 게시판('{board.name}')에 접근할 권한이 없습니다.",
            resource="board",
            resource_id=board.slug,
        )

    result["parent_config"] = board

    if len(parts) >= 2 and parts[1].isdigit():
        post_id = int(parts[1])
        post = (
            db.query(Post)
            .filter(Post.id == post_id, Post.board_id == board.id, Post.is_deleted == False)
            .first()
        )
        if post:
            if not board_crud.can_view_post(post, current_user, board):
                raise AccessDeniedError(
                    "이 게시물을 열람할 권한이 없거나 게시 기간이 아닙니다.",
                    resource="board",
                    resource_id=str(post_id),
                )
            if should_count_view("post", post.id, request, current_user):
                db.query(Post).filter(Post.id == post.id).update(
                    {Post.view_count: Post.view_count + 1}
                )
                db.commit()
                db.refresh(post)
            setattr(post, "user_name", board_crud.mask_post_author_name(post, current_user, board))
            result["instance"] = post
            result["bindings"] = resolve_board_services(db, board, user=current_user)
        return result

    category = request.query_params.get("category", "")
    total, posts = board_crud.get_post_list(
        db,
        board_id=board.id,
        skip=page * size,
        limit=size,
        user=current_user,
        keyword=keyword,
        sort=sort,
        category=category,
        use_pin=board_crud.is_board_pin_enabled(board.options),
    )
    result["instance"] = {"posts": posts, "total": total}
    result["bindings"] = resolve_board_services(db, board, user=current_user)
    return result


def _load_page_app_data(
    db: Session,
    request: Request,
    current_user: Optional[Any],
    parts: list[str],
    page: int,
    size: int,
    keyword: str,
    sort: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """페이지(page) 인스턴스 데이터 조립"""
    page_slug = parts[0]
    page_obj = db.query(Page).filter(Page.slug == page_slug).first()
    if page_obj:
        if not can_access_page(current_user, page_obj, action="read"):
            raise AccessDeniedError(
                f"해당 페이지('{page_obj.title}')에 접근할 권한이 없습니다.",
                resource="page",
                resource_id=page_obj.slug,
            )
        result["instance"] = page_obj
    return result


# 앱별 동적 데이터 로더 매핑 (하드코딩 분기 확장 대비)
_APP_DATA_LOADERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "board": _load_board_app_data,
    "page": _load_page_app_data,
}

# 개별 인스턴스 자체 권한으로 검증하는 앱 집합
_INSTANCE_SCOPED_APPS = frozenset({"board", "page"})


def load_app_data(
    db: Session,
    app_id: str,
    slug: str,
    request: Request,
    current_user: Optional[Any],
    page: int = 0,
    size: int = 10,
    keyword: str = "",
    sort: str = "latest",
) -> Dict[str, Any]:
    """범용 앱 데이터 조회 진입점 (레지스트리 검문 + 인스턴스 로더 위임)"""
    canonical_app_id = "board" if app_id in ("board", "boards") else app_id

    app_info = db.query(AppRegistry).filter(AppRegistry.app_id == canonical_app_id).first()
    if not app_info and canonical_app_id == "board":
        app_info = db.query(AppRegistry).filter(AppRegistry.app_id == "boards").first()
    if not app_info:
        raise ResourceNotFoundError(
            f"등록되지 않은 앱입니다: '{app_id}'",
            resource="app",
            resource_id=app_id,
        )

    if not app_info.is_active:
        raise AccessDeniedError(
            f"비활성화된 앱('{app_info.title or canonical_app_id}')입니다.",
            resource="app",
            resource_id=canonical_app_id,
        )

    if canonical_app_id not in _INSTANCE_SCOPED_APPS and not can_access_app(
        user=current_user,
        app_obj=app_info,
        action="read",
    ):
        raise AccessDeniedError(
            f"해당 앱('{app_info.title or canonical_app_id}')에 접근할 권한이 없습니다.",
            resource="app",
            resource_id=canonical_app_id,
        )

    result: Dict[str, Any] = {
        "app_info": app_info,
        "instance": None,
        "parent_config": None,
        "bindings": [],
    }

    loader = _APP_DATA_LOADERS.get(canonical_app_id)
    if loader:
        return loader(
            db=db,
            request=request,
            current_user=current_user,
            parts=slug.split("/"),
            page=page,
            size=size,
            keyword=keyword,
            sort=sort,
            result=result,
        )

    return result
