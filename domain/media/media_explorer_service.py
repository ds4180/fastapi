"""
============================================================================
[미디어 탐색기·서빙·ZIP·격리 통합 서비스 (domain/media/media_explorer_service.py)]
============================================================================
- 6곳에 산재해 있던 UUID 추출·썸네일 경로 탐색·고화질 폴백·MIME 추론을 단일화하고,
- 디렉터리 스캔, 예약어 검증 폴더 생성, 일괄 격리 삭제, 스트리밍 ZIP 아카이빙,
  통계 집계 비즈니스 로직을 라우터로부터 완전히 분리합니다.
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, desc, func, not_
from sqlalchemy.orm import Session

from core.permission import get_user_rank
from domain.media import media_config as config
from domain.media import media_service
from domain.media.media_policy_service import (
    can_user_read_asset,
    check_is_media_admin,
    get_media_settings,
    is_own_private_path,
    is_shared_office_path,
)
from domain.system.task_service import enqueue_task
from models import MediaAsset, User

logger = logging.getLogger("media_explorer_service")

TIER_INTERNAL_MAP = {
    "PROTECTED": "/PROTECTED/",
    "PRIVATE": "/PRIVATE/",
    "SYSTEM": "/SYSTEM/",
}

EXT_CONTENT_TYPES = {
    "webp": "image/webp",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
    "mp4": "video/mp4",
    "zip": "application/zip",
}


def validate_safe_path(target_dir: str) -> None:
    """Path Traversal(../)을 통한 MEDIA_ROOT 외부 경로 이탈 원천 차단"""
    real_root = os.path.realpath(config.MEDIA_ROOT)
    real_target = os.path.realpath(target_dir)
    if not (real_target == real_root or real_target.startswith(real_root + os.sep)):
        raise HTTPException(status_code=400, detail="유효하지 않은 경로입니다 (Path traversal blocked).")


def extract_asset_uuid(file_path: str) -> str:
    """IMG_{uuid}.{EXT} 또는 일반 파일 경로에서 기준 식별자를 안전하게 추출합니다."""
    base_name = os.path.basename(file_path or "")
    stem = os.path.splitext(base_name)[0]
    if stem.startswith(config.PREFIX["IMAGE"]):
        return stem[len(config.PREFIX["IMAGE"]):]
    return stem


def resolve_existing_thumb_rel(asset: MediaAsset, size_key: str) -> Optional[str]:
    """
    요청한 해상도(SM / MD / LG)의 썸네일이 디스크에 실제 존재하는지
    표준 경로 -> meta_info 기록 -> 레거시 thumbnails 폴더 순으로 탐색해 상대 경로를 반환합니다.
    """
    size_upper = size_key.upper()
    size_lower = size_key.lower()
    dir_name = os.path.dirname(asset.file_path or "")
    unique_id = extract_asset_uuid(asset.file_path or "")

    # 1. 표준 THUMB/TMB_{uuid}_{SIZE}.WEBP 탐색
    std_name = f"{config.PREFIX['THUMB']}{unique_id}_{size_upper}.WEBP"
    std_rel = os.path.join(dir_name, config.THUMB_FOLDER_NAME, std_name).replace("\\", "/")
    if os.path.exists(os.path.join(config.MEDIA_ROOT, std_rel)):
        return std_rel

    # 2. DB meta_info.thumbs 탐색
    meta_thumbs = (asset.meta_info or {}).get("thumbs")
    if isinstance(meta_thumbs, dict):
        saved_rel = meta_thumbs.get(size_lower) or meta_thumbs.get(size_upper)
        if saved_rel and os.path.exists(os.path.join(config.MEDIA_ROOT, saved_rel)):
            return saved_rel.replace("\\", "/")

    # 3. 레거시 thumbnails/{uuid}_{size}.webp 탐색
    legacy_name = f"{unique_id}_{size_lower}.webp"
    legacy_rel = os.path.join(dir_name, config.LEGACY_THUMB_FOLDER_NAME, legacy_name).replace("\\", "/")
    if os.path.exists(os.path.join(config.MEDIA_ROOT, legacy_rel)):
        return legacy_rel

    return None


def resolve_best_fallback_abs(asset: MediaAsset) -> Tuple[Optional[str], str, bool]:
    """
    다운로드·백업·ZIP 압축 시 원본 파일이 존재하면 원본을,
    원본 부재(배포 복제본·60일 만료) 이미지라면 최고화질 썸네일(LG -> MD -> SM)을 반환합니다.
    반환값: (절대경로 | None, 권장 파일명, 폴백썸네일사용여부)
    """
    orig_abs = os.path.join(config.MEDIA_ROOT, asset.file_path)
    if os.path.exists(orig_abs):
        return orig_abs, asset.original_name, False

    if asset.category == config.MEDIA_CATEGORIES["IMAGE"]:
        for sz in ("LG", "MD", "SM"):
            thumb_rel = resolve_existing_thumb_rel(asset, sz)
            if thumb_rel:
                stem = os.path.splitext(asset.original_name or "")[0] or f"asset_{asset.id}"
                return os.path.join(config.MEDIA_ROOT, thumb_rel), f"{stem}.webp", True

    return None, asset.original_name, False


def guess_content_type(rel_path: str, fallback_mime: Optional[str] = None) -> str:
    ext = (rel_path.rsplit(".", 1)[-1] if "." in rel_path else "").lower()
    return EXT_CONTENT_TYPES.get(ext) or fallback_mime or "application/octet-stream"


def resolve_secure_serve_response(
    db: Session,
    asset: MediaAsset,
    size: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    보안 서빙(/media/serve/{id}) 대상의 Nginx X-Accel-Redirect 경로와 Content-Type을 계산합니다.
    서빙 가능한 파일이 없어 기본 썸네일로 리다이렉트해야 하면 (None, "")을 반환합니다.
    """
    target_rel_path = asset.file_path
    orig_abs_path = os.path.join(config.MEDIA_ROOT, asset.file_path)

    if not size and asset.category == config.MEDIA_CATEGORIES["IMAGE"]:
        has_no_orig = (asset.meta_info or {}).get("has_original") is False or not os.path.exists(orig_abs_path)
        if has_no_orig:
            fallback_rel = None
            for sz in ("LG", "MD", "SM"):
                fallback_rel = resolve_existing_thumb_rel(asset, sz)
                if fallback_rel:
                    break
            if not fallback_rel:
                return None, ""
            target_rel_path = fallback_rel

    elif size and size.upper() in ("SM", "MD", "LG"):
        found_rel = resolve_existing_thumb_rel(asset, size.upper())
        if found_rel:
            target_rel_path = found_rel
        else:
            if asset.is_deleted or not os.path.exists(orig_abs_path):
                return None, ""
            enqueue_task(db, "THUMB_GEN", {"asset_id": asset.id}, priority=2, unique_key=f"thumb-gen-{asset.id}")
            db.commit()
            return None, ""

    internal_prefix = TIER_INTERNAL_MAP.get(asset.access_level, "/PUBLIC/")
    parts = target_rel_path.split("/")
    path_without_tier = "/".join(parts[1:]) if parts and parts[0].upper() in config.MEDIA_TIERS else target_rel_path
    redirect_path = f"{internal_prefix}{path_without_tier}"
    content_type = guess_content_type(target_rel_path, asset.mime_type)
    return redirect_path, content_type


def is_protected_root_folder(upper_tier: str, clean_fpath: str) -> bool:
    """일괄 삭제(bulk-delete) 시 리네임 격리로부터 보호해야 하는 시스템 기준 루트 경로 판별"""
    if not clean_fpath:
        return True
    upper_path = clean_fpath.upper()
    if upper_tier == "SYSTEM" and upper_path in ("GLOBAL", "GLOBAL/OFFICE"):
        return True
    if upper_tier == "PRIVATE":
        parts = [p for p in upper_path.split("/") if p]
        if parts == ["USERS"] or (len(parts) == 2 and parts[0] == "USERS"):
            return True
    return False


def validate_folder_creation_name(folder_name: str, clean_sub_path: str) -> str:
    """폴더 생성 이름의 경로 문자·숨김 접두어·시스템 예약어 충돌 여부를 검증하고 정규화된 이름을 반환합니다."""
    clean_name = (folder_name or "").strip().strip("/")
    if not clean_name or "/" in clean_name or "\\" in clean_name or clean_name in (".", ".."):
        raise HTTPException(status_code=400, detail="유효하지 않은 폴더 이름입니다.")

    upper_name = clean_name.upper()
    if clean_name.startswith(".") or upper_name.startswith("DEL_"):
        raise HTTPException(
            status_code=400,
            detail="점(.) 또는 시스템 격리 예약어(DEL_)로 시작하는 폴더 이름은 사용할 수 없습니다.",
        )
    if upper_name in config.RESERVED_FOLDER_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"'{clean_name}'은(는) 시스템 예약 폴더명이므로 사용할 수 없습니다.",
        )
    if not clean_sub_path and upper_name in config.RESERVED_ROOT_SUBFOLDERS:
        raise HTTPException(
            status_code=400,
            detail=f"최상위 경로에서는 시스템 구조 예약 폴더('{clean_name}')를 수동 생성할 수 없습니다.",
        )
    return clean_name


def get_media_stats_summary(db: Session) -> Dict[str, object]:
    """전체 및 Tier별 활성 미디어 자산 통계 집계"""
    total_count = db.query(func.count(MediaAsset.id)).filter(MediaAsset.is_deleted == False).scalar() or 0
    total_size = db.query(func.sum(MediaAsset.file_size)).filter(MediaAsset.is_deleted == False).scalar() or 0

    tier_stats = (
        db.query(
            MediaAsset.access_level,
            func.count(MediaAsset.id),
            func.sum(MediaAsset.file_size),
        )
        .filter(MediaAsset.is_deleted == False)
        .group_by(MediaAsset.access_level)
        .all()
    )
    tier_summary = {row[0]: {"count": row[1], "size": row[2] or 0} for row in tier_stats}
    return {
        "total_count": total_count,
        "total_size_bytes": total_size,
        "tier_summary": tier_summary,
        "folder_physical_summary": {},
    }


def get_recent_media_by_tier(db: Session, limit: int = 12) -> Dict[str, List[MediaAsset]]:
    """하위 호환용 계층별 최근 미디어 목록"""
    recent: Dict[str, List[MediaAsset]] = {}
    for tier in ("PUBLIC", "PROTECTED", "PRIVATE", "SYSTEM"):
        recent[tier.lower()] = (
            db.query(MediaAsset)
            .filter(MediaAsset.access_level == tier, MediaAsset.is_deleted == False)
            .order_by(desc(MediaAsset.created_at))
            .limit(limit)
            .all()
        )
    return recent


def list_media_directory(
    db: Session,
    current_user: User,
    tier: str = "PUBLIC",
    sub_path: str = "",
    recursive: bool = True,
    show_hidden: bool = False,
) -> Dict[str, object]:
    """동적 정책 및 4단계 거버넌스를 반영하여 지정 디렉터리의 폴더와 자산 목록을 조회합니다."""
    settings = get_media_settings(db)
    upper_tier = (tier or "PUBLIC").upper()
    target_sub_path = (sub_path or "").strip("/")
    is_admin = check_is_media_admin(current_user, db, action="read")
    user_rank = get_user_rank(current_user)

    if not is_admin:
        if upper_tier == "PRIVATE":
            if not target_sub_path:
                target_sub_path = f"USERS/{current_user.id}"
            elif not is_own_private_path(current_user, "PRIVATE", target_sub_path):
                raise HTTPException(status_code=403, detail="본인의 개인 폴더만 조회할 수 있습니다.")
        elif upper_tier == "SYSTEM":
            min_office_rank = int(settings.get("shared_office_min_rank", 2))
            if user_rank < min_office_rank or not is_shared_office_path("SYSTEM", target_sub_path):
                raise HTTPException(status_code=403, detail="공용폴더 접근 권한이 없습니다.")
        elif upper_tier == "PROTECTED":
            if user_rank < int(settings.get("protected_min_rank", 2)):
                raise HTTPException(status_code=403, detail="사내 보안 자산 열람 권한이 없습니다.")
        elif upper_tier == "PUBLIC":
            if user_rank < 1:
                raise HTTPException(status_code=403, detail="로그인이 필요합니다.")
        else:
            raise HTTPException(status_code=403, detail="유효하지 않은 저장 계층입니다.")

    base_tier_folder = config.MEDIA_TIERS.get(upper_tier, "PUBLIC")
    target_dir = os.path.join(config.MEDIA_ROOT, base_tier_folder, target_sub_path)
    validate_safe_path(target_dir)

    if not os.path.exists(target_dir):
        media_service.safe_makedirs(target_dir)

    folders = []
    allow_hidden = is_admin and show_hidden
    try:
        with os.scandir(target_dir) as entries:
            for entry in entries:
                if entry.is_dir():
                    if entry.name.upper() in config.RESERVED_FOLDER_NAMES:
                        continue
                    is_dot_or_del = entry.name.startswith(".") or entry.name.upper().startswith("DEL_")
                    if not allow_hidden and is_dot_or_del:
                        continue
                    folders.append(
                        {
                            "name": entry.name,
                            "type": "folder",
                            "is_hidden": is_dot_or_del,
                            "path": os.path.join(target_sub_path, entry.name).strip("/"),
                        }
                    )
    except Exception as exc:
        logger.warning("미디어 디렉터리 스캔 실패 (%s): %s", target_dir, exc)

    search_prefix = f"{base_tier_folder}/{target_sub_path}".strip("/")
    if target_sub_path:
        search_prefix += "/"

    base_filter = [MediaAsset.access_level == upper_tier]
    if not allow_hidden:
        base_filter.extend(
            [
                MediaAsset.is_deleted == False,
                not_(MediaAsset.original_name.like(".%")),
                not_(MediaAsset.file_path.like("%/.%")),
            ]
        )

    if recursive:
        base_filter.append(MediaAsset.file_path.like(f"{search_prefix}%"))
    else:
        base_filter.append(
            and_(
                MediaAsset.file_path.like(f"{search_prefix}%"),
                not_(MediaAsset.file_path.like(f"{search_prefix}%/%")),
            )
        )

    all_files = db.query(MediaAsset).filter(*base_filter).order_by(desc(MediaAsset.created_at)).all()
    return {
        "tier": tier,
        "current_path": target_sub_path,
        "show_hidden": allow_hidden,
        "folders": sorted(folders, key=lambda x: x["name"]),
        "files": all_files,
    }


def create_media_folder(
    db: Session,
    current_user: User,
    tier: str,
    sub_path: str,
    folder_name: str,
) -> str:
    """예약어 및 동적 쓰기 권한을 검증한 뒤 새 물리 폴더를 생성하고 상대 경로를 반환합니다."""
    settings = get_media_settings(db)
    upper_tier = (tier or "PUBLIC").upper()
    clean_sub_path = (sub_path or "").strip("/")
    is_admin = check_is_media_admin(current_user, db, action="write")

    if not is_admin:
        if upper_tier == "PRIVATE":
            if not clean_sub_path:
                clean_sub_path = f"USERS/{current_user.id}"
            if not is_own_private_path(current_user, upper_tier, clean_sub_path):
                raise HTTPException(status_code=403, detail="본인의 개인 폴더에서만 새 폴더를 생성할 수 있습니다.")
        elif upper_tier == "SYSTEM" and is_shared_office_path("SYSTEM", clean_sub_path):
            if get_user_rank(current_user) < int(settings.get("shared_office_write_min_rank", 4)):
                raise HTTPException(status_code=403, detail="공용폴더에 새 폴더를 생성할 권한이 없습니다.")
        else:
            raise HTTPException(status_code=403, detail="해당 영역에 폴더를 생성할 권한이 없습니다.")

    clean_folder_name = validate_folder_creation_name(folder_name, clean_sub_path)
    base_tier_folder = config.MEDIA_TIERS.get(upper_tier, "PUBLIC")
    new_dir = os.path.join(config.MEDIA_ROOT, base_tier_folder, clean_sub_path, clean_folder_name)
    validate_safe_path(new_dir)

    if os.path.exists(new_dir):
        raise HTTPException(status_code=400, detail="동일한 이름의 폴더가 이미 존재합니다.")

    media_service.safe_makedirs(new_dir)
    return os.path.join(clean_sub_path, clean_folder_name).strip("/")


def bulk_delete_media(
    db: Session,
    current_user: User,
    tier: str,
    asset_ids: List[int],
    folder_paths: List[str],
) -> int:
    """파일 및 폴더 일괄 소프트 삭제·격리 (시스템 루트 보호 및 하위 파일 선행 동기 격리 포함)"""
    is_admin = check_is_media_admin(current_user, db, action="write")
    submitted_count = 0

    if asset_ids:
        for asset_id in asset_ids:
            asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id, MediaAsset.is_deleted == False).first()
            if not asset:
                continue
            if not is_admin and asset.user_id != current_user.id:
                continue
            if media_service.delete_asset(db, asset_id):
                submitted_count += 1

    if folder_paths:
        upper_tier = (tier or "PUBLIC").upper()
        base_tier_folder = config.MEDIA_TIERS.get(upper_tier, "PUBLIC")
        today_str = datetime.now().strftime("%Y%m%d")

        for fpath in folder_paths:
            clean_fpath = (fpath or "").strip("/")
            if is_protected_root_folder(upper_tier, clean_fpath):
                raise HTTPException(
                    status_code=400,
                    detail=f"시스템 기본 루트 폴더('{clean_fpath or upper_tier}') 자체는 삭제할 수 없습니다. 내부 파일이나 하위 폴더를 선택해 주세요.",
                )

            if not is_admin and not is_own_private_path(current_user, upper_tier, clean_fpath):
                continue

            db_prefix = f"{base_tier_folder}/{clean_fpath}/"
            assets = (
                db.query(MediaAsset)
                .filter(
                    MediaAsset.access_level == upper_tier,
                    MediaAsset.file_path.like(f"{db_prefix}%"),
                    MediaAsset.is_deleted == False,
                )
                .all()
            )

            for asset in assets:
                if media_service.delete_asset(db, asset.id, sync_isolate=True):
                    submitted_count += 1

            abs_folder = os.path.join(config.MEDIA_ROOT, base_tier_folder, clean_fpath)
            try:
                validate_safe_path(abs_folder)
                if os.path.isdir(abs_folder):
                    parent_dir = os.path.dirname(abs_folder)
                    folder_base = os.path.basename(abs_folder)
                    if not folder_base.startswith("."):
                        isolated_folder = os.path.join(
                            parent_dir, f"{config.PREFIX['DELETE']}{today_str}_{folder_base}"
                        )
                        if os.path.exists(isolated_folder):
                            suffix = 1
                            while os.path.exists(f"{isolated_folder}_{suffix}"):
                                suffix += 1
                            isolated_folder = f"{isolated_folder}_{suffix}"
                        os.rename(abs_folder, isolated_folder)
                        submitted_count += 1
            except Exception as exc:
                logger.error("폴더 격리 리네임 실패 (%s): %s", abs_folder, exc)

    return submitted_count


def build_media_zip_stream(
    db: Session,
    current_user: User,
    tier: str,
    asset_ids: List[int],
    folder_paths: List[str],
) -> Tuple[io.BytesIO, int]:
    """선택된 파일·폴더 자산을 정책 제한(zip_download_max_files) 및 권한 검증 후 인메모리 ZIP으로 생성합니다."""
    if not asset_ids and not folder_paths:
        raise HTTPException(status_code=400, detail="다운로드할 항목을 선택해 주세요.")

    settings = get_media_settings(db)
    max_files = int(settings.get("zip_download_max_files", 100))
    is_admin = check_is_media_admin(current_user, db, action="read")
    upper_tier = (tier or "PUBLIC").upper()
    base_tier_folder = config.MEDIA_TIERS.get(upper_tier, "PUBLIC")
    user_rank = get_user_rank(current_user)

    collected: Dict[int, Tuple[MediaAsset, str]] = {}

    if asset_ids:
        direct_assets = (
            db.query(MediaAsset)
            .filter(MediaAsset.id.in_(asset_ids), MediaAsset.is_deleted == False)
            .all()
        )
        for a in direct_assets:
            if can_user_read_asset(current_user, a, db, settings=settings):
                collected[a.id] = (a, "")

    if folder_paths:
        for fpath in folder_paths:
            clean_fpath = (fpath or "").strip("/")
            if not is_admin:
                if upper_tier == "PRIVATE" and not is_own_private_path(current_user, upper_tier, clean_fpath):
                    continue
                if upper_tier == "SYSTEM" and (
                    user_rank < int(settings.get("shared_office_min_rank", 2))
                    or not is_shared_office_path("SYSTEM", clean_fpath)
                ):
                    continue
                if upper_tier == "PROTECTED" and user_rank < int(settings.get("protected_min_rank", 2)):
                    continue

            db_prefix = f"{base_tier_folder}/{clean_fpath}/" if clean_fpath else f"{base_tier_folder}/"
            folder_base = os.path.basename(clean_fpath) or base_tier_folder
            folder_assets = (
                db.query(MediaAsset)
                .filter(
                    MediaAsset.access_level == upper_tier,
                    MediaAsset.file_path.like(f"{db_prefix}%"),
                    MediaAsset.is_deleted == False,
                )
                .all()
            )
            for a in folder_assets:
                if can_user_read_asset(current_user, a, db, settings=settings):
                    rel_inside = a.file_path[len(db_prefix):] if a.file_path.startswith(db_prefix) else ""
                    sub_dir = os.path.dirname(rel_inside)
                    arc_dir = os.path.join(folder_base, sub_dir).strip("/") if sub_dir else folder_base
                    collected[a.id] = (a, arc_dir)

    if not collected:
        raise HTTPException(status_code=404, detail="다운로드 가능한 파일이 없습니다.")

    if len(collected) > max_files:
        raise HTTPException(
            status_code=400,
            detail=f"1회 ZIP 다운로드 최대 파일 수({max_files}개)를 초과했습니다 (선택됨: {len(collected)}개). 미디어 설정에서 한도를 조정하거나 나누어 다운로드해 주세요.",
        )

    zip_buffer = io.BytesIO()
    used_arcnames = set()
    added_count = 0

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for asset, arc_dir in collected.values():
            abs_src, display_name, _ = resolve_best_fallback_abs(asset)
            if not abs_src:
                continue
            safe_name = os.path.basename(display_name) or f"file_{asset.id}"
            candidate = f"{arc_dir}/{safe_name}" if arc_dir else safe_name
            if candidate in used_arcnames:
                stem, ext = os.path.splitext(candidate)
                idx = 1
                while f"{stem}_{idx}{ext}" in used_arcnames:
                    idx += 1
                candidate = f"{stem}_{idx}{ext}"
            used_arcnames.add(candidate)
            zf.write(abs_src, arcname=candidate)
            added_count += 1

    if added_count == 0:
        raise HTTPException(status_code=404, detail="디스크에서 다운로드 가능한 물리 파일을 찾을 수 없습니다.")

    zip_buffer.seek(0)
    return zip_buffer, added_count
