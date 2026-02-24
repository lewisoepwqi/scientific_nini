# Nini Windows 打包指南

将 Nini 打包为 Windows 可执行文件（.exe），生成安装包供用户一键安装。

## 前提条件

- Windows 10/11 x64
- Python >= 3.12
- Node.js >= 18（构建前端）
- [NSIS](https://nsis.sourceforge.io/)（可选，制作安装包）

## 快速打包

### 1. 安装打包依赖

```bash
pip install -e .[packaging]
```

### 2. 构建前端

```bash
cd web && npm install && npm run build && cd ..
```

### 3. 执行 PyInstaller 打包

```bash
pyinstaller nini.spec
```

生成目录：`dist/nini/`，其中 `nini.exe` 即为主程序。

### 4.（可选）制作安装包

安装 [NSIS](https://nsis.sourceforge.io/) 后：

```bash
makensis packaging/installer.nsi
```

生成文件：`dist/Nini-0.1.0-Setup.exe`

## 目录结构

打包后的 `dist/nini/` 目录结构：

```
dist/nini/
├── nini.exe                  # 主程序入口
├── web/dist/                 # 前端静态文件
├── data/
│   ├── fonts/                # 内置 CJK 字体
│   └── prompt_components/    # 系统提示词模板
├── templates/journal_styles/ # 期刊样式模板
├── skills/                   # Markdown 技能定义
├── python312.dll             # Python 运行时
└── ... (其他依赖库)
```

## 运行时数据

用户运行时产生的数据存储在 `~/.nini/`（即 `%USERPROFILE%\.nini\`）：

```
~/.nini/
├── db/nini.db        # SQLite 数据库
├── sessions/         # 会话数据
├── knowledge/        # 知识库索引
├── uploads/          # 上传文件
└── profiles/         # 用户画像
```

## 使用方式

安装完成后，用户可通过以下方式启动：

```bash
# 命令行启动
nini.exe start

# 或双击桌面快捷方式（自动执行 nini.exe start）
```

首次启动后，在浏览器中访问 `http://127.0.0.1:8000` 即可使用。

## 配置

首次运行前，用户需配置 LLM API Key：

```bash
# 生成配置文件模板
nini.exe init --env-file %USERPROFILE%\.nini\.env

# 编辑配置文件，填写 API Key
notepad %USERPROFILE%\.nini\.env
```

或直接在 Web 界面的模型配置面板中设置。

## 减小体积

打包体积较大（约 400-800 MB）主要来自科学计算库。可选优化：

1. **排除 kaleido**：如不需要图片导出功能，在 `nini.spec` 的 `excludes` 中添加 `"kaleido"`
2. **UPX 压缩**：spec 文件已启用 UPX，确保系统安装了 [UPX](https://upx.github.io/)
3. **排除未使用的 matplotlib 后端**：已在 spec 中配置

## 已知限制

- `nini tools create` / `nini skills create` 命令在打包模式下不可用（开发者命令）
- R 代码执行需要用户单独安装 R 环境
- 首次启动可能触发 Windows Defender SmartScreen 警告（建议代码签名）

## 代码签名（推荐）

为避免 SmartScreen 警告，建议使用代码签名证书签名 exe：

```powershell
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\nini\nini.exe
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com dist\Nini-0.1.0-Setup.exe
```

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| 启动闪退 | 在命令行运行 `nini.exe start` 查看错误输出 |
| 缺少 DLL | 安装 [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| 端口占用 | 使用 `nini.exe start --port 9000` 指定其他端口 |
| 数据库错误 | 删除 `~/.nini/db/nini.db` 重新初始化 |
