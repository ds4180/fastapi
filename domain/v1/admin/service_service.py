from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import ServiceInstance, ServiceApp, ServiceEngine, ServiceRegistry
from core.permission import evaluate_service_permission
from typing import List, Dict, Any, Optional

VALID_DISPLAYS = {"block", "inline", "grid-2"}
VALID_ALIGNS = {"start", "between", "end"}


def _normalize_service_entry(entry: Any, fallback_row: int) -> tuple[int | None, Dict[str, Any]]:
    """
    service_app_ids 배열의 개별 항목을 정규화합니다.
    - 레거시 정수(int): 단독 block 행으로 자동 변환 (100% 하위 호환)
    - 확장 객체(dict): { app_id, row, display('block'|'inline'|'grid-2'), wrap(bool), align('start'|'between'|'end') }
    """
    if isinstance(entry, int):
        return entry, {
            "row": fallback_row,
            "display": "block",
            "wrap": True,
            "align": "start",
        }
    if isinstance(entry, dict):
        raw_id = entry.get("app_id")
        try:
            app_id = int(raw_id) if raw_id is not None else None
        except (ValueError, TypeError):
            app_id = None
        display = str(entry.get("display") or "block").lower()
        if display not in VALID_DISPLAYS:
            display = "block"
        align = str(entry.get("align") or "start").lower()
        if align not in VALID_ALIGNS:
            align = "start"
        try:
            row_idx = int(entry.get("row")) if entry.get("row") is not None else fallback_row
        except (ValueError, TypeError):
            row_idx = fallback_row
        wrap = bool(entry.get("wrap", True))
        return app_id, {
            "row": row_idx,
            "display": display,
            "wrap": wrap,
            "align": align,
        }
    return None, {
        "row": fallback_row,
        "display": "block",
        "wrap": True,
        "align": "start",
    }


def resolve_service_apps(
    db: Session,
    service_app_ids: List[Any],
    user: Any = None,
    host_obj: Any = None,
) -> List[Dict[str, Any]]:
    """
    [App-Driven] 서비스 앱 ID(또는 레이아웃 확장 객체) 리스트를 순서대로 해석하여
    프론트엔드용 명세(ResolvedServiceBinding) 리스트로 반환합니다.
    (user/host_obj 전달 시 각 서비스앱의 읽기/쓰기 권한을 함께 계산)
    """
    if not service_app_ids:
        return []

    resolved_list = []
    for idx, raw_entry in enumerate(service_app_ids):
        app_id, layout = _normalize_service_entry(raw_entry, fallback_row=idx)
        if app_id is None:
            continue

        app = db.query(ServiceApp).filter(ServiceApp.id == app_id).first()
        if not app or not app.is_active:
            continue

        engine = db.query(ServiceEngine).filter(ServiceEngine.id == app.engine_id).first()
        if not engine:
            continue

        resolved_list.append({
            "app_id": app.id,
            "service_id": engine.registry_id,
            "engine_id": engine.id,
            "service_component": engine.frontend_plugin,
            "config": app.config,
            "layout": layout,
            "permissions": evaluate_service_permission(
                user=user,
                host_obj=host_obj,
                service_config=app.config,
                service_id=engine.registry_id,
                app_id=app.id,
            ),
        })

    return resolved_list


def resolve_service_instance(
    db: Session,
    instance_id: int,
    user: Any = None,
    host_obj: Any = None,
) -> List[Dict[str, Any]]:
    """
    [Bundle-Driven] 서비스 인스턴스(꾸러미)에 담긴 앱들을 순서대로 해석하여
    프론트엔드용 명세(ResolvedServiceBinding) 리스트로 반환합니다.
    """
    instance = db.query(ServiceInstance).filter(ServiceInstance.id == instance_id).first()
    if not instance or not instance.service_app_ids:
        return []
    return resolve_service_apps(db, instance.service_app_ids, user=user, host_obj=host_obj)


def resolve_board_services(db: Session, board: Any, user: Any = None) -> List[Dict[str, Any]]:
    """
    [Board-Driven] 게시판에 직접 지정된 service_app_ids가 있으면 우선 적용하고,
    없으면 연결된 공통 번들(service_instance_id)을 해석합니다.
    """
    direct_ids = getattr(board, "service_app_ids", None) or []
    if direct_ids:
        return resolve_service_apps(db, direct_ids, user=user, host_obj=board)
    instance_id = getattr(board, "service_instance_id", None)
    if instance_id:
        return resolve_service_instance(db, instance_id, user=user, host_obj=board)
    return []


def enforce_post_service_permission(
    db: Session,
    post: Any,
    user: Any,
    service_id: str,
    action: str = "write",
) -> Dict[str, Any]:
    """
    [서비스 API 공용 권한 가드]
    게시글에 연결된 호스트(BoardConfig)와 해당 서비스앱 바인딩(ServiceApp.config.permissions)을
    기준으로 API 요청 권한을 검증합니다. (프론트 UI와 100% 동일한 SSOT 판별)
    """
    board = getattr(post, "board", None)
    bindings = resolve_board_services(db, board, user=user) if board else []
    matched = [b for b in bindings if b.get("service_id") == service_id]

    if matched:
        perms = [b.get("permissions") or {} for b in matched]
    else:
        perms = [evaluate_service_permission(user=user, host_obj=board, service_config=None, service_id=service_id)]

    key = "can_write" if action == "write" else "can_read"
    allowed_perm = next((p for p in perms if p.get(key)), None)
    if allowed_perm is not None:
        return allowed_perm

    denied = perms[0]
    status_code = 401 if user is None else 403
    detail = denied.get("message") or ("로그인이 필요합니다." if user is None else "사용 권한이 없습니다.")
    raise HTTPException(status_code=status_code, detail=detail)
