from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.deps import require_any_app_permission
from core.exceptions import AccessDeniedError
from database import Base
from models import AppRegistry


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add_all([
            AppRegistry(app_id="apps", name="앱 관리", min_read_rank=9, min_write_rank=9, is_active=True),
            AppRegistry(app_id="menu", name="메뉴 관리", min_read_rank=4, min_write_rank=4, is_active=True),
            AppRegistry(app_id="services", name="서비스 관리", min_read_rank=9, min_write_rank=9, is_active=True),
            AppRegistry(app_id="board", name="게시판 관리", min_read_rank=4, min_write_rank=4, is_active=True),
            AppRegistry(app_id="target_groups", name="타겟 그룹", min_read_rank=4, min_write_rank=4, is_active=True),
            AppRegistry(app_id="survey", name="설문", min_read_rank=4, min_write_rank=4, is_active=True),
            AppRegistry(app_id="alerts", name="알림", min_read_rank=3, min_write_rank=3, is_active=True),
        ])
        db.commit()
        yield db
    finally:
        db.close()
        engine.dispose()


def _make_user(rank_level: int, uid: int = 10):
    return SimpleNamespace(
        id=uid,
        username=f"u{rank_level}",
        rank_level=rank_level,
        rank=lambda: rank_level,
        profile=SimpleNamespace(rank_level=rank_level, primary_group=None, secondary_groups=[]),
    )


def test_cross_app_read_allows_caller_app_manager(db_session):
    guard_apps_menu = require_any_app_permission(["apps", "menu"], action="read")
    guard_services_board = require_any_app_permission(["services", "board"], action="read")
    guard_candidates = require_any_app_permission(["target_groups", "survey"], action="read")
    guard_groups_alerts = require_any_app_permission(["target_groups", "alerts", "survey"], action="read")

    lv4 = _make_user(4, uid=40)
    lv3 = _make_user(3, uid=30)
    lv2 = _make_user(2, uid=20)

    # Lv.4는 menu/board/survey 읽기 권한으로 연관 조회 통과
    assert guard_apps_menu(current_user=lv4, db=db_session).id == 40
    assert guard_services_board(current_user=lv4, db=db_session).id == 40
    assert guard_candidates(current_user=lv4, db=db_session).id == 40

    # Lv.3는 alerts 읽기 권한으로 groups 목록 조회 통과
    assert guard_groups_alerts(current_user=lv3, db=db_session).id == 30

    # Lv.2는 어느 앱에도 권한이 없으므로 403 차단
    with pytest.raises(AccessDeniedError):
        guard_apps_menu(current_user=lv2, db=db_session)
    with pytest.raises(AccessDeniedError):
        guard_services_board(current_user=lv2, db=db_session)
    with pytest.raises(AccessDeniedError):
        guard_candidates(current_user=lv2, db=db_session)
    with pytest.raises(AccessDeniedError):
        guard_groups_alerts(current_user=lv2, db=db_session)


def test_cross_app_read_blocks_when_caller_app_inactive(db_session):
    menu_app = db_session.query(AppRegistry).filter(AppRegistry.app_id == "menu").first()
    menu_app.is_active = False
    db_session.commit()

    guard_apps_menu = require_any_app_permission(["apps", "menu"], action="read")
    lv4 = _make_user(4, uid=41)

    with pytest.raises(AccessDeniedError):
        guard_apps_menu(current_user=lv4, db=db_session)
