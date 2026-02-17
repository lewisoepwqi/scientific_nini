import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Loader2,
  Sparkles,
  XCircle,
} from 'lucide-react'
import { type AnalysisPlanProgress, type PlanStepStatus } from '../store'
import { emitPlanTelemetry } from '../telemetry'

interface Props {
  plan: AnalysisPlanProgress
}

function statusLabel(status: PlanStepStatus): string {
  switch (status) {
    case 'in_progress':
      return '进行中'
    case 'done':
      return '已完成'
    case 'blocked':
      return '已阻塞'
    case 'failed':
      return '失败'
    default:
      return '未开始'
  }
}

function statusBadgeClass(status: PlanStepStatus): string {
  switch (status) {
    case 'in_progress':
      return 'bg-blue-100 text-blue-700 border-blue-200'
    case 'done':
      return 'bg-emerald-100 text-emerald-700 border-emerald-200'
    case 'blocked':
      return 'bg-amber-100 text-amber-800 border-amber-200'
    case 'failed':
      return 'bg-red-100 text-red-700 border-red-200'
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200'
  }
}

function StepStatusIcon({ status }: { status: PlanStepStatus }) {
  switch (status) {
    case 'in_progress':
      return <Loader2 size={14} className="text-blue-600 animate-spin" />
    case 'done':
      return <CheckCircle2 size={14} className="text-emerald-600" />
    case 'blocked':
      return <AlertTriangle size={14} className="text-amber-600" />
    case 'failed':
      return <XCircle size={14} className="text-red-600" />
    default:
      return <Circle size={14} className="text-slate-400" />
  }
}

function truncateText(text: string, max = 96): string {
  const normalized = text.trim()
  if (normalized.length <= max) return normalized
  return `${normalized.slice(0, Math.max(0, max - 1)).trimEnd()}…`
}

export default function AnalysisPlanHeader({ plan }: Props) {
  const [mobileExpanded, setMobileExpanded] = useState(false)
  const previousStepRef = useRef<number | null>(null)
  const blockedEmittedRef = useRef(false)

  const safeCurrentIndex = Math.max(1, Math.min(plan.current_step_index, plan.total_steps || 1))
  const currentTitle = truncateText(plan.step_title || `步骤 ${safeCurrentIndex}`)
  const nextHint = truncateText(plan.next_hint || '', 120)
  const blockReason = truncateText(plan.block_reason || '', 120)

  const completedCount = useMemo(
    () => plan.steps.filter((step) => step.status === 'done').length,
    [plan.steps],
  )

  useEffect(() => {
    emitPlanTelemetry('plan_header_rendered', {
      total_steps: plan.total_steps,
      current_step_index: safeCurrentIndex,
      step_status: plan.step_status,
    })
  }, [plan.total_steps, safeCurrentIndex, plan.step_status])

  useEffect(() => {
    if (previousStepRef.current !== safeCurrentIndex) {
      emitPlanTelemetry('plan_step_changed', {
        from: previousStepRef.current,
        to: safeCurrentIndex,
        step_status: plan.step_status,
      })
      previousStepRef.current = safeCurrentIndex
    }
  }, [safeCurrentIndex, plan.step_status])

  useEffect(() => {
    const isBlocked = plan.step_status === 'blocked' || plan.step_status === 'failed'
    if (isBlocked && !blockedEmittedRef.current) {
      emitPlanTelemetry('plan_blocked_exposed', {
        current_step_index: safeCurrentIndex,
        step_status: plan.step_status,
      })
      blockedEmittedRef.current = true
      return
    }
    if (!isBlocked) {
      blockedEmittedRef.current = false
    }
  }, [plan.step_status, safeCurrentIndex])

  return (
    <div
      className="border-b bg-gradient-to-b from-slate-50 to-white px-4 py-3"
      data-testid="analysis-plan-header"
    >
      <div className="max-w-3xl mx-auto">
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-start justify-between gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm">
                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700">
                  <Sparkles size={13} />
                </span>
                <span className="font-semibold text-slate-900">分析进度</span>
                <span className="text-xs text-slate-500" data-testid="analysis-plan-step-index">
                  Step {safeCurrentIndex}/{plan.total_steps}
                </span>
                <span
                  className={`inline-flex items-center px-2 py-0.5 text-xs rounded-full border ${statusBadgeClass(plan.step_status)}`}
                >
                  {statusLabel(plan.step_status)}
                </span>
              </div>
              <p className="mt-2 text-sm font-medium text-slate-900" data-testid="analysis-plan-current-title">
                {currentTitle}
              </p>
              {nextHint && (
                <p className="mt-1 text-xs text-slate-600" data-testid="analysis-plan-next-hint">
                  {nextHint}
                </p>
              )}
              {blockReason && (
                <p className="mt-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                  {blockReason}
                </p>
              )}
            </div>

            <button
              data-testid="analysis-plan-toggle"
              className="md:hidden inline-flex items-center gap-1 text-xs text-slate-600 px-2 py-1 rounded-md border border-slate-200 hover:bg-slate-50"
              onClick={() => {
                const next = !mobileExpanded
                setMobileExpanded(next)
                emitPlanTelemetry('plan_expand_toggled', {
                  expanded: next,
                  current_step_index: safeCurrentIndex,
                })
              }}
              aria-expanded={mobileExpanded}
              aria-label={mobileExpanded ? '收起步骤列表' : '展开步骤列表'}
            >
              {mobileExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span>{mobileExpanded ? '收起' : '展开'}</span>
            </button>
          </div>

          <div
            className={`border-t border-slate-100 px-4 py-3 ${mobileExpanded ? 'block' : 'hidden md:block'}`}
            data-testid="analysis-plan-step-list"
          >
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>已完成 {completedCount} / {plan.total_steps}</span>
              <span>当前步骤高亮显示</span>
            </div>
            <ul className="mt-2 space-y-1.5">
              {plan.steps.map((step) => {
                const isCurrent = step.id === safeCurrentIndex
                const itemClass = isCurrent
                  ? 'border-blue-200 bg-blue-50/70 text-blue-900'
                  : step.status === 'done'
                    ? 'border-emerald-200 bg-emerald-50/60 text-emerald-900'
                    : step.status === 'failed'
                      ? 'border-red-200 bg-red-50/60 text-red-900'
                      : step.status === 'blocked'
                        ? 'border-amber-200 bg-amber-50/60 text-amber-900'
                        : 'border-slate-200 bg-slate-50 text-slate-700'

                return (
                  <li
                    key={step.id}
                    data-testid={`analysis-plan-step-${step.id}`}
                    className={`rounded-lg border px-2.5 py-2 flex items-start gap-2 text-xs ${itemClass}`}
                  >
                    <span className="mt-0.5">
                      <StepStatusIcon status={step.status} />
                    </span>
                    <span className={step.status === 'done' ? 'line-through opacity-80' : ''}>
                      {step.id}. {truncateText(step.title, 88)}
                    </span>
                  </li>
                )
              })}
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
