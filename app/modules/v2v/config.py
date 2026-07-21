# V2V Module Config
# Default granularity for output comparison
DEFAULT_GRANULARITY = "week"  # week | day | shift
SUPPORTED_GRANULARITIES = ["week", "day", "shift"]

# Table definitions - 13 tables (9 input + 2 output + 1 fcst detail + 1 virtual plan_input)
TABLE_DEFS = {
    # Input tables
    "bom": {
        "keywords": ["bom", "BOM"],
        "display_name": "BOM Snapshot",
        "category": "input",
        "key_fields": ["PARENT_PN_CODE", "ITEM_NO"],
        "compare_fields": ["UNIT_NUM", "LOSS_RATE", "PROCESS_LT", "PN_CODE_PATH"],
        "icon": "📦"
    },
    "fcst": {
        "keywords": ["fcst", "forecast"],
        "display_name": "FCST Main",
        "category": "input",
        "key_fields": ["PN_CODE"],
        "compare_fields": [],
        "icon": "📊",
        "needs_join": True,
        "join_table": "fcst_detail"
    },
    "fcst_detail": {
        "keywords": ["fcst_detail", "forecast_detail"],
        "display_name": "FCST Detail",
        "category": "input",
        "key_fields": ["MAIN_ID", "ACTUALFIRSTDAYOFWEEK"],
        "compare_fields": ["ACTUALWEEKVALUE"],
        "icon": "📈"
    },
    # actual_io removed per user request 2026-07-21 - no longer compared
    # "actual_io": {
    #     "keywords": ["actual_io", "io_actual", "actual"],
    #     "display_name": "Actual I/O",
    #     "category": "input",
    #     "key_fields": ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"],
    #     "compare_fields": ["PLAN_VALUE"],
    #     "icon": "🏭"
    # },
    "supply": {
        "keywords": ["supply", "kitting", "CTB"],
        "display_name": "Supply / Kitting",
        "category": "input",
        "key_fields": ["PN_CODE", "KITTING_DATE"],
        "compare_fields": ["KITTING_VALUE", "QTY_REM", "QTY_REM2", "TOTAL_LOSS_QTY"],
        "icon": "🚚"
    },
    "switch": {
        "keywords": ["switch", "matrix"],
        "display_name": "Switch Matrix",
        "category": "input",
        "key_fields": ["LINE_CODE", "BEFORE_PN_CODE", "AFTER_PN_CODE"],
        "compare_fields": ["SWITCH_DURATION"],
        "icon": "🔀"
    },
    "item": {
        "keywords": ["item", "material", "item_master"],
        "display_name": "Item Master",
        "category": "input",
        "key_fields": ["ITEM_NO"],
        "compare_fields": ["PRODUCT_STYLE", "COLOR", "TYPE"],
        "icon": "🏷️"
    },
    "line": {
        "keywords": ["line", "line_master"],
        "display_name": "Line Master",
        "category": "input",
        "key_fields": ["LINE_CODE"],
        "compare_fields": ["LINE_LEVEL", "LINE_TYPE", "IS_MAIN_PROCESS"],
        "icon": "🧵"
    },
    "calendar": {
        "keywords": ["calendar", "line_calendar"],
        "display_name": "Line Calendar",
        "category": "input",
        "key_fields": ["LINE_CODE", "PLAN_TYPE", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"],
        "compare_fields": ["PLAN_VALUE"],
        "icon": "📅"
    },
    "plan_config": {
        "keywords": ["plan_config", "plan_setting", "config"],
        "display_name": "Plan Config",
        "category": "input",
        "key_fields": ["ID"],
        "compare_fields": [],
        "icon": "⚙️"
    },
    # Output tables
    "plan_output": {
        "keywords": ["plan_output", "output_result", "production_result"],
        "display_name": "Plan Output",
        "category": "output",
        "key_fields": ["LINE_CODE", "SKU", "PLAN_DATE", "SHIFT_NAME", "PLAN_ITEM"],
        "compare_fields": ["PLAN_VALUE"],
        "icon": "📋",
        "supports_granularity": True
    },
    "balance": {
        "keywords": ["balance", "boh", "wip", "onhand", "inventory"],
        "display_name": "BOH",
        "category": "output",
        "key_fields": ["ITEM_CODE", "PLAN_DATE", "SHIFT_NAME"],
        "compare_fields": ["BALANCE_QTY", "SHIFT_OUT_QTY", "PRE_INPUT_QTY"],
        "icon": "📦",
        "supports_granularity": True
    },
    # Aggregated Input (virtual, but belongs to Output per user request)
    "plan_input": {
        "keywords": ["plan_input", "input_summary", "inputs"],
        "display_name": "Plan Input",
        "category": "output",
        "key_fields": ["SKU", "PLAN_DATE"],
        "compare_fields": ["PLAN_VALUE", "FCST_QTY", "SUPPLY_QTY"],
        "icon": "📥",
        "supports_granularity": True,
        "is_virtual": True
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
