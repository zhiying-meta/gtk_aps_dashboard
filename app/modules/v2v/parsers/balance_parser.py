"""
BOH (Balance) parser - 结存表_输出 - Renamed to BOH
SKU level comparison: ITEM_CODE + Time (granularity determines time bucket)
For BOH, we use LAST value per group (not sum), as inventory snapshot.
Supports: day, week, month/monthly, shift
Default only_diff=True, fixed SKU level.
Optimized for performance: vectorized date handling, minimal columns.
"""

import pandas as pd
from datetime import timedelta
import numpy as np

def parse_balance(file_path: str):
    df = pd.read_excel(file_path)
    return df

def to_saturday_dt(series):
    """Vectorized conversion to Saturday of week Sun-Sat"""
    # series is datetime
    # weekday Mon=0..Sun=6, Saturday=5, Sunday=6 -> delta to Saturday = (5 - weekday) %7
    # For Sun (6) -> 6 days to next Saturday (which is week ending)
    try:
        dow = series.dt.weekday
        delta = (5 - dow) % 7
        # For Sunday, delta=6 => Saturday 6 days later (week ending)
        return series + pd.to_timedelta(delta, unit='D')
    except:
        return series

def normalize_dates(df):
    """Optimized normalization: only create needed columns, handle NaT safely"""
    if df.empty:
        df["_DATE_DT"] = pd.Series(dtype='datetime64[ns]')
        df["_DATE"] = pd.Series(dtype='object')
        df["_WEEK"] = pd.Series(dtype='object')
        df["_MONTH"] = pd.Series(dtype='object')
        df["_SHIFT_ORDER"] = pd.Series(dtype='int')
        return df

    df = df.copy()
    # Convert PLAN_DATE to datetime, coerce errors to NaT, then drop NaT for grouping? Keep but will filter later
    df["_DATE_DT"] = pd.to_datetime(df["PLAN_DATE"], errors='coerce')
    # Drop rows where date is NaT - they cannot be grouped meaningfully and cause NaT errors
    df = df[~df["_DATE_DT"].isna()]
    if df.empty:
        df["_DATE"] = pd.Series(dtype='object')
        df["_WEEK"] = pd.Series(dtype='object')
        df["_MONTH"] = pd.Series(dtype='object')
        df["_SHIFT_ORDER"] = pd.Series(dtype='int')
        return df

    df["_DATE"] = df["_DATE_DT"].dt.strftime("%Y-%m-%d")
    # Week: Saturday ending
    week_dt = to_saturday_dt(df["_DATE_DT"])
    # Convert week_dt to string, handle NaT
    df["_WEEK"] = week_dt.dt.strftime("%Y-%m-%d")
    df["_MONTH"] = df["_DATE_DT"].dt.strftime("%Y-%m")

    # Shift order for last value
    if "SHIFT_CODE" in df.columns:
        df["_SHIFT_ORDER"] = pd.to_numeric(df["SHIFT_CODE"], errors='coerce').fillna(1)
    else:
        # Map SHIFT_NAME
        mapping = {"白班": 1, "夜班": 2}
        if "SHIFT_NAME" in df.columns:
            df["_SHIFT_ORDER"] = df["SHIFT_NAME"].map(mapping).fillna(1)
        else:
            df["_SHIFT_ORDER"] = 1

    # Ensure ITEM_CODE exists
    if "ITEM_CODE" not in df.columns:
        # Try SKU column as fallback
        for col in ["SKU", "PN_CODE", "ITEM_NO"]:
            if col in df.columns:
                df["ITEM_CODE"] = df[col]
                break
    return df

def apply_filters(df, filters):
    if not filters or df.empty:
        return df
    df = df.copy()
    for key, val in filters.items():
        if val is None or val == "" or df.empty:
            continue
        key_upper = key.upper()
        if key_upper in ["WEEK", "_WEEK"]:
            if "_WEEK" in df.columns:
                df = df[df["_WEEK"] == val]
        elif key_upper in ["DATE", "PLAN_DATE", "_DATE"]:
            if "_DATE" in df.columns:
                df = df[df["_DATE"] == val]
        elif key_upper in ["MONTH", "_MONTH"]:
            if "_MONTH" in df.columns:
                df = df[df["_MONTH"] == val]
        elif key_upper in ["ITEM_CODE", "ITEM", "SKU", "PN_CODE"]:
            if "ITEM_CODE" in df.columns:
                df = df[df["ITEM_CODE"].astype(str) == str(val)]
        elif key_upper == "SHIFT_NAME":
            if "SHIFT_NAME" in df.columns:
                df = df[df["SHIFT_NAME"] == val]
        else:
            if key in df.columns:
                df = df[df[key].astype(str) == str(val)]
    return df

def get_time_col(granularity):
    gran = (granularity or "week").lower()
    if gran in ["monthly", "month"]:
        return "_MONTH"
    elif gran == "week":
        return "_WEEK"
    elif gran == "day":
        return "_DATE"
    elif gran == "shift":
        return "_DATE"  # shift will be handled with extra group key
    else:
        return "_WEEK"

def diff_balance(df_a, df_b, group_by=None, granularity="week", filters=None, only_diff=True,
                 threshold_abs=0, threshold_pct=0, sort_by="abs_diff_desc", page=1, page_size=100,
                 compare_field="BALANCE_QTY"):
    """
    Fixed SKU level diff for BOH
    - group_by is ignored, forced to ITEM_CODE + time
    - granularity determines time bucket
    - compare_field defaults BALANCE_QTY
    Returns records with: ITEM_CODE, TIME, PREV, LATEST, DIFF, TAG etc
    """
    try:
        # Normalize
        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        df_a_filt = apply_filters(df_a_norm, filters)
        df_b_filt = apply_filters(df_b_norm, filters)

        if df_a_filt.empty and df_b_filt.empty:
            return {
                "total_a": 0,
                "total_b": 0,
                "records": [],
                "pagination": {"page": 1, "page_size": page_size, "total": 0},
                "group_by": ["ITEM_CODE"],
                "granularity": granularity
            }

        gran = (granularity or "week").lower()
        time_col = get_time_col(gran)

        # Determine grouping keys: always ITEM_CODE + time, plus SHIFT for shift granularity
        if gran == "shift":
            group_keys = ["ITEM_CODE", "_DATE", "SHIFT_NAME"]
            # Ensure SHIFT_NAME exists
            if "SHIFT_NAME" not in df_a_filt.columns:
                df_a_filt["SHIFT_NAME"] = "白班"
            if "SHIFT_NAME" not in df_b_filt.columns:
                df_b_filt["SHIFT_NAME"] = "白班"
        else:
            group_keys = ["ITEM_CODE", time_col]

        # Ensure group_keys exist, filter out missing
        group_keys = [k for k in group_keys if k in df_a_filt.columns or k in df_b_filt.columns]
        if not group_keys:
            group_keys = ["ITEM_CODE"]

        if compare_field not in df_a_filt.columns:
            compare_field = "BALANCE_QTY"
        if compare_field not in df_b_filt.columns:
            compare_field = "BALANCE_QTY"

        # For BOH, sort by date and shift order, then take last per group
        def sort_and_last(df, keys, field):
            if df.empty:
                return pd.DataFrame(columns=keys + [field])
            # Sort for last
            sort_cols = []
            if "_DATE_DT" in df.columns:
                sort_cols.append("_DATE_DT")
            if "_SHIFT_ORDER" in df.columns:
                sort_cols.append("_SHIFT_ORDER")
            if sort_cols:
                df = df.sort_values(sort_cols)
            try:
                agg = df.groupby(keys, as_index=False)[field].last()
                return agg
            except Exception as e:
                # Fallback
                try:
                    agg = df.groupby(keys, as_index=False).last()
                    keep = keys + [field]
                    agg = agg[[c for c in keep if c in agg.columns]]
                    return agg
                except:
                    return pd.DataFrame(columns=keys + [field])

        agg_a = sort_and_last(df_a_filt, group_keys, compare_field)
        agg_b = sort_and_last(df_b_filt, group_keys, compare_field)

        # Merge outer
        merged = pd.merge(agg_a, agg_b, on=group_keys, how="outer", suffixes=("_A", "_B"))
        col_a = f"{compare_field}_A"
        col_b = f"{compare_field}_B"
        if col_a not in merged.columns:
            merged[col_a] = 0
        if col_b not in merged.columns:
            merged[col_b] = 0

        merged[col_a] = merged[col_a].fillna(0)
        merged[col_b] = merged[col_b].fillna(0)
        merged["diff"] = merged[col_b] - merged[col_a]
        merged["abs_diff"] = merged["diff"].abs()

        # Tag
        def get_tag(row):
            a_missing = pd.isna(row.get(col_a)) or row.get(col_a) == 0 and row.get(f"{group_keys[0]}_exists_A") is False
            # Actually we use merge indicator: if row exists only in B, then A is 0 from fillna, but we need to know original presence
            # We already fillna, so detect based on whether group existed
            # For simplicity: if A original aggregation missing, treat as ADD, but since we used outer merge, fillna 0 will hide.
            # We'll use a helper column existence from merge: we can check if A was NaN before fillna.
            # Instead we keep original NaN check before fillna: we already filled, so we need to check via _merge logic? Let's approximate:
            # If col_a ==0 and col_b !=0 and abs diff == col_b => could be ADD, but also could be both present with A=0. We'll use additional logic below with presence sets.
            return "MODIFY"

        # Determine presence via original agg sets
        set_a = set([tuple(x) for x in agg_a[group_keys].to_numpy()]) if not agg_a.empty else set()
        set_b = set([tuple(x) for x in agg_b[group_keys].to_numpy()]) if not agg_b.empty else set()

        def compute_tag(row):
            key_tuple = tuple(row[k] for k in group_keys)
            in_a = key_tuple in set_a
            in_b = key_tuple in set_b
            if not in_a and in_b:
                return "ADDED"
            elif in_a and not in_b:
                return "DELETED"
            else:
                # both present
                if row["diff"] == 0:
                    return "UNCHANGED"
                else:
                    return "MODIFY"

        merged["change_tag"] = merged.apply(compute_tag, axis=1)
        merged["change_type"] = merged["change_tag"]  # for compatibility

        # For only_diff, exclude UNCHANGED
        if only_diff:
            merged = merged[merged["change_tag"] != "UNCHANGED"]

        # Thresholds
        if threshold_abs > 0:
            merged = merged[merged["abs_diff"] >= threshold_abs]
        if threshold_pct > 0:
            # Need diff_pct
            merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r[col_a] * 100) if r[col_a] != 0 else (100 if r["diff"] !=0 else 0), axis=1)
            merged = merged[merged["diff_pct"].abs() >= threshold_pct]
        else:
            # Still compute pct for display
            merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r[col_a] * 100) if r[col_a] != 0 else (100 if r["diff"] !=0 else 0), axis=1)

        # Sort
        if sort_by == "abs_diff_desc":
            merged = merged.sort_values("abs_diff", ascending=False)
        elif sort_by == "diff_desc":
            merged = merged.sort_values("diff", ascending=False)
        elif sort_by == "diff_asc":
            merged = merged.sort_values("diff", ascending=True)
        elif sort_by == "item_asc":
            sort_key = group_keys[0] if group_keys else col_a
            if sort_key in merged.columns:
                merged = merged.sort_values(sort_key)

        total = len(merged)
        start = (page-1)*page_size
        end = start+page_size
        paged = merged.iloc[start:end] if total>0 else merged

        # Convert to records, ensuring no NaT/Timestamp survives
        records = []
        for _, row in paged.iterrows():
            rec = {}
            # Copy only safe columns
            for k in group_keys:
                v = row.get(k)
                # Convert Timestamp/NaT to string or None
                if pd.isna(v):
                    rec[k] = None
                else:
                    # If it's Timestamp, convert to str YYYY-MM-DD
                    try:
                        if hasattr(v, 'strftime'):
                            rec[k] = v.strftime("%Y-%m-%d") if hasattr(v, 'year') else str(v)
                        else:
                            rec[k] = str(v) if not isinstance(v, (int, float)) else v
                    except:
                        rec[k] = str(v)
            # Explicitly ensure ITEM_CODE, DATE fields
            rec["ITEM_CODE"] = rec.get("ITEM_CODE") or row.get("ITEM_CODE") or "Unknown"
            # Time label
            time_val = rec.get(time_col) or row.get(time_col) or rec.get("_DATE") or rec.get("_WEEK") or rec.get("_MONTH")
            rec["TIME"] = time_val
            rec["DATE"] = rec.get("_DATE") or row.get("_DATE") if "_DATE" in group_keys else rec.get(time_col)
            rec["WEEK"] = rec.get("_WEEK") if "_WEEK" in row else None
            rec["MONTH"] = rec.get("_MONTH") if "_MONTH" in row else None
            if gran == "month" or gran == "monthly":
                rec["TIME_LABEL"] = rec.get("_MONTH")
            elif gran == "week":
                rec["TIME_LABEL"] = rec.get("_WEEK")
            else:
                rec["TIME_LABEL"] = rec.get("_DATE")

            rec["PREV"] = float(row.get(col_a, 0))
            rec["LATEST"] = float(row.get(col_b, 0))
            rec["PREVIOUS"] = rec["PREV"]
            rec["LATEST_VALUE"] = rec["LATEST"]
            rec[f"{compare_field}_A"] = rec["PREV"]
            rec[f"{compare_field}_B"] = rec["LATEST"]
            rec["diff"] = float(row.get("diff", 0))
            rec["DIFF"] = rec["diff"]
            rec["abs_diff"] = float(row.get("abs_diff", 0))
            rec["diff_pct"] = float(row.get("diff_pct", 0))
            rec["change_tag"] = row.get("change_tag", "MODIFY")
            rec["change_type"] = rec["change_tag"]
            rec["TAG"] = rec["change_tag"]

            # Compatibility keys
            rec["_group_values"] = {k: rec.get(k) for k in group_keys}
            rec["_DATE"] = rec.get("_DATE")
            rec["_WEEK"] = rec.get("_WEEK")
            rec["_MONTH"] = rec.get("_MONTH")
            rec["ITEM_CODE"] = rec.get("ITEM_CODE")

            # For frontend table columns
            records.append(rec)

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "filtered_a": len(df_a_filt),
            "filtered_b": len(df_b_filt),
            "aggregated_a": len(agg_a),
            "aggregated_b": len(agg_b),
            "total_after_filter": total,
            "records": records,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "group_by": group_keys,
            "granularity": granularity,
            "valid_keys": group_keys,
            "compare_field": compare_field,
            "filters": filters or {},
            "display_name": "BOH",
            "table": "balance"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "total_a": len(df_a) if 'df_a' in locals() else 0,
            "total_b": len(df_b) if 'df_b' in locals() else 0,
            "error": str(e),
            "records": [],
            "pagination": {"page": 1, "page_size": page_size, "total": 0}
        }


def get_chart_data_balance(df_a, df_b, item_code=None, granularity="day", compare_field="BALANCE_QTY"):
    try:
        eff_filters = {}
        if item_code:
            eff_filters["ITEM_CODE"] = item_code

        df_a_norm = normalize_dates(df_a)
        df_b_norm = normalize_dates(df_b)

        df_a_filt = apply_filters(df_a_norm, eff_filters)
        df_b_filt = apply_filters(df_b_norm, eff_filters)

        gran = (granularity or "day").lower()
        time_col = get_time_col(gran)

        if df_a_filt.empty and df_b_filt.empty:
            return {"dates": [], "values_a": [], "values_b": []}

        # For chart, group by time_col only (for single item)
        def agg_for_chart(df):
            if df.empty:
                return pd.DataFrame()
            # Sort then last
            sort_cols = []
            if "_DATE_DT" in df.columns:
                sort_cols.append("_DATE_DT")
            if "_SHIFT_ORDER" in df.columns:
                sort_cols.append("_SHIFT_ORDER")
            if sort_cols:
                df = df.sort_values(sort_cols)
            try:
                agg = df.groupby(time_col, as_index=False)[compare_field].last()
                return agg
            except:
                return df

        agg_a = agg_for_chart(df_a_filt)
        agg_b = agg_for_chart(df_b_filt)

        if agg_a.empty and agg_b.empty:
            return {"dates": [], "values_a": [], "values_b": []}

        merged = pd.merge(agg_a, agg_b, on=time_col, how="outer", suffixes=("_A", "_B"))
        merged = merged.sort_values(time_col)
        merged = merged.fillna(0)

        col_a = f"{compare_field}_A"
        col_b = f"{compare_field}_B"
        if col_a not in merged.columns:
            col_a = "BALANCE_QTY_A" if "BALANCE_QTY_A" in merged.columns else col_a
        if col_b not in merged.columns:
            col_b = "BALANCE_QTY_B" if "BALANCE_QTY_B" in merged.columns else col_b

        dates = merged[time_col].astype(str).tolist()
        vals_a = merged[col_a].tolist() if col_a in merged.columns else []
        vals_b = merged[col_b].tolist() if col_b in merged.columns else []

        return {
            "dates": dates,
            "values_a": vals_a,
            "values_b": vals_b,
            "granularity": granularity,
            "compare_field": compare_field,
            "filters": eff_filters
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "dates": [], "values_a": [], "values_b": []}
