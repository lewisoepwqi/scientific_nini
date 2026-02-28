/**
 * 推理时间线组件 - 展示分析步骤的时间线视图
 */
import React, { useState } from "react";
import {
  Clock,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  Circle,
  Lightbulb,
  ArrowRight,
  Target,
  Sparkles,
  Brain,
} from "lucide-react";

export interface TimelineStep {
  id: string;
  title: string;
  description?: string;
  type: "analysis" | "decision" | "planning" | "reflection" | "default";
  status: "completed" | "in_progress" | "pending";
  timestamp?: string;
  confidence?: number;
  keyDecisions?: string[];
  duration?: number; // in seconds
}

interface ReasoningTimelineProps {
  steps: TimelineStep[];
  currentStep?: number;
  onStepClick?: (step: TimelineStep, index: number) => void;
  className?: string;
}

const typeConfig = {
  analysis: {
    icon: Brain,
    color: "text-blue-600",
    bgColor: "bg-blue-50",
    borderColor: "border-blue-200",
    label: "分析",
  },
  decision: {
    icon: Target,
    color: "text-amber-600",
    bgColor: "bg-amber-50",
    borderColor: "border-amber-200",
    label: "决策",
  },
  planning: {
    icon: Sparkles,
    color: "text-purple-600",
    bgColor: "bg-purple-50",
    borderColor: "border-purple-200",
    label: "规划",
  },
  reflection: {
    icon: Lightbulb,
    color: "text-emerald-600",
    bgColor: "bg-emerald-50",
    borderColor: "border-emerald-200",
    label: "反思",
  },
  default: {
    icon: Circle,
    color: "text-gray-600",
    bgColor: "bg-gray-50",
    borderColor: "border-gray-200",
    label: "步骤",
  },
};

const statusConfig = {
  completed: {
    icon: CheckCircle,
    color: "text-green-600",
    bgColor: "bg-green-100",
  },
  in_progress: {
    icon: Circle,
    color: "text-blue-600",
    bgColor: "bg-blue-100",
  },
  pending: {
    icon: Circle,
    color: "text-gray-400",
    bgColor: "bg-gray-100",
  },
};

export const ReasoningTimeline: React.FC<ReasoningTimelineProps> = ({
  steps,
  currentStep = -1,
  onStepClick,
  className = "",
}) => {
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return "";
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  const formatTime = (timestamp?: string) => {
    if (!timestamp) return "";
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return "";
    }
  };

  return (
    <div className={`space-y-2 ${className}`}>
      {steps.map((step, index) => {
        const typeStyle = typeConfig[step.type] || typeConfig.default;
        const statusStyle = statusConfig[step.status];
        const StatusIcon = statusStyle.icon;
        const isExpanded = expandedSteps.has(step.id);
        const isCurrent = index === currentStep;

        return (
          <div
            key={step.id}
            className={`relative rounded-lg border transition-all duration-200 ${
              isCurrent
                ? `border-blue-300 bg-blue-50/50 shadow-sm`
                : `border-gray-200 bg-white hover:border-gray-300`
            }`}
          >
            {/* 连接线 */}
            {index < steps.length - 1 && (
              <div className="absolute left-6 top-full w-0.5 h-2 bg-gray-200" />
            )}

            {/* 头部 - 可点击展开 */}
            <button
              onClick={() => {
                toggleStep(step.id);
                onStepClick?.(step, index);
              }}
              className="w-full flex items-center gap-3 p-3 text-left"
            >
              {/* 状态图标 */}
              <div
                className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${statusStyle.bgColor}`}
              >
                <StatusIcon size={18} className={statusStyle.color} />
              </div>

              {/* 类型标签 */}
              <div
                className={`flex-shrink-0 px-2 py-1 rounded text-xs font-medium ${typeStyle.bgColor} ${typeStyle.color}`}
              >
                {typeStyle.label}
              </div>

              {/* 标题 */}
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm text-gray-900 truncate">
                  {step.title}
                </div>
                {step.timestamp && (
                  <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
                    <Clock size={10} />
                    <span>{formatTime(step.timestamp)}</span>
                    {step.duration && (
                      <>
                        <span>·</span>
                        <span>{formatDuration(step.duration)}</span>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* 置信度 */}
              {step.confidence !== undefined && step.confidence > 0 && (
                <div className="flex-shrink-0 flex items-center gap-1 text-xs">
                  <div
                    className={`px-2 py-1 rounded ${
                      step.confidence >= 0.8
                        ? "bg-green-100 text-green-700"
                        : step.confidence >= 0.5
                          ? "bg-amber-100 text-amber-700"
                          : "bg-red-100 text-red-700"
                    }`}
                  >
                    {(step.confidence * 100).toFixed(0)}%
                  </div>
                </div>
              )}

              {/* 展开箭头 */}
              <div className="flex-shrink-0 text-gray-400">
                {isExpanded ? (
                  <ChevronDown size={16} />
                ) : (
                  <ChevronRight size={16} />
                )}
              </div>
            </button>

            {/* 展开内容 */}
            {isExpanded && (
              <div className="px-3 pb-3 pt-0">
                <div className="pl-[52px]">
                  {/* 描述 */}
                  {step.description && (
                    <div className="text-sm text-gray-600 mb-3 leading-relaxed">
                      {step.description}
                    </div>
                  )}

                  {/* 关键决策 */}
                  {step.keyDecisions && step.keyDecisions.length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs font-medium text-gray-500 mb-2">
                        关键决策
                      </div>
                      <ul className="space-y-1.5">
                        {step.keyDecisions.map((decision, idx) => (
                          <li
                            key={idx}
                            className="flex items-start gap-2 text-sm"
                          >
                            <ArrowRight
                              size={14}
                              className="text-amber-500 mt-0.5 flex-shrink-0"
                            />
                            <span className="text-gray-700">{decision}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}

      {steps.length === 0 && (
        <div className="text-center py-8 text-gray-400 text-sm">
          暂无分析步骤
        </div>
      )}
    </div>
  );
};

export default ReasoningTimeline;
