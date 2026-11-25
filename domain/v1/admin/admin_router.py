"""
[관리자 통합 라우터 애그리게이터 (domain/v1/admin/admin_router.py)]
- 기존 단일 비대 파일(2,536줄)을 플랫폼 코어 서브 라우터(6개)와
  독립 비즈니스 도메인 관리자 라우터(5개)로 분리하고,
  외부 진입점(/v1/admin/*) 및 하위 호환 심볼을 100% 보존하는 얇은 조합 레이어입니다.
"""

from fastapi import APIRouter

from domain.dayoff import dayoff_admin_router
from domain.push import push_admin_router
from domain.v1.admin.routers import (
    app_registry_router,
    config_admin_router,
    dashboard_router,
    menu_admin_router,
    service_admin_router,
    user_admin_router,
)
from domain.v1.board import board_admin_router
from domain.v1.dispatch import dispatch_daily_router
from domain.v1.dispatch.dispatch_builder import (
    DEFAULT_VEHICLES_METADATA,
    build_daily_dispatch_rows,
    build_dispatch_work_rates,
    load_drivers_metadata,
    load_vehicles_metadata,
    query_active_routes_for_date,
)
from domain.v1.route_master import route_master_router

# 하위 호환 심볼 재노출 (단위 테스트 및 레거시 참조 보호)
from domain.v1.admin.routers.app_registry_router import check_app_admin
from domain.v1.admin.routers.config_admin_router import (
    check_config_admin,
    check_config_admin_read,
    check_config_admin_write,
)
from domain.v1.admin.routers.dashboard_router import check_admin, get_dashboard_summary
from domain.v1.admin.routers.menu_admin_router import (
    API_VERSION_PREFIX,
    MIGRATED_PAGES_MAP,
    check_menu_admin,
    check_menu_admin_read,
    check_menu_admin_write,
    filter_menu_tree,
    get_instance_slug,
    resolve_menu_url,
)
from domain.v1.admin.routers.service_admin_router import (
    check_service_admin,
    check_service_admin_write,
)
from domain.v1.admin.routers.user_admin_router import (
    check_user_admin,
    check_user_admin_read,
    check_user_admin_write,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin_v1"],
)

# 1. 플랫폼 코어 관리자 라우터
router.include_router(dashboard_router.router)
router.include_router(user_admin_router.router)
router.include_router(app_registry_router.router)
router.include_router(menu_admin_router.router)
router.include_router(config_admin_router.router)
router.include_router(service_admin_router.router)

# 2. 독립 비즈니스 도메인 관리자 라우터
router.include_router(board_admin_router.router)
router.include_router(push_admin_router.router)
router.include_router(dayoff_admin_router.router)
router.include_router(route_master_router.router)
router.include_router(dispatch_daily_router.router)
