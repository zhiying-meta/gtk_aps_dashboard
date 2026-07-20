# V2V (Version to Version) 模块 - 需求分析与实现规划

> 基于 APS 自动排产系统的版本对比需求，针对输入快照与输出结果的差异快速定位

---

## 1. 背景 (Background)

APS (Advanced Planning & Scheduling) 是一个自动排产系统，每次生成新排产计划时：
- 输入：多张快照表（BOM, FCST, 产能, 供应等）
- 输出：排产结果 + 物料结存

由于计算逻辑复杂，同一 forecast 周期下，不同时间生成的版本（MPS_RECORD_CODE 不同）结果可能差异很大。

**V2V 目的：**
- 快速抓取 **输入变量** 的变化
- 快速抓取 **输出结果** 的差异
- 支持多维度钻取（线体维度、SKU 维度、时间维度）

用户提供了一个完整版本样本：`Ivy-20260716-gated-v2/` 包含 12 张表，其中 `MPS_RECORD_CODE=5253702048555071-202629-003` 为当前版本的唯一标识。

---

## 2. 输入数据对比 (Input Comparison)

### 2.1 总览 - 9 大类输入

| # | 表名 | 文件名示例 | 关键程度 | 变化频率 | 对比重点 |
|---|------|-----------|---------|---------|---------|
| 1 | BOM快照 | BOM快照.xlsx | 高 | 低 | 物料层级、用量、损耗、LT |
| 2 | FCST主表+明细 | FCST主表.xlsx + FCST明细表.xlsx | 极高 | 高 | 周需求量变化 |
| 3 | I_O实际值表 | I_O实际值表.xlsx | 高 | 中 | 实际投入产出的时间覆盖 & 数值一致性 |
| 4 | Supply供应表 | supply供应表.xlsx | 极高 | 中 | 每周累计到料量变化 |
| 5 | 切换矩阵 | 切换矩阵快照表.xlsx | 高 | 低 | 切换损耗时间 |
| 6 | 料号快照 | 料号快照表.xlsx | 低 | 极低 | 属性映射备用 |
| 7 | 线体快照 | 线体快照表.xlsx | 低 | 极低 | 线体层级 |
| 8 | 线体日历 | 线体日历快照表.xlsx | 极高 | 低 | UPH, 良率, 效率, 工时 curve |
| 9 | 计划设置 | 计划设置表.xlsx | 中 | 低 | 计划参数整体对比 |

---

### 2.2 逐表详细对比逻辑

#### 1. BOM快照表 (BOM)

**原始字段 (34列)：** ID, MPS_RECORD_CODE, ITEM_NO, ITEM_DESC, PARENT_PN_CODE, UNIT_NUM, LOSS_RATE, PROCESS_LT, ...

**业务说明：**
- ITEM_NO 是子料，PARENT_PN_CODE 是父料，形成物料树
- ITEM_DESC 与 PARENT_PN_CODE 内容重复（待验证，文档说一样）
- UNIT_NUM 用量, LOSS_RATE 损耗, PROCESS_LT process 时间

**Key:** `(PARENT_PN_CODE, ITEM_NO)` 或 `COMPONENT_SEQ_ID`
推荐使用 `(PARENT_PN_CODE, ITEM_NO)` 作为业务主键，因为最直观。

**对比项：**
- 新增/删除 的 BOM 关系 (新增子料, 删除子料)
- UNIT_NUM 变化 (+/- delta)
- LOSS_RATE 变化
- PROCESS_LT 变化
- PN_CODE_PATH 路径变化 (可选)

**展示：**
- 表格：Parent -> Child 树形，或扁平列表
- 高亮：新增 green, 删除 red, 修改 yellow 且显示 delta
- 过滤：按 Parent SKU / Child SKU / 变化类型 (Add/Del/Modify)

---

#### 2. FCST主表 + FCST明细 (Forecast)

**关联关系：**
- FCST主表：ID <-> PN_CODE (SKU)
- FCST明细表：MAIN_ID = FCST主表.ID, 没有 PN_CODE 直接信息
- 需要 JOIN 才能得到：SKU -> Weekly Demand

**FCST主表字段 (24列)：** ID, PN_CODE, YEAR, MONTH, VERSION (APS-20260706135042), FORECAST_NAME

**FCST明细字段 (13列)：** MAIN_ID, YEAR, MONTH, WEEK, FIRSTDAYOFWEEK, ACTUALWEEKDAYS, ACTUALWEEKVALUE, ACTUALFIRSTDAYOFWEEK (周六日期), CREATE_TIME

**业务规则：**
- ACTUALFIRSTDAYOFWEEK 是周六，作为周的标识
- 周定义：周日到周六为一个完整周
- ACTUALWEEKVALUE 是该周该 SKU 的需求数量

**Key:** `(SKU, ACTUALFIRSTDAYOFWEEK)`  主键，SKU 通过 JOIN 获得

**对比项：**
- 每周 SKU 需求量变化：ACTUALWEEKVALUE 变化量 & 变化率
- 新增/删除的 SKU 需求周
- 版本信息变化：VERSION 对比 (可能是计划生成时间戳)

**特殊处理：**
- 需要先将 主表+明细 JOIN 成 宽表，再做 V2V
- 时间对齐：两个版本可能 forecast 覆盖周期长度不同，以并集为准，缺失补 0 或空

**展示：**
- 表格：SKU x Week 矩阵，单元格显示 V_A, V_B, Diff
- 热力图：Diff 绝对值颜色深浅
- 筛选：SKU 前缀 (SK-), Style, Color (需关联料号快照表 的 PRODUCT_STYLE/COLOR)

---

#### 3. I_O实际值表 (Actual Input/Output)

**字段 (11列)：** MPS_RECORD_CODE, LINE_CODE (AL5-Frame, AL5-L Temple, R Temple, FAT, PKG), SHIFT_NAME (白班/夜班), PLAN_ITEM (INPUT/OUTPUT), PLAN_TYPE (FCST...?), SKU (GB-Rec M-BLACK, SK-xxx), PLAN_DATE, PLAN_VALUE

**业务规则：**
- 从 MES 拉取的历史实际值，从 Day1 开始
- 包含智能眼镜产线的分段：
  - Frame 框, L Temple 左腿, R Temple 右腿, FAT 总装测试, PKG 包装
- GB (General Build) 概念：为了减少 SKU 切换，中间态无镜片通用件，PKG 时配镜片
  - GB_PN 映射可从 SKU Master 或 BOM 发现

**Key:** `(LINE_CODE, SKU, PLAN_DATE, SHIFT_NAME, PLAN_ITEM)` 细粒度主键

**对比项 - 两部分：**
1. **时间覆盖 Highlight：**
   - Version A 覆盖 2026/04/21 ~ 2026/07/16
   - Version B 覆盖 2026/04/21 ~ 2026/07/23 (更长)
   - 需要高亮：B 多出的时间段数据 (新增 7 天)，A 没有的数据
2. **相同时间范围一致性检查：**
   - 对于重叠时间区间 (交集)，相同 KEY 的 PLAN_VALUE 应该一致
   - 若不一致，标红为异常：同样的历史实际值，不同版本竟然变了 -> 数据拉取 bug

**展示：**
- 时间轴视图，显示覆盖范围对比条
- 表格：按日期展开，列：V_A, V_B, Diff + 标记是否越界
- 按 LINE_CODE / SKU 过滤

---

#### 4. Supply供应表 (Kitting / CTB)

**字段 (12列)：** PN_CODE (原料), KITTING_DATE (到料日), KITTING_VALUE (数量), QTY_REM, DATA_TYPE=KITTING, TOTAL_LOSS_QTY

**业务规则：**
- 从 Day1 到年底 (FCST cover 时间)
- 到料计划，非累计，需要转累计？但 raw 是每日增量

**Key:** `(PN_CODE, KITTING_DATE)`

**对比项：**
- 按周聚合到料对比（按周六分组求和，或累计到周）
- 每日到料变化 delta
- 按 PN_CODE 的累计总量曲线对比

**算法：**
- 选项1：每日明细直接 diff
- 选项2：聚合到周 (周六为截止)，对比每周到料总量 `SUM(KITTING_VALUE group by week)`
- 选项3：累计视角 `CUMSUM` 对比，计算到每个周六的累计到料量 (更符合 CTB 逻辑)

推荐：提供两种视图 toggle，daily 和 weekly cum。

**展示：**
- 原料维度可搜索 (PN_CODE 前缀 GB-, etc)
- 曲线图：双版本累计到料曲线
- 表格：周维度差异高亮

---

#### 5. 切换矩阵快照表 (Switch Matrix)

**字段 (11列)：** LINE_CODE (AL1-PKG...), BEFORE_PROJECT_CODE ?, BEFORE_PN_CODE (隐在列6), AFTER_PN_CODE, SWITCH_DURATION (小时), STANDARD_HUMAN

**业务规则：**
- SK-xxx 到 SK-yyy 的切换在不同线体损耗不同
- 影响产能计算

**Key:** `(LINE_CODE, BEFORE_PN_CODE, AFTER_PN_CODE)`

**对比项：**
- 新增/删除的切换组合
- SWITCH_DURATION 变化 (一般不变，变了要高亮)

**展示：**
- 矩阵热力图 (Before x After)，但 SKU 数量大 2800 行，不适合全矩阵
- 列表：仅显示变化的记录
- 按 LINE_CODE 过滤

---

#### 6. 料号快照表 (Item Master)

**字段 (39列)：** ITEM_NO, PRODUCT_STYLE, COLOR, TYPE, STYLE, PURPOSE, PRODUCT_TYPE, UNIT, MAKE_OR_BUY, ...

**业务：** 物料属性，PRODUCT_STYLE, COLOR 用于映射，MAKE_OR_BUY 自制/外购

**对比：** 按用户说 没必要比较，但保留作为辅助 JOIN 表，用于提供 Style/Color 过滤维度。可做简单版本：
- 新增/删除物料
- PRODUCT_STYLE / COLOR / TYPE 变化

**实现：** 可选，低优先级，作属性字典库使用，不单独作为 diff 表。

---

#### 7. 线体快照表 (Line Master)

**字段 (21列)：** LINE_CODE, LINE_NAME, LINE_LEVEL (层级), LINE_TYPE (AL/ML Auto/Manual), PROJECT_LINE, IS_MAIN_PROCESS

**业务：** 线体层级关系，AL = Auto Line, ML = Manual Line

**对比：** 线体本身几乎不变，简单记录新增/删除，或 LINE_LEVEL, LINE_TYPE 变化。不重点展示。

---

#### 8. 线体日历快照表 (Line Calendar) - 重要

**字段 (15列)：** SITE, LINE_CODE, LINE_TYPE (自动线), PLAN_TYPE (包含 checkout?, UPH, Yield 良率, Efficiency 效率, 工时?), YEAR, MONTH, WEEK, PLAN_DATE (隔几天一个?), SHIFT_NAME (白班/夜班), PLAN_VALUE (数值), PLAN_ITEM (INPUT/OUTPUT)

**业务解释 (重点)：**
- PLAN_TYPE 包含：
  - UPH (Unit Per Hour) 每小时产能，分 INPUT UPH 和 OUTPUT UPH (INPUT > OUTPUT 因有损耗)
  - Yield 良率
  - Efficiency 效率
  - 工时 (每班几小时，正常 10h)
  - checkout (待确认含义)
- 白班/夜班是不同团队，UPH 有爬坡曲线 (ramp-up curve)
- 此曲线由相关团队确认后作为 APS 输入

**Key:** `(LINE_CODE, PLAN_TYPE, PLAN_DATE, SHIFT_NAME, PLAN_ITEM)`  (INPUT vs OUTPUT UPH 需区分)

**对比项：**
- 每线体每日每班每类型的 PLAN_VALUE 变化
- 按 PLAN_TYPE 分组对比 (UPH 曲线变化影响很大)
- 爬坡趋势图对比

**特殊处理：**
- PLAN_DATE 不是连续的，是"隔几天"，需要按日期对齐并集
- 分段：Frame / L Temple / R Temple / FAT / PKG
- Shift 区分

**展示：**
- 折线图：UPH curve 双版本对比，按线体筛选
- 表格：透视，日期为列，值差异高亮
- 筛选：LINE_CODE, PLAN_TYPE (UPH, 良率, 效率...), SHIFT

---

#### 9. 计划设置表 (Plan Config) - 1 行

**字段 (50列)：** PLAN_MONTHS, DEADLINE, PLAN_MONTH, FORECAST_MONTH, IS_REFERENCE, EXECUTION_TIME, DOS_TARGETS, ALLOW_ADVANCE_DAYS, WORK_HOUR, VERSION_NAME, RPT_VERSION, BOM_VERSION, UPH_VERSION, ...

**业务：** 整个 APS 计划的全局参数，仅一行。

**对比：** 字段级 diff，列出所有 50 个字段中值不同的项，类似 JSON diff。

**展示：**
- Key-Value 表：Field | V_A | V_B | Changed?
- 高亮变化行

---

## 3. 输出数据对比 (Output Comparison)

### 3.1 排产结果快照表_输出 (Main Output)

**字段 (16列)：** LINE_CODE, SHIFT_NAME, PLAN_ITEM (INPUT/OUTPUT), PLAN_TYPE (KITTING?), SKU (SK-开头 是正常 FG, GB-开头 是 GB, FR/LT/RT 是前道), PLAN_DATE, PLAN_VALUE (数量), OPERATION_TYPE

**业务：**
- 每条线，每天，每班，每个 SKU 的投入产出计划
- SKU 前缀：
  - SK-xxx FG 成品 (在 PKG 线)
  - GB-xxx General Build 中间态 (在 FAT)
  - FR-xxx Frame, LT-xxx L Temple, RT-xxx R Temple (在各前道线)
- PKG 段：GB 库存是否够
- 产能受：UPH, 良率, 效率, 切换损耗 影响

**Key:** `(LINE_CODE, SKU, PLAN_DATE, SHIFT_NAME, PLAN_ITEM)`

**对比需求 (用户明确)：**
- 从不同维度对比版本的排产差异
  - 线体维度：某线体在某日总产量在两个版本差异
  - SKU 维度：某 SKU 在所有线体的排产总量差异
- 主对比字段：PLAN_VALUE (投产数量)

**算法：**
1. 按天聚合：可选按 SHIFT 合并或分开
   - 白班+夜班 = 当日总量
2. 按周聚合：周六为周截止，求和
3. 支持 3 粒度：Shift 细粒度 / Day / Week
4. 聚合类型：
   - `SUM(PLAN_VALUE)` 按 SKU 或按线体

**展示 (需设计)：**
- **Summary 卡片：** 总差异条数，新增/删除/变化的记录数
- **切换视图：**
  - Dim=Line: 按 LINE_CODE 分组，周为列，值为总量，对比 V_A vs V_B diff
  - Dim=SKU: 按 SKU 分组
  - Dim=Line+SKU: 细粒度
- **表格：** 列：LINE_CODE, SKU, DATE, V_A, V_B, Diff, Diff%
- **热力图：** LINE x DATE 矩阵，颜色代表 diff 大小
- **图表：** 选中某 SKU / 某线体，展示双版本产能曲线对比 (line chart)

---

### 3.2 结存表_输出 (WIP / OnHand Balance)

**字段 (9列)：** MPS_RECORD_CODE, PLAN_DATE, SHIFT_NAME, SHIFT_CODE (1白班 2夜班), ITEM_CODE, SHIFT_OUT_QTY, PRE_INPUT_QTY, BALANCE_QTY, CREATION_DATE

**业务：**
- 排产过程中各段库存结存
- 如 PKG 段要考虑 GB 库存是否够
- SHIFT_OUT_QTY 出库? PRE_INPUT_QTY 前段投入? BALANCE_QTY 结存

**Key:** `(ITEM_CODE, PLAN_DATE, SHIFT_NAME)`

**对比项：**
- BALANCE_QTY 变化 (最重要)
- SHIFT_OUT_QTY, PRE_INPUT_QTY 变化
- 负库存预警：BALANCE < 0 高亮

**展示：**
- 类似排产结果：按 ITEM_CODE x DATE 矩阵
- 双版本 BALANCE 曲线对比
- 差异大或负库存高亮

---

## 4. 整体架构设计

### 4.1 现有架构回顾

```
Flask Factory (app/__init__.py)
├── static/global/index.html (SPA shell)
├── static/modules/plan_merge/ (现有模块: Gated/Ungated/CTB)
│   ├── routes.py: /api/process + /api/download + /templates/*
│   ├── engine.py: 聚合逻辑
│   └── frontend: app.js 657 行，纯 vanilla JS + filter/pivot
└── app/modules/plan_merge/templates/

问题：
- 路由未命名空间：/api/process 会冲突，V2V 必须加前缀 /v2v/api/...
- 前端单页面写死，只能展示一个模块，需要重构成多模块路由或新增页面
```

### 4.2 V2V 模块目标架构

```
新增：
app/modules/v2v/
├── __init__.py          # Blueprint('v2v', url_prefix='/v2v')
├── routes.py            # /v2v/api/*, /v2v/templates/*
├── config.py            # diff 配置
├── utils.py             # 通用解析：读取 12 张表的 xlsx 或 zip
├── parsers/
│   ├── bom_parser.py
│   ├── fcst_parser.py   # JOIN 主+明细
│   ├── actual_parser.py
│   ├── supply_parser.py
│   ├── switch_parser.py
│   ├── item_parser.py
│   ├── line_parser.py
│   ├── calendar_parser.py
│   ├── config_parser.py
│   ├── output_plan_parser.py
│   └── balance_parser.py
├── diff_engine.py       # 核心对比逻辑：每张表 diff 策略
└── excel_generator.py   # 导出 V2V 报告 Excel

static/modules/v2v/
├── app.js               # 新模块前端逻辑 (约 1000 行)
├── style.css            # 复用 + 新增
└── components/ (可选)
    ├── diff_table.js
    ├── chart_view.js
    └── summary_cards.js

static/global/
├── index.html           # 改造：sidebar 增加 V2V nav，content 区域模块切换
├── style.css            # sidebar active 状态
└── app.js               # 模块路由器：data-module 切换，动态加载 JS
```

### 4.3 数据上传方式设计 (关键决策)

**选项 A：双版本文件夹 Zip 上传 (推荐)**
- 用户将两个版本的快照文件夹分别打包成 zip，命名如 `V1_20260716.zip`, `V2_20260723.zip`
- 前端：两个上传卡片，Version A + Version B
- 后端：解压到 `uploads/{id}/vA/` 和 `vB/`，分别解析
- 优点：符合用户现有文件组织，Ivy-... 文件夹直接可 zip
- 缺点：需要處理 zip 解压

**选项 B：Excel 合并文件 (多 Sheet) 类似现有 plan_merge**
- 将两个版本的所有表合并到一个超大 Excel，每个 Sheet 包含 V_A 和 V_B 的区分列
- 缺点：文件极大，I_O 实际值表 13w 行 + 供应表 12w 行 + 日历 39w 行，合并会超过 100M，Excel 会卡

**选项 C：多文件分别上传 Version A/B (最灵活)**
- 前端：对每种快照类型，提供两个文件输入 (A 和 B)，如 BOM A, BOM B
- 实际上 12 张表 x 2 = 24 个文件输入，太繁琐
- 折中：分 2 组，每组 12 个文件输入，或动态隐藏可选表

**推荐方案：混合模式**
- **Primary：Zip 模式** - 上传两个 Zip，每个 Zip 内包含 12 张 xlsx (或按原文件夹结构)，系统自动识别文件名匹配
  - 支持：`BOM快照.xlsx`, `FCST主表.xlsx`, `FCST明细表.xlsx`, `I_O实际值表.xlsx`, `supply供应表.xlsx`, `切换矩阵快照表.xlsx`, `料号快照表.xlsx`, `线体快照表.xlsx`, `线体日历快照表.xlsx`, `计划设置表.xlsx`, `排产结果快照表_输出.xlsx`, `结存表_输出.xlsx`
  - 文件名允许模糊匹配，忽略大小写，前缀匹配 e.g. `BOM` 匹配 `BOM快照`
- **Secondary：单文件夹上传** - 后续可扩展，用户直接选文件夹 (需前端 File API `webkitdirectory`)
- **Fallback：单 Excel 多 Sheet** - 兼容旧模式，若用户提供单个 Excel 包含 `BOM`, `FCST主表` 等 Sheet 名，也能解析

**MVP 先实现：**
- 前端 2 个主上传区：Version A Zip, Version B Zip
- 后端解压，读取每个 xlsx，忽略不存在的表，返回解析统计

---

### 4.4 后端 Diff Engine 设计

#### 通用 Diff 数据结构

```python
@dataclass
class DiffRecord:
    key: tuple              # 业务主键
    field: str              # 变化字段 e.g. "UNIT_NUM"
    value_a: any
    value_b: any
    delta: float | None
    delta_percent: float | None
    change_type: str        # "ADD", "DEL", "MODIFY", "UNCHANGED"
```

每个表 diff 后产生：
```json
{
  "table": "bom",
  "total_a": 553,
  "total_b": 560,
  "added": 10,
  "deleted": 3,
  "modified": 15,
  "unchanged": 538,
  "records": [ DiffRecord... ],
  "summary": {...}
}
```

#### 各表 Diff 实现伪代码

```python
def diff_bom(df_a, df_b):
    # df: DataFrame with PARENT_PN_CODE, ITEM_NO, UNIT_NUM, LOSS_RATE, PROCESS_LT
    key = ["PARENT_PN_CODE", "ITEM_NO"]
    merged = pd.merge(df_a, df_b, on=key, how="outer", suffixes=("_A","_B"), indicator=True)
    merged["change_type"] = merged["_merge"].map({"left_only":"DEL","right_only":"ADD","both":"BOTH"})
    # 对于 BOTH，检查字段变化
    for field in ["UNIT_NUM","LOSS_RATE","PROCESS_LT"]:
        mask = both & (merged[field+"_A"] != merged[field+"_B"])
        merged.loc[mask, "change_type"] = "MODIFY"
    return merged

def diff_fcst(fcst_a_main, fcst_a_detail, fcst_b_main, fcst_b_detail):
    # JOIN 主+明细 -> sku_master dict
    # 然后转 wide: SKU x Week
    # merge outer, diff

def diff_supply(df_a, df_b, granularity="weekly"):
    # 若 weekly，先 groupby PN_CODE + week(Saturday) sum KITTING_VALUE
    # 再 outer merge diff

def diff_actual_io(df_a, df_b):
    # 计算时间覆盖：min_max date per version
    # 标记额外时间段
    # 对于交集，做 equality check
```

#### 性能考虑

- I_O 13w 行，Supply 12w 行，Calendar 39w 行，Plan Output 20w 行，Balance 19w 行 -> 总计约 100w 行级别
- 使用 Pandas 必须优化：只读取必要列，用 `usecols`
- 避免全量 outer merge 大表时内存爆炸：对 Calendar 按 LINE_CODE 分块 diff
- 后端返回给前端数据需要分页 + 聚合统计，不能一次性返回 20w diff records JSON (会超 100M)
- 方案：后端返回 summary + top N差异 + 聚合数据，前端按需请求明细： `/v2v/api/diff/detail?table=bom&page=1&change_type=MODIFY`

---

### 4.5 前端展示设计 (关键 UX)

#### 4.5.1 整体页面布局

```
Sidebar:
  - Report
    - Gated/Ungated/CTB (现有)
    - V2V Comparison (新增) ⭐

Main Content (V2V模式):
  Section 1: Version Upload
    [Version A 卡片] [Version B 卡片] -> 显示各 12 张表解析状态 (✓/✗)
    [Config] 粒度选择: Daily / Weekly, Diff阈值
    [▶ Compare 按钮]

  Section 2: Summary Dashboard
    - 12 张表的统计卡片网格 (3x4)
      每张卡片：
        表名 + 图标
        统计：A总数 / B总数 / Added / Deleted / Modified
        差异率进度条
        点击跳转到 detail tab
    - 总览：输入差异数 vs 输出差异数

  Section 3: Detail Tabs
    Tab 栏：BOM | FCST | I_O | Supply | Switch | Calendar | PlanConfig | PlanOutput | Balance | (Item/Line 可折叠)

    每个 Tab 内：
      - Toolbar: Filter (Change Type: All/Add/Del/Modify), Search (PN, Line...), Column Toggle, Download
      - View Toggle: Table / Chart / Heatmap
      - Table: 冻结列 (Key) + V_A + V_B + Diff + Diff% + ChangeType badge
        - 高亮规则：Add 绿背景, Del 红背景, Modify 黄背景, Diff 负值红字
      - Chart (若适用):
        - FCST: SKU 周需求双版本柱状图
        - Supply: PN 累计到料双曲线
        - Calendar: LINE UPH 曲线
        - Output: LINE产能曲线 / SKU产能曲线
        - Balance: ITEM库存曲线

#### 4.5.2 交互细节

- **Version Label:** 用户可编辑版本名称，默认用 MPS_RECORD_CODE 或 文件名 或 时间戳
- **高亮：**
  - 表头固定，首列固定 (SKU / LINE)
  - Diff 列排序：按 delta 绝对值排序，快速定位大差异
  - 负库存 Balance <0 红色加粗
- **钻取：**
  - 点击某 SKU，在其它 Tab 自动过滤该 SKU 相关数据 (跨表联动)
  - 例如：在 BOM Tab 点击 SK-xxx，自动在 FCST, Output, Balance 中筛选该 SKU
- **下载：**
  - 每个 Tab 独立下载 Excel (A+B+Diff 3列)
  - 汇总下载：所有表差异汇总到一个 Excel 多 Sheet

#### 4.5.3 复用现有组件

- 复用 `plan_merge` 的 dropdown filter 组件 (search + multi-select)
- 复用 table frozen 逻辑
- 复用 modal schema 显示

---

### 4.6 API 设计

```
V2V 命名空间：/v2v

GET  /v2v/                         -> 返回 V2V 前端页面 (或复用 global index.html，路由切换)
GET  /v2v/templates/schema        -> 各表字段说明

POST /v2v/api/compare
  FormData:
    version_a_zip: File
    version_b_zip: File
    version_a_name: string (optional)
    version_b_name: string (optional)
    granularity: daily|weekly (default weekly)
  Response:
    {
      "job_id": "uuid",
      "versions": {"a": {"name":"V1","record_code":"...", "file_count":12, "date_range":[...]}, "b": {...}},
      "summary": {
         "bom": {"total_a":553,"total_b":560,"added":10,"deleted":3,"modified":15},
         "fcst": {...},
         ...
      },
      "warnings": []
    }

GET  /v2v/api/diff/{table_name}?job_id=xxx&change_type=MODIFY&page=1&page_size=100&search=SK-xxx
  Response:
    {
      "table": "bom",
      "pagination": {"page":1,"page_size":100,"total":15},
      "records": [ {key, field, value_a, value_b, delta, change_type} ],
      "weeks": [...], # 若有周维度
    }

GET  /v2v/api/diff/{table}/chart?job_id=xxx&key=xxx  # 获取某key的图表数据 (时间序列双版本)

POST /v2v/api/download
  Body: {job_id, tables: ["bom","fcst",...], format: "excel"}
  Response: binary xlsx

POST /v2v/api/download/{table}
  单表下载

# Job 持久化 (可选)
- 简单版：job 数据存内存或上传后 temp 文件，job_id 有效期 1h
- 进阶版：存 SQLite 或本地 json，支持历史 job 列表
```

---

## 5. 实现阶段规划

### Phase 1: MVP - 基础框架 + 核心 3 表

**目标：** 跑通端到端，验证架构

- [ ] 后端：
  - 创建 `app/modules/v2v/` Blueprint，注册 `/v2v` 前缀
  - 实现 Zip 解压 + 12 表识别 + Pandas 读取 (可先只读 BOM, FCST, PlanConfig)
  - 实现 `diff_bom`, `diff_fcst`, `diff_plan_config` 3 个 diff 引擎
  - API: `/v2v/api/compare` 返回 summary
  - API: `/v2v/api/diff/{table}` 返回分页 detail
- [ ] 前端：
  - 在 sidebar 增加 V2V 入口
  - 改造 `index.html` 为多模块：module 切换显示不同 section (或新建 `v2v.html`)
  - 上传双 Zip，显示解析状态
  - Summary 卡片展示
  - 3 个 Tab 的表格展示差异，高亮
- [ ] 测试：
  - 使用 `Ivy-20260716-gated-v2` 复制一份改几行作为 V2，用来测试 diff

**预计工作量：** 2-3 天

---

### Phase 2: 输入全量表 + 图表

**目标：** 完成所有输入表的对比

- [ ] 实现剩余输入 diff：
  - I_O实际值表 (覆盖检查 + 一致性)
  - Supply供应表 (weekly/daily 双视图)
  - 切换矩阵
  - 线体日历 (UPH curve) - 重点图表
  - 料号/线体 (简单 Add/Del)
- [ ] 前端图表：
  - 引入 Chart.js 或 ECharts (CDN 方式，避免 npm)
  - 对 FCST, Supply, Calendar 实现折线/柱状图双版本对比
- [ ] 优化：
  - 大表分页 + 搜索
  - 性能：Pandas 分块读取，列裁剪

**预计：** 3-4 天

---

### Phase 3: 输出表 + 维度钻取

**目标：** 完成输出表对比，核心价值所在

- [ ] 排产结果快照表：
  - 支持按 Line / SKU / Day/Week 聚合切换
  - 实现 3 粒度：Shift / Day / Week
  - 热力图：Line x Date diff
  - 曲线图：选中 SKU/Line 的双版本产能对比
- [ ] 结存表：
  - Balance 曲线 + 负库存预警
  - 按 ITEM 维度过滤
- [ ] 跨表联动：
  - 点击 SKU 在所有 Tab 同步过滤 (global filter bus)
- [ ] 下载：
  - 单表 + 全量 Excel 导出

**预计：** 3-4 天

---

### Phase 4:  polish + 高级功能

- [ ] 版本管理：历史 job 列表，本地存储最近 5 次比较
- [ ] 阈值配置：只显示差异 > X% 的记录，过滤噪音
- [ ] 自定义 Key：允许用户配置对比 Key (如 BOM 是否用 COMPONENT_SEQ_ID)
- [ ] 导入方式扩展：支持文件夹直接选择 (`webkitdirectory`)，支持单文件多 Sheet Excel
- [ ] 性能：后端使用 Polars 加速 (比 Pandas 快 5x) 或 DuckDB
- [ ] UI：暗色模式，表格列可拖拽调整宽度
- [ ] 文档：更新 README，录制 demo GIF

**预计：** 2-3 天

**总计：** 约 10-14 天完成全功能

---

## 6. 技术选型与风险

### 6.1 技术栈

- **后端：** Flask (已有) + Pandas (已有) + openpyxl (已有) + Python 3.10+
- **前端：** Vanilla JS (已有，无需 React) + Chart.js (CDN) + 复用现有 CSS
- **存储：** 内存 + temp 文件 (uploads/job_id)，无需数据库 (MVP)
- **Excel 导出：** openpyxl 样式高亮

### 6.2 风险 & 对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 大文件导致 OOM (Calendar 39w行) | 后端崩溃 | 分块读取，只读必要列 `usecols`，限制上传大小 100M，前端提示 |
| Pandas merge 大表慢 | 接口超时 | 使用 Polars 或 按 LINE_CODE 分批 diff，异步任务 + 进度条 |
| 前端一次性渲染大量 diff 行卡顿 | UI 卡死 | 分页，虚拟滚动 (只渲染可见行)，或限制 Top 1000 差异 |
| 用户上传文件名不规范 | 解析失败 | 支持模糊匹配：`bom` 关键词匹配，列举已识别文件列表让用户确认 |
| FCST 主+明细 JOIN 逻辑错误 | FCST diff 不准 | 写单元测试，用样本数据验证 JOIN 后 SKU 数量 |
| 双版本时间覆盖不一致 | 对比误判 | 明确策略：并集补空，交集一致性检查，UI 明确标出额外时间段 |

---

## 7. 待确认问题 (Open Questions)

1. **I_O实际值表中的 PLAN_TYPE 含义：** 除了 FCST 还有什么类型？是否都需要对比？-只有这一种FCST的
2. **线体日历中 checkout 含义：** `PLAN_TYPE=checkout` 是什么业务？需要确认。 - 这个后续再确认吧，你就去比就好了先。
3. **版本标识：** 用户希望 version 名称如何定义？用 MPS_RECORD_CODE 还是自定义命名 (如 V1_0716, V2_0723)？- 这个在文件夹中去定义吧
4. **上传方式偏好：** 是否接受 Zip 方式，还是希望直接选文件夹？是否会有单文件多 Sheet 的情况？- 就是一个文件夹一个文件夹的去比吧，不同版本的放在不同的文件夹，都是这么些file呢
5. **输出对比粒度：** 排产结果是按白班/夜班分开看，还是合并到天/周？默认聚合到天还是周？- 支持的颗粒度可以到shift，但是呢，是这样，可以自己选，就是先从周度看是否有问题，然后周度没问题的就不看了，周度有问题就看到天，天有问题的，再选shift的那种，所以可以drill down的那种。
6. **GS (General Stock) 是否也需要对比？** 文档没提到 Supply 的 QTY_REM 等字段是否需对比。- 需要对比
7. **是否需要支持 3 版本对比 (V1 vs V2 vs V3)？** 还是先只支持 2 版本。- 两个版本就行
8. **权限：** 是否需要登录，或内部使用即可？- 先不考虑权限的问题，登录即可使用的那种

---

## 8. 附录：样本数据统计 (Ivy-20260716-gated-v2)

| 表 | 行数 | 列数 | 关键列 |
|----|------|------|--------|
| BOM快照 | 553 | 34 | PARENT_PN_CODE, ITEM_NO, UNIT_NUM, LOSS_RATE, PROCESS_LT |
| FCST主表 | 66 | 24 | ID, PN_CODE |
| FCST明细 | 2951 | 13 | MAIN_ID, ACTUALFIRSTDAYOFWEEK, ACTUALWEEKVALUE |
| I_O实际值 | 131,481 | 11 | LINE_CODE, SKU, PLAN_DATE, PLAN_VALUE |
| Supply供应 | 121,129 | 12 | PN_CODE, KITTING_DATE, KITTING_VALUE |
| 切换矩阵 | 2,803 | 11 | LINE_CODE, BEFORE/AFTER_PN, SWITCH_DURATION |
| 料号快照 | 444 | 39 | ITEM_NO, STYLE, COLOR |
| 线体快照 | 61 | 21 | LINE_CODE, LINE_LEVEL, LINE_TYPE |
| 线体日历 | 397,081 | 15 | LINE_CODE, PLAN_TYPE, PLAN_DATE, SHIFT, PLAN_VALUE |
| 计划设置 | 2 (1+header) | 50 | 单行 50 字段 |
| 排产结果输出 | 203,684 | 16 | LINE_CODE, SKU, PLAN_DATE, PLAN_VALUE |
| 结存输出 | 199,547 | 9 | ITEM_CODE, PLAN_DATE, BALANCE_QTY |

**总行数：~1M 行**，属于中大型 Excel 处理，需注意性能。

---

## 9. 下一步行动

1. **用户确认：** 审阅本设计文档，确认上传方式、对比粒度、优先级
2. **原型：** 基于 Phase 1 创建 `app/modules/v2v/` 空壳 + 前端占位页面，跑通路由
3. **Demo 数据准备：** 将 `Ivy-20260716-gated-v2` 复制一份，手动修改少量数据作为 Version B，用于开发测试
4. **开始 Phase 1 编码**

---

*文档生成时间：2026-07-20*
*作者：OpenCode Analysis*
*基于：gtk_aps_dashboard 仓库现状 + 用户口述需求 + Ivy-20260716-gated-v2 样本数据分析*
