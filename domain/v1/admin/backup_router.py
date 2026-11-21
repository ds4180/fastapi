"""
============================================================================
[관리자 물리적 백업 프린트 라우터 (domain/v1/admin/backup_router.py)]
============================================================================

💡 역할:
- AppRegistry에 설치된 앱의 DB 모델 및 선택 가능한 컬럼 메타데이터 제공
- 기간별(상·하반기/사용자 지정) 또는 마지막 출력 이후 증분(CONTINUE) 데이터 조회
- 출력 이력(SystemConfig: backup_print_logs) 저장 및 조회
"""

from datetime import datetime, date, time
import hashlib
import io
import json
from typing import List, Optional, Dict, Any
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Date, DateTime
from sqlalchemy.orm import Session
import xlsxwriter

from database import get_db, Base
from core.deps import get_current_user
from core.audit import safe_log_audit
from models import (
    AppRegistry,
    BackupPrintLog,
    User,
    DayOff,
    Dispatch,
    RouteMaster,
    Post,
    Alert,
    AuditLog,
    MediaAsset,
    Page,
)

router = APIRouter(prefix="/v1/admin/backup", tags=["Admin Backup"])


def require_backup_admin(current_user: User = Depends(get_current_user)) -> User:
    rank = current_user.rank() if callable(getattr(current_user, "rank", None)) else 0
    if rank < 4:
        raise HTTPException(status_code=403, detail="백업 관리 권한이 없습니다. (Rank 4 이상)")
    return current_user


# 앱별 매핑 테이블 및 허용 필드 메타데이터 (민감 컬럼 제외)
BACKUP_APP_SPECS: Dict[str, Dict[str, Any]] = {
    "dayoff": {
        "model": DayOff,
        "date_field": "date",
        "is_datetime": False,
        "soft_delete": "is_deleted",
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "user_id", "label": "사원ID", "default": True},
            {"key": "date", "label": "휴무일", "default": True},
            {"key": "type", "label": "휴무유형", "default": True},
            {"key": "status", "label": "상태", "default": True},
            {"key": "memo", "label": "사유", "default": True},
            {"key": "group_id", "label": "묶음ID", "default": False},
            {"key": "create_date", "label": "신청일시", "default": True},
        ],
    },
    "dispatch": {
        "model": Dispatch,
        "date_field": "target_date",
        "is_datetime": False,
        "soft_delete": None,
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "target_date", "label": "배차일자", "default": True},
            {"key": "timetable_id", "label": "시간표ID", "default": False},
            {"key": "driver_name", "label": "기사명", "default": True},
            {"key": "vehicle_no", "label": "차량번호", "default": True},
            {"key": "start_time", "label": "출발시각", "default": True},
            {"key": "status", "label": "상태", "default": True},
            {"key": "memo", "label": "비고", "default": True},
        ],
    },
    "route_master": {
        "model": RouteMaster,
        "date_field": "start_date",
        "is_datetime": False,
        "soft_delete": None,
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "route_name", "label": "노선명", "default": True},
            {"key": "route_type", "label": "노선유형", "default": True},
            {"key": "start_date", "label": "적용시작일", "default": True},
            {"key": "end_date", "label": "적용종료일", "default": True},
            {"key": "vehicle_count", "label": "차량수", "default": True},
            {"key": "version", "label": "버전", "default": True},
            {"key": "is_regular_duty", "label": "당연근무", "default": False},
        ],
    },
    "board": {
        "model": Post,
        "date_field": "create_date",
        "is_datetime": True,
        "soft_delete": "is_deleted",
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "board_id", "label": "게시판ID", "default": True},
            {"key": "user_id", "label": "작성자ID", "default": True},
            {"key": "title", "label": "제목", "default": True},
            {"key": "status", "label": "상태", "default": True},
            {"key": "view_count", "label": "조회수", "default": False},
            {"key": "create_date", "label": "작성일시", "default": True},
            {"key": "modify_date", "label": "수정일시", "default": False},
        ],
    },
    "alerts": {
        "model": Alert,
        "date_field": "create_date",
        "is_datetime": True,
        "soft_delete": None,
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "category", "label": "분류", "default": True},
            {"key": "level", "label": "중요도", "default": True},
            {"key": "message", "label": "내용", "default": True},
            {"key": "target_group", "label": "대상그룹", "default": True},
            {"key": "is_active", "label": "활성여부", "default": True},
            {"key": "start_date", "label": "시작일시", "default": False},
            {"key": "end_date", "label": "종료일시", "default": False},
            {"key": "create_date", "label": "등록일시", "default": True},
        ],
    },
    "observability": {
        "model": AuditLog,
        "date_field": "created_at",
        "is_datetime": True,
        "soft_delete": None,
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "app_id", "label": "앱ID", "default": True},
            {"key": "log_type", "label": "유형", "default": True},
            {"key": "severity", "label": "심각도", "default": True},
            {"key": "action", "label": "액션", "default": True},
            {"key": "user_summary", "label": "수행자", "default": True},
            {"key": "title", "label": "제목", "default": True},
            {"key": "ip_address", "label": "IP주소", "default": False},
            {"key": "created_at", "label": "발생시각", "default": True},
        ],
    },
    "user_manage": {
        "model": User,
        "date_field": None,
        "is_datetime": False,
        "soft_delete": None,
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "username", "label": "아이디", "default": True},
            {"key": "real_name", "label": "실명", "default": True},
            {"key": "email", "label": "이메일", "default": True},
            {"key": "phone", "label": "연락처", "default": True},
        ],
    },
    "media": {
        "model": MediaAsset,
        "date_field": "created_at",
        "is_datetime": True,
        "soft_delete": "is_deleted",
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "app_id", "label": "앱ID", "default": True},
            {"key": "original_name", "label": "원본파일명", "default": True},
            {"key": "category", "label": "카테고리", "default": True},
            {"key": "mime_type", "label": "형식", "default": False},
            {"key": "file_size", "label": "크기(Byte)", "default": True},
            {"key": "access_level", "label": "접근권한", "default": True},
            {"key": "created_at", "label": "업로드일시", "default": True},
        ],
    },
    "page": {
        "model": Page,
        "date_field": "created_at",
        "is_datetime": True,
        "soft_delete": "is_deleted",
        "fields": [
            {"key": "id", "label": "ID", "default": True},
            {"key": "slug", "label": "슬러그", "default": True},
            {"key": "title", "label": "제목", "default": True},
            {"key": "status", "label": "상태", "default": True},
            {"key": "is_active", "label": "활성여부", "default": True},
            {"key": "view_count", "label": "조회수", "default": False},
            {"key": "published_at", "label": "게시일시", "default": False},
            {"key": "created_at", "label": "생성일시", "default": True},
        ],
    },
}


class PrintDataReq(BaseModel):
    app_id: str
    fields: List[str] = Field(default_factory=list)
    mode: str = "CUSTOM"  # CONTINUE | HALF_YEAR | CUSTOM
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = Field(default=1000, ge=1, le=5000)


class PrintLogCreateReq(BaseModel):
    app_id: str
    app_name: Optional[str] = None
    mode: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    last_record_id: Optional[int] = None
    last_seq_no: int = 0
    record_count: int = 0
    fields: List[str] = Field(default_factory=list)
    checksum: Optional[str] = None


def _log_to_dict(row: BackupPrintLog) -> Dict[str, Any]:
    return {
        "id": row.id,
        "app_id": row.app_id,
        "app_name": row.app_name or row.app_id,
        "mode": row.mode,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "last_record_id": row.last_record_id,
        "last_seq_no": row.last_seq_no,
        "record_count": row.record_count,
        "fields": list(row.fields or []),
        "checksum": row.checksum,
        "printed_by": row.printed_by,
        "printed_at": row.printed_at.strftime("%Y-%m-%d %H:%M:%S") if row.printed_at else None,
    }


def _load_print_logs(db: Session, app_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    q = db.query(BackupPrintLog)
    if app_id:
        q = q.filter(BackupPrintLog.app_id == app_id)
    rows = q.order_by(BackupPrintLog.id.desc()).limit(limit).all()
    return [_log_to_dict(r) for r in rows]


def _serialize_cell(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M")
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, bool):
        return "Y" if val else "N"
    raw = str(val)
    return raw


# 민감 컬럼 자동 제외 목록 (자동 테이블/컬럼 인식 시 보안 필터)
SENSITIVE_COLUMNS = {
    "hashed_password",
    "password",
    "password_hash",
    "secret",
    "secret_key",
    "private_key",
    "token",
    "access_token",
    "refresh_token",
    "jti",
    "salt",
    "p256dh",
    "auth",
    "auth_key",
    "totp_secret",
}

# 불규칙한 기존 앱 ID ↔ 테이블명 매핑 (신규 앱은 테이블명 자동 매칭)
APP_TABLE_ALIASES: Dict[str, str] = {
    "observability": "audit_logs",
    "audit_log": "audit_logs",
    "board": "post",
    "boards": "post",
    "media": "media_assets",
    "user_manage": "users",
    "group_manage": "groups",
    "tasks": "system_tasks",
    "config": "system_config",
    "apps": "app_registry",
    "services": "service_registry",
    "pushs": "push_subscription",
    "backup": "backup_print_logs",
    "blackbox": "blackbox_videos",
}

PREFERRED_DATE_COLUMNS = [
    "work_date",
    "date",
    "start_date",
    "published_at",
    "printed_at",
    "created_at",
    "updated_at",
]


def _get_table_model_map() -> Dict[str, Any]:
    """SQLAlchemy Base.registry에 등록된 모든 ORM 모델의 {table_name: ModelClass} 맵을 반환합니다."""
    table_map: Dict[str, Any] = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        tbl = getattr(cls, "__table__", None)
        if tbl is not None and tbl.name not in table_map:
            table_map[tbl.name] = cls
    return table_map


def _resolve_app_spec(app_id: str) -> Optional[Dict[str, Any]]:
    """
    app_id에 대응하는 백업 스펙(ORM 모델, 날짜 컬럼, 허용 필드)을 반환합니다.
    1) BACKUP_APP_SPECS에 큐레이션된 스펙이 있으면 한글 라벨/기본 선택/날짜 기준을 우선 적용하고,
       DB 테이블에 새로 추가된 일반 컬럼도 자동으로 병합합니다.
    2) BACKUP_APP_SPECS에 없는 앱도 AppRegistry app_id와 SQLAlchemy 테이블명을 자동 매칭해 지원합니다.
    """
    curated = BACKUP_APP_SPECS.get(app_id)
    table_map = _get_table_model_map()

    model_cls = curated["model"] if curated else None
    if model_cls is None:
        norm = (app_id or "").strip().lower().replace("-", "_")
        candidates = [
            APP_TABLE_ALIASES.get(norm, ""),
            norm,
            norm[:-1] if norm.endswith("s") else "",
            f"{norm}s",
        ]
        for cand in candidates:
            if cand and cand in table_map:
                model_cls = table_map[cand]
                break

    if model_cls is None:
        return None

    table = model_cls.__table__
    curated_fields = {f["key"]: f for f in (curated or {}).get("fields", [])}

    fields: List[Dict[str, Any]] = []
    # 1) 큐레이션 순서 우선 유지
    for f in (curated or {}).get("fields", []):
        if f["key"] in table.columns and f["key"].lower() not in SENSITIVE_COLUMNS:
            fields.append(dict(f))

    # 2) DB 테이블의 나머지 컬럼 자동 인식 (신규 컬럼/신규 앱)
    auto_default_budget = 6 if not curated else 0
    for col in table.columns:
        cname = col.name
        if cname in curated_fields or cname.lower() in SENSITIVE_COLUMNS:
            continue
        label = (col.comment or cname).strip()
        is_default = False
        if not curated and (cname == "id" or auto_default_budget > 0):
            is_default = True
            if cname != "id":
                auto_default_budget -= 1
        fields.append({"key": cname, "label": label, "default": is_default})

    if not fields:
        return None

    # 날짜 필터 컬럼 자동 탐지
    date_field = curated.get("date_field") if curated else None
    is_datetime = bool(curated.get("is_datetime")) if curated else False
    if not curated:
        for d_name in PREFERRED_DATE_COLUMNS:
            if d_name in table.columns and isinstance(table.columns[d_name].type, (Date, DateTime)):
                date_field = d_name
                is_datetime = isinstance(table.columns[d_name].type, DateTime)
                break
        if date_field is None:
            for col in table.columns:
                if isinstance(col.type, (Date, DateTime)):
                    date_field = col.name
                    is_datetime = isinstance(col.type, DateTime)
                    break

    soft_delete = curated.get("soft_delete") if curated else ("is_deleted" if "is_deleted" in table.columns else None)

    return {
        "model": model_cls,
        "date_field": date_field,
        "is_datetime": is_datetime,
        "soft_delete": soft_delete,
        "fields": fields,
    }


@router.get("/apps")
def get_backup_apps(
    db: Session = Depends(get_db),
    admin: User = Depends(require_backup_admin),
):
    """설치된 앱 중 백업 출력 가능한 앱과 DB 필드 목록, 최근 출력 이력을 반환합니다."""
    installed = db.query(AppRegistry).order_by(AppRegistry.app_id.asc()).all()
    logs = _load_print_logs(db)

    latest_by_app: Dict[str, Dict[str, Any]] = {}
    for entry in logs:
        aid = entry.get("app_id")
        if aid and aid not in latest_by_app:
            latest_by_app[aid] = entry

    apps = []
    for app_obj in installed:
        spec = _resolve_app_spec(app_obj.app_id)
        if not spec:
            continue
        apps.append({
            "app_id": app_obj.app_id,
            "name": app_obj.name or app_obj.app_id,
            "table_name": spec["model"].__table__.name,
            "has_date_filter": spec["date_field"] is not None,
            "date_field": spec["date_field"],
            "fields": spec["fields"],
            "last_log": latest_by_app.get(app_obj.app_id),
        })

    return {"apps": apps}


def _build_print_data(payload: PrintDataReq, db: Session) -> Dict[str, Any]:
    """선택한 앱, DB 필드, 기간/이어서 출력 조건에 맞춰 대장 출력용 표 데이터를 생성합니다."""
    spec = _resolve_app_spec(payload.app_id)
    if not spec:
        raise HTTPException(status_code=404, detail=f"지원되지 않는 앱입니다: {payload.app_id}")

    allowed_fields = {f["key"]: f["label"] for f in spec["fields"]}
    selected_keys = [k for k in payload.fields if k in allowed_fields]
    if not selected_keys:
        selected_keys = [f["key"] for f in spec["fields"] if f.get("default")]

    model_cls = spec["model"]
    query = db.query(model_cls)

    soft_del_col = spec.get("soft_delete")
    if soft_del_col and hasattr(model_cls, soft_del_col):
        query = query.filter(getattr(model_cls, soft_del_col) == False)

    logs = _load_print_logs(db)
    last_log = next((l for l in logs if l.get("app_id") == payload.app_id), None)

    mode = (payload.mode or "CUSTOM").upper()
    start_seq = 1

    if mode == "CONTINUE" and last_log:
        last_id = last_log.get("last_record_id")
        if last_id is not None:
            query = query.filter(model_cls.id > int(last_id))
        start_seq = int(last_log.get("last_seq_no") or 0) + 1
    elif spec["date_field"]:
        date_col = getattr(model_cls, spec["date_field"])
        if payload.start_date:
            s_d = date.fromisoformat(payload.start_date[:10])
            s_val = datetime.combine(s_d, time.min) if spec["is_datetime"] else s_d
            query = query.filter(date_col >= s_val)
        if payload.end_date:
            e_d = date.fromisoformat(payload.end_date[:10])
            e_val = datetime.combine(e_d, time.max) if spec["is_datetime"] else e_d
            query = query.filter(date_col <= e_val)

    rows_orm = query.order_by(model_cls.id.asc()).limit(payload.limit).all()

    columns = [{"key": k, "label": allowed_fields[k]} for k in selected_keys]
    rows: List[Dict[str, Any]] = []
    last_record_id = None

    for idx, r in enumerate(rows_orm):
        last_record_id = getattr(r, "id", None)
        row_dict: Dict[str, Any] = {"_seq": start_seq + idx}
        for k in selected_keys:
            row_dict[k] = _serialize_cell(getattr(r, k, None))
        rows.append(row_dict)

    raw_bytes = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(raw_bytes).hexdigest()[:16].upper()
    last_seq_no = (start_seq + len(rows) - 1) if rows else (start_seq - 1)

    return {
        "app_id": payload.app_id,
        "mode": mode,
        "columns": columns,
        "rows": rows,
        "record_count": len(rows),
        "start_seq": start_seq,
        "last_seq_no": last_seq_no,
        "last_record_id": last_record_id,
        "checksum": checksum,
        "last_log": last_log,
    }


@router.post("/print-data")
def fetch_backup_print_data(
    payload: PrintDataReq,
    db: Session = Depends(get_db),
    admin: User = Depends(require_backup_admin),
):
    """선택한 앱, DB 필드, 기간/이어서 출력 조건에 맞춰 대장 출력용 표 데이터를 조회합니다."""
    return _build_print_data(payload, db)


@router.post("/print-xlsx")
def export_backup_print_xlsx(
    payload: PrintDataReq,
    db: Session = Depends(get_db),
    admin: User = Depends(require_backup_admin),
):
    """선택한 앱, DB 필드, 기간/증분 조건에 맞춰 서식이 적용된 .xlsx 대장 파일을 스트리밍 다운로드합니다."""
    data = _build_print_data(payload, db)
    app_obj = db.query(AppRegistry).filter(AppRegistry.app_id == payload.app_id).first()
    app_name = (app_obj.name if app_obj and app_obj.name else payload.app_id)
    printed_by = getattr(admin, "real_name", None) or admin.username
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    worksheet = workbook.add_worksheet("백업대장")

    title_fmt = workbook.add_format({
        "bold": True, "font_size": 14, "font_color": "#0F172A", "valign": "vcenter"
    })
    meta_fmt = workbook.add_format({
        "font_size": 9, "font_color": "#475569", "valign": "vcenter"
    })
    header_fmt = workbook.add_format({
        "bold": True, "font_size": 10, "bg_color": "#F1F5F9", "font_color": "#0F172A",
        "border": 1, "align": "center", "valign": "vcenter"
    })
    seq_fmt = workbook.add_format({
        "font_size": 10, "border": 1, "align": "center", "valign": "vcenter"
    })
    cell_fmt = workbook.add_format({
        "font_size": 10, "border": 1, "valign": "vcenter"
    })

    cols = data["columns"]
    total_cols = max(1, len(cols) + 1)
    period_label = (
        f"마지막 출력 이후 증분 (#{data['start_seq']}~)"
        if data["mode"] == "CONTINUE"
        else f"{payload.start_date or '-'} ~ {payload.end_date or '-'}"
    )

    worksheet.set_row(0, 26)
    worksheet.merge_range(0, 0, 0, total_cols - 1, f"[공식 백업 대장] {app_name} ({payload.app_id})", title_fmt)
    worksheet.set_row(1, 20)
    worksheet.merge_range(
        1, 0, 1, total_cols - 1,
        f"조회조건: {period_label} | 총 {data['record_count']}건 | 출력일시: {now_str} | 발행자: {printed_by} | SHA-256: {data['checksum']}",
        meta_fmt,
    )

    header_row = 3
    worksheet.set_row(header_row, 22)
    worksheet.write(header_row, 0, "No.", header_fmt)
    col_widths = [8]
    for c_idx, col in enumerate(cols, start=1):
        label = str(col["label"])
        worksheet.write(header_row, c_idx, label, header_fmt)
        col_widths.append(max(12, len(label) * 2 + 4))

    for r_idx, row in enumerate(data["rows"], start=header_row + 1):
        worksheet.write(r_idx, 0, row.get("_seq"), seq_fmt)
        for c_idx, col in enumerate(cols, start=1):
            val = str(row.get(col["key"], ""))
            worksheet.write(r_idx, c_idx, val, cell_fmt)
            col_widths[c_idx] = min(48, max(col_widths[c_idx], len(val) + 4))

    for idx, width in enumerate(col_widths):
        worksheet.set_column(idx, idx, width)

    workbook.close()
    output.seek(0)

    filename = f"backup_{payload.app_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    encoded_name = quote(filename)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/print-logs")
def list_backup_print_logs(
    app_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_backup_admin),
):
    return {"logs": _load_print_logs(db, app_id=app_id)}


@router.post("/print-logs")
def create_backup_print_log(
    payload: PrintLogCreateReq,
    db: Session = Depends(get_db),
    admin: User = Depends(require_backup_admin),
):
    row = BackupPrintLog(
        app_id=payload.app_id,
        app_name=payload.app_name or payload.app_id,
        mode=payload.mode,
        start_date=payload.start_date,
        end_date=payload.end_date,
        last_record_id=payload.last_record_id,
        last_seq_no=payload.last_seq_no,
        record_count=payload.record_count,
        fields=payload.fields,
        checksum=payload.checksum,
        printed_by=getattr(admin, "real_name", None) or admin.username,
        printed_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    safe_log_audit(
        db=db,
        app_id=payload.app_id,
        log_type="CHANGE",
        action="BACKUP_PRINT_SAVED",
        title=f"[{payload.app_id}] 물리 백업 출력 확정 (제{row.id}호, {payload.record_count}건)",
        user=admin,
        resource_type="backup_print_log",
        resource_id=str(row.id),
        message=f"관리자 '{admin.username}'이(가) {payload.app_id} 백업 대장 {payload.record_count}건을 출력 확정했습니다. (마지막 ID: {payload.last_record_id})",
    )
    return {"message": "success", "log": _log_to_dict(row)}


@router.delete("/print-logs/{log_id}")
def delete_backup_print_log(
    log_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_backup_admin),
):
    """저장된 출력 이력(체크포인트)을 삭제합니다."""
    row = db.query(BackupPrintLog).filter(BackupPrintLog.id == log_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"출력 이력을 찾을 수 없습니다: {log_id}")

    app_id = row.app_id
    record_count = row.record_count
    db.delete(row)
    db.commit()

    safe_log_audit(
        db=db,
        app_id=app_id,
        log_type="CHANGE",
        action="BACKUP_PRINT_LOG_DELETED",
        title=f"[{app_id}] 물리 백업 체크포인트 삭제 (제{log_id}호)",
        user=admin,
        resource_type="backup_print_log",
        resource_id=str(log_id),
        message=f"관리자 '{admin.username}'이(가) {app_id} 백업 출력 이력(제{log_id}호, {record_count}건)을 삭제했습니다.",
    )
    return {"message": "deleted", "id": log_id}
