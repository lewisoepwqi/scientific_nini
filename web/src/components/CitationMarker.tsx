/**
 * 引用标注组件 - CitationMarker
 *
 * 在 AI 回答中展示 [1], [2] 样式的引用标注
 * 支持悬停和点击交互
 */
import React, { useState, useRef, useEffect } from "react";
import { BookOpen, X } from "lucide-react";
import type { RetrievalItem } from "../store";
import Button from "./ui/Button";

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
 if (retrieval.score >= 0.8) return { text: "高可信度", color: "text-[var(--success)] bg-[var(--accent-subtle)] dark:text-[var(--success)]" };
 if (retrieval.score >= 0.6) return { text: "一般参考", color: "text-[var(--warning)] bg-[var(--accent-subtle)]" };
 return { text: "参考", color: "text-[var(--text-muted)] bg-[var(--bg-elevated)] dark:text-[var(--text-muted)] dark:bg-[var(--bg-elevated)]" };
 })();
 const verificationLabel = (() => {
 if (!retrieval?.verificationStatus) return null;
 if (retrieval.verificationStatus === "verified") {
 return { text: "已验证", color: "text-[var(--success)] bg-[var(--accent-subtle)] dark:text-[var(--success)]" };
 }
 if (retrieval.verificationStatus === "conflicted") {
 return { text: "证据冲突", color: "text-[var(--error)] bg-[var(--accent-subtle)]" };
 }
 return { text: "待验证", color: "text-[var(--warning)] bg-[var(--accent-subtle)] dark:text-[var(--warning)]" };
 })();

 return (
 <span className="relative inline-block">
 <Button
 variant="ghost"
 ref={markerRef}
 type="button"
 onClick={() => {
 setTooltipOpen(!tooltipOpen);
 onClick?.();
 }}
 onMouseEnter={() => setTooltipOpen(true)}
 onMouseLeave={() => setTooltipOpen(false)}
 className={`
 inline-flex items-center justify-center mx-0.5
 ${compact ? "min-w-[14px] h-3.5 text-[10px]" : "min-w-[18px] h-4 text-xs"}
 px-1 py-0 font-medium text-[var(--accent)] bg-[var(--accent-subtle)]
 rounded align-super leading-none
`}
 aria-label={`引用 ${index}`}
 >
 [{index}]
 </Button>

 {/* Tooltip */}
 {tooltipOpen && retrieval && (
 <div
 className={`absolute left-1/2 -translate-x-1/2 ${
 tooltipPos === "below" ? "top-full mt-1" : "bottom-full mb-1"
 } z-50 max-w-80 bg-[var(--bg-base)] rounded-lg shadow-lg border border-[var(--border-default)] p-3`}
 onMouseEnter={() => setTooltipOpen(true)}
 onMouseLeave={() => setTooltipOpen(false)}
 >
 {/* 箭头 */}
 <div
 className={`absolute left-1/2 -translate-x-1/2 w-2 h-2 bg-[var(--bg-base)] border-l border-t border-[var(--border-default)] rotate-45 ${
 tooltipPos === "below" ? "-top-1" : "-bottom-1 rotate-[225deg]"
 }`}
 />

 {/* 内容 */}
 <div className="relative">
 {/* 头部 */}
 <div className="flex items-start justify-between gap-2 mb-2">
 <div className="flex items-center gap-1.5 text-[var(--accent)]">
 <BookOpen size={12} />
 <span className="text-xs font-medium">引用 [{index}]</span>
 </div>
 <Button
 variant="ghost"
 type="button"
 onClick={() => setTooltipOpen(false)}
 className="text-[var(--text-muted)]"
 >
 <X size={12} />
 </Button>
 </div>

 {/* 来源标题 */}
 <div className="text-xs font-medium text-[var(--text-secondary)] dark:text-[var(--text-disabled)] mb-1 truncate">
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
 <div className="mt-2 text-[11px] text-[var(--text-secondary)] line-clamp-3">
 {retrieval.snippet}
 </div>
 )}

 {(retrieval.sourceType || retrieval.acquisitionMethod || retrieval.sourceId) && (
 <div className="mt-2 space-y-1 text-[10px] text-[var(--text-muted)]">
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
 if (score >= 0.8) return { text: "高可信度", color: "text-[var(--success)] bg-[var(--accent-subtle)] border-[var(--success)] dark:text-[var(--success)]" };
 if (score >= 0.6) return { text: "一般参考", color: "text-[var(--warning)] bg-[var(--accent-subtle)] border-[var(--warning)] dark:text-[var(--warning)]" };
 return { text: "参考", color: "text-[var(--text-muted)] bg-[var(--bg-elevated)] border-[var(--border-default)] dark:text-[var(--text-muted)] dark:bg-[var(--bg-elevated)] dark:border-[var(--border-default)]" };
}
