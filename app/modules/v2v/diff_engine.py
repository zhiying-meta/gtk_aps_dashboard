"""
V2V Diff Engine - Core comparison logic - Phase2 with all input tables
"""
import os
import pandas as pd
from typing import Dict

from .config import TABLE_DEFS
from .parsers.bom_parser import parse_bom, diff_bom
from .parsers.fcst_parser import parse_fcst, diff_fcst
from .parsers.actual_parser import diff_actual, get_chart_data_actual
from .parsers.supply_parser import diff_supply, get_chart_data_supply
from .parsers.switch_parser import diff_switch
from .parsers.calendar_parser import diff_calendar, get_chart_data_calendar
from .parsers.item_parser import diff_item
from .parsers.line_parser import diff_line

def load_all_tables_from_folder(folder_path: str, fast_large=False) -> Dict:
    """
    Load all tables from folder
    fast_large: if True, for large tables (actual_io, supply, calendar, plan_output, balance) only load row count quickly via openpyxl, not full df
    For summary speed
    """
    from .utils import scan_folder_for_tables
    import openpyxl
    scan = scan_folder_for_tables(folder_path)
    data = {}
    large_tables = {"actual_io", "supply", "calendar", "plan_output", "balance"}
    for table_key, fpath in scan["tables"].items():
        try:
            if fast_large and table_key in large_tables:
                # Fast row count via openpyxl read_only
                wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
                ws = wb.active
                # Use max_row - 1 as data rows
                # For large files, this is fast
                count = ws.max_row - 1
                wb.close()
                # Create a dummy df with just count? We'll store a small DataFrame with count info
                # For summary we only need counts for large tables in fast mode
                # Create empty df with _row_count attribute
                data[table_key] = {"_row_count": count, "_fast": True, "_path": fpath}
            else:
                # For small tables or when not fast_large, load full df but with needed columns only
                # Determine needed columns from TABLE_DEFS
                needed_cols = None
                if table_key in TABLE_DEFS:
                    defn = TABLE_DEFS[table_key]
                    needed = defn.get("key_fields", []) + defn.get("compare_fields", [])
                    # For fcst, need ID and MAIN_ID etc
                    if table_key == "fcst":
                        needed = ["ID", "PN_CODE"]
                    elif table_key == "fcst_detail":
                        needed = ["MAIN_ID", "ACTUALFIRSTDAYOFWEEK", "ACTUALWEEKVALUE"]
                    elif table_key == "actual_io":
                        needed = ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM", "PLAN_VALUE", "PLAN_TYPE"]
                    elif table_key == "supply":
                        needed = ["PN_CODE", "KITTING_DATE", "KITTING_VALUE", "QTY_REM", "QTY_REM2", "TOTAL_LOSS_QTY"]
                    elif table_key == "switch":
                        needed = None  # we need to handle Unnamed
                    elif table_key == "calendar":
                        needed = ["LINE_CODE", "PLAN_TYPE", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM", "PLAN_VALUE"]
                    elif table_key == "plan_output":
                        needed = ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM", "PLAN_VALUE"]
                    elif table_key == "balance":
                        needed = ["ITEM_CODE", "PLAN_DATE", "SHIFT_NAME", "SHIFT_CODE", "BALANCE_QTY", "SHIFT_OUT_QTY", "PRE_INPUT_QTY"]
                    # Only use needed if all exist, else load all
                    needed_cols = needed

                if needed_cols:
                    try:
                        df = pd.read_excel(fpath, usecols=lambda c: c in needed_cols or any(nc.lower() in str(c).lower() for nc in needed_cols))
                        data[table_key] = df
                    except:
                        df = pd.read_excel(fpath)
                        data[table_key] = df
                else:
                    df = pd.read_excel(fpath)
                    data[table_key] = df
        except Exception as e:
            print(f"Failed to load {table_key} from {fpath}: {e}")
            data[table_key] = None
    return data


def get_row_count_fast(file_path: str) -> int:
    import openpyxl
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        count = ws.max_row - 1
        wb.close()
        return count
    except:
        return 0


def compare_two_versions(folder_a: str, folder_b: str, granularity: str = "week") -> Dict:
    """
    Fast summary: only diff small tables (<5k rows) for quick initial response
    Large tables (actual_io, supply, calendar, plan_output, balance) will be counted via fast row count and detailed diff on-demand
    This makes initial compare <10s instead of 90s
    """
    from .utils import scan_folder_for_tables
    import openpyxl

    # Fast scan to get file list and row counts
    scan_a = scan_folder_for_tables(folder_a)
    scan_b = scan_folder_for_tables(folder_b)

    # For small tables, load full data and diff immediately
    small_tables = ["bom", "fcst", "fcst_detail", "plan_config", "switch", "item", "line"]
    large_tables = ["supply", "calendar", "plan_output", "balance", "plan_input"]  # actual_io removed per user request

    data_a_small = {}
    data_b_small = {}

    def load_with_uscols(fpath, table_key):
        try:
            # Determine needed cols
            needed_map = {
                "bom": ["PARENT_PN_CODE", "ITEM_NO", "UNIT_NUM", "LOSS_RATE", "PROCESS_LT"],
                "fcst": ["ID", "PN_CODE"],
                "fcst_detail": ["MAIN_ID", "ACTUALFIRSTDAYOFWEEK", "ACTUALWEEKVALUE"],
                "plan_config": None,
                "switch": None,
                "item": ["ITEM_NO", "PRODUCT_STYLE", "COLOR", "TYPE"],
                "line": ["LINE_CODE", "LINE_LEVEL", "LINE_TYPE"]
            }
            needed = needed_map.get(table_key)
            if needed:
                try:
                    df = pd.read_excel(fpath, usecols=lambda c: c in needed or any(nc.lower() in str(c).lower() for nc in needed))
                    return df
                except:
                    return pd.read_excel(fpath)
            else:
                return pd.read_excel(fpath)
        except Exception as e:
            print(f"Failed to load {table_key} from {fpath}: {e}")
            return None

    # Load small tables
    for table_key in small_tables:
        if table_key in scan_a["tables"]:
            data_a_small[table_key] = load_with_uscols(scan_a["tables"][table_key], table_key)
        if table_key in scan_b["tables"]:
            data_b_small[table_key] = load_with_uscols(scan_b["tables"][table_key], table_key)

    # Fast row counts for large tables via openpyxl max_row (very fast)
    def fast_count(fpath):
        try:
            wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
            ws = wb.active
            cnt = ws.max_row - 1
            wb.close()
            return cnt
        except:
            return 0

    large_counts_a = {}
    large_counts_b = {}
    for table_key in large_tables:
        if table_key in scan_a["tables"]:
            large_counts_a[table_key] = fast_count(scan_a["tables"][table_key])
        if table_key in scan_b["tables"]:
            large_counts_b[table_key] = fast_count(scan_b["tables"][table_key])

    result = {
        "version_a": {
            "path": folder_a,
            "name": os.path.basename(folder_a),
            "tables": list(scan_a["tables"].keys()),
            "file_count": scan_a["stats"]["total_files"],
            "recognized": scan_a["stats"]["recognized"]
        },
        "version_b": {
            "path": folder_b,
            "name": os.path.basename(folder_b),
            "tables": list(scan_b["tables"].keys()),
            "file_count": scan_b["stats"]["total_files"],
            "recognized": scan_b["stats"]["recognized"]
        },
        "granularity": granularity,
        "summary": {},
        "diffs": {},
        "warnings": []
    }

    # 1. BOM
    try:
        if "bom" in data_a_small and "bom" in data_b_small and data_a_small["bom"] is not None and data_b_small["bom"] is not None:
            diff = diff_bom(data_a_small["bom"], data_b_small["bom"])
            result["diffs"]["bom"] = diff
            result["summary"]["bom"] = {
                "total_a": diff.get("total_a", 0),
                "total_b": diff.get("total_b", 0),
                "added": diff.get("added", 0),
                "deleted": diff.get("deleted", 0),
                "modified": diff.get("modified", 0)
            }
        else:
            result["summary"]["bom"] = {"error": "Missing BOM"}
    except Exception as e:
        result["summary"]["bom"] = {"error": str(e)}

    # 2. FCST
    try:
        if "fcst" in data_a_small and "fcst_detail" in data_a_small and "fcst" in data_b_small and "fcst_detail" in data_b_small:
            if data_a_small["fcst"] is not None and data_a_small["fcst_detail"] is not None and data_b_small["fcst"] is not None and data_b_small["fcst_detail"] is not None:
                diff = diff_fcst(data_a_small["fcst"], data_a_small["fcst_detail"], data_b_small["fcst"], data_b_small["fcst_detail"], granularity=granularity)
                result["diffs"]["fcst"] = diff
                result["summary"]["fcst"] = {
                    "total_a": diff.get("total_a", 0),
                    "total_b": diff.get("total_b", 0),
                    "added": diff.get("added", 0),
                    "deleted": diff.get("deleted", 0),
                    "modified": diff.get("modified", 0)
                }
            else:
                result["summary"]["fcst"] = {"error": "FCST data is None"}
        else:
            result["summary"]["fcst"] = {"error": "Missing FCST"}
    except Exception as e:
        result["summary"]["fcst"] = {"error": str(e)}

    # 3. Plan Config
    try:
        if "plan_config" in data_a_small and "plan_config" in data_b_small:
            df_a = data_a_small["plan_config"]
            df_b = data_b_small["plan_config"]
            if df_a is not None and df_b is not None and not df_a.empty and not df_b.empty:
                row_a = df_a.iloc[0].to_dict()
                row_b = df_b.iloc[0].to_dict()
                all_keys = set(row_a.keys()) | set(row_b.keys())
                modified = []
                for k in all_keys:
                    va = row_a.get(k)
                    vb = row_b.get(k)
                    if pd.isna(va) and pd.isna(vb):
                        continue
                    if str(va) != str(vb):
                        modified.append({
                            "field": k,
                            "value_a": str(va) if not pd.isna(va) else None,
                            "value_b": str(vb) if not pd.isna(vb) else None,
                            "change_type": "MODIFY"
                        })
                result["diffs"]["plan_config"] = {
                    "total_a": 1,
                    "total_b": 1,
                    "modified": len(modified),
                    "records": modified
                }
                result["summary"]["plan_config"] = {
                    "total_a": 1,
                    "total_b": 1,
                    "modified": len(modified),
                    "added": 0,
                    "deleted": 0
                }
            else:
                result["summary"]["plan_config"] = {"error": "Empty config"}
        else:
            result["summary"]["plan_config"] = {"error": "Missing config"}
    except Exception as e:
        result["summary"]["plan_config"] = {"error": str(e)}

    # 4. Switch (small)
    try:
        if "switch" in data_a_small and "switch" in data_b_small and data_a_small["switch"] is not None and data_b_small["switch"] is not None:
            diff = diff_switch(data_a_small["switch"], data_b_small["switch"])
            result["diffs"]["switch"] = diff
            result["summary"]["switch"] = {
                "total_a": diff.get("total_a", 0),
                "total_b": diff.get("total_b", 0),
                "added": diff.get("added", 0),
                "deleted": diff.get("deleted", 0),
                "modified": diff.get("modified", 0)
            }
        else:
            result["summary"]["switch"] = {"error": "Missing switch", "total_a": large_counts_a.get("switch",0), "total_b": large_counts_b.get("switch",0)}
    except Exception as e:
        result["summary"]["switch"] = {"error": str(e)}

    # 5. Item
    try:
        if "item" in data_a_small and "item" in data_b_small and data_a_small["item"] is not None and data_b_small["item"] is not None:
            diff = diff_item(data_a_small["item"], data_b_small["item"])
            result["diffs"]["item"] = diff
            result["summary"]["item"] = {
                "total_a": diff.get("total_a", 0),
                "total_b": diff.get("total_b", 0),
                "added": diff.get("added", 0),
                "deleted": diff.get("deleted", 0),
                "modified": diff.get("modified", 0)
            }
        else:
            result["summary"]["item"] = {"error": "Missing item"}
    except Exception as e:
        result["summary"]["item"] = {"error": str(e)}

    # 6. Line
    try:
        if "line" in data_a_small and "line" in data_b_small and data_a_small["line"] is not None and data_b_small["line"] is not None:
            diff = diff_line(data_a_small["line"], data_b_small["line"])
            result["diffs"]["line"] = diff
            result["summary"]["line"] = {
                "total_a": diff.get("total_a", 0),
                "total_b": diff.get("total_b", 0),
                "added": diff.get("added", 0),
                "deleted": diff.get("deleted", 0),
                "modified": diff.get("modified", 0)
            }
        else:
            result["summary"]["line"] = {"error": "Missing line"}
    except Exception as e:
        result["summary"]["line"] = {"error": str(e)}

    # 7. Large tables: fast counts only for summary, detailed diff on-demand via /v2v/api/diff/<table>
    # Include plan_input as virtual large table
    all_large = large_tables + ["plan_input"]
    for table_key in all_large:
        try:
            cnt_a = large_counts_a.get(table_key, 0)
            cnt_b = large_counts_b.get(table_key, 0)
            # For large tables, we don't compute diff in summary for speed, just show counts
            # Frontend will show "Click to load detailed diff" and call /v2v/api/diff/<table>
            result["summary"][table_key] = {
                "total_a": cnt_a,
                "total_b": cnt_b,
                "added": 0,
                "deleted": 0,
                "modified": 0,
                "note": "Large table: detailed diff on-demand via tab (fast summary mode)",
                "fast_summary": True
            }
        except Exception as e:
            result["summary"][table_key] = {"error": str(e)}

    # Overall
    total_added = sum([v.get("added", 0) for v in result["summary"].values() if isinstance(v, dict)])
    total_deleted = sum([v.get("deleted", 0) for v in result["summary"].values() if isinstance(v, dict)])
    total_modified = sum([v.get("modified", 0) for v in result["summary"].values() if isinstance(v, dict)])

    result["overall"] = {
        "total_tables_a": len(scan_a["tables"]),
        "total_tables_b": len(scan_b["tables"]),
        "total_added": total_added,
        "total_deleted": total_deleted,
        "total_modified": total_modified,
        "fast_summary": True,
        "note": "Large tables (actual_io, supply, calendar, plan_output, balance) use fast row-count for summary; detailed diff loaded on tab click"
    }

    return result


def load_single_table(folder_path: str, table_key: str):
    from .utils import scan_folder_for_tables
    scan = scan_folder_for_tables(folder_path)
    if table_key not in scan["tables"]:
        if table_key == "fcst":
            main_path = scan["tables"].get("fcst")
            detail_path = scan["tables"].get("fcst_detail")
            if main_path and detail_path:
                try:
                    df_main = pd.read_excel(main_path)
                    df_detail = pd.read_excel(detail_path)
                    return {"fcst": df_main, "fcst_detail": df_detail}
                except:
                    return {}
            return {}
        return None
    fpath = scan["tables"][table_key]
    try:
        # Optimized column selection for large tables to improve speed
        needed_map = {
            "balance": ["ITEM_CODE", "PLAN_DATE", "SHIFT_NAME", "SHIFT_CODE", "BALANCE_QTY", "SHIFT_OUT_QTY", "PRE_INPUT_QTY"],
            "plan_output": ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM", "PLAN_VALUE"],
            "supply": ["PN_CODE", "KITTING_DATE", "KITTING_VALUE", "QTY_REM", "QTY_REM2"],
            "calendar": ["LINE_CODE", "PLAN_TYPE", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM", "PLAN_VALUE"],
            "bom": ["PARENT_PN_CODE", "ITEM_NO", "UNIT_NUM", "LOSS_RATE", "PROCESS_LT", "PN_CODE_PATH"],
            "item": ["ITEM_NO", "PRODUCT_STYLE", "COLOR", "TYPE", "STYLE", "PRODUCT_TYPE", "MAKE_OR_BUY", "PRODUCT_CATEGORY", "PRODUCT_LINE", "ITEM_DESC"],
            "line": ["LINE_CODE", "LINE_LEVEL", "LINE_TYPE", "IS_MAIN_PROCESS", "LINE_NAME"],
        }
        needed = needed_map.get(table_key)
        if needed:
            try:
                # Use usecols to speed up reading
                df = pd.read_excel(fpath, usecols=lambda c: c in needed or any(nc.lower() in str(c).lower() for nc in needed))
                # If we filtered too aggressively and missing key cols, fallback to full read
                if table_key == "balance" and "ITEM_CODE" not in df.columns:
                    df = pd.read_excel(fpath)
                elif table_key == "plan_output" and "SKU" not in df.columns:
                    df = pd.read_excel(fpath)
                return df
            except Exception as e:
                # Fallback
                df = pd.read_excel(fpath)
                return df
        else:
            df = pd.read_excel(fpath)
            return df
    except Exception as e:
        print(f"Failed to load {table_key} from {fpath}: {e}")
        return None


def get_detailed_diff(folder_a: str, folder_b: str, table_name: str, granularity: str = "week", filters: Dict = None, page: int = 1, page_size: int = 100):
    # Optimized to load only needed tables
    if table_name == "fcst":
        data_a_fcst = load_single_table(folder_a, "fcst")
        data_a_detail = load_single_table(folder_a, "fcst_detail")
        data_b_fcst = load_single_table(folder_b, "fcst")
        data_b_detail = load_single_table(folder_b, "fcst_detail")
        data_a = {"fcst": data_a_fcst, "fcst_detail": data_a_detail}
        data_b = {"fcst": data_b_fcst, "fcst_detail": data_b_detail}
    else:
        df_a = load_single_table(folder_a, table_name)
        df_b = load_single_table(folder_b, table_name)
        data_a = {table_name: df_a}
        data_b = {table_name: df_b}

    def paginate_records(records, page, page_size, change_filter=None):
        # Apply change_type filter if needed
        if change_filter and change_filter != "ALL":
            if change_filter == "ADD":
                records = [r for r in records if r.get("change_type") in ["ADD", "added"] or "right_only" in str(r.get("_merge",""))]
            elif change_filter == "DEL":
                records = [r for r in records if r.get("change_type") in ["DEL", "deleted"] or "left_only" in str(r.get("_merge",""))]
            elif change_filter == "MODIFY":
                records = [r for r in records if r.get("change_type") in ["MODIFY", "INCONSISTENT"]]
            elif change_filter == "INCONSISTENT":
                records = [r for r in records if r.get("change_type") == "INCONSISTENT"]
        total = len(records)
        start = (page-1)*page_size
        end = start + page_size
        return records[start:end], total

    change_filter = filters.get("change_type") if filters else "ALL"

    if table_name == "bom":
        if "bom" not in data_a or "bom" not in data_b or data_a["bom"] is None or data_b["bom"] is None:
            return {"error": "BOM missing"}
        diff = diff_bom(data_a["bom"], data_b["bom"])
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            for rec in diff["records"].get("added", []):
                all_records.append({**rec, "change_type": "ADD"})
            for rec in diff["records"].get("deleted", []):
                all_records.append({**rec, "change_type": "DEL"})
            for rec in diff["records"].get("modified", []):
                all_records.append(rec)
        else:
            all_records = diff.get("records", [])
        paged, total = paginate_records(all_records, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {})
        }

    elif table_name == "fcst":
        if not all(k in data_a and k in data_b for k in ["fcst", "fcst_detail"]) or any(data_a[k] is None or data_b[k] is None for k in ["fcst", "fcst_detail"]):
            return {"error": "FCST missing"}
        diff = diff_fcst(data_a["fcst"], data_a["fcst_detail"], data_b["fcst"], data_b["fcst_detail"], granularity=granularity)
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            for rec in diff["records"].get("added", []):
                all_records.append({**rec, "change_type": "ADD"})
            for rec in diff["records"].get("deleted", []):
                all_records.append({**rec, "change_type": "DEL"})
            for rec in diff["records"].get("modified", []):
                all_records.append(rec)
        paged, total = paginate_records(all_records, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {})
        }

    elif table_name == "plan_config":
        if data_a.get("plan_config") is None or data_b.get("plan_config") is None:
            return {"error": "Plan config missing"}
        df_a = data_a["plan_config"]
        df_b = data_b["plan_config"]
        if df_a.empty or df_b.empty:
            return {"table": table_name, "pagination": {"page":1,"page_size":page_size,"total":0}, "records": [], "message": "Empty config"}
        row_a = df_a.iloc[0].to_dict()
        row_b = df_b.iloc[0].to_dict()
        all_keys = set(row_a.keys()) | set(row_b.keys())
        modified = []
        for k in all_keys:
            va = row_a.get(k)
            vb = row_b.get(k)
            if pd.isna(va) and pd.isna(vb):
                continue
            if str(va) != str(vb):
                modified.append({
                    "field": k,
                    "value_a": str(va) if not pd.isna(va) else None,
                    "value_b": str(vb) if not pd.isna(vb) else None,
                    "change_type": "MODIFY"
                })
        paged, total = paginate_records(modified, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": {"modified": total}
        }

    elif table_name == "actual_io":
        if data_a.get("actual_io") is None or data_b.get("actual_io") is None:
            return {"error": "actual_io missing"}
        diff = diff_actual(data_a["actual_io"], data_b["actual_io"])
        # Combine all record types
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            # Inconsistent is most important
            for rec in diff["records"].get("inconsistent", []):
                all_records.append(rec)
            for rec in diff["records"].get("added", []):
                # Convert added record to display format
                all_records.append({"key": {"RAW": str(rec)[:200]}, "field": "PLAN_VALUE", "value_a": None, "value_b": rec.get("PLAN_VALUE_B") if isinstance(rec, dict) else str(rec), "change_type": "ADD", "raw": rec})
            for rec in diff["records"].get("deleted", []):
                all_records.append({"key": {"RAW": str(rec)[:200]}, "field": "PLAN_VALUE", "value_a": rec.get("PLAN_VALUE_A") if isinstance(rec, dict) else str(rec), "value_b": None, "change_type": "DEL", "raw": rec})
        # For inconsistent, already in desired format
        paged, total = paginate_records(all_records, page, page_size, change_filter if change_filter != "ALL" else None)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {}),
            "coverage": diff.get("coverage", {})
        }

    elif table_name == "supply":
        if data_a.get("supply") is None or data_b.get("supply") is None:
            return {"error": "supply missing"}
        diff = diff_supply(data_a["supply"], data_b["supply"], granularity=granularity)
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            for rec in diff["records"].get("added", []):
                all_records.append({**rec, "change_type": "ADD"} if isinstance(rec, dict) and "change_type" not in rec else {**rec, "change_type": rec.get("change_type","ADD")})
            for rec in diff["records"].get("deleted", []):
                all_records.append({**rec, "change_type": "DEL"} if isinstance(rec, dict) and "change_type" not in rec else {**rec, "change_type": rec.get("change_type","DEL")})
            for rec in diff["records"].get("modified", []):
                all_records.append(rec)
        paged, total = paginate_records(all_records, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {})
        }

    elif table_name == "switch":
        if data_a.get("switch") is None or data_b.get("switch") is None:
            return {"error": "switch missing"}
        diff = diff_switch(data_a["switch"], data_b["switch"])
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            for rec in diff["records"].get("added", []):
                all_records.append({**rec, "change_type": "ADD"})
            for rec in diff["records"].get("deleted", []):
                all_records.append({**rec, "change_type": "DEL"})
            for rec in diff["records"].get("modified", []):
                all_records.append(rec)
        paged, total = paginate_records(all_records, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {})
        }

    elif table_name == "calendar":
        if data_a.get("calendar") is None or data_b.get("calendar") is None:
            return {"error": "calendar missing"}
        diff = diff_calendar(data_a["calendar"], data_b["calendar"], granularity=granularity)
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            for rec in diff["records"].get("added", []):
                all_records.append({**rec, "change_type": "ADD"})
            for rec in diff["records"].get("deleted", []):
                all_records.append({**rec, "change_type": "DEL"})
            for rec in diff["records"].get("modified", []):
                all_records.append(rec)
        paged, total = paginate_records(all_records, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {})
        }

    elif table_name == "item":
        if data_a.get("item") is None or data_b.get("item") is None:
            return {"error": "item missing"}
        diff = diff_item(data_a["item"], data_b["item"])
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            for rec in diff["records"].get("added", []):
                all_records.append({**rec, "change_type": "ADD"})
            for rec in diff["records"].get("deleted", []):
                all_records.append({**rec, "change_type": "DEL"})
            for rec in diff["records"].get("modified", []):
                all_records.append(rec)
        paged, total = paginate_records(all_records, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {})
        }

    elif table_name == "line":
        if data_a.get("line") is None or data_b.get("line") is None:
            return {"error": "line missing"}
        diff = diff_line(data_a["line"], data_b["line"])
        all_records = []
        if "records" in diff and isinstance(diff["records"], dict):
            for rec in diff["records"].get("added", []):
                all_records.append({**rec, "change_type": "ADD"})
            for rec in diff["records"].get("deleted", []):
                all_records.append({**rec, "change_type": "DEL"})
            for rec in diff["records"].get("modified", []):
                all_records.append(rec)
        paged, total = paginate_records(all_records, page, page_size, change_filter)
        return {
            "table": table_name,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "records": paged,
            "summary": diff.get("summary", {})
        }

    elif table_name == "plan_output":
        # Refactored: Fixed SKU level, no dimension builder, default only_diff
        from .parsers.plan_output_parser import diff_plan_output as diff_plan_output_agg
        if data_a.get("plan_output") is None or data_b.get("plan_output") is None:
            return {"error": "plan_output missing"}
        # Force SKU level per user request - ignore incoming group_by
        group_by = ["SKU"]
        real_filters = {}
        if filters:
            for k,v in filters.items():
                if k in ["SKU", "WEEK", "DATE", "_WEEK", "_DATE", "_MONTH", "MONTH", "PLAN_DATE", "SHIFT_NAME", "LINE_CODE", "PLAN_ITEM"]:
                    if v:
                        real_filters[k] = v
                # Support generic sku/week filters
                if k == "sku" and v:
                    real_filters["SKU"] = v
                if k == "week" and v:
                    real_filters["WEEK"] = v
        only_diff = filters.get("only_diff", True) if filters else True
        if isinstance(only_diff, str):
            only_diff = only_diff.lower() != "false"
        threshold_abs = float(filters.get("threshold_abs", 0)) if filters and filters.get("threshold_abs") else 0
        threshold_pct = float(filters.get("threshold_pct", 0)) if filters and filters.get("threshold_pct") else 0
        sort_by = filters.get("sort", "abs_diff_desc") if filters else "abs_diff_desc"
        page = int(filters.get("page", page)) if filters and filters.get("page") else page
        page_size = int(filters.get("page_size", page_size)) if filters and filters.get("page_size") else page_size
        cum = filters.get("cum", False) if filters else False  # Default cum False now, per fixed table logic
        if isinstance(cum, str):
            cum = cum.lower() in ["true", "1", "yes", "cum"]

        diff_result = diff_plan_output_agg(
            data_a["plan_output"], data_b["plan_output"],
            group_by=group_by,
            granularity=granularity,
            filters=real_filters,
            only_diff=only_diff,
            threshold_abs=threshold_abs,
            threshold_pct=threshold_pct,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
            cum=cum
        )
        if "error" in diff_result:
            return diff_result
        # Normalize to expected format
        return {
            "table": table_name,
            "pagination": diff_result.get("pagination", {"page": page, "page_size": page_size, "total": diff_result.get("total_after_filter", 0)}),
            "records": diff_result.get("records", []),
            "summary": {
                "total_a": diff_result.get("total_a", 0),
                "total_b": diff_result.get("total_b", 0),
                "aggregated_a": diff_result.get("aggregated_a", 0),
                "aggregated_b": diff_result.get("aggregated_b", 0),
                "total_after_filter": diff_result.get("total_after_filter", 0)
            },
            "group_by": group_by,
            "granularity": granularity,
            "filters": real_filters,
            "valid_keys": diff_result.get("valid_keys", [])
        }

    elif table_name == "balance":
        from .parsers.balance_parser import diff_balance as diff_balance_agg
        if data_a.get("balance") is None or data_b.get("balance") is None:
            return {"error": "balance missing"}
        # Force SKU level (ITEM_CODE + time) per user request - no dimension builder
        group_by = ["ITEM_CODE"]
        real_filters = {}
        if filters:
            for k,v in filters.items():
                if k in ["ITEM_CODE", "WEEK", "DATE", "_WEEK", "_DATE", "_MONTH", "MONTH", "PLAN_DATE", "SHIFT_NAME", "SKU"]:
                    if v:
                        real_filters[k] = v
                if k == "week" and v:
                    real_filters["WEEK"] = v
                if k in ["item", "sku"] and v:
                    real_filters["ITEM_CODE"] = v
                if k == "MONTH" and v:
                    real_filters["_MONTH"] = v
        only_diff = filters.get("only_diff", True) if filters else True
        if isinstance(only_diff, str):
            only_diff = only_diff.lower() != "false"
        threshold_abs = float(filters.get("threshold_abs", 0)) if filters and filters.get("threshold_abs") else 0
        threshold_pct = float(filters.get("threshold_pct", 0)) if filters and filters.get("threshold_pct") else 0
        compare_field = filters.get("compare_field", "BALANCE_QTY") if filters else "BALANCE_QTY"

        diff_result = diff_balance_agg(
            data_a["balance"], data_b["balance"],
            group_by=group_by,
            granularity=granularity,
            filters=real_filters,
            only_diff=only_diff,
            threshold_abs=threshold_abs,
            threshold_pct=threshold_pct,
            sort_by=filters.get("sort", "abs_diff_desc") if filters else "abs_diff_desc",
            page=page,
            page_size=page_size,
            compare_field=compare_field
        )
        if "error" in diff_result:
            return diff_result
        return {
            "table": table_name,
            "pagination": diff_result.get("pagination", {}),
            "records": diff_result.get("records", []),
            "summary": {
                "total_a": diff_result.get("total_a", 0),
                "total_b": diff_result.get("total_b", 0),
                "total_after_filter": diff_result.get("total_after_filter", 0)
            },
            "group_by": group_by,
            "granularity": granularity,
            "filters": real_filters,
            "valid_keys": diff_result.get("valid_keys", [])
        }

    elif table_name == "plan_input":
        # Virtual table: FCST aggregated, fixed SKU level
        from .parsers.plan_input_parser import diff_plan_input as diff_pi
        fcst_main_a = load_single_table(folder_a, "fcst")
        fcst_detail_a = load_single_table(folder_a, "fcst_detail")
        fcst_main_b = load_single_table(folder_b, "fcst")
        fcst_detail_b = load_single_table(folder_b, "fcst_detail")
        if fcst_main_a is None or fcst_detail_a is None or fcst_main_b is None or fcst_detail_b is None:
            return {"error": "FCST data missing for plan_input"}

        group_by = ["PN_CODE"]  # Force SKU level

        real_filters = {}
        if filters:
            for k,v in filters.items():
                if k in ["PN_CODE", "SKU", "WEEK", "_WEEK", "_MONTH", "MONTH", "ITEM_CODE", "DATE", "_DATE"]:
                    if v:
                        real_filters[k] = v
                if k == "sku" and v:
                    real_filters["PN_CODE"] = v
                if k == "week" and v:
                    real_filters["WEEK"] = v

        only_diff = filters.get("only_diff", True) if filters else True
        if isinstance(only_diff, str):
            only_diff = only_diff.lower() != "false"
        threshold_abs = float(filters.get("threshold_abs", 0)) if filters and filters.get("threshold_abs") else 0

        diff_result = diff_pi(
            fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b,
            None, None,
            group_by=group_by,
            granularity=granularity,
            filters=real_filters,
            only_diff=only_diff,
            threshold_abs=threshold_abs
        )
        if "error" in diff_result:
            return diff_result
        return {
            "table": table_name,
            "pagination": diff_result.get("pagination", {"page": page, "page_size": page_size, "total": diff_result.get("total_after_filter", 0)}),
            "records": diff_result.get("records", []),
            "summary": {
                "total_a": diff_result.get("total_a", 0),
                "total_b": diff_result.get("total_b", 0),
                "total_after_filter": diff_result.get("total_after_filter", 0)
            },
            "group_by": group_by,
            "granularity": granularity,
            "filters": real_filters
        }

    else:
        return {
            "table": table_name,
            "pagination": {"page": 1, "page_size": page_size, "total": 0},
            "records": [],
            "message": f"Detailed diff for {table_name} not implemented"
        }


def get_chart_data(folder_a: str, folder_b: str, table_name: str, **kwargs):
    """
    Get chart data for a table
    kwargs: pn_code, line_code, plan_type, etc.
    """
    # For virtual tables like plan_input, we need special handling
    if table_name == "plan_input":
        from .parsers.plan_input_parser import get_chart_data_plan_input as chart_pi
        fcst_main_a = load_single_table(folder_a, "fcst")
        fcst_detail_a = load_single_table(folder_a, "fcst_detail")
        fcst_main_b = load_single_table(folder_b, "fcst")
        fcst_detail_b = load_single_table(folder_b, "fcst_detail")
        if any(x is None for x in [fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b]):
            return {"error": "FCST data missing for plan_input chart"}
        pn_code = kwargs.get("pn_code") or kwargs.get("sku") or kwargs.get("item_code")
        granularity = kwargs.get("granularity", "week")
        return chart_pi(fcst_main_a, fcst_detail_a, fcst_main_b, fcst_detail_b, pn_code=pn_code, granularity=granularity)

    df_a = load_single_table(folder_a, table_name)
    df_b = load_single_table(folder_b, table_name)
    if df_a is None or df_b is None:
        return {"error": f"Missing {table_name}"}

    if table_name == "supply":
        pn_code = kwargs.get("pn_code")
        return get_chart_data_supply(df_a, df_b, pn_code=pn_code)
    elif table_name == "calendar":
        line_code = kwargs.get("line_code")
        plan_type = kwargs.get("plan_type", "UPH")
        shift = kwargs.get("shift_name", "白班")
        return get_chart_data_calendar(df_a, df_b, line_code=line_code, plan_type=plan_type, shift_name=shift)
    elif table_name == "actual_io":
        line_code = kwargs.get("line_code")
        sku = kwargs.get("sku")
        return get_chart_data_actual(df_a, df_b, line_code=line_code, sku=sku)
    elif table_name == "plan_output":
        from .parsers.plan_output_parser import get_chart_data_plan_output as chart_po
        line_code = kwargs.get("line_code")
        sku = kwargs.get("sku")
        granularity = kwargs.get("granularity", "day")
        filters = {}
        if line_code:
            filters["LINE_CODE"] = line_code
        if sku:
            filters["SKU"] = sku
        for k in ["LINE_CODE", "SKU", "WEEK", "PLAN_ITEM"]:
            if kwargs.get(k.lower()) and k.lower() not in ["line_code", "sku"]:
                filters[k] = kwargs.get(k.lower())
        return chart_po(df_a, df_b, group_by=[], filters=filters, granularity=granularity, line_code=line_code, sku=sku)
    elif table_name == "balance":
        from .parsers.balance_parser import get_chart_data_balance as chart_bal
        item_code = kwargs.get("item_code") or kwargs.get("sku") or kwargs.get("pn_code")
        granularity = kwargs.get("granularity", "day")
        compare_field = kwargs.get("compare_field", "BALANCE_QTY")
        return chart_bal(df_a, df_b, item_code=item_code, granularity=granularity, compare_field=compare_field)
    else:
        return {"error": f"Chart not supported for {table_name}"}
