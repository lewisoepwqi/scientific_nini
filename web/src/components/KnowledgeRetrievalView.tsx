/**
 * KnowledgeRetrievalView - 知识检索结果可视化组件
 *
 * 展示知识库检索的结果，包括相关性分数、来源和匹配内容。
 */
import { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, Search, Sparkles } from "lucide-react";

interface KnowledgeResult {
 id: string;
 title: string;
 excerpt: string;
 relevance_score: number;
 source_method: "vector" | "keyword" | "hybrid";
 metadata?: {
 domain?: string;
 tags?: string[];
 };
}

interface KnowledgeRetrievalViewProps {
 query: string;
 results: KnowledgeResult[];
 total_count: number;
 search_time_ms: number;
 search_method: string;
}

export default function KnowledgeRetrievalView({
 query,
 results,
 total_count,
 search_time_ms,
 search_method,
}: KnowledgeRetrievalViewProps) {
 const [expandedId, setExpandedId] = useState<string | null>(null);

 const getSourceIcon = (method: string) => {
 switch (method) {
 case "vector":
 return <Sparkles className="w-3 h-3 text-[var(--domain-analysis)]" />;
 case "keyword":
 return <Search className="w-3 h-3 text-[var(--accent)]" />;
 case "hybrid":
 return (
 <div className="flex -space-x-1">
 <Sparkles className="w-3 h-3 text-[var(--domain-analysis)]" />
 <Search className="w-3 h-3 text-[var(--accent)]" />
 </div>
 );
 default:
 return <BookOpen className="w-3 h-3 text-[var(--text-muted)]" />;
 }
 };

 const getSourceLabel = (method: string) => {
 switch (method) {
 case "vector":
 return "语义匹配";
 case "keyword":
 return "关键词";
 case "hybrid":
 return "混合";
 default:
 return method;
 }
 };

 const getRelevanceColor = (score: number) => {
 if (score >= 0.8) return "bg-[var(--success)]";
 if (score >= 0.6) return "bg-[var(--warning)]";
 return "bg-[var(--text-muted)]";
 };

 if (!results || results.length === 0) {
 return (
 <div className="p-4 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-default)]">
 <div className="flex items-center gap-2 text-[var(--text-muted)]">
 <BookOpen className="w-4 h-4" />
 <span className="text-sm">未找到相关知识</span>
 </div>
 </div>
 );
 }

 return (
 <div className="rounded-lg bg-[var(--accent-subtle)] border border-[var(--accent-subtle)]">
 {/* 头部信息 */}
 <div className="px-4 py-3 border-b border-[var(--accent-subtle)]">
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-2">
 <BookOpen className="w-4 h-4 text-[var(--accent)]" />
 <span className="font-medium text-[var(--accent)]">
 知识库检索
 </span>
 <span className="text-xs text-[var(--accent)] bg-[var(--accent-subtle)] px-2 py-0.5 rounded-full">
 {total_count} 条结果
 </span>
 </div>
 <div className="text-xs text-[var(--accent)]">
 {search_time_ms}ms · {search_method === "hybrid" ? "混合检索" : search_method}
 </div>
 </div>
 {query && (
 <div className="mt-2 text-sm text-[var(--accent)]">
 查询: <span className="font-medium">{query}</span>
 </div>
 )}
 </div>

 {/* 结果列表 */}
 <div className="divide-y divide-[var(--border-subtle)]">
 {results.map((result) => (
 <div
 key={result.id}
 role="button"
 tabIndex={0}
 aria-expanded={expandedId === result.id}
 className="p-4 hover:bg-[var(--accent-subtle)]/50 transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded"
 onClick={() => setExpandedId(expandedId === result.id ? null : result.id)}
 onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpandedId(expandedId === result.id ? null : result.id) } }}
 >
 <div className="flex items-start gap-3">
 {/* 相关性分数 */}
 <div className="flex-shrink-0">
 <div className="relative w-10 h-10">
 <svg className="w-10 h-10 transform -rotate-90">
 <circle
 cx="20"
 cy="20"
 r="16"
 fill="none"
 stroke="currentColor"
 strokeWidth="3"
 className="text-[var(--text-muted)]"
 />
 <circle
 cx="20"
 cy="20"
 r="16"
 fill="none"
 stroke="currentColor"
 strokeWidth="3"
 strokeDasharray={`${result.relevance_score * 100} 100`}
 className={`${getRelevanceColor(result.relevance_score)}`}
 />
 </svg>
 <span className="absolute inset-0 flex items-center justify-center text-xs font-medium">
 {Math.round(result.relevance_score * 100)}%
 </span>
 </div>
 </div>

 {/* 内容 */}
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2">
 <h4 className="font-medium text-[var(--text-primary)] truncate">
 {result.title}
 </h4>
 <div className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
 {getSourceIcon(result.source_method)}
 <span>{getSourceLabel(result.source_method)}</span>
 </div>
 </div>

 <p className="mt-1 text-sm text-[var(--text-secondary)] line-clamp-2">
 {result.excerpt}
 </p>

 {/* 标签 */}
 {result.metadata?.tags && result.metadata.tags.length > 0 && (
 <div className="mt-2 flex flex-wrap gap-1">
 {result.metadata.tags.map((tag) => (
 <span
 key={tag}
 className="text-xs px-2 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--accent)]"
 >
 {tag}
 </span>
 ))}
 </div>
 )}

 {/* 展开/收起 */}
 {expandedId === result.id && (
 <div className="mt-3 p-3 bg-[var(--bg-base)] rounded border border-[var(--accent-subtle)]">
 <p className="text-sm text-[var(--text-secondary)]">
 {result.excerpt}
 </p>
 {result.metadata?.domain && (
 <div className="mt-2 text-xs text-[var(--text-muted)]">
 领域: {result.metadata.domain}
 </div>
 )}
 </div>
 )}
 </div>

 {/* 展开图标 */}
 <div className="flex-shrink-0 text-[var(--text-muted)]">
 {expandedId === result.id ? (
 <ChevronUp className="w-4 h-4" />
 ) : (
 <ChevronDown className="w-4 h-4" />
 )}
 </div>
 </div>
 </div>
 ))}
 </div>
 </div>
 );
}
