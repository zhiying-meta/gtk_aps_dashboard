# V2V 模块 - 已确认需求规格 (Confirmed Spec)

> 基于用户对 8 个开放问题的答复，更新后的最终规格

**更新时间:** 2026-07-20
**状态:** ✅ 已确认，可进入开发

---

## 已确认答复

| # | 问题 | 答复 | 对实现的影响 |
|---|------|------|-------------|
| 1 | I_O实际值表 PLAN_TYPE 有哪些？ | **只有 FCST 一种** | 简化：只对比 FCST 类型，但代码保留通用性以防未来扩展 |
| 2 | 线体日历 checkout 含义 | **后续再确认，先直接对比** | 不需业务解释，所有 PLAN_TYPE 统一按 Key=(LINE,TYPE,DATE,SHIFT) 对比 |
| 3 | 版本标识 | **文件夹中定义** | 版本名 = 文件夹名，如 `Ivy-20260716-gated-v2` vs `Ivy-20260723-gated-v3`，用文件夹名作为 Version Label |
| 4 | 上传方式 | **文件夹 vs 文件夹，不同版本的放不同文件夹，里面都是同样的 file** | 前端提供两个文件夹上传入口 (webkitdirectory)，或后端扫描 `data/` 下不同版本子目录；Zip 作为备选，MVP 先支持文件夹名选择 |
| 5 | 输出对比粒度 | **支持到 shift，但要 drill down：周->天->shift，周没问题不看，周有问题看天，天有问题看shift** | 核心UX：层级钻取设计，默认周粒度，异常时可下钻 |
| 6 | GS QTY_REM 是否对比 | **需要对比** | Supply表需对比所有数值字段：KITTING_VALUE, QTY_REM, QTY_REM2, TOTAL_LOSS_QTY |
| 7 | 是否支持3版本 | **两个版本就行** | 只做 A vs B，不做多版本矩阵 |
| 8 | 权限 | **先不考虑，登录即可用** | 无需登录态，直接可用 |

---

## 修订后的核心设计

### 1. 上传 / 数据源 (Folder-based)

**用户场景：**
```
本地文件结构：
~/aps_data/
  ├── Ivy-20260716-gated-v2/   -> 12 个 xlsx
  └── Ivy-20260723-gated-v3/   -> 12 个 xlsx
```

**前端实现 (推荐)：**
- 两个大的 Drop Zone：
  - **Version A**: 点击选择文件夹 (input webkitdirectory) -> 显示文件夹名作为版本名 + 解析出 12 表清单 ✓/✗
  - **Version B**: 同上
- 备选：后端提供 `data/` 目录扫描，类似现有 `plan_merge_demo` 自动扫描，若 `data/` 下有多个版本文件夹，直接下拉选择 A/B，无需上传（更适合服务器部署）
  - API: `GET /v2v/api/versions` -> 扫描 `Ivy-*` 或 `data/v2v/*` 目录，返回版本列表
  - 前端：两个下拉框选版本

**MVP 同时支持两种：**
- 优先实现 **文件上传** (folder)，因为用户本地已有文件夹
- 第二步实现 **服务器目录扫描** (若用户把文件夹放到服务器 `v2v_data/` 下)

**后端存储：**
```
uploads/v2v/{job_id}/
  ├── vA/
  │   ├── BOM快照.xlsx
  │   ├── FCST主表.xlsx
  │   └── ...
  └── vB/
      └── ...
```

---

### 2. Drill-Down 钻取设计 (关键)

#### 2.1 输出表：排产结果 + 结存表

**粒度层级：**
```
Week (周六为周结束，周日-周六为一周)
  └─> Day (自然日)
       └─> Shift (白班/夜班)
```

**交互流程：**
1. **默认视图：Weekly**
   - 每行：LINE_CODE + SKU + Week + V_A总量 + V_B总量 + Diff + Diff% + ChangeType
   - 按周聚合：`SUM(PLAN_VALUE) group by (LINE,SKU,Week)`
   - 表头：Week 列 (如 `2026/07/12 Wk`)
2. **标记异常周：**
   - 若某行 Diff !=0，整行黄色高亮，且提供 `▶ Drill` 按钮
   - 点击 `▶` 展开或跳转到 Day 视图，并自动过滤到该 (LINE,SKU,Week)
3. **Day 视图：**
   - `SUM(PLAN_VALUE) group by (LINE,SKU,Day)` 过滤到特定 Week
   - 显示该周内每天的差异
   - 同样，某天有差异可继续下钻到 Shift
4. **Shift 视图 (最细)：**
   - 原始粒度：`LINE,SKU,DATE,SHIFT,PLAN_ITEM,PLAN_VALUE`
   - 显示白班/夜班分别的差异

**UI 组件：**
- 面包屑导航：`All Weeks > Week 2026/07/12 > Day 2026/07/15 > Shift`
- 按钮：`[Week] [Day] [Shift]` 切换粒度 (类似现有 FG/GB 切换)
- 表格行：可点击展开 (类似现有 pivot 的 ▸/▾)

**聚合逻辑伪代码：**
```python
def aggregate_plan(df, granularity, filters):
    # granularity: 'week' | 'day' | 'shift'
    if granularity == 'week':
        df['week'] = df['PLAN_DATE'].apply(to_saturday)
        grouped = df.groupby(['LINE_CODE','SKU','week'])['PLAN_VALUE'].sum()
    elif granularity == 'day':
        grouped = df.groupby(['LINE_CODE','SKU','PLAN_DATE'])['PLAN_VALUE'].sum()
    else: # shift
        grouped = df.groupby(['LINE_CODE','SKU','PLAN_DATE','SHIFT_NAME','PLAN_ITEM'])...
    # 然后 A vs B outer merge diff
```

#### 2.2 输入表是否也需要 Drill-Down？

- **I_O实际值表**：也需要 Week->Day->Shift，因为原始就有 Shift
- **Supply表**：建议 Week->Day，因为是到料日维度，无 Shift
- **FCST表**：只有 Week 粒度 (ACTUALFIRSTDAYOFWEEK 本身就是周)，无需下钻
- **Calendar表**：有 Shift，需支持 Day->Shift，或 Week->Day->Shift (因为 PLAN_DATE 是隔几天的，Week 粒度也有意义)
- **BOM/Switch/Config**：无时间维度，无需钻取

---

### 3. Supply 表扩展对比 (基于 Q6 回答)

**原计划：** 只对比 KITTING_VALUE

**修订后：** 对比所有数量字段：
- KITTING_VALUE
- QTY_REM
- QTY_REM2
- TOTAL_LOSS_QTY
- DATA_TYPE (通常都是 KITTING，但若变需高亮)

**Key 仍为：**(PN_CODE, KITTING_DATE)

**Diff 记录：** 每个 Field 单独一条 DiffRecord，或一行记录包含多 Field 变化
推荐：一行包含多列对比：
```
PN_CODE | KITTING_DATE | Field | V_A | V_B | Diff
--------|--------------|-------|-----|-----|-----
PN-001  | 2026/08/01   | KITTING_VALUE | 100 | 120 | +20
PN-001  | 2026/08/01   | QTY_REM       | 10  | 0   | -10
```

或横向展开：
```
PN_CODE | Date | KITTING_A | KITTING_B | KITTING_Diff | QTY_REM_A | QTY_REM_B ...
```

推荐前者 (纵向)，更易扩展。

---

### 4. 前端页面详细规划 (修订版)

#### 4.1 路由

```
GET /v2v -> V2V 模块 SPA (新建 static/modules/v2v/index.html 或复用 global/index.html 动态加载)
```

Sidebar 增加：
```html
<a class="nav-item" data-module="v2v">
  <span>🔍</span> V2V Comparison
</a>
```

#### 4.2 Section 1: Version Loader

```
┌─────────────────────────┐  ┌─────────────────────────┐
│ Version A               │  │ Version B               │
│ [选择文件夹]            │  │ [选择文件夹]            │
│ 名: Ivy-20260716-gated-v2│  │ 名: Ivy-20260723-gated-v3│
│ 12 文件已识别:          │  │ 12 文件已识别:          │
│ ✓ BOM快照 (553行)       │  │ ✓ BOM快照 (560行)       │
│ ✓ FCST主表 (66行)       │  │ ✓ FCST主表 (70行)       │
│ ✓ ...                   │  │ ✓ ...                   │
│ 日期范围: 2026/04-2026/12│  │ 日期范围: 2026/04-2026/12│
└─────────────────────────┘  └─────────────────────────┘

[⚙️ 粒度: Week ▼] [阈值: 0% ▼] [▶ Compare]
```

**技术：**
- `<input type="file" webkitdirectory directory>` 获取文件夹
- 前端用 JS 遍历 `event.target.files`，按文件名关键词匹配表类型
- 实时显示已识别文件数
- 点击 Compare 时 FormData 上传两个文件夹的所有文件 (或先只传文件名，后端从服务器 `data/` 读)

#### 4.3 Section 2: Summary (12 卡片)

沿用之前设计，但增加文件夹名显示：

```
Total: 12 tables scanned
Version A: Ivy-20260716 (MPS: 5253...)  vs  Version B: Ivy-20260723 (MPS: 5253...)

[ BOM: 553 vs 560 (+7) ] [ FCST: 66 vs 70 ... ] ...
```

每卡片点击跳转对应 Tab。

#### 4.4 Section 3: Detail Tabs + Drill-Down

```
Tabs: [BOM] [FCST] [I_O] [Supply] [Switch] [Calendar] [PlanConfig] [PlanOutput ⭐] [Balance ⭐]

PlanOutput Tab 内：
  粒度切换：[Week (默认)] [Day] [Shift]   面包屑：All > Week 2026/07/12
  过滤： ChangeType [All/Add/Del/Modify] + Search LINE/SKU + Threshold
  表格：
    | LINE | SKU | Week | V_A | V_B | Diff | Diff% | V | Drill |
    | AL6-Frame | FR-Rec | 2026/07/12 | 100 | 120 | +20 | +20% | MODIFY | [▶ Day] |

  点击 [▶ Day] 后：
    自动切换到 Day 粒度，并过滤 LINE=AL6-Frame, SKU=FR-Rec, Week=2026/07/12
    表格变为：
    | LINE | SKU | Date | V_A | V_B | Diff | Drill |
    | ...  | ... | 2026/07/08 | 10 | 20 | +10 | [▶ Shift] |
```

**实现：**
- 前端状态：`currentTable`, `currentGranularity`, `drillFilters = {line, sku, week, day}`
- 每次粒度切换或 Drill 点击，调用 `GET /v2v/api/diff/{table}?granularity=day&week=2026-07-12&line=AL6-Frame`

---

### 5. 后端 API 修订 (支持 Drill-Down)

```
POST /v2v/api/compare
  Input: FormData with files for vA and vB (webkitdirectory -> multiple files with relative paths)
  Output: { job_id, versions: {a:{name, file_stats}, b:{...}}, summary: {bom:{...}, ...} }

GET /v2v/api/versions  (可选，服务器目录扫描模式)
  Output: [{name: "Ivy-20260716-gated-v2", path: "...", file_count:12, mps_code:"5253..."}]

POST /v2v/api/compare_by_path  (服务器目录模式)
  Body: {a_path: "Ivy-20260716-gated-v2", b_path: "Ivy-20260723-gated-v3"}
  Output: 同 compare

GET /v2v/api/diff/{table_name}?job_id=xxx&granularity=week|day|shift&change_type=MODIFY&week=2026-07-12&line=AL6-Frame&sku=FR-xxx&page=1
  Output: {
    table: "plan_output",
    granularity: "week",
    pagination: {page, size, total},
    records: [
      {LINE_CODE, SKU, week/day/shift, value_a, value_b, diff, diff_percent, change_type},
      ...
    ],
    breadcrumbs: [{label:"All Weeks", granularity:"week", filters:{}}, {label:"Week 2026/07/12", granularity:"day", filters:{week:"2026-07-12"}}]
  }

GET /v2v/api/diff/{table}/chart?job_id=xxx&line=xxx&sku=xxx
  Output: 时间序列对比数据，用于折线图

POST /v2v/api/download
  Body: {job_id, tables:[], granularity: "week"}
```

---

### 6. 实现步骤 (修订)

#### Phase 1: MVP 框架 + 上传 (1-2 天)

- [ ] 创建 `app/modules/v2v/` Blueprint, `url_prefix='/v2v'`
- [ ] 后端 `utils.py`: Zip/文件夹解析，12 表识别 (模糊匹配 `bom`, `fcst主`, `fcst明细`, `io实际`, `supply`, `切换矩阵`, `料号`, `线体快照`, `线体日历`, `计划设置`, `排产结果`, `结存`)
- [ ] 后端 `routes.py`: `/v2v/api/compare` 支持 folder upload (前端 webkitdirectory 收集所有文件)
- [ ] 后端 `diff_engine.py`: 实现 `diff_bom`, `diff_fcst` (JOIN), `diff_config` 3 表
- [ ] 前端：sidebar 新增 V2V 入口，创建 `static/modules/v2v/index.html` 或在 `global/index.html` 新增 section
- [ ] 前端：Version A/B 两个文件夹选择器，显示已识别文件清单
- [ ] 前端：Summary 12 卡片
- [ ] 测试：用 `Ivy-20260716-gated-v2` 复制一份改几行作为 V2

#### Phase 2: 输入表全量 + 基础表格 (2 天)

- [ ] 剩余输入表 diff 实现 (重点 Calendar 39万行需分块)
- [ ] Supply 表扩展多字段对比
- [ ] 前端 Table 组件 (复用 plan_merge 冻结列 + 高亮)

#### Phase 3: 输出表 + Drill-Down (核心, 3 天)

- [ ] 后端：PlanOutput 按 granularity 聚合 + 过滤，支持 week/day/shift 3 档
- [ ] 后端：Balance 同上
- [ ] 后端：I_O, Supply, Calendar 也支持 drill-down
- [ ] 前端：Granularity 切换按钮 + Breadcrumb 面包屑 + Drill ▶ 按钮
- [ ] 前端：Chart.js 引入，PlanOutput/ Balance/Supply/Calendar 曲线图

#### Phase 4: Polish (1-2 天)

- [ ] 服务器目录扫描模式 `/v2v/api/versions`
- [ ] 阈值过滤 (只显示 diff > X%)
- [ ] 下载 Excel (单表 + 全量)
- [ ] 性能优化 (Pandas usecols, 分页)
- [ ] 文档更新 README

---

### 7. 文件清单 (待创建)

```
app/modules/v2v/
├── __init__.py
├── routes.py
├── config.py
├── utils.py              # 文件识别 + 读取
├── diff_engine.py        # 调度各表 diff
└── parsers/
    ├── bom_parser.py
    ├── fcst_parser.py
    ├── io_parser.py
    ├── supply_parser.py
    ├── switch_parser.py
    ├── item_parser.py
    ├── line_parser.py
    ├── calendar_parser.py
    ├── plan_config_parser.py
    ├── plan_output_parser.py
    └── balance_parser.py

static/modules/v2v/
├── index.html (或整合到 global/index.html)
├── app.js
└── style.css
```

---

### 8. 立即下一步

1. ✅ 已确认需求 (本文档)
2. ⏭️ 开始 Phase 1: 创建空 Blueprint + 前端占位页，验证路由
3. ⏭️ 准备测试数据：复制 `Ivy-20260716-gated-v2` 为 `Ivy-20260723-gated-v3` 并修改少量数据
4. ⏭️ 实现 folder upload 解析

---

## 9. Phase3 精细化更新 (基于用户反馈 2026-07-20 最新)

> 用户反馈输出报表不要全量几十万行，要自由组合、渐进式 drill-down

**已创建独立详细设计文档**: `docs/V2V_PHASE3_REFINED_SPEC.md`

**核心变更**:

- 旧：后端一次性 outer merge 20万行全量返回
- 新：Query-driven + 后端聚合 + Only Diff + Top N + 懒加载 Drill-down
  - API 支持 `group_by=LINE_CODE,SKU`, `granularity=week|day|shift`, `filters`, `only_diff`, `threshold`
  - 首屏 20万 → 聚合后 1200 → 过滤后 50 行
  - 面包屑：`All Weeks > LINE=AL6-Frame Week=2026/07/12 > Day=2026/07/08`
  - 快捷按钮：按线体周汇总 / 按SKU周汇总
  - 下载仅当前视图

详见 `V2V_PHASE3_REFINED_SPEC.md` 第 2-7 章。

---

*确认时间: 2026-07-20 (初始) + 2026-07-20 (Phase3 精细化更新)*
*基于: 用户在 V2V_REQUIREMENTS_AND_PLAN.md 中的 8 个答复 + Phase3 口头反馈*
