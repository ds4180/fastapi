"""
커스텀 앱(survey 거버넌스 권한·DRAFT/비대상 차단, blackbox 감사로그) 테스트 (tests/test_custom_apps_security.py)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from domain.v1.custom.survey import survey_router


def test_survey_readable_blocks_draft_and_untargeted_via_governance(monkeypatch):
    """AppRegistry('survey') 권한이 없는 일반 사원은 DRAFT 및 비대상 설문 열람 시 403 차단되는지 검증"""
    user = SimpleNamespace(id=10, profile=SimpleNamespace(rank_level=2), rank=lambda: 2)
    monkeypatch.setattr(survey_router, "_is_survey_admin", lambda u, db, action="read": False)
    monkeypatch.setattr(survey_router.service, "is_user_targeted", lambda c, u: False)

    # 1. DRAFT 초안 차단
    draft_campaign = SimpleNamespace(id=1, status="DRAFT")
    with pytest.raises(HTTPException) as exc_draft:
        survey_router._ensure_survey_readable(MagicMock(), draft_campaign, user, my_rows=[])
    assert exc_draft.value.status_code == 403

    # 2. OPEN 설문이라도 비대상·미응답자는 차단
    open_campaign = SimpleNamespace(id=2, status="OPEN")
    with pytest.raises(HTTPException) as exc_untargeted:
        survey_router._ensure_survey_readable(MagicMock(), open_campaign, user, my_rows=[])
    assert exc_untargeted.value.status_code == 403

    # 3. 설문 관리 권한자(AppRegistry 거버넌스 통과)는 DRAFT도 열람 허용
    monkeypatch.setattr(survey_router, "_is_survey_admin", lambda u, db, action="read": True)
    survey_router._ensure_survey_readable(MagicMock(), draft_campaign, user, my_rows=[])
