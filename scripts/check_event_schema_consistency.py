#!/usr/bin/env python3
"""
检查前后端 WebSocket 事件数据契约一致性。

用法:
    python scripts/check_event_schema_consistency.py

返回:
    0 - 契约一致
    1 - 发现不一致

此脚本验证后端 Pydantic 模型与前端的 TypeScript 类型是否一致，
防止因字段不匹配导致的功能异常。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 后端模型文件
BACKEND_SCHEMA_FILE = PROJECT_ROOT / "src/nini/models/event_schemas.py"

# 前端类型文件
FRONTEND_TYPE_FILES = [
    PROJECT_ROOT / "web/src/store/types.ts",
    PROJECT_ROOT / "web/src/types/analysis.ts",
]


def parse_python_model_fields(file_path: Path) -> dict[str, set[str]]:
    """解析 Python 文件中的 Pydantic 模型字段。"""
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content)

    models: dict[str, set[str]] = {}
    current_model: str | None = None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # 检查是否继承自 BaseModel
            is_basemodel = any(
                isinstance(base, ast.Name) and base.id == "BaseModel"
                for base in node.bases
            )
            if is_basemodel or node.name.endswith("Data"):
                current_model = node.name
                models[current_model] = set()

                # 解析类中的字段
                for item in node.body:
                    if isinstance(item, ast.AnnAssign):
                        if isinstance(item.target, ast.Name):
                            models[current_model].add(item.target.id)

    return models


def parse_typescript_interface_fields(file_path: Path) -> dict[str, set[str]]:
    """解析 TypeScript 文件中的接口字段。"""
    content = file_path.read_text(encoding="utf-8")

    interfaces: dict[str, set[str]] = {}

    # 匹配接口定义
    interface_pattern = r"export\s+interface\s+(\w+)\s*\{([^}]+)\}"
    field_pattern = r"(\w+)(\?)?:\s*[^;]+;"

    for match in re.finditer(interface_pattern, content, re.DOTALL):
        interface_name = match.group(1)
        interface_body = match.group(2)

        fields: set[str] = set()
        for field_match in re.finditer(field_pattern, interface_body):
            field_name = field_match.group(1)
            # 排除注释和特殊字段
            if not field_name.startswith("//") and not field_name.startswith("*"):
                fields.add(field_name)

        interfaces[interface_name] = fields

    return interfaces


def check_analysis_step_consistency(
    backend_models: dict[str, set[str]],
    frontend_interfaces: dict[str, set[str]],
) -> list[str]:
    """检查 AnalysisStep / AnalysisPlanStep 的字段一致性。"""
    errors: list[str] = []

    # 后端模型名
    backend_model_name = "AnalysisPlanStep"
    # 前端接口名
    frontend_interface_name = "AnalysisStep"

    backend_fields = backend_models.get(backend_model_name, set())
    frontend_fields = frontend_interfaces.get(frontend_interface_name, set())

    if not backend_fields:
        errors.append(f"错误：后端模型 {backend_model_name} 未找到")
        return errors

    if not frontend_fields:
        errors.append(f"错误：前端接口 {frontend_interface_name} 未找到")
        return errors

    # 检查关键字段
    critical_fields = ["id", "title", "status", "action_id", "tool_hint"]

    for field in critical_fields:
        has_backend = field in backend_fields
        has_frontend = field in frontend_fields

        if has_backend and not has_frontend:
            errors.append(
                f"不一致：字段 '{field}' 在后端 {backend_model_name} 中存在，"
                f"但在前端 {frontend_interface_name} 中缺失"
            )
        elif has_frontend and not has_backend:
            errors.append(
                f"警告：字段 '{field}' 在前端 {frontend_interface_name} 中存在，"
                f"但在后端 {backend_model_name} 中缺失"
            )

    return errors


def main() -> int:
    """主函数。"""
    print("=" * 60)
    print("WebSocket 事件数据契约一致性检查")
    print("=" * 60)

    # 解析后端模型
    print(f"\n[1/3] 解析后端模型: {BACKEND_SCHEMA_FILE.relative_to(PROJECT_ROOT)}")
    if not BACKEND_SCHEMA_FILE.exists():
        print(f"错误：文件不存在 - {BACKEND_SCHEMA_FILE}")
        return 1

    backend_models = parse_python_model_fields(BACKEND_SCHEMA_FILE)
    print(f"发现 {len(backend_models)} 个模型:")
    for name in sorted(backend_models.keys()):
        print(f"  - {name}: {len(backend_models[name])} 个字段")

    # 解析前端类型
    print(f"\n[2/3] 解析前端类型文件")
    frontend_interfaces: dict[str, set[str]] = {}
    for file_path in FRONTEND_TYPE_FILES:
        if file_path.exists():
            interfaces = parse_typescript_interface_fields(file_path)
            frontend_interfaces.update(interfaces)
            print(f"  - {file_path.relative_to(PROJECT_ROOT)}: {len(interfaces)} 个接口")

    print(f"\n发现 {len(frontend_interfaces)} 个接口:")
    for name in sorted(frontend_interfaces.keys()):
        print(f"  - {name}: {len(frontend_interfaces[name])} 个字段")

    # 检查一致性
    print(f"\n[3/3] 检查契约一致性")
    print("-" * 60)

    errors = check_analysis_step_consistency(backend_models, frontend_interfaces)

    if errors:
        print("发现不一致：")
        for error in errors:
            print(f"  ❌ {error}")
        print("-" * 60)
        print("结果：失败 - 请修复上述不一致后再提交代码")
        return 1
    else:
        print("  ✅ AnalysisStep / AnalysisPlanStep 字段一致")
        print("-" * 60)
        print("结果：通过 - 前后端数据契约一致")
        return 0


if __name__ == "__main__":
    sys.exit(main())
