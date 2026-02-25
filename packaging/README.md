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

脚本会自动完成：安装依赖 → 下载 Chromium（图表导出用） → 构建前端 → PyInstaller 打包 → 生成安装包（如果已安装 NSIS）。

### 方式二：手动分步执行

```powershell
# 1. 打包
pyinstaller nini.spec --noconfirm

# 2.（可选）制作安装包
makensis packaging\installer.nsi
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
+-- nini.exe                  # 主程序入口
+-- web\dist\                 # 前端静态文件
+-- data\
|   +-- fonts\                # 内置 CJK 字体
|   +-- prompt_components\    # 系统提示词模板
+-- templates\journal_styles\ # 期刊样式模板
+-- skills\                   # Markdown 技能定义
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
dist\nini\nini.exe doctor

# 2. 生成配置文件
dist\nini\nini.exe init
# 配置文件生成在 %USERPROFILE%\.nini\.env

# 3. 编辑配置，填入至少一个 LLM API Key
notepad %USERPROFILE%\.nini\.env

# 4. 启动服务
dist\nini\nini.exe start

# 5. 打开浏览器访问
start http://127.0.0.1:8000
```

### 验证清单

| 检查项 | 预期结果 |
|--------|---------|
| `nini.exe doctor` | 检查通过，无 FAIL |
| `nini.exe start` | 控制台输出 "Nini 启动完成" |
| 浏览器 `127.0.0.1:8000` | 显示前端界面 |
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
3. 安装完成后桌面/开始菜单出现快捷方式
4. 控制面板"程序和功能"中可见 Nini 条目
5. 卸载时提示是否清理用户数据

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

- `nini tools create` / `nini skills create` 命令在打包模式下不可用（开发者命令）
- R 代码执行需要用户单独安装 R 环境
- 首次启动可能触发 Windows Defender SmartScreen 警告（建议代码签名）

---

## 十一、故障排查

| 问题 | 解决方案 |
|------|---------|
| `ModuleNotFoundError: No module named 'xxx'` | 在 `nini.spec` 的 `hiddenimports` 中添加缺失模块，重新打包 |
| 启动后闪退 | 在 cmd 中运行 `dist\nini\nini.exe start` 查看错误堆栈 |
| `Failed to execute script` | 检查杀毒软件是否拦截；尝试以管理员身份运行 |
| 缺少 DLL | 安装 [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| 前端页面空白 | 确认打包前已执行 `npm run build`，检查 `dist\nini\web\dist\index.html` 是否存在 |
| SmartScreen 警告 | 正常现象（未签名），点击"更多信息" -> "仍要运行"；正式发布建议代码签名 |
| `.env` 不生效 | 确认文件路径：`%USERPROFILE%\.nini\.env`，编码 UTF-8 无 BOM |
| 端口 8000 被占用 | 使用 `nini.exe start --port 9000` |
| scipy/numpy 报错 | 可能需在 spec 中补充 `scipy.special._cdflib` 等隐式依赖 |
| 数据库错误 | 删除 `%USERPROFILE%\.nini\db\nini.db` 重新初始化 |
| 图表导出失败（Chrome not found） | 打包前确保运行 `kaleido_get_chrome -y`；若命令不存在，执行 `python -c "from choreographer.cli._cli_utils import get_chrome_sync; print(get_chrome_sync())"`；或手动设置环境变量 `BROWSER_PATH` 指向 Chrome 可执行文件 |
