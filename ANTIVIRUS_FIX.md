# 杀毒软件 / 企业安全软件误报解决 (App被ban)

PyInstaller 打包的 exe/app 常被误报为病毒，尤其是：
- One-file 单文件 + UPX 压缩
- 未签名
- 会监听端口 (Flask开 8502)

## 为什么被ban

- PyInstaller 的 bootloader 特征被很多病毒也使用，杀毒软件启发式检测误报
- UPX 压缩是常见加壳手段，极易触发
- 监听本地端口被视为可疑行为

## 解决方案（按推荐顺序）

### 方案1: 使用非PyInstaller分发（0误报）✅ 推荐

运行：
```bash
python make_portable.py
```

会生成 `dist_portable/`：

- `windows/` : Windows便携版，无exe，只有.py文件和START.bat
  - 同事双击 `START.bat` 即可，有Python就直接跑，没有会提示
  - 可选：下载 Python embeddable 包放到 `python_embed/` 做到完全离线，无需系统Python
  - **不会被杀毒软件拦截**，因为不是exe，只是Python脚本

- `macos_linux/` : macOS/Linux便携版，`./START.sh` 自动创建venv

- `ProductionPlanReview.pyz` : 单文件zipapp，`python3 ProductionPlanReview.pyz` 运行

**这是最安全的分发方式，企业环境推荐。**

### 方案2: 安全构建的PyInstaller版（低误报）

已更新构建脚本，默认 **禁用UPX**：

```bash
# 安全版（禁用UPX，one-folder模式，误报率最低）
python build_safe.py

# 或者
python build.py   # 已改为 --noupx
```

- **永远用 one-folder 模式** (`dist/ProductionPlanReview/` 文件夹)，不要用 one-file 单文件
  - One-folder 误报率远低于 one-file
- 不要用 `--onefile`，除非必要

### 方案3: 加白名单（临时解决）

**Windows Defender / 安全中心：**
1. Windows安全中心 → 病毒和威胁防护 → 管理设置 → 排除项 → 添加文件夹 → 选择 `ProductionPlanReview` 文件夹
2. 或者：属性 → 勾选“解除锁定” / 右键 → 允许运行

**macOS Gatekeeper：**
```bash
# 移除隔离属性
xattr -cr /path/to/ProductionPlanReview.app
# 或 dist/ProductionPlanReview/ProductionPlanReview

# 临时签名
codesign --force --deep --sign - /path/to/ProductionPlanReview.app

# 右键 → 打开（不是双击），点“仍要打开”
```
或 系统设置 → 隐私与安全性 → 仍要打开

**公司电脑有EDR (CrowdStrike, SentinelOne等)：**
- 联系IT加白名单，路径或hash
- 或改用方案1的 portable 版本

### 方案4: Docker（完全绕过）

如果同事有Docker：

```bash
docker build -t ppr .
docker run -p 8502:8502 ppr
# 浏览器打开 http://localhost:8502
```

Docker镜像不会被当病毒。

### 方案5: Web服务部署

把 app 部署到内部服务器，同事直接用浏览器访问，无需本地运行。

---

## 已做的优化

- `ProductionPlanReview.spec` 中 `upx=False` (之前 True)
- `build.py` 默认 `--noupx`
- 新增 `build_safe.py` 专门做低误报构建
- 新增 `make_portable.py` 生成无exe的便携版
- `app/config.py` 使用可写路径 `~/.production_plan_review/uploads` 避免权限问题

## 推荐分发策略

| 场景 | 推荐方式 | 是否会被ban |
|------|----------|-------------|
| 普通同事，Windows | `dist_portable/windows/` + START.bat | ❌ 不会 |
| 普通同事，macOS | `dist_portable/macos_linux/` + START.sh | ❌ 不会 |
| 严格企业安全 | Docker | ❌ 不会 |
| 需单文件exe | `build_safe.py --onefile` | ⚠️ 可能，需加白名单 |
| 需原生窗口 | `build.py --with-webview --windowed` | ⚠️ 较低 |

**一句话总结：别发 exe，发文件夹 `dist_portable/windows/` 最安全。**
