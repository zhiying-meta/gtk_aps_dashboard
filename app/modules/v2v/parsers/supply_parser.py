"""
Supply parser - Supply供应表
Key: (PN_CODE, KITTING_DATE)
Compare fields: KITTING_VALUE, QTY_REM, QTY_REM2, TOTAL_LOSS_QTY
Supports weekly aggregation
"""
import pandas as pd

def parse_supply(file_path: str):
    df = pd.read_excel(file_path)
    return df

def diff_supply(df_a, df_b, granularity="day"):
    """
    granularity: day (default) or week
    For week, aggregate by PN_CODE + week (Saturday)
    """
    try:
        key_cols = ["PN_CODE", "KITTING_DATE"]
        compare_fields = ["KITTING_VALUE", "QTY_REM", "QTY_REM2", "TOTAL_LOSS_QTY"]

        # Ensure columns exist
        for k in key_cols:
            if k not in df_a.columns or k not in df_b.columns:
                return {
                    "total_a": len(df_a),
                    "total_b": len(df_b),
                    "added": 0,
                    "deleted": 0,
                    "modified": 0,
                    "error": f"Missing key {k}",
                    "records": []
                }

        # Normalize date
        df_a = df_a.copy()
        df_b = df_b.copy()
        df_a["_KITTING_DATE_DT"] = pd.to_datetime(df_a["KITTING_DATE"], errors='coerce')
        df_b["_KITTING_DATE_DT"] = pd.to_datetime(df_b["KITTING_DATE"], errors='coerce')

        if granularity == "week":
            def to_saturday(dt):
                if pd.isna(dt):
                    return None
                dow = dt.weekday()
                delta = (5 - dow) % 7
                from datetime import timedelta
                return dt + timedelta(days=delta)

            df_a["_WEEK"] = df_a["_KITTING_DATE_DT"].apply(to_saturday)
            df_b["_WEEK"] = df_b["_KITTING_DATE_DT"].apply(to_saturday)

            agg_fields = {field: "sum" for field in compare_fields if field in df_a.columns}
            df_a_agg = df_a.groupby(["PN_CODE", "_WEEK"], as_index=False).agg(agg_fields)
            df_b_agg = df_b.groupby(["PN_CODE", "_WEEK"], as_index=False).agg(agg_fields)

            merge_key = ["PN_CODE", "_WEEK"]
            df_a_use = df_a_agg
            df_b_use = df_b_agg
        elif granularity in ["monthly", "month"]:
            # Monthly: YYYY-MM
            df_a["_MONTH"] = df_a["_KITTING_DATE_DT"].dt.strftime("%Y-%m")
            df_b["_MONTH"] = df_b["_KITTING_DATE_DT"].dt.strftime("%Y-%m")
            agg_fields = {field: "sum" for field in compare_fields if field in df_a.columns}
            df_a_agg = df_a.groupby(["PN_CODE", "_MONTH"], as_index=False).agg(agg_fields)
            df_b_agg = df_b.groupby(["PN_CODE", "_MONTH"], as_index=False).agg(agg_fields)
            merge_key = ["PN_CODE", "_MONTH"]
            df_a_use = df_a_agg
            df_b_use = df_b_agg
        else:
            # Day granularity - direct merge on PN + Date
            df_a_use = df_a
            df_b_use = df_b
            df_a_use["_MERGE_DATE"] = df_a_use["_KITTING_DATE_DT"].dt.strftime("%Y-%m-%d")
            df_b_use["_MERGE_DATE"] = df_b_use["_KITTING_DATE_DT"].dt.strftime("%Y-%m-%d")
            merge_key = ["PN_CODE", "_MERGE_DATE"]

        # Outer merge
        merged = pd.merge(df_a_use, df_b_use, on=merge_key, how="outer", suffixes=("_A", "_B"), indicator=True)

        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        modified_records = []

        for _, row in both.iterrows():
            for field in compare_fields:
                if field not in df_a.columns:
                    continue
                col_a = field + "_A" if field + "_A" in row else field
                col_b = field + "_B" if field + "_B" in row else field
                if col_a not in row or col_b not in row:
                    continue
                va = row[col_a]
                vb = row[col_b]
                if pd.isna(va) and pd.isna(vb):
                    continue
                # Compare
                try:
                    if pd.isna(va) or pd.isna(vb):
                        diff = True
                    else:
                        diff = abs(float(va) - float(vb)) > 1e-6
                        if not diff:
                            continue
                except:
                    if str(va) == str(vb):
                        continue
                    diff = True

                if diff:
                    # Build key
                    if granularity == "week":
                        key = {
                            "PN_CODE": row["PN_CODE"],
                            "WEEK": str(row["_WEEK"]),
                            "GRANULARITY": "week"
                        }
                    else:
                        key = {
                            "PN_CODE": row["PN_CODE"],
                            "KITTING_DATE": row.get("_MERGE_DATE") or str(row.get("KITTING_DATE")),
                            "GRANULARITY": "day"
                        }

                    try:
                        delta = float(vb) - float(va) if not pd.isna(va) and not pd.isna(vb) else None
                    except:
                        delta = None

                    modified_records.append({
                        "key": key,
                        "field": field,
                        "value_a": float(va) if not pd.isna(va) and isinstance(va, (int,float)) else (str(va) if not pd.isna(va) else None),
                        "value_b": float(vb) if not pd.isna(vb) and isinstance(vb, (int,float)) else (str(vb) if not pd.isna(vb) else None),
                        "delta": delta,
                        "change_type": "MODIFY"
                    })

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "added": len(added),
            "deleted": len(deleted),
            "modified": len(modified_records),
            "records": {
                "added": added.head(50).to_dict(orient="records"),
                "deleted": deleted.head(50).to_dict(orient="records"),
                "modified": modified_records[:100]
            },
            "summary": {
                "added": len(added),
                "deleted": len(deleted),
                "modified": len(modified_records),
                "granularity": granularity
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "total_a": len(df_a) if 'df_a' in locals() else 0,
            "total_b": len(df_b) if 'df_b' in locals() else 0,
            "added": 0,
            "deleted": 0,
            "modified": 0,
            "error": str(e),
            "records": []
        }


def get_chart_data_supply(df_a, df_b, pn_code=None):
    """
    Get cumulative kitting curve for chart
    """
    try:
        if pn_code:
            df_a = df_a[df_a["PN_CODE"] == pn_code]
            df_b = df_b[df_b["PN_CODE"] == pn_code]

        df_a = df_a.copy()
        df_b = df_b.copy()
        df_a["_DATE"] = pd.to_datetime(df_a["KITTING_DATE"], errors='coerce')
        df_b["_DATE"] = pd.to_datetime(df_b["KITTING_DATE"], errors='coerce')

        df_a = df_a.sort_values("_DATE")
        df_b = df_b.sort_values("_DATE")

        # Daily sum then cumsum
        daily_a = df_a.groupby("_DATE")["KITTING_VALUE"].sum().sort_index()
        daily_b = df_b.groupby("_DATE")["KITTING_VALUE"].sum().sort_index()

        cum_a = daily_a.cumsum()
        cum_b = daily_b.cumsum()

        # Outer merge dates
        all_dates = sorted(set(cum_a.index) | set(cum_b.index))
        dates_str = [d.strftime("%Y-%m-%d") if hasattr(d, 'strftime') else str(d) for d in all_dates]

        vals_a = []
        vals_b = []
        last_a = 0
        last_b = 0
        for d in all_dates:
            if d in cum_a:
                last_a = cum_a[d]
            if d in cum_b:
                last_b = cum_b[d]
            vals_a.append(float(last_a))
            vals_b.append(float(last_b))

        return {
            "dates": dates_str,
            "values_a": vals_a,
            "values_b": vals_b,
            "daily_a": daily_a.tolist(),
            "daily_b": daily_b.tolist()
        }
    except Exception as e:
        return {"error": str(e), "dates": [], "values_a": [], "values_b": []}
