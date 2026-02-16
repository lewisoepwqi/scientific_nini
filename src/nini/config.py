"""应用配置，基于 Pydantic Settings。"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（pyproject.toml 所在位置）
_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """全局配置，支持 .env 文件和环境变量。"""

    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="NINI_",
        extra="ignore",
    )

    # ---- 基础 ----
    app_name: str = "Nini"
    debug: bool = False
    data_dir: Path = _ROOT / "data"

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
    skills_dir_path: Path = _ROOT / "skills"

    # ---- 自动上下文压缩 ----
    auto_compress_enabled: bool = True
    auto_compress_threshold_tokens: int = 30000
    auto_compress_target_tokens: int = 15000

    # ---- Memory 优化 ----
    memory_large_payload_threshold_bytes: int = 10 * 1024  # 10 KB，超过此大小的数据引用化
    memory_auto_compress: bool = True
    memory_compress_threshold_kb: int = 500
    memory_keep_recent_messages: int = 20

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
    def skills_snapshot_path(self) -> Path:
        p = self.data_dir / "SKILLS_SNAPSHOT.md"
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
