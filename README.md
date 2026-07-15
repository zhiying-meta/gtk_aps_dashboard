# Production Plan Review

Upload production plan data → Configure Cut Day → Auto-generate comparison report (ExF / Ungated / Gated / CTB)

## Requirements

- Python 3.10+
- macOS / Linux / Windows

## Quick Start

```bash
# 1. Clone or download
cd gtk-result-table

# 2. Run (auto-installs deps + starts server + opens browser)
./run.sh           # macOS / Linux
# or double-click run.bat  # Windows

# 3. Manual start
pip install -r requirements.txt
python run.py
```

Visit **http://localhost:8502** (configurable via `PORT` env var or `app/config.py`)

## Usage

### 1. Prepare Input File

Download template or use demo data from the web UI:

- **📄 Download Template** → empty template with headers only
- **📦 Template + Demo** → template + demo file with sample data

Input is a single `.xlsx` containing **6 sheets**:

| Sheet | Required | Description |
|-------|----------|-------------|
| `sku_master` | ✅ | SKU master data (Style, Color, Usage, Pallet_Qty, GB_PN) |
| `plan_output_gated` | ✅ | Gated daily output |
| `plan_output_ungated` | ✅ | Ungated daily output |
| `forecast` | ✅ | Weekly forecast (Saturday-ending weeks) |
| `ctb_sku_cum` | ✅ | SKU-level CTB cumulative |
| `ctb_gb_cum` | ✅ | GB-level CTB cumulative |

Click **📋 sheet_name** in the UI to view field descriptions.

### 2. Upload & Configure

1. Select input file
2. Configure Cut Day of Week:
   - **ExF** (Forecast) — fixed to Saturday (baseline)
   - **ETD** (ship date) — default Saturday
   - **PKG Output** — default Wednesday
   - **GB Output** — default Tuesday
   - ETD / PKG / GB dropdowns show offset from Saturday (e.g., "3d early")
3. Click **▶ Generate**

### 3. View Report

- **FG / GB tabs** — toggle between Finished Good (SKU) and Group BOM views
- **Filters** — multi-select dropdowns with search: PN, Usage, Style, Color, Type, Detail
- **✕ Clear** — reset all filters at once
- **Columns** — toggle PN / Usage / Style / Color / Cut Day / Pallet visibility
- **Aggregate by** — check Usage / Style / Color to group and sum PNs with expand/collapse drill-down; uncheck all to return to detail view
- **📥 Download Excel** — exports FG and GB as separate sheets

## Project Structure

```
gtk-result-table/
├── app/
│   ├── __init__.py              # Flask factory + root route
│   ├── config.py                # PORT, UPLOAD_FOLDER
│   └── modules/plan_merge/      # Plan merge blueprint
│       ├── __init__.py           # Blueprint registration
│       ├── routes.py             # API endpoints
│       ├── engine.py             # Data processing + Excel generation
│       ├── utils.py              # XLSX parsing helpers
│       ├── config.py             # Default cut-day values
│       └── templates/            # Download templates + demo
├── static/
│   ├── global/                   # Global HTML/CSS/JS
│   │   ├── index.html           # Single-page application
│   │   ├── style.css            # Layout, sidebar
│   │   └── app.js               # Sidebar toggle
│   └── modules/plan_merge/
│       ├── app.js               # Main frontend logic
│       └── style.css            # Table, filters, modals, pivot
├── uploads/                     # Temp upload directory
├── requirements.txt
├── run.sh                       # macOS/Linux launcher
├── run.bat                      # Windows launcher
└── run.py                       # Entry point
```

## Business Logic

| Module | Source | Algorithm |
|--------|--------|-----------|
| **ExF** | forecast sheet | Weekly values aligned to ExF Cut Day (Saturday) |
| **ETD** | plan_output (daily) | Aggregate to Cut Day weeks → `FLOOR(CumSum / Pallet_Qty) * Pallet_Qty` |
| **Packout** | plan_output (daily) | Aggregate to Cut Day weeks (no pallet rounding) |
| **CTB** | ctb_sku_cum / ctb_gb_cum | Take last daily value per Cut Day week |
| **GB** | Sum of FG data by GB_PN | Packout & CTB only; no ETD/ExF at GB level |
