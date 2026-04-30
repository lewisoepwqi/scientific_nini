# Nini Windows 打包完整操作指南

将 Nini 打包为 Windows 可执行文件（.exe），生成安装包供用户一键安装。

---

## 一、环境准备

### 1.1 安装 Python 3.12+

从 [python.org](https://www.python.org/downloads/) 下载安装，**安装时勾选 "Add Python to PATH"**。

```powershell
# 验证
python --version
# 应输出 Python 3.12.x 或更高
```

### 1.2 安装 Node.js 18+

从 [nodejs.org](https://nodejs.org/) 下载 LTS 版本安装。

```powershell
node --version
npm --version
```

### 1.3 安装 NSIS（可选，制作安装包用）

从 https://nsis.sourceforge.io/Download 下载安装，安装完成后确认 `makensis` 在 PATH 中：

```powershell
makensis /VERSION
```

### 1.4 安装 UPX（可选，压缩体积）

从 https://upx.github.io/ 下载 Windows 版，解压后将 `upx.exe` 所在目录加入 PATH。

---

## 二、获取源码

```powershell
git clone https://github.com/lewisoepwqi/scientific_nini.git
cd scientific_nini
```

---

## 三、安装依赖

```powershell
# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate

# 安装后端 + 打包依赖
pip install -e .[packaging]

# 安装前端依赖并构建
cd web
npm install
npm run build
cd ..
```

构建完成后确认 `web\dist\index.html` 存在：

```powershell
dir web\dist\index.html
```

---

## 四、执行打包

### 方式一：一键打包脚本（推荐）

项目根目录提供了 `build_windows.bat`，执行：

```powershell
build_windows.bat
```

脚本会自动完成：安装依赖 → 可选生成打包版密钥 → 下载 Chromium（图表导出用） → 构建前端 → PyInstaller 打包 → 生成安装包（如果已安装 NSIS）。

当前桌面壳默认行为：

1. 双击 `nini.exe` 直接打开内嵌 WebView2 窗口，不再默认拉起系统浏览器。
2. 若用户显式执行 `nini.exe --external-browser`，则回退到浏览器兼容模式。
3. NSIS 安装器会检测 WebView2 Runtime，缺失时自动下载安装。

### 方式一补充：常用打包环境变量

```powershell
# 1. 可选：内嵌系统内置模型 Key（用于“系统内置”模型）
$env:NINI_BUILTIN_DASHSCOPE_API_KEY="sk-xxx"

# 2. 可选：内嵌试用 Key（用于试用模式）
$env:NINI_TRIAL_API_KEY="sk-xxx"

# 3. 可选：打包便携版 Ollama 运行时
$env:NINI_OLLAMA_BUNDLE_DIR="D:\portable-ollama"

# 4. 可选：把本地 Ollama 模型目录一起打包
$env:NINI_OLLAMA_MODELS_DIR="D:\ollama-models"

build_windows.bat
```

说明：

1. `NINI_BUILTIN_DASHSCOPE_API_KEY` / `NINI_TRIAL_API_KEY` 只建议在发布机构建机上设置。脚本会生成临时的 `src\nini\_builtin_key.py`，打包结束后自动删除。
2. `NINI_OLLAMA_BUNDLE_DIR` 需要指向一个可直接运行 `ollama.exe` 的目录。
3. `NINI_OLLAMA_MODELS_DIR` 通常体积很大，建议只在离线交付场景下使用。

### 方式二：手动分步执行

```powershell
# 1. 可选：生成打包版密钥
python scripts\encrypt_builtin_key.py

# 2. 打包
pyinstaller nini.spec --noconfirm

# 3.（可选）制作安装包
makensis /DPRODUCT_VERSION=0.1.0 packaging\installer.nsi
```

**预计耗时**：5-15 分钟（取决于机器性能）。

打包完成后，产物在 `dist\nini\` 目录：

```powershell
# 验证产物
dir dist\nini\nini.exe

# 查看目录大小（MB）
powershell -Command "(Get-ChildItem dist\nini -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB"
```

---

## 五、产物目录结构

### 打包产物 `dist\nini\`

```
dist\nini\
+-- nini.exe                  # GUI 启动器（双击直接打开内嵌桌面窗口，不弹终端）
+-- nini-cli.exe              # CLI 入口（doctor/init/start 等）
+-- nini-updater.exe          # 应用内升级器（等待旧进程退出、静默安装、重启）
+-- web\dist\                 # 前端静态文件
+-- data\
|   +-- fonts\                # 内置 CJK 字体
|   +-- prompt_components\    # 系统提示词模板
+-- templates\journal_styles\ # 期刊样式模板
+-- skills\                   # Markdown 技能定义
+-- runtime\ollama\           # 可选：便携版 Ollama
+-- runtime\ollama-models\    # 可选：本地模型权重
+-- python312.dll             # Python 运行时
+-- ... (其他依赖库)
```

### 用户运行时数据 `%USERPROFILE%\.nini\`

用户运行时产生的数据存储在 `~/.nini/`（即 `%USERPROFILE%\.nini\`）：

```
%USERPROFILE%\.nini\
+-- .env              # 用户配置（API Key 等）
+-- db\nini.db        # SQLite 数据库
+-- sessions\         # 会话数据
+-- knowledge\        # 知识库索引
+-- uploads\          # 上传文件
+-- profiles\         # 用户画像
```

---

## 六、本地验证

```powershell
# 1. 测试 doctor 命令
dist\nini\nini-cli.exe doctor

# 2. 生成配置文件
dist\nini\nini-cli.exe init
# 配置文件生成在 %USERPROFILE%\.nini\.env

# 3. 编辑配置，填入至少一个 LLM API Key
notepad %USERPROFILE%\.nini\.env

# 4. 启动服务（CLI 调试模式）
dist\nini\nini-cli.exe start

# 5. 用户双击 GUI 启动器时不会弹终端，并直接显示内嵌桌面窗口
dist\nini\nini.exe
```

### 验证清单

| 检查项 | 预期结果 |
|--------|---------|
| `nini-cli.exe doctor` | 检查通过，无 FAIL |
| `nini.exe` | 不弹终端，直接打开内嵌桌面窗口 |
| `nini-cli.exe start` | 控制台输出启动日志 |
| `nini-updater.exe` | 存在于 `dist\nini\`，不依赖 Web UI 或 Agent 运行时状态 |
| 内嵌窗口首页 | 显示前端界面 |
| 发送一条消息 | Agent 正常响应 |
| 上传 CSV 文件 | 数据加载成功 |

---

## 七、制作安装包（可选）

```powershell
makensis packaging\installer.nsi
```

生成文件：`dist\Nini-0.1.0-Setup.exe`

双击运行安装包验证：

1. 安装向导显示中文欢迎页
2. 可选择安装目录（默认 `%LOCALAPPDATA%\Nini`）
3. 安装完成后桌面/开始菜单出现快捷方式，默认快捷方式指向 `nini.exe`
4. 开始菜单额外提供”命令行工具”，指向 `nini-cli.exe`
5. 控制面板”程序和功能”中可见 Nini 条目
6. 卸载时提示是否清理用户数据

### 企业离线包构建

如需内嵌 WebView2 Runtime（适用于无网络访问的企业环境）：

```batch
set BUNDLE_WEBVIEW2=1
build_windows.bat
```

构建脚本会自动下载 `MicrosoftEdgeWebView2RuntimeInstallerX64.exe` 并捆绑进安装包。
安装时无需网络，直接从安装包内部完成 WebView2 安装。

### 静默安装（GPO / 批量部署）

用于企业 GPO 部署或批量安装场景，所有错误通过退出码反映（0 = 成功，非 0 = 失败），不弹出任何对话框。

```batch
REM 静默安装到默认路径（%LOCALAPPDATA%\Nini）
nini-setup.exe /S

REM 静默安装到自定义路径
nini-setup.exe /S /D=C:\Enterprise\Nini

REM 静默卸载
"C:\Enterprise\Nini\uninstall.exe" /S
```

**参数说明**：
- `/S`：启用静默模式，无任何交互式对话框（错误通过日志和退出码反映）
- `/D=<path>`：指定安装路径，必须与 `/S` 结合使用且放在末尾

**检查安装结果**：
```batch
nini-setup.exe /S /D=C:\Enterprise\Nini
echo %ERRORLEVEL%
REM 退出码 0 表示成功，非 0 表示失败
```

### 代码签名

签名需要：
- 已安装 Authenticode 证书（EV 证书或标准证书均可）
- Windows SDK 中的 `signtool.exe` 在 PATH 中

```batch
REM 指定证书指纹（在系统证书存储中查找）
set SIGNING_CERT_THUMBPRINT=YOUR_CERT_THUMBPRINT_HERE
build_windows.bat
```

构建脚本会自动对 `nini.exe`、`nini-cli.exe`、`nini-updater.exe` 和安装包进行 SHA-256 签名并附加时间戳。
若未设置 `SIGNING_CERT_THUMBPRINT`，跳过签名，适用于开发构建。

---

## 八、应用内升级发布元数据

应用内升级第一版使用静态发布目录。建议服务器目录结构如下：

```text
updates/
+-- stable/
|   +-- latest.json
|   +-- Nini-0.1.1-Setup.exe
|   +-- Nini-0.1.1-Setup.exe.sha256
+-- beta/
    +-- latest.json
    +-- Nini-0.1.2rc1-Setup.exe
    +-- Nini-0.1.2rc1-Setup.exe.sha256
```

客户端配置的更新源基础 URL 应指向 `updates/` 根目录，程序会按 `NINI_UPDATE_CHANNEL` 访问 `<base>/<channel>/latest.json`：

```env
NINI_UPDATE_BASE_URL=https://download.example.com/nini/updates/
NINI_UPDATE_CHANNEL=stable
NINI_UPDATE_AUTO_CHECK_ENABLED=true
NINI_UPDATE_CHECK_INTERVAL_HOURS=24
```

### 生成 manifest 草稿

`build_windows.bat` 在生成安装包后会始终生成 `.sha256` 文件。若设置 `NINI_UPDATE_ASSET_BASE_URL`（兼容回退到 `NINI_UPDATE_BASE_URL`），还会生成并校验 `dist\latest.json`：

```batch
set "NINI_VERSION=0.1.1"
set "NINI_UPDATE_ASSET_BASE_URL=https://download.example.com/nini/updates/stable/"
set "NINI_UPDATE_CHANNEL=stable"
set "NINI_UPDATE_NOTES=修复升级检查失败|优化启动稳定性"
set "SIGNING_CERT_THUMBPRINT=YOUR_CERT_THUMBPRINT_HERE"
build_windows.bat
```

也可以手动执行：

```powershell
python scripts\generate_update_manifest.py `
  --installer dist\Nini-0.1.1-Setup.exe `
  --version 0.1.1 `
  --channel stable `
  --base-url https://download.example.com/nini/updates/stable/ `
  --notes "修复升级检查失败|优化启动稳定性" `
  --output dist\latest.json

python scripts\verify_update_manifest.py `
  --manifest dist\latest.json `
  --installer dist\Nini-0.1.1-Setup.exe
```

上传前必须确认：

| 检查项 | 要求 |
|--------|------|
| `latest.json` | `product=nini`、`channel` 与服务器目录一致、版本号符合 PEP 440 |
| 安装包 URL | 必须是 HTTPS，且与更新源基础 URL 同域 |
| `size` / `sha256` | 必须通过 `verify_update_manifest.py` 校验 |
| 签名 | 正式发布必须签名 `nini.exe`、`nini-cli.exe`、`nini-updater.exe` 和安装包 |
| manifest 签名字段 | `signature` / `signature_url` 目前预留，MVP 不强制校验 |

### 应用内升级烟测

发布到 stable 前至少执行一次打包版升级烟测：

1. 安装旧版，例如 `Nini-0.1.0-Setup.exe`。
2. 在 `%USERPROFILE%\.nini` 创建或保留真实配置、数据库、会话、上传文件和日志。
3. 将旧版配置指向测试更新源，并确认 `latest.json` 指向新版安装包。
4. 启动旧版 Nini，在设置页手动检查更新。
5. 下载更新包，确认状态从 downloading 变为 ready。
6. 点击立即重启并升级，确认旧进程退出、安装器静默覆盖安装、新版 `nini.exe` 自动启动。
7. 检查 `%USERPROFILE%\.nini\logs\updater.log`，确认记录等待进程、安装退出码和重启结果。
8. 验证 `%USERPROFILE%\.nini` 中配置、数据库、会话、上传文件和日志仍存在。

如需禁用企业环境更新入口：

```env
NINI_UPDATE_DISABLED=true
```

测试构建可显式关闭安装包签名校验，但正式发布不得关闭：

```env
NINI_UPDATE_SIGNATURE_CHECK_ENABLED=false
```

正式发布建议使用证书指纹允许列表：

```env
NINI_UPDATE_SIGNATURE_ALLOWED_THUMBPRINTS=YOUR_CERT_THUMBPRINT_HERE
```

---

## 九、减小体积

打包体积较大（约 400-800 MB）主要来自科学计算库。可选优化：

1. **排除 kaleido**：如不需要图片导出功能，在 `nini.spec` 的 `excludes` 中添加 `"kaleido"`
2. **UPX 压缩**：spec 文件已启用 UPX，确保系统安装了 [UPX](https://upx.github.io/)
3. **排除未使用的 matplotlib 后端**：已在 spec 中配置

---

## 十、代码签名（推荐）

为避免 Windows SmartScreen 警告，建议使用代码签名证书签名：

```powershell
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\nini\nini.exe
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\nini\nini-cli.exe
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\nini\nini-updater.exe
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\Nini-0.1.0-Setup.exe
```

---

## 十一、已知限制

- `nini-cli.exe tools create` / `nini-cli.exe skills create` 命令在打包模式下不可用（开发者命令）
- R 代码执行需要用户单独安装 R 环境
- 若要“连本地模型一起打包”，当前仅建议走便携版 Ollama + 模型目录整体打包；安装包体积可能达到数 GB 到数十 GB
- 首次启动可能触发 Windows Defender SmartScreen 警告（建议代码签名）

---

## 十二、故障排查

| 问题 | 解决方案 |
|------|---------|
| `ModuleNotFoundError: No module named 'xxx'` | 在 `nini.spec` 的 `hiddenimports` 中添加缺失模块，重新打包 |
| 双击后浏览器未打开 | 在 cmd 中运行 `dist\nini\nini-cli.exe start` 查看错误堆栈 |
| `Failed to execute script` | 检查杀毒软件是否拦截；尝试以管理员身份运行 |
| 缺少 DLL | 安装 [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| 前端页面空白 | 确认打包前已执行 `npm run build`，检查 `dist\nini\web\dist\index.html` 是否存在 |
| SmartScreen 警告 | 正常现象（未签名），点击"更多信息" -> "仍要运行"；正式发布建议代码签名 |
| `.env` 不生效 | 确认文件路径：`%USERPROFILE%\.nini\.env`，编码 UTF-8 无 BOM |
| 端口 8000 被占用 | 使用 `nini-cli.exe start --port 9000` |
| scipy/numpy 报错 | 可能需在 spec 中补充 `scipy.special._cdflib` 等隐式依赖 |
| 数据库错误 | 删除 `%USERPROFILE%\.nini\db\nini.db` 重新初始化 |
| 图表导出失败（Chrome not found） | 打包前确保运行 `kaleido_get_chrome -y`；若命令不存在，执行 `python -c "from choreographer.cli._cli_utils import get_chrome_sync; print(get_chrome_sync())"`；或手动设置环境变量 `BROWSER_PATH` 指向 Chrome 可执行文件 |
| 便携版 Ollama 未自动启动 | 确认 `runtime\ollama\ollama.exe` 已被打包，且 `NINI_OLLAMA_BUNDLE_DIR` 指向的是可运行目录 |
