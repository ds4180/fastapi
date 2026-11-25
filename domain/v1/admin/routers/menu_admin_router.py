from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from core.audit import safe_log_audit
from core.deps import get_current_user_optional, require_app_permission
from core.permission import ROOT_RANK, evaluate_permission, get_user_rank
from database import get_db
from domain.system.app_service import migrate_boards_to_board
from domain.v1.admin import admin_schema
from models import AppRegistry, BoardConfig, Menu, Page, User

router = APIRouter()

API_VERSION_PREFIX = "/v1"

check_menu_admin_read = require_app_permission("menu", action="read")
check_menu_admin_write = require_app_permission("menu", action="write")
check_menu_admin = check_menu_admin_read  # 하위 호환 보존

# 📄 정적 PAGES 이관 및 구버전 URL 정규화 경로 매핑
MIGRATED_PAGES_MAP = {
    "/v1/custom/chart": "/v1/pages/chart",
    "/v1/custom/canvas": "/v1/pages/canvas",
    "/v1/custom/uploadfile": "/v1/pages/uploadfile",
    "/v1/app/boards": "/v1/app/board",
    "/v1/admin/boards": "/v1/admin/board",
}


def _build_menu_lookup_cache(db: Session) -> dict:
    """
    [메뉴 트리 N+1 쿼리 제거용 일괄 조회 캐시]
    메뉴 순회 중 반복 호출되는 AppRegistry, BoardConfig(slug), Page(slug)를
    요청당 1회씩만 일괄 로드하여 메모리 딕셔너리로 제공합니다.
    """
    apps_by_id = {a.app_id: a for a in db.query(AppRegistry).all() if a.app_id}
    board_slugs = {
        row[0]: row[1]
        for row in db.query(BoardConfig.id, BoardConfig.slug).all()
        if row[0] is not None
    }
    page_slugs = {
        row[0]: row[1]
        for row in db.query(Page.id, Page.slug).all()
        if row[0] is not None
    }
    return {
        "apps_by_id": apps_by_id,
        "board_slugs": board_slugs,
        "page_slugs": page_slugs,
    }


def resolve_menu_url(
    menu: Menu,
    db: Session,
    lookup_cache: Optional[dict] = None,
    resolved_slug: Optional[str] = None,
) -> str:
    """
    [v3.0 헌법 표준 단일 원칙 주소 조립기]
    """
    # 1. 🔗 수동 입력 URL 및 폴더/구분선
    if menu.link_type == "URL":
        raw_url = menu.external_url or "#"
        # 🩹 부모 접합 버그로 오염된 '#/' 접두사 자동 자가치유
        if raw_url.startswith("#/") and len(raw_url) > 2:
            raw_url = raw_url[1:]
            menu.external_url = raw_url
            db.commit()
        if raw_url in MIGRATED_PAGES_MAP:
            menu.external_url = MIGRATED_PAGES_MAP[raw_url]
            db.commit()
            return menu.external_url
        return raw_url

    if menu.link_type in ["FOLDER", "DIVIDER"]:
        return "#"

    # 2. ⚙️ 앱 엔진 기반 메뉴 경로 판별
    if menu.app_id:
        clean_id = menu.app_id
        instance_id = str(menu.app_instance_id) if menu.app_instance_id is not None else ""

        is_admin_mode = menu.link_type == "SYSTEM" or instance_id == "-1"

        if lookup_cache is not None and "apps_by_id" in lookup_cache:
            app_reg = lookup_cache["apps_by_id"].get(clean_id)
        else:
            app_reg = db.query(AppRegistry).filter(AppRegistry.app_id == clean_id).first()

        if is_admin_mode:
            if app_reg and app_reg.frontend_route:
                return (
                    "/v1/admin/board"
                    if app_reg.frontend_route == "/v1/admin/boards"
                    else app_reg.frontend_route
                )
            if clean_id in ["dashboard", ""]:
                return f"{API_VERSION_PREFIX}/admin"
            if clean_id in ("board", "boards"):
                return f"{API_VERSION_PREFIX}/admin/board"
            return f"{API_VERSION_PREFIX}/admin/{clean_id}"

        # 👤 [사용자 화면]: 각 앱의 타입에 맞는 전용 거처로 1:1 직행
        if menu.link_type == "CUSTOM":
            if clean_id == "page":
                slug = resolved_slug if resolved_slug is not None else get_instance_slug(menu, db, lookup_cache)
                if slug and slug != "-1":
                    return f"{API_VERSION_PREFIX}/custom/page/{slug}"
                return f"{API_VERSION_PREFIX}/custom/page"
            return f"{API_VERSION_PREFIX}/custom/{clean_id}"

        if menu.link_type in ["INSTANCE", "APP"]:
            slug = resolved_slug if resolved_slug is not None else get_instance_slug(menu, db, lookup_cache)
            app_prefix = "board" if clean_id in ("board", "boards") else clean_id
            if slug and slug != "-1":
                return f"{API_VERSION_PREFIX}/app/{app_prefix}/{slug}"
            return f"{API_VERSION_PREFIX}/app/{app_prefix}"

    # 3. 📄 DB 기반 페이지(Page) 직접 링크 (/v1/custom/page/{slug})
    if menu.link_type in ["PAGE", "PAGES"] and (menu.page_id or menu.app_id):
        slug = resolved_slug if resolved_slug is not None else get_instance_slug(menu, db, lookup_cache)
        if slug and slug != "-1":
            return f"{API_VERSION_PREFIX}/custom/page/{slug}"
        return f"{API_VERSION_PREFIX}/custom/page"

    return menu.external_url or "#"


def get_instance_slug(
    menu: Menu,
    db: Session,
    lookup_cache: Optional[dict] = None,
) -> Optional[str]:
    """
    [인스턴스 ID -> 슬러그(Slug) 변환 헬퍼 (PostgreSQL 타입 안전 가드)]
    """
    raw_val = menu.app_instance_id if menu.app_instance_id is not None else menu.page_id
    if raw_val is None:
        return None
    if raw_val == -1 or str(raw_val) == "-1":
        return "-1"

    clean_id = menu.app_id or ""

    int_id = None
    try:
        int_id = int(raw_val)
    except (ValueError, TypeError):
        int_id = None

    if clean_id in ["board", "boards"]:
        if int_id is not None:
            if lookup_cache is not None and "board_slugs" in lookup_cache:
                slug_val = lookup_cache["board_slugs"].get(int_id)
                return slug_val if slug_val else str(raw_val)
            board = db.query(BoardConfig).filter(BoardConfig.id == int_id).first()
            return board.slug if board else str(raw_val)
        return str(raw_val)

    if clean_id == "page" or menu.link_type in ["PAGE", "PAGES"]:
        if int_id is not None:
            if lookup_cache is not None and "page_slugs" in lookup_cache:
                slug_val = lookup_cache["page_slugs"].get(int_id)
                return slug_val if slug_val else str(raw_val)
            page_obj = db.query(Page).filter(Page.id == int_id).first()
            return page_obj.slug if page_obj else str(raw_val)
        return str(raw_val)

    return str(raw_val)


def filter_menu_tree(
    menus: List[Menu],
    current_user: Optional[User],
    db: Session,
    bypass_auth: bool = False,
    lookup_cache: Optional[dict] = None,
):
    """[4단계 권한 기반 재귀적 메뉴 필터링 및 동적 URL 주입]"""
    if lookup_cache is None:
        lookup_cache = _build_menu_lookup_cache(db)

    filtered = []
    sorted_menus = sorted(menus, key=lambda x: x.order)
    user_rank = get_user_rank(current_user) if not bypass_auth else ROOT_RANK

    for m in sorted_menus:
        is_allowed = True if bypass_auth else (
            bool(m.is_visible)
            and evaluate_permission(
                user=current_user,
                action="read",
                min_read_rank=m.min_rank if m.min_rank is not None else 0,
                allow_groups=m.allow_groups or [],
                deny_groups=m.deny_groups or [],
            )
        )

        # 🚨 [앱 킬 스위치 연동]: 연결된 앱이 비활성화(is_active=False)된 경우 일반 사용자 메뉴 자동 숨김
        if is_allowed and not bypass_auth and m.app_id and user_rank != ROOT_RANK:
            app_reg = lookup_cache["apps_by_id"].get(m.app_id)
            if app_reg is not None and app_reg.is_active is False:
                is_allowed = False
        if is_allowed:
            resolved_slug = None if bypass_auth else get_instance_slug(m, db, lookup_cache)
            final_url = resolve_menu_url(m, db, lookup_cache=lookup_cache, resolved_slug=resolved_slug)
            normalized_link_type = "INSTANCE" if m.link_type == "APP" else m.link_type

            menu_data = {
                "id": m.id,
                "title": m.title,
                "parent_id": m.parent_id,
                "icon_name": m.icon_name,
                "icon_color": m.icon_color,
                "link_type": normalized_link_type,
                "external_url": final_url,
                "order": m.order,
                "is_visible": m.is_visible,
                "min_rank": m.min_rank,
                "allow_groups": m.allow_groups or [],
                "deny_groups": m.deny_groups or [],
                "app_id": m.app_id,
                "app_instance_id": m.app_instance_id if bypass_auth else (resolved_slug or m.app_instance_id),
                "sub_menus": filter_menu_tree(
                    m.sub_menus, current_user, db, bypass_auth=bypass_auth, lookup_cache=lookup_cache
                ),
            }
            filtered.append(menu_data)
    return filtered


@router.get("/menu/public", response_model=List[admin_schema.MenuSchema])
def get_public_menus(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """일반 사용자용 공개 메뉴 조회 (4단계 그룹/랭킹 권한 필터링 및 지능형 URL 생성 포함)"""
    migrate_boards_to_board(db)
    root_menus = (
        db.query(Menu)
        .options(joinedload(Menu.sub_menus).joinedload(Menu.sub_menus))
        .filter(Menu.parent_id == None, Menu.is_visible == True)
        .order_by(Menu.order)
        .all()
    )
    lookup_cache = _build_menu_lookup_cache(db)
    return filter_menu_tree(root_menus, current_user, db, bypass_auth=False, lookup_cache=lookup_cache)


@router.get("/menu", response_model=List[admin_schema.MenuSchema])
def get_all_menus(db: Session = Depends(get_db), admin: User = Depends(check_menu_admin_read)):
    """관리자용 전체 메뉴 트리 (menu 거버넌스 연동)"""
    migrate_boards_to_board(db)
    legacy_menus = db.query(Menu).filter(Menu.link_type == "APP").all()
    if legacy_menus:
        for lm in legacy_menus:
            lm.link_type = "INSTANCE"
        db.commit()

    broken_menus = (
        db.query(Menu)
        .filter((Menu.link_type == "SYSTEM") | (Menu.external_url.like("%/admin/admin_%")))
        .all()
    )
    if broken_menus:
        for bm in broken_menus:
            bm.external_url = resolve_menu_url(bm, db)
        db.commit()

    root_menus = (
        db.query(Menu)
        .options(joinedload(Menu.sub_menus))
        .filter(Menu.parent_id == None)
        .order_by(Menu.order)
        .all()
    )
    return filter_menu_tree(root_menus, admin, db, bypass_auth=True)


@router.post("/menu", response_model=admin_schema.MenuSchema)
def create_menu(
    menu_in: admin_schema.MenuCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_menu_admin_write),
):
    data = menu_in.dict()
    if data.get("link_type") == "APP":
        data["link_type"] = "INSTANCE"
    elif data.get("link_type") == "SYSTEM":
        data["app_instance_id"] = -1

    original_instance_id = data.get("app_instance_id")

    if original_instance_id and isinstance(original_instance_id, str):
        if data.get("app_id") in ["page", "pages"]:
            page_obj = db.query(Page).filter(Page.slug == original_instance_id).first()
            if page_obj:
                data["app_instance_id"] = page_obj.id
        else:
            board = db.query(BoardConfig).filter(BoardConfig.slug == original_instance_id).first()
            if board:
                data["app_instance_id"] = board.id

    db_menu = Menu(**data)
    db.add(db_menu)
    db.commit()
    db.refresh(db_menu)

    if db_menu.link_type in ["INSTANCE", "CUSTOM", "SYSTEM", "APP", "PAGES", "PAGE"]:
        db_menu.external_url = resolve_menu_url(db_menu, db)
        db.commit()
        db.refresh(db_menu)

    safe_log_audit(
        db=db,
        app_id="menu",
        log_type="SYSTEM",
        action="MENU_CREATED",
        title=f"메뉴 항목 생성: {db_menu.title} (ID: {db_menu.id})",
        user=admin,
        resource_type="menu",
        resource_id=str(db_menu.id),
        message=f"타입: {db_menu.link_type}, URL: {db_menu.external_url}, 권한: R{db_menu.min_rank}",
        metadata={
            "menu_id": db_menu.id,
            "title": db_menu.title,
            "parent_id": db_menu.parent_id,
            "link_type": db_menu.link_type,
            "external_url": db_menu.external_url,
            "app_id": db_menu.app_id,
            "min_rank": db_menu.min_rank,
            "allow_groups": db_menu.allow_groups,
            "deny_groups": db_menu.deny_groups,
        },
    )

    result = admin_schema.MenuSchema.model_validate(db_menu)
    if isinstance(original_instance_id, str):
        result.app_instance_id = original_instance_id

    return result


@router.put("/menu/{menu_id}", response_model=admin_schema.MenuSchema)
def update_menu(
    menu_id: int,
    menu_in: admin_schema.MenuUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(check_menu_admin_write),
):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu:
        raise HTTPException(status_code=404)

    data = menu_in.dict(exclude_unset=True)
    if data.get("link_type") == "APP":
        data["link_type"] = "INSTANCE"
    elif data.get("link_type") == "SYSTEM":
        data["app_instance_id"] = -1

    original_instance_id = data.get("app_instance_id")

    if original_instance_id and isinstance(original_instance_id, str):
        if data.get("app_id") in ["page", "pages"]:
            page_obj = db.query(Page).filter(Page.slug == original_instance_id).first()
            if page_obj:
                data["app_instance_id"] = page_obj.id
        else:
            board = db.query(BoardConfig).filter(BoardConfig.slug == original_instance_id).first()
            if board:
                data["app_instance_id"] = board.id

    diff_list = []
    for key, value in data.items():
        old_val = getattr(db_menu, key, None)
        if old_val != value:
            diff_list.append(
                {
                    "field": key,
                    "old": old_val,
                    "new": value,
                }
            )
        setattr(db_menu, key, value)

    db.commit()
    db.refresh(db_menu)

    if db_menu.link_type in ["INSTANCE", "CUSTOM", "SYSTEM", "APP", "PAGES", "PAGE"]:
        db_menu.external_url = resolve_menu_url(db_menu, db)
        db.commit()
        db.refresh(db_menu)

    if diff_list:
        is_security_change = any(
            f["field"] in ["min_rank", "allow_groups", "deny_groups", "is_visible"] for f in diff_list
        )
        safe_log_audit(
            db=db,
            app_id="menu",
            log_type="SECURITY" if is_security_change else "SYSTEM",
            action="MENU_UPDATED",
            title=f"메뉴 항목 수정: {db_menu.title} (ID: {db_menu.id})",
            user=admin,
            resource_type="menu",
            resource_id=str(db_menu.id),
            message=f"{len(diff_list)}개 항목 변경 완료: " + ", ".join([d["field"] for d in diff_list]),
            diff_payload=diff_list,
            metadata={"menu_id": db_menu.id, "updated_fields": list(data.keys())},
        )

    result = admin_schema.MenuSchema.model_validate(db_menu)
    if isinstance(original_instance_id, str):
        result.app_instance_id = original_instance_id

    return result


@router.delete("/menu/{menu_id}")
def delete_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(check_menu_admin_write),
):
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu:
        raise HTTPException(status_code=404)

    menu_id_val = db_menu.id
    menu_title = db_menu.title
    menu_url = db_menu.external_url

    db.delete(db_menu)
    db.commit()

    safe_log_audit(
        db=db,
        app_id="menu",
        log_type="SECURITY",
        action="MENU_DELETED",
        title=f"메뉴 항목 삭제 완료: {menu_title} (ID: {menu_id_val})",
        user=admin,
        severity="WARN",
        resource_type="menu",
        resource_id=str(menu_id_val),
        message=f"메뉴 '{menu_title}' (URL: {menu_url}) 항목이 시스템에서 영구 삭제되었습니다.",
        metadata={"menu_id": menu_id_val, "title": menu_title, "url": menu_url},
    )

    return {"message": "success"}
