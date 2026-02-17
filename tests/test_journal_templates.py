"""期刊模板外部化功能测试。

测试范围：
1. YAML 文件加载
2. 内置模板（6种期刊）
3. 用户自定义模板 CRUD
4. 热重载功能
5. 向后兼容性
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from nini.tools.templates.journal_styles import (
    TEMPLATES,
    _DEFAULT_TEMPLATES,
    _ensure_templates_loaded,
    delete_custom_template,
    get_template,
    get_template_info,
    get_template_names,
    get_templates,
    reload_templates,
    save_custom_template,
)


class TestBuiltinTemplates:
    """测试内置期刊模板。"""

    def test_all_builtin_templates_exist(self):
        """测试所有6种内置模板都存在。"""
        expected_templates = ["default", "nature", "science", "cell", "nejm", "lancet"]
        names = get_template_names()

        for template in expected_templates:
            assert template in names, f"缺少内置模板: {template}"

    def test_default_template_structure(self):
        """测试默认模板的结构完整性。"""
        template = get_template("default")

        assert template["name"] == "默认模板"
        assert "font" in template
        assert "font_size" in template
        assert "line_width" in template
        assert "dpi" in template
        assert "figure_size" in template
        assert "colors" in template
        assert isinstance(template["colors"], list)
        assert len(template["colors"]) > 0

    def test_nature_template_colors(self):
        """测试 Nature 模板的颜色配置。"""
        template = get_template("nature")

        assert template["name"] == "Nature"
        assert template["font_size"] == 11
        assert template["dpi"] == 300
        expected_colors = ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4"]
        assert template["colors"] == expected_colors

    def test_science_template_colors(self):
        """测试 Science 模板的颜色配置。"""
        template = get_template("science")

        assert template["name"] == "Science"
        expected_colors = ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B"]
        assert template["colors"] == expected_colors

    def test_cell_template_structure(self):
        """测试 Cell 模板的结构。"""
        template = get_template("cell")

        assert template["name"] == "Cell"
        assert template["font_size"] == 11
        assert template["line_width"] == 1.0

    def test_nejm_template_structure(self):
        """测试 NEJM 模板的结构。"""
        template = get_template("nejm")

        assert template["name"] == "NEJM"
        assert template["font_size"] == 10

    def test_lancet_template_structure(self):
        """测试 Lancet 模板的结构。"""
        template = get_template("lancet")

        assert template["name"] == "Lancet"
        assert template["font_size"] == 10

    def test_case_insensitive_lookup(self):
        """测试模板名称大小写不敏感。"""
        assert get_template("NATURE") == get_template("nature")
        assert get_template("Nature") == get_template("nature")
        assert get_template("  nature  ") == get_template("nature")

    def test_nonexistent_template_fallback(self):
        """测试不存在模板时回退到 default。"""
        result = get_template("nonexistent_journal")
        default = get_template("default")

        assert result == default


class TestYAMLLoading:
    """测试 YAML 文件加载功能。"""

    def test_yaml_templates_loaded(self):
        """测试 YAML 文件被正确加载。"""
        reload_templates()
        templates = get_templates()

        # 确认从 YAML 加载了模板
        assert "nature" in templates
        assert "science" in templates
        assert templates["nature"]["name"] == "Nature"

    def test_template_metadata_from_yaml(self):
        """测试从 YAML 加载的元数据。"""
        info = get_template_info("nature")

        assert info is not None
        assert info["key"] == "nature"
        assert "metadata" in info
        assert info["is_builtin"] is True


class TestCustomTemplates:
    """测试用户自定义模板功能。"""

    def test_save_custom_template(self, tmp_path, monkeypatch):
        """测试保存自定义模板。"""
        # 使用临时目录作为用户模板目录
        import nini.tools.templates.journal_styles as js

        monkeypatch.setattr(js, "_USER_TEMPLATES_DIR", tmp_path)
        monkeypatch.setattr(js, "_TEMPLATES_CACHE", None)

        config = {
            "name": "我的自定义模板",
            "font": "Arial",
            "font_size": 14,
            "line_width": 2.0,
            "dpi": 600,
            "figure_size": [8.0, 6.0],
            "colors": ["#FF0000", "#00FF00", "#0000FF"],
        }

        result = save_custom_template("my_custom", config)
        assert result is True

        # 验证文件已创建
        template_file = tmp_path / "my_custom.yaml"
        assert template_file.exists()

        # 验证可以加载
        template = get_template("my_custom")
        assert template["name"] == "我的自定义模板"
        assert template["font_size"] == 14

    def test_delete_custom_template(self, tmp_path, monkeypatch):
        """测试删除自定义模板。"""
        import nini.tools.templates.journal_styles as js

        monkeypatch.setattr(js, "_USER_TEMPLATES_DIR", tmp_path)
        monkeypatch.setattr(js, "_TEMPLATES_CACHE", None)

        # 先创建一个模板
        config = {"name": "待删除模板", "font_size": 12}
        save_custom_template("to_delete", config)

        # 删除
        result = delete_custom_template("to_delete")
        assert result is True

        # 验证文件已删除
        assert not (tmp_path / "to_delete.yaml").exists()

    def test_delete_nonexistent_template(self, tmp_path, monkeypatch):
        """测试删除不存在的模板。"""
        import nini.tools.templates.journal_styles as js

        monkeypatch.setattr(js, "_USER_TEMPLATES_DIR", tmp_path)

        result = delete_custom_template("nonexistent")
        assert result is False

    def test_custom_template_override_builtin(self, tmp_path, monkeypatch):
        """测试用户模板可以覆盖内置模板。"""
        import nini.tools.templates.journal_styles as js

        monkeypatch.setattr(js, "_USER_TEMPLATES_DIR", tmp_path)
        monkeypatch.setattr(js, "_TEMPLATES_CACHE", None)

        # 创建一个覆盖 nature 的自定义模板
        config = {
            "name": "自定义 Nature",
            "font_size": 20,  # 不同的值
            "colors": ["#FFFFFF"],  # 不同的颜色
        }
        save_custom_template("nature", config)

        # 验证被覆盖
        template = get_template("nature")
        assert template["name"] == "自定义 Nature"
        assert template["font_size"] == 20

    def test_get_template_info_custom(self, tmp_path, monkeypatch):
        """测试获取自定义模板的详细信息。"""
        import nini.tools.templates.journal_styles as js

        monkeypatch.setattr(js, "_USER_TEMPLATES_DIR", tmp_path)
        monkeypatch.setattr(js, "_TEMPLATES_CACHE", None)

        config = {"name": "测试模板", "font_size": 13}
        save_custom_template("test_info", config)

        info = get_template_info("test_info")
        assert info is not None
        assert info["name"] == "测试模板"
        assert info["font_size"] == 13
        assert info["is_builtin"] is False
        assert info["metadata"]["is_custom"] is True


class TestTemplateReload:
    """测试模板热重载功能。"""

    def test_reload_clears_cache(self, monkeypatch):
        """测试重载清除缓存。"""
        import nini.tools.templates.journal_styles as js

        # 先加载一次
        _ensure_templates_loaded()
        assert js._TEMPLATES_CACHE is not None

        # 重载
        reload_templates()

        # 缓存应该被重置并重新加载
        assert js._TEMPLATES_CACHE is not None
        assert "nature" in js._TEMPLATES_CACHE


class TestBackwardCompatibility:
    """测试向后兼容性。"""

    def test_templates_module_import(self):
        """测试从 templates.py 导入。"""
        from nini.tools import templates

        # 应该可以访问所有主要函数
        assert hasattr(templates, "get_template")
        assert hasattr(templates, "get_templates")
        assert hasattr(templates, "get_template_names")
        assert hasattr(templates, "save_custom_template")
        assert hasattr(templates, "delete_custom_template")
        assert hasattr(templates, "reload_templates")
        assert hasattr(templates, "TEMPLATES")

    def test_templates_package_import(self):
        """测试从 templates 包导入。"""
        from nini.tools import templates

        # 应该可以访问期刊模板函数
        assert hasattr(templates, "get_templates")
        assert hasattr(templates, "get_template_names")
        assert hasattr(templates, "save_custom_template")

    def test_get_template_function(self):
        """测试 get_template 函数兼容性。"""
        from nini.tools.templates import get_template

        # 可以获取期刊模板
        nature = get_template("nature")
        assert isinstance(nature, dict)
        assert nature["name"] == "Nature"

    def test_templates_constant(self):
        """测试 TEMPLATES 常量向后兼容。"""
        from nini.tools.templates import TEMPLATES

        assert isinstance(TEMPLATES, dict)
        assert "default" in TEMPLATES
        assert "nature" in TEMPLATES


class TestTemplateInfo:
    """测试模板信息查询功能。"""

    def test_get_template_info_builtin(self):
        """测试获取内置模板信息。"""
        info = get_template_info("nature")

        assert info is not None
        assert info["key"] == "nature"
        assert info["name"] == "Nature"
        assert "font_size" in info
        assert "dpi" in info
        assert "colors" in info
        assert "metadata" in info
        assert info["is_builtin"] is True

    def test_get_template_info_nonexistent(self):
        """测试获取不存在模板的信息。"""
        info = get_template_info("nonexistent_journal_xyz")

        assert info is None

    def test_all_templates_have_info(self):
        """测试所有模板都有完整信息。"""
        for name in get_template_names():
            info = get_template_info(name)
            assert info is not None, f"模板 {name} 缺少信息"
            assert "key" in info
            assert "name" in info
            assert "colors" in info


class TestFigureSize:
    """测试图表尺寸配置。"""

    def test_default_figure_size(self):
        """测试默认图表尺寸。"""
        template = get_template("default")

        assert template["figure_size"] == [6.4, 4.8]

    def test_journal_figure_size(self):
        """测试期刊模板图表尺寸。"""
        for journal in ["nature", "science", "cell", "nejm", "lancet"]:
            template = get_template(journal)
            # 双栏期刊通常使用 3.54 英寸宽度
            assert template["figure_size"][0] == 3.54
            assert template["figure_size"][1] == 2.76


class TestColors:
    """测试颜色配置。"""

    def test_default_has_10_colors(self):
        """测试默认模板有10种颜色。"""
        template = get_template("default")

        assert len(template["colors"]) == 10

    def test_journals_have_6_colors(self):
        """测试期刊模板有6种颜色。"""
        for journal in ["nature", "science", "cell", "nejm", "lancet"]:
            template = get_template(journal)
            assert len(template["colors"]) == 6, f"{journal} 应该有6种颜色"

    def test_colors_are_valid_hex(self):
        """测试颜色是有效的十六进制格式。"""
        for name in get_template_names():
            template = get_template(name)
            for color in template["colors"]:
                assert color.startswith("#"), f"{name} 的颜色 {color} 不是有效十六进制"
                assert len(color) == 7, f"{name} 的颜色 {color} 长度不正确"
