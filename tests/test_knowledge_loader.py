"""KnowledgeLoader 单元测试。"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from nini.knowledge.loader import KnowledgeEntry, KnowledgeLoader


@pytest.fixture()
def knowledge_dir(tmp_path: Path) -> Path:
    """创建包含测试知识文件的临时目录。"""
    methods = tmp_path / "methods"
    methods.mkdir()

    # comparison.md — high 优先级
    (methods / "comparison.md").write_text(
        textwrap.dedent("""\
        <!-- keywords: t检验, 比较, 差异, 两组, anova -->
        <!-- priority: high -->
        # 组间比较方法选择指南
        两组比较用 t 检验，多组用 ANOVA。
        """),
        encoding="utf-8",
    )

    # correlation.md — high 优先级
    (methods / "correlation.md").write_text(
        textwrap.dedent("""\
        <!-- keywords: 相关, 回归, pearson, spearman -->
        <!-- priority: high -->
        # 相关与回归
        Pearson 用于正态，Spearman 用于非正态。
        """),
        encoding="utf-8",
    )

    # normality.md — normal 优先级
    (methods / "normality.md").write_text(
        textwrap.dedent("""\
        <!-- keywords: 正态, 分布, shapiro, 非参数 -->
        <!-- priority: normal -->
        # 正态性检查
        用 Shapiro-Wilk 检验正态性。
        """),
        encoding="utf-8",
    )

    pitfalls = tmp_path / "pitfalls"
    pitfalls.mkdir()

    # common_errors.md — low 优先级
    (pitfalls / "common_errors.md").write_text(
        textwrap.dedent("""\
        <!-- keywords: 错误, 误用, 陷阱 -->
        <!-- priority: low -->
        # 常见统计错误
        不要用多次 t 检验代替 ANOVA。
        """),
        encoding="utf-8",
    )

    # README.md — 应被跳过
    (tmp_path / "README.md").write_text("# 说明\n这是说明文件", encoding="utf-8")

    return tmp_path


@pytest.fixture()
def loader(knowledge_dir: Path) -> KnowledgeLoader:
    return KnowledgeLoader(knowledge_dir)


class TestKnowledgeLoaderInit:
    """测试初始化和文件解析。"""

    def test_loads_all_md_files_except_readme(self, loader: KnowledgeLoader) -> None:
        assert len(loader.entries) == 4

    def test_parses_keywords(self, loader: KnowledgeLoader) -> None:
        entry = next(e for e in loader.entries if "comparison" in e.path.name)
        assert "t检验" in entry.keywords
        assert "anova" in entry.keywords

    def test_parses_priority(self, loader: KnowledgeLoader) -> None:
        comparison = next(e for e in loader.entries if "comparison" in e.path.name)
        assert comparison.priority == "high"
        assert comparison.priority_weight == 2

        errors = next(e for e in loader.entries if "common_errors" in e.path.name)
        assert errors.priority == "low"
        assert errors.priority_weight == 0

    def test_strips_html_comments_from_content(self, loader: KnowledgeLoader) -> None:
        entry = next(e for e in loader.entries if "comparison" in e.path.name)
        assert "<!-- keywords" not in entry.content
        assert "<!-- priority" not in entry.content
        assert "组间比较" in entry.content

    def test_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        loader = KnowledgeLoader(empty)
        assert len(loader.entries) == 0

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        loader = KnowledgeLoader(tmp_path / "does_not_exist")
        assert len(loader.entries) == 0


class TestKnowledgeLoaderSelect:
    """测试关键词匹配和选择逻辑。"""

    def test_matches_t_test_keyword(self, loader: KnowledgeLoader) -> None:
        result = loader.select("帮我做 t检验")
        assert "组间比较" in result

    def test_matches_correlation_keyword(self, loader: KnowledgeLoader) -> None:
        result = loader.select("分析变量间的相关性")
        assert "相关与回归" in result

    def test_matches_normality_keyword(self, loader: KnowledgeLoader) -> None:
        result = loader.select("数据不是正态分布怎么办")
        assert "正态性检查" in result

    def test_no_match_returns_empty(self, loader: KnowledgeLoader) -> None:
        result = loader.select("今天天气怎么样")
        assert result == ""

    def test_empty_message_returns_empty(self, loader: KnowledgeLoader) -> None:
        result = loader.select("")
        assert result == ""

    def test_priority_affects_ranking(self, loader: KnowledgeLoader) -> None:
        """high 优先级的条目应排在前面（同样匹配 1 个关键词时）。"""
        # "比较" 命中 comparison(high)，"错误" 命中 common_errors(low)
        result = loader.select("比较分析中的错误")
        # comparison 应排在 errors 前面
        idx_comparison = result.find("组间比较")
        idx_errors = result.find("常见统计错误")
        assert idx_comparison >= 0
        assert idx_errors >= 0
        assert idx_comparison < idx_errors

    def test_max_entries_limit(self, loader: KnowledgeLoader) -> None:
        # 匹配多个关键词的消息
        result = loader.select(
            "t检验 相关 正态 分布 比较 差异 错误",
            max_entries=2,
        )
        # 应最多包含 2 个条目的内容
        matched_titles = sum(
            1
            for title in ["组间比较", "相关与回归", "正态性检查", "常见统计错误"]
            if title in result
        )
        assert matched_titles <= 2

    def test_max_total_chars_limit(self, loader: KnowledgeLoader) -> None:
        result = loader.select(
            "t检验 相关 正态",
            max_total_chars=50,
        )
        # 结果应不超过限制（允许截断标记的额外开销）
        assert len(result) <= 60  # 允许 "..." 的小额溢出

    def test_case_insensitive_matching(self, loader: KnowledgeLoader) -> None:
        result = loader.select("ANOVA 分析")
        assert "组间比较" in result

    def test_multiple_keyword_hits_boost_score(self, loader: KnowledgeLoader) -> None:
        """多个关键词命中应提高排名。"""
        # "t检验 两组 差异 比较" 命中 comparison 的 4 个关键词
        # "相关" 只命中 correlation 的 1 个关键词
        result = loader.select("t检验 两组 差异 比较 相关", max_entries=2)
        idx_comparison = result.find("组间比较")
        idx_correlation = result.find("相关与回归")
        assert idx_comparison >= 0
        assert idx_comparison < idx_correlation


class TestKnowledgeLoaderReload:
    """测试 reload 功能。"""

    def test_reload_picks_up_new_files(self, knowledge_dir: Path) -> None:
        loader = KnowledgeLoader(knowledge_dir)
        assert len(loader.entries) == 4

        # 添加新文件
        (knowledge_dir / "methods" / "new.md").write_text(
            "<!-- keywords: 新方法 -->\n# 新方法\n内容",
            encoding="utf-8",
        )
        loader.reload()
        assert len(loader.entries) == 5
