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
import pickle
import hashlib
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
    try:
        # Try to read only needed columns to speed up (21M xlsx with 14 cols)
        needed = ["LINE_CODE", "PLAN_DATE", "SHIFT_NAME", "PLAN_TYPE", "PLAN_VALUE", "PLAN_ITEM"]
        try:
            df = pd.read_excel(path, sheet_name=0, engine='openpyxl', usecols=needed)
        except Exception:
            # Fallback: read all then filter (for files with different column names or extra spaces)
            df = pd.read_excel(path, sheet_name=0, engine='openpyxl')
    except EOFError as e:
        raise ValueError(f"Calendar file {path} is corrupted/truncated (EOFError). Please re-upload a valid xlsx. The file may have been incompletely uploaded (network interrupted) or is not a valid Excel. Original error: {e}")
    except Exception as e:
        err_str = str(e).lower()
        if "eof" in err_str or "truncated" in err_str or "not a zip file" in err_str or "badzipfile" in err_str or "file is not a zip file" in err_str:
            raise ValueError(f"Calendar file {path} is corrupted/invalid xlsx: {e}. Please re-upload. Ensure file is .xlsx (not .xls, not 0 bytes) and upload completed (check file size).")
        raise
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _load_schedule_df(path: str) -> pd.DataFrame:
    try:
        needed = ["LINE_CODE", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM", "PLAN_VALUE"]
        try:
            df = pd.read_excel(path, sheet_name=0, engine='openpyxl', usecols=needed)
        except Exception:
            df = pd.read_excel(path, sheet_name=0, engine='openpyxl')
    except EOFError as e:
        raise ValueError(f"Schedule file {path} is corrupted/truncated (EOFError). Please re-upload a valid xlsx. The file may have been incompletely uploaded. Original error: {e}")
    except Exception as e:
        err_str = str(e).lower()
        if "eof" in err_str or "truncated" in err_str or "not a zip file" in err_str or "badzipfile" in err_str or "file is not a zip file" in err_str:
            raise ValueError(f"Schedule file {path} is corrupted/invalid xlsx: {e}. Please re-upload. Ensure file is .xlsx and upload completed.")
        raise
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _norm_date_series(s: pd.Series) -> pd.Series:
    """Vectorized date normalization to YYYY-MM-DD, fallback to stripped string"""
    try:
        dt = pd.to_datetime(s, errors='coerce')
        normalized = dt.dt.strftime('%Y-%m-%d')
        # fallback for NaT
        mask = normalized.isna()
        if mask.any():
            # use original stripped string for those
            fallback = s.astype(str).str.strip()
            normalized = normalized.copy()
            normalized.loc[mask] = fallback.loc[mask]
        return normalized
    except Exception:
        # fallback slow path
        return s.apply(_norm_date)

def _build_calendar_map(calendar_df: pd.DataFrame) -> Dict[Tuple[str,str,str], Dict[str,float]]:
    """
    Returns dict key (line, date_str, shift) -> {UPH, 工时, 效率, 良率}
    Only PLAN_ITEM == INPUT
    Optimized: vectorized date norm + groupby last (faster than iterrows)
    """
    if 'PLAN_ITEM' in calendar_df.columns:
        df = calendar_df[calendar_df['PLAN_ITEM'] == 'INPUT']
    else:
        df = calendar_df

    if df.empty:
        return {}

    df = df.copy()
    # Vectorized normalization
    df['LINE_CODE'] = df['LINE_CODE'].astype(str).str.strip()
    df['SHIFT_NAME'] = df['SHIFT_NAME'].astype(str).str.strip()
    df['PLAN_TYPE'] = df['PLAN_TYPE'].astype(str).str.strip()
    df['PLAN_DATE_NORM'] = _norm_date_series(df['PLAN_DATE'])
    df['PLAN_VALUE'] = pd.to_numeric(df['PLAN_VALUE'], errors='coerce').fillna(0.0)

    # Group by 4 keys, take last value
    try:
        grouped_series = df.groupby(['LINE_CODE', 'PLAN_DATE_NORM', 'SHIFT_NAME', 'PLAN_TYPE'], sort=False)['PLAN_VALUE'].last()
    except Exception:
        # fallback to first if last fails
        grouped_series = df.groupby(['LINE_CODE', 'PLAN_DATE_NORM', 'SHIFT_NAME', 'PLAN_TYPE'])['PLAN_VALUE'].last()

    # Build dict of dicts
    from collections import defaultdict
    cal_map = defaultdict(dict)
    # grouped_series is Series with MultiIndex; iterate via items() is faster than iterrows
    for (line, date_norm, shift, ptype), val in grouped_series.items():
        try:
            fv = float(val)
        except:
            fv = 0.0
        cal_map[(line, date_norm, shift)][ptype] = fv

    return dict(cal_map)

def _build_load_map(schedule_df: pd.DataFrame) -> Dict[Tuple[str,str,str], float]:
    """
    Schedule load map: sum PLAN_VALUE per (line, date, shift) where INPUT
    Optimized via vectorized groupby sum
    """
    if 'PLAN_ITEM' in schedule_df.columns:
        df = schedule_df[schedule_df['PLAN_ITEM'] == 'INPUT']
    else:
        df = schedule_df

    if df.empty:
        return {}

    df = df.copy()
    df['LINE_CODE'] = df['LINE_CODE'].astype(str).str.strip()
    df['SHIFT_NAME'] = df['SHIFT_NAME'].astype(str).str.strip()
    df['PLAN_DATE_NORM'] = _norm_date_series(df['PLAN_DATE'])
    df['PLAN_VALUE'] = pd.to_numeric(df['PLAN_VALUE'], errors='coerce').fillna(0.0)

    try:
        load_series = df.groupby(['LINE_CODE', 'PLAN_DATE_NORM', 'SHIFT_NAME'], sort=False)['PLAN_VALUE'].sum()
    except Exception:
        load_series = df.groupby(['LINE_CODE', 'PLAN_DATE_NORM', 'SHIFT_NAME'])['PLAN_VALUE'].sum()

    # Convert to dict with tuple keys
    load_map = {}
    for (line, date_norm, shift), val in load_series.items():
        try:
            fv = float(val)
        except:
            fv = 0.0
        load_map[(line, date_norm, shift)] = fv
    return load_map

def _compute_records(version: str, calendar_path: str, schedule_path: str) -> UtilizationCache:
    # Try pickle fast path
    try:
        cached = _try_load_pickle(calendar_path, schedule_path, version)
        if cached:
            # print(f"[util] loaded from pickle {version}")
            return cached
    except Exception:
        pass

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
    # Save to pickle for fast future load
    try:
        _save_pickle(cache, calendar_path, schedule_path)
    except Exception as e:
        print(f"[util] save pickle failed {e}")
        pass
    return cache

def _get_pickle_path(calendar_path: str, schedule_path: str) -> str:
    # Pickle path next to calendar file: .cache.pkl
    try:
        cal_p = pathlib.Path(calendar_path)
        return str(cal_p.parent / f".cache_{cal_p.parent.name}_{hashlib.md5((calendar_path+schedule_path).encode()).hexdigest()[:8]}.pkl")
    except:
        return ""

def _try_load_pickle(calendar_path: str, schedule_path: str, version: str):
    pkl_path = pathlib.Path(calendar_path).parent / f"cache_{version}.pkl"
    # Also check generic pickle
    if not pkl_path.exists():
        # Try alternative naming
        alt = pathlib.Path(calendar_path).parent / ".cache.pkl"
        if alt.exists():
            pkl_path = alt
        else:
            return None

    # Check mtime
    try:
        cal_mtime = pathlib.Path(calendar_path).stat().st_mtime
        sched_mtime = pathlib.Path(schedule_path).stat().st_mtime
        pkl_mtime = pkl_path.stat().st_mtime
        if pkl_mtime < max(cal_mtime, sched_mtime):
            return None  # stale
        with open(pkl_path, 'rb') as f:
            data = pickle.load(f)
            # Validate version
            if getattr(data, 'version', None) == version:
                return data
    except Exception as e:
        # print(f"[util] pickle load failed {e}")
        return None
    return None

def _save_pickle(cache: UtilizationCache, calendar_path: str, schedule_path: str):
    try:
        pkl_path = pathlib.Path(calendar_path).parent / f"cache_{cache.version}.pkl"
        # Don't save raw dataframes to keep pickle small
        cache_copy = UtilizationCache(
            version=cache.version,
            records_shift=cache.records_shift,
            records_day=cache.records_day,
            lines=cache.lines,
            dates=cache.dates,
            shifts=cache.shifts,
            raw_calendar=None,
            raw_schedule=None,
        )
        with open(pkl_path, 'wb') as f:
            pickle.dump(cache_copy, f)
    except Exception as e:
        print(f"[util] pickle save failed {e}")

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

    if not calendar_path or not schedule_path:
        raise FileNotFoundError(f"Need calendar and schedule xlsx. Found calendar={calendar_path}, schedule={schedule_path} in {base_dir} version={version}. After clear, no fallback to IVY — matrix should be empty.")

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
    Try to load gated and ungated if available. Uses _CACHES for fast path, but also checks filesystem for missing versions.
    """
    global _CACHES
    result = {}
    base_path = pathlib.Path(base_dir)

    # Check cache first, but validate files still exist — if user manually deletes gated/ungated folders, cache should be invalidated
    # This fixes: manually clear gated and ungated, but matrix still shows other version with no actual data
    for k in list(_CACHES.keys()):
        if k.startswith(base_dir + "::"):
            ver = k.split("::")[-1]
            util_dir = base_path / "utilization" / ver
            cal = util_dir / "工作日历快照.xlsx"
            sched = util_dir / "排产结果表.xlsx"
            # If files missing (manual clear), remove from cache — becomes Not Ready
            if not (util_dir.exists() and cal.exists() and sched.exists()):
                _CACHES.pop(k, None)
                continue
            # Files exist, keep cache
            result[ver] = _CACHES[k]

    # Check explicit utilization folders for any missing versions — only check exact files, no fallback to IVY or rglob
    # After clear, folders will be empty, so result stays empty and matrix shows no values (as user expects)
    for ver in ['gated', 'ungated']:
        if ver in result:
            continue
        util_dir = base_path / "utilization" / ver
        if util_dir.exists():
            try:
                cal = util_dir / "工作日历快照.xlsx"
                sched = util_dir / "排产结果表.xlsx"
                if cal.exists() and sched.exists():
                    c = _compute_records(ver, str(cal), str(sched))
                    result[ver] = c
                    _CACHES[f"{base_dir}::{ver}"] = c
            except Exception:
                continue

    if result:
        return result

    # No fallback to IVY folders — after clear, should be truly empty (no values).
    # Demo must be explicitly loaded via /api/utilization/demo/load which copies IVY files into utilization/gated.
    # This ensures clear all results in empty matrix, as user expects.
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
