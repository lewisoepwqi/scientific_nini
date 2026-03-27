/**
 * IntentTimelineItem - 意图理解确认项
 *
 * 在用户消息之后展示系统对意图的确认和理解
 * 与 IntentSummaryCard 的区别：
 * - SummaryCard：预判/输入辅助（在用户输入时展示）
 * - TimelineItem：确认/执行反馈（在用户发送后展示）
 */

import {
  BrainCircuit,
  Target,
  Wrench,
  HelpCircle,
  CheckCircle2,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Lightbulb,
} from "lucide-react";
import { useState } from "react";
import { type IntentAnalysisView } from "../store";

interface Props {
  analysis: IntentAnalysisView;
  onApplySuggestion: (value: string) => void;
  isActive?: boolean;
}

// 生成确认摘要（与 SummaryCard 的预测摘要做区分）
function generateConfirmationSummary(analysis: IntentAnalysisView): string {
  const topCapability = analysis.capability_candidates[0];

  if (analysis.clarification_needed) {
    return "需要您确认具体意图后再继续分析";
  }

  if (topCapability) {
    const displayName =
      (topCapability.payload?.display_name as string) || topCapability.name;
    return `已确认您的分析意图：${displayName}`;
  }

  // 此分支不应被触发（hasContent 检查已阻止无内容渲染）
  return "";
}

export default function IntentTimelineItem({
  analysis,
  onApplySuggestion,
  isActive = false,
}: Props) {
  const [expanded, setExpanded] = useState(false);

  const hasClarification = analysis.clarification_needed;
  const topCapability = analysis.capability_candidates[0];

  // 无有效内容时不渲染，避免展示无意义的"已理解您的分析需求"
  const hasContent = hasClarification || !!topCapability;
  if (!hasContent) return null;

  const summary = generateConfirmationSummary(analysis);

  return (
    <div
      className={`my-2 rounded-xl border transition-all ${
        isActive
          ? "border-sky-200 dark:border-sky-800 bg-sky-50/50 dark:bg-sky-900/20"
          : "border-slate-200 dark:border-slate-700 bg-slate-50/30 dark:bg-slate-800/50"
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-3 py-2.5"
      >
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={`flex h-5 w-5 shrink-0 items-center justify-center rounded ${
              isActive ? "bg-sky-100 dark:bg-sky-900/40 text-sky-600 dark:text-sky-400" : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400"
            }`}
          >
            <BrainCircuit size={12} />
          </div>
          <span className="text-xs text-slate-600 dark:text-slate-400 truncate">{summary}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {hasClarification && (
            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">
              需确认
            </span>
          )}
          {expanded ? (
            <ChevronUp size={14} className="text-slate-400" />
          ) : (
            <ChevronDown size={14} className="text-slate-400" />
          )}
        </div>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="border-t border-slate-200/50 dark:border-slate-700/50 px-3 pb-3">
          <div className="mt-2 space-y-2">
            {/* 主要意图确认 */}
            {topCapability && (
              <div className="flex items-center gap-2 rounded-lg bg-white/60 dark:bg-slate-800/60 p-2">
                <Target size={12} className="text-sky-600" />
                <div className="min-w-0">
                  <div className="text-[11px] text-slate-500 dark:text-slate-400">分析类型</div>
                  <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    {(topCapability.payload?.display_name as string) ||
                      topCapability.name}
                  </div>
                </div>
              </div>
            )}

            {/* 推荐工具 */}
            {analysis.tool_hints.length > 0 && (
              <div className="flex items-center gap-2 rounded-lg bg-white/60 dark:bg-slate-800/60 p-2">
                <Wrench size={12} className="text-emerald-600" />
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] text-slate-500 dark:text-slate-400 mb-1">
                    将使用以下工具
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {analysis.tool_hints.slice(0, 4).map((tool) => (
                      <span
                        key={tool}
                        className="inline-flex rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-700"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 激活技能 */}
            {analysis.active_skills.length > 0 && (
              <div className="flex items-center gap-2 rounded-lg bg-white/60 dark:bg-slate-800/60 p-2">
                <Sparkles size={12} className="text-purple-600" />
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] text-slate-500 dark:text-slate-400 mb-1">
                    已激活智能技能
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {analysis.active_skills.map((skill) => (
                      <span
                        key={skill.name}
                        className="inline-flex rounded border border-purple-200 dark:border-purple-800 bg-white dark:bg-slate-800 px-1.5 py-0.5 text-[11px] text-purple-700 dark:text-purple-400"
                      >
                        {skill.name}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 澄清建议 */}
            {hasClarification && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-2">
                <div className="flex items-center gap-1.5 text-amber-700 text-[11px] font-medium">
                  <HelpCircle size={12} />
                  需要您的确认
                </div>
                <div className="mt-1 text-xs text-amber-900">
                  {analysis.clarification_question}
                </div>
                {analysis.clarification_options.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {analysis.clarification_options.map((option) => (
                      <button
                        key={option.label}
                        onClick={() =>
                          onApplySuggestion(`我想做${option.label}`)
                        }
                        className="inline-flex rounded-full border border-amber-300 dark:border-amber-700 bg-white dark:bg-slate-800 px-2 py-0.5 text-[11px] text-amber-800 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 确认完成提示 */}
            {!hasClarification && topCapability && (
              <div className="flex items-center gap-1.5 text-xs text-emerald-600">
                <CheckCircle2 size={12} />
                <span>意图已确认，正在分析...</span>
              </div>
            )}

            {/* 空状态提示 */}
            {!topCapability &&
              analysis.tool_hints.length === 0 &&
              analysis.active_skills.length === 0 &&
              !hasClarification && (
                <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500 italic">
                  <Lightbulb size={12} />
                  <span>暂无具体推荐，系统将基于您的描述进行分析</span>
                </div>
              )}
          </div>
        </div>
      )}
    </div>
  );
}
