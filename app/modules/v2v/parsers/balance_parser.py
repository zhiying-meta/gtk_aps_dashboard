"""
Balance parser - 结存表_输出
Similar to plan_output but for balance: ITEM_CODE, BALANCE_QTY, etc.
For weekly, we take last balance per week (not sum), but provide both.
"""
import pandas as pd
from datetime import timedelta

def parse_balance(file_path: str):
    df = pd.read_excel(file_path)
    return df

def to_saturday(dt):
    if pd.isna(dt):
        return None
    dow = dt.weekday()
    delta = (5 - dow) % 7
    return dt + timedelta(days=delta)

def normalize_dates(df):
    df = df.copy()
    df["_DATE_DT"] = pd.to_datetime(df["PLAN_DATE"], errors='coerce')
    df["_DATE"] = df["_DATE_DT"].dt.strftime("%Y-%m-%d")
    df["_WEEK_DT"] = df["_DATE_DT"].apply(lambda x: to_saturday(x) if pd.notna(x) else None)
    df["_WEEK"] = df["_WEEK_DT"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) and hasattr(x, 'strftime') else None)
    # Shift order for last value: white=1, night=2
    # Use SHIFT_CODE if available, else SHIFT_NAME
    if "SHIFT_CODE" in df.columns:
        df["_SHIFT_ORDER"] = df["SHIFT_CODE"]
    else:
        df["_SHIFT_ORDER"] = df["SHIFT_NAME"].map({"白班": 1, "夜班": 2}).fillna(1)
    return df

def apply_filters(df, filters):
    if not filters:
        return df
    df = df.copy()
    for key, val in filters.items():
        if val is None or val == "":
            continue
        key_upper = key.upper()
        if key_upper == "WEEK" or key_upper == "_WEEK":
            if "_WEEK" in df.columns:
                df = df[df["_WEEK"] == val]
        elif key_upper in ["DATE", "PLAN_DATE", "_DATE"]:
            if "_DATE" in df.columns:
                df = df[df["_DATE"] == val]
        elif key_upper == "ITEM_CODE" or key_upper == "ITEM" or key_upper == "SKU":
            if "ITEM_CODE" in df.columns:
                df = df[df["ITEM_CODE"] == val]
        elif key_upper == "SHIFT_NAME":
            if "SHIFT_NAME" in df.columns:
                df = df[df["SHIFT_NAME"] == val]
        else:
            if key in df.columns:
                df = df[df[key].astype(str) == str(val)]
    return df

def get_group_keys(group_by, granularity):
    clean_gb = []
    for g in group_by:
        g = g.strip()
        if g and g not in clean_gb:
            clean_gb.append(g)
    if granularity == "week":
        time_cols = ["_WEEK"]
    elif granularity == "day":
        time_cols = ["_DATE"]
    else:
        time_cols = ["_DATE", "SHIFT_NAME"]
        time_cols = [c for c in time_cols if c not in clean_gb]
    final_keys = clean_gb + time_cols
    return final_keys, clean_gb, time_cols

def aggregate_balance(df, group_by, granularity, agg_method="last"):
    """
    Aggregate balance data
    For BALANCE_QTY, use last value per group (sort by date and shift order)
    For others sum? But for simplicity, we use last for BALANCE and sum for others, or configurable.
    """
    df = normalize_dates(df)

    if df.empty:
        return pd.DataFrame()

    group_keys, clean_gb, time_cols = get_group_keys(group_by, granularity)
    valid_keys = [k for k in group_keys if k in df.columns]
    if not valid_keys:
        valid_keys = time_cols

    # Sort for last value logic
    df = df.sort_values(["_DATE_DT", "_SHIFT_ORDER"])

    if granularity == "week":
        if agg_method == "last":
            # Only keep valid_keys + compare fields, not internal timestamp columns
            # Use last for BALANCE_QTY and other compare fields
            agg_dict = {}
            # Keep the last of compare fields and any other numeric fields we need
            for col in ["BALANCE_QTY", "SHIFT_OUT_QTY", "PRE_INPUT_QTY"]:
                if col in df.columns:
                    agg_dict[col] = "last"
            # If valid_keys includes internal, keep them as first
            agg = df.groupby(valid_keys, as_index=False).agg(agg_dict) if agg_dict else df.groupby(valid_keys, as_index=False).last()
            # Drop internal timestamp columns if present
            agg = agg[[c for c in agg.columns if not c.startswith("_") or c in valid_keys]]
        else:
            agg = df.groupby(valid_keys, as_index=False).agg({
                "BALANCE_QTY": "sum",
                "SHIFT_OUT_QTY": "sum",
                "PRE_INPUT_QTY": "sum"
            })
    elif granularity == "day":
        if agg_method == "last":
            # Only keep valid_keys + compare fields
            agg_dict = {}
            for col in ["BALANCE_QTY", "SHIFT_OUT_QTY", "PRE_INPUT_QTY"]:
                if col in df.columns:
                    agg_dict[col] = "last"
            agg = df.groupby(valid_keys, as_index=False).agg(agg_dict) if agg_dict else df.groupby(valid_keys, as_index=False).last()
            agg = agg[[c for c in agg.columns if not c.startswith("_") or c in valid_keys]]
        else:
            agg = df.groupby(valid_keys, as_index=False).agg({
                "BALANCE_QTY": "sum",
                "SHIFT_OUT_QTY": "sum",
                "PRE_INPUT_QTY": "sum"
            })
    else:  # shift
        agg = df.groupby(valid_keys, as_index=False).agg({
            "BALANCE_QTY": "last",
            "SHIFT_OUT_QTY": "sum",
            "PRE_INPUT_QTY": "sum"
        }) if not df.empty else df
        agg = agg[[c for c in agg.columns if not c.startswith("_") or c in valid_keys]]

    return agg, valid_keys

def diff_balance(df_a, df_b, group_by, granularity="week", filters=None, only_diff=True,
                 threshold_abs=0, threshold_pct=0, sort_by="abs_diff_desc", page=1, page_size=100,
                 compare_field="BALANCE_QTY"):
    """
    Diff for balance table
    compare_field: BALANCE_QTY, SHIFT_OUT_QTY, PRE_INPUT_QTY
    """
    try:
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
                "group_by": group_by,
                "granularity": granularity
            }

        group_keys, clean_gb, time_cols = get_group_keys(group_by, granularity)
        valid_keys_a = [k for k in group_keys if k in df_a_filt.columns]
        valid_keys_b = [k for k in group_keys if k in df_b_filt.columns]
        valid_keys = list(set(valid_keys_a) & set(valid_keys_b))
        if not valid_keys:
            valid_keys = [k for k in group_keys if k in df_a_filt.columns or k in df_b_filt.columns]
            if not valid_keys:
                valid_keys = time_cols

        # Aggregate: for balance, last per group
        df_a_filt = df_a_filt.sort_values(["_DATE_DT", "_SHIFT_ORDER"])
        df_b_filt = df_b_filt.sort_values(["_DATE_DT", "_SHIFT_ORDER"])

        # Use last for compare_field, but need to handle if field not exists
        if compare_field not in df_a_filt.columns:
            compare_field = "BALANCE_QTY"

        # Only keep valid_keys + compare_field to avoid Timestamp/NaT columns that break JSON
        def safe_groupby_last(df, keys, field):
            if df.empty:
                return pd.DataFrame(columns=keys + [field])
            # Only aggregate the compare field, keep keys
            try:
                # Use last for compare field
                agg = df.groupby(keys, as_index=False)[field].last()
                return agg
            except:
                # Fallback: use last for all, then filter columns
                agg = df.groupby(keys, as_index=False).last()
                # Keep only keys and field
                keep_cols = keys + [field]
                # Also keep any other compare fields if present
                for cf in ["BALANCE_QTY", "SHIFT_OUT_QTY", "PRE_INPUT_QTY"]:
                    if cf in agg.columns and cf not in keep_cols:
                        keep_cols.append(cf)
                agg = agg[[c for c in keep_cols if c in agg.columns]]
                return agg

        agg_a = safe_groupby_last(df_a_filt, valid_keys, compare_field)
        agg_b = safe_groupby_last(df_b_filt, valid_keys, compare_field)

        # Ensure compare_field exists
        if compare_field not in agg_a.columns:
            agg_a[compare_field] = 0
        if compare_field not in agg_b.columns:
            agg_b[compare_field] = 0

        merged = pd.merge(agg_a, agg_b, on=valid_keys, how="outer", suffixes=("_A", "_B"))
        col_a = f"{compare_field}_A"
        col_b = f"{compare_field}_B"
        if col_a not in merged.columns:
            merged[col_a] = 0
        if col_b not in merged.columns:
            merged[col_b] = 0

        merged[col_a] = merged[col_a].fillna(0)
        merged[col_b] = merged[col_b].fillna(0)
        merged["diff"] = merged[col_b] - merged[col_a]
        merged["diff_pct"] = merged.apply(lambda r: (r["diff"] / r[col_a] * 100) if r[col_a] != 0 else (100 if r["diff"] !=0 else 0), axis=1)
        merged["abs_diff"] = merged["diff"].abs()

        # Negative balance flag
        merged["is_negative_a"] = merged[col_a] < 0
        merged["is_negative_b"] = merged[col_b] < 0

        if only_diff:
            merged = merged[merged["diff"] != 0]

        if threshold_abs > 0:
            merged = merged[merged["abs_diff"] >= threshold_abs]
        if threshold_pct > 0:
            merged = merged[merged["diff_pct"].abs() >= threshold_pct]

        if sort_by == "abs_diff_desc":
            merged = merged.sort_values("abs_diff", ascending=False)
        elif sort_by == "diff_desc":
            merged = merged.sort_values("diff", ascending=False)

        total = len(merged)
        start = (page-1)*page_size
        end = start+page_size
        paged = merged.iloc[start:end] if total>0 else merged

        records = paged.to_dict(orient="records")
        enriched = []
        for rec in records:
            enriched.append({
                **rec,
                "_drill": {
                    "can_drill_day": granularity == "week",
                    "can_drill_shift": granularity in ["week", "day"],
                    "next_granularity": "day" if granularity=="week" else "shift" if granularity=="day" else None
                },
                "_group_values": {k: rec.get(k) for k in valid_keys},
                "is_negative": rec.get("is_negative_a") or rec.get("is_negative_b")
            })

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "filtered_a": len(df_a_filt),
            "filtered_b": len(df_b_filt),
            "aggregated_a": len(agg_a),
            "aggregated_b": len(agg_b),
            "total_after_filter": total,
            "records": enriched,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "group_by": group_by,
            "granularity": granularity,
            "valid_keys": valid_keys,
            "compare_field": compare_field,
            "filters": filters or {}
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

        if granularity == "week":
            time_col = "_WEEK"
            df_a_filt = df_a_filt.sort_values(["_DATE_DT", "_SHIFT_ORDER"]).groupby(time_col, as_index=False).last()
            df_b_filt = df_b_filt.sort_values(["_DATE_DT", "_SHIFT_ORDER"]).groupby(time_col, as_index=False).last()
        else:
            time_col = "_DATE"
            df_a_filt = df_a_filt.sort_values(["_DATE_DT", "_SHIFT_ORDER"]).groupby(time_col, as_index=False).last() if not df_a_filt.empty else df_a_filt
            df_b_filt = df_b_filt.sort_values(["_DATE_DT", "_SHIFT_ORDER"]).groupby(time_col, as_index=False).last() if not df_b_filt.empty else df_b_filt

        df_a_filt = df_a_filt.sort_values(time_col) if time_col in df_a_filt.columns else df_a_filt
        df_b_filt = df_b_filt.sort_values(time_col) if time_col in df_b_filt.columns else df_b_filt

        merged = pd.merge(df_a_filt, df_b_filt, on=time_col, how="outer", suffixes=("_A", "_B"))
        merged = merged.sort_values(time_col)
        merged = merged.fillna(0)

        # Determine y columns
        col_a = f"{compare_field}_A"
        col_b = f"{compare_field}_B"
        if col_a not in merged.columns:
            col_a = "BALANCE_QTY_A"
        if col_b not in merged.columns:
            col_b = "BALANCE_QTY_B"

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
