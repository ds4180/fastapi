"""
============================================================================
[SQLAlchemy 세션 감사 자동 추출 리스너 (core/audit_listener.py)]
============================================================================

💡 이 파일의 역할:
SQLAlchemy Session의 `before_flush` 이벤트를 가로채어,
`AuditMixin`을 상속받은 모든 도메인 모델(배차, 차량, 휴무, 게시판 등)의 
컬럼 변경 사항(Diff-Patch)을 자동으로 계산하고 `audit_logs` 테이블에 보존합니다.

🌟 100% 개발자 무간섭 (Zero-Burden):
도메인 개발자가 "로그 남기는 코드"를 한 줄도 짜지 않아도, 
DB 커밋 순간 수정 전(from) 값과 수정 후(to) 값이 초 단위로 영구 박제됩니다!
"""

import logging
from typing import TYPE_CHECKING
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from core.audit import sanitize_diff

if TYPE_CHECKING:
    from models.base import AuditMixin
    from models.audit import AuditLog

logger = logging.getLogger("core.audit.listener")


def audit_before_flush(session: Session, flush_context, instances):
    """
    [SQLAlchemy before_flush 이벤트 핸들러]
    세션에 변경(dirty)되거나 삭제(deleted)된 AuditMixin 인스턴스를 검사하여
    Diff-Patch 감사로그를 현재 트랜잭션에 자동으로 탑재합니다.
    """
    # 🛡️ [무한 재귀 방어]: 감사로그 레코드 생성으로 인한 중복 flush 트리거 차단
    if getattr(session, "_is_audit_processing", False):
        return

    session._is_audit_processing = True
    try:
        from models.base import AuditMixin
        from models.audit import AuditLog

        # ----------------------------------------------------------------------
        # 1. 수정된 객체 (session.dirty) -> UPDATE Diff-Patch 자동 추출
        # ----------------------------------------------------------------------
        for target in list(session.dirty):
            # AuditMixin을 상속받은 도메인 모델만 추적 (AuditLog 자체는 제외)
            if not isinstance(target, AuditMixin) or isinstance(target, AuditLog):
                continue

            state = inspect(target)
            exclude_fields = getattr(target, "__audit_exclude_fields__", set()) or set()
            changes = []

            for attr in state.attrs:
                # 추적 제외 필드(updated_at, version 등)는 건너뜀
                if attr.key in exclude_fields or attr.key == "version":
                    continue

                hist = attr.history
                # 컬럼에 실제 값 변경이 일어난 경우
                if hist.has_changes():
                    from_val = hist.deleted[0] if hist.deleted else None
                    to_val = hist.added[0] if hist.added else getattr(target, attr.key, None)

                    # 단순 문자열 변환 및 JSON 직렬화 가능 형태로 보정
                    from_str = str(from_val) if from_val is not None else None
                    to_str = str(to_val) if to_val is not None else None

                    if from_str != to_str:
                        changes.append({
                            "field": attr.key,
                            "from": from_str,
                            "to": to_str
                        })

            # 실제로 바뀐 컬럼이 하나라도 있는 경우에만 감사로그 생성
            if changes:
                # 1) 버전 번호 1 자동 증가 (낙관적 락)
                target.version = (target.version or 1) + 1

                # 2) 메타데이터 및 PK 추출
                app_id = getattr(target, "__audit_app_id__", "system")
                table_name = getattr(target, "__tablename__", target.__class__.__name__)
                pk_val = getattr(target, "id", None) or getattr(target, "pk", None) or ""

                # 3) 민감정보 마스킹된 Diff
                safe_diff = sanitize_diff(changes)

                # 4) AuditLog 레코드를 현재 세션 플러시에 함께 추가
                audit_entry = AuditLog(
                    app_id=app_id,
                    log_type="CHANGE",
                    severity="INFO",
                    action="UPDATE",
                    resource_type=table_name,
                    resource_id=str(pk_val) if pk_val else None,
                    title=f"[{table_name}] #{pk_val} 데이터 수정됨",
                    diff_payload=safe_diff,
                    metadata_payload={"model": target.__class__.__name__, "version": target.version}
                )
                session.add(audit_entry)

        # ----------------------------------------------------------------------
        # 2. 삭제된 객체 (session.deleted) -> DELETE 감사로그 자동 적재
        # ----------------------------------------------------------------------
        for target in list(session.deleted):
            if not isinstance(target, AuditMixin) or isinstance(target, AuditLog):
                continue

            app_id = getattr(target, "__audit_app_id__", "system")
            table_name = getattr(target, "__tablename__", target.__class__.__name__)
            pk_val = getattr(target, "id", None) or getattr(target, "pk", None) or ""

            audit_entry = AuditLog(
                app_id=app_id,
                log_type="CHANGE",
                severity="WARN",
                action="DELETE",
                resource_type=table_name,
                resource_id=str(pk_val) if pk_val else None,
                title=f"[{table_name}] #{pk_val} 데이터 삭제됨",
                diff_payload=[],
                metadata_payload={"model": target.__class__.__name__}
            )
            session.add(audit_entry)

    except Exception as e:
        logger.error(f"❌ [audit_before_flush] 자동 Diff 추출 중 오류 발생: {e}", exc_info=True)
    finally:
        session._is_audit_processing = False


def setup_audit_listeners():
    """
    SQLAlchemy 세션에 전역 감사로그 자동 캡처 리스너를 등록합니다.
    """
    event.listen(Session, "before_flush", audit_before_flush)
    logger.info("🏛️ [Audit] SQLAlchemy AuditMixin 자동 Diff-Patch 리스너가 등록되었습니다.")
