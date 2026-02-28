/**
 * 决策标签组件 - 高亮显示决策关键词
 */
import React from "react";
import { Target, CheckCircle2, AlertCircle, Lightbulb, ArrowRight } from "lucide-react";

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
    bgColor: "bg-blue-100",
    textColor: "text-blue-800",
    borderColor: "border-blue-300",
    label: "主要决策",
  },
  secondary: {
    bgColor: "bg-gray-100",
    textColor: "text-gray-700",
    borderColor: "border-gray-300",
    label: "次要决策",
  },
  fallback: {
    bgColor: "bg-amber-100",
    textColor: "text-amber-800",
    borderColor: "border-amber-300",
    label: "备选方案",
  },
  suggestion: {
    bgColor: "bg-emerald-100",
    textColor: "text-emerald-800",
    borderColor: "border-emerald-300",
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
        <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500 mb-2">
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
                ${config.bgColor} ${config.textColor} ${config.borderColor}
                ${compact ? "px-2 py-0.5 text-xs" : "px-3 py-1.5 text-sm"}
                transition-all duration-200 hover:shadow-sm cursor-default
              `}
              title={decision.text}
            >
              <IconComponent size={compact ? 10 : 14} />
              <span className="font-medium truncate max-w-[200px]">
                {decision.text}
              </span>
              {decision.confidence !== undefined && decision.confidence > 0 && (
                <span
                  className={`
                    text-xs px-1.5 py-0.5 rounded-full
                    ${decision.confidence >= 0.8
                      ? "bg-green-200/50"
                      : decision.confidence >= 0.5
                        ? "bg-amber-200/50"
                        : "bg-red-200/50"
                    }
                  `}
                >
                  {(decision.confidence * 100).toFixed(0)}%
                </span>
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
  // 创建正则表达式来匹配关键词
  const pattern = keywords
    .map((kw) => kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const regex = new RegExp(`(${pattern})`, "gi");

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
              className="bg-amber-100 text-amber-900 px-0.5 rounded font-medium"
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
