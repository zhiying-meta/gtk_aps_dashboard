"""FCST parser - Main + Detail JOIN"""
import pandas as pd

def parse_fcst(main_path: str, detail_path: str):
    try:
        main_df = pd.read_excel(main_path)
        detail_df = pd.read_excel(detail_path)
        return main_df, detail_df
    except Exception as e:
        raise e


def build_fcst_joined(main_df, detail_df):
    """
    JOIN main and detail via ID = MAIN_ID, then build SKU x Week matrix
    Returns DataFrame with SKU, Week, Value
    """
    try:
        # Ensure ID columns are same type
        main_df = main_df.copy()
        detail_df = detail_df.copy()
        # Convert ID to string for join safety
        main_df["ID_STR"] = main_df["ID"].astype(str)
        detail_df["MAIN_ID_STR"] = detail_df["MAIN_ID"].astype(str)

        # Merge
        merged = pd.merge(detail_df, main_df[["ID_STR", "PN_CODE"]], left_on="MAIN_ID_STR", right_on="ID_STR", how="left")
        # Now merged has PN_CODE, ACTUALFIRSTDAYOFWEEK, ACTUALWEEKVALUE
        # Group by PN_CODE, ACTUALFIRSTDAYOFWEEK sum ACTUALWEEKVALUE
        if "ACTUALFIRSTDAYOFWEEK" not in merged.columns or "PN_CODE" not in merged.columns:
            return pd.DataFrame()

        # Normalize week date
        # Keep relevant cols
        grouped = merged.groupby(["PN_CODE", "ACTUALFIRSTDAYOFWEEK"], as_index=False)["ACTUALWEEKVALUE"].sum()
        return grouped
    except Exception as e:
        print(f"FCST JOIN error: {e}")
        return pd.DataFrame()


def build_fcst_raw_detail(main_df, detail_df):
    """Build raw detail with unique key ID+YEAR+MONTH+WEEK for exact row-level diff"""
    try:
        detail_df = detail_df.copy()
        # Create unique key: ID + YEAR + MONTH + WEEK + ACTUALFIRSTDAYOFWEEK
        detail_df["_RAW_KEY"] = detail_df["ID"].astype(str) + "_" + detail_df["YEAR"].astype(str) + "_" + detail_df["MONTH"].astype(str) + "_" + detail_df["WEEK"].astype(str) + "_" + detail_df["ACTUALFIRSTDAYOFWEEK"].astype(str)
        return detail_df
    except Exception as e:
        print(f"FCST raw build error: {e}")
        return pd.DataFrame()


def diff_fcst(main_a, detail_a, main_b, detail_b, mode="grouped", granularity="week"):
    """
    mode: grouped (default, by PN+Week sum) or raw (by ID+YEAR+MONTH+WEEK exact)
    granularity: week, day, monthly - for time grouping
    For user who edits 1 detail row, grouped may show 2 modifies because 2 SKUs share same MAIN_ID
    """
    try:
        joined_a = build_fcst_joined(main_a, detail_a)
        joined_b = build_fcst_joined(main_b, detail_b)

        # Handle monthly granularity: convert Week to Month
        if granularity in ["monthly", "month"]:
            # Convert ACTUALFIRSTDAYOFWEEK to YYYY-MM
            def week_to_month(df):
                if df.empty:
                    return df
                df = df.copy()
                try:
                    df["_MONTH"] = pd.to_datetime(df["ACTUALFIRSTDAYOFWEEK"], errors='coerce').dt.strftime("%Y-%m")
                    # Group by PN_CODE + _MONTH sum
                    df = df.groupby(["PN_CODE", "_MONTH"], as_index=False)["ACTUALWEEKVALUE"].sum()
                    df.rename(columns={"_MONTH": "ACTUALFIRSTDAYOFWEEK"}, inplace=True)
                except Exception as e:
                    print(f"Month conversion error: {e}")
                return df
            joined_a = week_to_month(joined_a)
            joined_b = week_to_month(joined_b)

        if joined_a.empty and joined_b.empty:
            return {
                "total_a": 0,
                "total_b": 0,
                "added": 0,
                "deleted": 0,
                "modified": 0,
                "records": [],
                "summary": {}
            }

        # Grouped diff (business level)
        merged = pd.merge(joined_a, joined_b, on=["PN_CODE", "ACTUALFIRSTDAYOFWEEK"], how="outer", suffixes=("_A", "_B"), indicator=True)
        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        modified = []
        for _, row in both.iterrows():
            va = row.get("ACTUALWEEKVALUE_A")
            vb = row.get("ACTUALWEEKVALUE_B")
            if pd.isna(va) and pd.isna(vb):
                continue
            if va != vb:
                try:
                    if pd.isna(va) or pd.isna(vb):
                        pass
                    else:
                        if float(va) == float(vb):
                            continue
                except:
                    if str(va) == str(vb):
                        continue
                modified.append({
                    "key": {"PN_CODE": row["PN_CODE"], "WEEK": str(row["ACTUALFIRSTDAYOFWEEK"])},
                    "field": "ACTUALWEEKVALUE",
                    "value_a": float(va) if not pd.isna(va) else 0,
                    "value_b": float(vb) if not pd.isna(vb) else 0,
                    "delta": float(vb)-float(va) if not pd.isna(va) and not pd.isna(vb) else None,
                    "change_type": "MODIFY",
                    "explanation": "Note: 1 detail row may affect 2 SKUs because SK-1001899-01 and SK-1001900-01 share same MAIN_ID 5195605342487620"
                })

        # Raw detail diff (exact row level)
        raw_a = build_fcst_raw_detail(main_a, detail_a)
        raw_b = build_fcst_raw_detail(main_b, detail_b)
        raw_modified = []
        raw_added = pd.DataFrame()
        raw_deleted = pd.DataFrame()
        try:
            if not raw_a.empty and not raw_b.empty:
                raw_merged = pd.merge(raw_a, raw_b, on="_RAW_KEY", how="outer", suffixes=("_A", "_B"), indicator=True)
                raw_added = raw_merged[raw_merged["_merge"] == "right_only"]
                raw_deleted = raw_merged[raw_merged["_merge"] == "left_only"]
                raw_both = raw_merged[raw_merged["_merge"] == "both"]
                for _, row in raw_both.iterrows():
                    va = row.get("ACTUALWEEKVALUE_A")
                    vb = row.get("ACTUALWEEKVALUE_B")
                    if pd.isna(va) and pd.isna(vb):
                        continue
                    if va != vb:
                        try:
                            if not pd.isna(va) and not pd.isna(vb) and float(va) == float(vb):
                                continue
                        except:
                            if str(va) == str(vb):
                                continue
                        # Find PN for this raw key via main
                        # raw key contains ID which maps to PN via main
                        raw_modified.append({
                            "key": {"RAW_KEY": row["_RAW_KEY"], "ID_A": row.get("ID_A"), "WEEK_A": row.get("ACTUALFIRSTDAYOFWEEK_A")},
                            "field": "ACTUALWEEKVALUE",
                            "value_a": float(va) if not pd.isna(va) else 0,
                            "value_b": float(vb) if not pd.isna(vb) else 0,
                            "delta": float(vb)-float(va) if not pd.isna(va) and not pd.isna(vb) else None,
                            "change_type": "MODIFY_RAW"
                        })
        except Exception as e:
            print(f"Raw diff error: {e}")

        return {
            "total_a": len(joined_a),
            "total_b": len(joined_b),
            "added": len(added),
            "deleted": len(deleted),
            "modified": len(modified),
            "modified_raw": len(raw_modified),
            "added_raw": len(raw_added),
            "deleted_raw": len(raw_deleted),
            "records": {
                "added": added.head(100).to_dict(orient="records"),
                "deleted": deleted.head(100).to_dict(orient="records"),
                "modified": modified[:100],
                "modified_raw": raw_modified[:100],
                "added_raw": raw_added.head(20).to_dict(orient="records") if not raw_added.empty else [],
                "deleted_raw": raw_deleted.head(20).to_dict(orient="records") if not raw_deleted.empty else []
            },
            "summary": {
                "total_weeks_a": joined_a["ACTUALFIRSTDAYOFWEEK"].nunique() if not joined_a.empty else 0,
                "total_weeks_b": joined_b["ACTUALFIRSTDAYOFWEEK"].nunique() if not joined_b.empty else 0,
                "total_skus_a": joined_a["PN_CODE"].nunique() if not joined_a.empty else 0,
                "total_skus_b": joined_b["PN_CODE"].nunique() if not joined_b.empty else 0,
                "note": "1 detail row may affect 2 SKUs because SK-1001899-01 and SK-1001900-01 share MAIN_ID 5195605342487620, so changing 1 detail row shows as 2 grouped modifies",
                "raw_total_a": len(raw_a),
                "raw_total_b": len(raw_b)
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "total_a": 0,
            "total_b": 0,
            "added": 0,
            "deleted": 0,
            "modified": 0,
            "error": str(e),
            "records": []
        }


def get_fcst_horizontal_matrix(main_a, detail_a, main_b, detail_b, granularity="week", sku_category="ALL", only_diff=True, change_type="ALL"):
    """Horizontal matrix for FCST - similar to Plan Input but using FCST parser logic"""
    try:
        from .matrix_helpers import apply_sku_filter_df, generate_time_buckets
        # Reuse build_fcst_joined logic but with normalized dates
        def normalize_fcst_detail(detail_df, main_df):
            try:
                if detail_df.empty or main_df.empty:
                    return pd.DataFrame()
                detail_df = detail_df.copy()
                main_df = main_df.copy()
                main_df["ID_STR"] = main_df["ID"].astype(str)
                detail_df["MAIN_ID_STR"] = detail_df["MAIN_ID"].astype(str)
                merged = pd.merge(detail_df, main_df[["ID_STR", "PN_CODE"]], left_on="MAIN_ID_STR", right_on="ID_STR", how="left")
                merged["_WEEK_DT"] = pd.to_datetime(merged["ACTUALFIRSTDAYOFWEEK"], errors='coerce')
                merged = merged[~merged["_WEEK_DT"].isna()]
                if merged.empty:
                    return merged
                merged["_DATE_DT"] = merged["_WEEK_DT"]
                merged["_WEEK"] = merged["_WEEK_DT"].dt.strftime("%Y-%m-%d")
                merged["_DATE"] = merged["_WEEK"]
                merged["_MONTH"] = merged["_WEEK_DT"].dt.strftime("%Y-%m")
                return merged
            except Exception as e:
                print(f"FCST matrix normalize error: {e}")
                return pd.DataFrame()

        df_a_norm = normalize_fcst_detail(detail_a, main_a)
        df_b_norm = normalize_fcst_detail(detail_b, main_b)

        df_a_filt = apply_sku_filter_df(df_a_norm, "PN_CODE", sku_category)
        df_b_filt = apply_sku_filter_df(df_b_norm, "PN_CODE", sku_category)

        if df_a_filt.empty and df_b_filt.empty:
            return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0}}

        gran = (granularity or "week").lower()
        if gran in ["month", "monthly"]:
            time_col = "_MONTH"
        else:
            time_col = "_WEEK"

        time_buckets = generate_time_buckets(df_a_filt, df_b_filt, gran)

        if not time_buckets:
            return {"time_buckets": [], "sku_list": [], "matrix": {}, "summary": {"total_skus":0, "total_times":0}}

        group_keys = ["PN_CODE", time_col]
        def agg_sum(df, keys):
            if df.empty:
                return pd.DataFrame(columns=keys + ["ACTUALWEEKVALUE"])
            try:
                return df.groupby(keys, as_index=False)["ACTUALWEEKVALUE"].sum()
            except:
                return pd.DataFrame(columns=keys + ["ACTUALWEEKVALUE"])

        agg_a = agg_sum(df_a_filt, group_keys)
        agg_b = agg_sum(df_b_filt, group_keys)

        def get_label(row):
            return row.get(time_col)

        lookup_a = {}
        lookup_b = {}
        if not agg_a.empty:
            for _, r in agg_a.iterrows():
                sku = r.get("PN_CODE")
                t_label = get_label(r)
                if sku and t_label:
                    lookup_a[(sku, t_label)] = float(r.get("ACTUALWEEKVALUE", 0))
        if not agg_b.empty:
            for _, r in agg_b.iterrows():
                sku = r.get("PN_CODE")
                t_label = get_label(r)
                if sku and t_label:
                    lookup_b[(sku, t_label)] = float(r.get("ACTUALWEEKVALUE", 0))

        skus_a = set(agg_a["PN_CODE"].dropna()) if not agg_a.empty and "PN_CODE" in agg_a.columns else set()
        skus_b = set(agg_b["PN_CODE"].dropna()) if not agg_b.empty and "PN_CODE" in agg_b.columns else set()
        all_skus = sorted(list(skus_a | skus_b))

        bucket_labels = time_buckets

        def matches_ct(tag, filter_ct):
            if not filter_ct or filter_ct.upper() == "ALL":
                return True
            return tag.upper() == filter_ct.upper()

        matrix = {}
        for sku in all_skus:
            matrix[sku] = {}
            has_matching = False
            for tb in bucket_labels:
                prev = lookup_a.get((sku, tb), None)
                latest = lookup_b.get((sku, tb), None)
                if prev is None and latest is None:
                    matrix[sku][tb] = None
                else:
                    p_val = prev if prev is not None else 0
                    l_val = latest if latest is not None else 0
                    diff = l_val - p_val
                    if prev is None and latest is not None:
                        tag = "ADDED"
                    elif prev is not None and latest is None:
                        tag = "DELETED"
                    else:
                        tag = "MODIFY" if diff !=0 else "UNCHANGED"
                    if not matches_ct(tag, change_type):
                        matrix[sku][tb] = None
                        continue
                    if tag == "UNCHANGED" and only_diff:
                        matrix[sku][tb] = None
                        continue
                    if diff !=0 or tag in ["ADDED","DELETED"]:
                        has_matching = True
                    matrix[sku][tb] = {"prev": p_val, "latest": l_val, "diff": diff, "tag": tag, "prev_raw": prev, "latest_raw": latest}
            if only_diff and not has_matching:
                if sku in matrix:
                    has_any = any(v is not None for v in matrix[sku].values())
                    if not has_any:
                        del matrix[sku]
            elif change_type and change_type.upper() != "ALL":
                has_any = any(v is not None for v in matrix[sku].values())
                if not has_any and sku in matrix:
                    del matrix[sku]

        final_skus = sorted(list(matrix.keys()))

        return {
            "time_buckets": time_buckets,
            "bucket_labels": bucket_labels,
            "sku_list": final_skus,
            "matrix": matrix,
            "granularity": gran,
            "sku_category": sku_category,
            "summary": {
                "total_skus": len(final_skus),
                "total_times": len(bucket_labels),
                "total_original_skus": len(all_skus),
                "time_range": f"{bucket_labels[0]} to {bucket_labels[-1]}" if bucket_labels else ""
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "time_buckets": [], "sku_list": [], "matrix": {}}

