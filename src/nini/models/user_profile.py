"""用户画像数据模型。

持久化用户偏好和分析历史，用于个性化体验。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# 支持的领域
class DomainType(str):
    """研究领域类型。"""

    GENERAL = "general"
    BIOLOGY = "biology"
    MEDICINE = "medicine"
    PSYCHOLOGY = "psychology"
    ECONOMICS = "economics"
    SOCIOLOGY = "sociology"
    ENGINEERING = "engineering"


# 支持的期刊风格
class JournalStyle(str):
    """学术期刊风格。"""

    NATURE = "nature"
    SCIENCE = "science"
    CELL = "cell"
    NEJM = "nejm"
    LANCET = "lancet"
    APA = "apa"
    IEEE = "ieee"


@dataclass
class UserProfile:
    """用户画像数据类。"""

    # 标识
    user_id: str

    # 领域偏好
    domain: str = "general"
    research_interest: str = ""  # 研究兴趣描述

    # 统计偏好
    significance_level: float = 0.05
    preferred_correction: str = "bonferroni"  # 多重比较校正方法
    confidence_interval: float = 0.95

    # 可视化偏好
    journal_style: str = "nature"
    color_palette: str = "default"
    figure_width: int = 800
    figure_height: int = 600
    figure_dpi: int = 300

    # 分析习惯
    auto_check_assumptions: bool = True
    include_effect_size: bool = True
    include_ci: bool = True
    include_power_analysis: bool = False

    # 历史统计
    total_analyses: int = 0
    favorite_tests: list[str] = field(default_factory=list)
    recent_datasets: list[str] = field(default_factory=list)

    # 科研画像扩展
    research_domains: list[str] = field(default_factory=list)  # 多领域标签
    preferred_methods: dict[str, float] = field(default_factory=dict)  # 方法偏好权重
    output_language: str = "zh"  # 输出语言偏好
    report_detail_level: str = "standard"  # brief / standard / detailed
    typical_sample_size: str = ""  # 常见样本量范围描述
    research_notes: str = ""  # 用户自定义研究备注

    # 时间戳
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # 内部计数器（用于追踪使用频率）
    _test_usage_counter: dict[str, int] = field(default_factory=dict, repr=False, compare=False)

    def increment_analysis_count(self) -> None:
        """增加分析计数。"""
        self.total_analyses += 1
        self.updated_at = datetime.now(timezone.utc)

    def record_test_usage(self, test_method: str) -> None:
        """记录检验方法使用。"""
        # 更新内部计数器
        self._test_usage_counter[test_method] = self._test_usage_counter.get(test_method, 0) + 1

        # 按使用频率排序更新 favorite_tests
        self.favorite_tests = [
            test for test, _ in Counter(self._test_usage_counter).most_common(10)
        ]

        # 同步更新方法偏好权重（归一化）
        total = sum(self._test_usage_counter.values())
        if total > 0:
            self.preferred_methods = {
                method: count / total
                for method, count in Counter(self._test_usage_counter).most_common(10)
            }

        self.updated_at = datetime.now(timezone.utc)

    def add_recent_dataset(self, dataset_name: str, max_count: int = 10) -> None:
        """添加最近使用的数据集。"""
        # 移除已存在的相同名称
        if dataset_name in self.recent_datasets:
            self.recent_datasets.remove(dataset_name)
        # 添加到开头
        self.recent_datasets.insert(0, dataset_name)
        # 保持最大数量
        if len(self.recent_datasets) > max_count:
            self.recent_datasets = self.recent_datasets[:max_count]
        self.updated_at = datetime.now(timezone.utc)

    def update_preference(
        self,
        domain: str | None = None,
        journal_style: str | None = None,
        significance_level: float | None = None,
    ) -> None:
        """更新用户偏好。"""
        if domain is not None:
            self.domain = domain
        if journal_style is not None:
            self.journal_style = journal_style
        if significance_level is not None:
            self.significance_level = significance_level
        self.updated_at = datetime.now(timezone.utc)

    def add_research_domain(self, domain: str, max_count: int = 5) -> None:
        """添加研究领域标签。"""
        if domain not in self.research_domains:
            self.research_domains.append(domain)
            if len(self.research_domains) > max_count:
                self.research_domains = self.research_domains[-max_count:]
            self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "user_id": self.user_id,
            "domain": self.domain,
            "research_interest": self.research_interest,
            "significance_level": self.significance_level,
            "preferred_correction": self.preferred_correction,
            "confidence_interval": self.confidence_interval,
            "journal_style": self.journal_style,
            "color_palette": self.color_palette,
            "figure_width": self.figure_width,
            "figure_height": self.figure_height,
            "figure_dpi": self.figure_dpi,
            "auto_check_assumptions": self.auto_check_assumptions,
            "include_effect_size": self.include_effect_size,
            "include_ci": self.include_ci,
            "include_power_analysis": self.include_power_analysis,
            "total_analyses": self.total_analyses,
            "favorite_tests": self.favorite_tests,
            "recent_datasets": self.recent_datasets,
            "research_domains": self.research_domains,
            "preferred_methods": self.preferred_methods,
            "output_language": self.output_language,
            "report_detail_level": self.report_detail_level,
            "typical_sample_size": self.typical_sample_size,
            "research_notes": self.research_notes,
            "test_usage_counter": dict(self._test_usage_counter),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        """从字典创建实例。"""
        # 处理时间戳
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")

        if isinstance(created_at, str):
            from datetime import datetime, timezone

            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if isinstance(updated_at, str):
            from datetime import datetime, timezone

            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))

        return cls(
            user_id=data["user_id"],
            domain=data.get("domain", "general"),
            research_interest=data.get("research_interest", ""),
            significance_level=data.get("significance_level", 0.05),
            preferred_correction=data.get("preferred_correction", "bonferroni"),
            confidence_interval=data.get("confidence_interval", 0.95),
            journal_style=data.get("journal_style", "nature"),
            color_palette=data.get("color_palette", "default"),
            figure_width=data.get("figure_width", 800),
            figure_height=data.get("figure_height", 600),
            figure_dpi=data.get("figure_dpi", 300),
            auto_check_assumptions=data.get("auto_check_assumptions", True),
            include_effect_size=data.get("include_effect_size", True),
            include_ci=data.get("include_ci", True),
            include_power_analysis=data.get("include_power_analysis", False),
            total_analyses=data.get("total_analyses", 0),
            favorite_tests=data.get("favorite_tests", []),
            recent_datasets=data.get("recent_datasets", []),
            research_domains=data.get("research_domains", []),
            preferred_methods=data.get("preferred_methods", {}),
            output_language=data.get("output_language", "zh"),
            report_detail_level=data.get("report_detail_level", "standard"),
            typical_sample_size=data.get("typical_sample_size", ""),
            research_notes=data.get("research_notes", ""),
            _test_usage_counter=data.get("test_usage_counter", {}),
            created_at=created_at or datetime.now(timezone.utc),
            updated_at=updated_at or datetime.now(timezone.utc),
        )
