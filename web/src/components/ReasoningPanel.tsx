/**
 * ReasoningPanel - 推理过程展示面板
 *
 * 显示 Agent 的分析思路和决策过程，支持折叠/展开。
 */
import { useState } from "react";
import { Lightbulb, ChevronDown, ChevronUp, Copy, Check, FileOutput } from "lucide-react";
import { useStore } from "../store";

interface ReasoningData {
  step: string;
  thought: string;
  rationale: string;
  alternatives?: string[];
  confidence?: number;
  reasoning_type?: "analysis" | "decision" | "planning" | "reflection";
  key_decisions?: string[];
  tags?: string[];
}

interface ReasoningPanelProps {
  data: ReasoningData;
  defaultExpanded?: boolean;
}

export default function ReasoningPanel({
  data,
  defaultExpanded = false,
}: ReasoningPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [copied, setCopied] = useState(false);
  const [exported, setExported] = useState(false);
  const sessionId = useStore((s) => s.sessionId);

  const handleExportToReport = async () => {
    if (!sessionId) {
      alert('请先选择或创建会话');
      return;
    }

    const reasoningText = `## 分析思路：${getStepLabel(data.step)}\n\n**思考过程：**\n${data.thought}\n\n**决策理由：**\n${data.rationale}`;

    try {
      const response = await fetch(`/api/sessions/${sessionId}/export-reasoning`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reasoning: reasoningText,
          step: data.step,
          reasoning_type: data.reasoning_type,
          confidence: data.confidence,
        }),
      });

      if (response.ok) {
        setExported(true);
        setTimeout(() => setExported(false), 2000);
      } else {
        console.error('导出到报告失败');
      }
    } catch (e) {
      console.error('导出失败:', e);
    }
  };

  const getStepLabel = (step: string) => {
    const labels: Record<string, string> = {
      method_selection: "方法选择",
      parameter_selection: "参数选择",
      chart_selection: "图表选择",
      assumption_check: "假设检验",
      fallback_decision: "降级决策",
      data_interpretation: "数据解读",
    };
    return labels[step] || step;
  };

  const getTypeLabel = (type?: string) => {
    const labels: Record<string, string> = {
      analysis: "分析",
      decision: "决策",
      planning: "规划",
      reflection: "反思",
    };
    return type ? labels[type] || type : "";
  };

  const getTypeColor = (type?: string) => {
    const colors: Record<string, string> = {
      analysis: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
      decision: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
      planning: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
      reflection: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
    };
    return type ? colors[type] || "" : "";
  };

  const handleCopy = async () => {
    const text = `分析思路：${getStepLabel(data.step)}\n\n思考过程：\n${data.thought}\n\n决策理由：\n${data.rationale}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error("复制失败:", e);
    }
  };

  // 提取决策关键词并高亮
  const highlightDecisionKeywords = (text: string) => {
    const keywords = [
      "选择", "决定", "因此", "因为", "所以", "建议", "推荐",
      "由于", "基于", "考虑", "对比", "评估", "判断",
    ];
    let result = text;
    keywords.forEach((keyword) => {
      result = result.replace(
        new RegExp(keyword, "g"),
        `<span class="font-semibold text-amber-600 dark:text-amber-400">${keyword}</span>`
      );
    });
    return result;
  };

  return (
    <div className="my-2 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/20 overflow-hidden">
      {/* 头部 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-amber-100/50 dark:hover:bg-amber-900/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Lightbulb className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-medium text-amber-900 dark:text-amber-100">
            {getStepLabel(data.step)}
          </span>
          {data.reasoning_type && (
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${getTypeColor(
                data.reasoning_type
              )}`}
            >
              {getTypeLabel(data.reasoning_type)}
            </span>
          )}
          {data.confidence !== undefined && data.confidence < 1.0 && (
            <span className="text-xs text-amber-600/70 dark:text-amber-400/70">
              置信度: {Math.round(data.confidence * 100)}%
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleCopy();
            }}
            className="p-1 rounded hover:bg-amber-200/50 dark:hover:bg-amber-800/50 text-amber-600 dark:text-amber-400"
            title="复制分析思路"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleExportToReport();
            }}
            className="p-1 rounded hover:bg-amber-200/50 dark:hover:bg-amber-800/50 text-amber-600 dark:text-amber-400"
            title="导出到报告"
          >
            {exported ? (
              <Check className="w-3.5 h-3.5" />
            ) : (
              <FileOutput className="w-3.5 h-3.5" />
            )}
          </button>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          )}
        </div>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="px-3 pb-3 space-y-3">
          {/* 思考过程 */}
          <div>
            <h4 className="text-xs font-medium text-amber-700 dark:text-amber-300 mb-1">
              思考过程
            </h4>
            <p
              className="text-sm text-amber-900/80 dark:text-amber-100/80 leading-relaxed"
              dangerouslySetInnerHTML={{
                __html: highlightDecisionKeywords(data.thought),
              }}
            />
          </div>

          {/* 决策理由 */}
          {data.rationale && (
            <div>
              <h4 className="text-xs font-medium text-amber-700 dark:text-amber-300 mb-1">
                决策理由
              </h4>
              <p className="text-sm text-amber-900/80 dark:text-amber-100/80 leading-relaxed">
                {data.rationale}
              </p>
            </div>
          )}

          {/* 关键决策点 */}
          {data.key_decisions && data.key_decisions.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-amber-700 dark:text-amber-300 mb-1">
                关键决策
              </h4>
              <ul className="text-sm space-y-1">
                {data.key_decisions.map((decision, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2 text-amber-900/80 dark:text-amber-100/80"
                  >
                    <span className="text-amber-500 mt-0.5">•</span>
                    <span>{decision}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 替代方案 */}
          {data.alternatives && data.alternatives.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-amber-700 dark:text-amber-300 mb-1">
                考虑过的替代方案
              </h4>
              <ul className="text-sm space-y-1">
                {data.alternatives.map((alt, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2 text-amber-700/70 dark:text-amber-300/70"
                  >
                    <span className="text-amber-400">◦</span>
                    <span>{alt}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 标签 */}
          {data.tags && data.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {data.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-xs px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-800 text-amber-700 dark:text-amber-300"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
