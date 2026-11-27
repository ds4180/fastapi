"""
============================================================================
[미디어 자산 관리 동적 정책·권한 서비스 (domain/media/media_policy_service.py)]
============================================================================
- SystemConfig(key="media_settings")를 단일 진실 공급원(SSOT)으로 삼아
  업로드 용량·확장자, WebP 품질·해상도, 배포 원본 생략 여부, 60/30일 수명주기,
  계층별 접근 최소 랭크, ZIP 일괄 다운로드 제한, 탐색기 기본값까지 통합 관리합니다.
"""

from __future__ import annotations

import os
import posixpath
from typing import Any, Dict, List, Tuple
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from core.permission import ROOT_RANK, can_access_app, get_user_rank
from domain.media import media_config as config
from models import AppRegistry, MediaAsset, SystemConfig, User

MEDIA_SETTINGS_KEY = "media_settings"

DEFAULT_TAB_LABELS: Dict[str, str] = {
    "SHARED": "공용폴더 (OFFICE)",
    "PERSONAL": "내 파일함 (USERS)",
    "PUBLIC": "공개 자산 (PUBLIC)",
    "PROTECTED": "사내 보안 (PROTECTED)",
    "SYSTEM": "시스템 코어 (SYSTEM)",
    "PRIVATE": "전체 유저함 (PRIVATE)",
}

DEFAULT_ALLOWED_EXTENSIONS: List[str] = [
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".docx", ".xlsx", ".zip", ".hwp", ".txt", ".csv",
]

DEFAULT_MEDIA_SETTINGS: Dict[str, Any] = {
    # 1. 업로드 및 파일 검증 정책
    "max_file_size_mb": 100,
    "enforce_extension_whitelist": True,
    "allowed_extensions": list(DEFAULT_ALLOWED_EXTENSIONS),
    "default_upload_tier_for_user": "PUBLIC",

    # 2. 이미지 썸네일·배포 정책
    "webp_quality": 85,
    "thumb_sm_max_px": 300,
    "thumb_md_max_px": 900,
    "thumb_lg_max_px": 1920,
    "publish_strip_image_original": True,

    # 3. 수명주기·보관·GC 정책
    "enable_original_auto_expiry": True,
    "original_keep_days": 60,
    "isolation_retention_days": 30,
    "default_gc_indices": [1, 2, 3, 4, 5, 6],

    # 4. 접근 권한·다운로드 거버넌스 정책
    "shared_office_min_rank": 2,
    "shared_office_write_min_rank": 4,
    "protected_min_rank": 2,
    "system_serve_min_rank": 2,
    "zip_download_max_files": 100,

    # 5. 탐색기 기본 UI 정책
    "default_view_mode": "grid",
    "default_recursive_view": True,
    "tab_labels": dict(DEFAULT_TAB_LABELS),
}


def _clamp_int(value: Any, min_val: int, max_val: int, fallback: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_val, min(max_val, num))


def _normalize_extensions(raw: Any) -> List[str]:
    if isinstance(raw, str):
        items = [part.strip() for part in raw.replace(";", ",").split(",")]
    elif isinstance(raw, list):
        items = [str(part).strip() for part in raw]
    else:
        return list(DEFAULT_ALLOWED_EXTENSIONS)

    cleaned: List[str] = []
    seen = set()
    for item in items:
        if not item:
            continue
        ext = item.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        ext = "".join(ch for ch in ext if ch.isalnum() or ch == ".")
        if len(ext) < 2 or ext == ".":
            continue
        if ext not in seen:
            seen.add(ext)
            cleaned.append(ext)

    return cleaned if cleaned else list(DEFAULT_ALLOWED_EXTENSIONS)


def _normalize_gc_indices(raw: Any) -> List[int]:
    if not isinstance(raw, list):
        return [1, 2, 3, 4, 5, 6]
    valid = sorted({int(x) for x in raw if isinstance(x, (int, str)) and str(x).isdigit() and 1 <= int(x) <= 6})
    return valid if valid else [1, 2, 3, 4, 5, 6]


def normalize_media_settings(raw: Any) -> Dict[str, Any]:
    """DB JSON 또는 클라이언트 입력을 안전하게 검증·정규화합니다."""
    src = raw if isinstance(raw, dict) else {}

    default_tier = str(
        src.get("default_upload_tier_for_user") or DEFAULT_MEDIA_SETTINGS["default_upload_tier_for_user"]
    ).strip().upper()
    if default_tier not in ("PUBLIC", "PROTECTED", "PRIVATE"):
        default_tier = "PUBLIC"

    view_mode = str(src.get("default_view_mode") or DEFAULT_MEDIA_SETTINGS["default_view_mode"]).strip().lower()
    if view_mode not in ("grid", "list"):
        view_mode = "grid"

    raw_labels = src.get("tab_labels") if isinstance(src.get("tab_labels"), dict) else {}
    tab_labels: Dict[str, str] = {}
    for key, fallback_label in DEFAULT_TAB_LABELS.items():
        val = str(raw_labels.get(key) or "").strip()
        tab_labels[key] = (val or fallback_label)[:40]

    sm_px = _clamp_int(src.get("thumb_sm_max_px"), 120, 600, DEFAULT_MEDIA_SETTINGS["thumb_sm_max_px"])
    md_px = _clamp_int(src.get("thumb_md_max_px"), max(sm_px, 400), 1600, DEFAULT_MEDIA_SETTINGS["thumb_md_max_px"])
    lg_px = _clamp_int(src.get("thumb_lg_max_px"), max(md_px, 1000), 3840, DEFAULT_MEDIA_SETTINGS["thumb_lg_max_px"])

    return {
        "max_file_size_mb": _clamp_int(
            src.get("max_file_size_mb"), 1, 500, DEFAULT_MEDIA_SETTINGS["max_file_size_mb"]
        ),
        "enforce_extension_whitelist": bool(
            src.get("enforce_extension_whitelist", DEFAULT_MEDIA_SETTINGS["enforce_extension_whitelist"])
        ),
        "allowed_extensions": _normalize_extensions(src.get("allowed_extensions")),
        "default_upload_tier_for_user": default_tier,
        "webp_quality": _clamp_int(
            src.get("webp_quality"), 40, 100, DEFAULT_MEDIA_SETTINGS["webp_quality"]
        ),
        "thumb_sm_max_px": sm_px,
        "thumb_md_max_px": md_px,
        "thumb_lg_max_px": lg_px,
        "publish_strip_image_original": bool(
            src.get("publish_strip_image_original", DEFAULT_MEDIA_SETTINGS["publish_strip_image_original"])
        ),
        "enable_original_auto_expiry": bool(
            src.get("enable_original_auto_expiry", DEFAULT_MEDIA_SETTINGS["enable_original_auto_expiry"])
        ),
        "original_keep_days": _clamp_int(
            src.get("original_keep_days"), 1, 3650, DEFAULT_MEDIA_SETTINGS["original_keep_days"]
        ),
        "isolation_retention_days": _clamp_int(
            src.get("isolation_retention_days"), 1, 365, DEFAULT_MEDIA_SETTINGS["isolation_retention_days"]
        ),
        "default_gc_indices": _normalize_gc_indices(src.get("default_gc_indices")),
        "shared_office_min_rank": _clamp_int(
            src.get("shared_office_min_rank"), 1, 9, DEFAULT_MEDIA_SETTINGS["shared_office_min_rank"]
        ),
        "shared_office_write_min_rank": _clamp_int(
            src.get("shared_office_write_min_rank"), 1, 9, DEFAULT_MEDIA_SETTINGS["shared_office_write_min_rank"]
        ),
        "protected_min_rank": _clamp_int(
            src.get("protected_min_rank"), 1, 9, DEFAULT_MEDIA_SETTINGS["protected_min_rank"]
        ),
        "system_serve_min_rank": _clamp_int(
            src.get("system_serve_min_rank"), 1, 9, DEFAULT_MEDIA_SETTINGS["system_serve_min_rank"]
        ),
        "zip_download_max_files": _clamp_int(
            src.get("zip_download_max_files"), 1, 500, DEFAULT_MEDIA_SETTINGS["zip_download_max_files"]
        ),
        "default_view_mode": view_mode,
        "default_recursive_view": bool(
            src.get("default_recursive_view", DEFAULT_MEDIA_SETTINGS["default_recursive_view"])
        ),
        "tab_labels": tab_labels,
    }


def get_media_settings(db: Session) -> Dict[str, Any]:
    """SystemConfig에서 미디어 관리 정책 설정을 조회합니다."""
    row = db.query(SystemConfig).filter(SystemConfig.key == MEDIA_SETTINGS_KEY).first()
    if row and isinstance(row.value, dict):
        return normalize_media_settings(row.value)
    return normalize_media_settings(DEFAULT_MEDIA_SETTINGS)


def update_media_settings(db: Session, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """미디어 관리 정책 설정을 검증·저장하고 (이전값, 신규값) 튜플을 반환합니다."""
    old_settings = get_media_settings(db)
    clean = normalize_media_settings(payload)
    row = db.query(SystemConfig).filter(SystemConfig.key == MEDIA_SETTINGS_KEY).first()
    if row:
        row.value = clean
    else:
        row = SystemConfig(
            key=MEDIA_SETTINGS_KEY,
            value=clean,
            description="미디어 자산·스토리지 통합 관리 정책 설정 (JSON)",
        )
        db.add(row)
    db.commit()
    return old_settings, clean


def get_thumb_specs_from_settings(settings: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """동적 설정값으로부터 SM / MD / LG 썸네일 생성 규격 사전을 구성합니다."""
    sm = int(settings.get("thumb_sm_max_px", 300))
    md = int(settings.get("thumb_md_max_px", 900))
    lg = int(settings.get("thumb_lg_max_px", 1920))
    return {
        "SM": {"size": (sm, sm), "suffix": "SM"},
        "MD": {"size": (md, md), "suffix": "MD"},
        "LG": {"size": (lg, lg), "suffix": "LG"},
    }


def check_is_media_admin(user: User, db: Session, action: str = "read") -> bool:
    """AppRegistry('media') 4단계 거버넌스 기반 미디어 관리자 권한 판별 (하드코딩 랭크 제거)"""
    if get_user_rank(user) == ROOT_RANK:
        return True
    app_meta = db.query(AppRegistry).filter(AppRegistry.app_id == "media").first()
    if not app_meta:
        app_meta = db.query(AppRegistry).filter(AppRegistry.app_id == "admin_media").first()
    if not app_meta:
        return get_user_rank(user) >= 4
    return can_access_app(user, app_meta, action=action)


def _normalize_clean_sub_path(sub_path: str) -> str:
    """상대 경로(../) 및 역슬래시를 정규화하고 상위 탈출 시도가 있으면 빈 문자열 대신 안전하게 차단합니다."""
    raw = (sub_path or "").replace("\\", "/").strip("/")
    if not raw:
        return ""
    norm = posixpath.normpath(raw)
    if norm in (".", "..") or norm.startswith("../") or "/../" in f"/{norm}/":
        return "__INVALID_TRAVERSAL__"
    return norm


def is_own_private_path(user: User, tier: str, sub_path: str) -> bool:
    """사용자가 본인의 개인 폴더(PRIVATE/USERS/{user.id})에 접근 중인지 검증 (../ 우회 차단)"""
    if (tier or "").upper() != "PRIVATE":
        return False
    clean = _normalize_clean_sub_path(sub_path)
    user_root = f"USERS/{user.id}"
    return clean == user_root or clean.startswith(f"{user_root}/")


def is_shared_office_path(tier: str, sub_path: str) -> bool:
    """전사 공용폴더(SYSTEM/GLOBAL/OFFICE) 경로 여부 판별 (../ 우회 차단)"""
    if (tier or "").upper() != "SYSTEM":
        return False
    clean = _normalize_clean_sub_path(sub_path)
    return clean == "GLOBAL/OFFICE" or clean.startswith("GLOBAL/OFFICE/")


def can_user_read_asset(
    user: User,
    asset: MediaAsset,
    db: Session,
    settings: Dict[str, Any] | None = None,
) -> bool:
    """미디어 자산 단일 열람/서빙/ZIP 포함 권한을 동적 정책 기준으로 판별합니다."""
    if check_is_media_admin(user, db, action="read"):
        return True
    cfg = settings or get_media_settings(db)
    lvl = (asset.access_level or "PUBLIC").upper()
    user_rank = get_user_rank(user)

    if lvl == "PUBLIC":
        return True
    if lvl == "PRIVATE":
        return asset.user_id == user.id
    if lvl == "PROTECTED":
        return user_rank >= int(cfg.get("protected_min_rank", 2))
    if lvl == "SYSTEM":
        return user_rank >= int(cfg.get("system_serve_min_rank", 2))
    return False


def validate_upload_permission(
    user: User,
    db: Session,
    target_tier: str,
    clean_sub_path: str,
    settings: Dict[str, Any] | None = None,
) -> None:
    """업로드 대상 Tier 및 경로에 대한 사용자 권한을 동적 정책 기준으로 검증합니다."""
    if check_is_media_admin(user, db, action="write"):
        return
    cfg = settings or get_media_settings(db)
    upper_tier = (target_tier or "PUBLIC").upper()
    user_rank = get_user_rank(user)

    if upper_tier == "SYSTEM":
        if is_shared_office_path("SYSTEM", clean_sub_path):
            min_w = int(cfg.get("shared_office_write_min_rank", 4))
            if user_rank >= min_w:
                return
        raise HTTPException(status_code=403, detail="해당 SYSTEM 경로에 업로드할 권한이 없습니다.")

    if upper_tier == "PRIVATE":
        if clean_sub_path and not is_own_private_path(user, "PRIVATE", clean_sub_path):
            raise HTTPException(status_code=403, detail="본인의 개인 폴더에만 업로드할 수 있습니다.")


def validate_upload_file_constraints(
    filename: str,
    content_size: int,
    settings: Dict[str, Any],
) -> None:
    """동적 설정(최대 용량 MB, 허용 확장자 화이트리스트) 기준으로 업로드 파일을 검증합니다."""
    max_mb = int(settings.get("max_file_size_mb", 100))
    max_bytes = max_mb * 1024 * 1024
    if content_size > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기 제한({max_mb}MB)을 초과했습니다: {filename}",
        )

    if settings.get("enforce_extension_whitelist", True):
        ext = os.path.splitext(filename or "")[1].lower()
        allowed = {e.lower() for e in settings.get("allowed_extensions", DEFAULT_ALLOWED_EXTENSIONS)}
        if not ext or ext not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"허용되지 않는 파일 확장자('{ext or '없음'}')입니다. 미디어 설정에서 허용 확장자를 확인해 주세요.",
            )
