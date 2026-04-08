import { useEffect, useMemo, useRef, useState } from 'react'
import { useIsDesktop } from '../hooks'
import {
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
import Button from './ui/Button'
import { Badge } from './ui/Badge'

interface Props {
 plan: AnalysisPlanProgress
}

function statusLabel(status: PlanStepStatus): string {
 switch (status) {
 case 'in_progress':
 return '进行中'
 case 'done':
 return '已完成'
 case 'failed':
 case 'blocked':
 return '失败'
 case 'skipped':
 return '已跳过'
 default:
 return '未开始'
 }
}

function statusToVariant(status: PlanStepStatus): 'default' | 'success' | 'error' {
 switch (status) {
 case 'done':
 return 'success'
 case 'failed':
 case 'blocked':
 return 'error'
 default:
 return 'default'
 }
}

function StepStatusIcon({ status }: { status: PlanStepStatus }) {
 switch (status) {
 case 'in_progress':
 return <Loader2 size={14} className="text-[var(--accent)] animate-spin" />
 case 'done':
 return <CheckCircle2 size={14} className="text-[var(--success)]" />
 case 'failed':
 case 'blocked':
 return <XCircle size={14} className="text-[var(--error)]" />
 default:
 return <Circle size={14} className="text-[var(--text-muted)]" />
 }
}

function truncateText(text: string, max = 96): string {
 const normalized = text.trim()
 if (normalized.length <= max) return normalized
 return `${normalized.slice(0, Math.max(0, max - 1)).trimEnd()}…`
}

export default function AnalysisPlanHeader({ plan }: Props) {
 const isDesktop = useIsDesktop()
 const [mobileExpanded, setMobileExpanded] = useState(false)
 const previousStepRef = useRef<number | null>(null)

 // 桌面端始终展开，切换时重置移动端折叠状态
 useEffect(() => {
 if (isDesktop) setMobileExpanded(false)
 }, [isDesktop])
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
 className="border-b border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-3"
 data-testid="analysis-plan-header"
 >
 <div className="max-w-3xl mx-auto">
 <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] shadow-sm">
 <div className="flex items-start justify-between gap-3 px-4 py-3">
 <div className="min-w-0 flex-1">
 <div className="flex items-center gap-2 text-sm">
 <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[var(--accent-subtle)] text-[var(--accent)]">
 <Sparkles size={13} />
 </span>
 <span className="font-semibold text-[var(--text-primary)]">分析进度</span>
 <span className="text-xs text-[var(--text-secondary)]" data-testid="analysis-plan-step-index">
 Step {safeCurrentIndex}/{plan.total_steps}
 </span>
 <Badge variant={statusToVariant(plan.step_status)}>
 {statusLabel(plan.step_status)}
 </Badge>
 </div>
 <p className="mt-2 text-sm font-medium text-[var(--text-primary)]" data-testid="analysis-plan-current-title">
 {currentTitle}
 </p>
 {nextHint && (
 <p className="mt-1 text-xs text-[var(--text-secondary)]" data-testid="analysis-plan-next-hint">
 {nextHint}
 </p>
 )}
 {blockReason && (
 <p className="mt-1 text-xs text-[var(--warning)] bg-[var(--accent-subtle)] border border-[var(--warning)] rounded px-2 py-1">
 {blockReason}
 </p>
 )}
 </div>

 <Button
 variant="secondary"
 size="sm"
 data-testid="analysis-plan-toggle"
 className="md:hidden"
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
 </Button>
 </div>

 <div
 className={`border-t border-[var(--border-subtle)] px-4 py-3 ${mobileExpanded ? 'block' : 'hidden md:block'}`}
 data-testid="analysis-plan-step-list"
 >
 <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
 <span>已完成 {completedCount} / {plan.total_steps}</span>
 <span>步骤按状态着色</span>
 </div>
 <ul className="mt-2 space-y-1.5">
 {plan.steps.map((step) => {
 const itemClass =
 step.status === 'in_progress'
 ? 'border-[var(--accent)] bg-[var(--accent-subtle)]/70 text-[var(--accent)]'
 : step.status === 'done'
 ? 'border-[var(--success)] bg-[var(--accent-subtle)]/60 text-[var(--success)]'
 : step.status === 'failed' || step.status === 'blocked'
 ? 'border-[var(--error)] bg-[var(--accent-subtle)]/60 text-[var(--error)]'
 : step.status === 'skipped'
 ? 'border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-muted)]'
 : 'border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]'
 const textStyle =
 step.status === 'done' || step.status === 'skipped' ? 'line-through opacity-80' : ''

 return (
 <li
 key={step.id}
 data-testid={`analysis-plan-step-${step.id}`}
 className={`rounded-lg border px-2.5 py-2 flex items-start gap-2 text-xs ${itemClass}`}
 >
 <span className="mt-0.5">
 <StepStatusIcon status={step.status} />
 </span>
 <span className={textStyle}>
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
