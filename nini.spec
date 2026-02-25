# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec 文件 — Nini Windows 桌面打包。

使用方式：
    pyinstaller nini.spec

生成目录：dist/nini/（onedir 模式），配合 NSIS 制作安装包。
"""

import sys
from pathlib import Path

block_cipher = None

# 项目根目录
ROOT = Path(SPECPATH)

# 构建 datas 列表：只包含实际存在的目录，避免打包时报错
_candidate_datas = [
    # (源路径, bundle 内目标路径, 是否必须)
    (ROOT / "web" / "dist", "web/dist", True),
    (ROOT / "data" / "fonts", "data/fonts", False),
    (ROOT / "data" / "prompt_components", "data/prompt_components", False),
    (ROOT / "templates" / "journal_styles", "templates/journal_styles", False),
    (ROOT / "skills", "skills", False),
]

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

a = Analysis(
    [str(ROOT / "src" / "nini" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=_datas,
    hiddenimports=[
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
    ],
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir 模式
    name="nini",
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="nini",
)
