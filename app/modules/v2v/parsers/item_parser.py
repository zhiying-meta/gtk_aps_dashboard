"""
Item Master parser - 料号快照表
Key: ITEM_NO
Compare: dynamic - compare all common columns for modified detection
Fix: ensure added/deleted records are returned in consistent format with key dict
"""
import pandas as pd

def parse_item(file_path: str):
    df = pd.read_excel(file_path)
    return df

def diff_item(df_a, df_b):
    try:
        key = "ITEM_NO"
        # Core compare fields - expanded to cover real columns
        base_compare_fields = ["PRODUCT_STYLE", "COLOR", "TYPE", "STYLE", "PRODUCT_TYPE", "MAKE_OR_BUY", "PRODUCT_CATEGORY", "PRODUCT_LINE", "ITEM_DESC", "UNIT", "PURPOSE"]

        if key not in df_a.columns or key not in df_b.columns:
            return {"total_a": len(df_a), "total_b": len(df_b), "added":0,"deleted":0,"modified":0, "error": f"Missing {key}", "records":[]}

        merged = pd.merge(df_a, df_b, on=key, how="outer", suffixes=("_A","_B"), indicator=True)
        added_df = merged[merged["_merge"] == "right_only"]
        deleted_df = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        # Determine actual compare fields present in both DataFrames
        common_cols = set(df_a.columns) & set(df_b.columns)
        compare_fields = [c for c in base_compare_fields if c in common_cols]
        # Also include any other columns that differ except key and ID-like
        # If base list empty or too few, compare all non-key common columns
        if len(compare_fields) < 3:
            exclude = {key, "ID", "MPS_RECORD_CODE", "ORG_CODE", "CREATE_BY", "CREATE_TIME", "APS_CONSTRAIT_START_DATE", "APS_CONSTRAIT_END_DATE"}
            compare_fields = [c for c in common_cols if c not in exclude]

        modified = []
        for _, row in both.iterrows():
            for field in compare_fields:
                col_a = field + "_A"
                col_b = field + "_B"
                if col_a not in row or col_b not in row:
                    continue
                va = row[col_a]
                vb = row[col_b]
                if pd.isna(va) and pd.isna(vb):
                    continue
                if str(va) != str(vb):
                    modified.append({
                        "key": {key: row[key]},
                        "field": field,
                        "value_a": str(va) if not pd.isna(va) else None,
                        "value_b": str(vb) if not pd.isna(vb) else None,
                        "change_type": "MODIFY",
                        "ITEM_NO": row[key]
                    })

        # Build added records with proper key wrapper
        def build_records(sub_df, change_type):
            recs = []
            for _, r in sub_df.head(100).iterrows():
                item_no = r.get(key) if key in r else r.get(f"{key}_A") or r.get(f"{key}_B")
                # Fallback: try to find ITEM_NO from column
                if pd.isna(item_no):
                    # search for any column containing ITEM_NO
                    for c in sub_df.columns:
                        if "ITEM_NO" in c and pd.notna(r.get(c)):
                            item_no = r.get(c)
                            break
                recs.append({
                    "key": {key: str(item_no) if not pd.isna(item_no) else "Unknown"},
                    "field": key,
                    "ITEM_NO": str(item_no) if not pd.isna(item_no) else "Unknown",
                    "value_a": None if change_type == "ADD" else str(item_no),
                    "value_b": str(item_no) if change_type == "ADD" else None,
                    "change_type": change_type,
                    # include some context columns if present
                    "PRODUCT_STYLE": str(r.get("PRODUCT_STYLE_B") or r.get("PRODUCT_STYLE_A") or "")[:100],
                    "COLOR": str(r.get("COLOR_B") or r.get("COLOR_A") or "")[:100],
                    "TYPE": str(r.get("TYPE_B") or r.get("TYPE_A") or "")[:100],
                })
            return recs

        added_recs = build_records(added_df, "ADD")
        deleted_recs = build_records(deleted_df, "DEL")

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "added": len(added_df),
            "deleted": len(deleted_df),
            "modified": len(modified),
            "records": {
                "added": added_recs,
                "deleted": deleted_recs,
                "modified": modified[:100]
            },
            "summary": {
                "added": len(added_df),
                "deleted": len(deleted_df),
                "modified": len(modified)
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"total_a": len(df_a) if 'df_a' in locals() else 0, "total_b": len(df_b) if 'df_b' in locals() else 0, "added":0,"deleted":0,"modified":0,"error":str(e),"records":[]}
