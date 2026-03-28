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
import Button from "./ui/Button";

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
 <div className="overflow-hidden rounded-xl border border-[var(--border-default)] bg-gradient-to-br from-[var(--bg-elevated)] via-[var(--bg-base)] to-[var(--accent-subtle)]/50 shadow-sm">
 {/* 头部：一句话概括 + 操作按钮 */}
 <div className="flex items-center justify-between px-3 py-2.5">
 <div className="flex items-center gap-2 min-w-0">
 <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-elevated)] text-white">
 <BrainCircuit size={14} />
 </div>
 {loading ? (
 <div className="flex items-center gap-1.5 text-sm text-[var(--text-muted)]">
 <Loader2 size={12} className="animate-spin" />
 <span className="truncate">正在理解您的意图...</span>
 </div>
 ) : (
 <span className="text-sm text-[var(--text-secondary)] truncate">{summary}</span>
 )}
 </div>

 {/* 操作按钮区域 */}
 {!loading && (
 <div className="flex items-center gap-1 shrink-0">
 {/* 低置信度指示 */}
 {autoExpandClarification && (
 <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--warning-subtle)] text-[var(--warning)] dark:text-[var(--warning)] text-[10px]">
 <HelpCircle size={10} />
 需确认
 </span>
 )}
 {/* 展开/折叠按钮 */}
 <button
 type="button"
 onClick={() => setDetailsExpanded(!detailsExpanded)}
 className="flex items-center gap-0.5 px-2 py-1 text-[11px] rounded-md text-[var(--text-secondary)] bg-transparent border-none cursor-pointer focus:outline-none"
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
 <div className="border-t border-[var(--border-subtle)] px-3 py-3 space-y-3">
 {/* 推荐能力 */}
 {analysis.capability_candidates.length > 0 && (
 <div className="flex items-start gap-2">
 <Target size={14} className="text-[var(--domain-profile)] mt-0.5 shrink-0" />
 <div className="min-w-0">
 <div className="text-[11px] text-[var(--text-muted)] mb-1">
 推荐分析类型
 </div>
 <div className="flex flex-wrap gap-1.5">
 {analysis.capability_candidates.slice(0, 3).map((c) => {
 const name =
 (c.payload?.display_name as string) || c.name;
 return (
 <Button
 variant="ghost"
 key={c.name}
 onClick={() => onApplySuggestion(`请帮我做${name}`)}
 className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--accent-subtle)] text-[var(--domain-profile)] text-xs hover:bg-[var(--accent-subtle)]"
 >
 {name}
 </Button>
 );
 })}
 </div>
 </div>
 </div>
 )}

 {/* 推荐工具 */}
 {analysis.tool_hints.length > 0 && (
 <div className="flex items-start gap-2">
 <Wrench size={14} className="text-[var(--success)] mt-0.5 shrink-0" />
 <div className="min-w-0">
 <div className="text-[11px] text-[var(--text-muted)] mb-1">
 推荐工具
 </div>
 <div className="flex flex-wrap gap-1.5">
 {analysis.tool_hints.slice(0, 4).map((tool) => (
 <span
 key={tool}
 className="inline-flex px-1.5 py-0.5 rounded bg-[var(--success-subtle)] text-[var(--success)] text-[11px] dark:text-[var(--success)]"
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
          <div className="rounded-lg border border-[var(--warning)] bg-[var(--warning-subtle)]">
            <button
              type="button"
              onClick={() => setClarificationExpanded(!clarificationExpanded)}
              className="w-full flex items-center justify-between px-2.5 py-2 text-left bg-transparent border-none cursor-pointer focus:outline-none"
            >
 <div className="flex items-center gap-1.5 text-[var(--warning)] text-xs">
 <HelpCircle size={12} />
 <span className="font-medium">需要确认</span>
 </div>
 {clarificationExpanded ? (
 <ChevronUp size={12} className="text-[var(--warning)]" />
 ) : (
 <ChevronDown size={12} className="text-[var(--warning)]" />
 )}
 </button>
 {clarificationExpanded && (
 <div className="px-2.5 pb-2.5">
 <div className="text-xs text-[var(--warning)] mb-2">
 {analysis.clarification_question}
 </div>
 {analysis.clarification_options.length > 0 && (
 <div className="flex flex-wrap gap-1.5">
 {analysis.clarification_options.map((option) => (
 <Button
 variant="ghost"
 key={option.label}
 onClick={() =>
 onApplySuggestion(`我想做${option.label}`)
 }
 className="inline-flex items-center px-2 py-1 rounded-full border border-[var(--warning)] bg-[var(--bg-base)] text-[var(--warning)] text-[11px] dark:text-[var(--warning)]"
 >
 {option.label}
 </Button>
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
 <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] italic">
 <Lightbulb size={12} />
 <span>暂无具体推荐，系统将基于您的描述进行分析</span>
 </div>
 )}
 </div>
 )}
 </div>
 );
}
