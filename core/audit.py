"""
============================================================================
[코어 전역 감사로그 서비스 파사드 (core/audit.py)]
============================================================================

💡 이 파일의 역할:
시스템 내 모든 중요 활동(접속/인증, 앱 데이터 변경, 에러, 보안 침해)을 
`audit_logs` 테이블에 안전하고 일관된 형식으로 기록하는 중앙 관문(Facade)입니다.

🌟 실사용 핵심 방어벽:
1. [Fail-Safe 격리 (safe_log_audit)]: 로깅 중 DB 에러가 발생해도 주 비즈니스 트랜잭션이 중단되지 않습니다.
2. [개인정보/비밀번호 마스킹 (sanitize_diff)]: password, resident_no 등 민감 필드는 '********'로 자동 마스킹됩니다.
3. [인사이동 불변 스냅샷 (get_user_summary)]: 작업 시점의 사용자 이름, 부서, 권한 랭크를 텍스트로 보존합니다.
"""

from __future__ import annotations

import logging
from typing import Optional, Any, Union, TYPE_CHECKING
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from models.user import User
    from models.audit import AuditLog

# 🛡️ 개인정보보호 및 보안을 위한 민감 필드 마스킹 목록
SENSITIVE_FIELDS = {
    "password",
    "resident_no",
    "account_no",
    "secret",
    "token",
    "session_key",
    "credit_card",
}

logger = logging.getLogger("core.audit")

# ----------------------------------------------------------------------------
# 🏛️ 보안 감사 이벤트 훅 레지스트리 (Observer Pattern - 느슨한 결합)
# ----------------------------------------------------------------------------
# 코어 계층이 상위 도메인 앱(Watchdog 등)을 직접 역참조하지 않도록
# 콜백 훅을 등록받아 안전하게 실행합니다.
SECURITY_AUDIT_HOOKS: list = []


def register_security_audit_hook(callback) -> None:
    """
    [보안 감사 훅 등록기]
    SECURITY 타입의 감사로그가 발생할 때 실행할 도메인 리스너 콜백을 등록합니다.
    """
    if callback not in SECURITY_AUDIT_HOOKS:
        SECURITY_AUDIT_HOOKS.append(callback)
        logger.info(f"🏛️ [Audit] 보안 감사 이벤트 훅 등록 완료: {callback.__name__}")


def get_user_summary(user: Optional[User]) -> str:
    """
    사용자의 당시 신분 스냅샷 문자열을 반환합니다.
    예: "홍길동 (운수1팀/Lv.2)" 또는 "GUEST (비로그인)"
    """
    if not user:
        return "GUEST (비로그인)"

    try:
        # 표시 이름 결정 (real_name > display_name > username)
        profile = getattr(user, "profile", None)
        display_name = getattr(user, "real_name", None) or (
            getattr(profile, "display_name", None) if profile else None
        ) or getattr(user, "username", "Unknown")

        # 랭크 레벨 결정 (0~9)
        rank = user.rank() if callable(getattr(user, "rank", None)) else getattr(user, "rank", 0)

        # 주 소속 부서/팀
        primary_group = getattr(profile, "primary_group", None) if profile else None
        group_str = primary_group if primary_group else "소속없음"

        return f"{display_name} ({group_str}/Lv.{rank})"
    except Exception:
        # 🛡️ 세션 분리(Detached) 등으로 지연 로딩 실패 시에도 안전한 기본 폴백 반환
        uname = getattr(user, "username", "User")
        uid = getattr(user, "id", "?")
        return f"{uname}#{uid} (스냅샷 로드 제한)"


def sanitize_diff(diff_payload: Optional[list]) -> list:
    """
    diff_payload 내부의 민감 정보(비밀번호, 주민번호, 계좌번호 등)를
    '********'로 자동 마스킹하여 개인정보 침해를 원천 방지합니다.
    """
    if not diff_payload or not isinstance(diff_payload, list):
        return []

    sanitized = []
    for item in diff_payload:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        field_name = str(entry.get("field", "")).lower()

        # 민감 필드에 해당하거나 'password'/'secret'/'token'이 포함된 경우 마스킹
        if field_name in SENSITIVE_FIELDS or any(s in field_name for s in ["password", "secret", "token"]):
            if "from" in entry and entry["from"] is not None:
                entry["from"] = "********"
            if "to" in entry and entry["to"] is not None:
                entry["to"] = "********"
            if "value" in entry and entry["value"] is not None:
                entry["value"] = "********"

        sanitized.append(entry)

    return sanitized


def log_audit(
    db: Session,
    app_id: Optional[str],
    log_type: str,
    action: str,
    title: str,
    user: Optional[Any] = None,
    severity: str = "INFO",
    resource_type: Optional[str] = None,
    resource_id: Optional[Union[str, int]] = None,
    message: Optional[str] = None,
    diff_payload: Optional[list] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> Any:
    """
    [전사 통합 감사로그 표준 기록 함수]
    """
    from models.audit import AuditLog

    # 1. 사용자 신분 스냅샷
    user_summary = get_user_summary(user)
    user_id = getattr(user, "id", None) if user else None

    # 2. 민감 정보 마스킹된 Diff
    safe_diff = sanitize_diff(diff_payload)

    # 3. AuditLog 레코드 생성
    audit_record = AuditLog(
        app_id=app_id,
        log_type=log_type.upper(),
        severity=severity.upper(),
        action=action.upper(),
        user_id=user_id,
        user_summary=user_summary,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        title=title,
        message=message,
        diff_payload=safe_diff,
        metadata_payload=metadata or {},
        ip_address=ip_address,
    )

    db.add(audit_record)
    if commit:
        db.commit()
        db.refresh(audit_record)
        if log_type.upper() == "SECURITY":
            # 🌟 옵저버 훅들을 순회 호출하여 코어-도메인 역참조를 원천 차단
            for hook in SECURITY_AUDIT_HOOKS:
                try:
                    hook(db, audit_record)
                except Exception as he:
                    logger.warning(f"⚠️ Audit 보안 리스너 훅 실행 실패 ({getattr(hook, '__name__', 'hook')}): {he}")

    return audit_record


def safe_log_audit(
    db: Session,
    app_id: Optional[str],
    log_type: str,
    action: str,
    title: str,
    user: Optional[User] = None,
    severity: str = "INFO",
    resource_type: Optional[str] = None,
    resource_id: Optional[Union[str, int]] = None,
    message: Optional[str] = None,
    diff_payload: Optional[list] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> Optional[AuditLog]:
    """
    [Fail-Safe 방어 감사로그 기록 함수]
    로깅 도중 예외가 발생하더라도 메인 비즈니스(배차, 로그인 등)가 실패하지 않도록 보호합니다.
    """
    try:
        return log_audit(
            db=db,
            app_id=app_id,
            log_type=log_type,
            action=action,
            title=title,
            user=user,
            severity=severity,
            resource_type=resource_type,
            resource_id=resource_id,
            message=message,
            diff_payload=diff_payload,
            metadata=metadata,
            ip_address=ip_address,
            commit=commit,
        )
    except Exception as e:
        logger.error(f"❌ [safe_log_audit] 감사로그 기록 실패 (주 트랜잭션 보호): {e}", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return None
