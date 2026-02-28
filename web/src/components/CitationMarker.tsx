/**
 * 引用标记组件 - 行内引用标记
 */
import React, { useState } from "react";
import { BookOpen } from "lucide-react";

export interface Citation {
  index: number;
  documentId: string;
  documentTitle: string;
  excerpt: string;
  relevanceScore: number;
  sourceUrl?: string;
}

interface CitationMarkerProps {
  index: number;
  citation?: Citation;
  onClick?: (index: number) => void;
  compact?: boolean;
}

export const CitationMarker: React.FC<CitationMarkerProps> = ({
  index,
  citation,
  onClick,
  compact = false,
}) => {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <span className="relative inline-block">
      <sup
        onClick={() => onClick?.(index)}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`
          inline-flex items-center justify-center
          ${compact ? "min-w-[14px] h-3.5 text-[10px]" : "min-w-[18px] h-4 text-xs"}
          px-1 rounded-full
          bg-blue-100 text-blue-700
          hover:bg-blue-200 hover:text-blue-800
          cursor-pointer transition-colors duration-150
          font-medium leading-none
        `}
      >
        {index}
      </sup>

      {/* Tooltip preview */}
      {isHovered && citation && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 w-64">
          <div className="bg-white rounded-lg shadow-lg border border-gray-200 p-3 text-left">
            <div className="flex items-start gap-2">
              <BookOpen size={14} className="text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm text-gray-900 truncate">
                  {citation.documentTitle}
                </div>
                <div className="text-xs text-gray-500 mt-1 line-clamp-2">
                  {citation.excerpt}
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">
                    score: {citation.relevanceScore.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          </div>
          {/* Arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1">
            <div className="border-4 border-transparent border-t-white" />
          </div>
        </div>
      )}
    </span>
  );
};

interface CitationMarkerListProps {
  citations: Citation[];
  onCitationClick?: (citation: Citation) => void;
  className?: string;
}

export const CitationMarkerList: React.FC<CitationMarkerListProps> = ({
  citations,
  onCitationClick,
  className = "",
}) => {
  if (!citations || citations.length === 0) return null;

  return (
    <div className={`inline-flex items-center gap-1 ${className}`}>
      {citations.map((citation) => (
        <CitationMarker
          key={citation.index}
          index={citation.index}
          citation={citation}
          onClick={() => onCitationClick?.(citation)}
        />
      ))}
    </div>
  );
};

/**
 * 带引用标记的内容渲染器
 */
interface CitationContentProps {
  content: string;
  citations: Citation[];
  onCitationClick?: (citation: Citation) => void;
}

export const CitationContent: React.FC<CitationContentProps> = ({
  content,
  citations,
  onCitationClick,
}) => {
  // Parse citations like [1], [2], etc.
  const parts = content.split(/(\[\d+\])/g);

  return (
    <span>
      {parts.map((part, index) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (match) {
          const citationIndex = parseInt(match[1], 10);
          const citation = citations.find((c) => c.index === citationIndex);
          return (
            <CitationMarker
              key={index}
              index={citationIndex}
              citation={citation}
              onClick={() => citation && onCitationClick?.(citation)}
            />
          );
        }
        return <span key={index}>{part}</span>;
      })}
    </span>
  );
};

export default CitationMarker;
