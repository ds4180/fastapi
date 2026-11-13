"""
[적용날짜 기준 레코드 선택 (core/effective.py)]

레코드를 수정하지 않고 적용날짜와 함께 추가만 한다.
조회 시 '적용날짜 <= 비교날짜' 인 레코드 중 가장 최근 것 1건을 사용한다.

예) [2026-08-01, 3], [2026-12-01, 5]
    pick(rows, date(2026, 11, 20)) -> [2026-08-01, 3]
    pick(rows, date(2026, 12, 5))  -> [2026-12-01, 5]
"""

from datetime import date, datetime


def _to_date(val):
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val[:10])
    return val


def _attr(record, key, default=None):
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def pick(records, as_of=None, field="effective_date"):
    """적용날짜(field) <= 비교날짜(as_of, 기본 오늘) 인 미삭제 레코드 중 가장 최근 것 1건 (없으면 None)"""
    target = _to_date(as_of) if as_of is not None else date.today()
    valid = []
    for idx, r in enumerate(records):
        if _attr(r, "is_deleted", False):
            continue
        raw_d = _attr(r, field)
        if raw_d is None:
            continue
        d_val = _to_date(raw_d)
        if d_val <= target:
            tie_id = _attr(r, "id", 0) or 0
            valid.append((d_val, tie_id, idx, r))
    if not valid:
        return None
    return max(valid, key=lambda item: (item[0], item[1], item[2]))[3]
