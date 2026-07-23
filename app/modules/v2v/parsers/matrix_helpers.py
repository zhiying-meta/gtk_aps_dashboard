"""
Matrix helpers for horizontal continuous time axis + SKU/Line category filtering
Supports BOH, Plan Output, Plan Input, FCST
"""

import pandas as pd
from datetime import datetime, timedelta

# SKU categories as per user request
SKU_CATEGORIES = {
    "ALL": {"label": "All SKU", "filter": lambda x: True},
    "MATERIAL": {"label": "1- Material (3010*)", "filter": lambda s: str(s).startswith("3010")},
    "FRAME": {"label": "2- Frame (FR-*)", "filter": lambda s: str(s).startswith("FR-")},
    "GB": {"label": "3- GB (GB-*)", "filter": lambda s: str(s).startswith("GB-")},
    "LT": {"label": "4- LT (LT-*)", "filter": lambda s: str(s).startswith("LT-")},
    "RT": {"label": "5- RT (RT-*)", "filter": lambda s: str(s).startswith("RT-")},
    "FG": {"label": "6- FG (SK-*)", "filter": lambda s: str(s).startswith("SK-")},
}

# Line categories
LINE_CATEGORIES = {
    "ALL": {"label": "All Lines", "filter": lambda x: True},
    "AL1": {"label": "1- AL1 (AL1-*)", "filter": lambda s: str(s).startswith("AL1-") or str(s)== "AL1" or str(s).startswith("AL1")},
    "AL2": {"label": "2- AL2 (AL2-*)", "filter": lambda s: str(s).startswith("AL2-")},
    "AL3": {"label": "3- AL3 (AL3-*)", "filter": lambda s: str(s).startswith("AL3-")},
    "AL4": {"label": "4- AL4 (AL4-*)", "filter": lambda s: str(s).startswith("AL4-")},
    "AL5": {"label": "5- AL5 (AL5-*)", "filter": lambda s: str(s).startswith("AL5-")},
    "AL6": {"label": "6- AL6 (AL6-*)", "filter": lambda s: str(s).startswith("AL6-")},
    "AL7": {"label": "7- AL7 (AL7-*)", "filter": lambda s: str(s).startswith("AL7-")},
    "AL8": {"label": "8- AL8 (AL8-*)", "filter": lambda s: str(s).startswith("AL8-")},
    "AL9": {"label": "9- AL9 (AL9-*)", "filter": lambda s: str(s).startswith("AL9-")},
    "AL10": {"label": "10- AL10 (AL10-*)", "filter": lambda s: str(s).startswith("AL10-")},
    "ML2": {"label": "11- ML2 (ML2-*) Manual", "filter": lambda s: str(s).startswith("ML2-")},
    "ML5": {"label": "12- ML5 (ML5-*) Manual", "filter": lambda s: str(s).startswith("ML5-")},
}

def filter_sku_series(series, category):
    """Filter SKU list by category"""
    cat = (category or "ALL").upper()
    if cat not in SKU_CATEGORIES:
        # Try to handle direct prefix like FR-, GB- etc
        if cat.startswith("FR"):
            cat = "FRAME"
        elif cat.startswith("GB"):
            cat = "GB"
        elif cat.startswith("LT"):
            cat = "LT"
        elif cat.startswith("RT"):
            cat = "RT"
        elif cat.startswith("SK"):
            cat = "FG"
        elif cat.startswith("3010"):
            cat = "MATERIAL"
        else:
            cat = "ALL"
    f = SKU_CATEGORIES.get(cat, SKU_CATEGORIES["ALL"])["filter"]
    try:
        return [s for s in series if f(s)]
    except:
        return list(series)

def filter_line_series(series, category):
    cat = (category or "ALL").upper()
    if cat not in LINE_CATEGORIES:
        cat = "ALL"
    f = LINE_CATEGORIES.get(cat, LINE_CATEGORIES["ALL"])["filter"]
    try:
        return [s for s in series if f(s)]
    except:
        return list(series)

def _match_single_sku_category(value, cat):
    """Check if single SKU value matches single category"""
    v = str(value)
    cat_u = cat.upper()
    if cat_u in ["MATERIAL", "3010", "3010*"]:
        return v.startswith("3010")
    elif cat_u in ["FRAME", "FR", "FR-"]:
        return v.startswith("FR-")
    elif cat_u in ["GB", "GB-"]:
        return v.startswith("GB-")
    elif cat_u in ["LT", "LT-"]:
        return v.startswith("LT-")
    elif cat_u in ["RT", "RT-"]:
        return v.startswith("RT-")
    elif cat_u in ["FG", "SK", "SK-"]:
        return v.startswith("SK-")
    else:
        # Use mapped filter
        f = SKU_CATEGORIES.get(cat_u, SKU_CATEGORIES.get("ALL"))["filter"]
        try:
            return f(v)
        except:
            return False

def apply_sku_filter_df(df, sku_col, category):
    """Apply SKU category filter to DataFrame - supports multi-select comma separated like 'GB,FG'"""
    if not category or df.empty:
        return df
    cat_str = str(category).strip()
    if not cat_str or cat_str.upper() == "ALL":
        return df
    # Split by comma for multi-select
    cats = [c.strip() for c in cat_str.split(",") if c.strip()]
    if not cats:
        return df
    # If ALL is in list, no filter
    if any(c.upper() == "ALL" for c in cats):
        return df

    # Build mask with OR logic across categories
    def matches_any(val):
        for c in cats:
            if _match_single_sku_category(val, c):
                return True
        return False

    try:
        return df[df[sku_col].astype(str).apply(matches_any)]
    except Exception as e:
        print(f"SKU filter error: {e}")
        return df

def _match_single_line_category(value, cat):
    v = str(value)
    cat_u = cat.upper()
    prefix = cat_u.split("-")[0]
    # Match prefix exactly or prefix-
    return v.startswith(prefix+"-") or v == prefix or v.startswith(prefix)

def apply_line_filter_df(df, line_col, category):
    """Supports multi-select like 'AL1,AL2,ML2'"""
    if not category or df.empty:
        return df
    cat_str = str(category).strip()
    if not cat_str or cat_str.upper() == "ALL":
        return df
    if line_col not in df.columns:
        return df
    cats = [c.strip() for c in cat_str.split(",") if c.strip()]
    if not cats:
        return df
    if any(c.upper() == "ALL" for c in cats):
        return df

    def matches_any(val):
        for c in cats:
            if _match_single_line_category(val, c):
                return True
        return False

    try:
        return df[df[line_col].astype(str).apply(matches_any)]
    except Exception as e:
        print(f"Line filter error: {e}")
        return df

def to_saturday(dt):
    """Convert datetime to Saturday of that week (Sun-Sat week)"""
    if pd.isna(dt):
        return None
    dow = dt.weekday()
    delta = (5 - dow) % 7
    return dt + timedelta(days=delta)

def generate_continuous_weeks(min_date, max_date):
    """Generate continuous Saturdays between min and max date"""
    try:
        # Ensure min and max are datetime
        min_dt = pd.to_datetime(min_date)
        max_dt = pd.to_datetime(max_date)
        # Convert to Saturday
        # Find Saturday of min week
        min_sat = to_saturday(min_dt)
        max_sat = to_saturday(max_dt)
        # Generate range
        current = min_sat
        weeks = []
        while current <= max_sat:
            weeks.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=7)
        return weeks
    except Exception as e:
        print(f"Generate weeks error: {e}")
        return []

def generate_continuous_months(min_date, max_date):
    """Generate continuous months YYYY-MM between min and max"""
    try:
        min_dt = pd.to_datetime(min_date)
        max_dt = pd.to_datetime(max_date)
        # Start at first day of min month
        current = datetime(min_dt.year, min_dt.month, 1)
        end = datetime(max_dt.year, max_dt.month, 1)
        months = []
        while current <= end:
            months.append(current.strftime("%Y-%m"))
            # Next month
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
        return months
    except Exception as e:
        print(f"Generate months error: {e}")
        return []

def generate_continuous_days(min_date, max_date):
    try:
        min_dt = pd.to_datetime(min_date)
        max_dt = pd.to_datetime(max_date)
        current = min_dt
        days = []
        while current <= max_dt:
            days.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return days
    except Exception as e:
        print(f"Generate days error: {e}")
        return []

def generate_continuous_shifts(min_date, max_date, shift_names):
    """Generate continuous shift buckets: for each day, each shift"""
    try:
        days = generate_continuous_days(min_date, max_date)
        buckets = []
        for d in days:
            for shift in shift_names:
                buckets.append({"date": d, "shift": shift, "label": f"{d} {shift}"})
        return buckets
    except Exception as e:
        print(f"Generate shifts error: {e}")
        return []

def generate_time_buckets(df_a_norm, df_b_norm, granularity, shift_names=None):
    """
    Generate continuous time buckets based on granularity
    Returns list of bucket labels and helper for grouping
    """
    gran = (granularity or "week").lower()
    # Determine min and max date from both dataframes
    try:
        min_date = None
        max_date = None
        for df in [df_a_norm, df_b_norm]:
            if df.empty or "_DATE_DT" not in df.columns:
                continue
            # Drop NaT
            valid_dates = df["_DATE_DT"].dropna()
            if valid_dates.empty:
                continue
            cur_min = valid_dates.min()
            cur_max = valid_dates.max()
            if min_date is None or cur_min < min_date:
                min_date = cur_min
            if max_date is None or cur_max > max_date:
                max_date = cur_max

        # Fallback for FCST which uses _WEEK_DT
        if min_date is None:
            for df in [df_a_norm, df_b_norm]:
                if df.empty or "_WEEK_DT" not in df.columns:
                    continue
                valid = df["_WEEK_DT"].dropna()
                if valid.empty:
                    continue
                cur_min = valid.min()
                cur_max = valid.max()
                if min_date is None or cur_min < min_date:
                    min_date = cur_min
                if max_date is None or cur_max > max_date:
                    max_date = cur_max

        if min_date is None or max_date is None:
            return []

        if gran in ["week", "weekly"]:
            return generate_continuous_weeks(min_date, max_date)
        elif gran in ["month", "monthly"]:
            return generate_continuous_months(min_date, max_date)
        elif gran == "day" or gran == "daily":
            return generate_continuous_days(min_date, max_date)
        elif gran == "shift":
            if not shift_names:
                shift_names = ["白班", "夜班"]
            return generate_continuous_shifts(min_date, max_date, shift_names)
        else:
            return generate_continuous_weeks(min_date, max_date)
    except Exception as e:
        print(f"Generate time buckets error: {e}")
        import traceback; traceback.print_exc()
        return []
