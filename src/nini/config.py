"""应用配置，基于 Pydantic Settings。"""

import os
import sys
from pathlib import Path
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


def _get_bundle_web_dist_dir() -> Path:
    """获取前端构建产物目录。"""
    root = _get_bundle_root()
    if IS_FROZEN:
        return root / "app" / "web" / "dist"
    return root / "web" / "dist"


def _get_bundle_templates_dir() -> Path:
    """获取内置期刊模板目录。"""
    root = _get_bundle_root()
    if IS_FROZEN:
        return root / "assets" / "templates" / "journal_styles"
    return root / "templates" / "journal_styles"


def _get_bundle_recipes_dir() -> Path:
    """获取 Recipe 配置目录。"""
    root = _get_bundle_root()
    if IS_FROZEN:
        return root / "assets" / "config" / "recipes"
    return root / "config" / "recipes"


def _get_bundle_skill_dirs() -> list[Path]:
    """获取随安装包携带的内置技能目录。"""
    root = _get_bundle_root()
    if IS_FROZEN:
        return [
            root / "assets" / "skills" / "nini",
            root / "assets" / "skills" / "shared",
        ]
    return [root / ".nini" / "skills", root / "skills"]


def _get_default_skills_dir() -> Path:
    """获取默认技能写入目录。"""
    if IS_FROZEN:
        return _get_user_data_dir() / "skills"
    return _get_bundle_root() / ".nini" / "skills"


def _setup_frozen_chrome_path() -> None:
    """在打包模式下设置 BROWSER_PATH 环境变量，让 choreographer 找到打包的 Chrome。"""
    if not IS_FROZEN:
        return
    if os.environ.get("BROWSER_PATH"):
        return  # 用户已手动设置
    browser_root = _get_bundle_root() / "runtime" / "browser" / "chromium"
    # Windows: chrome-win64/chrome.exe; Linux: chrome-linux64/chrome
    for candidate in [
        browser_root / "chrome-win64" / "chrome.exe",
        browser_root / "chrome-win32" / "chrome.exe",
        browser_root / "chrome-linux64" / "chrome",
        browser_root
        / "chrome-mac-x64"
        / "Google Chrome for Testing.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome for Testing",
        browser_root
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


def _setup_frozen_model_cache_paths() -> None:
    """在打包模式下注入离线模型缓存路径。"""
    if not IS_FROZEN:
        return

    bundle = _get_bundle_root()
    huggingface_home = bundle / "runtime" / "models" / "huggingface"
    sentence_transformers_home = bundle / "runtime" / "models" / "sentence-transformers"
    offline_bundle_found = False

    if huggingface_home.exists():
        os.environ.setdefault("HF_HOME", str(huggingface_home))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(huggingface_home / "hub"))
        offline_bundle_found = True

    if sentence_transformers_home.exists():
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(sentence_transformers_home))
        offline_bundle_found = True

    if offline_bundle_found:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("NINI_FORCE_LOCAL_MODELS", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


_setup_frozen_model_cache_paths()


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
    log_level: str | None = None
    log_dir_path: str | None = None
    log_file_name: str = "nini.log"
    log_rotate_when: str = "midnight"
    log_rotate_interval: int = 1
    log_backup_count: int = 7

    # ---- 安全 ----
    api_key: str | None = None  # 设置后所有 API/WS 请求需携带此密钥
    cors_origins: str = ""  # 生产模式 CORS 允许的来源（逗号分隔），空则拒绝跨域

    # ---- 试用模式 ----
    # ⚠️ 安全风险：此密钥嵌入配置或二进制后可被逆向提取，仅用于受控试用场景
    trial_api_key: str | None = None  # 内嵌试用密钥（留空则试用模式不可用）
    trial_days: int = 14  # 试用有效天数

    # ---- 系统内置用量限额 ----
    builtin_fast_limit: int = 100  # 快速模式最大调用次数
    builtin_deep_limit: int = 50  # 深度模式最大调用次数

    # ---- LLM ----
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # Moonshot AI (Kimi)
    moonshot_api_key: str | None = None
    moonshot_model: str = "moonshot-v1-8k"

    # Kimi Coding（kimi.com Coding Plan）
    kimi_coding_api_key: str | None = None
    kimi_coding_base_url: str = "https://api.kimi.com/coding/v1"
    kimi_coding_model: str = "kimi-for-coding"

    # 智谱 AI (GLM) — 默认使用 Coding Plan 端点
    zhipu_api_key: str | None = None
    zhipu_base_url: str = "https://open.bigmodel.cn/api/coding/paas/v4"
    zhipu_model: str = "glm-4"

    # DeepSeek
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"

    # 阿里百炼（通义千问）
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"

    # 系统内置模型（阿里百炼）
    builtin_dashscope_api_key: str | None = None
    builtin_dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    builtin_chat_fast_model: str = "qwen3.5-27b"
    builtin_chat_deep_model: str = "qwen3.5-plus"
    builtin_image_fast_model: str = "qwen3-vl-8b-instruct"
    builtin_image_deep_model: str = "qwen-vl-plus"
    builtin_title_model: str = "qwen2.5-14b-instruct"

    # MiniMax
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M2.5"

    # LLM 通用
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    llm_max_retries: int = 3
    llm_stream_retries: int = 2
    llm_timeout: int = 120  # HTTP 请求超时（秒）
    llm_trust_env_proxy: bool = False

    # ---- Agent ----
    # <= 0 表示不限制迭代次数（仅受用户中止/模型与工具自然收敛约束）
    agent_max_iterations: int = 0
    # Agent 主动执行超时（秒），不计 ask_user_question 等待等人工阻塞时间。
    # 为 None 时回退到兼容字段 agent_max_timeout_seconds。
    agent_active_execution_timeout_seconds: int | None = None
    # Agent 整轮 wall-clock 超时（秒），包含人工等待；0 表示不限制。
    # 该字段用于极端兜底，避免会话永久悬挂。
    agent_run_wall_clock_timeout_seconds: int = 0
    # 兼容旧配置：历史上该字段表示单一 Agent 总超时。
    # 现仅作为 agent_active_execution_timeout_seconds 未显式配置时的回退值。
    # 600s 为多步骤 PDCA 分析的基础保障；单步快速问答实际不会用满。
    agent_max_timeout_seconds: int = 600
    tool_argument_normalization_enabled: bool = True
    tool_circuit_breaker_threshold: int = 2
    # 批次完成摘要注入：每轮结束后向 LLM 提供"本轮已完成工具"快照，
    # 预防 LLM 在下一轮盲目重复调用（守卫语义工具）。
    # 如需关闭作为回滚手段，可设置为 False。
    runner_completion_summary_enabled: bool = True

    # ---- 上传 ----
    max_upload_size: int = 50 * 1024 * 1024  # 50 MB
    allowed_extensions: str = "csv,xlsx,xls,tsv,txt"

    # ---- 多 Agent 并发 ----
    max_sub_agent_concurrency: int = 4  # spawn_batch 最大并行子 Agent 数

    # ---- 沙箱 ----
    sandbox_timeout: int = 60  # 秒（含代码执行 + DataFrame 跨进程序列化时间）
    sandbox_max_memory_mb: int = 512
    sandbox_image_export_timeout: int = 60  # 图片导出专用超时（秒），kaleido 渲染较慢
    r_enabled: bool = True
    r_sandbox_timeout: int = 120
    r_sandbox_max_memory_mb: int = 1024
    r_package_install_timeout: int = 300
    r_auto_install_packages: bool = False
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

    # ---- 网络插件 ----
    network_timeout: int = 10  # 网络可用性检测超时（秒），对应环境变量 NINI_NETWORK_TIMEOUT
    network_probe_url: str = "https://www.baidu.com"  # 可用性探测目标（可换为国内可达地址）
    network_proxy: str | None = None  # HTTP 代理地址（可选），如 http://proxy:8080

    # ---- 功能特性开关 ----
    enable_cost_tracking: bool = True  # 启用成本追踪
    enable_reasoning: bool = True  # 启用推理事件展示
    enable_knowledge: bool = True  # 启用知识库 RAG

    # ---- 本地优先配置 ----
    # 已废弃：IntentAnalyzer 现已内置 Trie 优化，optimized_rules/rules 无区别，保留字段仅为兼容旧配置
    intent_strategy: str = "optimized_rules"  # 废弃字段，不再影响实际行为
    knowledge_strategy: str = "bm25"  # 知识检索策略: bm25 | vector | hybrid
    enable_cloud_fallback: bool = False  # 是否允许云端服务回退

    # ---- 知识库 ----
    knowledge_max_entries: int = 3  # 每次注入最多几个知识条目
    knowledge_max_chars: int = 3000  # 注入总字符数上限
    knowledge_max_tokens: int = 2000  # 知识注入 token 上限
    knowledge_top_k: int = 5  # 向量检索返回的最大条目数
    knowledge_openai_embedding_model: str = "text-embedding-3-small"
    knowledge_local_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    hierarchical_reranker_model: str = "BAAI/bge-reranker-base"

    prompt_component_max_chars: int = 20000
    prompt_total_max_chars: int = 60000
    # ---- Skills 目录配置 ----
    # 主 Skills 目录（Nini 品牌路径）
    skills_dir_path: Path = _get_default_skills_dir()
    # 额外的 Skills 目录（逗号分隔的路径列表）
    skills_extra_dirs: str = ""
    # 自动发现兼容目录（.claude/skills/、.codex/skills/ 等）
    skills_auto_discover_compat_dirs: bool = True

    # ---- 自动上下文压缩 ----
    auto_compress_enabled: bool = True
    auto_compress_threshold_tokens: int = 30000
    auto_compress_target_tokens: int = 15000

    # ---- Deep Task 可观测性 ----
    deep_task_budget_token_limit: int = 12000
    deep_task_budget_cost_limit_usd: float = 2.0
    deep_task_budget_tool_call_limit: int = 24
    deep_task_external_retry_limit: int = 2
    deep_task_external_timeout_seconds: int = 90

    # ---- Memory 优化 ----
    memory_large_payload_threshold_bytes: int = 10 * 1024  # 10 KB，超过此大小的数据引用化
    memory_auto_compress: bool = True
    memory_compress_threshold_kb: int = 500  # 已废弃，由 memory_compress_threshold_tokens 替代
    memory_compress_threshold_tokens: int = 8000  # 基于 Token 数的触发阈值（CJK 感知）
    memory_keep_recent_messages: int = 6  # 压缩时最少保留的近期消息数（约 3 轮对话）
    compressed_context_max_chars: int = 3000  # 压缩上下文字符硬截断兜底（轻量路径）
    compressed_context_max_segments: int = 3  # 压缩摘要段数上限，超出后触发丢弃或 LLM 合并

    # ---- SQLite 会话存储 ----
    session_db_filename: str = "session.db"  # 每个会话目录下的 SQLite 文件名

    # ---- 派生属性 ----
    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def logs_dir(self) -> Path:
        if self.log_dir_path:
            return Path(self.log_dir_path).expanduser()
        return self.data_dir / "logs"

    @property
    def log_file_path(self) -> Path:
        return self.logs_dir / self.log_file_name

    @property
    def effective_log_level(self) -> str:
        return str(self.log_level or ("DEBUG" if self.debug else "INFO")).upper()

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "nini.db"

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge"

    @property
    def prompt_components_dir(self) -> Path:
        return self.data_dir / "prompt_components"

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

        if not IS_FROZEN and self.skills_auto_discover_compat_dirs:
            # 行业标准兼容目录（按优先级）
            _append(_ROOT / ".codex" / "skills")
            _append(_ROOT / ".claude" / "skills")
            _append(_ROOT / ".opencode" / "skills")
            _append(_ROOT / ".agents" / "skills")

        # 用户技能目录优先，便于覆盖内置技能。
        _append(self.skills_dir)

        # 安装包内置技能目录。
        for builtin_dir in _get_bundle_skill_dirs():
            _append(builtin_dir)

        # 用户显式追加目录（最低优先）
        for raw in self.skills_extra_dirs.split(","):
            candidate = raw.strip()
            if not candidate:
                continue
            _append(Path(candidate))

        return dirs

    @property
    def skills_snapshot_path(self) -> Path:
        return self.data_dir / "SKILLS_SNAPSHOT.md"

    @property
    def skills_state_path(self) -> Path:
        """技能管理状态文件（如启用/禁用覆盖）。"""
        return self.data_dir / "skills_state.json"

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip() for ext in self.allowed_extensions.split(",")]

    @property
    def profiles_dir(self) -> Path:
        """用户画像存储目录。"""
        return self.data_dir / "profiles"

    @property
    def recipes_dir(self) -> Path:
        """Recipe 配置目录。"""
        return _get_bundle_recipes_dir()

    def ensure_dirs(self) -> None:
        """集中创建所有必要目录。在模块加载时及 data_dir 变更后调用。"""
        for d in (
            self.data_dir,
            self.logs_dir,
            self.upload_dir,
            self.sessions_dir,
            self.db_path.parent,  # data/db/
            self.knowledge_dir,
            self.prompt_components_dir,
            self.profiles_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


# 全局单例
settings = Settings()
settings.ensure_dirs()
