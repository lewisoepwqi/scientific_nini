# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec 文件 — Nini Windows 桌面打包。

使用方式：
    pyinstaller nini.spec

生成目录：dist/nini/（onedir 模式），配合 NSIS 制作安装包。
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# 项目根目录
ROOT = Path(SPECPATH)

# ── 自动检测 choreographer 的 Chrome 下载目录 ──────────────────────────────
# kaleido 使用 choreographer 库调用 Chromium 来导出图表为图片。
# 运行 `kaleido_get_chrome` 后，Chrome 会下载到 choreographer 默认缓存目录。
# 如果命令不在 PATH，可改用：
# `python -c "from choreographer.cli._cli_utils import get_chrome_sync; print(get_chrome_sync())"`。
# 打包时会把该目录归档到 runtime/browser/chromium 下，否则打包产物无法使用图片导出功能。
_choreo_chrome_dir = None
try:
    import choreographer.cli._cli_utils as _cli
    _choreo_browser_exe = Path(_cli.default_download_path)
    if _choreo_browser_exe.exists() and any(_choreo_browser_exe.iterdir()):
        _choreo_chrome_dir = _choreo_browser_exe
        print(f"  INFO: Found choreographer Chrome at: {_choreo_chrome_dir}")
    else:
        print(f"  WARN: choreographer Chrome dir empty or missing: {_choreo_browser_exe}")
        print("        Run `kaleido_get_chrome -y` before packaging to enable chart export.")
        print("        If command not found, use: python -c \"from choreographer.cli._cli_utils import get_chrome_sync; print(get_chrome_sync())\"")
except Exception as e:
    print(f"  WARN: Cannot detect choreographer Chrome path: {e}")
    print("        Chart image export may not work in packaged app.")

# 构建 datas 列表：只包含实际存在的目录，避免打包时报错
_candidate_datas = [
    # (源路径, bundle 内目标路径, 是否必须)
    (ROOT / "web" / "dist", "app/web/dist", True),
    (ROOT / "data" / "fonts", "assets/fonts", False),
    (ROOT / "data" / "prompt_components", "assets/prompt_components", False),
    (ROOT / "config" / "recipes", "assets/config/recipes", True),
    (ROOT / "templates" / "journal_styles", "assets/templates/journal_styles", False),
    (ROOT / ".nini" / "skills", "assets/skills/nini", False),
    (ROOT / "skills", "assets/skills/shared", False),
]

_optional_dir_envs = [
    ("NINI_OLLAMA_BUNDLE_DIR", "runtime/ollama/bin"),
    ("NINI_OLLAMA_MODELS_DIR", "runtime/ollama/models"),
    ("NINI_HF_HOME", "runtime/models/huggingface"),
    ("NINI_SENTENCE_TRANSFORMERS_HOME", "runtime/models/sentence-transformers"),
]

for env_name, dest in _optional_dir_envs:
    raw_path = os.environ.get(env_name, "").strip()
    if not raw_path:
        continue
    src = Path(raw_path).expanduser().resolve()
    if src.exists():
        _candidate_datas.append((src, dest, False))
        print(f"  INFO: Including optional bundle from {env_name}: {src}")
    else:
        print(f"  WARN: {env_name} points to missing path, skipping: {src}")

# 添加 choreographer Chrome 到打包数据
if _choreo_chrome_dir is not None:
    _candidate_datas.append(
        (_choreo_chrome_dir, "runtime/browser/chromium", False),
    )

_datas = []
for src, dest, required in _candidate_datas:
    if src.exists():
        _datas.append((str(src), dest))
    elif required:
        raise FileNotFoundError(
            f"Required data directory not found: {src}\n"
            f"Please build the frontend first: cd web && npm install && npm run build"
        )
    else:
        print(f"  WARN: Optional data directory not found, skipping: {src}")


def _collect_optional_submodules(package_name: str) -> list[str]:
    """收集可选依赖的子模块；未安装时静默跳过。"""
    try:
        modules = collect_submodules(package_name)
        print(f"  INFO: Collected optional submodules for {package_name}: {len(modules)}")
        return modules
    except Exception as exc:
        print(f"  WARN: Cannot collect optional submodules for {package_name}: {exc}")
        return []


_hiddenimports = [
    # ----- nini 自身模块 -----
    "nini",
    "nini.app",
    "nini.config",
    "nini.agent.runner",
    "nini.agent.session",
    "nini.agent.model_resolver",
    "nini.agent.planner",
    "nini.agent.plan_parser",
    "nini.agent.task_manager",
    "nini.api.routes",
    "nini.api.websocket",
    "nini.models.database",
    "nini.tools.registry",
    # ----- uvicorn 内部模块（动态加载） -----
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # ----- tiktoken 编码注册表 -----
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    # ----- 科学计算（PyInstaller 自带 hook 已覆盖大部分） -----
    "statsmodels.tsa",
    # ----- 可视化 -----
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_svg",
    "matplotlib.backends.backend_pdf",
    # ----- 数据库 -----
    "aiosqlite",
    # ----- Pydantic -----
    "pydantic",
    "pydantic_settings",
    # ----- Markdown -----
    "markdown",
    "markdown.extensions",
    "markdown.extensions.tables",
    "markdown.extensions.fenced_code",
]

for optional_package in [
    "webview",
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "tokenizers",
    "safetensors",
    "llama_index.embeddings.huggingface",
]:
    _hiddenimports.extend(_collect_optional_submodules(optional_package))

a = Analysis(
    [
        str(ROOT / "src" / "nini" / "__main__.py"),
        str(ROOT / "src" / "nini" / "windows_launcher.py"),
    ],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除开发依赖，减小体积
        "pytest",
        "pytest_asyncio",
        "pytest_cov",
        "black",
        "mypy",
        "IPython",
        "notebook",
        "jupyter",
        "tkinter",
        "_tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 收集完整子包（含数据文件）
a.datas += Tree(str(ROOT / "src" / "nini"), prefix="nini", excludes=["__pycache__", "*.pyc"])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


def _select_script(toc, script_stem):
    for entry in toc:
        if entry[0] == script_stem:
            return [entry]
    raise KeyError(f"Script entry not found in Analysis.scripts: {script_stem}")

cli_exe = EXE(
    pyz,
    _select_script(a.scripts, "__main__"),
    [],
    exclude_binaries=True,  # onedir 模式
    name="nini-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 控制台应用（显示日志输出）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "nini.ico") if (ROOT / "packaging" / "nini.ico").exists() else None,
)

launcher_exe = EXE(
    pyz,
    _select_script(a.scripts, "windows_launcher"),
    [],
    exclude_binaries=True,
    name="nini",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 启动器，双击不弹终端
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "nini.ico") if (ROOT / "packaging" / "nini.ico").exists() else None,
)

coll = COLLECT(
    cli_exe,
    launcher_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="nini",
)
