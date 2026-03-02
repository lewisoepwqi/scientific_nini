/**
 * 引用列表组件 - CitationList
 *
 * 在 AI 回答底部展示参考来源列表
 */
import { BookOpen } from "lucide-react";
import type { RetrievalItem } from "../store";
import { getCredibilityLabel } from "./CitationMarker";

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

  return (
    <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-700">
      {/* 标题 */}
      <div className="flex items-center gap-1.5 mb-2 text-slate-600 dark:text-slate-400">
        <BookOpen size={14} />
        <span className="text-xs font-medium">参考来源</span>
      </div>

      {/* 来源列表 */}
      <ul className="space-y-1.5">
        {retrievals.map((retrieval, index) => {
          const credibility = getCredibilityLabel(retrieval.score);
          return (
            <li
              key={`${retrieval.source}-${index}`}
              className="flex items-start gap-2 text-xs"
            >
              {/* 序号 */}
              <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded bg-blue-50 text-blue-600 font-medium text-[11px]">
                {index + 1}
              </span>

              {/* 来源信息 */}
              <div className="flex-1 min-w-0 py-0.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-slate-700 dark:text-slate-200 truncate">
                    {retrieval.source}
                  </span>
                  {credibility && (
                    <span
                      className={`inline-flex px-1.5 py-0 rounded text-[10px] border ${credibility.color}`}
                    >
                      {credibility.text}
                    </span>
                  )}
                </div>
                {/* 知识片段 */}
                {retrieval.snippet && (
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2">
                    {retrieval.snippet}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
