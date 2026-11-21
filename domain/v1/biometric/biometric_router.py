"""
============================================================================
[생체 인증 / WebAuthn Passkey 통합 라우터 (domain/v1/biometric/biometric_router.py)]
============================================================================

- Passkey 등록(options/verify) 및 검증(options/verify)
- 등록된 보안 기기 목록 조회, 별명 변경, 해지(삭제)
- 생체 인증 및 원격 지문 공조 감사 이력(BiometricAuthLog) 조회/기록
- 동적 RP_ID 지원: jeju.live / www.jeju.live -> jeju.live, dev.jeju.live -> dev.jeju.live, localhost -> localhost
"""

from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import webauthn
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from core.deps import get_current_user
from database import get_db
from models import BiometricAuthLog, User, UserPasskey

router = APIRouter(
    prefix="/v1/biometric",
    tags=["Biometric"],
)

# Redis 장애 시를 대비한 프로세스 내 폴백 챌린지 저장소 (TTL 300초)
_FALLBACK_CHALLENGES: Dict[str, tuple[str, float]] = {}


def _get_redis():
    try:
        from redis_config import rd
        return rd
    except Exception:
        return None


def _save_challenge(purpose: str, user_id: int, challenge_bytes: bytes) -> None:
    challenge_b64 = bytes_to_base64url(challenge_bytes)
    key = f"webauthn:challenge:{purpose}:{user_id}"
    rd = _get_redis()
    if rd is not None:
        try:
            rd.setex(key, 300, challenge_b64)
            return
        except Exception:
            pass
    _FALLBACK_CHALLENGES[key] = (challenge_b64, datetime.now().timestamp() + 300)


def _pop_challenge(purpose: str, user_id: int) -> Optional[bytes]:
    key = f"webauthn:challenge:{purpose}:{user_id}"
    rd = _get_redis()
    if rd is not None:
        try:
            val = rd.get(key)
            if val:
                rd.delete(key)
                if isinstance(val, bytes):
                    val = val.decode("utf-8")
                return base64url_to_bytes(val)
        except Exception:
            pass
    entry = _FALLBACK_CHALLENGES.pop(key, None)
    if entry and entry[1] >= datetime.now().timestamp():
        return base64url_to_bytes(entry[0])
    return None


def _resolve_rp_and_origin(request: Request) -> tuple[str, str]:
    """접속 Origin/Host 기반으로 RP_ID와 expected_origin을 안전하게 판별합니다."""
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or "localhost").split(",")[0].strip()
        origin = f"{proto}://{host}"

    parsed = urlparse(origin)
    hostname = (parsed.hostname or "localhost").lower()

    if hostname in ("jeju.live", "www.jeju.live"):
        rp_id = "jeju.live"
    elif hostname == "dev.jeju.live":
        rp_id = "dev.jeju.live"
    elif hostname in ("localhost", "127.0.0.1"):
        rp_id = "localhost"
    else:
        rp_id = hostname

    return rp_id, origin


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _add_log(
    db: Session,
    user_id: int,
    action: str,
    status: str,
    request: Request,
    credential_id: Optional[str] = None,
    device_name: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    db.add(
        BiometricAuthLog(
            user_id=user_id,
            credential_id=credential_id,
            action=action,
            status=status,
            device_name=device_name,
            ip_address=_client_ip(request),
            detail=detail[:255] if detail else None,
        )
    )


class RegisterVerifyPayload(BaseModel):
    credential: dict
    device_name: Optional[str] = None


class AuthVerifyPayload(BaseModel):
    credential: dict
    action: Optional[str] = "VERIFY"
    detail: Optional[str] = None


class PasskeyUpdatePayload(BaseModel):
    device_name: str


class CoopLogPayload(BaseModel):
    action: str
    status: str
    detail: Optional[str] = None
    device_name: Optional[str] = None


@router.get("/passkeys")
def get_my_passkeys(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rp_id, origin = _resolve_rp_and_origin(request)
    passkeys = (
        db.query(UserPasskey)
        .filter(UserPasskey.user_id == current_user.id, UserPasskey.is_active == True)
        .order_by(UserPasskey.created_at.desc())
        .all()
    )
    logs = (
        db.query(BiometricAuthLog)
        .filter(BiometricAuthLog.user_id == current_user.id)
        .order_by(BiometricAuthLog.created_at.desc())
        .limit(30)
        .all()
    )
    return {
        "rp_id": rp_id,
        "origin": origin,
        "passkeys": [
            {
                "id": p.id,
                "credential_id": p.credential_id,
                "device_name": p.device_name,
                "sign_count": p.sign_count,
                "transports": p.transports or [],
                "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in passkeys
        ],
        "logs": [
            {
                "id": l.id,
                "action": l.action,
                "status": l.status,
                "device_name": l.device_name,
                "ip_address": l.ip_address,
                "detail": l.detail,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.post("/register/options")
def get_registration_options(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rp_id, _ = _resolve_rp_and_origin(request)
    existing = (
        db.query(UserPasskey)
        .filter(UserPasskey.user_id == current_user.id, UserPasskey.is_active == True)
        .all()
    )

    exclude_credentials: List[PublicKeyCredentialDescriptor] = []
    for item in existing:
        try:
            exclude_credentials.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            )
        except Exception:
            continue

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name="Jeju.live 통합 관제",
        user_id=str(current_user.id).encode("utf-8"),
        user_name=current_user.username,
        user_display_name=current_user.real_name or current_user.username,
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )

    _save_challenge("register", current_user.id, options.challenge)
    return json.loads(webauthn.options_to_json(options))


@router.post("/register/verify")
def verify_registration(
    payload: RegisterVerifyPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rp_id, origin = _resolve_rp_and_origin(request)
    expected_challenge = _pop_challenge("register", current_user.id)
    if not expected_challenge:
        raise HTTPException(status_code=400, detail="등록 세션(Challenge)이 만료되었습니다. 다시 시도해 주세요.")

    try:
        verification = webauthn.verify_registration_response(
            credential=payload.credential,
            expected_challenge=expected_challenge,
            expected_origin=origin,
            expected_rp_id=rp_id,
            require_user_verification=True,
        )
    except Exception as e:
        _add_log(db, current_user.id, "REGISTER", "FAILED", request, detail=f"등록 검증 실패: {e}")
        db.commit()
        raise HTTPException(status_code=400, detail=f"지문 등록 검증 실패: {e}")

    cred_id_b64 = bytes_to_base64url(verification.credential_id)
    pub_key_b64 = bytes_to_base64url(verification.credential_public_key)
    transports = payload.credential.get("response", {}).get("transports") or ["internal"]
    device_name = (payload.device_name or "").strip() or "내 생체인증 기기"

    existing = db.query(UserPasskey).filter(UserPasskey.credential_id == cred_id_b64).first()
    if existing:
        if existing.user_id != current_user.id:
            raise HTTPException(status_code=409, detail="이미 다른 계정에 등록된 보안 열쇠입니다.")
        existing.public_key = pub_key_b64
        existing.sign_count = verification.sign_count
        existing.device_name = device_name
        existing.transports = transports
        existing.is_active = True
        passkey = existing
    else:
        passkey = UserPasskey(
            user_id=current_user.id,
            credential_id=cred_id_b64,
            public_key=pub_key_b64,
            sign_count=verification.sign_count,
            device_name=device_name,
            transports=transports,
            aaguid=str(verification.aaguid) if getattr(verification, "aaguid", None) else None,
        )
        db.add(passkey)

    _add_log(
        db,
        current_user.id,
        "REGISTER",
        "SUCCESS",
        request,
        credential_id=cred_id_b64,
        device_name=device_name,
        detail=f"Passkey 등록 완료 ({rp_id})",
    )
    db.commit()
    db.refresh(passkey)

    return {
        "verified": True,
        "passkey": {
            "id": passkey.id,
            "credential_id": passkey.credential_id,
            "device_name": passkey.device_name,
            "sign_count": passkey.sign_count,
            "created_at": passkey.created_at.isoformat() if passkey.created_at else None,
        },
    }


@router.post("/authenticate/options")
def get_authentication_options(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rp_id, _ = _resolve_rp_and_origin(request)
    passkeys = (
        db.query(UserPasskey)
        .filter(UserPasskey.user_id == current_user.id, UserPasskey.is_active == True)
        .all()
    )
    if not passkeys:
        raise HTTPException(status_code=404, detail="등록된 Passkey 기기가 없습니다. 먼저 기기를 등록해 주세요.")

    allow_credentials: List[PublicKeyCredentialDescriptor] = []
    for pk in passkeys:
        try:
            transports = []
            for t in (pk.transports or []):
                try:
                    transports.append(AuthenticatorTransport(t))
                except Exception:
                    continue
            allow_credentials.append(
                PublicKeyCredentialDescriptor(
                    id=base64url_to_bytes(pk.credential_id),
                    transports=transports or None,
                )
            )
        except Exception:
            continue

    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _save_challenge("auth", current_user.id, options.challenge)
    return json.loads(webauthn.options_to_json(options))


@router.post("/authenticate/verify")
def verify_authentication(
    payload: AuthVerifyPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rp_id, origin = _resolve_rp_and_origin(request)
    expected_challenge = _pop_challenge("auth", current_user.id)
    if not expected_challenge:
        raise HTTPException(status_code=400, detail="인증 세션(Challenge)이 만료되었습니다. 다시 시도해 주세요.")

    raw_id = payload.credential.get("id") or payload.credential.get("rawId")
    passkey = (
        db.query(UserPasskey)
        .filter(
            UserPasskey.user_id == current_user.id,
            UserPasskey.credential_id == raw_id,
            UserPasskey.is_active == True,
        )
        .first()
    )
    if not passkey:
        _add_log(db, current_user.id, payload.action or "VERIFY", "FAILED", request, detail="등록되지 않은 보안 열쇠")
        db.commit()
        raise HTTPException(status_code=404, detail="현재 계정에 등록된 Passkey를 찾을 수 없습니다.")

    try:
        verification = webauthn.verify_authentication_response(
            credential=payload.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=base64url_to_bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as e:
        _add_log(
            db,
            current_user.id,
            payload.action or "VERIFY",
            "FAILED",
            request,
            credential_id=passkey.credential_id,
            device_name=passkey.device_name,
            detail=f"서명 검증 실패: {e}",
        )
        db.commit()
        raise HTTPException(status_code=400, detail=f"지문 서명 검증 실패: {e}")

    passkey.sign_count = verification.new_sign_count
    passkey.last_used_at = datetime.now()

    action_name = payload.action or "VERIFY"
    _add_log(
        db,
        current_user.id,
        action_name,
        "SUCCESS",
        request,
        credential_id=passkey.credential_id,
        device_name=passkey.device_name,
        detail=payload.detail or f"Passkey 서명 검증 통과 (누적 {passkey.sign_count}회)",
    )
    db.commit()

    return {
        "verified": True,
        "device_name": passkey.device_name,
        "sign_count": passkey.sign_count,
        "credential_id": passkey.credential_id,
    }


@router.patch("/passkeys/{passkey_id}")
def update_passkey_name(
    passkey_id: int,
    payload: PasskeyUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    passkey = (
        db.query(UserPasskey)
        .filter(UserPasskey.id == passkey_id, UserPasskey.user_id == current_user.id, UserPasskey.is_active == True)
        .first()
    )
    if not passkey:
        raise HTTPException(status_code=404, detail="등록된 기기를 찾을 수 없습니다.")

    new_name = payload.device_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="기기 이름을 입력해 주세요.")
    passkey.device_name = new_name[:120]
    db.commit()
    return {"id": passkey.id, "device_name": passkey.device_name}


@router.delete("/passkeys/{passkey_id}")
def revoke_passkey(
    passkey_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    passkey = (
        db.query(UserPasskey)
        .filter(UserPasskey.id == passkey_id, UserPasskey.user_id == current_user.id, UserPasskey.is_active == True)
        .first()
    )
    if not passkey:
        raise HTTPException(status_code=404, detail="등록된 기기를 찾을 수 없습니다.")

    device_name = passkey.device_name
    cred_id = passkey.credential_id
    db.delete(passkey)
    _add_log(
        db,
        current_user.id,
        "REVOKE",
        "SUCCESS",
        request,
        credential_id=cred_id,
        device_name=device_name,
        detail="보안 기기 해지 및 삭제",
    )
    db.commit()
    return {"deleted": True}


@router.post("/coop/log")
def log_coop_event(
    payload: CoopLogPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _add_log(
        db,
        current_user.id,
        payload.action[:30],
        payload.status[:20],
        request,
        device_name=payload.device_name,
        detail=payload.detail,
    )
    db.commit()
    return {"logged": True}
