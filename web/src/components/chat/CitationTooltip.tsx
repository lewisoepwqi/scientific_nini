/**
 * CitationTooltip —— 引用角标 tooltip。
 *
 * 设计规范：.impeccable.md Chat Components §CitationTooltip
 * 100ms show delay，最大宽度 320px，自动避边定位。
 */
import React, { useState, useRef, useEffect, useCallback } from "react";
import { BookOpen, X } from "lucide-react";
import type { RetrievalItem } from "../../store";
import Button from "../ui/Button";

interface CitationTooltipProps {
 /** 引用序号 */
 index: number;
 /** 对应的检索结果 */
 retrieval?: RetrievalItem;
 /** 点击回调 */
 onClick?: () => void;
 /** 是否紧凑模式 */
 compact?: boolean;
}

export default React.memo(function CitationTooltip({
 index,
 retrieval,
 onClick,
 compact = false,
}: CitationTooltipProps) {
 const [visible, setVisible] = useState(false);
 const [position, setPosition] = useState<"above" | "below">("below");
 const markerRef = useRef<HTMLButtonElement>(null);
 const showTimerRef = useRef<ReturnType<typeof setTimeout>>();

 // 100ms 延迟显示
 const handleMouseEnter = useCallback(() => {
 showTimerRef.current = setTimeout(() => setVisible(true), 100);
 }, []);

 const handleMouseLeave = useCallback(() => {
 if (showTimerRef.current) {
 clearTimeout(showTimerRef.current);
 showTimerRef.current = undefined;
 }
 setVisible(false);
 }, []);

 // 清理定时器
 useEffect(() => {
 return () => {
 if (showTimerRef.current) clearTimeout(showTimerRef.current);
 };
 }, []);

 // 计算 tooltip 位置
 useEffect(() => {
 if (!visible || !markerRef.current) return;
 const rect = markerRef.current.getBoundingClientRect();
 const spaceBelow = window.innerHeight - rect.bottom;
 setPosition(spaceBelow < 140 && rect.top > 140 ? "above" : "below");
 }, [visible]);

 return (
 <span className="relative inline-block">
 <Button
 variant="ghost"
 ref={markerRef}
 type="button"
 onClick={() => {
 setVisible(!visible);
 onClick?.();
 }}
 onMouseEnter={handleMouseEnter}
 onMouseLeave={handleMouseLeave}
 className={`
 inline-flex items-center justify-center mx-0.5 px-1 py-0 font-medium
 rounded align-super leading-none
 ${compact ? "min-w-[14px] h-3.5 text-[10px]" : "min-w-[18px] h-4 text-xs"}
 text-[var(--accent)] bg-[var(--accent-subtle)]
`}
 aria-label={`引用 ${index}`}
 >
 [{index}]
 </Button>

 {visible && retrieval && (
 <div
 className={`absolute left-1/2 -translate-x-1/2 z-50 w-80 max-w-[320px] rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-2.5 shadow-lg ${
 position === "below" ? "top-full mt-1" : "bottom-full mb-1"
 }`}
 onMouseEnter={() => setVisible(true)}
 onMouseLeave={handleMouseLeave}
 >
 {/* 头部 */}
 <div className="flex items-start justify-between gap-2 mb-1.5">
 <div className="flex items-center gap-1.5 text-[var(--accent)]">
 <BookOpen size={12} />
 <span className="text-xs font-medium">引用 [{index}]</span>
 </div>
 <Button
 variant="ghost"
 type="button"
 onClick={() => setVisible(false)}
 className="text-[var(--text-muted)] h-5 w-5 p-0"
 >
 <X size={12} />
 </Button>
 </div>

 {/* 来源标题 */}
 <div className="text-xs font-medium text-[var(--text-primary)] truncate">
 {retrieval.source}
 </div>

 {/* 可信度 */}
 {retrieval.score != null && (
 <span
 className={`mt-1 inline-flex px-1.5 py-0.5 rounded text-[10px] ${
 retrieval.score >= 0.8
 ? "text-[var(--success)] bg-[var(--success)]/10"
 : retrieval.score >= 0.6
 ? "text-[var(--warning)] bg-[var(--warning)]/10"
 : "text-[var(--text-muted)] bg-[var(--bg-overlay)]"
 }`}
 >
 {retrieval.score >= 0.8 ? "高可信度" : retrieval.score >= 0.6 ? "一般参考" : "参考"}
 </span>
 )}

 {/* 片段预览 */}
 {retrieval.snippet && (
 <div className="mt-1.5 text-xs text-[var(--text-muted)] line-clamp-2">
 {retrieval.snippet}
 </div>
 )}
 </div>
 )}
 </span>
 );
});
