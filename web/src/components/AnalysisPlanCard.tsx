/**
 * 分析思路卡片组件 —— 醒目展示 Agent 的分析计划和推理过程。
 */
import { useState } from 'react'
import { Lightbulb, ChevronDown, ChevronRight } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface Props {
  content: string
}

export default function AnalysisPlanCard({ content }: Props) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="flex gap-3 mb-4">
      <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-indigo-100 text-indigo-600">
        <Lightbulb size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 overflow-hidden">
          {/* 标题栏 */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-indigo-100/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Lightbulb size={14} className="text-indigo-600" />
              <span className="font-medium text-indigo-900">分析思路</span>
            </div>
            {expanded
              ? <ChevronDown size={14} className="text-indigo-600" />
              : <ChevronRight size={14} className="text-indigo-600" />
            }
          </button>

          {/* 内容区 */}
          {expanded && (
            <div className="px-4 pb-3 border-t border-indigo-200/50">
              <div className="mt-2 text-sm text-indigo-900 markdown-body prose prose-sm max-w-none prose-headings:text-indigo-900 prose-strong:text-indigo-900">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
