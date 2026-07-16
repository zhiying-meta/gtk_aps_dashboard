# Production Plan Review

Upload production plan data → Configure Cut Day → Auto-generate comparison report (ExF / Ungated / Gated / CTB)

## Requirements

- Python 3.10+ (for dev mode)
- macOS / Linux / Windows
- For end users without Python: use pre-built desktop app (see Desktop App section)

## Quick Start (Dev)

```bash
# 1. Clone or download
cd gtk-result-table

# 2. Run (auto-installs deps + starts server + opens browser)
./run.sh           # macOS / Linux
# or double-click run.bat  # Windows

# 3. Manual start
pip install -r requirements.txt
python run.py

# 4. Desktop mode (dev, with auto-browser + status window)
python desktop_app.py
```

Visit **http://localhost:8502** (configurable via `PORT` env var or `app/config.py`)

## Desktop App (No Python Required)

If your colleague has Python environment issues, build a standalone executable:

### Option A: One-click build scripts

```bash
# macOS / Linux
chmod +x build_app.sh
./build_app.sh              # one-folder mode (recommended, fast)
./build_app.sh --onefile    # single exe file (slower startup)
./build_app.sh --webview    # native window (needs pywebview)

# Windows
build_app.bat
build_app.bat --onefile
```

Output:
- `dist/ProductionPlanReview/` (folder) - zip and send
- `dist/ProductionPlanReview.exe` (Windows) or `ProductionPlanReview` (macOS/Linux) for one-file mode

Double-click the exe/app to run - it will:
1. Find free port (8502+)
2. Start server in background
3. Open browser automatically
4. Show status window (Tkinter) with Quit button

### Option B: Manual PyInstaller

```bash
pip install pyinstaller waitress
python build.py                    # one-folder
python build.py --onefile          # one-file
python build.py --onefile --windowed --with-webview  # native window, no console
```

### Option C: Native window (pywebview)

For a true desktop feel (no external browser):

```bash
pip install pywebview
python desktop_app.py  # will auto-detect pywebview and open native window
# To bundle:
python build.py --with-webview --windowed
```

With pywebview installed, the app opens a 1280x860 native window with the report inside, no browser needed.

### Distributing

- **One-folder**: Zip `dist/ProductionPlanReview` and send. Colleague unzips and double-clicks `ProductionPlanReview` / `ProductionPlanReview.exe`
- **One-file**: Send single `ProductionPlanReview` / `.exe` directly (larger, slower startup ~2-3s)
- Upload folder when frozen is stored in `~/.production_plan_review/uploads` (writable) or system temp, so no permission issues
- No Python, no pip, no terminal needed for end user

### Troubleshooting Desktop App

- **Port in use**: App auto-tries 8502-8522
- **Antivirus false positive** (Windows): One-file exe may trigger due to PyInstaller - use one-folder mode or add exception
- **macOS Gatekeeper**: Right-click → Open to bypass unsigned warning, or codesign: `codesign --deep --force --sign - dist/ProductionPlanReview.app`
- If browser doesn't open, check console / status window shows URL, manually open `http://127.0.0.1:8502`

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
│   ├── __init__.py              # Flask factory (PyInstaller compatible)
│   ├── config.py                # PORT, UPLOAD_FOLDER (writable when frozen)
│   └── modules/plan_merge/      # Plan merge blueprint
│       ├── __init__.py           # Blueprint registration
│       ├── routes.py             # API endpoints
│       ├── engine.py             # Data processing + Excel + ETD offset logic
│       ├── utils.py              # XLSX parsing helpers
│       ├── config.py             # Default cut-day + offset values
│       └── templates/            # Download templates + demo
├── static/
│   ├── global/                   # Global HTML/CSS/JS
│   │   ├── index.html           # SPA + nav categories (Multiple/Single)
│   │   ├── style.css            # Layout, sidebar
│   │   └── app.js               # Sidebar toggle + module switch
│   └── modules/plan_merge/
│       ├── app.js               # Main logic + ETD offset param + expand fix
│       └── style.css            # Table, filters, modals, pivot
├── uploads/                     # Temp upload dir (dev) – frozen uses ~/.production_plan_review/uploads
├── desktop_app.py               # Desktop entry: auto port, browser, Tkinter/pywebview
├── ProductionPlanReview.spec    # PyInstaller spec (one-folder)
├── build.py                     # Build script (pyinstaller wrapper)
├── build_app.sh / .bat          # One-click build for macOS/Linux/Windows
├── requirements.txt
├── run.sh / run.bat             # Dev launchers (auto-install Python)
└── run.py                       # Dev entry point
```

## Business Logic

| Module | Source | Algorithm |
|--------|--------|-----------|
| **ExF** | forecast sheet | Weekly values aligned to ExF Cut Day (Saturday) |
| **ETD** | plan_output (daily) | `ETD(D)=PackoutCum(D-n)` where `n=ETD Packout Offset` (default 2) → Aggregate to Cut Day weeks → `FLOOR(CumSum / Pallet_Qty) * Pallet_Qty` . e.g. Sat ETD uses Thu Packout cum |
| **Packout** | plan_output (daily) | Aggregate to Cut Day weeks (no pallet rounding) |
| **CTB** | ctb_sku_cum / ctb_gb_cum | Take last daily value per Cut Day week |
| **GB** | Sum of FG data by GB_PN | Packout & CTB only; no ETD/ExF at GB level |

ETD offset is configurable in section 2 (default 2 days).
