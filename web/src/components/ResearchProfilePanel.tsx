/**
 * ResearchProfilePanel - 研究画像配置面板
 *
 * 让用户可以查看和修改研究偏好，完成四层记忆闭环。
 * 通过 Zustand store 管理状态，保证全局一致性。
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
} from "lucide-react";
import { useStore, type ResearchProfile } from "../store";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const JOURNAL_STYLES = [
  { value: "nature", label: "Nature", description: "自然科学顶刊风格" },
  { value: "science", label: "Science", description: "综合性科学顶刊风格" },
  { value: "cell", label: "Cell", description: "生命科学顶刊风格" },
  { value: "nejm", label: "NEJM", description: "新英格兰医学杂志风格" },
  { value: "lancet", label: "Lancet", description: "柳叶刀风格" },
  { value: "apa", label: "APA", description: "美国心理学会风格" },
  { value: "ieee", label: "IEEE", description: "电气电子工程师学会风格" },
];

const REPORT_DETAIL_LEVELS = [
  { value: "brief", label: "简洁", description: "仅包含核心结果" },
  { value: "standard", label: "标准", description: "平衡详细程度" },
  { value: "detailed", label: "详细", description: "包含完整分析细节" },
];

const DOMAINS = [
  { value: "general", label: "通用", icon: "🔬" },
  { value: "biology", label: "生物学", icon: "🧬" },
  { value: "medicine", label: "医学", icon: "🏥" },
  { value: "psychology", label: "心理学", icon: "🧠" },
  { value: "economics", label: "经济学", icon: "📊" },
  { value: "sociology", label: "社会学", icon: "👥" },
  { value: "engineering", label: "工程学", icon: "⚙️" },
];

export default function ResearchProfilePanel({ isOpen, onClose }: Props) {
  const profile = useStore((s) => s.researchProfile);
  const loading = useStore((s) => s.researchProfileLoading);
  const fetchProfile = useStore((s) => s.fetchResearchProfile);
  const updateProfile = useStore((s) => s.updateResearchProfile);
  const narrative = useStore((s) => s.researchProfileNarrative);
  const narrativeLoading = useStore((s) => s.researchProfileNarrativeLoading);
  const fetchNarrative = useStore((s) => s.fetchResearchProfileNarrative);

  // 本地编辑副本，保存前不影响全局状态
  const [draft, setDraft] = useState<ResearchProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [activeTab, setActiveTab] = useState<"basic" | "statistics" | "output" | "journal">(
    "basic",
  );

  // 面板打开时加载画像，切换到研究日志 Tab 时加载叙述层
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

  // 当 store 数据更新时，同步到本地副本
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
      setTimeout(() => setSaveSuccess(false), 2000);
    } else {
      setError("保存失败，请重试");
    }
  };

  if (!isOpen) return null;

  const updateField = <K extends keyof ResearchProfile>(
    field: K,
    value: ResearchProfile[K]
  ) => {
    setDraft((prev) => (prev ? { ...prev, [field]: value } : null));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-gradient-to-r from-slate-900 to-slate-800 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-white">
              <User size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">研究画像</h2>
              <p className="text-xs text-slate-400">配置您的研究偏好和输出风格</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-200 bg-slate-50/50">
          {[
            { id: "basic" as const, label: "基础信息", icon: User },
            { id: "statistics" as const, label: "统计偏好", icon: BarChart3 },
            { id: "output" as const, label: "输出设置", icon: Palette },
            { id: "journal" as const, label: "研究日志", icon: BookOpen },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-1 items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? "border-b-2 border-sky-500 text-sky-600"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <tab.icon size={16} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="max-h-[60vh] overflow-y-auto p-6">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={24} className="animate-spin text-slate-400" />
              <span className="ml-2 text-slate-600">加载中...</span>
            </div>
          )}

          {error && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {draft && !loading && (
            <div className="space-y-6">
              {/* 基础信息 Tab */}
              {activeTab === "basic" && (
                <>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      研究领域
                    </label>
                    <div className="grid grid-cols-4 gap-2">
                      {DOMAINS.map((d) => (
                        <button
                          key={d.value}
                          onClick={() => updateField("domain", d.value)}
                          className={`flex flex-col items-center gap-1 rounded-xl border p-3 text-xs transition-all ${
                            draft.domain === d.value
                              ? "border-sky-500 bg-sky-50 text-sky-700"
                              : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          <span className="text-lg">{d.icon}</span>
                          <span>{d.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      研究兴趣描述
                    </label>
                    <textarea
                      value={draft.research_interest}
                      onChange={(e) => updateField("research_interest", e.target.value)}
                      placeholder="例如：植物根系发育的分子机制研究..."
                      className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
                      rows={3}
                    />
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      典型样本量
                    </label>
                    <input
                      type="text"
                      value={draft.typical_sample_size}
                      onChange={(e) => updateField("typical_sample_size", e.target.value)}
                      placeholder="例如：每组 30-50 个样本"
                      className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
                    />
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      研究备注
                    </label>
                    <textarea
                      value={draft.research_notes}
                      onChange={(e) => updateField("research_notes", e.target.value)}
                      placeholder="其他需要记录的研究偏好..."
                      className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
                      rows={2}
                    />
                  </div>
                </>
              )}

              {/* 统计偏好 Tab */}
              {activeTab === "statistics" && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        显著性水平 (α)
                      </label>
                      <select
                        value={draft.significance_level}
                        onChange={(e) =>
                          updateField("significance_level", parseFloat(e.target.value))
                        }
                        className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none"
                      >
                        <option value={0.01}>0.01 (更严格)</option>
                        <option value={0.05}>0.05 (标准)</option>
                        <option value={0.10}>0.10 (较宽松)</option>
                      </select>
                    </div>

                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        置信区间
                      </label>
                      <select
                        value={draft.confidence_interval}
                        onChange={(e) =>
                          updateField("confidence_interval", parseFloat(e.target.value))
                        }
                        className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none"
                      >
                        <option value={0.90}>90%</option>
                        <option value={0.95}>95%</option>
                        <option value={0.99}>99%</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      多重比较校正方法
                    </label>
                    <select
                      value={draft.preferred_correction}
                      onChange={(e) => updateField("preferred_correction", e.target.value)}
                      className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none"
                    >
                      <option value="bonferroni">Bonferroni (保守)</option>
                      <option value="fdr">FDR (较宽松)</option>
                      <option value="none">不进行校正</option>
                    </select>
                  </div>

                  <div className="space-y-3">
                    <label className="block text-sm font-medium text-slate-700">分析选项</label>
                    {[
                      {
                        key: "auto_check_assumptions" as const,
                        label: "自动前提检验",
                        desc: "自动检查正态性、方差齐性等统计前提",
                      },
                      {
                        key: "include_effect_size" as const,
                        label: "包含效应量",
                        desc: "报告中包含 Cohen's d、η² 等效应量指标",
                      },
                      {
                        key: "include_ci" as const,
                        label: "包含置信区间",
                        desc: "结果中报告置信区间范围",
                      },
                      {
                        key: "include_power_analysis" as const,
                        label: "包含功效分析",
                        desc: "分析统计功效和样本量需求",
                      },
                    ].map((item) => (
                      <label
                        key={item.key}
                        className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3 transition-colors hover:bg-slate-50"
                      >
                        <input
                          type="checkbox"
                          checked={draft[item.key]}
                          onChange={(e) => updateField(item.key, e.target.checked)}
                          className="mt-0.5 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                        />
                        <div>
                          <div className="text-sm font-medium text-slate-700">{item.label}</div>
                          <div className="text-xs text-slate-500">{item.desc}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </>
              )}

              {/* 研究日志 Tab */}
              {activeTab === "journal" && (
                <div className="space-y-4">
                  {narrativeLoading && (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 size={20} className="animate-spin text-slate-400" />
                      <span className="ml-2 text-sm text-slate-500">加载研究日志...</span>
                    </div>
                  )}

                  {!narrativeLoading && !narrative && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center">
                      <BookOpen size={32} className="mx-auto mb-2 text-slate-300" />
                      <p className="text-sm text-slate-500">暂无研究日志</p>
                      <p className="mt-1 text-xs text-slate-400">
                        保存研究画像后将自动生成，Agent 分析时会追加观察记录
                      </p>
                    </div>
                  )}

                  {!narrativeLoading && narrative && (
                    <>
                      {/* 研究偏好摘要（系统生成，只读） */}
                      {narrative.sections.auto && (
                        <div>
                          <div className="mb-1.5 flex items-center gap-1.5">
                            <span className="text-xs font-semibold text-slate-600">
                              研究偏好摘要
                            </span>
                            <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] text-sky-600">
                              系统维护
                            </span>
                          </div>
                          <pre className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">
                            {narrative.sections.auto}
                          </pre>
                        </div>
                      )}

                      {/* 分析习惯与观察（Agent 写入，只读） */}
                      {narrative.sections.agent ? (
                        <div>
                          <div className="mb-1.5 flex items-center gap-1.5">
                            <span className="text-xs font-semibold text-slate-600">
                              分析习惯与观察
                            </span>
                            <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] text-violet-600">
                              Agent 记录
                            </span>
                          </div>
                          <pre className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">
                            {narrative.sections.agent}
                          </pre>
                        </div>
                      ) : (
                        <div className="rounded-xl border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400">
                          Agent 尚未记录分析习惯，分析过程中会自动追加
                        </div>
                      )}

                      {/* 备注（对应 research_notes，跳转到基础信息编辑） */}
                      {narrative.sections.user && (
                        <div>
                          <div className="mb-1.5 flex items-center gap-1.5">
                            <span className="text-xs font-semibold text-slate-600">备注</span>
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-600">
                              可在基础信息中编辑
                            </span>
                          </div>
                          <pre className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">
                            {narrative.sections.user}
                          </pre>
                        </div>
                      )}

                      <p className="text-center text-[10px] text-slate-400">
                        研究日志由系统自动维护，如需修改偏好请在其他标签页编辑后保存
                      </p>
                    </>
                  )}
                </div>
              )}

              {/* 输出设置 Tab */}
              {activeTab === "output" && (
                <>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      期刊风格
                    </label>
                    <div className="space-y-2">
                      {JOURNAL_STYLES.map((style) => (
                        <label
                          key={style.value}
                          className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-all ${
                            draft.journal_style === style.value
                              ? "border-sky-500 bg-sky-50"
                              : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          <input
                            type="radio"
                            name="journal_style"
                            value={style.value}
                            checked={draft.journal_style === style.value}
                            onChange={(e) => updateField("journal_style", e.target.value)}
                            className="h-4 w-4 border-slate-300 text-sky-600 focus:ring-sky-500"
                          />
                          <div className="flex-1">
                            <div className="text-sm font-medium text-slate-700">
                              {style.label}
                            </div>
                            <div className="text-xs text-slate-500">{style.description}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      报告详细程度
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      {REPORT_DETAIL_LEVELS.map((level) => (
                        <button
                          key={level.value}
                          onClick={() => updateField("report_detail_level", level.value)}
                          className={`rounded-xl border p-3 text-center text-sm transition-all ${
                            draft.report_detail_level === level.value
                              ? "border-sky-500 bg-sky-50 text-sky-700"
                              : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          <div className="font-medium">{level.label}</div>
                          <div className="mt-1 text-[10px] text-slate-500">{level.description}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        图表宽度
                      </label>
                      <input
                        type="number"
                        value={draft.figure_width}
                        onChange={(e) =>
                          updateField("figure_width", parseInt(e.target.value))
                        }
                        className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        图表高度
                      </label>
                      <input
                        type="number"
                        value={draft.figure_height}
                        onChange={(e) =>
                          updateField("figure_height", parseInt(e.target.value))
                        }
                        className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700">
                        DPI
                      </label>
                      <input
                        type="number"
                        value={draft.figure_dpi}
                        onChange={(e) => updateField("figure_dpi", parseInt(e.target.value))}
                        className="w-full rounded-xl border border-slate-200 p-3 text-sm focus:border-sky-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">
                      输出语言
                    </label>
                    <div className="flex gap-2">
                      {[
                        { value: "zh", label: "中文" },
                        { value: "en", label: "English" },
                      ].map((lang) => (
                        <button
                          key={lang.value}
                          onClick={() => updateField("output_language", lang.value)}
                          className={`rounded-lg border px-4 py-2 text-sm transition-all ${
                            draft.output_language === lang.value
                              ? "border-sky-500 bg-sky-50 text-sky-700"
                              : "border-slate-200 hover:border-slate-300"
                          }`}
                        >
                          {lang.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50/50 px-6 py-4">
          <button
            onClick={() => {
              if (activeTab === "journal") {
                fetchNarrative();
              } else {
                fetchProfile();
              }
            }}
            disabled={loading || narrativeLoading}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
          >
            <RefreshCw
              size={14}
              className={loading || narrativeLoading ? "animate-spin" : ""}
            />
            刷新
          </button>

          <div className="flex items-center gap-3">
            {saveSuccess && (
              <div className="flex items-center gap-1 text-sm text-green-600">
                <CheckCircle2 size={14} />
                已保存
              </div>
            )}
            <button
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100"
            >
              取消
            </button>
            <button
              onClick={saveHandler}
              disabled={saving || !draft}
              className="flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              {saving ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Save size={14} />
              )}
              保存设置
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
