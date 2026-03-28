/**
 * ResearchProfilePanel - 研究画像配置面板
 *
 * 让用户可以查看和修改研究偏好，完成四层记忆闭环。
 * 通过 Zustand store 管理状态，保证全局一致性。
 *
 * 设计风格：学术工作台 / 科研笔记本
 * 色调：暖象牙色底面 + 深焦炭色标题栏 + 琥珀金点缀
 */

import { useEffect, useState } from "react";
import {
  User,
  BarChart3,
  Palette,
  Save,
  Loader2,
  RefreshCw,
  CheckCircle2,
  BookOpen,
  FlaskConical,
  X,
} from "lucide-react";
import { useStore, type ResearchProfile } from "../store";
import BaseModal from "./BaseModal";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const JOURNAL_STYLES = [
  { value: "nature", label: "Nature", description: "自然科学顶刊风格" },
  { value: "science", label: "Science", description: "综合性科学顶刊风格" },
  { value: "cell", label: "Cell", description: "生命科学顶刊风格" },
  { value: "nejm", label: "NEJM", description: "新英格兰医学杂志" },
  { value: "lancet", label: "Lancet", description: "柳叶刀风格" },
  { value: "apa", label: "APA", description: "美国心理学会风格" },
  { value: "ieee", label: "IEEE", description: "电气电子工程师学会" },
];

const REPORT_DETAIL_LEVELS = [
  { value: "brief", label: "简洁", description: "核心结果" },
  { value: "standard", label: "标准", description: "平衡详尽" },
  { value: "detailed", label: "详细", description: "完整细节" },
];

const DOMAINS = [
  { value: "general", label: "通用", icon: "⚗️" },
  { value: "biology", label: "生物学", icon: "🧬" },
  { value: "medicine", label: "医学", icon: "🏥" },
  { value: "psychology", label: "心理学", icon: "🧠" },
  { value: "economics", label: "经济学", icon: "📈" },
  { value: "sociology", label: "社会学", icon: "👥" },
  { value: "engineering", label: "工程学", icon: "⚙️" },
];

/* ---- 段落颜色标记 ---- */
const SECTION_COLORS = {
  auto: { bg: "bg-teal-50", border: "border-l-teal-400", badge: "bg-teal-100 text-teal-700" },
  agent: {
    bg: "bg-violet-50",
    border: "border-l-violet-400",
    badge: "bg-violet-100 text-violet-700",
  },
  user: {
    bg: "bg-amber-50",
    border: "border-l-amber-400",
    badge: "bg-amber-100 text-amber-700",
  },
};

/* ---- 小标签组件 ---- */
function SectionBadge({
  label,
  color,
}: {
  label: string;
  color: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide ${color}`}
    >
      {label}
    </span>
  );
}

/* ---- 开关控件 ---- */
function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
        checked ? "bg-amber-500" : "bg-stone-200"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export default function ResearchProfilePanel({ isOpen, onClose }: Props) {
  const profile = useStore((s) => s.researchProfile);
  const loading = useStore((s) => s.researchProfileLoading);
  const fetchProfile = useStore((s) => s.fetchResearchProfile);
  const updateProfile = useStore((s) => s.updateResearchProfile);
  const narrative = useStore((s) => s.researchProfileNarrative);
  const narrativeLoading = useStore((s) => s.researchProfileNarrativeLoading);
  const fetchNarrative = useStore((s) => s.fetchResearchProfileNarrative);

  const [draft, setDraft] = useState<ResearchProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [activeTab, setActiveTab] = useState<"basic" | "statistics" | "output" | "journal">(
    "basic",
  );

  useEffect(() => {
    if (isOpen) {
      fetchProfile();
    }
  }, [isOpen, fetchProfile]);

  useEffect(() => {
    if (isOpen && activeTab === "journal") {
      fetchNarrative();
    }
  }, [isOpen, activeTab, fetchNarrative]);

  useEffect(() => {
    if (profile) {
      setDraft({ ...profile });
    }
  }, [profile]);

  const saveHandler = async () => {
    if (!draft) return;
    setSaving(true);
    setSaveSuccess(false);
    setError(null);
    const ok = await updateProfile({
      domain: draft.domain,
      research_interest: draft.research_interest,
      significance_level: draft.significance_level,
      preferred_correction: draft.preferred_correction,
      confidence_interval: draft.confidence_interval,
      journal_style: draft.journal_style,
      color_palette: draft.color_palette,
      figure_width: draft.figure_width,
      figure_height: draft.figure_height,
      figure_dpi: draft.figure_dpi,
      auto_check_assumptions: draft.auto_check_assumptions,
      include_effect_size: draft.include_effect_size,
      include_ci: draft.include_ci,
      include_power_analysis: draft.include_power_analysis,
      research_domains: draft.research_domains,
      output_language: draft.output_language,
      report_detail_level: draft.report_detail_level,
      typical_sample_size: draft.typical_sample_size,
      research_notes: draft.research_notes,
    });
    setSaving(false);
    if (ok) {
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } else {
      setError("保存失败，请重试");
    }
  };

  if (!isOpen) return null;

  const updateField = <K extends keyof ResearchProfile>(field: K, value: ResearchProfile[K]) => {
    setDraft((prev) => (prev ? { ...prev, [field]: value } : null));
  };

  const TABS = [
    { id: "basic" as const, label: "基础信息", icon: User },
    { id: "statistics" as const, label: "统计偏好", icon: BarChart3 },
    { id: "output" as const, label: "输出设置", icon: Palette },
    { id: "journal" as const, label: "研究日志", icon: BookOpen },
  ];

  return (
    <BaseModal open={isOpen} onClose={onClose} title="研究画像" maxWidthClass="max-w-xl">
      <div
        className="flex max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl shadow-2xl bg-amber-50/80 border border-amber-200/60"
      >
        {/* ---- 标题栏 ---- */}
        <div
          className="relative flex flex-shrink-0 items-center gap-4 px-6 py-4 bg-gradient-to-br from-stone-900 to-stone-800"
        >
          {/* 右上角关闭 */}
          <button
            onClick={onClose}
            className="absolute right-4 top-4 rounded-lg p-1.5 text-stone-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            <X size={16} />
          </button>

          <div
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber-600/20"
          >
            <FlaskConical size={20} className="text-amber-400" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white tracking-tight">研究画像</h2>
            <p className="text-xs text-stone-400">
              科研偏好 · 输出规范 · 分析日志
            </p>
          </div>

          {/* 成功提示 */}
          {saveSuccess && (
            <div className="ml-auto mr-8 flex items-center gap-1.5 text-xs text-emerald-400">
              <CheckCircle2 size={13} />
              已保存
            </div>
          )}
        </div>

        {/* ---- Tab 导航 ---- */}
        <div
          role="tablist"
          aria-label="研究画像设置"
          className="flex flex-shrink-0 border-b border-amber-200/60 bg-amber-50/50"
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`profile-panel-${tab.id}`}
              id={`profile-tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-all ${
                activeTab === tab.id
                  ? "border-b-2 border-amber-500 text-amber-700 bg-amber-50/80"
                  : "text-stone-500 hover:text-stone-800"
              }`}
            >
              <tab.icon size={14} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* ---- 内容区 ---- */}
        <div
          role="tabpanel"
          aria-labelledby={`profile-tab-${activeTab}`}
          id={`profile-panel-${activeTab}`}
          className="min-h-0 flex-1 overflow-y-auto px-6 py-5"
        >
          {loading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={22} className="animate-spin text-amber-400" />
              <span className="ml-2 text-sm text-stone-500">加载中…</span>
            </div>
          )}

          {error && (
            <div className="mb-4 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          )}

          {draft && !loading && (
            <div className="space-y-5">
              {/* ---- 基础信息 ---- */}
              {activeTab === "basic" && (
                <>
                  <div>
                    <p className="mb-2.5 text-xs font-semibold uppercase tracking-widest text-stone-400">
                      主研究领域
                    </p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      {DOMAINS.map((d) => (
                        <button
                          key={d.value}
                          onClick={() => updateField("domain", d.value)}
                          className={`flex flex-col items-center gap-1 rounded-xl border p-2.5 text-center text-xs font-medium transition-all ${
                            draft.domain === d.value
                              ? "border-amber-400 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200 shadow-sm"
                              : "border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-stone-600 dark:text-slate-400 hover:border-stone-300 dark:hover:border-slate-600 hover:bg-stone-50 dark:hover:bg-slate-700/50"
                          }`}
                        >
                          <span className="text-base leading-none">{d.icon}</span>
                          <span className="leading-tight">{d.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-stone-400">
                      研究兴趣
                    </label>
                    <textarea
                      value={draft.research_interest}
                      onChange={(e) => updateField("research_interest", e.target.value)}
                      placeholder="例：植物根系发育的分子机制…"
                      className="w-full rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-stone-700 dark:text-slate-300 placeholder-stone-300 dark:placeholder-slate-600 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
                      rows={3}
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-stone-400">
                      典型样本量
                    </label>
                    <input
                      type="text"
                      value={draft.typical_sample_size}
                      onChange={(e) => updateField("typical_sample_size", e.target.value)}
                      placeholder="例：每组 30–50 个样本"
                      className="w-full rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-stone-700 dark:text-slate-300 placeholder-stone-300 dark:placeholder-slate-600 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-stone-400">
                      研究备注
                    </label>
                    <textarea
                      value={draft.research_notes}
                      onChange={(e) => updateField("research_notes", e.target.value)}
                      placeholder="其他偏好或约束条件…"
                      className="w-full rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-stone-700 dark:text-slate-300 placeholder-stone-300 dark:placeholder-slate-600 focus:border-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
                      rows={2}
                    />
                  </div>
                </>
              )}

              {/* ---- 统计偏好 ---- */}
              {activeTab === "statistics" && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-stone-400">
                        显著性水平 α
                      </label>
                      <select
                        value={draft.significance_level}
                        onChange={(e) =>
                          updateField("significance_level", parseFloat(e.target.value))
                        }
                        className="w-full rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-stone-700 dark:text-slate-300 focus:border-amber-400 focus:outline-none"
                      >
                        <option value={0.01}>0.01（更严格）</option>
                        <option value={0.05}>0.05（标准）</option>
                        <option value={0.1}>0.10（较宽松）</option>
                      </select>
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-stone-400">
                        置信区间
                      </label>
                      <select
                        value={draft.confidence_interval}
                        onChange={(e) =>
                          updateField("confidence_interval", parseFloat(e.target.value))
                        }
                        className="w-full rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-stone-700 dark:text-slate-300 focus:border-amber-400 focus:outline-none"
                      >
                        <option value={0.9}>90%</option>
                        <option value={0.95}>95%</option>
                        <option value={0.99}>99%</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-stone-400">
                      多重比较校正
                    </label>
                    <select
                      value={draft.preferred_correction}
                      onChange={(e) => updateField("preferred_correction", e.target.value)}
                      className="w-full rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-stone-700 dark:text-slate-300 focus:border-amber-400 focus:outline-none"
                    >
                      <option value="bonferroni">Bonferroni（保守）</option>
                      <option value="fdr">FDR（较宽松）</option>
                      <option value="none">不校正</option>
                    </select>
                  </div>

                  <div className="space-y-2">
                    <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-stone-400">
                      分析选项
                    </p>
                    {[
                      {
                        key: "auto_check_assumptions" as const,
                        label: "自动前提检验",
                        desc: "正态性、方差齐性等统计前提",
                      },
                      {
                        key: "include_effect_size" as const,
                        label: "包含效应量",
                        desc: "Cohen's d、η² 等效应量指标",
                      },
                      {
                        key: "include_ci" as const,
                        label: "包含置信区间",
                        desc: "结果中报告置信区间范围",
                      },
                      {
                        key: "include_power_analysis" as const,
                        label: "包含功效分析",
                        desc: "统计功效和样本量需求",
                      },
                    ].map((item) => (
                      <div
                        key={item.key}
                        className="flex items-center gap-3 rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3"
                      >
                        <ToggleSwitch
                          checked={draft[item.key]}
                          onChange={(v) => updateField(item.key, v)}
                        />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-stone-700 dark:text-slate-300">{item.label}</p>
                          <p className="text-xs text-stone-400 dark:text-slate-500">{item.desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* ---- 输出设置 ---- */}
              {activeTab === "output" && (
                <>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-stone-400">
                      期刊风格
                    </p>
                    <div className="space-y-1.5">
                      {JOURNAL_STYLES.map((style) => (
                        <label
                          key={style.value}
                          className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-all ${
                            draft.journal_style === style.value
                              ? "border-amber-400 bg-amber-50 dark:bg-amber-900/20"
                              : "border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-stone-300 dark:hover:border-slate-600 hover:bg-stone-50 dark:hover:bg-slate-700/50"
                          }`}
                        >
                          <input
                            type="radio"
                            name="journal_style"
                            value={style.value}
                            checked={draft.journal_style === style.value}
                            onChange={(e) => updateField("journal_style", e.target.value)}
                            className="h-3.5 w-3.5 border-stone-300 text-amber-500 focus:ring-amber-400"
                          />
                          <div className="flex flex-1 items-center justify-between">
                            <span className="text-sm font-semibold text-stone-700">
                              {style.label}
                            </span>
                            <span className="text-xs text-stone-400">{style.description}</span>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-stone-400">
                      报告详细程度
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                      {REPORT_DETAIL_LEVELS.map((level) => (
                        <button
                          key={level.value}
                          onClick={() => updateField("report_detail_level", level.value)}
                          className={`rounded-xl border px-3 py-3 text-center transition-all ${
                            draft.report_detail_level === level.value
                              ? "border-amber-400 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200"
                              : "border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-stone-600 dark:text-slate-400 hover:border-stone-300 dark:hover:border-slate-600"
                          }`}
                        >
                          <p className="text-sm font-semibold">{level.label}</p>
                          <p className="mt-0.5 text-[10px] text-stone-400">{level.description}</p>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    {[
                      {
                        key: "figure_width" as const,
                        label: "图表宽度 (in)",
                      },
                      {
                        key: "figure_height" as const,
                        label: "图表高度 (in)",
                      },
                      { key: "figure_dpi" as const, label: "DPI" },
                    ].map((f) => (
                      <div key={f.key}>
                        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-stone-400">
                          {f.label}
                        </label>
                        <input
                          type="number"
                          value={draft[f.key]}
                          onChange={(e) =>
                            updateField(f.key, parseInt(e.target.value) as ResearchProfile[typeof f.key])
                          }
                          className="w-full rounded-xl border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm font-mono text-stone-700 dark:text-slate-300 focus:border-amber-400 focus:outline-none"
                        />
                      </div>
                    ))}
                  </div>

                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-stone-400">
                      输出语言
                    </p>
                    <div className="flex gap-2">
                      {[
                        { value: "zh", label: "中文" },
                        { value: "en", label: "English" },
                      ].map((lang) => (
                        <button
                          key={lang.value}
                          onClick={() => updateField("output_language", lang.value)}
                          className={`rounded-xl border px-5 py-2 text-sm font-medium transition-all ${
                            draft.output_language === lang.value
                              ? "border-amber-400 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200"
                              : "border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-stone-600 dark:text-slate-400 hover:border-stone-300 dark:hover:border-slate-600"
                          }`}
                        >
                          {lang.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* ---- 研究日志 ---- */}
              {activeTab === "journal" && (
                <div className="space-y-4">
                  {narrativeLoading && (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 size={20} className="animate-spin text-amber-400" />
                      <span className="ml-2 text-sm text-stone-500">加载研究日志…</span>
                    </div>
                  )}

                  {!narrativeLoading && !narrative && (
                    <div
                      className="rounded-2xl border-2 border-dashed p-10 text-center border-amber-300/50 bg-amber-50/80"
                    >
                      <BookOpen size={32} className="mx-auto mb-3 text-stone-400 dark:text-stone-500" />
                      <p className="text-sm font-medium text-stone-500">研究日志尚未生成</p>
                      <p className="mt-1 text-xs text-stone-400">
                        保存研究画像后自动生成，Agent 分析时会追加观察
                      </p>
                    </div>
                  )}

                  {!narrativeLoading && narrative && (
                    <div className="space-y-4">
                      {/* 研究偏好摘要 */}
                      {narrative.sections.auto && (
                        <div
                          className={`rounded-xl border-l-4 p-4 ${SECTION_COLORS.auto.bg} ${SECTION_COLORS.auto.border}`}
                          style={{ borderTopRightRadius: "0.75rem", borderBottomRightRadius: "0.75rem", borderTopLeftRadius: "0", borderBottomLeftRadius: "0" }}
                        >
                          <div className="mb-2 flex items-center gap-2">
                            <span className="text-xs font-semibold text-stone-600">
                              研究偏好摘要
                            </span>
                            <SectionBadge
                              label="系统维护"
                              color={SECTION_COLORS.auto.badge}
                            />
                          </div>
                          <p className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-stone-600">
                            {narrative.sections.auto}
                          </p>
                        </div>
                      )}

                      {/* Agent 观察记录 */}
                      {narrative.sections.agent ? (
                        <div
                          className={`rounded-xl border-l-4 p-4 ${SECTION_COLORS.agent.bg} ${SECTION_COLORS.agent.border}`}
                        >
                          <div className="mb-2 flex items-center gap-2">
                            <span className="text-xs font-semibold text-stone-600">
                              分析习惯与观察
                            </span>
                            <SectionBadge
                              label="Agent 记录"
                              color={SECTION_COLORS.agent.badge}
                            />
                          </div>
                          <p className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-stone-600">
                            {narrative.sections.agent}
                          </p>
                        </div>
                      ) : (
                        <div
                          className={`rounded-xl border-l-4 border-dashed p-4 ${SECTION_COLORS.agent.bg} ${SECTION_COLORS.agent.border}`}
                          style={{ borderLeftStyle: "dashed" }}
                        >
                          <div className="mb-1 flex items-center gap-2">
                            <span className="text-xs font-semibold text-stone-500">
                              分析习惯与观察
                            </span>
                            <SectionBadge
                              label="Agent 记录"
                              color={SECTION_COLORS.agent.badge}
                            />
                          </div>
                          <p className="text-xs italic text-stone-400">
                            尚未记录——分析过程中将自动追加
                          </p>
                        </div>
                      )}

                      {/* 用户备注 */}
                      {narrative.sections.user && (
                        <div
                          className={`rounded-xl border-l-4 p-4 ${SECTION_COLORS.user.bg} ${SECTION_COLORS.user.border}`}
                        >
                          <div className="mb-2 flex items-center gap-2">
                            <span className="text-xs font-semibold text-stone-600">备注</span>
                            <SectionBadge
                              label="可在基础信息中编辑"
                              color={SECTION_COLORS.user.badge}
                            />
                          </div>
                          <p className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-stone-600">
                            {narrative.sections.user}
                          </p>
                        </div>
                      )}

                      <p className="text-center text-[10px] text-stone-400">
                        研究日志由系统自动维护 · 如需修改偏好请在其他标签页编辑后保存
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ---- 底部操作栏 ---- */}
        <div
          className="flex flex-shrink-0 items-center justify-between border-t border-amber-200/60 bg-amber-50/50 px-6 py-3"
        >
          <button
            onClick={() => {
              if (activeTab === "journal") {
                fetchNarrative();
              } else {
                fetchProfile();
              }
            }}
            disabled={loading || narrativeLoading}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-stone-500 dark:text-slate-400 transition-colors hover:bg-stone-100 hover:text-stone-700 disabled:opacity-40"

          >
            <RefreshCw
              size={12}
              className={loading || narrativeLoading ? "animate-spin" : ""}
            />
            刷新
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="rounded-lg px-4 py-1.5 text-sm text-stone-500 dark:text-slate-400 transition-colors hover:bg-stone-100 dark:hover:bg-slate-700"
            >
              关闭
            </button>
            {activeTab !== "journal" && (
              <button
                onClick={saveHandler}
                disabled={saving || !draft}
                className="flex items-center gap-2 rounded-lg px-4 py-1.5 text-sm font-semibold text-white transition-colors bg-amber-700 hover:bg-amber-800 disabled:bg-amber-600 disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Save size={13} />
                )}
                保存设置
              </button>
            )}
          </div>
        </div>
      </div>
    </BaseModal>
  );
}
