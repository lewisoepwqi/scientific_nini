/**
 * ResearchProfilePage - 研究画像独立页面
 *
 * 全宽卡片式布局，每个配置区域用独立卡片包裹：
 *   1. 基本配置 — 研究领域、兴趣、样本量、备注
 *   2. 统计偏好 — 显著性水平、置信区间、校正方法、分析开关
 *   3. 输出风格 — 期刊风格、报告详细度、图表尺寸、语言
 *   4. 研究日志 — 系统维护的偏好摘要 + Agent 观察 + 用户备注（只读）
 * 底部固定操作栏：重置默认 + 保存更改
 */
import { useEffect, useState } from "react";
import {
  User,
  BarChart3,
  Palette,
  BookOpen,
  Save,
  Loader2,
  RefreshCw,
  CheckCircle2,
  FlaskConical,
  Dna,
  Stethoscope,
  Brain,
  TrendingUp,
  Users,
  Cog,
  RotateCcw,
  Lock,
} from "lucide-react";
import { useStore, type ResearchProfile } from "../../store";
import PageHeader from "./PageHeader";
import { Badge } from "../ui/Badge";
import type { BadgeVariant } from "../ui/Badge";
import Button from "../ui/Button";

// ─── 常量 ───────────────────────────────────────────────────────────────────

const DOMAINS = [
  { value: "general", label: "通用", icon: FlaskConical },
  { value: "biology", label: "生物学", icon: Dna },
  { value: "medicine", label: "医学", icon: Stethoscope },
  { value: "psychology", label: "心理学", icon: Brain },
  { value: "economics", label: "经济学", icon: TrendingUp },
  { value: "sociology", label: "社会学", icon: Users },
  { value: "engineering", label: "工程学", icon: Cog },
];

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

// 研究日志段落颜色
const SECTION_COLORS: Record<string, { border: string; variant: BadgeVariant }> = {
  auto: { border: "border-l-[var(--success)]", variant: "default" },
  agent: { border: "border-l-violet-400", variant: "default" },
  user: { border: "border-l-[var(--accent)]", variant: "default" },
};

// ─── 子组件 ──────────────────────────────────────────────────────────────────

/** iOS 风格开关 */
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
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 ${
        checked ? "bg-[var(--accent)]" : "bg-[var(--bg-overlay)]"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-[var(--bg-base)] shadow transition-transform duration-200 ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

/** 区段卡片头部 */
function CardHeader({
  icon: Icon,
  title,
  badge,
}: {
  icon: typeof User;
  title: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2.5 mb-5">
      <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[var(--accent-subtle)]">
        <Icon size={15} className="text-[var(--accent)]" />
      </div>
      <h2 className="text-sm font-semibold text-[var(--text-primary)] m-0">
        {title}
      </h2>
      {badge}
    </div>
  );
}

/** 表单字段标签 */
function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-1.5 block text-xs font-medium text-[var(--text-muted)]">
      {children}
    </label>
  );
}

/** 研究日志段落小标签 */
function SectionBadge({ label, variant }: { label: string; variant: BadgeVariant }) {
  return <Badge variant={variant}>{label}</Badge>;
}

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  onBack: () => void;
}

// ─── 主组件 ──────────────────────────────────────────────────────────────────

export default function ResearchProfilePage({ onBack }: Props) {
  /* ---- store 状态 ---- */
  const profile = useStore((s) => s.researchProfile);
  const loading = useStore((s) => s.researchProfileLoading);
  const fetchProfile = useStore((s) => s.fetchResearchProfile);
  const updateProfile = useStore((s) => s.updateResearchProfile);
  const narrative = useStore((s) => s.researchProfileNarrative);
  const narrativeLoading = useStore((s) => s.researchProfileNarrativeLoading);
  const fetchNarrative = useStore((s) => s.fetchResearchProfileNarrative);

  /* ---- 本地状态 ---- */
  const [draft, setDraft] = useState<ResearchProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  /* ---- 数据加载 ---- */
  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  useEffect(() => {
    fetchNarrative();
  }, [fetchNarrative]);

  useEffect(() => {
    if (profile) {
      setDraft({ ...profile });
    }
  }, [profile]);

  /* ---- 保存处理 ---- */
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

  /* ---- 重置默认值 ---- */
  const resetHandler = () => {
    if (profile) {
      setDraft({ ...profile });
    }
  };

  /* ---- 泛型字段更新 ---- */
  const updateField = <K extends keyof ResearchProfile>(field: K, value: ResearchProfile[K]) => {
    setDraft((prev) => (prev ? { ...prev, [field]: value } : null));
  };

  /* ===== 渲染 ===== */
  return (
    <div className="h-full flex flex-col bg-[var(--bg-base)]">
      {/* 顶栏 */}
      <PageHeader
        title="研究画像"
        onBack={onBack}
        actions={
          <div className="flex items-center gap-1.5">
            {saveSuccess && (
              <span className="flex items-center gap-1 text-xs text-[var(--success)]">
                <CheckCircle2 size={13} />
                已保存
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                fetchProfile();
                fetchNarrative();
              }}
              disabled={loading || narrativeLoading}
              className="flex items-center gap-1 text-xs text-[var(--text-muted)]"
            >
              <RefreshCw size={12} className={loading || narrativeLoading ? "animate-spin" : ""} />
              刷新
            </Button>
          </div>
        }
      />

      {/* 滚动内容区 */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-5 pb-24 space-y-5">
          {/* 加载中 */}
          {loading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={22} className="animate-spin text-[var(--accent)]" />
              <span className="ml-2 text-sm text-[var(--text-muted)]">加载中...</span>
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="rounded-xl border border-[var(--error)] bg-[var(--accent-subtle)] px-4 py-3 text-sm text-[var(--error)]">
              {error}
            </div>
          )}

          {draft && !loading && (
            <>
              {/* ========== 卡片 1：基本配置 ========== */}
              <div className="rounded-xl border border-[var(--border-default)] p-5">
                <CardHeader icon={User} title="基本配置" />

                <div className="space-y-5">
                  {/* 主研究领域 */}
                  <div>
                    <FieldLabel>主研究领域</FieldLabel>
                    <div className="grid grid-cols-4 gap-2">
                      {DOMAINS.map((d) => (
                        <button
                          type="button"
                          key={d.value}
                          onClick={() => updateField("domain", d.value)}
                          className={`flex flex-col items-center justify-center gap-1 rounded-lg border p-2.5 text-center text-xs font-medium transition-colors ${
                            draft.domain === d.value
                              ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)] shadow-sm"
                              : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                          }`}
                        >
                          <d.icon size={16} className="shrink-0" />
                          <span className="leading-tight">{d.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 研究兴趣 */}
                  <div>
                    <FieldLabel>研究兴趣</FieldLabel>
                    <textarea
                      value={draft.research_interest}
                      onChange={(e) => updateField("research_interest", e.target.value)}
                      placeholder="例：植物根系发育的分子机制..."
                      className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5 text-sm text-[var(--text-secondary)] placeholder-[var(--text-disabled)] focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
                      rows={3}
                    />
                  </div>

                  {/* 典型样本量 + 研究备注 并排 */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <FieldLabel>典型样本量</FieldLabel>
                      <input
                        type="text"
                        value={draft.typical_sample_size}
                        onChange={(e) => updateField("typical_sample_size", e.target.value)}
                        placeholder="例：每组 30-50 个样本"
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5 text-sm text-[var(--text-secondary)] placeholder-[var(--text-disabled)] focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
                      />
                    </div>
                    <div>
                      <FieldLabel>研究备注</FieldLabel>
                      <input
                        type="text"
                        value={draft.research_notes}
                        onChange={(e) => updateField("research_notes", e.target.value)}
                        placeholder="其他偏好或约束条件"
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5 text-sm text-[var(--text-secondary)] placeholder-[var(--text-disabled)] focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* ========== 卡片 2：统计偏好 ========== */}
              <div className="rounded-xl border border-[var(--border-default)] p-5">
                <CardHeader icon={BarChart3} title="统计偏好" />

                <div className="space-y-5">
                  {/* 三个下拉并排 */}
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <FieldLabel>显著性水平 &alpha;</FieldLabel>
                      <select
                        value={draft.significance_level}
                        onChange={(e) =>
                          updateField("significance_level", parseFloat(e.target.value))
                        }
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5 text-sm text-[var(--text-secondary)] focus:border-[var(--accent)] focus:outline-none"
                      >
                        <option value={0.01}>0.01</option>
                        <option value={0.05}>0.05</option>
                        <option value={0.1}>0.10</option>
                      </select>
                    </div>
                    <div>
                      <FieldLabel>置信区间</FieldLabel>
                      <select
                        value={draft.confidence_interval}
                        onChange={(e) =>
                          updateField("confidence_interval", parseFloat(e.target.value))
                        }
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5 text-sm text-[var(--text-secondary)] focus:border-[var(--accent)] focus:outline-none"
                      >
                        <option value={0.9}>90%</option>
                        <option value={0.95}>95%</option>
                        <option value={0.99}>99%</option>
                      </select>
                    </div>
                    <div>
                      <FieldLabel>多重比较校正</FieldLabel>
                      <select
                        value={draft.preferred_correction}
                        onChange={(e) => updateField("preferred_correction", e.target.value)}
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5 text-sm text-[var(--text-secondary)] focus:border-[var(--accent)] focus:outline-none"
                      >
                        <option value="bonferroni">Bonferroni</option>
                        <option value="fdr">FDR</option>
                        <option value="none">不校正</option>
                      </select>
                    </div>
                  </div>

                  {/* 分析选项开关 */}
                  <div>
                    <FieldLabel>分析选项</FieldLabel>
                    <div className="space-y-2">
                      {[
                        {
                          key: "auto_check_assumptions" as const,
                          label: "自动前提检验",
                          desc: "正态性、方差齐性等统计前提",
                        },
                        {
                          key: "include_effect_size" as const,
                          label: "包含效应量",
                          desc: "Cohen's d、\u03b7\u00b2 等效应量指标",
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
                          className="flex items-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5"
                        >
                          <ToggleSwitch
                            checked={draft[item.key]}
                            onChange={(v) => updateField(item.key, v)}
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-[var(--text-secondary)]">
                              {item.label}
                            </p>
                            <p className="text-xs text-[var(--text-muted)]">{item.desc}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* ========== 卡片 3：输出风格 ========== */}
              <div className="rounded-xl border border-[var(--border-default)] p-5">
                <CardHeader icon={Palette} title="输出风格" />

                <div className="space-y-5">
                  {/* 期刊风格 */}
                  <div>
                    <FieldLabel>期刊风格</FieldLabel>
                    <div className="grid grid-cols-4 gap-2">
                      {JOURNAL_STYLES.map((style) => (
                        <button
                          type="button"
                          key={style.value}
                          onClick={() => updateField("journal_style", style.value)}
                          className={`flex flex-col items-center justify-center rounded-lg border px-2 py-2.5 text-center transition-colors ${
                            draft.journal_style === style.value
                              ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)] shadow-sm"
                              : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                          }`}
                        >
                          <span className="text-sm font-semibold">{style.label}</span>
                          <span className="mt-0.5 text-xs text-[var(--text-muted)] whitespace-normal">
                            {style.description}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 报告详细程度 + 输出语言 并排 */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <FieldLabel>报告详细程度</FieldLabel>
                      <div className="flex gap-2">
                        {REPORT_DETAIL_LEVELS.map((level) => (
                          <button
                            type="button"
                            key={level.value}
                            onClick={() => updateField("report_detail_level", level.value)}
                            className={`flex-1 flex flex-col items-center justify-center rounded-lg border px-2 py-2 text-center transition-colors ${
                              draft.report_detail_level === level.value
                                ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                                : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                            }`}
                          >
                            <span className="text-sm font-semibold">{level.label}</span>
                            <span className="text-xs text-[var(--text-muted)]">
                              {level.description}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <FieldLabel>输出语言</FieldLabel>
                      <div className="flex gap-2">
                        {[
                          { value: "zh", label: "中文" },
                          { value: "en", label: "English" },
                        ].map((lang) => (
                          <button
                            type="button"
                            key={lang.value}
                            onClick={() => updateField("output_language", lang.value)}
                            className={`flex-1 rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                              draft.output_language === lang.value
                                ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                                : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                            }`}
                          >
                            {lang.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* 图表尺寸 */}
                  <div>
                    <FieldLabel>图表尺寸</FieldLabel>
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { key: "figure_width" as const, label: "宽度 (in)" },
                        { key: "figure_height" as const, label: "高度 (in)" },
                        { key: "figure_dpi" as const, label: "DPI" },
                      ].map((f) => (
                        <div key={f.key}>
                          <span className="text-xs text-[var(--text-muted)]">{f.label}</span>
                          <input
                            type="number"
                            value={draft[f.key]}
                            onChange={(e) =>
                              updateField(
                                f.key,
                                parseInt(e.target.value) as ResearchProfile[typeof f.key],
                              )
                            }
                            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2 text-sm font-mono text-[var(--text-secondary)] focus:border-[var(--accent)] focus:outline-none mt-1"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* ========== 卡片 4：研究日志（只读） ========== */}
              <div className="rounded-xl border border-dashed border-[var(--border-default)] p-5">
                <CardHeader
                  icon={BookOpen}
                  title="研究日志"
                  badge={
                    <span className="flex items-center gap-1 text-xs text-[var(--text-muted)] bg-[var(--bg-elevated)] px-2 py-0.5 rounded-full">
                      <Lock size={10} />
                      只读
                    </span>
                  }
                />

                {narrativeLoading && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={18} className="animate-spin text-[var(--accent)]" />
                    <span className="ml-2 text-sm text-[var(--text-muted)]">加载中...</span>
                  </div>
                )}

                {!narrativeLoading && !narrative && (
                  <div className="rounded-lg border border-dashed border-[var(--border-subtle)] p-8 text-center">
                    <BookOpen size={28} className="mx-auto mb-2 text-[var(--text-muted)] opacity-40" />
                    <p className="text-sm text-[var(--text-muted)]">研究日志尚未生成</p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      保存研究画像后自动生成，Agent 分析时会追加观察
                    </p>
                  </div>
                )}

                {!narrativeLoading && narrative && (
                  <div className="space-y-3">
                    {/* 研究偏好摘要 */}
                    {narrative.sections.auto && (
                      <div
                        className={`rounded-lg border-l-[3px] p-3.5 bg-[var(--bg-elevated)] ${SECTION_COLORS.auto.border}`}
                      >
                        <div className="mb-1.5 flex items-center gap-2">
                          <span className="text-xs font-medium text-[var(--text-secondary)]">
                            研究偏好摘要
                          </span>
                          <SectionBadge label="系统维护" variant={SECTION_COLORS.auto.variant} />
                        </div>
                        <p className="whitespace-pre-wrap text-xs leading-relaxed text-[var(--text-secondary)]">
                          {narrative.sections.auto}
                        </p>
                      </div>
                    )}

                    {/* Agent 观察记录 */}
                    {narrative.sections.agent ? (
                      <div
                        className={`rounded-lg border-l-[3px] p-3.5 bg-[var(--bg-elevated)] ${SECTION_COLORS.agent.border}`}
                      >
                        <div className="mb-1.5 flex items-center gap-2">
                          <span className="text-xs font-medium text-[var(--text-secondary)]">
                            分析习惯与观察
                          </span>
                          <SectionBadge label="Agent 记录" variant={SECTION_COLORS.agent.variant} />
                        </div>
                        <p className="whitespace-pre-wrap text-xs leading-relaxed text-[var(--text-secondary)]">
                          {narrative.sections.agent}
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-lg border border-dashed border-[var(--border-subtle)] p-3.5 text-center">
                        <p className="text-xs text-[var(--text-muted)]">
                          Agent 观察尚未记录 — 分析过程中将自动追加
                        </p>
                      </div>
                    )}

                    {/* 用户备注 */}
                    {narrative.sections.user && (
                      <div
                        className={`rounded-lg border-l-[3px] p-3.5 bg-[var(--bg-elevated)] ${SECTION_COLORS.user.border}`}
                      >
                        <div className="mb-1.5 flex items-center gap-2">
                          <span className="text-xs font-medium text-[var(--text-secondary)]">
                            备注
                          </span>
                          <SectionBadge label="可在基本配置中编辑" variant={SECTION_COLORS.user.variant} />
                        </div>
                        <p className="whitespace-pre-wrap text-xs leading-relaxed text-[var(--text-secondary)]">
                          {narrative.sections.user}
                        </p>
                      </div>
                    )}

                    <p className="text-center text-xs text-[var(--text-muted)]">
                      研究日志由系统自动维护 · 如需修改偏好请在上方编辑后保存
                    </p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 底部固定操作栏 */}
      <div
        className="flex flex-shrink-0 items-center justify-end gap-2 px-6 py-3 bg-[var(--bg-base)]"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <Button
          variant="secondary"
          onClick={resetHandler}
          disabled={!draft || loading}
          icon={<RotateCcw size={13} />}
          className="rounded-lg px-4 py-1.5 text-sm"
        >
          重置默认
        </Button>
        <Button
          variant="primary"
          loading={saving}
          disabled={!draft}
          onClick={saveHandler}
          icon={<Save size={13} />}
          className="rounded-lg px-4 py-1.5 text-sm"
        >
          保存更改
        </Button>
      </div>
    </div>
  );
}
