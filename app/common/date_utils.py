"""
Unified date parsing utilities - previously duplicated in 5 places
- plan_merge/engine.py
- plan_merge/utils.py
- v2v/utils.py
- io_report/engine.py
- utilization_report/engine.py
"""
from datetime import datetime, date, timedelta
from functools import lru_cache

# Unified date formats across all modules
DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y年%m月%d日",
    "%Y年%m月%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y%m%d",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
]

DOW_MAP = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def normalize_date_str(value) -> str:
    """Convert datetime or date-like string to 'YYYY-MM-DD' (or return as-is)."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if not isinstance(value, str):
        return str(value).strip() if value is not None else ""
    s = value.strip()
    if not s:
        return ""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


@lru_cache(maxsize=2048)
def to_dt(s: str) -> datetime:
    """Parse date string with multiple format support (cached)."""
    s = str(s).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {s}")


@lru_cache(maxsize=2048)
def to_saturday_label(ds: str) -> str:
    """Convert any date to Saturday of that week."""
    try:
        dt = to_dt(ds)
    except Exception:
        return ds
    dow = dt.weekday()
    sat = dt + timedelta(days=5 - dow)
    return sat.strftime("%Y-%m-%d")


@lru_cache(maxsize=4096)
def date_to_week_label_cached(ds: str, cut_day: str) -> str:
    """Map date to week label by cut day."""
    td = DOW_MAP.get(cut_day, 5)
    dt = to_dt(ds)
    cd = dt.weekday()
    diff = (td - cd) % 7
    week_end = dt + timedelta(days=diff)
    return to_saturday_label(week_end.strftime("%Y-%m-%d"))


def to_saturday(date_str: str) -> str:
    """Convert any date to Saturday of that week (week ending) - v2v compatible version."""
    try:
        dt = to_dt(date_str)
        dow = dt.weekday()
        delta = (5 - dow) % 7
        # For Sun-Sat week, Sun (6) -> +6 = correct
        from datetime import timedelta as _td
        sat = dt + _td(days=delta)
        return sat.strftime("%Y-%m-%d")
    except Exception:
        return str(date_str)


def clear_caches():
    """Clear all lru caches - for fresh upload handling."""
    to_dt.cache_clear()
    to_saturday_label.cache_clear()
    date_to_week_label_cached.cache_clear()
