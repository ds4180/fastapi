"""
미디어 보안·경로 정규화·서빙 헤더·라우터 스레드풀 검증 테스트 (tests/test_media_security.py)
"""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from domain.fileupload import fileupload_router
from domain.media import media_router, media_service
from domain.media.media_policy_service import is_own_private_path, is_shared_office_path
from domain.user.user_router import get_current_user


def test_uploadfiles_requires_authentication():
    """레거시 /uploadfiles 엔드포인트에 로그인 인증(get_current_user) 의존성이 강제되는지 검증"""
    sig = inspect.signature(fileupload_router.upload_files)
    assert "current_user" in sig.parameters
    dep = sig.parameters["current_user"].default
    assert getattr(dep, "dependency", None) is get_current_user


def test_path_traversal_blocked_in_policy_and_service():
    """sub_path 및 original_name 경로 이탈(../) 우회 차단 검증"""
    user = SimpleNamespace(id=5)

    assert is_own_private_path(user, "PRIVATE", "USERS/5") is True
    assert is_own_private_path(user, "PRIVATE", "USERS/5/docs") is True
    assert is_own_private_path(user, "PRIVATE", "USERS/5/../../USERS/1") is False
    assert is_own_private_path(user, "PRIVATE", "USERS/5\\..\\..\\USERS\\1") is False

    assert is_shared_office_path("SYSTEM", "GLOBAL/OFFICE/2026") is True
    assert is_shared_office_path("SYSTEM", "GLOBAL/OFFICE/../../SECRET") is False

    assert media_service.sanitize_sub_path("PUBLIC", "docs/2026") == "PUBLIC/docs/2026"
    with pytest.raises(HTTPException) as exc:
        media_service.sanitize_sub_path("PUBLIC", "../PRIVATE/USERS/1")
    assert exc.value.status_code == 400

    assert media_service.sanitize_original_filename("../../evil.pdf") == "evil.pdf"
    assert media_service.sanitize_original_filename("..\\..\\배차표.pdf") == "배차표.pdf"
    assert media_service.sanitize_original_filename("..") == "unnamed"


def test_media_secure_serve_blocks_deleted_and_encodes_korean_header(monkeypatch):
    """삭제된 자산 404 차단, 한글 파일명 X-Accel-Redirect URI 인코딩, nosniff 헤더 검증"""
    user = SimpleNamespace(id=1)

    # 1. 삭제된 자산 조회 시 None 반환 -> 404
    db_deleted = MagicMock()
    db_deleted.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc_404:
        media_router.media_secure_serve(asset_id=999, size=None, db=db_deleted, current_user=user)
    assert exc_404.value.status_code == 404

    # 2. 한글/공백 포함 문서 파일 X-Accel-Redirect 인코딩 및 nosniff 검증
    asset = SimpleNamespace(
        id=10,
        user_id=1,
        access_level="PRIVATE",
        file_path="PRIVATE/USERS/1/DOC_abcd1234_제주 배차표.PDF",
        mime_type="application/pdf",
        category="document",
        is_deleted=False,
        meta_info={},
    )
    db_ok = MagicMock()
    db_ok.query.return_value.filter.return_value.first.return_value = asset
    monkeypatch.setattr(media_router, "can_user_read_asset", lambda u, a, db: True)
    monkeypatch.setattr(
        media_router,
        "resolve_secure_serve_response",
        lambda db, a, size=None: ("/PRIVATE/USERS/1/DOC_abcd1234_제주 배차표.PDF", "application/pdf"),
    )

    resp = media_router.media_secure_serve(asset_id=10, size=None, db=db_ok, current_user=user)
    x_accel = resp.headers["X-Accel-Redirect"]
    assert x_accel.isascii()
    assert "%EC%A0%9C%EC%A3%BC%20%EB%B0%B0%EC%B0%A8%ED%91%9C.PDF" in x_accel
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Content-Type"] == "application/pdf"


def test_media_sync_routes_are_not_async():
    """동기 파일·DB 작업을 수행하는 media_router 엔드포인트들이 def로 선언되어 스레드풀을 타는지 검증"""
    sync_endpoints = [
        media_router.media_secure_serve,
        media_router.media_get_settings_api,
        media_router.media_update_settings_api,
        media_router.media_admin_stats,
        media_router.media_admin_recent,
        media_router.media_publish,
        media_router.media_admin_list,
        media_router.media_admin_create_folder,
        media_router.media_admin_zip_download,
        media_router.media_admin_backup,
        media_router.media_admin_bulk_delete,
        media_router.media_admin_run_gc,
        media_router.media_admin_delete,
    ]
    for fn in sync_endpoints:
        assert not inspect.iscoroutinefunction(fn), f"{fn.__name__} should be sync def"
