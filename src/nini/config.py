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
    kimi_coding_model: str = "kimi-for-coding"

    # 智谱 AI (GLM)
    zhipu_api_key: Optional[str] = None
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
    llm_trust_env_proxy: bool = False

    # ---- Agent ----
    agent_max_iterations: int = 20

    # ---- 上传 ----
    max_upload_size: int = 50 * 1024 * 1024  # 50 MB
    allowed_extensions: str = "csv,xlsx,xls,tsv,txt"

    # ---- 沙箱 ----
    sandbox_timeout: int = 30  # 秒
    sandbox_max_memory_mb: int = 512

    # ---- 知识库 ----
    knowledge_max_entries: int = 3  # 每次注入最多几个知识条目
    knowledge_max_chars: int = 3000  # 注入总字符数上限
    prompt_component_max_chars: int = 20000
    prompt_total_max_chars: int = 60000
    skills_dir_path: Path = _ROOT / "skills"

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


# 全局单例
settings = Settings()
