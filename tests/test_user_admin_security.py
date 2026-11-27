"""
관리자 계정 권한 변경/복구 엣지케이스 보안 테스트 (tests/test_user_admin_security.py)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from domain.v1.admin import admin_schema
from domain.v1.admin.routers import user_admin_router


def _make_user(uid: int, rank: int, is_active: bool = True, username: str = "u"):
    profile = SimpleNamespace(rank_level=rank, is_active=is_active)
    return SimpleNamespace(id=uid, username=username, profile=profile, rank=lambda: rank)


def test_update_user_rank_blocks_demoting_equal_or_higher_rank():
    """Lv.4 관리자가 동급(Lv.4) 또는 상위(Lv.5) 관리자를 강등하려 하면 403 차단되는지 검증"""
    admin_lv4 = _make_user(10, rank=4, username="mgr4")
    target_lv5 = _make_user(20, rank=5, username="dir5")

    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.first.return_value = target_lv5

    with pytest.raises(HTTPException) as exc:
        user_admin_router.update_user_rank(
            user_id=20,
            rank_in=admin_schema.UserRankUpdate(rank_level=1),
            db=db,
            admin=admin_lv4,
        )
    assert exc.value.status_code == 403


def test_restore_user_blocks_active_account_and_root_downgrade():
    """활성 상태 계정 또는 상위/Root 계정에 /restore 호출 시 강등 없이 400/403 차단되는지 검증"""
    admin_lv4 = _make_user(10, rank=4, username="mgr4")
    root_user = _make_user(1, rank=9, is_active=True, username="root")
    active_lv1 = _make_user(30, rank=1, is_active=True, username="staff1")

    db = MagicMock()

    # 1. Lv.4가 Root 계정에 /restore 호출 -> 403
    db.query.return_value.options.return_value.filter.return_value.first.return_value = root_user
    with pytest.raises(HTTPException) as exc_root:
        user_admin_router.restore_user_by_admin(user_id=1, db=db, admin=admin_lv4)
    assert exc_root.value.status_code == 403
    assert root_user.profile.rank_level == 9

    # 2. 이미 활성(is_active=True)인 일반 계정에 /restore 호출 -> 400
    db.query.return_value.options.return_value.filter.return_value.first.return_value = active_lv1
    with pytest.raises(HTTPException) as exc_active:
        user_admin_router.restore_user_by_admin(user_id=30, db=db, admin=admin_lv4)
    assert exc_active.value.status_code == 400
