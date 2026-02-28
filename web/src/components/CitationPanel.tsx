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
import { Citation } from "./CitationMarker";

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
    <div className="fixed inset-y-0 right-0 w-96 bg-white shadow-xl border-l border-gray-200 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2">
          <BookOpen size={18} className="text-blue-600" />
          <span className="font-semibold text-gray-900">知识引用</span>
          <span className="text-sm text-gray-500">({citations.length})</span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-500 transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* Citation List */}
        <div className={`${selectedCitation ? "w-1/3" : "w-full"} border-r border-gray-200 overflow-y-auto`}>
          <div className="p-2 space-y-1">
            {citations.map((citation) => (
              <button
                key={citation.index}
                onClick={() => onCitationSelect?.(citation)}
                className={`
                  w-full text-left p-2 rounded-lg transition-colors
                  ${selectedIndex === citation.index
                    ? "bg-blue-50 border border-blue-200"
                    : "hover:bg-gray-50 border border-transparent"
                  }
                `}
              >
                <div className="flex items-start gap-2">
                  <span className={`
                    flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium
                    ${selectedIndex === citation.index
                      ? "bg-blue-600 text-white"
                      : "bg-gray-200 text-gray-600"
                    }
                  `}>
                    {citation.index}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">
                      {citation.documentTitle}
                    </div>
                    <div className="flex items-center gap-1 mt-1">
                      <BarChart3 size={10} className="text-gray-400" />
                      <span className="text-xs text-gray-500">
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
                <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                  <FileText size={14} />
                  <span>文档</span>
                </div>
                <h3 className="font-semibold text-gray-900">
                  {selectedCitation.documentTitle}
                </h3>
              </div>

              {/* Relevance Score */}
              <div>
                <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                  <BarChart3 size={14} />
                  <span>相关度</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
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
                  <span className="text-sm font-medium text-gray-700">
                    {(selectedCitation.relevanceScore * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Excerpt */}
              <div>
                <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                  <Tag size={14} />
                  <span>引用内容</span>
                </div>
                <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700 leading-relaxed border border-gray-200">
                  {selectedCitation.excerpt}
                </div>
              </div>

              {/* Document ID */}
              <div className="pt-2 border-t border-gray-200">
                <div className="text-xs text-gray-400">
                  文档 ID: {selectedCitation.documentId}
                </div>
              </div>

              {/* Source URL */}
              {selectedCitation.sourceUrl && (
                <a
                  href={selectedCitation.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700"
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
