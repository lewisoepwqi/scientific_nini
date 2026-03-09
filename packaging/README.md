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
4. 开始菜单额外提供“命令行工具”，指向 `nini-cli.exe`
5. 控制面板"程序和功能"中可见 Nini 条目
6. 卸载时提示是否清理用户数据

---

## 八、减小体积

打包体积较大（约 400-800 MB）主要来自科学计算库。可选优化：

1. **排除 kaleido**：如不需要图片导出功能，在 `nini.spec` 的 `excludes` 中添加 `"kaleido"`
2. **UPX 压缩**：spec 文件已启用 UPX，确保系统安装了 [UPX](https://upx.github.io/)
3. **排除未使用的 matplotlib 后端**：已在 spec 中配置

---

## 九、代码签名（推荐）

为避免 Windows SmartScreen 警告，建议使用代码签名证书签名：

```powershell
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\nini\nini.exe
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\Nini-0.1.0-Setup.exe
```

---

## 十、已知限制

- `nini-cli.exe tools create` / `nini-cli.exe skills create` 命令在打包模式下不可用（开发者命令）
- R 代码执行需要用户单独安装 R 环境
- 若要“连本地模型一起打包”，当前仅建议走便携版 Ollama + 模型目录整体打包；安装包体积可能达到数 GB 到数十 GB
- 首次启动可能触发 Windows Defender SmartScreen 警告（建议代码签名）

---

## 十一、故障排查

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
