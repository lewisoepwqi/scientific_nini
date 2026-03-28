/**
 * 引用标注组件 - CitationMarker
 *
 * 在 AI 回答中展示 [1], [2] 样式的引用标注
 * 支持悬停和点击交互
 */
import React, { useState, useRef, useEffect } from "react";
import { BookOpen, X } from "lucide-react";
import type { RetrievalItem } from "../store";

interface CitationMarkerProps {
  /** 引用序号 */
  index: number;
  /** 对应的检索结果 */
  retrieval?: RetrievalItem;
  /** 点击回调 */
  onClick?: () => void;
  /** 是否紧凑模式 */
  compact?: boolean;
}

export default React.memo(function CitationMarker({
  index,
  retrieval,
  onClick,
  compact = false,
}: CitationMarkerProps) {
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const [tooltipPos, setTooltipPos] = useState<"above" | "below">("below");
  const markerRef = useRef<HTMLButtonElement>(null);
  const formatTime = (value?: string): string | null => {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("zh-CN", { hour12: false });
  };

  // 计算 tooltip 位置，避免超出视口
  useEffect(() => {
    if (!tooltipOpen || !markerRef.current) return;

    const rect = markerRef.current.getBoundingClientRect();
    const tooltipHeight = 120; // 预估高度
    const spaceBelow = window.innerHeight - rect.bottom;

    if (spaceBelow < tooltipHeight && rect.top > tooltipHeight) {
      setTooltipPos("above");
    } else {
      setTooltipPos("below");
    }
  }, [tooltipOpen]);

  // 计算可信度标签
  const credibilityLabel = (() => {
    if (!retrieval?.score) return null;
    if (retrieval.score >= 0.8) return { text: "高可信度", color: "text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-900/20" };
    if (retrieval.score >= 0.6) return { text: "一般参考", color: "text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-900/20" };
    return { text: "参考", color: "text-slate-500 bg-slate-100 dark:text-slate-400 dark:bg-slate-800" };
  })();
  const verificationLabel = (() => {
    if (!retrieval?.verificationStatus) return null;
    if (retrieval.verificationStatus === "verified") {
      return { text: "已验证", color: "text-emerald-700 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-900/20" };
    }
    if (retrieval.verificationStatus === "conflicted") {
      return { text: "证据冲突", color: "text-rose-700 bg-rose-50 dark:text-rose-400 dark:bg-rose-900/20" };
    }
    return { text: "待验证", color: "text-amber-700 bg-amber-50 dark:text-amber-400 dark:bg-amber-900/20" };
  })();

  return (
    <span className="relative inline-block">
      <button
        ref={markerRef}
        onClick={() => {
          setTooltipOpen(!tooltipOpen);
          onClick?.();
        }}
        onMouseEnter={() => setTooltipOpen(true)}
        onMouseLeave={() => setTooltipOpen(false)}
        className={`
          inline-flex items-center justify-center mx-0.5
          ${compact ? "min-w-[14px] h-3.5 text-[10px]" : "min-w-[18px] h-4 text-xs"}
          px-1 py-0 font-medium text-blue-600 bg-blue-50 hover:bg-blue-100
          rounded transition-colors cursor-pointer align-super leading-none
        `}
        aria-label={`引用 ${index}`}
      >
        [{index}]
      </button>

      {/* Tooltip */}
      {tooltipOpen && retrieval && (
        <div
          className={`absolute left-1/2 -translate-x-1/2 ${
            tooltipPos === "below" ? "top-full mt-1" : "bottom-full mb-1"
          } z-50 w-64 bg-white dark:bg-slate-800 rounded-lg shadow-lg border border-slate-200 dark:border-slate-700 p-3`}
          onMouseEnter={() => setTooltipOpen(true)}
          onMouseLeave={() => setTooltipOpen(false)}
        >
          {/* 箭头 */}
          <div
            className={`absolute left-1/2 -translate-x-1/2 w-2 h-2 bg-white dark:bg-slate-800 border-l border-t border-slate-200 dark:border-slate-700 rotate-45 ${
              tooltipPos === "below" ? "-top-1" : "-bottom-1 rotate-[225deg]"
            }`}
          />

          {/* 内容 */}
          <div className="relative">
            {/* 头部 */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-1.5 text-blue-600">
                <BookOpen size={12} />
                <span className="text-xs font-medium">引用 [{index}]</span>
              </div>
              <button
                onClick={() => setTooltipOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X size={12} />
              </button>
            </div>

            {/* 来源标题 */}
            <div className="text-xs font-medium text-slate-700 dark:text-slate-200 mb-1 truncate">
              {retrieval.source}
            </div>

            {/* 可信度标签 */}
            {credibilityLabel && (
              <span
                className={`inline-flex px-1.5 py-0.5 rounded text-[10px] ${credibilityLabel.color}`}
              >
                {credibilityLabel.text}
              </span>
            )}
            {verificationLabel && (
              <span
                className={`ml-1 inline-flex px-1.5 py-0.5 rounded text-[10px] ${verificationLabel.color}`}
              >
                {verificationLabel.text}
              </span>
            )}

            {/* 片段预览 */}
            {retrieval.snippet && (
              <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400 line-clamp-3">
                {retrieval.snippet}
              </div>
            )}

            {(retrieval.sourceType || retrieval.acquisitionMethod || retrieval.sourceId) && (
              <div className="mt-2 space-y-1 text-[10px] text-slate-400 dark:text-slate-500">
                {retrieval.sourceType && <div>来源类型：{retrieval.sourceType}</div>}
                {retrieval.acquisitionMethod && <div>获取方式：{retrieval.acquisitionMethod}</div>}
                {retrieval.claimId && <div>claim_id：{retrieval.claimId}</div>}
                {retrieval.sourceId && <div>来源ID：{retrieval.sourceId}</div>}
                {retrieval.sourceTime && <div>来源时间：{formatTime(retrieval.sourceTime)}</div>}
                {retrieval.accessedAt && <div>获取时间：{formatTime(retrieval.accessedAt)}</div>}
                {retrieval.reasonSummary && <div>原因摘要：{retrieval.reasonSummary}</div>}
                {retrieval.conflictSummary && <div>冲突摘要：{retrieval.conflictSummary}</div>}
              </div>
            )}
          </div>
        </div>
      )}
    </span>
  );
});

// 辅助函数：计算可信度标签
export function getCredibilityLabel(score?: number): { text: string; color: string } | null {
  if (score === undefined || score === null) return null;
  if (score >= 0.8) return { text: "高可信度", color: "text-emerald-600 bg-emerald-50 border-emerald-200 dark:text-emerald-400 dark:bg-emerald-900/20 dark:border-emerald-800" };
  if (score >= 0.6) return { text: "一般参考", color: "text-amber-600 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-900/20 dark:border-amber-800" };
  return { text: "参考", color: "text-slate-500 bg-slate-100 border-slate-200 dark:text-slate-400 dark:bg-slate-800 dark:border-slate-600" };
}
