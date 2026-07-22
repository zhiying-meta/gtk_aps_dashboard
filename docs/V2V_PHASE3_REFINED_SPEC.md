# V2V Phase3 - 输出表精细化设计 (Refined Spec based on User Feedback 2026-07-20)

> 用户反馈：输出报表不要一上来就全量几十万行，要自由组合、渐进式钻取、数据量可控

---

## 1. 用户核心顾虑 (Original Feedback)

> "针对输出的报表，我其实是希望这个东西是你自由组合，在网页端显示出来。如果我需要下载我就download下来，但不是一定要一个报表出来...我不会需要一次性把所有数据都拿出来比较...我按照自己理解的层级关系去选择，可以比较自由地选择...输出的结果，我希望的是可以从不同维度，不断 drill down 的层级，可能从一个更 overall 的 picture 上去比较，发现有问题，我再 drill down...减少数据展示...最开始可能有一个 weekly 对比，数据展示比较小一点，但如果要去 daily，我可以选择 OK，我想要哪一个 week，在那个 week 下面再做对比，而不是一开始选那么多...还要考虑到使用阅读方面的便利性...跑个几十万行十几万行，随着数据量越来越多的时候，其实就不太现实...不要盲目粗暴地全部分析，给我一个几十万行的报表，就算有问题没问题，我很难看出来"

**提炼：**

1.  **不要大而全报表**：拒绝一次性全量 20万行 diff + 导出大 Excel
2.  **自由组合维度**：用户按自己理解的层级选择维度对比，不是固定模板
3.  **渐进式 Drill-down**：Overall -> Detail，Weekly 有问题 -> 再看该 Week 的 Daily -> 再看 Shift
4.  **数据量可控 & 阅读便利**：首屏应是小数据（几十到几百行汇总），通过点击下钻逐步展开
5.  **下载可选且只下当前视图**：不是全量

---

## 2. 设计原则重塑

### 旧思路 (Phase3 初版 - 废弃)

- 后端一次性 `outer merge` 20万行明细，计算所有 diff，返回全量 20万行给前端
- 前端全量渲染或分页，生成大报表 Excel
- 问题：OOM、慢、看不懂

### 新思路 (Phase3 Refined - 当前)

**Query-driven + 后端聚合 + 前端渐进披露**

- **原则1：后端聚合，默认只返回有差异的汇总**
  - 用户选 `group_by=LINE_CODE` + `granularity=week`，后端先 `groupby sum` 聚合为 60线×20周=1200行，再 merge diff，再过滤 `diff !=0`，可能只剩 50 行
  - 首屏数据量从 20万 → 50 行

- **原则2：Top N + 阈值过滤噪音**
  - 按 `abs(diff)` 倒序，默认 Top 100
  - 支持阈值：`abs(diff) > 100` 或 `diff% > 5%`

- **原则3：懒加载 Drill-down**
  - 面包屑导航：`All Weeks (LINE维度) > LINE=AL6-Frame Week=2026/07/12 (Day) > Day=2026/07/08 (Shift)`
  - 每次下钻是新 API 请求，带上父级 filters，只查子集

- **原则4：维度构建器 (Dimension Builder)**
  - 用户自由勾选 group_by 字段：LINE_CODE, SKU, PLAN_ITEM, PLAN_TYPE, etc.
  - 粒度独立：Week/Day/Shift
  - 预设快捷按钮：最常用组合一键切换

---

## 3. 输出表业务维度分析

### 3.1 排产结果快照表_输出 (plan_output) - 20w行

**原始字段**: LINE_CODE, SHIFT_NAME, PLAN_ITEM (INPUT/OUTPUT), PLAN_TYPE (KITTING?), SKU (SK-/GB-/FR-/LT-/RT-), PLAN_DATE, PLAN_VALUE

**可分组维度**:

- LINE_CODE: 线体维度 (AL6-Frame, AL1-PKG...)
- SKU: 物料维度 (SK-xxx, GB-xxx, FR-xxx...)
- PLAN_ITEM: INPUT vs OUTPUT
- PLAN_DATE: 时间 (Week/Day/Shift 粒度)
- SHIFT_NAME: 白班/夜班 (Shift 粒度时)
- PLAN_TYPE: KITTING 等

**常用聚合场景**:

1.  **按线体周汇总** (最常用 Overall): `group_by=LINE_CODE, granularity=week` → 看哪条线哪周总产能有差异
2.  **按SKU周汇总**: `group_by=SKU, granularity=week` → 看哪个成品/GB 总量有差异
3.  **按线体+SKU周汇总**: `group_by=LINE_CODE,SKU, granularity=week` → 细一点，1200行变 1w行但过滤后可能 100 行
4.  **按线体+SKU天汇总**: `group_by=LINE_CODE,SKU, granularity=day` + filter `WEEK=2026/07/12` → 下钻后
5.  **最细**: `group_by=LINE_CODE,SKU,SHIFT,PLAN_ITEM, granularity=shift` + filter `LINE=... DATE=...`

### 3.2 结存表_输出 (balance) - 19w行

**原始字段**: PLAN_DATE, SHIFT_NAME, ITEM_CODE, SHIFT_OUT_QTY, PRE_INPUT_QTY, BALANCE_QTY

**可分组维度**: ITEM_CODE, PLAN_DATE, SHIFT

**常用场景**:

1.  **按物料周汇总**: `group_by=ITEM_CODE, granularity=week` → 看哪个物料周结存有差异，负库存预警
2.  **按物料天汇总**: 下钻
3.  **按物料Shift**: 最细

---

## 4. 交互流程举例 (User Story)

### Story A: 排产结果 - 按线体看

**Step0**: 选版本 A=0716 vs B=0723

**Step1 - 维度构建器**:

```
Grouping: [✓] LINE_CODE   Granularity: [Week ▼]
Filter: LINE: All, 只看有差异: [✓] 是, 阈值 Diff > 0

[▶应用]
```

**Step2 - Overall 表格 (小, 可能 2 行)**:

| LINE_CODE | Week | A总量 | B总量 | Diff | Diff% |  |
|---|---|---:|---:|---:|---:|---|
| AL6-Frame | 2026/07/12 | 1200 | 1000 | -200 | -16% | [▶看SKU] |
| AL1-PKG | 2026/07/19 | 500 | 800 | +300 | +60% | [▶看SKU] |

**Step3 - 点 [▶看SKU]**:

自动设置 Filter `LINE=AL6-Frame, WEEK=2026/07/12`, Grouping 改为 `SKU + Day`

| SKU | Day | A | B | Diff |  |
|---|---|---:|---:|---:|---|
| FR-Rec M-BLACK | 2026/07/08 | 100 | 0 | -100 | [▶Shift] |

**Step4 - 点 [▶Shift]**:

Filter `LINE=AL6-Frame, SKU=FR-Rec..., DATE=2026/07/08`, Granularity=Shift

| SKU | Date | Shift | A | B | Diff |
|---|---|---|---|---:|---:|
| FR-Rec | 2026/07/08 | 白班 | 60 | 0 | -60 |
| FR-Rec | 2026/07/08 | 夜班 | 40 | 0 | -40 |

**全程每次请求 <100 行**

### Story B: 结存 - 按物料看负库存

Grouping: `ITEM_CODE + Week`, 过滤 `BALANCE<0` 或 `diff !=0`

首屏只显示有负库存或结存差异的物料周，几十行，点击下钻看天/Shift，Chart 显示该物料双版本结存曲线。

---

## 5. 后端 API 设计 (Refined)

### 5.1 聚合 Diff API

```
GET /v2v/api/output/diff
  ?job_id=xxx
  &table=plan_output|balance
  &group_by=LINE_CODE,SKU         # 逗号分隔，自由组合
  &granularity=week|day|shift
  &filters=LINE_CODE=AL6-Frame;WEEK=2026-07-12  # 分号分隔 key=value
  &only_diff=true                  # 默认true，只返回 diff!=0
  &threshold_abs=0
  &threshold_pct=0
  &sort=abs_diff_desc              # 按 abs(diff) 倒序
  &page=1&page_size=100
```

**处理逻辑**:

1. 加载对应表 df_a, df_b (不加载其他表)
2. 应用 filters (先过滤 df_a/df_b)
3. 按 granularity 处理日期：`week` -> 转 Saturday, `day` -> date, `shift` -> date+shift
4. 按 group_by + granularity 聚合：`df.groupby(group_by + [time_col])['PLAN_VALUE'].sum()`
5. Outer merge 聚合后结果，计算 diff, diff%
6. 过滤 only_diff
7. 过滤 threshold
8. 排序, 分页返回

**性能**:

- 20万行 groupby 在 Pandas <0.5s
- 结果缓存：对 (job_id, table, group_by, granularity, filters) 做 LRU 缓存 5min，避免重复计算

### 5.2 Chart API (已存在，沿用)

```
GET /v2v/api/chart/plan_output?job_id=xxx&line_code=AL6-Frame&sku=FR-Rec...&granularity=day
```

返回该过滤条件下时间序列双版本对比，用于右侧图表。

### 5.3 Download API

```
POST /v2v/api/download/current_view
  Body: {job_id, table, group_by, granularity, filters, only_diff}
```

只导出当前视图的聚合结果，不是全量 20万行。若用户真要全量明细，需显式选最细粒度且关闭 only_diff，并提示数据量大。

---

## 6. 前端 UI 设计 (Refined)

```
┌─ 左侧 300px 维度构建器 ─┐┌─ 中间 表格 + 面包屑 ──────────┐┌─ 右侧 Chart (可选) ─┐
│ Group by:                ││ Breadcrumb: All Weeks > ...  ││ 选中行趋势图      │
│  [ ] LINE_CODE           ││                               ││  A vs B 曲线      │
│  [✓] SKU                 ││ Granularity: [W][D][S]        ││                  │
│  [ ] PLAN_ITEM           ││                               ││                  │
│                          ││ 表格:  聚合结果 (小)          ││                  │
│ Granularity: Week▼       ││  LINE | Week | A | B |Diff|Drill││                │
│                          ││  ...                         ││                  │
│ Filters:                 ││                               ││                  │
│  LINE: [All ▼]           ││ Pagination: 1/5               ││                  │
│  SKU: [SK- ▼]            ││                               ││                  │
│  [✓] Only diff           ││                               ││                  │
│  Threshold: > [0]        ││                               ││                  │
│                          ││                               ││                  │
│ [▶ Apply]  快捷按钮:      ││                               ││                  │
│  按线体周汇总             ││                               ││                  │
│  按SKU周汇总              ││                               ││                  │
└──────────────────────────┘└───────────────────────────────┘└───────────────────┘
```

**快捷按钮**:

- 按线体周汇总 (默认 Overall)
- 按SKU周汇总
- 按线体SKU周汇总
- 按物料周汇总 (Balance)

**面包屑 + Drill**: 点击表格行 Drill 列，自动把该行 key 加入 filters，granularity 下钻一级，重新查询。

---

## 7. 数据量控制策略 (总结)

| 策略 | 说明 | 效果 |
|------|------|------|
| 后端聚合 | 先 groupby 再 diff | 20万 → 1200 → 过滤后 50 行 |
| Only Diff 默认开 | `diff !=0` 才返回 | 噪音清零，首屏干净 |
| Top N + 阈值 | `abs(diff)` 倒序 Top 100 + 阈值 | 即使 1200 行也只看最大差异 |
| 分页 | page_size=100 | 前端不卡 |
| 懒加载 Drill | 每次下钻新请求，只查子集 | 每次请求 <100 行 |
| 缓存 | LRU 缓存聚合结果 | 重复查询 <100ms |
| 下载当前视图 | 不是全量 | 避免几十万行 Excel |

---

## 8. 实现步骤 (Phase3 Refined)

- [ ] 后端：创建 `parsers/plan_output_parser.py` + `balance_parser.py` 支持 group_by 聚合
- [ ] 后端：重构 `diff_engine.py` -> `get_aggregated_diff()` 支持 group_by/filters/only_diff/threshold/sort
- [ ] 后端：新增 `/v2v/api/output/diff` (或复用 `/v2v/api/diff/<table>` 但扩展参数)
- [ ] 后端：`/v2v/api/chart/plan_output` + `/balance` 实现时间序列
- [ ] 前端：维度构建器组件 (checkbox group + granularity toggle + filter selects)
- [ ] 前端：面包屑 + Drill 按钮逻辑
- [ ] 前端：表格渲染聚合结果 + Chart 联动 (点击行更新图表)
- [ ] 前端：快捷按钮 + Only Diff + Threshold
- [ ] 联调：用 Ivy 20万行数据测试 按线体周汇总 -> 下钻 -> 按SKU天汇总 全流程

---

## 9. 与用户确认的点已纳入

- ✅ 自由组合维度：Group by 多选
- ✅ 网页端为主，下载可选且只下当前视图
- ✅ 不是一次性全量比较：后端聚合 + only_diff + Top N
- ✅ Drill-down 层级：Week -> Day -> Shift，面包屑导航
- ✅ 阅读便利：首屏小数据，渐进披露，Chart 辅助

---

*更新时间: 2026-07-20 (用户反馈后)*
*状态: 已确认，进入 Phase3 开发*
