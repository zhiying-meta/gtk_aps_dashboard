# Production Plan Review

Upload production plan data → Configure Cut Day → Auto-generate comparison report (ExF / Ungated / Gated / CTB)

## Requirements

- Python 3.10+
- macOS / Linux / Windows

> 推荐使用 `run.sh` / `run.bat` 一键启动，脚本会自动处理 Python 和 pip 缺失问题。

## Quick Start

### macOS / Linux (推荐)

```bash
cd gtk-result-table

# 一键启动（自动创建 .venv、安装依赖、启动服务、打开浏览器）
chmod +x run.sh
./run.sh

# 常用参数
./run.sh --reset          # 强制重建虚拟环境，修复环境问题
./run.sh --clean          # 清理 uploads 和 pycache
./run.sh --port=8503       # 指定端口
./run.sh --reset --clean   # 彻底重置
```

### Windows

```bat
# 双击运行
run.bat

# 或命令行
run.bat --reset
run.bat --clean
```

### 手动启动

```bash
pip install -r requirements.txt
python run.py
# 访问 http://localhost:8502
```

启动后访问 **http://localhost:8502**（端口可通过 `PORT` 环境变量配置，默认 8502）

## 启动脚本特性 (run.sh / run.bat)

`run.sh` 已针对常见环境问题做了健壮性处理，无需手动配置：

### 1. Python 检测兼容
- 自动查找 `python3` / `python` / `python3.13` / `python3.12` / `python3.11` / `python3.10` / Homebrew 路径
- 兼容 `python` 命令指向 Python3 的系统（如部分 Linux、Git Bash）
- 版本检查：要求 >=3.10，低于则提示
- 若完全未安装 Python：
  - macOS: 尝试 `brew install python`，若无 brew 则引导安装
  - Linux: 尝试 `apt-get / yum / dnf / pacman` 自动安装
  - Windows: 尝试 `winget install Python`

### 2. pip 命令找不到的处理（重点）
> 场景：用户已安装 Python，但终端输入 `pip` / `pip3` 提示 `command not found`

原因：
- Python 是最小化安装（未包含 pip）
- 未将 pip 加入 PATH
- Debian/Ubuntu 的 `venv` 默认不包含 pip

解决方案（脚本自动执行，无需手动）：
- **始终使用 `python -m pip` 而非 `pip` 命令**，不受 PATH 影响
- 自动检测 `python -m pip --version`
- 若失败，按顺序尝试修复：
  1. `python -m ensurepip --upgrade`
  2. `python -m ensurepip --default-pip`
  3. Linux: `sudo apt-get install python3-pip python3-venv` / `yum / dnf install python3-pip`
  4. `curl https://bootstrap.pypa.io/get-pip.py` 下载并安装
  5. `wget` 方式下载 get-pip.py
  6. `python -c "urllib.request.urlretrieve(... get-pip.py)"` 兜底下载（无 curl/wget 时）
- 对 `.venv` 同样适用：若 venv 创建时未包含 pip，会自动 bootstrap
- 启动时会有诊断输出：
  ```
  pip command: NOT FOUND (常见，可能是未加入PATH，但可用 python -m pip 替代)
  → 本脚本始终使用 'python3 -m pip' 而非 pip 命令，因此不受此影响 ✓
  ```

### 3. venv 隔离
- 自动在 `.venv/` 创建隔离环境，不污染系统 Python
- 若检测到依赖缺失/导入失败，自动重置一次
- 可手动 `./run.sh --reset` 强制重建

### 4. 依赖与端口
- 自动 `pip install -r requirements.txt`，失败自动重试
- 自动检测端口占用并 `lsof -ti :PORT | kill -9`
- 启动后自动打开浏览器

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
│   ├── __init__.py              # Flask factory
│   ├── config.py                # PORT, UPLOAD_FOLDER = project_root/uploads
│   └── modules/plan_merge/      # Plan merge blueprint
│       ├── __init__.py
│       ├── routes.py            # API endpoints
│       ├── engine.py            # Data processing + Excel + ETD offset logic
│       ├── utils.py             # XLSX parsing helpers
│       ├── config.py            # Default cut-day + offset values
│       └── templates/           # Download templates + demo
├── static/
│   ├── global/                  # Global HTML/CSS/JS
│   │   ├── index.html           # SPA
│   │   ├── style.css
│   │   └── app.js
│   └── modules/plan_merge/
│       ├── app.js               # Main logic
│       └── style.css
├── uploads/                     # Temp upload dir (gitignored)
├── requirements.txt            # flask, openpyxl, requests, waitress
├── run.sh / run.bat             # 一键启动脚本（自动处理 python/pip 缺失）
└── run.py                       # Entry point
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

## FAQ

**Q: 提示 `pip: command not found` 但已安装 Python？**
A: 这是常见情况，直接用 `./run.sh` 即可，脚本内部使用 `python -m pip`，不依赖 `pip` 命令。脚本也会自动尝试通过 `ensurepip` 和 `get-pip.py` 修复。

**Q: 只有 `python` 没有 `python3` 命令？**
A: 已兼容，`run.sh` 会自动查找 `python` 和 `python3` 多个候选。

**Q: 环境坏了怎么办？**
A: `./run.sh --reset` 重建虚拟环境。

**Q: 如何指定端口？**
A: `./run.sh --port=8503` 或 `PORT=8503 ./run.sh`

## License

Internal use.
