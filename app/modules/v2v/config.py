# V2V Module Config
# Default granularity for output comparison
DEFAULT_GRANULARITY = "week"  # week | day | shift
SUPPORTED_GRANULARITIES = ["week", "day", "shift"]

# Table definitions - 12 tables (9 input + 2 output + 1 extra fcst master/detail split)
TABLE_DEFS = {
    # Input tables
    "bom": {
        "keywords": ["bom", "BOM快照"],
        "display_name": "BOM快照",
        "category": "input",
        "key_fields": ["PARENT_PN_CODE", "ITEM_NO"],
        "compare_fields": ["UNIT_NUM", "LOSS_RATE", "PROCESS_LT", "PN_CODE_PATH"],
        "icon": "📦"
    },
    "fcst": {
        "keywords": ["fcst主表", "FCST主表", "fcst_main", "forecast_main"],
        "display_name": "FCST主表",
        "category": "input",
        "key_fields": ["PN_CODE"],
        "compare_fields": [],
        "icon": "📊",
        "needs_join": True,  # needs detail
        "join_table": "fcst_detail"
    },
    "fcst_detail": {
        "keywords": ["fcst明细", "FCST明细", "fcst_detail", "forecast_detail"],
        "display_name": "FCST明细表",
        "category": "input",
        "key_fields": ["MAIN_ID", "ACTUALFIRSTDAYOFWEEK"],
        "compare_fields": ["ACTUALWEEKVALUE"],
        "icon": "📈"
    },
    "actual_io": {
        "keywords": ["实际值", "I_O", "actual_io", "io_实际"],
        "display_name": "I_O实际值表",
        "category": "input",
        "key_fields": ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"],
        "compare_fields": ["PLAN_VALUE"],
        "icon": "🏭"
    },
    "supply": {
        "keywords": ["supply", "供应", "kitting", "CTB"],
        "display_name": "Supply供应表",
        "category": "input",
        "key_fields": ["PN_CODE", "KITTING_DATE"],
        "compare_fields": ["KITTING_VALUE", "QTY_REM", "QTY_REM2", "TOTAL_LOSS_QTY"],
        "icon": "🚚"
    },
    "switch": {
        "keywords": ["切换矩阵", "switch"],
        "display_name": "切换矩阵快照",
        "category": "input",
        "key_fields": ["LINE_CODE", "BEFORE_PN_CODE", "AFTER_PN_CODE"],
        "compare_fields": ["SWITCH_DURATION"],
        "icon": "🔀"
    },
    "item": {
        "keywords": ["料号快照", "item_master", "material"],
        "display_name": "料号快照表",
        "category": "input",
        "key_fields": ["ITEM_NO"],
        "compare_fields": ["PRODUCT_STYLE", "COLOR", "TYPE"],
        "icon": "🏷️"
    },
    "line": {
        "keywords": ["线体快照", "line_master"],
        "display_name": "线体快照表",
        "category": "input",
        "key_fields": ["LINE_CODE"],
        "compare_fields": ["LINE_LEVEL", "LINE_TYPE", "IS_MAIN_PROCESS"],
        "icon": "🧵"
    },
    "calendar": {
        "keywords": ["线体日历", "calendar"],
        "display_name": "线体日历快照",
        "category": "input",
        "key_fields": ["LINE_CODE", "PLAN_TYPE", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"],
        "compare_fields": ["PLAN_VALUE"],
        "icon": "📅"
    },
    "plan_config": {
        "keywords": ["计划设置", "plan_config", "plan_setting"],
        "display_name": "计划设置表",
        "category": "input",
        "key_fields": ["ID"],
        "compare_fields": [],  # all fields except ID,MPS...
        "icon": "⚙️"
    },
    # Output tables
    "plan_output": {
        "keywords": ["排产结果", "plan_output", "排产结果快照"],
        "display_name": "排产结果快照_输出",
        "category": "output",
        "key_fields": ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"],
        "compare_fields": ["PLAN_VALUE"],
        "icon": "📋",
        "supports_granularity": True
    },
    "balance": {
        "keywords": ["结存", "balance", "wio", "onhand"],
        "display_name": "结存表_输出",
        "category": "output",
        "key_fields": ["ITEM_CODE", "PLAN_DATE", "SHIFT_NAME"],
        "compare_fields": ["BALANCE_QTY", "SHIFT_OUT_QTY", "PRE_INPUT_QTY"],
        "icon": "📦",
        "supports_granularity": True
    }
}

# For display grouping
INPUT_TABLES = [k for k, v in TABLE_DEFS.items() if v["category"] == "input"]
OUTPUT_TABLES = [k for k, v in TABLE_DEFS.items() if v["category"] == "output"]

# Upload limits
MAX_UPLOAD_SIZE_MB = 200
SUPPORTED_EXTENSIONS = [".xlsx"]

# Diff thresholds
DEFAULT_DIFF_THRESHOLD = 0  # show all diffs
DEFAULT_TOP_N = 1000  # max diff records to return in one page

# For folder-based version naming, strip these suffixes for cleaner display
VERSION_NAME_CLEAN_PATTERNS = [
    "_gated", "_v2", "_v3", "Ivy-", "APS-"
]
