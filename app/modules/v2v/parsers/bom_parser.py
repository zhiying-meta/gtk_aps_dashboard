"""BOM parser"""
import pandas as pd

def parse_bom(file_path: str):
    try:
        df = pd.read_excel(file_path)
        # Normalize column names - ensure we have expected cols
        # Keep only relevant cols
        cols_needed = ["PARENT_PN_CODE", "ITEM_NO", "UNIT_NUM", "LOSS_RATE", "PROCESS_LT", "PN_CODE_PATH", "ITEM_DESC"]
        available = [c for c in cols_needed if c in df.columns]
        df = df[available] if available else df
        return df
    except Exception as e:
        raise e


def diff_bom(df_a, df_b):
    try:
        import pandas as pd
        # Ensure key cols exist
        key_cols = ["PARENT_PN_CODE", "ITEM_NO"]
        # Filter to only rows where key not null?
        if not all(k in df_a.columns and k in df_b.columns for k in key_cols):
            # Fallback: use first 2 cols as keys? Try to find
            # If not found, return simple stats
            return {
                "total_a": len(df_a),
                "total_b": len(df_b),
                "added": 0,
                "deleted": 0,
                "modified": 0,
                "records": [],
                "summary": {"error": "Missing key columns PARENT_PN_CODE, ITEM_NO"}
            }

        # Merge
        merged = pd.merge(df_a, df_b, on=key_cols, how="outer", suffixes=("_A", "_B"), indicator=True)
        added = merged[merged["_merge"] == "right_only"]
        deleted = merged[merged["_merge"] == "left_only"]
        both = merged[merged["_merge"] == "both"]

        modified_records = []
        compare_fields = ["UNIT_NUM", "LOSS_RATE", "PROCESS_LT"]
        for _, row in both.iterrows():
            for field in compare_fields:
                col_a = field + "_A" if field + "_A" in row else field
                col_b = field + "_B" if field + "_B" in row else field
                if col_a not in row or col_b not in row:
                    continue
                va = row[col_a]
                vb = row[col_b]
                # Handle NaN
                if pd.isna(va) and pd.isna(vb):
                    continue
                if va != vb:
                    # Check if both not NaN and diff
                    try:
                        if pd.isna(va) or pd.isna(vb):
                            diff = True
                        else:
                            diff = (float(va) != float(vb)) if isinstance(va, (int,float)) or (str(va).replace('.','').isdigit()) else (str(va) != str(vb))
                            if not diff:
                                continue
                    except:
                        if str(va) == str(vb):
                            continue
                    modified_records.append({
                        "key": {k: row[k] for k in key_cols},
                        "field": field,
                        "value_a": str(va) if not pd.isna(va) else None,
                        "value_b": str(vb) if not pd.isna(vb) else None,
                        "change_type": "MODIFY"
                    })

        return {
            "total_a": len(df_a),
            "total_b": len(df_b),
            "added": len(added),
            "deleted": len(deleted),
            "modified": len(modified_records),
            "unchanged": len(both) - len(set([r["key"]["PARENT_PN_CODE"]+r["key"]["ITEM_NO"] for r in modified_records])) if modified_records else len(both),
            "records": {
                "added": added.head(100).to_dict(orient="records"),
                "deleted": deleted.head(100).to_dict(orient="records"),
                "modified": modified_records[:100]
            },
            "summary": {
                "added": len(added),
                "deleted": len(deleted),
                "modified": len(modified_records)
            }
        }
    except Exception as e:
        return {
            "total_a": len(df_a) if df_a is not None else 0,
            "total_b": len(df_b) if df_b is not None else 0,
            "added": 0,
            "deleted": 0,
            "modified": 0,
            "error": str(e),
            "records": []
        }
