"""
게시판·댓글 권한 우회(비밀글/삭제댓글) 및 동시 읽음 방어 검증 테스트 (tests/test_board_comment_security.py)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from domain.v1.comment import comment_service


def test_comment_list_blocks_secret_or_unviewable_post(monkeypatch):
    """비밀글/예약글 등 can_view_post=False인 게시물에 대한 댓글 API 접근이 403으로 차단되는지 검증"""
    from domain.v1.board import board_crud

    post = SimpleNamespace(id=50, board=SimpleNamespace(id=1, slug="free"), is_deleted=False)
    monkeypatch.setattr(comment_service, "_get_active_post_or_404", lambda db, pid: post)
    monkeypatch.setattr(comment_service, "enforce_post_service_permission", lambda *a, **kw: None)
    monkeypatch.setattr(board_crud, "can_view_post", lambda p, u, b, db=None: False)

    user = SimpleNamespace(id=2, rank=lambda: 1)
    with pytest.raises(HTTPException) as exc:
        comment_service.list_post_comments(MagicMock(), post_id=50, current_user=user)
    assert exc.value.status_code == 403


def test_deleted_comment_cannot_be_updated_or_deleted():
    """이미 소프트 삭제된 댓글은 _get_comment_or_404에서 404로 차단되는지 검증"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        comment_service._get_comment_or_404(db, comment_id=999)
    assert exc.value.status_code == 404
