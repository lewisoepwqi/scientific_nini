"""应用配置，基于 Pydantic Settings。"""

import os
import sys
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------- 冻结环境（PyInstaller）路径解析 ----------

# PyInstaller 打包后 sys.frozen == True，sys._MEIPASS 指向解压的 bundle 目录
IS_FROZEN = getattr(sys, "frozen", False)


def _get_bundle_root() -> Path:
    """获取 bundle 资源根目录。

    - 开发模式：项目根目录（pyproject.toml 所在位置）
    - 冻结模式：PyInstaller 解压目录（sys._MEIPASS）
    """
    if IS_FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent.parent


def _setup_frozen_chrome_path() -> None:
    """在打包模式下设置 BROWSER_PATH 环境变量，让 choreographer 找到打包的 Chrome。"""
    if not IS_FROZEN:
        return
    if os.environ.get("BROWSER_PATH"):
        return  # 用户已手动设置
    bundle = _get_bundle_root()
    # Windows: chrome-win64/chrome.exe; Linux: chrome-linux64/chrome
    for candidate in [
        bundle / "choreographer" / "cli" / "browser_exe" / "chrome-win64" / "chrome.exe",
        bundle / "choreographer" / "cli" / "browser_exe" / "chrome-win32" / "chrome.exe",
        bundle / "choreographer" / "cli" / "browser_exe" / "chrome-linux64" / "chrome",
        bundle
        / "choreographer"
        / "cli"
        / "browser_exe"
        / "chrome-mac-x64"
        / "Google Chrome for Testing.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome for Testing",
        bundle
        / "choreographer"
        / "cli"
        / "browser_exe"
        / "chrome-mac-arm64"
        / "Google Chrome for Testing.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome for Testing",
    ]:
        if candidate.exists():
            os.environ["BROWSER_PATH"] = str(candidate)
            break


_setup_frozen_chrome_path()


def _get_user_data_dir() -> Path:
    """获取运行时可写数据目录。

    - 开发模式：项目根 / data
    - 冻结模式：~/.nini（用户主目录下，可写）
    """
    if IS_FROZEN:
        return Path.home() / ".nini"
    return _get_bundle_root() / "data"


# 项目/bundle 根目录
_ROOT = _get_bundle_root()


class Settings(BaseSettings):
    """全局配置，支持 .env 文件和环境变量。"""

    model_config = SettingsConfigDict(
        # 冻结模式：优先读用户数据目录的 .env，其次读 bundle/.env
        # 开发模式：两者指向同一个项目根目录
        env_file=(str(_get_user_data_dir() / ".env"), str(_ROOT / ".env")),
        env_file_encoding="utf-8",
        env_prefix="NINI_",
        extra="ignore",
    )

    # ---- 基础 ----
    app_name: str = "Nini"
    debug: bool = False
    data_dir: Path = _get_user_data_dir()

    # ---- LLM ----
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model: str = "gpt-4o"

    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # Moonshot AI (Kimi)
    moonshot_api_key: Optional[str] = None
    moonshot_model: str = "moonshot-v1-8k"

    # Kimi Coding（kimi.com Coding Plan）
    kimi_coding_api_key: Optional[str] = None
    kimi_coding_base_url: str = "https://api.kimi.com/coding/v1"
    kimi_coding_model: str = "kimi-for-coding"

    # 智谱 AI (GLM) — 默认使用 Coding Plan 端点
    zhipu_api_key: Optional[str] = None
    zhipu_base_url: str = "https://open.bigmodel.cn/api/coding/paas/v4"
    zhipu_model: str = "glm-4"

    # DeepSeek
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-chat"

    # 阿里百炼（通义千问）
    dashscope_api_key: Optional[str] = None
    dashscope_model: str = "qwen-plus"

    # MiniMax
    minimax_api_key: Optional[str] = None
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M2.5"

    # LLM 通用
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    llm_max_retries: int = 3
    llm_timeout: int = 120  # HTTP 请求超时（秒）
    llm_trust_env_proxy: bool = False

    # ---- Agent ----
    # <= 0 表示不限制迭代次数（仅受用户中止/模型与工具自然收敛约束）
    agent_max_iterations: int = 0

    # ---- 上传 ----
    max_upload_size: int = 50 * 1024 * 1024  # 50 MB
    allowed_extensions: str = "csv,xlsx,xls,tsv,txt"

    # ---- 沙箱 ----
    sandbox_timeout: int = 60  # 秒（含代码执行 + DataFrame 跨进程序列化时间）
    sandbox_max_memory_mb: int = 512
    sandbox_image_export_timeout: int = 60  # 图片导出专用超时（秒），kaleido 渲染较慢
    r_enabled: bool = True
    r_sandbox_timeout: int = 120
    r_sandbox_max_memory_mb: int = 1024
    r_package_install_timeout: int = 300
    r_auto_install_packages: bool = True
    r_webr_enabled: bool = True  # 允许 webr（WebAssembly R）作为执行后端，无需本地 R
    r_webr_timeout: int = 60  # webr 执行超时（秒），WASM 比原生 R 慢，可适当放宽

    # ---- Plotly 图表导出配置 ----
    plotly_export_width: int = 1400
    plotly_export_height: int = 900
    plotly_export_scale: float = 2.0
    plotly_export_timeout: float = 30.0  # 秒

    # ---- 图表风格与一致性配置 ----
    chart_default_style: str = "default"
    chart_default_render_engine: str = "auto"  # auto|plotly|matplotlib
    chart_bitmap_dpi: int = 300
    chart_default_export_formats: str = "pdf,svg,png"
    chart_similarity_threshold: float = 0.96
    font_fallback_url: str = ""  # 自定义字体下载 URL，空串使用内置镜像列表
    font_auto_download: bool = True  # 是否启用运行时自动下载字体

    # ---- 知识库 ----
    knowledge_max_entries: int = 3  # 每次注入最多几个知识条目
    knowledge_max_chars: int = 3000  # 注入总字符数上限
    knowledge_openai_embedding_model: str = "text-embedding-3-small"
    knowledge_local_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    prompt_component_max_chars: int = 20000
    prompt_total_max_chars: int = 60000
    skills_dir_path: Path = _get_bundle_root() / "skills"
    skills_extra_dirs: str = ""
    skills_auto_discover_compat_dirs: bool = False

    # ---- 自动上下文压缩 ----
    auto_compress_enabled: bool = True
    auto_compress_threshold_tokens: int = 30000
    auto_compress_target_tokens: int = 15000

    # ---- Memory 优化 ----
    memory_large_payload_threshold_bytes: int = 10 * 1024  # 10 KB，超过此大小的数据引用化
    memory_auto_compress: bool = True
    memory_compress_threshold_kb: int = 500
    memory_keep_recent_messages: int = 20
    compressed_context_max_chars: int = 2000  # 压缩上下文累积上限，超出后丢弃最旧段

    # ---- 派生属性 ----
    @property
    def upload_dir(self) -> Path:
        d = self.data_dir / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def sessions_dir(self) -> Path:
        d = self.data_dir / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def db_path(self) -> Path:
        d = self.data_dir / "db"
        d.mkdir(parents=True, exist_ok=True)
        return d / "nini.db"

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def knowledge_dir(self) -> Path:
        d = self.data_dir / "knowledge"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def prompt_components_dir(self) -> Path:
        d = self.data_dir / "prompt_components"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def skills_dir(self) -> Path:
        """Markdown 技能目录（文件型技能定义）。"""
        return Path(self.skills_dir_path)

    @property
    def skills_search_dirs(self) -> list[Path]:
        """Markdown 技能发现目录（按优先级排序，前者优先）。"""
        dirs: list[Path] = []
        seen: set[Path] = set()

        def _append(path: Path) -> None:
            resolved = path.expanduser().resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            dirs.append(resolved)

        if self.skills_auto_discover_compat_dirs:
            # 项目级兼容目录（优先）
            _append(_ROOT / ".codex" / "skills")
            _append(_ROOT / ".claude" / "skills")
            _append(_ROOT / ".opencode" / "skills")
            _append(_ROOT / ".agents" / "skills")

        # 现有默认目录
        _append(self.skills_dir)

        # 用户显式追加目录（最低优先）
        for raw in self.skills_extra_dirs.split(","):
            candidate = raw.strip()
            if not candidate:
                continue
            _append(Path(candidate))

        return dirs

    @property
    def skills_snapshot_path(self) -> Path:
        p = self.data_dir / "SKILLS_SNAPSHOT.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def skills_state_path(self) -> Path:
        """技能管理状态文件（如启用/禁用覆盖）。"""
        p = self.data_dir / "skills_state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip() for ext in self.allowed_extensions.split(",")]

    @property
    def profiles_dir(self) -> Path:
        """用户画像存储目录。"""
        d = self.data_dir / "profiles"
        d.mkdir(parents=True, exist_ok=True)
        return d


# 全局单例
settings = Settings()
