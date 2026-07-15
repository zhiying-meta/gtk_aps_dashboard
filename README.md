# 多版本计划拼接结果展示

上传排产数据 → 配置 Cut Day → 自动生成对比报表（ExF / Ungated / Gated / CTB）

## 系统要求

- Python 3.10+
- macOS / Linux / Windows

## 快速开始

```bash
# 1. 下载或克隆项目
cd gtk-result-table

# 2. 运行（自动安装依赖 + 启动服务 + 打开浏览器）
./run.sh           # macOS / Linux
# 或双击 run.bat  # Windows

# 3. 手动启动
pip install -r requirements.txt
python app/server.py
```

启动后访问 **http://localhost:8501**

## 使用流程

### 1. 准备输入文件

下载模板或使用演示数据：

- **📄 下载模板** → 仅含表头的空模板
- **📦 模板+演示** → 模板 + 含完整数据的演示文件

输入文件为单个 `.xlsx`，需包含以下 **6 个 Sheet**：

| Sheet | 必填 | 说明 |
|-------|------|------|
| `sku_master` | ✅ | SKU 主数据（含 Pallet_Qty） |
| `plan_output_gated` | ✅ | Gated 版本日级产出 |
| `plan_output_ungated` | ✅ | Ungated 版本日级产出 |
| `forecast` | ✅ | 周级 Forecast |
| `ctb_sku_cum` | ✅ | SKU 级 CTB 累计值 |
| `ctb_gb_cum` | ✅ | GB 级 CTB 累计值 |

每个 Sheet 的字段说明可在网页上点击「📋 sheet名称」查看。

### 2. 上传 & 配置

1. 选择输入文件（或点击「📂 一键上传」多选自动匹配）
2. 配置 Cut Day of Week：
   - **ExF**（Forecast 截止日）— 默认周六
   - **ETD**（预计发货截止日）— 默认周六
   - **PKG Output**（包装产出截止日）— 默认周三
   - **GB Output**（GB 维度截止日）— 默认周二
3. 点击「▶ 生成报表」

### 3. 查看报表

- **筛选**：多选下拉 + 搜索过滤，支持 Dim / PN / Usage / Style / Color / Type / Detail
- **列显隐**：切换 PN / Usage / Style / Color / Cut Day / Pallet 列
- **分组**：按 Style 或 Color 折叠
- **下载**：📥 下载 Excel（带格式，含冻结窗格、千分位、颜色标识）

## 项目结构

```
gtk-result-table/
├── app/
│   ├── server.py          # Flask 服务端
│   ├── backend_v2.py      # 数据处理引擎
│   ├── gen_templates.py   # 模板生成器
│   ├── extract_clean.py   # 数据清洗（源→参考数据）
│   ├── static/            # 前端页面 (HTML/CSS/JS)
│   └── templates/         # 下载模板
├── data-ref-xlsx/         # 清洗后的参考数据（含演示文件）
├── requirements.txt
├── run.sh                 # macOS/Linux 启动脚本
└── run.bat                # Windows 启动脚本
```

## 业务逻辑

| 模块 | 数据源 | 算法 |
|------|--------|------|
| **ExF** | forecast sheet | 按 ExF Cut Day 取周值 |
| **ETD** | plan_output (dtype=OUTPUT) | 按 ETD Cut Day 聚合 → `ROUNDDOWN(Cum / Pallet_Qty, 0) * Pallet_Qty` |
| **Packout** | plan_output (dtype=OUTPUT) | 按 PKG Output Cut Day 聚合（无取整） |
| **CTB** | ctb_sku_cum / ctb_gb_cum | 按 ETD Cut Day 取周末累计值 |
| **GB 维度** | FG 数据按 GB_PN 汇总 | Packout 用 GB Output Cut Day，无 ETD 模块 |
