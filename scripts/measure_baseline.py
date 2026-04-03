"""测量当前 Nini 配置下的 prompt token 开销。

用法：python scripts/measure_baseline.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def measure():
    # 延迟导入，确保路径正确
    from nini.config import settings
    from nini.agent.prompts.builder import PromptBuilder, PromptProfile

    # 使用 tiktoken 估算 token 数（中文场景）
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model("gpt-4")
    except Exception:
        # tiktoken 不可用时，用字符数 / 4 近似
        enc = None

    def count_tokens(text: str) -> int:
        if enc:
            return len(enc.encode(text))
        return len(text) // 4  # 粗略估算

    # ---- 1. System Prompt Token 开销 ----
    builder = PromptBuilder(context_window=None)  # full profile
    prompt = builder.build(intent_hints={"chart", "stat_test"})
    prompt_tokens = count_tokens(prompt)
    prompt_chars = len(prompt)

    # ---- 2. 工具 Schema Token 开销 ----
    try:
        from nini.tools.registry import create_default_tool_registry
        registry = create_default_tool_registry()
        tool_defs = registry.get_tool_definitions()
        # 工具定义通常是 list[dict]，转成字符串估算
        import json
        tool_text = json.dumps(tool_defs, ensure_ascii=False)
        tool_tokens = count_tokens(tool_text)
        tool_count = len(tool_defs)
    except Exception as e:
        tool_tokens = 0
        tool_count = 0
        print(f"警告: 工具 schema 测量失败: {e}")

    # ---- 3. 运行时上下文预算 ----
    from nini.agent.prompt_policy import get_runtime_context_budget

    full_budget = get_runtime_context_budget("full")
    standard_budget = get_runtime_context_budget("standard")
    compact_budget = get_runtime_context_budget("compact")

    # ---- 4. 测试通过率和耗时 ----
    import subprocess
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    duration = time.time() - t0

    # 解析测试结果
    test_line = ""
    for line in result.stdout.strip().split("\n"):
        if "passed" in line or "failed" in line:
            test_line = line
            break

    test_passed = 0
    test_failed = 0
    test_total = 0
    import re
    m = re.search(r"(\d+) passed", test_line)
    if m:
        test_passed = int(m.group(1))
    m = re.search(r"(\d+) failed", test_line)
    if m:
        test_failed = int(m.group(1))
    m = re.search(r"(\d+) total", test_line)
    if m:
        test_total = int(m.group(1))

    # ---- 输出结果 ----
    print(f"prompt_tokens: {prompt_tokens}")
    print(f"prompt_chars: {prompt_chars}")
    print(f"tool_schema_tokens: {tool_tokens}")
    print(f"tool_count: {tool_count}")
    print(f"runtime_budget_chars_full: {full_budget}")
    print(f"runtime_budget_chars_standard: {standard_budget}")
    print(f"runtime_budget_chars_compact: {compact_budget}")
    print(f"test_passed: {test_passed}")
    print(f"test_failed: {test_failed}")
    print(f"test_duration_sec: {duration:.1f}")


if __name__ == "__main__":
    measure()
