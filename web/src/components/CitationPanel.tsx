/**
 * 引用详情面板组件 - 侧边栏展示引用详情
 *
 * 使用 DetailPanel 基础组件（推入式面板，无遮罩）。
 */
import React from "react";
import Button from "./ui/Button";
import { DetailPanel } from "./ui";
import {
 ExternalLink,
 FileText,
 BarChart3,
 Tag,
} from "lucide-react";

interface Citation {
 index: number;
 documentId: string;
 documentTitle: string;
 excerpt: string;
 relevanceScore: number;
 sourceUrl?: string;
}

interface CitationPanelProps {
 citations: Citation[];
 selectedIndex?: number;
 onClose: () => void;
 onCitationSelect?: (citation: Citation) => void;
 isOpen: boolean;
}

export const CitationPanel: React.FC<CitationPanelProps> = ({
 citations,
 selectedIndex,
 onClose,
 onCitationSelect,
 isOpen,
}) => {
 const selectedCitation = selectedIndex !== undefined
 ? citations.find((c) => c.index === selectedIndex)
 : undefined;

 return (
 <DetailPanel
 isOpen={isOpen}
 onClose={onClose}
 title={`知识引用 (${citations.length})`}
 width={384}
 >
 <div className="flex h-full">
 {/* Citation List */}
 <div className={`${selectedCitation ? "w-1/3" : "w-full"} overflow-y-auto`} style={{ borderRight: selectedCitation ? '1px solid var(--border-subtle)' : undefined }}>
 <div className="p-2 space-y-1">
 {citations.map((citation) => (
 <Button
 key={citation.index}
 variant="ghost"
 type="button"
 onClick={() => onCitationSelect?.(citation)}
 className={`
 w-full text-left p-2 rounded-lg
 ${selectedIndex === citation.index
 ? "bg-[var(--accent-subtle)] border border-[var(--accent)]"
 : "border border-transparent"
 }
`}
 >
 <div className="flex items-start gap-2">
 <span className={`
 flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-medium
 ${selectedIndex === citation.index
 ? "bg-[var(--accent)] text-white"
 : "bg-[var(--bg-overlay)] text-[var(--text-secondary)]"
 }
`}>
 {citation.index}
 </span>
 <div className="flex-1 min-w-0">
 <div className="text-[12px] font-medium text-[var(--text-primary)] truncate">
 {citation.documentTitle}
 </div>
 <div className="flex items-center gap-1 mt-1">
 <BarChart3 size={10} className="text-[var(--text-muted)]" />
 <span className="text-[11px] text-[var(--text-muted)]">
 {citation.relevanceScore.toFixed(2)}
 </span>
 </div>
 </div>
 </div>
 </Button>
 ))}
 </div>
 </div>

 {/* Citation Detail */}
 {selectedCitation && (
 <div className="w-2/3 overflow-y-auto p-4">
 <div className="space-y-4">
 {/* Document Title */}
 <div>
 <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)] mb-1">
 <FileText size={14} />
 <span>文档</span>
 </div>
 <h3 className="font-semibold text-[var(--text-primary)]">
 {selectedCitation.documentTitle}
 </h3>
 </div>

 {/* Relevance Score */}
 <div>
 <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)] mb-1">
 <BarChart3 size={14} />
 <span>相关度</span>
 </div>
 <div className="flex items-center gap-2">
 <div className="flex-1 h-2 bg-[var(--bg-overlay)] rounded-full overflow-hidden">
 <div
 className={`h-full rounded-full ${
 selectedCitation.relevanceScore >= 0.8
 ? "bg-[var(--success)]"
 : selectedCitation.relevanceScore >= 0.5
 ? "bg-[var(--warning)]"
 : "bg-[var(--error)]"
 }`}
 style={{ width: `${selectedCitation.relevanceScore * 100}%` }}
 />
 </div>
 <span className="text-[12px] font-medium text-[var(--text-secondary)]">
 {(selectedCitation.relevanceScore * 100).toFixed(0)}%
 </span>
 </div>
 </div>

 {/* Excerpt */}
 <div>
 <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)] mb-1">
 <Tag size={14} />
 <span>引用内容</span>
 </div>
 <div className="bg-[var(--bg-elevated)] rounded-lg p-3 text-[13px] text-[var(--text-secondary)] leading-relaxed border border-[var(--border-subtle)]">
 {selectedCitation.excerpt}
 </div>
 </div>

 {/* Document ID */}
 <div className="pt-2 border-t border-[var(--border-subtle)]">
 <div className="text-[11px] text-[var(--text-muted)]">
 文档 ID: {selectedCitation.documentId}
 </div>
 </div>

 {/* Source URL */}
 {selectedCitation.sourceUrl && (
 <a
 href={selectedCitation.sourceUrl}
 target="_blank"
 rel="noopener noreferrer"
 className="inline-flex items-center gap-1.5 text-[13px] text-[var(--accent)] hover:text-[var(--accent-hover)]"
 >
 <ExternalLink size={14} />
 <span>查看来源</span>
 </a>
 )}
 </div>
 </div>
 )}
 </div>
 </DetailPanel>
 );
};

export default CitationPanel;
