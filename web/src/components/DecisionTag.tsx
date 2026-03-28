/**
 * 决策标签组件 - 高亮显示决策关键词
 */
import React, { useMemo } from "react";
import { Target, CheckCircle2, AlertCircle, Lightbulb, ArrowRight } from "lucide-react";
import { Badge } from "./ui/Badge";

export interface Decision {
 text: string;
 type?: "primary" | "secondary" | "fallback" | "suggestion";
 confidence?: number;
 icon?: "target" | "check" | "alert" | "lightbulb";
}

interface DecisionTagProps {
 decisions: Decision[];
 className?: string;
 compact?: boolean;
}

const typeConfig = {
 primary: {
 variant: "default" as const,
 label: "主要决策",
 },
 secondary: {
 variant: "default" as const,
 label: "次要决策",
 },
 fallback: {
 variant: "warning" as const,
 label: "备选方案",
 },
 suggestion: {
 variant: "success" as const,
 label: "建议",
 },
};

const iconMap = {
 target: Target,
 check: CheckCircle2,
 alert: AlertCircle,
 lightbulb: Lightbulb,
};

export const DecisionTag: React.FC<DecisionTagProps> = ({
 decisions,
 className = "",
 compact = false,
}) => {
 if (!decisions || decisions.length === 0) return null;

 return (
 <div className={`space-y-2 ${className}`}>
 {!compact && (
 <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
 <ArrowRight size={12} />
 <span>关键决策</span>
 </div>
 )}

 <div className={`flex ${compact ? "gap-1" : "gap-2"} flex-wrap`}>
 {decisions.map((decision, index) => {
 const config = typeConfig[decision.type || "primary"];
 const IconComponent = decision.icon ? iconMap[decision.icon] : ArrowRight;

 return (
 <div
 key={index}
 className={`
 inline-flex items-center gap-1.5 rounded-full border
 ${compact ? "px-2 py-0.5 text-xs" : "px-3 py-1.5 text-sm"}
 transition-all duration-200 hover:shadow-sm cursor-default
`}
 title={decision.text}
 >
 <Badge variant={config.variant} className={compact ? "text-[10px]" : "text-xs"}>
 <IconComponent size={compact ? 10 : 14} />
 <span className="font-medium truncate max-w-[200px]">
 {decision.text}
 </span>
 </Badge>
 {decision.confidence !== undefined && decision.confidence > 0 && (
 <Badge
 variant={
 decision.confidence >= 0.8
 ? "success"
 : decision.confidence >= 0.5
 ? "warning"
 : "error"
 }
 className="text-[10px]"
 >
 {(decision.confidence * 100).toFixed(0)}%
 </Badge>
 )}
 </div>
 );
 })}
 </div>
 </div>
 );
};

/**
 * 决策关键词高亮组件 - 在文本中高亮显示决策关键词
 */
interface DecisionHighlighterProps {
 text: string;
 keywords?: string[];
 className?: string;
}

const defaultDecisionKeywords = [
 "决定",
 "选择",
 "采用",
 "使用",
 "确定",
 "结论",
 "应该",
 "decide",
 "choose",
 "select",
 "determine",
 "conclusion",
 "should",
 "will use",
 "opt for",
 "recommend",
];

export const DecisionHighlighter: React.FC<DecisionHighlighterProps> = ({
 text,
 keywords = defaultDecisionKeywords,
 className = "",
}) => {
 // 缓存正则表达式，仅在 keywords 变化时重建
 const regex = useMemo(() => {
 const pattern = keywords
 .map((kw) => kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
 .join("|");
 return new RegExp(`(${pattern})`, "gi");
 }, [keywords]);

 // 分割文本并高亮关键词
 const parts = text.split(regex);

 return (
 <span className={className}>
 {parts.map((part, index) => {
 const isKeyword = keywords.some(
 (kw) => kw.toLowerCase() === part.toLowerCase()
 );

 if (isKeyword) {
 return (
 <mark
 key={index}
 className="bg-[var(--accent-subtle)] text-[var(--warning)] px-0.5 rounded font-medium"
 >
 {part}
 </mark>
 );
 }

 return <span key={index}>{part}</span>;
 })}
 </span>
 );
};

export default DecisionTag;
