/**
 * 引用列表组件 - CitationList
 *
 * 在 AI 回答底部展示参考来源列表
 */
import { BookOpen } from "lucide-react";
import type { RetrievalItem } from "../store";
import { getCredibilityLabel } from "./CitationMarker";

function getVerificationLabel(status?: RetrievalItem["verificationStatus"]): {
 text: string;
 color: string;
} | null {
 if (!status) return null;
 if (status === "verified") {
 return { text: "已验证", color: "text-[var(--success)] bg-[var(--accent-subtle)] border-[var(--success)]" };
 }
 if (status === "conflicted") {
 return { text: "证据冲突", color: "text-[var(--error)] bg-[var(--accent-subtle)] border-[var(--error)]" };
 }
 return { text: "待验证", color: "text-[var(--warning)] bg-[var(--accent-subtle)] border-[var(--warning)]" };
}

interface CitationListProps {
 /** 检索结果列表 */
 retrievals: RetrievalItem[];
 /** 是否可折叠 */
 collapsible?: boolean;
}

export default function CitationList({
 retrievals,
}: CitationListProps) {
 if (!retrievals || retrievals.length === 0) return null;

 const formatTime = (value?: string): string | null => {
 if (!value) return null;
 const date = new Date(value);
 if (Number.isNaN(date.getTime())) return value;
 return date.toLocaleString("zh-CN", { hour12: false });
 };

 return (
 <div className="mt-4 pt-3 border-t border-[var(--border-default)]">
 {/* 标题 */}
 <div className="flex items-center gap-1.5 mb-2 text-[var(--text-secondary)]">
 <BookOpen size={14} />
 <span className="text-xs font-medium">参考来源</span>
 </div>

 {/* 来源列表 */}
 <ul className="space-y-1.5">
 {retrievals.map((retrieval, index) => {
 const credibility = getCredibilityLabel(retrieval.score);
 const verification = getVerificationLabel(retrieval.verificationStatus);
 return (
 <li
 key={`${retrieval.source}-${index}`}
 className="flex items-start gap-2 text-xs"
 >
 {/* 序号 */}
 <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded bg-[var(--accent-subtle)] text-[var(--accent)] font-medium text-[11px]">
 {index + 1}
 </span>

 {/* 来源信息 */}
 <div className="flex-1 min-w-0 py-0.5">
 <div className="flex items-center gap-2 flex-wrap">
 <span className="font-medium text-[var(--text-secondary)] dark:text-[var(--text-disabled)] truncate">
 {retrieval.source}
 </span>
 {credibility && (
 <span
 className={`inline-flex px-1.5 py-0 rounded text-[10px] border ${credibility.color}`}
 >
 {credibility.text}
 </span>
 )}
 {verification && (
 <span
 className={`inline-flex px-1.5 py-0 rounded text-[10px] border ${verification.color}`}
 >
 {verification.text}
 </span>
 )}
 </div>
 {/* 知识片段 */}
 {retrieval.snippet && (
 <p className="mt-1 text-[11px] text-[var(--text-secondary)] line-clamp-2">
 {retrieval.snippet}
 </p>
 )}
 {(retrieval.sourceType || retrieval.acquisitionMethod || retrieval.sourceId) && (
 <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
 {retrieval.sourceType && (
 <span className="rounded border border-[var(--border-default)] px-1 py-0">
 {retrieval.sourceType}
 </span>
 )}
 {retrieval.acquisitionMethod && (
 <span>获取方式：{retrieval.acquisitionMethod}</span>
 )}
 {retrieval.claimId && <span>claim_id：{retrieval.claimId}</span>}
 {retrieval.sourceId && <span>来源ID：{retrieval.sourceId}</span>}
 </div>
 )}
 {(retrieval.sourceTime || retrieval.accessedAt) && (
 <div className="mt-1 text-[10px] text-[var(--text-muted)]">
 {retrieval.sourceTime && (
 <span>来源时间：{formatTime(retrieval.sourceTime)}</span>
 )}
 {retrieval.sourceTime && retrieval.accessedAt && <span> · </span>}
 {retrieval.accessedAt && (
 <span>获取时间：{formatTime(retrieval.accessedAt)}</span>
 )}
 </div>
 )}
 {(retrieval.reasonSummary || retrieval.conflictSummary) && (
 <div className="mt-1 text-[10px] text-[var(--text-secondary)]">
 {retrieval.reasonSummary && <span>原因：{retrieval.reasonSummary}</span>}
 {retrieval.reasonSummary && retrieval.conflictSummary && <span> · </span>}
 {retrieval.conflictSummary && (
 <span>冲突：{retrieval.conflictSummary}</span>
 )}
 </div>
 )}
 </div>
 </li>
 );
 })}
 </ul>
 </div>
 );
}
