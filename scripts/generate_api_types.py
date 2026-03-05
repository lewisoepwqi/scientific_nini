#!/usr/bin/env python3
"""
从后端 OpenAPI 规范生成前端 TypeScript 类型定义。

用法:
    python scripts/generate_api_types.py

此脚本：
1. 提取后端的 Pydantic 模型（通过 FastAPI 的 OpenAPI）
2. 生成对应的 TypeScript 类型定义
3. 输出到 web/src/types/generated/

需要安装: pip install datamodel-code-generator
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 输出目录
OUTPUT_DIR = PROJECT_ROOT / "web/src/types/generated"


def generate_openapi_spec() -> dict:
    """生成 OpenAPI 规范。"""
    import os

    os.chdir(PROJECT_ROOT)

    # 动态导入应用（避免需要在脚本中安装所有依赖）
    try:
        from nini.app import create_app

        app = create_app()
        return app.openapi()
    except ImportError as e:
        print(f"错误：无法导入应用 - {e}")
        print("提示：请在虚拟环境中运行此脚本")
        sys.exit(1)


def generate_typescript_types(openapi_spec: dict) -> str:
    """使用 datamodel-code-generator 生成 TypeScript 类型。"""
    # 创建临时文件存储 OpenAPI 规范
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(openapi_spec, f, ensure_ascii=False, indent=2)
        spec_path = f.name

    try:
        # 确保输出目录存在
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # 使用 datamodel-code-generator 生成 TypeScript
        # 这个工具可以将 JSON Schema 转换为 TypeScript 接口
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "datamodel_code_generator",
                "--input",
                spec_path,
                "--input-file-type",
                "openapi",
                "--output-model-type",
                "pydantic.BaseModel",
                "--target-python-version",
                "3.12",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )

        if result.returncode != 0:
            print(f"警告：datamodel-code-generator 失败 - {result.stderr}")
            return ""

        return result.stdout

    finally:
        # 清理临时文件
        Path(spec_path).unlink(missing_ok=True)


def generate_typescript_from_schemas(openapi_spec: dict) -> str:
    """手动从 OpenAPI schemas 生成 TypeScript 类型（简化版）。"""
    schemas = openapi_spec.get("components", {}).get("schemas", {})

    lines = [
        "/**",
        " * 从后端 OpenAPI 规范自动生成的 TypeScript 类型",
        " *",
        " * 生成时间：自动生成，请勿手动修改",
        " * 修改源：更新后端 Pydantic 模型后重新运行 generate_api_types.py",
        " */",
        "",
    ]

    # 按字母顺序排序 schema
    for schema_name in sorted(schemas.keys()):
        schema = schemas[schema_name]

        # 跳过内部模型
        if schema_name.startswith("Body_") or schema_name in ["HTTPValidationError"]:
            continue

        ts_interface = convert_schema_to_typescript(schema_name, schema)
        if ts_interface:
            lines.extend(ts_interface)
            lines.append("")

    return "\n".join(lines)


def convert_schema_to_typescript(name: str, schema: dict) -> list[str] | None:
    """将单个 JSON Schema 转换为 TypeScript 接口。"""
    schema_type = schema.get("type")

    if schema_type != "object":
        return None

    lines = [f"/** {schema.get('title', name)} */", f"export interface {name} {{"]

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for prop_name in sorted(properties.keys()):
        prop = properties[prop_name]
        ts_type = json_schema_type_to_typescript(prop)
        is_required = prop_name in required

        # 生成 JSDoc 注释
        description = prop.get("description", "")
        if description:
            lines.append(f"  /** {description} */")

        # 生成属性定义
        optional = "" if is_required else "?"
        lines.append(f"  {prop_name}{optional}: {ts_type};")

    lines.append("}")
    return lines


def json_schema_type_to_typescript(prop: dict) -> str:
    """将 JSON Schema 类型转换为 TypeScript 类型。"""
    prop_type = prop.get("type")

    # 处理 $ref 引用
    if "$ref" in prop:
        ref = prop["$ref"]
        # 提取引用名称
        if "#/components/schemas/" in ref:
            return ref.split("/")[-1]
        return "any"

    # 处理 anyOf/oneOf
    if "anyOf" in prop or "oneOf" in prop:
        variants = prop.get("anyOf") or prop.get("oneOf") or []
        types = [json_schema_type_to_typescript(v) for v in variants]
        # 过滤 null 并去重
        non_null_types = [t for t in types if t != "null"]
        if "null" in types:
            return " | ".join(set(non_null_types)) + " | null" if non_null_types else "null"
        return " | ".join(set(non_null_types))

    # 处理数组
    if prop_type == "array":
        items = prop.get("items", {})
        item_type = json_schema_type_to_typescript(items)
        return f"{item_type}[]"

    # 处理对象（递归）
    if prop_type == "object":
        # 如果有 properties，生成内联接口
        if "properties" in prop:
            props = []
            for key, val in prop["properties"].items():
                val_type = json_schema_type_to_typescript(val)
                props.append(f"{key}: {val_type}")
            return "{ " + "; ".join(props) + " }"
        return "Record<string, any>"

    # 基本类型映射
    type_mapping = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }

    # 处理多类型（如 ["string", "null"]）
    if isinstance(prop_type, list):
        types = [type_mapping.get(t, "any") for t in prop_type]
        return " | ".join(types)

    return type_mapping.get(prop_type, "any")


def main() -> int:
    """主函数。"""
    print("=" * 60)
    print("生成前端 TypeScript 类型定义")
    print("=" * 60)

    # 生成 OpenAPI 规范
    print("\n[1/3] 生成 OpenAPI 规范...")
    openapi_spec = generate_openapi_spec()
    print(f"  ✓ 发现 {len(openapi_spec.get('paths', {}))} 个路径")
    schemas = openapi_spec.get("components", {}).get("schemas", {})
    print(f"  ✓ 发现 {len(schemas)} 个 schema")

    # 生成 TypeScript 类型
    print("\n[2/3] 生成 TypeScript 类型...")
    ts_content = generate_typescript_from_schemas(openapi_spec)

    # 写入文件
    print("\n[3/3] 写入类型定义文件...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / "api.ts"
    output_file.write_text(ts_content, encoding="utf-8")
    print(f"  ✓ 已生成: {output_file.relative_to(PROJECT_ROOT)}")

    # 统计信息
    interface_count = ts_content.count("export interface")
    print(f"\n统计：")
    print(f"  - 生成接口: {interface_count} 个")
    print(f"  - 文件大小: {len(ts_content)} 字符")

    print("\n" + "=" * 60)
    print("完成！请将生成的类型导入到项目中使用。")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
