/**
 * 分析计划卡片组件 —— 渲染结构化步骤列表或回退 Markdown 展示。
 */
import { useState } from 'react'
import {
  Lightbulb,
  ChevronDown,
  ChevronRight,
  Circle,
  Loader2,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import type { AnalysisPlanData } from '../store'
import MarkdownContent from './MarkdownContent'

interface Props {
  content: string
  analysisPlan?: AnalysisPlanData
}

function StepIcon({ status }: { status: string }) {
  switch (status) {
    case 'in_progress':
      return <Loader2 size={16} className="text-blue-500 animate-spin" />
    case 'done':
      return <CheckCircle2 size={16} className="text-green-500" />
    case 'failed':
    case 'blocked':
      return <XCircle size={16} className="text-red-500" />
    default:
      return <Circle size={16} className="text-gray-300" />
  }
}

export default function AnalysisPlanCard({ content, analysisPlan }: Props) {
  const [expanded, setExpanded] = useState(true)

  const steps = analysisPlan?.steps
  const completedCount = steps?.filter((s) => s.status === 'done').length ?? 0
  const totalCount = steps?.length ?? 0

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
              <span className="font-medium text-indigo-900">
                {steps ? `分析计划 (${completedCount}/${totalCount})` : '分析思路'}
              </span>
            </div>
            {expanded
              ? <ChevronDown size={14} className="text-indigo-600" />
              : <ChevronRight size={14} className="text-indigo-600" />
            }
          </button>

          {/* 内容区 */}
          {expanded && (
            <div className="px-4 pb-3 border-t border-indigo-200/50">
              {steps ? (
                <ul className="mt-2 space-y-1.5">
                  {steps.map((step) => (
                    <li key={step.id} className="flex items-start gap-2 text-sm">
                      <span className="flex-shrink-0 mt-0.5">
                        <StepIcon status={step.status} />
                      </span>
                      <span
                        className={
                          step.status === 'done'
                            ? 'text-gray-500 line-through'
                            : step.status === 'failed' || step.status === 'blocked'
                              ? 'text-red-700'
                              : step.status === 'in_progress'
                                ? 'text-indigo-900 font-medium'
                                : 'text-indigo-900'
                        }
                      >
                        {step.title}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="mt-2 text-sm text-indigo-900 markdown-body prose prose-sm max-w-none prose-headings:text-indigo-900 prose-strong:text-indigo-900">
                  <MarkdownContent content={content} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
