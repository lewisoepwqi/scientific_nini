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
import Button from "./ui/Button";

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
          ? "border-[var(--domain-profile)] bg-[var(--accent-subtle)]/50"
          : "border-[var(--border-default)] bg-[var(--bg-elevated)]/50"
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-3 py-2.5 bg-transparent border-none cursor-pointer focus:outline-none"
      >
 <div className="flex items-center gap-2 min-w-0">
 <div
 className={`flex h-5 w-5 shrink-0 items-center justify-center rounded ${
 isActive ? "bg-[var(--accent-subtle)] text-[var(--domain-profile)]" : "bg-[var(--bg-overlay)] dark:bg-[var(--bg-overlay)] text-[var(--text-secondary)]"
 }`}
 >
 <BrainCircuit size={12} />
 </div>
 <span className="text-xs text-[var(--text-secondary)] truncate">{summary}</span>
 </div>
 <div className="flex items-center gap-1.5 shrink-0">
 {hasClarification && (
 <span className="rounded-full bg-[var(--warning-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--warning)]">
 需确认
 </span>
 )}
 {expanded ? (
 <ChevronUp size={14} className="text-[var(--text-muted)]" />
 ) : (
 <ChevronDown size={14} className="text-[var(--text-muted)]" />
 )}
 </div>
 </button>

 {/* 展开内容 */}
 {expanded && (
 <div className="border-t border-[var(--border-default)]/50 dark:border-[var(--border-default)]/50 px-3 pb-3">
 <div className="mt-2 space-y-2">
 {/* 主要意图确认 */}
 {topCapability && (
 <div className="flex items-center gap-2 rounded-lg bg-[var(--bg-base)]/60 p-2">
 <Target size={12} className="text-[var(--domain-profile)]" />
 <div className="min-w-0">
 <div className="text-[11px] text-[var(--text-secondary)]">分析类型</div>
 <div className="text-sm font-medium text-[var(--text-secondary)]">
 {(topCapability.payload?.display_name as string) ||
 topCapability.name}
 </div>
 </div>
 </div>
 )}

 {/* 推荐工具 */}
 {analysis.tool_hints.length > 0 && (
 <div className="flex items-center gap-2 rounded-lg bg-[var(--bg-base)]/60 p-2">
 <Wrench size={12} className="text-[var(--success)]" />
 <div className="min-w-0 flex-1">
 <div className="text-[11px] text-[var(--text-secondary)] mb-1">
 将使用以下工具
 </div>
 <div className="flex flex-wrap gap-1">
 {analysis.tool_hints.slice(0, 4).map((tool) => (
 <span
 key={tool}
 className="inline-flex rounded bg-[var(--accent-subtle)] px-1.5 py-0.5 text-[11px] text-[var(--success)] dark:text-[var(--success)]"
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
 <div className="flex items-center gap-2 rounded-lg bg-[var(--bg-base)]/60 p-2">
 <Sparkles size={12} className="text-[var(--domain-analysis)]" />
 <div className="min-w-0 flex-1">
 <div className="text-[11px] text-[var(--text-secondary)] mb-1">
 已激活智能技能
 </div>
 <div className="flex flex-wrap gap-1">
 {analysis.active_skills.map((skill) => (
 <span
 key={skill.name}
 className="inline-flex rounded border border-[var(--domain-analysis)] bg-[var(--bg-base)] px-1.5 py-0.5 text-[11px] text-[var(--domain-analysis)]"
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
 <div className="rounded-lg border border-[var(--warning)] bg-[var(--accent-subtle)]/70 p-2">
 <div className="flex items-center gap-1.5 text-[var(--warning)] text-[11px] font-medium">
 <HelpCircle size={12} />
 需要您的确认
 </div>
 <div className="mt-1 text-xs text-[var(--warning)]">
 {analysis.clarification_question}
 </div>
 {analysis.clarification_options.length > 0 && (
 <div className="mt-2 flex flex-wrap gap-1.5">
 {analysis.clarification_options.map((option) => (
 <Button
 variant="ghost"
 key={option.label}
 onClick={() =>
 onApplySuggestion(`我想做${option.label}`)
 }
 className="inline-flex rounded-full border border-[var(--warning)] px-2 py-0.5 text-[11px] text-[var(--warning)] dark:text-[var(--warning)] hover:bg-[var(--accent-subtle)]"
 >
 {option.label}
 </Button>
 ))}
 </div>
 )}
 </div>
 )}

 {/* 确认完成提示 */}
 {!hasClarification && topCapability && (
 <div className="flex items-center gap-1.5 text-xs text-[var(--success)]">
 <CheckCircle2 size={12} />
 <span>意图已确认，正在分析...</span>
 </div>
 )}

 {/* 空状态提示 */}
 {!topCapability &&
 analysis.tool_hints.length === 0 &&
 analysis.active_skills.length === 0 &&
 !hasClarification && (
 <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] italic">
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
