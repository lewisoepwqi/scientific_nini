#!/usr/bin/env python3
"""验证 Memory 优化功能的简单脚本。

不依赖 pytest，可以直接运行。
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nini.config import settings
from nini.memory.conversation import ConversationMemory


def test_large_payload_reference():
    """测试大型数据引用化。"""
    print("=" * 60)
    print("测试 1: 大型数据引用化")
    print("=" * 60)

    # 使用临时目录
    session_id = "verify_test"
    test_dir = project_root / "data" / "sessions"
    settings.sessions_dir = test_dir

    memory = ConversationMemory(session_id)

    # 创建一个大型数据（超过 10KB）
    large_data = {
        "type": "chart",
        "data": [{"x": list(range(1000)), "y": list(range(1000))} for _ in range(10)],
        "layout": {"title": "Big Chart" * 100},
    }

    entry = {
        "role": "assistant",
        "content": "测试大数据引用化",
        "chart_data": large_data,
    }

    print(f"原始数据大小: {len(json.dumps(large_data))} 字节")

    # 保存
    memory.append(entry)
    print("✓ 数据已保存")

    # 读取（不解析引用）
    loaded = memory.load_all(resolve_refs=False)
    assert len(loaded) == 1

    # 检查是否被引用化
    chart_field = loaded[0]["chart_data"]
    if isinstance(chart_field, dict) and "_ref" in chart_field:
        print(f"✓ 大型数据已引用化: {chart_field['_ref']}")
        print(f"  - 原始大小: {chart_field['_size_bytes']} 字节")

        # 验证引用文件存在
        ref_path = chart_field["_ref"]
        payload_file = test_dir / session_id / ref_path
        assert payload_file.exists(), f"引用文件不存在: {payload_file}"
        print(f"✓ 引用文件存在: {payload_file.relative_to(project_root)}")

        # 验证引用文件内容
        payload_data = json.loads(payload_file.read_text())
        assert payload_data == large_data
        print("✓ 引用文件内容正确")
    else:
        print("✗ 大型数据未被引用化（数据可能不够大）")
        return False

    # 测试引用解析
    loaded_resolved = memory.load_all(resolve_refs=True)
    assert loaded_resolved[0]["chart_data"] == large_data
    print("✓ 引用解析成功")

    # 清理
    memory.clear()
    print("✓ 测试完成\n")
    return True


def test_small_payload_not_referenced():
    """测试小型数据不会被引用化。"""
    print("=" * 60)
    print("测试 2: 小型数据不引用化")
    print("=" * 60)

    session_id = "verify_test_small"
    test_dir = project_root / "data" / "sessions"
    settings.sessions_dir = test_dir

    memory = ConversationMemory(session_id)

    # 创建小型数据
    small_data = {"x": [1, 2, 3], "y": [4, 5, 6]}

    entry = {
        "role": "assistant",
        "content": "测试小数据",
        "chart_data": small_data,
    }

    print(f"数据大小: {len(json.dumps(small_data))} 字节")

    # 保存
    memory.append(entry)
    print("✓ 数据已保存")

    # 读取
    loaded = memory.load_all()
    assert len(loaded) == 1

    # 检查是否未被引用化
    chart_field = loaded[0]["chart_data"]
    if isinstance(chart_field, dict) and "_ref" not in str(chart_field):
        print("✓ 小型数据未被引用化（直接保存在 JSONL 中）")
    else:
        print("✗ 小型数据被错误地引用化了")
        return False

    # 清理
    memory.clear()
    print("✓ 测试完成\n")
    return True


def test_config_parameters():
    """测试配置参数是否正确添加。"""
    print("=" * 60)
    print("测试 3: 配置参数")
    print("=" * 60)

    # 检查新增的配置参数
    assert hasattr(settings, "memory_large_payload_threshold_bytes")
    print(
        f"✓ memory_large_payload_threshold_bytes = {settings.memory_large_payload_threshold_bytes}"
    )

    assert hasattr(settings, "memory_auto_compress")
    print(f"✓ memory_auto_compress = {settings.memory_auto_compress}")

    assert hasattr(settings, "memory_compress_threshold_kb")
    print(f"✓ memory_compress_threshold_kb = {settings.memory_compress_threshold_kb}")

    assert hasattr(settings, "memory_keep_recent_messages")
    print(f"✓ memory_keep_recent_messages = {settings.memory_keep_recent_messages}")

    print("✓ 所有配置参数正确\n")
    return True


def main():
    """运行所有验证测试。"""
    print("\n" + "=" * 60)
    print("Memory 优化功能验证")
    print("=" * 60 + "\n")

    results = []

    try:
        results.append(("配置参数", test_config_parameters()))
    except Exception as e:
        print(f"✗ 配置参数测试失败: {e}\n")
        results.append(("配置参数", False))

    try:
        results.append(("大型数据引用化", test_large_payload_reference()))
    except Exception as e:
        print(f"✗ 大型数据引用化测试失败: {e}\n")
        results.append(("大型数据引用化", False))

    try:
        results.append(("小型数据不引用化", test_small_payload_not_referenced()))
    except Exception as e:
        print(f"✗ 小型数据不引用化测试失败: {e}\n")
        results.append(("小型数据不引用化", False))

    # 打印总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
