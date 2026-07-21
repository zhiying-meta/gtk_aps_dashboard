"""
Utilization Report Engine
- Calendar: 工作日历快照.xlsx (LINE_CODE, PLAN_DATE, SHIFT_NAME, PLAN_TYPE=UPH/工时/效率, PLAN_VALUE, PLAN_ITEM=INPUT)
- Schedule: 排产结果表.xlsx (LINE_CODE, PLAN_DATE, SHIFT_NAME, PLAN_ITEM=INPUT, PLAN_VALUE)

For each LINE_CODE, PLAN_DATE, SHIFT_NAME:
  capacity = UPH * efficiency * working_hours
  load = sum(schedule INPUT qty)
  utilization = load / capacity (if capacity>0)

Supports gated / ungated versions stored separately.
"""

import os
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import pandas as pd

@dataclass
class UtilizationRecord:
    line_code: str
    plan_date: str  # YYYY/M/D or YYYY-MM-DD normalized to YYYY-MM-DD
    shift_name: str
    uph: float
    efficiency: float
    working_hours: float
    capacity: float
    load: float
    utilization: float  # 0-1+

@dataclass
class UtilizationCache:
    version: str  # gated / ungated
    records_shift: List[Dict] = field(default_factory=list)  # per shift
    records_day: List[Dict] = field(default_factory=list)    # per day aggregated
    lines: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    shifts: List[str] = field(default_factory=list)
    raw_calendar: pd.DataFrame = None
    raw_schedule: pd.DataFrame = None

# Global caches per version
_CACHES: Dict[str, UtilizationCache] = {}
_BASE_DATA_DIR = None

def _norm_date(s):
    if pd.isna(s):
        return ""
    try:
        # pandas can parse
        dt = pd.to_datetime(s)
        return dt.strftime("%Y-%m-%d")
    except:
        return str(s).strip()

def _load_calendar_df(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0, engine='openpyxl')
    # Expected columns
    needed = {'LINE_CODE','PLAN_DATE','SHIFT_NAME','PLAN_TYPE','PLAN_VALUE','PLAN_ITEM'}
    cols = set(df.columns.astype(str))
    # Normalize column names (strip)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _load_schedule_df(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0, engine='openpyxl')
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _build_calendar_map(calendar_df: pd.DataFrame) -> Dict[Tuple[str,str,str], Dict[str,float]]:
    """
    Returns dict key (line, date_str, shift) -> {UPH, 工时, 效率, 良率}
    Only PLAN_ITEM == INPUT
    """
    # Filter INPUT
    if 'PLAN_ITEM' in calendar_df.columns:
        df = calendar_df[calendar_df['PLAN_ITEM'] == 'INPUT']
    else:
        df = calendar_df

    # Normalize dates
    df = df.copy()
    df['PLAN_DATE_NORM'] = df['PLAN_DATE'].apply(_norm_date)
    # Group by line, date_norm, shift, PLAN_TYPE -> take last PLAN_VALUE (or max? Use last)
    # Some duplicates may exist, take last
    grouped = {}
    for _, row in df.iterrows():
        key = (str(row['LINE_CODE']).strip(), row['PLAN_DATE_NORM'], str(row['SHIFT_NAME']).strip())
        ptype = str(row['PLAN_TYPE']).strip()
        try:
            val = float(row['PLAN_VALUE'])
        except:
            val = 0.0
        if key not in grouped:
            grouped[key] = {}
        # If duplicate, keep last (overwrite)
        grouped[key][ptype] = val
    return grouped

def _build_load_map(schedule_df: pd.DataFrame) -> Dict[Tuple[str,str,str], float]:
    """
    schedule_df columns: LINE_CODE, PLAN_DATE, SHIFT_NAME, PLAN_ITEM, PLAN_VALUE
    Sum where PLAN_ITEM == INPUT (or also OUTPUT? spec says input)
    """
    # Filter INPUT
    if 'PLAN_ITEM' in schedule_df.columns:
        # Some data uses INPUT only
        df = schedule_df[schedule_df['PLAN_ITEM'] == 'INPUT']
    else:
        df = schedule_df

    df = df.copy()
    df['PLAN_DATE_NORM'] = df['PLAN_DATE'].apply(_norm_date)
    load_map = {}
    for _, row in df.iterrows():
        key = (str(row['LINE_CODE']).strip(), row['PLAN_DATE_NORM'], str(row['SHIFT_NAME']).strip())
        try:
            val = float(row['PLAN_VALUE'])
        except:
            val = 0.0
        load_map[key] = load_map.get(key, 0.0) + val
    return load_map

def _compute_records(version: str, calendar_path: str, schedule_path: str) -> UtilizationCache:
    cal_df = _load_calendar_df(calendar_path)
    sched_df = _load_schedule_df(schedule_path)

    cal_map = _build_calendar_map(cal_df)
    load_map = _build_load_map(sched_df)

    # Union of keys
    all_keys = set(cal_map.keys()) | set(load_map.keys())

    records_shift = []
    # For daily aggregation
    daily_agg = {}  # (line, date) -> {capacity_sum, load_sum, details}

    lines_set = set()
    dates_set = set()
    shifts_set = set()

    for key in all_keys:
        line, date_norm, shift = key
        lines_set.add(line)
        dates_set.add(date_norm)
        shifts_set.add(shift)

        cal = cal_map.get(key, {})
        uph = cal.get('UPH', 0.0) or cal.get('uph', 0.0)
        eff = cal.get('效率', 0.0)
        wh = cal.get('工时', 0.0)
        # If missing, try 0
        try:
            uph = float(uph)
        except:
            uph = 0.0
        try:
            eff = float(eff)
        except:
            eff = 0.0
        try:
            wh = float(wh)
        except:
            wh = 0.0

        capacity = uph * eff * wh
        load = load_map.get(key, 0.0)
        util = load / capacity if capacity > 0 else 0.0

        # Raw utilization (may exceed 1.0 if overloaded)
        util_pct_raw = round(util*100, 2)
        # Capped at 100 for theoretical 0-100% range (overload shown as 100% with flag)
        util_pct_capped = min(100.0, util_pct_raw) if util_pct_raw is not None else 0
        rec = {
            'line_code': line,
            'plan_date': date_norm,
            'shift_name': shift,
            'uph': uph,
            'efficiency': eff,
            'working_hours': wh,
            'capacity': capacity,
            'load': load,
            'utilization': util,
            'utilization_pct': util_pct_raw,
            'utilization_pct_capped': util_pct_capped,
            'is_overload': util_pct_raw > 100.0,
        }
        records_shift.append(rec)

        # Daily agg
        dkey = (line, date_norm)
        if dkey not in daily_agg:
            daily_agg[dkey] = {'capacity': 0.0, 'load': 0.0, 'uphs': [], 'effs': [], 'whs': [], 'shifts': []}
        daily_agg[dkey]['capacity'] += capacity
        daily_agg[dkey]['load'] += load
        daily_agg[dkey]['uphs'].append(uph)
        daily_agg[dkey]['effs'].append(eff)
        daily_agg[dkey]['whs'].append(wh)
        daily_agg[dkey]['shifts'].append(shift)

    # Build daily records
    records_day = []
    for (line, date_norm), agg in daily_agg.items():
        cap = agg['capacity']
        load = agg['load']
        util = load / cap if cap > 0 else 0.0
        # Avg UPH / eff / wh weighted? Simple avg
        avg_uph = sum(agg['uphs'])/len(agg['uphs']) if agg['uphs'] else 0
        avg_eff = sum(agg['effs'])/len(agg['effs']) if agg['effs'] else 0
        sum_wh = sum(agg['whs'])
        util_pct_raw = round(util*100, 2)
        util_pct_capped = min(100.0, util_pct_raw)
        records_day.append({
            'line_code': line,
            'plan_date': date_norm,
            'shift_name': 'DAY',
            'uph': avg_uph,
            'efficiency': avg_eff,
            'working_hours': sum_wh,
            'capacity': cap,
            'load': load,
            'utilization': util,
            'utilization_pct': util_pct_raw,
            'utilization_pct_capped': util_pct_capped,
            'is_overload': util_pct_raw > 100.0,
            'shift_count': len(agg['shifts']),
        })

    # Sort
    records_shift.sort(key=lambda x: (x['line_code'], x['plan_date'], x['shift_name']))
    records_day.sort(key=lambda x: (x['line_code'], x['plan_date']))

    cache = UtilizationCache(
        version=version,
        records_shift=records_shift,
        records_day=records_day,
        lines=sorted(list(lines_set)),
        dates=sorted(list(dates_set)),
        shifts=sorted(list(shifts_set)),
        raw_calendar=cal_df,
        raw_schedule=sched_df,
    )
    return cache

def load_data_for_version(base_dir: str, version: str) -> UtilizationCache:
    """
    base_dir contains files: working calendar and schedule
    Expect files named like: 工作日历快照.xlsx and 排产结果表.xlsx OR calendar.xlsx / schedule.xlsx
    We'll search.
    base_dir/version folder if version subfolder exists, else base_dir itself.
    """
    base_path = pathlib.Path(base_dir)
    # Try version subfolder
    candidate_dirs = [
        base_path / version,
        base_path / f"utilization_{version}",
        base_path,
    ]
    # Also try IVY style folders
    # Search inside base_path for files
    calendar_path = None
    schedule_path = None

    for d in candidate_dirs:
        if not d.exists():
            continue
        # List xlsx files
        for f in d.glob("*.xlsx"):
            name = f.name.lower()
            if "工作日历" in f.name or "calendar" in name or "工作日历" in name:
                calendar_path = str(f)
            elif "排产结果" in f.name or "schedule" in name or "排产" in f.name:
                # Ensure not combined
                if calendar_path is None or "工作日历" not in f.name:
                    # heuristic: if file contains both words? prefer schedule
                    if "排产结果" in f.name or "schedule" in name:
                        schedule_path = str(f)
        # Also check inside if folder contains the two specific names
        if calendar_path and schedule_path:
            break

    # Fallback: search recursively for exact filenames (first)
    if not calendar_path or not schedule_path:
        # Search for 工作日历快照.xlsx and 排产结果表.xlsx in base_path
        for f in base_path.rglob("工作日历快照.xlsx"):
            calendar_path = str(f)
            break
        for f in base_path.rglob("排产结果表.xlsx"):
            # Take one that is in same parent as calendar if possible
            if calendar_path and pathlib.Path(f).parent == pathlib.Path(calendar_path).parent:
                schedule_path = str(f)
                break
        if not schedule_path:
            for f in base_path.rglob("排产结果表.xlsx"):
                schedule_path = str(f)
                break

    if not calendar_path or not schedule_path:
        raise FileNotFoundError(f"Need calendar and schedule xlsx. Found calendar={calendar_path}, schedule={schedule_path} in {base_dir} version={version}")

    return _compute_records(version, calendar_path, schedule_path)

def get_cache_for_version(base_dir: str, version: str) -> UtilizationCache:
    global _CACHES, _BASE_DATA_DIR
    key = f"{base_dir}::{version}"
    if key in _CACHES:
        return _CACHES[key]
    cache = load_data_for_version(base_dir, version)
    _CACHES[key] = cache
    _BASE_DATA_DIR = base_dir
    return cache

def get_all_caches(base_dir: str) -> Dict[str, UtilizationCache]:
    """
    Try to load gated and ungated if available. Uses _CACHES for fast path.
    """
    global _CACHES
    # Fast path: return cached if we have any for this base_dir
    cached = {}
    for k, v in _CACHES.items():
        if k.startswith(base_dir + "::"):
            ver = k.split("::")[-1]
            cached[ver] = v
    if cached:
        return cached

    result = {}
    base_path = pathlib.Path(base_dir)

    # First, try explicit utilization folders
    for ver in ['gated', 'ungated']:
        util_dir = base_path / "utilization" / ver
        if util_dir.exists():
            try:
                cal = util_dir / "工作日历快照.xlsx"
                sched = util_dir / "排产结果表.xlsx"
                if cal.exists() and sched.exists():
                    c = _compute_records(ver, str(cal), str(sched))
                    result[ver] = c
                    _CACHES[f"{base_dir}::{ver}"] = c
                else:
                    try:
                        c = load_data_for_version(str(util_dir), ver)
                        result[ver] = c
                        _CACHES[f"{base_dir}::{ver}"] = c
                    except:
                        pass
            except Exception:
                continue

    if not result:
        # Try generic search: look for data/IVY*Gated folder as gated only
        for sub in base_path.iterdir():
            if sub.is_dir() and ('Gated' in sub.name or 'gated' in sub.name.lower()):
                try:
                    cal = sub / "工作日历快照.xlsx"
                    sched = sub / "排产结果表.xlsx"
                    if cal.exists() and sched.exists():
                        c = _compute_records('gated', str(cal), str(sched))
                        result['gated'] = c
                        _CACHES[f"{base_dir}::gated"] = c
                        break
                except:
                    continue

    if not result:
        # Last fallback: scan for first pair anywhere under base_dir (limit to data/IVY* to avoid scanning entire data)
        # Only search one level deep for speed: look for IVY folders
        candidates = []
        for sub in base_path.iterdir():
            if sub.is_dir():
                cal = sub / "工作日历快照.xlsx"
                sched = sub / "排产结果表.xlsx"
                if cal.exists() and sched.exists():
                    candidates.append((cal, sched))
        # If still none, do limited rglob (first match)
        if not candidates:
            for cal_path in base_path.rglob("工作日历快照.xlsx"):
                sched_path = cal_path.parent / "排产结果表.xlsx"
                if sched_path.exists():
                    candidates.append((cal_path, sched_path))
                    break
                if len(candidates) >= 1:
                    break
        for cal_path, sched_path in candidates[:1]:
            try:
                c = _compute_records('gated', str(cal_path), str(sched_path))
                result['gated'] = c
                _CACHES[f"{base_dir}::gated"] = c
                break
            except Exception as e:
                print(f"[util] fallback load failed for {cal_path}: {e}")
                continue

    return result

def reload_all(base_dir: str):
    global _CACHES
    _CACHES.clear()
    return get_all_caches(base_dir)

def get_status(base_dir: str):
    caches = get_all_caches(base_dir)
    status = {}
    for ver, cache in caches.items():
        status[ver] = {
            'lines': len(cache.lines),
            'dates': len(cache.dates),
            'shifts': len(cache.shifts),
            'records_shift': len(cache.records_shift),
            'records_day': len(cache.records_day),
        }
    return status

def build_report(version_cache: UtilizationCache, mode: str = "shift", line_filter: str = "", date_from: str = "", date_to: str = "", shift_filter: str = "") -> List[Dict]:
    """
    mode: shift or day
    """
    recs = version_cache.records_shift if mode == "shift" else version_cache.records_day
    filtered = []
    for r in recs:
        if line_filter and line_filter.lower() not in r['line_code'].lower():
            continue
        if shift_filter and mode == "shift" and shift_filter != r['shift_name']:
            continue
        if date_from and r['plan_date'] < date_from:
            continue
        if date_to and r['plan_date'] > date_to:
            continue
        filtered.append(r)
    return filtered

def build_compare_report(gated_cache: UtilizationCache, ungated_cache: UtilizationCache, mode: str = "shift", **filters) -> List[Dict]:
    """
    Build comparison: for same line/date/shift, show gated vs ungated utilization
    """
    gated_recs = build_report(gated_cache, mode, **filters)
    ungated_map = {(r['line_code'], r['plan_date'], r.get('shift_name','')): r for r in build_report(ungated_cache, mode, **filters)}

    result = []
    for g in gated_recs:
        key = (g['line_code'], g['plan_date'], g.get('shift_name',''))
        u = ungated_map.get(key)
        if u:
            result.append({
                **g,
                'gated_utilization': g['utilization'],
                'gated_utilization_pct': g['utilization_pct'],
                'gated_load': g['load'],
                'gated_capacity': g['capacity'],
                'ungated_utilization': u['utilization'],
                'ungated_utilization_pct': u['utilization_pct'],
                'ungated_load': u['load'],
                'ungated_capacity': u['capacity'],
                'delta_utilization': round((g['utilization'] - u['utilization'])*100, 2),
                'delta_load': g['load'] - u['load'],
            })
        else:
            result.append({
                **g,
                'gated_utilization': g['utilization'],
                'gated_utilization_pct': g['utilization_pct'],
                'gated_load': g['load'],
                'gated_capacity': g['capacity'],
                'ungated_utilization': None,
                'ungated_utilization_pct': None,
                'ungated_load': None,
                'ungated_capacity': None,
                'delta_utilization': None,
                'delta_load': None,
            })
    return result
