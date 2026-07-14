import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

wb = openpyxl.Workbook()

nf = Font(name="微软雅黑", size=10)
bf = Font(name="微软雅黑", bold=True, size=11)
sf = Font(name="Consolas", size=9)
tf = Font(name="微软雅黑", bold=True, size=14)
hf = Font(name="微软雅黑", bold=True, size=12, color="FFFFFF")

hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
lfill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
yfill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
gfill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
pfill = PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")
vfill = PatternFill(start_color="E4DFEC", end_color="E4DFEC", fill_type="solid")
rfill = PatternFill(start_color="FCE4EC", end_color="FCE4EC", fill_type="solid")
ofill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

tb = Border(left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin'))

def sc(ws, r, c, val, font=nf, fill=None, align=None):
    cell = ws.cell(row=r, column=c, value=val)
    cell.font = font
    cell.border = tb
    if fill: cell.fill = fill
    cell.alignment = align or Alignment(vertical='center', wrap_text=True)
    return cell

def sh(ws, row, vals, fill=hfill, font=hf):
    for i, v in enumerate(vals, 1):
        sc(ws, row, i, v, font=font, fill=fill,
           align=Alignment(horizontal='center', vertical='center', wrap_text=True))

# ============================================================
# Sheet 1: 字段说明
# ============================================================
ws1 = wb.active
ws1.title = "字段说明"
ws1.column_dimensions['A'].width = 16
ws1.column_dimensions['B'].width = 18
ws1.column_dimensions['C'].width = 60
ws1.column_dimensions['D'].width = 45

sc(ws1, 1, 1, "字段说明（含取数逻辑）", font=tf)
sc(ws1, 2, 1, "字段", font=hf, fill=hfill, align=Alignment(horizontal='center', vertical='center', wrap_text=True))
sc(ws1, 2, 2, "类型", font=hf, fill=hfill, align=Alignment(horizontal='center', vertical='center', wrap_text=True))
sc(ws1, 2, 3, "说明", font=hf, fill=hfill, align=Alignment(horizontal='center', vertical='center', wrap_text=True))
sc(ws1, 2, 4, "示例", font=hf, fill=hfill, align=Alignment(horizontal='center', vertical='center', wrap_text=True))

fields = [
    ["PN", "String",
     "物料编码 / Part Number\n"
     "SKU级：SK-XXXXXXXX-XX\n"
     "GB级：GB-XXX-XXX",
     "SK-1001879-01"],
    ["Usage", "String",
     "用途/季节标识\n"
     "来源：排产结果表/BOM/CTB 的 Usage/Title 列\n"
     "值如：MP / Spring / Fall / Dummy / Demo",
     "Spring"],
    ["Style", "String",
     "眼镜款式描述\n"
     "来源：排产结果/CTB/虚拟料号关系的 Style 列\n"
     "值如：Rectangle M / Rectangle L / Bold / Slim Oval",
     "Rectangle M"],
    ["Color", "String",
     "颜色/Frame Color\n"
     "来源：排产结果/CTB/虚拟料号关系的 CMF/Frame Color 列\n"
     "值如：BLACK / CLASSIC HAVANA / LINEN / MERLOT",
     "BLACK"],
    ["Version-Type", "String",
     "版本类型枚举：\n"
     "• ExF — Forecast 基线\n"
     "  - SKU级：来自 gated.xlsx 的 FCST sheet（周级，周六Cut-Off）\n"
     "  - GB级：通过BOM表识别GB下所有SKU，汇总SKU的ExF\n"
     "• Ungated — 无限制排产版本（来自 ungated 排产结果表）\n"
     "• Gated — 受限排产版本（来自 gated 排产结果表）\n"
     "• CTB — 物料就绪数据（来自 Modelo SKU/GB CTB Publish）\n"
     "输出顺序：ExF → Ungated → Gated → CTB",
     "Ungated"],
    ["Version-Detail", "String",
     "指标细分枚举：\n"
     "• ETD — 预计发货量（Saturday Cut-Off）\n"
     "  公式：ROUNDDOWN(Cum_Output / Pallet_Qty, 0) * Pallet_Qty\n"
     "  含义：累计产出向下取整到最近整托盘数\n"
     "• ETD vs ExF — ETD 与 Forecast 的差值 = ETD - ExF\n"
     "• Packout — 包装产出量（Wednesday Cut-Off）\n"
     "  公式：取 OUTPUT Cum 的周三值（无托盘取整）\n"
     "• Packout vs ExF — Packout 与 Forecast 的差值 = Packout - ExF\n"
     "CTB 类型下此字段留空",
     "ETD"],
    ["Cut Day Of Week", "String",
     "业务截止日：\n"
     "• Saturday — ETD / ExF 卡周六\n"
     "• Wednesday — Packout 卡周三\n"
     "CTB 留空",
     "Saturday"],
    ["制程", "String",
     "生产制程/环节维度，用于筛选：\n"
     "• PKG — 包装（Output 取 线体=*PKG）\n"
     "• GB — 成品组（取 GB-PN 聚合）\n"
     "• FR — 镜框（Frame）\n"
     "• LT — 左镜腿（Left Temple）\n"
     "• RT — 右镜腿（Right Temple）\n"
     "数据来源：排产结果表的 线体编码 列 + 虚拟料号关系",
     "PKG"],
    ["Wk1 ~ Wk52+", "Integer",
     "周度数值，含义取决于 Version-Detail：\n"
     "• ETD → Pallet_Rounded = ROUNDDOWN(Cum_Output/Pallet_Qty, 0)*Pallet_Qty\n"
     "• Packout → 该周三的 OUTPUT Cum 原值（无取整）\n"
     "• ETD vs ExF / Packout vs ExF → 差值（可为负）\n"
     "• ExF → 原始 Forecast 量\n"
     "• CTB → CTB 周总量\n"
     "按 Cut-Off 日对齐后填入对应列",
     "120"],
]

for r, row in enumerate(fields, 3):
    for c, val in enumerate(row, 1):
        fill = lfill if c == 1 else None
        sc(ws1, r, c, val, font=nf, fill=fill, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 2: Sample-PKG
# ============================================================
ws2 = wb.create_sheet("Sample-PKG")
ws2.column_dimensions['A'].width = 18
ws2.column_dimensions['B'].width = 14
ws2.column_dimensions['C'].width = 14
ws2.column_dimensions['D'].width = 14
ws2.column_dimensions['E'].width = 14
ws2.column_dimensions['F'].width = 18
ws2.column_dimensions['G'].width = 16
ws2.column_dimensions['H'].width = 14
ws2.column_dimensions['I'].width = 14
ws2.column_dimensions['J'].width = 14

sh(ws2, 1, ["PN", "Usage", "Style", "Color", "Version-Type", "Version-Detail", "Cut Day Of Week", "Jul Wk1", "Jul Wk2", "..."])
data = [
    ["SK-123", "MP", "Rec M", "Black", "ExF", "", "Saturday", 120, 130, "..."],
    ["", "", "", "", "Ungated", "ETD", "Saturday", 100, 110, "..."],
    ["", "", "", "", "Ungated", "ETD vs ExF", "Saturday", -20, -20, "..."],
    ["", "", "", "", "Ungated", "Packout", "Wednesday", 95, 108, "..."],
    ["", "", "", "", "Ungated", "Packout vs ExF", "Wednesday", -25, -22, "..."],
    ["", "", "", "", "Gated", "ETD", "Saturday", 80, 90, "..."],
    ["", "", "", "", "Gated", "ETD vs ExF", "Saturday", -40, -40, "..."],
    ["", "", "", "", "Gated", "Packout", "Wednesday", 78, 85, "..."],
    ["", "", "", "", "Gated", "Packout vs ExF", "Wednesday", -42, -45, "..."],
    ["", "", "", "", "CTB", "", "", 200, 190, "..."],
]
for r, row in enumerate(data, 2):
    for c, val in enumerate(row, 1):
        sc(ws2, r, c, val, font=nf, align=Alignment(horizontal='center', vertical='center', wrap_text=True))


# ============================================================
# Sheet 3: Sample-GB
# ============================================================
ws3 = wb.create_sheet("Sample-GB")
for col, w in enumerate([18, 14, 14, 14, 14, 18, 16, 14, 14, 14], 1):
    ws3.column_dimensions[chr(64+col)].width = w

sh(ws3, 1, ["PN", "Usage", "Style", "Color", "Version-Type", "Version-Detail", "Cut Day Of Week", "Jul Wk1", "Jul Wk2", "..."])
data_gb = [
    ["GB-Rec M-Black", "MP", "Rec M", "Black", "ExF", "", "Saturday", 350, 380, "..."],
    ["", "", "", "", "Ungated", "ETD", "Saturday", 864, 864, "..."],
    ["", "", "", "", "Ungated", "ETD vs ExF", "Saturday", -250, -230, "..."],
    ["", "", "", "", "Ungated", "Packout", "Wednesday", 300, 320, "..."],
    ["", "", "", "", "Ungated", "Packout vs ExF", "Wednesday", -50, -60, "..."],
    ["", "", "", "", "Gated", "ETD", "Saturday", 864, 864, "..."],
    ["", "", "", "", "Gated", "ETD vs ExF", "Saturday", -300, -280, "..."],
    ["", "", "", "", "Gated", "Packout", "Wednesday", 280, 290, "..."],
    ["", "", "", "", "Gated", "Packout vs ExF", "Wednesday", -70, -90, "..."],
    ["", "", "", "", "CTB", "", "", 500, 480, "..."],
]
for r, row in enumerate(data_gb, 2):
    for c, val in enumerate(row, 1):
        sc(ws3, r, c, val, font=nf, align=Alignment(horizontal='center', vertical='center', wrap_text=True))


# ============================================================
# Sheet 4: 取数逻辑明细
# ============================================================
ws4 = wb.create_sheet("取数逻辑明细")
for col, w in zip(['A','B','C','D','E','F','G','H'], [18, 18, 24, 38, 45, 12, 16, 40]):
    ws4.column_dimensions[col].width = w

sc(ws4, 1, 1, "各 Version-Detail 取数逻辑与数据源映射", font=tf)
ws4.merge_cells('A1:H1')

sh(ws4, 2, ["Version-Type", "Version-Detail", "数据源文件", "数据源区域", "取数逻辑", "Cut-Off", "输出备注", "公式/算法"])

rows = [
    ["ExF", "(基线)",
     "gated.xlsx\nFCST sheet",
     "Row 4+ 逐SKU\nCol E=SKU\nCol I~BN=52周周六值",
     "【SKU级】直接按 SKU 读取每周值\n【GB级】通过BOM映射后汇总",
     "Saturday", "仅一份 ExF",
     "ExF (SKU) = FCST value\nExF (GB) = ΣExF of all SKUs\n  under same GB"],
    ["Ungated", "ETD",
     "ungated.xlsx\n排产结果 sheet",
     "Row 3+ 每日\nD=数据类型\nF=SKU\nI~=日级数据(365天)",
     "1. 过滤: dtype=OUTPUT, 线体含PKG\n2. 按SKU日级Sum→周聚合\n3. ROUNDDOWN(Cum/Pallet,0)*Pallet",
     "Saturday", "Ungated ETD",
     "=ROUNDDOWN(Cum/Pallet_Qty,0)*Pallet_Qty\nCum=ΣOUTPUT_daily(周六截止)"],
    ["Ungated", "ETD vs ExF",
     "同上 + ExF",
     "—",
     "Ungated ETD - 同SKU同周ExF",
     "Saturday", "差值可为负",
     "= ETD - ExF"],
    ["Ungated", "Packout",
     "ungated.xlsx\n排产结果 sheet",
     "同上",
     "1. 同ETD的过滤\n2. 日级按周三Cut-Off周聚合\n3. 直接取Cum值（无取整）",
     "Wednesday", "Ungated Packout",
     "= ΣOUTPUT_daily(周三截止)\n无托盘取整"],
    ["Ungated", "Packout vs ExF",
     "同上 + ExF",
     "—",
     "Ungated Packout - 同SKU同周ExF",
     "Wednesday", "差值可为负",
     "= Packout - ExF"],
    ["Gated", "ETD",
     "gated.xlsx\n排产结果 sheet",
     "同上",
     "同Ungated ETD逻辑，仅数据源换gated",
     "Saturday", "Gated ETD",
     "=ROUNDDOWN(Cum/Pallet_Qty,0)*Pallet_Qty"],
    ["Gated", "ETD vs ExF",
     "同上 + ExF",
     "—",
     "Gated ETD - ExF",
     "Saturday", "",
     "= Gated ETD - ExF"],
    ["Gated", "Packout",
     "gated.xlsx\n排产结果 sheet",
     "同上",
     "同Ungated Packout逻辑，仅数据源换gated",
     "Wednesday", "",
     "= ΣOUTPUT_daily(周三截止)"],
    ["Gated", "Packout vs ExF",
     "同上 + ExF",
     "—",
     "Gated Packout - ExF",
     "Wednesday", "",
     "= Gated Packout - ExF"],
    ["CTB", "（总量）",
     "Modelo SKU CTB\nPublish 0710 final.xlsx",
     "Modelo SKU CTB sheet\nRow 4+\nC=Style, D=Frame Color\nG=SKU, J~=日级CTB",
     "1. 读属性 + 日级CTB值\n2. 按周Sum聚合\n3. 输出为一行",
     "（留空）", "CTB仅总量",
     "CTB_weekly = ΣCTB_daily\n（周一~周日Sum）"],
]

for r, row in enumerate(rows, 3):
    fills = [vfill, None, gfill, gfill, None, yfill, ofill, rfill]
    for c, val in enumerate(row, 1):
        sc(ws4, r, c, val, font=nf, fill=fills[c-1],
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 5: 数据源文件清单
# ============================================================
ws5 = wb.create_sheet("数据源文件清单")
for col, w in zip(['A','B','C','D'], [48, 18, 60, 30]):
    ws5.column_dimensions[col].width = w

sc(ws5, 1, 1, "数据源文件清单与结构", font=tf)
ws5.merge_cells('A1:D1')
sh(ws5, 2, ["文件名", "用途", "关键表/字段", "备注"])

files = [
    ["Copy of Lager FATP By SKU Build Plan-20260713 gated.xlsx",
     "Gated版排产 + Forecast", "• FCST sheet: 周级Forecast, SKU行, 52周周六列\n• 排产结果 sheet: 日级排产, 365天",
     "ExF仅在此文件中有"],
    ["Copy of Lager FATP By SKU Build Plan-20260713 ungated.xlsx",
     "Ungated版排产", "• 排产结果 sheet: 与gated同结构",
     "无FCST sheet"],
    ["Ivy BOM 导入模板20260714.xlsx",
     "物料清单", "• BOM sheet: 装配件→组件\n  用于SKU→GB映射",
     "GB ExF汇总用"],
    ["虚拟料号关系 20260623.xlsx",
     "SKU↔GB/FR/LT/RT映射", "• Sheet1: SKU, Style, CMF, GB/FR/LT/RT PN新旧对照",
     "核心映射表"],
    ["Modelo SKU CTB Publish 0710 final.xlsx",
     "SKU级CTB", "• Modelo SKU CTB sheet: 日级CTB",
     "CTB数据源"],
    ["Modelo GB CTB Publish 0710 final.xlsx",
     "GB级CTB", "• Modelo GB CTB sheet: GB级日级CTB",
     "备选CTB数据源"],
    ["ETD example.xlsx",
     "ETD公式示例", "• PKG sheet: 日列(HLOOKUP取数)→Cum→ETD(托盘取整)\n  864默认Pallet, SK-1002701-01用240\n• GB sheet: 类似结构",
     "关键公式参考\n含Toggle机制"],
]

for r, row in enumerate(files, 3):
    for c, val in enumerate(row, 1):
        sc(ws5, r, c, val, font=nf, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 6: 排产结果解析
# ============================================================
ws6 = wb.create_sheet("排产结果解析")
for col, w in zip(['A','B','C','D','E','F','G'], [10, 10, 18, 14, 20, 55, 25]):
    ws6.column_dimensions[col].width = w

sc(ws6, 1, 1, "排产结果 sheet 结构说明", font=tf)
ws6.merge_cells('A1:G1')
sh(ws6, 2, ["列索引", "Excel列", "列名", "示例值", "说明", "取值规则", "ETD example对照"])

cols = [
    [0, "A", "（拼接键）", "AL1-PKGOUTPUT白班SK-1001879-01", "行标识", "忽略", "PKG sheet A列公式"],
    [1, "B", "（拼接键2）", "OUTPUTSK-1001879-01", "数据类型+SKU", "忽略", ""],
    [2, "C", "线体编码", "AL1-PKG", "产线标识(PKG/FAT/GB等)", "过滤: 含PKG=包装产出", "PKG sheet H列"],
    [3, "D", "数据类型", "OUTPUT", "OUTPUT/INPUT/CHECKIN等", "取数只取OUTPUT", "PKG sheet J列"],
    [4, "E", "班次", "白班/夜班", "班次", "各班次Sum合并", "PKG sheet I列"],
    [5, "F", "SKU", "SK-1001879-01", "物料编码(SK-/GB-/FR-等)", "关联输出表PN", "PKG sheet K列"],
    [6, "G", "是否排产", "Y/None", "排产标识", "过滤: =Y", ""],
    [7, "H", "现汇总量", "58410", "行总数量", "备用", ""],
    ["8~372", "I~(365d)", "日级日期", "46110~46474", "365天(2026-03-29~2027-03-28)", "核心数据: 按周聚合", "PKG sheet L~列"],
]

for r, row in enumerate(cols, 3):
    for c, val in enumerate(row, 1):
        fill = lfill if c in [1, 5] else None
        sc(ws6, r, c, val, font=nf, fill=fill, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 7: 周聚合逻辑
# ============================================================
ws7 = wb.create_sheet("周聚合逻辑")
ws7.column_dimensions['A'].width = 22
ws7.column_dimensions['B'].width = 55
ws7.column_dimensions['C'].width = 35

sc(ws7, 1, 1, "Week Cut-Off 聚合规则", font=tf)
ws7.merge_cells('A1:C1')
sh(ws7, 2, ["规则", "说明", "示例"])

rules = [
    ["业务周定义", "周一~周日为一个业务周\nETD example 日列：Sun(46110)~Sat", "2026-03-30(Mon)~2026-04-05(Sun)"],
    ["Saturday Cut-Off\n(ETD/ExF)", "取周一~周日的日数据Sum\n标记为该周周六\nExF原始已是周级周六值",
     "3/30~4/05 → Apr Wk1\n(4/04 Sat)"],
    ["Wednesday Cut-Off\n(Packout)", "取上周四~本周三的日数据Sum\n标记为该周周三",
     "4/02(Thu)~4/08(Wed)\n→ Apr Wk1 (4/08 Wed)"],
    ["ETD托盘取整公式", "ETD = ROUNDDOWN(Cum/Pallet,0)*Pallet\nCum = 周六截止的周Sum\nPallet = 配置值(864/240)",
     "Cum=1500, Pallet=864\n→ ROUNDDOWN(1500/864,0)*864\n= ROUNDDOWN(1.736,0)*864\n= 864"],
    ["Toggle机制", "R1901 = \"N\" → 显示原始Cum\nR1901 = 空 → 显示Pallet取整",
     "ETD example PKG sheet\nR1901: Col R=\"N\" (Sat起显示原始值)"],
    ["跨周数据处理", "无数据日期视为0", ""],
]

for r, row in enumerate(rules, 3):
    for c, val in enumerate(row, 1):
        fill = yfill if c == 1 else None
        sc(ws7, r, c, val, font=nf, fill=fill, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 8: CTB数据处理
# ============================================================
ws8 = wb.create_sheet("CTB数据处理")
for col, w in zip(['A','B','C','D'], [20, 20, 50, 30]):
    ws8.column_dimensions[col].width = w

sc(ws8, 1, 1, "CTB 数据源与处理逻辑", font=tf)
ws8.merge_cells('A1:D1')
sh(ws8, 2, ["步骤", "操作", "说明", "数据源/输出"])

ctb = [
    ["1.读取CTB表", "读 Modelo SKU CTB Publish", "Sheet=Modelo SKU CTB\nTitle=CTB, Usage=Spring", "数据源①"],
    ["2.提取属性", "Style, Frame Color, SKU等", "C=Style, D=Frame Color, G=SKU", "属性映射"],
    ["3.提取日级CTB", "J~列(2026-02-04起)日级值", "日期在Row3, 数值从Row4起", "日CTB值"],
    ["4.按周聚合", "周一~周日 Sum", "空值=0", "周CTB值"],
    ["5.Style/Color映射", "CTB表有则直接用\n否则通过虚拟料号关系反查", "", "参考"],
    ["6.输出拼接", "追加为CTB行\nVersion-Detail=空, Cut-Day=空", "CTB不分ETD/Packout", "输出表"],
    ["7.GB级CTB(可选)", "用 Modelo GB CTB Publish", "结构略有不同", "备选"],
]

for r, row in enumerate(ctb, 3):
    for c, val in enumerate(row, 1):
        fill = gfill if c == 1 else None
        sc(ws8, r, c, val, font=nf, fill=fill, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 9: GB维度聚合
# ============================================================
ws9 = wb.create_sheet("GB维度聚合")
ws9.column_dimensions['A'].width = 22
ws9.column_dimensions['B'].width = 55
ws9.column_dimensions['C'].width = 35

sc(ws9, 1, 1, "GB 维度聚合规则", font=tf)
ws9.merge_cells('A1:C1')
sh(ws9, 2, ["步骤", "说明", "数据来源"])

gb = [
    ["1. SKU→GB映射",
     "方法A: BOM表 装配件=SKU, 组件=GB-开头\n方法B: 虚拟料号关系 GB PN-新列",
     "Ivy BOM / 虚拟料号关系"],
    ["2. ExF GB级",
     "FCST只有SKU级!\n→ 先读各SKU ExF\n→ 按GB分组Sum",
     "gated.xlsx FCST sheet"],
    ["3. 排产结果 GB级",
     "排产结果自带GB-XXX行\n直接过滤dtype=OUTPUT线体=PKG即可\n无需额外汇总SKU",
     "排产结果 sheet"],
    ["4. CTB GB级",
     "直接用 Modelo GB CTB Publish\n或汇总SKU级CTB",
     "Modelo GB CTB / SKU CTB"],
    ["5. GB Cut-Off",
     "默认卡周二（可配置）",
     "业务配置"],
]

for r, row in enumerate(gb, 3):
    for c, val in enumerate(row, 1):
        fill = ofill if c == 1 else None
        sc(ws9, r, c, val, font=nf, fill=fill, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Sheet 10: 托盘与Offset配置
# ============================================================
ws10 = wb.create_sheet("托盘与Offset配置")
for col, w in zip(['A','B','C','D'], [22, 55, 35, 30]):
    ws10.column_dimensions[col].width = w

sc(ws10, 1, 1, "托盘数量(Pallet Qty)与ETD Offset配置规则", font=tf)
ws10.merge_cells('A1:D1')
sh(ws10, 2, ["配置项", "说明", "示例/默认值", "数据来源"])

cfg = [
    ["全局默认托盘数量",
     "将累计产出向下取整到最近整托盘\n"
     "公式：ROUNDDOWN(Cum/864,0)*864\n\n"
     "所有未在特例表中配置的SKU使用此默认值",
     "864",
     "ETD example PKG sheet\n49/53 SKU使用864"],
    ["SKU级托盘数量特例",
     "允许为特定SKU指定不同Pallet Qty\n\n"
     "配置表格式：\nPN | Pallet_Qty\n--------+-------\n*DEFAULT* | 864\nSK-1002701-01 | 240",
     "SK-1002701-01: 240",
     "ETD example PKG sheet R1875\nROUNDDOWN(…/240,…)公式"],
    ["托盘取整公式",
     "ETD = ROUNDDOWN(Cum_Output / Pallet_Qty, 0) * Pallet_Qty\n\n"
     "例: Cum=1500, Pallet=864\n"
     "→ ROUNDDOWN(1500/864,0)*864\n"
     "= ROUNDDOWN(1.736,0)*864 = 864\n\n"
     "只有凑满整托盘才算ETD",
     "ROUNDDOWN(N1794/864,0)*864",
     "ETD example PKG sheet\nR1848 Col16 公式"],
    ["ETD vs Packout区别",
     "• ETD: 托盘取整 + 周六截止\n• Packout: 无取整 + 周三截止\n\n"
     "数据源相同(OUTPUT Cum)\nCut-Off日和取整规则不同",
     "PKG sheet:\n  Cum R1794~1846\n  ETD R1848~1900",
     ""],
    ["ETD Offset(日期偏移)",
     "Auto数据→ETD的日期偏移(天)\n"
     "• 全局默认offset\n• 料号级特例",
     "默认864批次\n特例240批次",
     "转录:标粗用240\n其他用864"],
    ["Toggle机制",
     "R1901提供切换:\n对应列=\"N\" → 原始Cum\n列为空 → Pallet取整\n\n"
     "=IF(P$1901=\"N\", Cum,\n"
     "   ROUNDDOWN(Cum/864,0)*864)",
     "R1901: R~T=\"N\"\n(周六起显原始值)",
     "ETD example PKG sheet\nR1901"],
]

for r, row in enumerate(cfg, 3):
    for c, val in enumerate(row, 1):
        fill = [pfill, None, yfill, gfill][c-1]
        sc(ws10, r, c, val, font=nf, fill=fill, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# Save
# ============================================================
output_path = "/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/【界面报表】多版本计划拼接设计.xlsx"
wb.save(output_path)
print(f"Saved: {output_path}")
print("Sheets:", wb.sheetnames)
