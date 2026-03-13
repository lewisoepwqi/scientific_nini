"""用户画像 Markdown 叙述层。

实现 JSON（结构化字段）与 MD（叙述/洞察）的职责分离：
  文件路径：data/profiles/{profile_id}_profile.md

三类段落，操作权限不同：
  SECTION_AUTO   = "研究偏好摘要"   — 系统每次保存 JSON 时覆盖，用户不可直接编辑
  SECTION_AGENT  = "分析习惯与观察" — Agent append-only，超限后归档最旧条目
  SECTION_USER   = "备注"           — 用户自由编辑，与 research_notes 字段双向同步
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nini.config import settings

logger = logging.getLogger(__name__)

# 段落名称常量
SECTION_AUTO = "研究偏好摘要"
SECTION_AGENT = "分析习惯与观察"
SECTION_USER = "备注"
_ALL_SECTIONS = [SECTION_AUTO, SECTION_AGENT, SECTION_USER]

# 配置常量
MAX_AGENT_ENTRIES = 20  # AGENT 段条目上限，超出后触发归档
KEEP_AGENT_ENTRIES = 15  # 归档时保留的最新条目数
CONTEXT_MAX_CHARS = 1400  # 注入 LLM 时的字符上限
AGENT_MAX_CHARS_IN_CONTEXT = 500  # AGENT 段在 context 中的字符上限


class ProfileNarrativeManager:
    """用户画像 Markdown 叙述层管理器。

    负责 {profile_id}_profile.md 文件的读写、段落解析与内容生成。
    """

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self._dir = profiles_dir or settings.profiles_dir

    def _md_path(self, profile_id: str) -> Path:
        """获取叙述层文件路径。"""
        return self._dir / f"{profile_id}_profile.md"

    # ---- 段落解析与重建 ----

    @staticmethod
    def _parse_sections(md: str) -> dict[str, str]:
        """解析 MD 文件，返回各段落内容（不含标题行）。"""
        sections: dict[str, str] = {s: "" for s in _ALL_SECTIONS}
        current: str | None = None
        buf: list[str] = []

        for line in md.splitlines():
            if line.startswith("## "):
                # 保存上一段
                if current is not None and current in sections:
                    sections[current] = "\n".join(buf).strip()
                current = line[3:].strip()
                buf = []
            elif line.startswith("<!-- "):
                # 跳过 HTML 注释行
                continue
            else:
                if current is not None:
                    buf.append(line)

        # 保存最后一段
        if current is not None and current in sections:
            sections[current] = "\n".join(buf).strip()

        return sections

    @staticmethod
    def _build_md(auto_content: str, agent_content: str, user_content: str) -> str:
        """重建完整 MD 文件。"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts: list[str] = [
            f"<!-- _auto_generated: {now} -->",
            "<!-- 研究偏好摘要 由系统维护；分析习惯与观察 由 Agent 追加；备注 可自由编辑 -->",
            "",
            f"## {SECTION_AUTO}",
            auto_content if auto_content else "（暂无数据，请先保存研究画像）",
            "",
            f"## {SECTION_AGENT}",
            agent_content if agent_content else "",
            "",
            f"## {SECTION_USER}",
            user_content if user_content else "",
            "",
        ]
        return "\n".join(parts)

    # ---- AUTO 段内容生成 ----

    @staticmethod
    def generate_auto_content(profile: Any) -> str:
        """从 UserProfile 结构化字段生成'研究偏好摘要'段落。"""
        lines: list[str] = []

        # 研究领域
        domains = list(getattr(profile, "research_domains", None) or [])
        if not domains:
            domain = getattr(profile, "domain", "general")
            if domain and domain != "general":
                domains = [domain]
        if domains:
            lines.append(f"- **研究领域**：{' / '.join(domains)}")

        # 常用方法（来自频率统计）
        preferred: dict[str, float] = dict(getattr(profile, "preferred_methods", None) or {})
        favorite: list[str] = list(getattr(profile, "favorite_tests", None) or [])
        if preferred:
            top = sorted(preferred.items(), key=lambda x: x[1], reverse=True)[:5]
            method_str = "、".join(f"{m}（{w:.0%}）" for m, w in top)
            lines.append(f"- **常用方法**：{method_str}")
        elif favorite:
            lines.append(f"- **常用方法**：{', '.join(favorite[:5])}")

        # 统计参数
        alpha = getattr(profile, "significance_level", 0.05)
        ci = getattr(profile, "confidence_interval", 0.95)
        correction = getattr(profile, "preferred_correction", "bonferroni")
        stat_parts = [f"α = {alpha}", f"置信区间 {ci:.0%}"]
        if correction and correction != "none":
            stat_parts.append(f"{correction} 多重比较校正")
        lines.append(f"- **统计参数**：{', '.join(stat_parts)}")

        # 分析选项
        prefs: list[str] = []
        if getattr(profile, "auto_check_assumptions", True):
            prefs.append("自动前提检验")
        if getattr(profile, "include_effect_size", True):
            prefs.append("效应量")
        if getattr(profile, "include_ci", True):
            prefs.append("置信区间")
        if getattr(profile, "include_power_analysis", False):
            prefs.append("功效分析")
        if prefs:
            lines.append(f"- **分析选项**：{', '.join(prefs)}")

        # 输出风格
        journal = getattr(profile, "journal_style", "nature") or "nature"
        detail = getattr(profile, "report_detail_level", "standard") or "standard"
        lang = getattr(profile, "output_language", "zh") or "zh"
        detail_cn = {"brief": "简洁", "standard": "标准", "detailed": "详细"}.get(detail, detail)
        lang_cn = {"zh": "中文", "en": "英文"}.get(lang, lang)
        lines.append(f"- **输出风格**：{journal} 期刊风格，{detail_cn}报告，{lang_cn}")

        # 典型样本量
        typical = (getattr(profile, "typical_sample_size", "") or "").strip()
        if typical:
            lines.append(f"- **典型样本量**：{typical}")

        # 历史统计
        total = getattr(profile, "total_analyses", 0) or 0
        recent: list[str] = list(getattr(profile, "recent_datasets", None) or [])
        if total > 0:
            hist_parts = [f"累计分析 {total} 次"]
            if recent:
                hist_parts.append(f"最近数据集：{', '.join(recent[:3])}")
            lines.append(f"- **历史记录**：{'，'.join(hist_parts)}")

        # 研究兴趣（单独一行）
        interest = (getattr(profile, "research_interest", "") or "").strip()
        if interest:
            lines.append(f"\n**研究背景**：{interest}")

        return "\n".join(lines)

    # ---- 公开接口 ----

    def regenerate(self, profile_id: str, profile: Any) -> None:
        """从 UserProfile 重新生成 AUTO 段落，保留 AGENT / USER 段落不变。

        USER 段落内容与 research_notes 字段同步（JSON 字段为准）。
        """
        path = self._md_path(profile_id)

        # 读取现有内容，保留 AGENT 和 USER 段落
        existing: dict[str, str] = {s: "" for s in _ALL_SECTIONS}
        if path.exists():
            try:
                existing = self._parse_sections(path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("读取画像叙述层失败，重新初始化: %s", profile_id)

        # USER 段与 research_notes 字段同步（JSON 值覆盖 MD）
        notes = (getattr(profile, "research_notes", "") or "").strip()
        user_content = notes if notes else existing[SECTION_USER]

        auto_content = self.generate_auto_content(profile)
        md = self._build_md(auto_content, existing[SECTION_AGENT], user_content)

        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(md, encoding="utf-8")
            logger.debug("画像叙述层已更新: %s", profile_id)
        except Exception:
            logger.warning("写入画像叙述层失败: %s", profile_id, exc_info=True)

    def append_agent_observation(self, profile_id: str, observation: str) -> bool:
        """追加一条 Agent 分析观察到 AGENT 段落。

        超过 MAX_AGENT_ENTRIES 时，自动保留最新 KEEP_AGENT_ENTRIES 条并归档旧条目。

        Returns:
            是否成功写入
        """
        if not observation or not observation.strip():
            return False

        path = self._md_path(profile_id)
        sections: dict[str, str] = {s: "" for s in _ALL_SECTIONS}
        if path.exists():
            try:
                sections = self._parse_sections(path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("读取画像叙述层失败: %s", profile_id)

        # 构建新条目（带日期戳）
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_entry = f"- [{ts}] {observation.strip()}"

        agent_content = sections[SECTION_AGENT]
        if agent_content:
            entries = [line for line in agent_content.splitlines() if line.strip()]
        else:
            entries = []
        entries.append(new_entry)

        # 超限归档：保留最新 KEEP_AGENT_ENTRIES 条
        if len(entries) > MAX_AGENT_ENTRIES:
            dropped = len(entries) - KEEP_AGENT_ENTRIES
            entries = [f"- （最早 {dropped} 条已归档）"] + entries[-KEEP_AGENT_ENTRIES:]

        sections[SECTION_AGENT] = "\n".join(entries)

        # AUTO 段不存在时用占位符（避免文件格式破损）
        auto_content = sections[SECTION_AUTO] or "（请先保存研究画像以生成摘要）"
        md = self._build_md(auto_content, sections[SECTION_AGENT], sections[SECTION_USER])

        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(md, encoding="utf-8")
            return True
        except Exception:
            logger.warning("写入画像叙述层失败: %s", profile_id, exc_info=True)
            return False

    def update_user_notes(self, profile_id: str, notes: str) -> bool:
        """更新 USER 段落内容（与 research_notes 字段同步调用）。"""
        path = self._md_path(profile_id)
        sections: dict[str, str] = {s: "" for s in _ALL_SECTIONS}
        if path.exists():
            try:
                sections = self._parse_sections(path.read_text(encoding="utf-8"))
            except Exception:
                pass

        sections[SECTION_USER] = notes.strip() if notes else ""
        auto_content = sections[SECTION_AUTO] or "（请先保存研究画像以生成摘要）"
        md = self._build_md(auto_content, sections[SECTION_AGENT], sections[SECTION_USER])

        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(md, encoding="utf-8")
            return True
        except Exception:
            logger.warning("写入画像叙述层失败: %s", profile_id, exc_info=True)
            return False

    def read_narrative(self, profile_id: str) -> str:
        """读取完整 MD 叙述层内容（含注释头）。"""
        path = self._md_path(profile_id)
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            logger.warning("读取画像叙述层失败: %s", profile_id)
            return ""

    def read_sections(self, profile_id: str) -> dict[str, str]:
        """读取各段落内容字典，key 为段落名称。"""
        content = self.read_narrative(profile_id)
        if not content:
            return {s: "" for s in _ALL_SECTIONS}
        return self._parse_sections(content)

    def get_narrative_for_context(
        self,
        profile_id: str,
        *,
        max_chars: int = CONTEXT_MAX_CHARS,
    ) -> str:
        """获取适合注入 LLM 上下文的叙述文本。

        裁剪策略（按优先级）：
        1. AUTO 段完整保留（最高优先）
        2. AGENT 段：从最新条目向前截取，不超过 AGENT_MAX_CHARS_IN_CONTEXT
        3. USER 段：有剩余空间时追加
        最终结果不超过 max_chars。
        """
        sections = self.read_sections(profile_id)
        if not any(sections.values()):
            return ""

        auto_text = sections[SECTION_AUTO]
        agent_text = sections[SECTION_AGENT]
        user_text = sections[SECTION_USER]

        # 裁剪 AGENT 段，防止大量历史条目撑爆 context
        if agent_text and len(agent_text) > AGENT_MAX_CHARS_IN_CONTEXT:
            lines = [line for line in agent_text.splitlines() if line.strip()]
            kept: list[str] = []
            total = 0
            for line in reversed(lines):
                if total + len(line) + 1 > AGENT_MAX_CHARS_IN_CONTEXT:
                    break
                kept.insert(0, line)
                total += len(line) + 1
            agent_text = "\n".join(kept)

        parts: list[str] = []
        if auto_text:
            parts.append(f"## {SECTION_AUTO}\n{auto_text}")
        if agent_text:
            parts.append(f"## {SECTION_AGENT}\n{agent_text}")
        if user_text:
            parts.append(f"## {SECTION_USER}\n{user_text}")

        result = "\n\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n…（更多内容已省略）"

        return result


# ---- 全局单例 ----

_profile_narrative_manager: ProfileNarrativeManager | None = None


def get_profile_narrative_manager() -> ProfileNarrativeManager:
    """获取全局画像叙述层管理器单例。"""
    global _profile_narrative_manager
    if _profile_narrative_manager is None:
        _profile_narrative_manager = ProfileNarrativeManager()
    return _profile_narrative_manager
