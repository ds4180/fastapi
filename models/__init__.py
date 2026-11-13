"""
============================================================================
[백엔드 모델 통합 관문 (models/__init__.py - Facade Pattern)]
============================================================================

💡 이 파일의 역할:
각 도메인별(user, system, board, dispatch 등)로 깔끔하게 분할된 모든 모델들을
한곳으로 모아 외부에 단일 창구(Facade)로 제공(Re-export)합니다.

🌟 100% 하위 호환성 보장:
기존 프로젝트의 수십 개 라우터 및 서비스 코드에서 사용하는
`from models import User, Post, Dispatch, Base, ...` 문법이
단 1글자의 수정도 없이 완벽하게 그대로 동작합니다!
"""

# 📌 1. 최소 척추 (Base & Mixin)
from models.base import Base, TimestampMixin, AuditMixin

# 📌 2. 인증 및 사용자/그룹 코어
from models.user import User, UserProfile, UserSession, Group

# 📌 3. 시스템 메타 및 자율 신경계 태스크
from models.system import (
    SystemConfig,
    AppRegistry,
    ServiceRegistry,
    ServiceEngine,
    ServiceApp,
    ServiceInstance,
    Menu,
    SystemTask,
)

# 📌 4. 게시판 및 CMS 콘텐츠
from models.board import (
    BoardConfig,
    Post,
    PostReaction,
    Tag,
    Comment,
    PostRead,
    post_tag,
)

# 📌 6. 배차 및 노선 관리
from models.dispatch import (
    RouteMaster,
    RouteTimetable,
    Dispatch,
)

# 📌 7. 기타 개별 도메인 업무 앱
from models.dayoff import DayOff, DayOffPolicy
from models.alert import Alert
from models.page import Page
from models.media import MediaAsset
from models.push import PushSubscription

# 📌 8. 전역 감사로그 및 보안 관제 코어
from models.audit import AuditLog, SENSITIVE_FIELDS

# 📌 9. 전사 통합 미니앱 마이크로 텍스트 엔진
from models.miniapp import MiniappItem, MiniappRead

# 외부 노출 심볼 목록 (명시적 공개)
__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    "AuditMixin",
    # Audit & Observability
    "AuditLog",
    "SENSITIVE_FIELDS",
    # User & Group
    "User",
    "UserProfile",
    "UserSession",
    "Group",
    # System
    "SystemConfig",
    "AppRegistry",
    "ServiceRegistry",
    "ServiceEngine",
    "ServiceApp",
    "ServiceInstance",
    "Menu",
    "SystemTask",
    # Board
    "BoardConfig",
    "Post",
    "PostReaction",
    "Tag",
    "Comment",
    "PostRead",
    "post_tag",
    # Dispatch
    "RouteMaster",
    "RouteTimetable",
    "Dispatch",
    # Others
    "DayOff",
    "DayOffPolicy",
    "Alert",
    "Page",
    "MediaAsset",
    "PushSubscription",
    "AuditLog",
    "SENSITIVE_FIELDS",
    "MiniappItem",
    "MiniappRead",
]
