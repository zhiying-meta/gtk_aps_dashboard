import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

wb = openpyxl.load_workbook('/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/【界面报表】多版本计划拼接设计.xlsx')

nf = Font(name="微软雅黑", size=10)
bf = Font(name="微软雅黑", bold=True, size=11)
sf = Font(name="Consolas", size=9)
hf = Font(name="微软雅黑", bold=True, size=12, color="FFFFFF")

hfill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
lfill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
yfill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
gfill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
pfill = PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")
vfill = PatternFill(start_color="E4DFEC", end_color="E4DFEC", fill_type="solid")
rfill = PatternFill(start_color="FCE4EC", end_color="FCE4EC", fill_type="solid")

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
# 1. Update 字段说明 - add formula info to Version-Detail
# ============================================================
ws1 = wb['字段说明']
# Row 8 = Version-Detail
sc(ws1, 8, 3,
   '指标细分枚举：\n'
   '• ETD — 预计发货量（Saturday Cut-Off）\n'
   '  公式：ROUNDDOWN(Cum_Output / Pallet_Qty, 0) * Pallet_Qty\n'
   '  含义：将累计产出向下取整到最近整托盘数\n'
   '• ETD vs ExF — ETD 与 Forecast 的差值 = ETD - ExF\n'
   '• Packout — 包装产出量（Wednesday Cut-Off）\n'
   '  公式：取 OUTPUT Cum 的周三值（无托盘取整）\n'
   '• Packout vs ExF — Packout 与 Forecast 的差值 = Packout - ExF\n'
   'CTB 类型下此字段留空',
   font=nf, align=Alignment(vertical='center', wrap_text=True))

# Row 12 = Wk1 ~ Wk52+
sc(ws1, 12, 3,
   '周度数值，含义取决于 Version-Detail：\n'
   '• ETD → Pallet_Rounded = ROUNDDOWN(Cum_Output / Pallet_Qty, 0) * Pallet_Qty\n'
   '• Packout → 该周三的 OUTPUT Cum 原值（无取整）\n'
   '• ETD vs ExF / Packout vs ExF → 差值（可为负）\n'
   '• ExF → 原始 Forecast 量\n'
   '• CTB → CTB 周总量\n'
   '按 Cut-Off 日对齐后填入对应列',
   font=nf, align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# 2. Update 取数逻辑明细 - ETD rows with formula details
# ============================================================
ws2 = wb['取数逻辑明细']
# Column widths
ws2.column_dimensions['H'] = 35

# Add header for new formula column at col H
sh(ws2, 2, [
    "Version-Type", "Version-Detail", "数据源文件", "数据源Sheet/区域",
    "取数逻辑", "Cut-Off", "输出备注", "公式/算法"
])

# Ungated ETD row - expand logic
sc(ws2, 4, 5,
   '1. 过滤：数据类型=OUTPUT，线体含\'PKG\'\n'
   '2. 按 SKU 分组，各班次/线体的 OUTPUT 日值累加\n'
   '3. 日级按 Cut-Off 周聚合：\n'
   '   周六对齐：周一~周日映射到当周六\n'
   '4. 计算 ETD = ROUNDDOWN(Cum_Output / Pallet_Qty, 0) * Pallet_Qty\n'
   '   • Pallet_Qty 优先取 SKU 级配置\n'
   '   • 无配置则取全局默认值（如 864）\n'
   '5. 周度输出',
   font=nf, align=Alignment(vertical='center', wrap_text=True))

sc(ws2, 4, 8,
   'ETD = ROUNDDOWN(ΣOUTPUT_daily / Pallet_Qty, 0) * Pallet_Qty\n\n'
   '例：Cum_Output=1000, Pallet_Qty=864\n'
   '   = ROUNDDOWN(1000/864,0)*864\n'
   '   = ROUNDDOWN(1.157,0)*864\n'
   '   = 1 * 864 = 864',
   font=sf, fill=rfill,
   align=Alignment(vertical='center', wrap_text=True))

# Gated ETD row
sc(ws2, 8, 5,
   '与 Ungated ETD 逻辑完全一致\n'
   '仅数据源换为 gated 版文件\n'
   '取 OUTPUT + PKG 线体\n'
   '按周六 Cut-Off 周聚合\n'
   '应用 Pallet_Qty 向下取整',
   font=nf, align=Alignment(vertical='center', wrap_text=True))

sc(ws2, 8, 8,
   'ETD = ROUNDDOWN(ΣOUTPUT_daily / Pallet_Qty, 0) * Pallet_Qty\n\n'
   'Pallet_Qty 配置示例：\n'
   '• 全局默认: 864\n'
   '• SK-1002701-01: 240',
   font=sf, fill=rfill,
   align=Alignment(vertical='center', wrap_text=True))

# Packout rows - add formula explanation
for row_idx in [5, 9]:  # Ungated Packout, Gated Packout
    sc(ws2, row_idx, 5,
       '1. 过滤：数据类型=OUTPUT，线体含\'PKG\'\n'
       '2. 按 SKU 分组，各班次/线体的 OUTPUT 日值累加\n'
       '3. 日级按周三 Cut-Off 周聚合：\n'
       '   周四~下周三映射到当周三\n'
       '4. Packout = OUTPUT Cum 的周三值\n'
       '   （直接取累积值，无托盘取整）',
       font=nf, align=Alignment(vertical='center', wrap_text=True))
    sc(ws2, row_idx, 8,
       'Packout = ΣOUTPUT_daily (Wed Cut-Off)\n\n'
       '与 ETD 的区别：\n'
       '• Packout 无托盘取整\n'
       '• Packout 是周三截止\n'
       '• ETD 是周六截止且托盘取整',
       font=sf, fill=rfill,
       align=Alignment(vertical='center', wrap_text=True))

# ETD vs ExF / Packout vs ExF - add formula
for row_idx in [6, 10]:  # vs ExF rows
    sc(ws2, row_idx, 8,
       '差值 = Version_Value - ExF\n\n'
       '• 负数：低于 Forecast\n'
       '• 正数：高于 Forecast\n'
       '• 同周同SKU比较',
       font=sf, fill=rfill,
       align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# 3. Update ETD Offset配置 -> rename & expand to "托盘&Offset配置"
# ============================================================
ws_old = wb['ETD Offset配置']
ws_old.title = '托盘与Offset配置'

# Expand content
sc(ws_old, 1, 1, "托盘数量（Pallet Qty）与 ETD Offset 配置规则", font=Font(name="微软雅黑", bold=True, size=14))
ws_old.merge_cells('A1:D1')

sh(ws_old, 2, ["配置项", "说明", "示例/默认值", "数据来源"])

configs = [
    ["全局默认托盘数量\n(Global Pallet Qty)",
     "将累计产出向下取整到\n最接近的整托盘数\n公式：ROUNDDOWN(Cum/864,0)*864\n\n所有未在特例表中配置的 SKU\n使用此默认值",
     "864",
     "业务约定\n（ETD example PKG sheet 中\n49/53 个 SKU 使用 864）",
    ],
    ["SKU 级托盘数量特例\n(SKU Pallet Qty Override)",
     "允许为特定 SKU 指定不同的\n托盘数量\n\n配置表格式：\nPN\t| Pallet_Qty\n---+----------\n*DEFAULT* | 864\nSK-1002701-01 | 240",
     "SK-1002701-01: 240\n（GB-Bold-Clear 料号）\n\nETD example PKG sheet 中\n4/53 个 SKU 使用 240",
     "ETD example.xlsx\nPKG sheet R1875\n（ROUNDDOWN/240 公式）",
    ],
    ["托盘取整计算公式",
     "ETD = ROUNDDOWN(Cum_Output / Pallet_Qty, 0) * Pallet_Qty\n\n"
     "参数说明：\n"
     "• Cum_Output = 该SKU的累计包装产出\n"
     "  （按Saturday Cut-Off聚合的周度值）\n"
     "• Pallet_Qty = 托盘数量（SKU级或全局）\n"
     "• ROUNDDOWN(., 0) = 向下取整到整数倍\n\n"
     "例：Cum=1500, Pallet=864\n"
     "  ROUNDDOWN(1500/864, 0)*864\n"
     "  = ROUNDDOWN(1.736, 0)*864\n"
     "  = 1 * 864 = 864\n\n"
     "含义：只有凑满整托盘的量才算ETD",
     "ROUNDDOWN(N1794/864,0)*864\n（PKG sheet R1848 公式）",
     "ETD example.xlsx\nPKG sheet",
    ],
    ["ETD vs Packout 区别",
     "• ETD = 托盘取整 + 周六截止\n"
     "• Packout = 无取整 + 周三截止\n\n"
     "两者数据源相同（OUTPUT Cum），\n"
     "但 Cut-Off 日和取整规则不同",
     "PKG sheet 结构：\n  Cum (raw) → ETD (rounded)\n  OUTPUT Cum R1794~1846\n  ETD R1848~1900",
     "",
    ],
    ["ETD Offset\n（日期偏移）",
     "从原始数据到 ETD 的日期偏移\n用于将 Auto 数据对齐到 ETD\n（天为单位）\n\n配置方式：\n• 全局默认 offset\n• 料号级特例",
     "全局默认: 864 批次\n特例: 240 批次",
     "转录中提到\n「标粗的料号用240\n不标粗的用864」",
    ],
    ["Toggle 机制\n（原始值/取整切换）",
     "PKG sheet R1901 提供切换行\n当对应列 = \"N\" 时，ETD 显示\n原始 Cum 值（非取整）\n当列为空时，显示 Pallet_Rounded 值\n\n公式：\n=IF(P$1901=\"N\", Cum, ROUNDDOWN(Cum/864,0)*864)",
     "R1901: col R=\"N\", col S=\"N\"\n表示周六起显示原始 Cum",
     "ETD example.xlsx\nPKG sheet R1901",
    ],
]

for r, row in enumerate(configs, 3):
    for c, val in enumerate(row, 1):
        fill = [pfill, None, yfill, gfill][c-1] if c <= 4 else None
        sc(ws_old, r, c, val, font=nf, fill=fill,
           align=Alignment(vertical='center', wrap_text=True))


# ============================================================
# 4. Update 数据源文件清单 - add ETD example
# ============================================================
ws3 = wb['数据源文件清单']

# Add ETD example file entry at row 9
sc(ws3, 9, 1, "ETD example.xlsx",
   font=nf, align=Alignment(vertical='center', wrap_text=True))
sc(ws3, 9, 2, "ETD 示例表（含公式参考）",
   font=nf, align=Alignment(vertical='center', wrap_text=True))
sc(ws3, 9, 3,
   "• PKG sheet：\n"
   "  Row 6: 日列日期序列（46109起）\n"
   "  Row 7: 日列星期标识\n"
   "  Row 8+: HLOOKUP从排产结果取数\n"
   "  Rows 1794~1846: OUTPUT Cum（累计）\n"
   "  Rows 1847~1900: ETD（含托盘取整）\n"
   "    864 为默认 Pallet_Qty\n"
   "    240 为 SK-1002701-01 特例\n"
   "  Row 1901: Toggle（\"N\"=原始值）\n\n"
   "• GB sheet：类似结构\n\n"
   "核心公式：\n"
   "=IF(P$1901=\"N\", O1848,\n"
   "   ROUNDDOWN(N1794/864,0)*864)",
   font=sf, align=Alignment(vertical='center', wrap_text=True))

ws3.merge_cells('C9:D9')

for c in range(1, 5):
    ws3.cell(row=9, column=c).border = tb


# ============================================================
# Save
# ============================================================
output_path = "/Users/zhiyingchen/openhands_workspace/Projects/gtk-result-table/【界面报表】多版本计划拼接设计.xlsx"
wb.save(output_path)
print(f"Saved to {output_path}")
