import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from copy import copy

wb = openpyxl.load_workbook('/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/【界面报表】多版本计划拼接设计.xlsx')

header_font = Font(name="微软雅黑", bold=True, size=12, color="FFFFFF")
sub_font = Font(name="微软雅黑", bold=True, size=11)
normal_font = Font(name="微软雅黑", size=10)
small_font = Font(name="微软雅黑", size=9)
code_font = Font(name="Consolas", size=9)

header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
light_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
orange_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
pink_fill = PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")
violet_fill = PatternFill(start_color="E4DFEC", end_color="E4DFEC", fill_type="solid")

thin_border = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)

def sc(ws, r, c, val, font=normal_font, fill=None, align=None):
    cell = ws.cell(row=r, column=c, value=val)
    cell.font = font
    cell.border = thin_border
    if fill:
        cell.fill = fill
    cell.alignment = align or Alignment(vertical='center', wrap_text=True)
    return cell

def set_header_row(ws, row, vals, fill=header_fill, font=header_font):
    for i, v in enumerate(vals, 1):
        sc(ws, row, i, v, font=font, fill=fill,
           align=Alignment(horizontal='center', vertical='center', wrap_text=True))

# ============================================================
# Sheet 1: Update existing Design -> rename to "字段说明"
# ============================================================
ws_old = wb['Design']
ws_old.title = "字段说明"

# Clear old content after row 14, add detailed field description rows
# The old sheet has 14 rows. Let's replace rows 3-10 with expanded content.

# Keep header rows 1-2, replace 3-10 with detailed versions
# First clear rows 3-14
for row in range(3, 15):
    for col in range(1, 5):
        ws_old.cell(row=row, column=col).value = None

ws_old.column_dimensions['A'].width = 16
ws_old.column_dimensions['B'].width = 18
ws_old.column_dimensions['C'].width = 55
ws_old.column_dimensions['D'].width = 45

# R1 header
sc(ws_old, 1, 1, "字段说明（含取数逻辑）", font=Font(name="微软雅黑", bold=True, size=14))

set_header_row(ws_old, 2, ["字段", "类型", "说明", "示例"])

fields = [
    ["PN", "String", "物料编码 / Part Number\nSKU级：SK-XXXXXXXX-XX\nGB级：GB-XXX-XXX", "SK-1001879-01"],
    ["Usage", "String", "用途/季节标识\n来源：排产结果表 / BOM / CTB 的 Usage/Title 列\n值如：MP / Spring / Fall / Dummy / Demo", "Spring"],
    ["Style", "String", "眼镜款式描述\n来源：排产结果 / CTB / 虚拟料号关系的 Style 列\n值如：Rectangle M / Rectangle L / Bold / Slim Oval", "Rectangle M"],
    ["Color", "String", "颜色/Frame Color\n来源：排产结果 / CTB / 虚拟料号关系的 CMF / Frame Color 列\n值如：BLACK / CLASSIC HAVANA / LINEN / MERLOT", "BLACK"],
    ["Version-Type", "String", "版本类型枚举：\n• ExF — Forecast 基线（来自 FCST sheet）\n• Ungated — 无限制排产版本（来自 ungated 排产结果表）\n• Gated — 受限排产版本（来自 gated 排产结果表）\n• CTB — 物料就绪数据（来自 Modelo SKU/GB CTB Publish）\n输出顺序：ExF → Ungated → Gated → CTB", "Ungated"],
    ["Version-Detail", "String", "指标细分枚举：\n• ETD — 预计发货量（Saturday Cut-Off）\n• ETD vs ExF — ETD 与 Forecast 的差值 = ETD - ExF\n• Packout — 包装产出量（Wednesday Cut-Off）\n• Packout vs ExF — Packout 与 Forecast 的差值 = Packout - ExF\nCTB 类型下此字段留空", "ETD"],
    ["Cut Day Of Week", "String", "业务截止日：\n• Saturday — ETD / ExF 卡周六\n• Wednesday — Packout 卡周三\nCTB 留空", "Saturday"],
    ["制程", "String", "生产制程/环节维度，用于筛选：\n• PKG — 包装（Output 取 线体=*PKG）\n• GB — 成品组（取 GB-PN 聚合）\n• FR — 镜框（Frame）\n• LT — 左镜腿（Left Temple）\n• RT — 右镜腿（Right Temple）\n数据来源：排产结果表的 线体编码 列 + 虚拟料号关系", "PKG"],
    ["Wk1 ~ Wk52+", "Integer", "周度数值，含义取决于 Version-Detail：\n• ETD/Packout → 该周累计排产量（Sum of daily OUTPUT）\n• ETD vs ExF / Packout vs ExF → 差值（可为负）\n• ExF → 原始 Forecast 量\n• CTB → CTB 周总量\n按 Cut-Off 日对齐后填入对应列", "120"],
]

for r, row in enumerate(fields, 3):
    for c, val in enumerate(row, 1):
        fill = light_fill if c == 1 else None
        sc(ws_old, r, c, val, font=normal_font, fill=fill,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 2: 取数逻辑明细
# ============================================================
ws2 = wb.create_sheet("取数逻辑明细")
ws2.column_dimensions['A'].width = 18
ws2.column_dimensions['B'].width = 18
ws2.column_dimensions['C'].width = 22
ws2.column_dimensions['D'].width = 45
ws2.column_dimensions['E'].width = 45
ws2.column_dimensions['F'].width = 30
ws2.column_dimensions['G'].width = 30

sc(ws2, 1, 1, "各 Version-Detail 取数逻辑与数据源映射", font=Font(name="微软雅黑", bold=True, size=14))
ws2.merge_cells('A1:G1')

set_header_row(ws2, 2, [
    "Version-Type", "Version-Detail", "数据源文件", "数据源Sheet/区域", "取数逻辑", "Cut-Off", "输出备注"
])

data_rows = [
    # ExF
    ["ExF", "(基线)", 
     "Copy of Lager FATP By SKU\nBuild Plan-20260713\ngated.xlsx",
     "FCST sheet\nRow 4+ 逐SKU\nCol E = SKU\nCol I~BN = 52周周度值\n(2026-04-04 ~ 2027-03-27, 均为周六)",
     "1. 按 SKU 读取每周值\n2. PN = SKU 列\n3. Style/Color 通过虚拟料号关系表或 BOM 反查\n4. 直接填入对应周列\n无需额外计算",
     "Saturday\n（原始日期已是周六）",
     "仅一份 ExF，不区分子版本"],
    
    # Ungated - ETD
    ["Ungated", "ETD",
     "Copy of Lager FATP By SKU\nBuild Plan-20260713\nungated.xlsx",
     "排产结果 sheet\nRow 3+ 每行一个(SKU+线体+班次+数据类型)\n• D列=数据类型\n• F列=SKU/线体编码\n• H列=现汇总量\n• I~列(46110~46474)=日级数据",
     "1. 过滤：数据类型=OUTPUT，线体含'PKG'\n2. 按 SKU 分组，各班次/线体的 OUTPUT 日值累加\n3. 日级按 Cut-Off 周聚合：\n   周六对齐：周一~周日映射到当周六\n4. 如配置 ETD offset（240/864批次），则调整日期偏移\n5. 周度输出",
     "Saturday",
     "Ungated ETD = unconstrained\nversion's PKG OUTPUT\naggregated to Saturday weeks"],
    
    # Ungated - ETD vs ExF
    ["Ungated", "ETD vs ExF",
     "（同 ETD）+ ExF",
     "—",
     "1. 取 Ungated ETD 周值\n2. 取同 SKU 同周的 ExF 值\n3. 差值 = ETD - ExF\n4. 结果为负数表示低于 Forecast",
     "Saturday",
     "对比值，可为负"],
    
    # Ungated - Packout
    ["Ungated", "Packout",
     "Copy of Lager FATP By SKU\nBuild Plan-20260713\nungated.xlsx",
     "同上（排产结果 sheet）",
     "1. 过滤：数据类型=OUTPUT，线体含'PKG'\n2. 按 SKU 分组累加\n3. 日级按周三 Cut-Off 周聚合：\n   周四~下周三映射到当周三\n4. 周度输出",
     "Wednesday",
     "Ungated Packout = 周三截止\n的 PKG OUTPUT Cum"],
    
    # Ungated - Packout vs ExF
    ["Ungated", "Packout vs ExF",
     "（同 Packout）+ ExF",
     "—",
     "1. 取 Ungated Packout 周值\n2. 取同 SKU 同周的 ExF 值\n3. 差值 = Packout - ExF",
     "Wednesday",
     "对比值，可为负"],
    
    # Gated - ETD
    ["Gated", "ETD",
     "Copy of Lager FATP By SKU\nBuild Plan-20260713\ngated.xlsx",
     "排产结果 sheet\n（结构同上）",
     "与 Ungated ETD 逻辑完全一致\n仅数据源换为 gated 版文件\n取 OUTPUT + PKG 线体\n按周六 Cut-Off 周聚合",
     "Saturday",
     "Gated ETD = constrained\nversion's PKG OUTPUT"],
    
    # Gated - ETD vs ExF
    ["Gated", "ETD vs ExF",
     "（同 Gated ETD）+ ExF",
     "—",
     "Gated ETD - ExF（同周同SKU）",
     "Saturday",
     "对比值"],
    
    # Gated - Packout
    ["Gated", "Packout",
     "Copy of Lager FATP By SKU\nBuild Plan-20260713\ngated.xlsx",
     "排产结果 sheet",
     "与 Ungated Packout 逻辑一致\n仅数据源换为 gated 版\n按周三 Cut-Off 周聚合",
     "Wednesday",
     "Gated Packout = constrained\nPKG OUTPUT"],
    
    # Gated - Packout vs ExF
    ["Gated", "Packout vs ExF",
     "（同 Gated Packout）+ ExF",
     "—",
     "Gated Packout - ExF（同周同SKU）",
     "Wednesday",
     "对比值"],
    
    # CTB
    ["CTB", "（总量）",
     "Modelo SKU CTB Publish\n0710 final.xlsx",
     "Modelo SKU CTB sheet\nRow 4+ 逐SKU\n• C=Style, D=Frame Color\n• G=SKU\n• J~列(2026-02-04起)=日级CTB值",
     "1. 读 SKU、Style、Color、Case PN\n2. 从日级CTB列取值\n3. 按周 Sum 聚合（周一定义周一~周日）\n4. 映射到输出周列\n5. Style/Color 直接从CTB表中取\n   （若为空则通过 虚拟料号关系 反查）",
     "（留空）",
     "CTB 仅一行总量，\n不区分 ETD/Packout"],
]

for r, row in enumerate(data_rows, 3):
    for c, val in enumerate(row, 1):
        fills = [violet_fill, None, green_fill, green_fill, None, yellow_fill, orange_fill]
        sc(ws2, r, c, val, font=normal_font, fill=fills[c-1] if c <= len(fills) else None,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 3: 数据源文件清单
# ============================================================
ws3 = wb.create_sheet("数据源文件清单")
ws3.column_dimensions['A'].width = 45
ws3.column_dimensions['B'].width = 15
ws3.column_dimensions['C'].width = 55
ws3.column_dimensions['D'].width = 30

sc(ws3, 1, 1, "数据源文件清单与结构", font=Font(name="微软雅黑", bold=True, size=14))
ws3.merge_cells('A1:D1')

set_header_row(ws3, 2, ["文件名", "用途", "关键表/字段", "备注"])

files = [
    ["Copy of Lager FATP By SKU Build Plan-20260713 gated.xlsx",
     "Gated 版排产结果 + Forecast",
     "• FCST sheet：周级Forecast\n  行=SKU，列=周（周六截止，52周）\n• 排产结果 sheet：日级排产\n  数据类型=OUTPUT/INPUT/CHECKIN等\n  线体=PKG/FAT等，SKU=SK-XXX/GB-XXX",
     "Forecast (ExF) 仅在此文件中有",
    ],
    ["Copy of Lager FATP By SKU Build Plan-20260713 ungated.xlsx",
     "Ungated 版排产结果",
     "• 排产结果 sheet：与 gated 结构相同\n  仅数据值不同（不受限）",
     "无 FCST sheet"],
    ["Ivy BOM 导入模板20260714.xlsx",
     "物料清单",
     "• BOM sheet：装配件→组件层级\n  装配件=SKU/GB-PN\n  组件=FR/LT/RT零件PN\n  关键列：装配件, 组件, 单机用量, 损耗率",
     "用于 SKU→GB→FR/LT/RT 的组成关系"],
    ["虚拟料号关系 20260623.xlsx",
     "SKU ↔ GB/FR/LT/RT 映射",
     "• Sheet1：\n  SKU, Style, CMF,\n  GB PN-旧, GB PN-新,\n  FR PN-旧, FR PN-新,\n  LT PN-旧, LT PN-新,\n  RT PN-旧, RT PN-新",
     "核心映射表，建立 SKU→各制程PN 关系"],
    ["Modelo SKU CTB Publish 0710 final.xlsx",
     "SKU 级 CTB 数据",
     "• Modelo SKU CTB sheet：日级CTB\n  Title=CTB, Usage=Spring,\n  Style, Frame Color, Lens,\n  SKU, Case PN,\n  日级列(2026-02-04起)",
     "CTB = Clear To Build\n物料就绪量"],
    ["Modelo GB CTB Publish 0710 final.xlsx",
     "GB 级 CTB 数据",
     "• Modelo GB CTB sheet：日级CTB\n  Title=CTB, Process, Component,\n  Style, Frame Color,\n  日级列(2026-02-02起)",
     "GB 级 CTB（备选）"],
]

for r, row in enumerate(files, 3):
    for c, val in enumerate(row, 1):
        sc(ws3, r, c, val, font=normal_font,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 4: 排产结果数据解析
# ============================================================
ws4 = wb.create_sheet("排产结果解析")
ws4.column_dimensions['A'].width = 16
ws4.column_dimensions['B'].width = 20
ws4.column_dimensions['C'].width = 14
ws4.column_dimensions['D'].width = 14
ws4.column_dimensions['E'].width = 30
ws4.column_dimensions['F'].width = 50
ws4.column_dimensions['G'].width = 20

sc(ws4, 1, 1, "排产结果 sheet 结构说明", font=Font(name="微软雅黑", bold=True, size=14))
ws4.merge_cells('A1:G1')

set_header_row(ws4, 2, ["列索引", "Excel列", "列名", "示例值", "说明", "取值规则", "备注"])

cols_info = [
    [0, "A", "（拼接键）", "AL1-PKGOUTPUT白班SK-1001879-01", "行标识：线体+数据类型+班次+SKU 拼接", "忽略，仅用于识别", ""],
    [1, "B", "（拼接键2）", "OUTPUTSK-1001879-01", "数据类型+SKU 拼接", "忽略", ""],
    [2, "C", "线体编码", "AL1-PKG", "产线标识：AL1=Assembly Line 1\nPKG=Packaging\nFAT=Final Assembly Test", "关键字段：\n线体含'PKG' → 包装产出\n线体含'FAT' → 组装产出", "PKG 用于 Packout/ETD"],
    [3, "D", "数据类型", "OUTPUT", "数据分类枚举：\n• OUTPUT — 产出量\n• INPUT — 投入量\n• CHECKIN / CHECKOUT\n• FRESH WIP / REPAIR WIP\n• Unconstrain Input\n• UnGated Fresh/Reflow Input", "关键字段：\n取数只取 OUTPUT 类型", "OUTPUT = 已完成产出"],
    [4, "E", "班次", "白班 / 夜班", "班次标识", "各班次值需 Sum 合并", "日总量 = 白班+夜班"],
    [5, "F", "SKU", "SK-1001879-01", "排产物料编码\n可能是 SK-XXX / GB-XXX / FR-XXX\n或空（汇总行）", "关键字段：\n关联到输出表 PN", "含汇总行（SKU/TTL）需过滤"],
    [6, "G", "是否排产", "Y / None", "是否参与排产标识", "过滤条件：='Y'", ""],
    [7, "H", "现汇总量", "58410.0", "该行总数量（非日级）", "备用，一般不用于周报表", "日级数据优先"],
    ["8~372", "I~", "日级日期列", "46110~46474", "365个日级列，每列一天\n46110 = 2026-03-29(周日)\n46474 = 2027-03-28(周日)", "核心数据：按周聚合时\n取对应日期范围的值\n空值按0处理", "日级→周聚合\n关键步骤"],
]

for r, row in enumerate(cols_info, 3):
    for c, val in enumerate(row, 1):
        fill = light_fill if c in [1, 5] else None
        sc(ws4, r, c, val, font=normal_font, fill=fill,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 5: 周聚合逻辑
# ============================================================
ws5 = wb.create_sheet("周聚合逻辑")
ws5.column_dimensions['A'].width = 22
ws5.column_dimensions['B'].width = 45
ws5.column_dimensions['C'].width = 14

sc(ws5, 1, 1, "Week Cut-Off 聚合规则", font=Font(name="微软雅黑", bold=True, size=14))
ws5.merge_cells('A1:C1')

set_header_row(ws5, 2, ["规则", "说明", "示例"])

week_rules = [
    ["业务周定义", "周一~周日为一个业务周", "2026-03-30(Mon) ~ 2026-04-05(Sun) = 同一周"],
    ["Saturday Cut-Off\n（ETD / ExF）",
     "取该周 周一~周日 的日数据求和\n标记为该周周六的数值\nExF 原始数据已是周级周六值，无需额外聚合",
     "周 2026-03-30~04-05 → 填到 Apr Wk1 (04-04 Sat)"],
    ["Wednesday Cut-Off\n（Packout）",
     "取 上周四~本周三 的日数据求和\n标记为该周周三的数值\n（业务约定：周三的 Packout 对比周六的 X-Factory）",
     "2026-04-02(Thu) ~ 2026-04-08(Wed) → 填到 Apr Wk1 (04-08 Wed)"],
    ["CTB 周聚合",
     "日级 CTB 按周一~周日 Sum\n填入对应周列（不区分 Cut-Off）",
     "2026-02-04 ~ 2026-02-10 求和 → 对应周列"],
    ["跨周数据处理",
     "排产结果无数据的日期视为 0\nMonday-Sunday 周对齐方式：\n以 ISO 周或自定义周为准",
     "需在配置中指定周定义方式"],
    ["ETD Offset 配置",
     "从 Auto→ETD 需应用 Offset：\n• 全局默认 offset（如 864 批次）\n• 料号级特例（如 240 批次）\nOffset 影响数据的日期归属周",
     "SK-1001887-01: offset=240\n其他: offset=864"],
]

for r, row in enumerate(week_rules, 3):
    for c, val in enumerate(row, 1):
        fill = yellow_fill if c == 1 else None
        sc(ws5, r, c, val, font=normal_font, fill=fill,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 6: CTB 数据处理
# ============================================================
ws6 = wb.create_sheet("CTB数据处理")
ws6.column_dimensions['A'].width = 20
ws6.column_dimensions['B'].width = 20
ws6.column_dimensions['C'].width = 45
ws6.column_dimensions['D'].width = 30

sc(ws6, 1, 1, "CTB 数据源与处理逻辑", font=Font(name="微软雅黑", bold=True, size=14))
ws6.merge_cells('A1:D1')

set_header_row(ws6, 2, ["步骤", "操作", "说明", "数据源/输出"])

ctb_steps = [
    ["1. 读取CTB表",
     "读 Modelo SKU CTB Publish\n  0710 final.xlsx",
     "Sheet = Modelo SKU CTB\nTitle=CTB, Usage=Spring", "数据源①"],
    ["2. 提取属性列",
     "取 Style, Frame Color, Lens,\nLens Color, SKU, Case PN",
     "C=Style, D=Frame Color,\nE=Lens, F=Lens Color,\nG=SKU, H=Case PN\nI=Case Description", "属性映射"],
    ["3. 提取日级CTB值",
     "定位 J~列起（2026-02-04始）\n的日级数值",
     "日期存储在 Row 3\n数值从 Row 4 起", "日CTB值"],
    ["4. 按周聚合",
     "将日级值按 周一~周日\nSum 聚合到业务周",
     "空值视为 0\n周定义与排产结果一致", "周CTB值"],
    ["5. SKU→Style/Color映射",
     "若 CTB 表本身有 Style/Color\n则直接用；否则通过\n虚拟料号关系表反查",
     "虚拟料号关系：\nSKU → Style, CMF(Color)", "参考数据源②"],
    ["6. 输出拼接",
     "作为一行追加到输出表\nPN=SKU, Version-Type=CTB\nVersion-Detail=空\nCut-Day=空",
     "CTB 不区分 ETD/Packout\n仅一个总量值", "输出表"],
    ["7. GB级CTB（可选）",
     "若需要 GB 维度 CTB，\n用 Modelo GB CTB Publish\n  0710 final.xlsx",
     "Sheet=Modelo GB CTB\n结构略有不同，有 Process 等列\n聚合方式同上", "数据源③"],
]

for r, row in enumerate(ctb_steps, 3):
    for c, val in enumerate(row, 1):
        fill = green_fill if c == 1 else None
        sc(ws6, r, c, val, font=normal_font, fill=fill,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 7: GB 维度聚合逻辑
# ============================================================
ws7 = wb.create_sheet("GB维度聚合")
ws7.column_dimensions['A'].width = 22
ws7.column_dimensions['B'].width = 45
ws7.column_dimensions['C'].width = 30

sc(ws7, 1, 1, "GB 维度聚合规则（Sample-GB）", font=Font(name="微软雅黑", bold=True, size=14))
ws7.merge_cells('A1:C1')

set_header_row(ws7, 2, ["步骤", "说明", "数据来源"])

gb_steps = [
    ["1. SKU→GB 映射",
     "通过 虚拟料号关系 或 BOM 表\n找到每个 SKU 所属的 GB PN\n一个 GB 可对应多个 SKU",
     "虚拟料号关系.xlsx\nGB PN-新 列",
    ],
    ["2. 按 GB 分组聚合",
     "将同 GB 下所有 SKU 的\n周度值（ETD/Packout/ExF）Sum\n获取该 GB 的 X-Factory 量",
     "排产结果表\n（按SKU聚合后→按GB再聚合）",
    ],
    ["3. GB 级 Cut-Off",
     "GB output 默认卡周二\n（从转录：周一~周二出产\n  满足周三 Packout）\n需可配置",
     "业务配置",
    ],
    ["4. GB 级输出格式",
     "与 Sample-PKG 结构一致\n但 PN = GB PN\nStyle/Color 为 GB 级属性\n分 Ungated/Gated/ExF/CTB",
     "输出表：Sample-GB",
    ],
]

for r, row in enumerate(gb_steps, 3):
    for c, val in enumerate(row, 1):
        fill = orange_fill if c == 1 else None
        sc(ws7, r, c, val, font=normal_font, fill=fill,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 8: ETD Offset 配置
# ============================================================
ws8 = wb.create_sheet("ETD Offset配置")
ws8.column_dimensions['A'].width = 22
ws8.column_dimensions['B'].width = 50
ws8.column_dimensions['C'].width = 40

sc(ws8, 1, 1, "ETD Offset 配置规则", font=Font(name="微软雅黑", bold=True, size=14))
ws8.merge_cells('A1:C1')

set_header_row(ws8, 2, ["配置项", "说明", "示例/默认值"])

etd_rows = [
    ["Offset 含义",
     "从 Auto(OTTO)→ETD 需偏移的天数/批次\n业务上有 864/240 两种批次类型\n\n864 = 常规批次（~36天）\n240 = 特殊批次（~10天）\n\nOffset 影响日级数据归属周",
     "",
    ],
    ["全局默认 Offset",
     "所有未在料号特例表中配置的 PN\n使用此默认值",
     "864",
    ],
    ["料号级 Offset 特例",
     "允许为特定 PN 指定不同 Offset\n需要单独维护配置表",
     "SK-1001887-01: 240\nSK-1001888-01: 864\n（标粗料号用240）",
    ],
    ["Offset 作用方式",
     "日级数据日期 + Offset 天 = ETD 日期\nETD 日期所属周 = 该产量归属周\n\n例：3/29 的产出 + 864 Offset\n     → ETD 日期 ≈ 3/29 + 864天\n     → 归属到对应周",
     "",
    ],
    ["配置表格式（建议）",
     "两列配置表：\nPN | Offset_Days\n（留空 PN 的行作为默认值）",
     "PN           | Offset\n----------------------\n*DEFAULT*    | 864\nSK-1001887-01 | 240\nSK-1001888-01 | 240",
    ],
]

for r, row in enumerate(etd_rows, 3):
    for c, val in enumerate(row, 1):
        fill = pink_fill if c == 1 else None
        sc(ws8, r, c, val, font=normal_font, fill=fill,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Save
# ============================================================
output_path = "/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/【界面报表】多版本计划拼接设计.xlsx"
wb.save(output_path)
print(f"Saved to {output_path}")
