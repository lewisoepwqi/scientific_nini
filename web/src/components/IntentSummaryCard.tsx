/**
 * 意图理解摘要卡片
 *
 * 一句话概括 + 可展开查看详情
 * - 低置信度时自动展开澄清选项
 */
import { useState, useMemo } from "react";
import {
  BrainCircuit,
  Loader2,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  Wrench,
  HelpCircle,
  Target,
} from "lucide-react";
import { type IntentAnalysisView } from "../store";

interface Props {
  analysis: IntentAnalysisView | null;
  loading: boolean;
  onApplySuggestion: (value: string) => void;
}

// 生成一句话概括
function generateSummary(analysis: IntentAnalysisView): string {
  const topCapability = analysis.capability_candidates[0];
  const hasClarification = analysis.clarification_needed;

  if (hasClarification) {
    return "系统识别到多个可能的分析方向，需要您确认具体意图";
  }

  if (topCapability) {
    const displayName =
      (topCapability.payload?.display_name as string) || topCapability.name;
    return `系统理解您想要进行${displayName}`;
  }

  if (analysis.tool_hints.length > 0) {
    return `系统推荐您使用${analysis.tool_hints[0]}等工具进行分析`;
  }

  return "系统正在分析您的需求";
}

// 判断是否为低置信度（需要自动展开澄清）
function isLowConfidence(analysis: IntentAnalysisView): boolean {
  if (!analysis.clarification_needed) return false;

  // 如果有多个候选意图且分数接近，认为是低置信度
  if (analysis.capability_candidates.length >= 2) {
    const top = analysis.capability_candidates[0];
    const second = analysis.capability_candidates[1];
    // 如果第二名分数超过第一名的 80%，认为是低置信度
    if (top.score > 0 && second.score / top.score > 0.8) {
      return true;
    }
  }

  return analysis.clarification_needed;
}

export default function IntentSummaryCard({
  analysis,
  loading,
  onApplySuggestion,
}: Props) {
  // 是否展开详情
  const [detailsExpanded, setDetailsExpanded] = useState(false);

  // 低置信度时自动展开
  const autoExpandClarification = useMemo(() => {
    return analysis ? isLowConfidence(analysis) : false;
  }, [analysis]);

  // 澄清区域展开状态
  const [clarificationExpanded, setClarificationExpanded] = useState(() =>
    autoExpandClarification
  );

  if (!loading && !analysis) return null;

  const summary = analysis ? generateSummary(analysis) : "";
  const hasClarification = analysis?.clarification_needed ?? false;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-amber-50/50 shadow-sm">
      {/* 头部：一句话概括 + 操作按钮 */}
      <div className="flex items-center justify-between px-3 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-white">
            <BrainCircuit size={14} />
          </div>
          {loading ? (
            <div className="flex items-center gap-1.5 text-sm text-slate-500">
              <Loader2 size={12} className="animate-spin" />
              <span className="truncate">正在理解您的意图...</span>
            </div>
          ) : (
            <span className="text-sm text-slate-700 truncate">{summary}</span>
          )}
        </div>

        {/* 操作按钮区域 */}
        {!loading && (
          <div className="flex items-center gap-1 shrink-0">
            {/* 低置信度指示 */}
            {autoExpandClarification && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 text-[10px]">
                <HelpCircle size={10} />
                需确认
              </span>
            )}
            {/* 展开/折叠按钮 */}
            <button
              onClick={() => setDetailsExpanded(!detailsExpanded)}
              className="flex items-center gap-0.5 px-2 py-1 text-[11px] text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
            >
              {detailsExpanded ? (
                <>
                  <span>收起</span>
                  <ChevronUp size={12} />
                </>
              ) : (
                <>
                  <span>查看详情</span>
                  <ChevronDown size={12} />
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* 展开详情区域 */}
      {detailsExpanded && analysis && (
        <div className="border-t border-slate-100 px-3 py-3 space-y-3">
          {/* 推荐能力 */}
          {analysis.capability_candidates.length > 0 && (
            <div className="flex items-start gap-2">
              <Target size={14} className="text-sky-600 mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="text-[11px] text-slate-400 dark:text-slate-500 mb-1">
                  推荐分析类型
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.capability_candidates.slice(0, 3).map((c) => {
                    const name =
                      (c.payload?.display_name as string) || c.name;
                    return (
                      <button
                        key={c.name}
                        onClick={() => onApplySuggestion(`请帮我做${name}`)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 dark:bg-sky-900/20 dark:text-sky-400 text-xs hover:bg-sky-100 dark:hover:bg-sky-900/30 transition-colors"
                      >
                        {name}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* 推荐工具 */}
          {analysis.tool_hints.length > 0 && (
            <div className="flex items-start gap-2">
              <Wrench size={14} className="text-emerald-600 mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="text-[11px] text-slate-400 dark:text-slate-500 mb-1">
                  推荐工具
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.tool_hints.slice(0, 4).map((tool) => (
                    <span
                      key={tool}
                      className="inline-flex px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px] dark:bg-emerald-900/20 dark:text-emerald-400"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 澄清建议（可折叠） */}
          {hasClarification && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/50">
              <button
                onClick={() => setClarificationExpanded(!clarificationExpanded)}
                className="w-full flex items-center justify-between px-2.5 py-2 text-left"
              >
                <div className="flex items-center gap-1.5 text-amber-700 text-xs">
                  <HelpCircle size={12} />
                  <span className="font-medium">需要确认</span>
                </div>
                {clarificationExpanded ? (
                  <ChevronUp size={12} className="text-amber-600" />
                ) : (
                  <ChevronDown size={12} className="text-amber-600" />
                )}
              </button>
              {clarificationExpanded && (
                <div className="px-2.5 pb-2.5">
                  <div className="text-xs text-amber-800 mb-2">
                    {analysis.clarification_question}
                  </div>
                  {analysis.clarification_options.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {analysis.clarification_options.map((option) => (
                        <button
                          key={option.label}
                          onClick={() =>
                            onApplySuggestion(`我想做${option.label}`)
                          }
                          className="inline-flex items-center px-2 py-1 rounded-full border border-amber-300 bg-white text-amber-800 text-[11px] hover:bg-amber-100 transition-colors dark:border-amber-700 dark:bg-slate-800 dark:text-amber-400 dark:hover:bg-amber-900/30"
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 空状态提示：当没有推荐内容时显示 */}
          {analysis.capability_candidates.length === 0 &&
            analysis.tool_hints.length === 0 &&
            !hasClarification && (
              <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500 italic">
                <Lightbulb size={12} />
                <span>暂无具体推荐，系统将基于您的描述进行分析</span>
              </div>
            )}
        </div>
      )}
    </div>
  );
}
