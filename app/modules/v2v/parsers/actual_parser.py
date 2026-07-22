"""
Actual IO parser - I_O实际值表
Key: (LINE_CODE, SKU, PLAN_DATE, SHIFT_NAME, PLAN_ITEM)
Checks:
- Time coverage: min/max date per version
- Overlapping range consistency: same key should have same PLAN_VALUE
"""
import pandas as pd
from datetime import datetime

def parse_actual(file_path: str):
    try:
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        raise e

def normalize_date(df, col="PLAN_DATE"):
    """Convert PLAN_DATE to datetime"""
    try:
        df["_PLAN_DATE_DT"] = pd.to_datetime(df[col], errors='coerce')
    except:
        df["_PLAN_DATE_DT"] = df[col]
    return df

def diff_actual(df_a, df_b):
    try:
        # Ensure needed columns
        key_cols = ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"]
        compare_field = "PLAN_VALUE"

        # Check if columns exist, if not return error
        for k in key_cols:
            if k not in df_a.columns or k not in df_b.columns:
                return {
                    "total_a": len(df_a),
                    "total_b": len(df_b),
                    "added": 0,
                    "deleted": 0,
                    "modified": 0,
                    "error": f"Missing key column {k}",
                    "records": []
                }

        # Normalize dates for coverage analysis
        df_a = normalize_date(df_a.copy())
        df_b = normalize_date(df_b.copy())

        # Coverage
        min_a = df_a["_PLAN_DATE_DT"].min()
        max_a = df_a["_PLAN_DATE_DT"].max()
        min_b = df_b["_PLAN_DATE_DT"].min()
        max_b = df_b["_PLAN_DATE_DT"].max()

        # For diff, we do outer merge on key columns
        # Use PLAN_DATE as string for merge to avoid datetime issues, but use normalized for range
        # Create merge key: convert PLAN_DATE to string YYYY-MM-DD for stable merge
        for df in [df_a, df_b]:
            df["_MERGE_DATE"] = df["_PLAN_DATE_DT"].dt.strftime("%Y-%m-%d") if pd.api.types.is_datetime64_any_dtype(df["_PLAN_DATE_DT"]) else df["PLAN_DATE"].astype(str)

        merge_keys = ["LINE_CODE", "SKU", "_MERGE_DATE", "SHIFT_NAME", "PLAN_ITEM"]

        merged = pd.merge(
            df_a, df_b,
            on=merge_keys,
            how="outer",
            suffixes=("_A", "_B"),
            indicator=True
        )

        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        # For both, check consistency of PLAN_VALUE
        inconsistent = []
        for _, row in both.iterrows():
            va = row.get(f"{compare_field}_A")
            vb = row.get(f"{compare_field}_B")
            if pd.isna(va) and pd.isna(vb):
                continue
            # If both are numbers and equal, it's consistent
            try:
                if pd.isna(va) or pd.isna(vb):
                    # One missing -> inconsistency
                    inconsistent.append({
                        "key": {k: row.get(k) or row.get(k+"_A") for k in ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"]},
                        "field": compare_field,
                        "value_a": float(va) if not pd.isna(va) else None,
                        "value_b": float(vb) if not pd.isna(vb) else None,
                        "change_type": "INCONSISTENT",
                        "message": "Same historical actual should be identical across versions"
                    })
                else:
                    if float(va) != float(vb):
                        inconsistent.append({
                            "key": {
                                "LINE_CODE": row.get("LINE_CODE"),
                                "SKU": row.get("SKU"),
                                "PLAN_DATE": row.get("_MERGE_DATE"),
                                "SHIFT_NAME": row.get("SHIFT_NAME"),
                                "PLAN_ITEM": row.get("PLAN_ITEM")
                            },
                            "field": compare_field,
                            "value_a": float(va),
                            "value_b": float(vb),
                            "delta": float(vb) - float(va),
                            "change_type": "INCONSISTENT"
                        })
            except Exception as e:
                if str(va) != str(vb):
                    inconsistent.append({
                        "key": {
                            "LINE_CODE": row.get("LINE_CODE"),
                            "SKU": row.get("SKU"),
                            "PLAN_DATE": row.get("_MERGE_DATE"),
                            "SHIFT_NAME": row.get("SHIFT_NAME"),
                            "PLAN_ITEM": row.get("PLAN_ITEM")
                        },
                        "field": compare_field,
                        "value_a": str(va),
                        "value_b": str(vb),
                        "change_type": "INCONSISTENT"
                    })

        # Coverage analysis: find extra dates in B
        # Group added/deleted by date
        extra_in_b = added["_MERGE_DATE"].nunique() if not added.empty else 0
        missing_in_b = deleted["_MERGE_DATE"].nunique() if not deleted.empty else 0

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "added": len(added),
            "deleted": len(deleted),
            "modified": 0,
            "inconsistent": len(inconsistent),
            "coverage": {
                "min_a": str(min_a),
                "max_a": str(max_a),
                "min_b": str(min_b),
                "max_b": str(max_b),
                "extra_dates_in_b": extra_in_b,
                "missing_dates_in_b": missing_in_b,
                "date_range_a": f"{min_a} to {max_a}",
                "date_range_b": f"{min_b} to {max_b}"
            },
            "records": {
                "added": added.head(100).to_dict(orient="records"),
                "deleted": deleted.head(100).to_dict(orient="records"),
                "inconsistent": inconsistent[:100]
            },
            "summary": {
                "inconsistent": len(inconsistent),
                "extra_in_b": len(added),
                "missing_in_b": len(deleted)
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


def get_chart_data_actual(df_a, df_b, line_code=None, sku=None):
    """
    Get time series data for charting actual IO
    Returns aggregated daily data for a specific LINE + SKU
    """
    try:
        # Filter if provided
        if line_code:
            df_a = df_a[df_a["LINE_CODE"] == line_code]
            df_b = df_b[df_b["LINE_CODE"] == line_code]
        if sku:
            df_a = df_a[df_a["SKU"] == sku]
            df_b = df_b[df_b["SKU"] == sku]

        # Group by PLAN_DATE sum PLAN_VALUE
        # Normalize date
        df_a["_DATE"] = pd.to_datetime(df_a["PLAN_DATE"], errors='coerce').dt.strftime("%Y-%m-%d")
        df_b["_DATE"] = pd.to_datetime(df_b["PLAN_DATE"], errors='coerce').dt.strftime("%Y-%m-%d")

        agg_a = df_a.groupby("_DATE")["PLAN_VALUE"].sum().reset_index()
        agg_b = df_b.groupby("_DATE")["PLAN_VALUE"].sum().reset_index()

        # Merge for chart
        merged = pd.merge(agg_a, agg_b, on="_DATE", how="outer", suffixes=("_A", "_B")).sort_values("_DATE")
        merged = merged.fillna(0)

        return {
            "dates": merged["_DATE"].tolist(),
            "values_a": merged["PLAN_VALUE_A"].tolist(),
            "values_b": merged["PLAN_VALUE_B"].tolist()
        }
    except Exception as e:
        return {"error": str(e), "dates": [], "values_a": [], "values_b": []}
