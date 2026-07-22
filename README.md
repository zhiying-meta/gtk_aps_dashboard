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

### 离线静态打包（无服务器 / 无数据库 / 多版本 / 全功能）【推荐分发】

参考 `campus-planning-system/export_static.py` 模式，`export_static.py` 把前后端打包成纯静态 `dist/`，**所有功能在浏览器内完成，无需 Python/服务器/数据库**。

#### 为什么需要

- 公司无合适部署位置、无数据库
- 需要给计划、销售、老板直接发文件即用
- 需要一版/多版对比，且要保留上传、配置、筛选、聚合、下载 Excel 全功能

#### 原理

- `static/modules/plan_merge/engine.js` 是 `engine.py` 的浏览器移植版（聚合、ETD offset、CTB 取周最后、GB 求和等完全一致）
- `export_static.py`：
  1. 拷贝 `static/` → `dist/static/`，把 `/static/` 绝对路径改为 `./static/` 相对路径，适配 `file://` 双击
  2. 本地化 `xlsx.full.min.js` 到 `dist/static/xlsx.full.min.js`，真离线
  3. 可选：把输入的多个 `.xlsx` 用 Python 引擎预处理成 `window.STATIC_DB = {versions:[...], meta, schema}` 写入 `dist/data.js`
  4. 注入 `<script src="./data.js">` 到 `dist/index.html`
- 前端检测：`if (window.STATIC_DB) 进入离线版本切换模式，否则走在线/客户端引擎`

#### 如何打包

```bash
# 安装依赖（只需一次）
pip install -r requirements.txt

# 1. 单版本演示（默认 templates/input_demo.xlsx）
python export_static.py

# 2. 多版本对比（最常用 - 预烘焙多版进离线包）
python export_static.py --inputs "data/W25_v1.xlsx" "data/W25_v2.xlsx" "data/W26_final.xlsx" --note "W25 3版对比+W26定版"

# 3. 通配符批量
python export_static.py --inputs "data/*.xlsx" -o dist

# 4. 指定输出目录
python export_static.py --inputs "data/*.xlsx" --output ./release/PPR_offline

# 5. 自定义 ETD 等配置（打包时固定）
python export_static.py --inputs "data/*.xlsx" --config-etd-cut Saturday --config-output-cut Wednesday --config-offset 2
```

产出：

```
dist/
├── index.html               # 入口，双击即用
├── data.js                  # 预烘焙数据 window.STATIC_DB = {versions, meta, schema}
├── static/
│   ├── xlsx.full.min.js     # 本地化，真离线
│   ├── global/...
│   └── modules/plan_merge/
│       ├── engine.js        # 浏览器版计算引擎（全功能关键）
│       └── app.js
├── input_template.xlsx
├── input_demo.xlsx
└── README_OFFLINE.txt
```

> `data.js` 大小：1版约 1MB，3版约 3MB，属于正常，浏览器可承载。

#### 如何使用打包的内容

**分发：**

```bash
zip -r PPR_offline_v1.zip dist
# 发邮件/Teams/SharePoint/飞书、企业微信均可
```

**接收方使用（无需任何安装）：**

1. 解压 `dist.zip` 到任意目录
2. 双击 `dist/index.html`（Chrome / Edge 推荐）
3. 看到顶部蓝色 Banner：`📦 Offline Static Mode - Full 功能已就绪`

**功能说明（离线也全部可用）：**

- **预烘焙版本切换：** Banner 下拉选择打包时嵌入的版本，`Compare multi` 勾选可合并多版，自动加 `PlanVersion` 列
- **Show Upload：** 点击 `📁 Show Upload` 可展开上传区，**离线上传新文件**：
  - 选择新的 6-sheet xlsx
  - 修改 ETD / PKG / GB Cut Day 和 `ETD vs Packout Offset`
  - 点击 `▶ Generate`，走 `engine.js` 浏览器内计算，效果与 Python 后端一致
- **筛选/列显/聚合：** PN / Usage / Style / Color / Type / Detail 多选、搜索、✕ Clear；Aggregate by Usage/Style/Color 展开折叠
- **下载 Excel：** `📥 Download Excel` 走客户端 `XLSX.writeFile`，FG/GB 分 sheet
- **Schema：** 点击 `📋 sheet_name` 查看字段说明，离线时读 `static/schema.json`

**I/O Report 离线（已全功能化）：**
- 切换到 `I/O Report` 页，顶部会显示 `📦 Offline Mode - I/O Report 可用 (客户端引擎)`
- 上传方式与在线一致：
  - 方式1：分别选 `Item Master / Schedule / Balance` 3 个 xlsx
  - 方式2：选 1 个 `combined` 文件（包含 3 个 sheet：Item Master / Schedule Result / BOH Balance）
  - 支持一键多选 3 文件自动分拣
- 点击 `▶ Upload & Analyze`，走 `static/modules/io_report/engine.js` 浏览器内计算，無需服务器
- 之后 `Row Dimensions` 拖拽（Line / PN / Style）、`Column` 切 Shift/Day/Week/Month、Filters、Merge Group、Download Excel 全部可用，与在线版一致

**常见问题：**

- **Q: 双击白屏？** A: 用 Chrome/Edge 打开，勿用 IE。`file://` 下部分浏览器禁 `fetch` 本地文件，但本包已改为相对路径+本地 xlsx 库，无需联网。
- **Q: 第一次联网？** A: 已内置 `xlsx.full.min.js`，完全无需联网。旧版 CDN 版需联网一次，当前版已解决。
- **Q: 包太大？** A: 每版约 1MB，若嵌入 10版则 10MB，可改 `--inputs` 只放关键版本，或发不带 `data.js` 的空壳版（对方离线上传）。
- **Q: I/O Report 和 Gated 页面为啥打包后一样？** A: 已修复。旧版离线包 I/O 页显示“仅 Gated 可用”提示；新版已内置 `io_report/engine.js`，离线 I/O 页面与原始一致，支持上传 3 文件/Combined，9 张报表、拖拽维度、合并、下载全可用。若仍看到旧提示，请重新 `python export_static.py` 生成 dist。

#### 与 run.sh 对比

| 方式 | 依赖 | 部署 | 多版 | 接收方门槛 |
|------|------|------|------|------------|
| `run.sh` / `run.py` | Python 3.10+ | 无需 | 需手动多次上传 | 需会命令行 |
| `dist/` 静态包 | 无（浏览器） | 无 | 预烘焙+现场上传均可 | 双击即用，推荐 |

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
│       ├── engine.py            # Data processing + Excel + ETD offset logic (Python)
│       ├── utils.py             # XLSX parsing helpers
│       ├── config.py            # Default cut-day + offset values
│       └── templates/           # Download templates + demo
├── static/
│   ├── global/                  # Global HTML/CSS/JS
│   │   ├── index.html           # SPA
│   │   ├── style.css
│   │   └── app.js
│   └── modules/plan_merge/
│       ├── engine.js            # Browser port of engine.py (full offline)
│       ├── app.js               # Main logic + static mode + client engine
│       └── style.css
├── uploads/                     # Temp upload dir (gitignored)
├── dist/                        # Offline static build (gitignored, generated by export_static.py)
│   ├── index.html               # Double-click to use
│   ├── data.js                  # window.STATIC_DB = {versions, meta, schema}
│   └── static/...
├── requirements.txt            # flask, openpyxl, requests, waitress
├── export_static.py            # Static offline builder (inspired by campus-planning-system)
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

**Q: 无数据库、无部署，怎么给别人用？**
A: 用静态离线打包：
```bash
python export_static.py --inputs "data/W25*.xlsx" --note "W25多版对比"
zip -r PPR_offline.zip dist
```
把 `dist.zip` 发给对方，对方解压双击 `index.html` 即可，上传/配置/筛选/聚合/下载 全可用，真离线。详见上面“离线静态打包”章节。

**Q: 离线包双击白屏？**
A: 用 Chrome/Edge 打开，勿用 IE。当前包已内置 `xlsx.full.min.js`，无需联网。

**Q: 离线包能否上传新文件？**
A: 可以。顶部点 `📁 Show Upload`，选择新 xlsx，改 Cut Day / Offset，`▶ Generate` 走 `engine.js` 浏览器内计算，与 Python 后端一致。

## License

Internal use.
