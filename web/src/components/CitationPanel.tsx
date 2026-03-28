/**
 * 引用详情面板组件 - 侧边栏展示引用详情
 */
import React from "react";
import {
  BookOpen,
  X,
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
  if (!isOpen) return null;

  const selectedCitation = selectedIndex !== undefined
    ? citations.find((c) => c.index === selectedIndex)
    : undefined;

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-white dark:bg-slate-900 shadow-xl border-l border-slate-200 dark:border-slate-700 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
        <div className="flex items-center gap-2">
          <BookOpen size={18} className="text-blue-600" />
          <span className="font-semibold text-slate-900 dark:text-slate-100">知识引用</span>
          <span className="text-sm text-slate-500 dark:text-slate-400">({citations.length})</span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-500 dark:text-slate-400 transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* Citation List */}
        <div className={`${selectedCitation ? "w-1/3" : "w-full"} border-r border-slate-200 dark:border-slate-700 overflow-y-auto`}>
          <div className="p-2 space-y-1">
            {citations.map((citation) => (
              <button
                key={citation.index}
                onClick={() => onCitationSelect?.(citation)}
                className={`
                  w-full text-left p-2 rounded-lg transition-colors
                  ${selectedIndex === citation.index
                    ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800"
                    : "hover:bg-slate-50 dark:hover:bg-slate-800 border border-transparent"
                  }
                `}
              >
                <div className="flex items-start gap-2">
                  <span className={`
                    flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium
                    ${selectedIndex === citation.index
                      ? "bg-blue-600 text-white"
                      : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
                    }
                  `}>
                    {citation.index}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                      {citation.documentTitle}
                    </div>
                    <div className="flex items-center gap-1 mt-1">
                      <BarChart3 size={10} className="text-slate-400 dark:text-slate-500" />
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {citation.relevanceScore.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Citation Detail */}
        {selectedCitation && (
          <div className="w-2/3 overflow-y-auto p-4">
            <div className="space-y-4">
              {/* Document Title */}
              <div>
                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mb-1">
                  <FileText size={14} />
                  <span>文档</span>
                </div>
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                  {selectedCitation.documentTitle}
                </h3>
              </div>

              {/* Relevance Score */}
              <div>
                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mb-1">
                  <BarChart3 size={14} />
                  <span>相关度</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        selectedCitation.relevanceScore >= 0.8
                          ? "bg-green-500"
                          : selectedCitation.relevanceScore >= 0.5
                            ? "bg-amber-500"
                            : "bg-red-500"
                      }`}
                      style={{ width: `${selectedCitation.relevanceScore * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    {(selectedCitation.relevanceScore * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Excerpt */}
              <div>
                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mb-1">
                  <Tag size={14} />
                  <span>引用内容</span>
                </div>
                <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 text-sm text-slate-700 dark:text-slate-300 leading-relaxed border border-slate-200 dark:border-slate-700">
                  {selectedCitation.excerpt}
                </div>
              </div>

              {/* Document ID */}
              <div className="pt-2 border-t border-slate-200 dark:border-slate-700">
                <div className="text-xs text-slate-400 dark:text-slate-500">
                  文档 ID: {selectedCitation.documentId}
                </div>
              </div>

              {/* Source URL */}
              {selectedCitation.sourceUrl && (
                <a
                  href={selectedCitation.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                >
                  <ExternalLink size={14} />
                  <span>查看来源</span>
                </a>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CitationPanel;
