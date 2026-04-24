"""批次完成摘要 —— 跨工具的主动预防层。

背景
----
当 LLM 在同一用户轮内进行多轮 tool_call 调度时，偶发"忘记自己上一轮
已完成的工具调用"的现象，从而重复发起带守卫语义的工具请求（例如
`dataset_catalog(profile, …, full)`），被 DUPLICATE_* 守卫拦截。

反应式守卫是兜底层；本模块提供预防层：
在每一轮 LLM 请求组装前，由 runner 注入一条 system 备注，列出"本轮
已成功完成的带守卫语义工具及其产出量级"，主动告知 LLM 哪些工具
不必再次调用。

与守卫的关系
------------
- **预防**（本模块）：在下一轮请求前主动告知 LLM 批内已完成状态。
- **兜底**（runner DUPLICATE_* 守卫）：LLM 仍然发起重复调用时拦截。

两层互补；不删除守卫。
"""

from __future__ import annotations

from typing import Any, Callable

# summarizer 签名：(parsed_args, tool_result_dict) -> 单行摘要 | None
# 返回 None 表示该次调用无需进入摘要（例如非守卫语义的 operation）。
CompletionSummarizer = Callable[[dict[str, Any], dict[str, Any]], str | None]

# 默认一次注入的最大摘要条数；超出则仅保留最近 N 条。
# 同一批次内工具数通常 ≤ 6，8 留出余量。
MAX_SUMMARY_LINES = 8


def _summarize_dataset_catalog(args: dict[str, Any], result: dict[str, Any]) -> str | None:
    """仅覆盖 `dataset_catalog(profile, …)`。

    list / search / dataframe_preview 等 operation 不进入摘要，因为它们
    没有对应的 DUPLICATE_* 守卫，也不构成"可复用结果"的强语义。
    """
    operation = str(args.get("operation") or "").strip().lower()
    if operation != "profile":
        return None
    dataset_name = args.get("dataset_name")
    if not dataset_name and isinstance(result, dict):
        data_summary = result.get("data_summary")
        if isinstance(data_summary, dict):
            dataset_name = data_summary.get("dataset_name")
    if not isinstance(dataset_name, str) or not dataset_name.strip():
        return None
    view = str(args.get("view") or "summary").strip() or "summary"
    shape_text = "已完成"
    if isinstance(result, dict):
        data_summary = result.get("data_summary")
        if isinstance(data_summary, dict):
            rows = data_summary.get("rows")
            cols = data_summary.get("columns")
            if isinstance(rows, int) and isinstance(cols, int):
                shape_text = f"{rows} 行 × {cols} 列"
    return f"dataset_catalog(profile, {dataset_name}, {view}) — {shape_text}"


# 工具 → summarizer 注册表。未登记的工具不进入摘要。
_SUMMARIZERS: dict[str, CompletionSummarizer] = {
    "dataset_catalog": _summarize_dataset_catalog,
}


def summarize_completion(
    tool_name: str, args: dict[str, Any], result: dict[str, Any]
) -> str | None:
    """对单次成功工具调用生成摘要行；未登记或不适用则返回 None。

    summarizer 内部抛异常一律吞掉并返回 None，保证预防层不影响主流程。
    """
    summarizer = _SUMMARIZERS.get(tool_name)
    if summarizer is None:
        return None
    try:
        return summarizer(args, result)
    except Exception:
        return None


def format_summary_prompt(lines: list[str]) -> str:
    """将摘要行列表格式化为注入到下一轮 LLM 的 system 备注内容。

    空列表返回空字符串（调用方据此决定是否注入）。
    超过 MAX_SUMMARY_LINES 条时仅保留最近 N 条并标注截断。
    """
    if not lines:
        return ""
    truncated = False
    if len(lines) > MAX_SUMMARY_LINES:
        lines = lines[-MAX_SUMMARY_LINES:]
        truncated = True
    header = "【本轮已完成的分析工具（请勿重复调用，直接使用其结果推进下一步）】"
    body = "\n".join(f"- {line}" for line in lines)
    footer = f"\n（仅显示最近 {MAX_SUMMARY_LINES} 条）" if truncated else ""
    return f"{header}\n{body}{footer}"
