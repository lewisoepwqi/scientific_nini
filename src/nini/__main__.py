"""命令行入口：`python -m nini` / `nini`。"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
import sys
from typing import Sequence


def _default_env_content() -> str:
    return (
        "# Nini 配置（首次运行建议修改）\n"
        "NINI_DEBUG=false\n"
        "\n"
        "# 可选：OpenAI\n"
        "NINI_OPENAI_API_KEY=\n"
        "NINI_OPENAI_MODEL=gpt-4o\n"
        "\n"
        "# 可选：Anthropic Claude\n"
        "NINI_ANTHROPIC_API_KEY=\n"
        "NINI_ANTHROPIC_MODEL=claude-sonnet-4-20250514\n"
        "\n"
        "# 可选：Ollama（默认启用本地服务）\n"
        "NINI_OLLAMA_BASE_URL=http://localhost:11434\n"
        "NINI_OLLAMA_MODEL=qwen2.5:7b\n"
        "\n"
        "# 可选：Moonshot AI (Kimi)\n"
        "NINI_MOONSHOT_API_KEY=\n"
        "NINI_MOONSHOT_MODEL=moonshot-v1-8k\n"
        "\n"
        "# 可选：Kimi Coding（api.kimi.com）\n"
        "NINI_KIMI_CODING_API_KEY=\n"
        "NINI_KIMI_CODING_BASE_URL=https://api.kimi.com/coding/v1\n"
        "NINI_KIMI_CODING_MODEL=kimi-for-coding\n"
        "\n"
        "# 可选：智谱 AI (GLM) — 默认 Coding Plan 端点\n"
        "NINI_ZHIPU_API_KEY=\n"
        "NINI_ZHIPU_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4\n"
        "NINI_ZHIPU_MODEL=glm-4\n"
        "\n"
        "# 可选：DeepSeek\n"
        "NINI_DEEPSEEK_API_KEY=\n"
        "NINI_DEEPSEEK_MODEL=deepseek-chat\n"
        "\n"
        "# 可选：阿里百炼（通义千问）\n"
        "NINI_DASHSCOPE_API_KEY=\n"
        "NINI_DASHSCOPE_MODEL=qwen-plus\n"
        "\n"
        "# Agent / 沙箱\n"
        "NINI_AGENT_MAX_ITERATIONS=0\n"
        "NINI_SANDBOX_TIMEOUT=30\n"
        "NINI_SANDBOX_MAX_MEMORY_MB=512\n"
        "NINI_SANDBOX_IMAGE_EXPORT_TIMEOUT=60\n"
        "NINI_R_ENABLED=true\n"
        "NINI_R_SANDBOX_TIMEOUT=120\n"
        "NINI_R_SANDBOX_MAX_MEMORY_MB=1024\n"
        "NINI_R_PACKAGE_INSTALL_TIMEOUT=300\n"
        "NINI_R_AUTO_INSTALL_PACKAGES=true\n"
    )


def _render_markdown_skill_template(name: str, description: str, category: str) -> str:
    """渲染 Markdown Skill 脚手架内容。"""
    return f"""---
name: {name}
description: {description}
category: {category}
---

# {name}

{description}

## 适用场景

- 说明该技能适用于哪些问题类型、输入条件与预期输出。
- 如果有前置依赖（数据、工具、权限），在此明确标注。

## 步骤

1. 描述执行前的准备动作（如读取上下文、校验输入）。
2. 描述核心执行流程（调用哪些工具、按何顺序执行）。
3. 描述输出要求（结果格式、产物命名、失败时回退策略）。

## 注意事项

- 明确边界条件和风险点（如大数据集、长耗时、外部依赖失败）。
- 明确不可执行动作或必须人工确认的步骤。
"""


def _detect_kaleido_chrome_status() -> tuple[bool, str]:
    """检测 kaleido 与 Chrome 可用性。"""
    try:
        importlib.import_module("kaleido")
    except ImportError:
        return False, "kaleido 未安装（pip install kaleido）"

    try:
        chromium_module = importlib.import_module("choreographer.browsers.chromium")
    except ImportError as exc:
        return False, f"kaleido 已安装，Chrome 状态未知（{exc}）（运行 `kaleido_get_chrome` 安装）"

    get_browser_path = getattr(chromium_module, "get_browser_path", None)
    chromium_based_browsers = getattr(chromium_module, "chromium_based_browsers", None)
    if not callable(get_browser_path) or chromium_based_browsers is None:
        return (
            False,
            "kaleido 已安装，Chrome 状态未知（choreographer API 不兼容）（运行 `kaleido_get_chrome` 安装）",
        )

    try:
        chrome_path = get_browser_path(chromium_based_browsers)
    except Exception as exc:  # pragma: no cover - 防止环境差异导致 doctor 直接失败
        return (
            False,
            f"kaleido 已安装，Chrome 状态未知（{type(exc).__name__}: {exc}）（运行 `kaleido_get_chrome` 安装）",
        )

    if chrome_path:
        return True, f"Chrome: {chrome_path}"
    return False, "Chrome 未安装（运行 `kaleido_get_chrome` 安装）"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nini - 科研数据分析 AI Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="启动 Nini 服务")
    start_parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    start_parser.add_argument("--port", type=int, default=8000, help="监听端口")
    start_parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    start_parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="日志级别",
    )
    start_parser.set_defaults(func=_cmd_start)

    init_parser = subparsers.add_parser("init", help="生成首次运行配置文件")
    init_parser.add_argument(
        "--env-file",
        default=".env",
        help="配置文件路径，默认当前目录 .env",
    )
    init_parser.add_argument("--force", action="store_true", help="覆盖已存在的配置文件")
    init_parser.set_defaults(func=_cmd_init)

    doctor_parser = subparsers.add_parser("doctor", help="检查运行环境与配置")
    doctor_parser.set_defaults(func=_cmd_doctor)

    export_parser = subparsers.add_parser("export-memory", help="导出会话记忆为格式化 JSON")
    export_parser.add_argument("session_id", help="会话 ID")
    export_parser.add_argument(
        "-o", "--output", type=Path, help="输出文件路径（JSON），默认输出到标准输出"
    )
    export_parser.add_argument(
        "--pretty/--compact",
        dest="pretty",
        action="store_true",
        default=True,
        help="是否格式化输出（默认格式化）",
    )
    export_parser.set_defaults(func=_cmd_export_memory)

    # nini skills 子命令组
    skills_parser = subparsers.add_parser("skills", help="管理技能")
    skills_sub = skills_parser.add_subparsers(dest="skills_command", required=True)

    # nini skills list
    skills_list = skills_sub.add_parser("list", help="列出所有已注册技能")
    skills_list.add_argument(
        "--type",
        choices=["function", "markdown", "all"],
        default="all",
        help="按类型过滤（默认 all）",
    )
    skills_list.add_argument(
        "--category",
        default=None,
        help="按分类过滤，如 statistics / visualization",
    )
    skills_list.add_argument(
        "--format",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="输出格式（默认 table）",
    )
    skills_list.set_defaults(func=_cmd_skills_list)

    # nini skills create
    skills_create = skills_sub.add_parser("create", help="创建技能脚手架")
    skills_create.add_argument("skill_name", help="技能名称（snake_case）")
    skills_create.add_argument(
        "--type",
        dest="skill_type",
        choices=["function", "markdown"],
        default="function",
        help="技能类型（默认 function）",
    )
    skills_create.add_argument(
        "--category",
        default="other",
        help="技能分类（默认 other）",
    )
    skills_create.add_argument(
        "--description",
        default="",
        help="技能描述",
    )
    skills_create.set_defaults(func=_cmd_skills_create)

    # nini skills export
    skills_export = skills_sub.add_parser("export", help="导出技能为指定格式")
    skills_export.add_argument(
        "--format",
        dest="export_format",
        choices=["openai", "mcp", "claude-code"],
        default="mcp",
        help="导出格式（默认 mcp）",
    )
    skills_export.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出文件路径（默认输出到标准输出）",
    )
    skills_export.set_defaults(func=_cmd_skills_export)

    return parser


def _normalize_argv(argv: Sequence[str]) -> list[str]:
    if not argv or argv[0].startswith("-"):
        # 向后兼容：`nini --port 9000` 等价于 `nini start --port 9000`
        return ["start", *argv]
    return list(argv)


def _cmd_start(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("缺少依赖，请先运行: pip install -e .[dev]")
        return 1

    uvicorn.run(
        "nini.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["src"] if args.reload else None,
        log_level=args.log_level,
    )
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    env_path = Path(args.env_file).expanduser().resolve()
    if env_path.exists() and not args.force:
        print(f"配置文件已存在: {env_path}")
        print("如需覆盖请添加 --force")
        return 1

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(_default_env_content(), encoding="utf-8")

    print(f"已生成配置文件: {env_path}")
    print("下一步：")
    print("1) 填写 API Key（或确保本地 Ollama 可用）")
    print("2) 运行 `nini start --reload` 启动服务")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from nini.config import settings
    from nini.sandbox.r_executor import detect_r_installation

    checks: list[tuple[str, bool, str, bool]] = []

    py_ok = sys.version_info >= (3, 12)
    checks.append(
        (
            "Python 版本 >= 3.12",
            py_ok,
            f"当前: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            True,
        )
    )

    data_dir_ok = True
    data_dir_msg = ""
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        data_dir_msg = f"{settings.data_dir}"
    except Exception as exc:
        data_dir_ok = False
        data_dir_msg = str(exc)
    checks.append(("数据目录可写", data_dir_ok, data_dir_msg, True))

    model_ok = bool(
        settings.openai_api_key
        or settings.anthropic_api_key
        or settings.moonshot_api_key
        or settings.kimi_coding_api_key
        or settings.zhipu_api_key
        or settings.deepseek_api_key
        or settings.dashscope_api_key
        or (settings.ollama_base_url and settings.ollama_model)
    )
    # 收集已配置的提供商名称
    configured_providers: list[str] = []
    if settings.openai_api_key:
        configured_providers.append("OpenAI")
    if settings.anthropic_api_key:
        configured_providers.append("Anthropic")
    if settings.moonshot_api_key:
        configured_providers.append("Moonshot")
    if settings.kimi_coding_api_key:
        configured_providers.append("Kimi Coding")
    if settings.zhipu_api_key:
        configured_providers.append("智谱AI")
    if settings.deepseek_api_key:
        configured_providers.append("DeepSeek")
    if settings.dashscope_api_key:
        configured_providers.append("阿里百炼")
    if settings.ollama_base_url and settings.ollama_model:
        configured_providers.append("Ollama")
    model_detail = ", ".join(configured_providers) if configured_providers else "未配置任何模型"
    checks.append(
        (
            "至少一个模型路由可用",
            model_ok,
            model_detail,
            True,
        )
    )

    # kaleido + Chrome 检查（图片导出依赖）
    kaleido_ok, kaleido_msg = _detect_kaleido_chrome_status()
    checks.append(("kaleido + Chrome（图片导出，可选）", kaleido_ok, kaleido_msg, False))

    r_info = detect_r_installation()
    r_ok = bool(r_info.get("available"))
    r_detail = str(r_info.get("version") or r_info.get("message") or "未知")
    if not settings.r_enabled:
        r_detail = "已禁用（NINI_R_ENABLED=false）"
    checks.append(
        ("Rscript（run_r_code，可选）", r_ok if settings.r_enabled else True, r_detail, False)
    )

    web_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    checks.append(("前端构建产物存在（可选）", web_dist.exists(), str(web_dist), False))

    print("Nini 环境检查:")
    failed = 0
    for name, ok, detail, required in checks:
        mark = "OK" if ok else "FAIL"
        if not required and not ok:
            mark = "WARN"
        print(f"- [{mark}] {name}: {detail}")
        if required and not ok:
            failed += 1

    if failed == 0:
        print("检查通过，可以运行 `nini start`。")
        return 0

    print(f"检查完成：{failed} 项失败，请先修复。")
    return 1


def _cmd_export_memory(args: argparse.Namespace) -> int:
    """导出会话记忆为格式化 JSON"""
    import json
    from datetime import datetime, timezone
    from nini.memory.conversation import ConversationMemory, format_memory_entries

    session_id = args.session_id

    try:
        mem = ConversationMemory(session_id)
        entries = mem.load_messages(resolve_refs=False)
        formatted = format_memory_entries(entries)

        result = {
            "session_id": session_id,
            "total_entries": len(entries),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "entries": formatted,
        }

        # 序列化
        indent = 2 if args.pretty else None
        json_str = json.dumps(result, ensure_ascii=False, indent=indent, default=str)

        if args.output:
            args.output.write_text(json_str, encoding="utf-8")
            print(f"✓ 已导出到 {args.output}")
        else:
            print(json_str)

        return 0

    except FileNotFoundError:
        print(f"错误：会话 {session_id} 不存在或无记忆文件")
        return 1
    except Exception as e:
        print(f"错误：{e}")
        return 1


def _cmd_skills_list(args: argparse.Namespace) -> int:
    """列出已注册技能。"""
    from nini.skills.registry import create_default_registry

    registry = create_default_registry()
    skill_type = None if args.type == "all" else args.type
    catalog = registry.list_skill_catalog(skill_type=skill_type)

    if args.category:
        catalog = [s for s in catalog if s.get("category") == args.category]

    if not catalog:
        print("未找到匹配的技能。")
        return 0

    if args.output_format == "json":
        import json

        print(json.dumps(catalog, ensure_ascii=False, indent=2))
        return 0

    # 表格输出：按 category 分组
    from collections import defaultdict

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for s in catalog:
        by_cat[s.get("category", "other")].append(s)

    print(f"共 {len(catalog)} 个技能\n")
    for cat in sorted(by_cat):
        print(f"[{cat}]")
        for s in sorted(by_cat[cat], key=lambda x: x["name"]):
            stype = s.get("type", "?")[0].upper()  # F / M
            enabled = "+" if s.get("enabled", True) else "-"
            print(f"  {enabled} {s['name']:40s} ({stype}) {s.get('description', '')[:50]}")
        print()

    return 0


def _cmd_skills_create(args: argparse.Namespace) -> int:
    """创建技能脚手架文件。"""
    import re

    name = args.skill_name
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        print(f"错误：技能名称 '{name}' 不合法，必须为小写字母开头的 snake_case 格式。")
        return 1

    from nini.skills.markdown_scanner import VALID_CATEGORIES

    if args.category not in VALID_CATEGORIES:
        print(f"错误：分类 '{args.category}' 不在标准分类中：{sorted(VALID_CATEGORIES)}")
        return 1

    description = args.description or f"{name} 技能"

    if args.skill_type == "markdown":
        return _create_markdown_skill(name, description, args.category)
    return _create_function_skill(name, description, args.category)


def _create_function_skill(name: str, description: str, category: str) -> int:
    """创建 Function Skill 脚手架。"""
    # 类名：snake_case → PascalCase + "Skill"
    class_name = "".join(word.capitalize() for word in name.split("_")) + "Skill"
    target = Path(__file__).resolve().parent / "skills" / f"{name}.py"

    if target.exists():
        print(f"错误：文件已存在 {target}")
        return 1

    content = f'''"""技能：{description}"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.skills.base import Skill, SkillResult


class {class_name}(Skill):
    """{description}"""

    @property
    def name(self) -> str:
        return "{name}"

    @property
    def category(self) -> str:
        return "{category}"

    @property
    def description(self) -> str:
        return "{description}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {{
            "type": "object",
            "properties": {{
                # TODO: 定义参数
            }},
            "required": [],
        }}

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        # TODO: 实现技能逻辑
        return SkillResult(success=True, message="{name} 执行完成")
'''
    target.write_text(content, encoding="utf-8")
    print(f"已创建 Function Skill 脚手架：{target}")
    print(f"下一步：")
    print(f"  1. 编辑 {target} 实现 execute() 逻辑")
    print(f"  2. 在 registry.py 的 create_default_registry() 中注册")
    print(f"  3. 添加测试 tests/test_{name}.py")
    return 0


def _create_markdown_skill(name: str, description: str, category: str) -> int:
    """创建 Markdown Skill 脚手架。"""
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    target_dir = skills_dir / name
    target = target_dir / "SKILL.md"

    if target.exists():
        print(f"错误：文件已存在 {target}")
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    content = _render_markdown_skill_template(name, description, category)
    target.write_text(content, encoding="utf-8")
    print(f"已创建 Markdown Skill 脚手架：{target}")
    print(f"下一步：编辑 {target} 完善技能内容")
    return 0


def _cmd_skills_export(args: argparse.Namespace) -> int:
    """导出技能为指定格式。"""
    import json

    from nini.skills.registry import create_default_registry
    from nini.skills.tool_adapter import ToolAdapter

    registry = create_default_registry()
    adapter = ToolAdapter(registry)

    if args.export_format == "openai":
        result = json.dumps(adapter.to_openai_tools(), ensure_ascii=False, indent=2)
    elif args.export_format == "mcp":
        result = json.dumps(adapter.to_mcp_tools(), ensure_ascii=False, indent=2)
    elif args.export_format == "claude-code":
        result = adapter.to_claude_code_markdown()
    else:
        print(f"不支持的格式: {args.export_format}")
        return 1

    if args.output:
        args.output.write_text(result, encoding="utf-8")
        print(f"已导出到 {args.output}")
    else:
        print(result)

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(_normalize_argv(argv or sys.argv[1:]))
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("已中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
