/**
 * 对话主面板 —— 消息列表 + 输入框，居中限宽。
 * 输入区提取为 ChatInputArea，避免每次击键触发消息列表重渲染。
 * 所有消息按原始顺序展示，保持思考-行动-回答的连贯性。
 *
 * 注意：任务进度统一在工作区展示，Skill 进度面板会在对话区顶部显示
 */
import { useEffect, useRef, useMemo, useCallback, useState, startTransition } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useStore } from '../store'
import { useConfirm } from '../store/confirm-store'
import { useOnboardStore } from '../store/onboard-store'
import OnboardHint from './OnboardHint'
import MessageBubble from './MessageBubble'
import { Loader2 } from 'lucide-react'
import RecipeCenter from './RecipeCenter'
import PendingQuestionBanner from './PendingQuestionBanner'
import IntentTimelineItem from './IntentTimelineItem'
import AskUserQuestionPanel from './AskUserQuestionPanel'
import ChatInputArea from './ChatInputArea'
import SkillProgressPanel from './SkillProgressPanel'
import Button from './ui/Button'
import type { AgentRunThread, DispatchFailureItem, DispatchLedgerItem } from '../store/types'

const compactTokenFormatter = new Intl.NumberFormat('en-US', {
 notation: 'compact',
 compactDisplay: 'short',
 maximumFractionDigits: 1,
})

const selectedRunStatusLabel = {
 running: '运行中',
 completed: '已完成',
 error: '失败',
 stopped: '已终止',
} as const

const selectedRunStatusClass = {
 running:
 'border-[color-mix(in_srgb,var(--accent)_22%,transparent)] bg-[var(--accent-subtle)] text-[var(--accent)]',
 completed:
 'border-[color-mix(in_srgb,var(--success)_22%,transparent)] bg-[color-mix(in_srgb,var(--success)_10%,var(--bg-base))] text-[var(--success)]',
 error:
 'border-[color-mix(in_srgb,var(--error)_22%,transparent)] bg-[color-mix(in_srgb,var(--error)_10%,var(--bg-base))] text-[var(--error)]',
 stopped:
 'border-[color-mix(in_srgb,var(--text-muted)_24%,transparent)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]',
} as const

function renderDispatchLedgerBadges(
 run: AgentRunThread,
) {
 const badges: string[] = []
 if (typeof run.runnableCount === 'number') {
 badges.push(`可执行 ${run.runnableCount}`)
 }
 if (typeof run.preflightFailureCount === 'number') {
 badges.push(`预检失败 ${run.preflightFailureCount}`)
 }
 if (typeof run.routingFailureCount === 'number' && run.routingFailureCount > 0) {
 badges.push(`路由失败 ${run.routingFailureCount}`)
 }
 if (typeof run.executionFailureCount === 'number' && run.executionFailureCount > 0) {
 badges.push(`执行失败 ${run.executionFailureCount}`)
 }
 return badges
}

function renderDispatchFailureSection(
 title: string,
 items: DispatchFailureItem[] | null | undefined,
) {
 if (!items || items.length === 0) return null
 return (
 <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3">
 <p className="text-xs font-medium text-[var(--text-secondary)]">{title}</p>
 <div className="mt-2 space-y-2">
 {items.map((item, index) => (
 <div
 key={`${title}-${item.agent_id || 'unknown'}-${index}`}
 className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2"
 >
 <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
 <span className="text-xs font-semibold text-[var(--text-primary)]">
 {item.agent_id || '未匹配 agent'}
 </span>
 {item.task && (
 <span className="text-xs text-[var(--text-secondary)]">{item.task}</span>
 )}
 </div>
 <p className="mt-1 text-xs text-[var(--text-muted)] break-words">
 {item.error || '未返回详细原因'}
 </p>
 </div>
 ))}
 </div>
 </div>
 )
}

const dispatchLedgerStatusLabel: Record<string, string> = {
 success: '成功',
 error: '失败',
 stopped: '已停止',
}

const dispatchLedgerStatusClass: Record<string, string> = {
 success:
 'border-[color-mix(in_srgb,var(--success)_22%,transparent)] bg-[color-mix(in_srgb,var(--success)_10%,var(--bg-base))] text-[var(--success)]',
 error:
 'border-[color-mix(in_srgb,var(--error)_22%,transparent)] bg-[color-mix(in_srgb,var(--error)_10%,var(--bg-base))] text-[var(--error)]',
 stopped:
 'border-[color-mix(in_srgb,var(--text-muted)_24%,transparent)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]',
}

function renderDispatchLedgerSection(
 items: DispatchLedgerItem[] | null | undefined,
) {
 if (!items || items.length === 0) return null
 return (
 <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3">
 <p className="text-xs font-medium text-[var(--text-secondary)]">子任务账本</p>
 <div className="mt-2 space-y-2">
 {items.map((item, index) => {
 const status = typeof item.status === 'string' ? item.status : 'success'
 const statusLabel = dispatchLedgerStatusLabel[status] || status
 const statusClass =
 dispatchLedgerStatusClass[status] ||
 'border-[var(--border-subtle)] bg-[var(--bg-base)] text-[var(--text-secondary)]'
 return (
 <div
 key={`${item.agent_id || item.agent_name || 'entry'}-${item.task || index}`}
 className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2"
 >
 <div className="flex flex-wrap items-center justify-between gap-2">
 <div className="min-w-0">
 <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
 <span className="text-xs font-semibold text-[var(--text-primary)]">
 {item.agent_name || item.agent_id || '未命名 agent'}
 </span>
 {item.task && (
 <span className="text-xs text-[var(--text-secondary)]">{item.task}</span>
 )}
 </div>
 </div>
 <span
 className={`inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-semibold leading-none ${statusClass}`}
 >
 {statusLabel}
 </span>
 </div>
 {(item.summary || item.error || item.stop_reason) && (
 <p className="mt-1 text-xs text-[var(--text-muted)] break-words">
 {item.error || item.summary || item.stop_reason}
 </p>
 )}
 {(typeof item.execution_time_ms === 'number' ||
 typeof item.artifact_count === 'number' ||
 typeof item.document_count === 'number') && (
 <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
 {typeof item.execution_time_ms === 'number' && (
 <span>耗时 {formatDuration(item.execution_time_ms)}</span>
 )}
 {typeof item.artifact_count === 'number' && item.artifact_count > 0 && (
 <span>产物 {item.artifact_count}</span>
 )}
 {typeof item.document_count === 'number' && item.document_count > 0 && (
 <span>文档 {item.document_count}</span>
 )}
 </div>
 )}
 </div>
 )
 })}
 </div>
 </div>
 )
}

function formatDuration(durationMs: number): string {
 if (durationMs < 1000) return `${Math.max(1, durationMs)}ms`
 const seconds = Math.floor(durationMs / 1000)
 const minutes = Math.floor(seconds / 60)
 const remainSeconds = seconds % 60
 return minutes > 0 ? `${minutes}m ${remainSeconds}s` : `${remainSeconds}s`
}

/** 首次访问欢迎提示 */
function WelcomeHint() {
 const isSeen = useOnboardStore((s) => s.isSeen);
 const markSeen = useOnboardStore((s) => s.markSeen);
 if (isSeen("welcome")) return null;
 return (
 <OnboardHint
 title="欢迎使用 Nini"
 autoDismissMs={6000}
 onDismiss={() => markSeen("welcome")}
 >
 从模板快速开始科研分析，或直接在下方输入你的需求。
 试试输入 <code className="rounded bg-[var(--bg-elevated)] px-1 text-[var(--text-secondary)] dark:bg-[var(--bg-overlay)] dark:text-[var(--text-muted)]">/</code> 发现更多分析技能。
 </OnboardHint>
 );
}

export default function ChatPanel() {
 const confirm = useConfirm()
 // 数据 selector 合并，使用 useShallow 减少重渲染
 const {
 sessionId,
 appBootstrapping,
 messages,
 isStreaming,
 pendingAskUserQuestionsBySession,
 pendingAskUserQuestion,
 askUserQuestionNotificationPreference,
 currentIntentAnalysis,
 streamingMetrics,
 agentRuns,
 selectedRunId,
 } = useStore(
 useShallow((s) => ({
 sessionId: s.sessionId,
 appBootstrapping: s.appBootstrapping,
 messages: s.messages,
 isStreaming: s.isStreaming,
 pendingAskUserQuestionsBySession: s.pendingAskUserQuestionsBySession,
  pendingAskUserQuestion: s.pendingAskUserQuestion,
  askUserQuestionNotificationPreference: s.askUserQuestionNotificationPreference,
  currentIntentAnalysis: s.currentIntentAnalysis,
  streamingMetrics: s._streamingMetrics,
  agentRuns: s.agentRuns,
  selectedRunId: s.selectedRunId,
 })),
 )
 // 函数 selector 独立（Zustand 对函数引用稳定，不触发重渲染）
 const createNewSession = useStore((s) => s.createNewSession)
 const switchSession = useStore((s) => s.switchSession)
 const setAskUserQuestionNotificationPreference = useStore(
 (s) => s.setAskUserQuestionNotificationPreference,
 )
 const setComposerDraft = useStore((s) => s.setComposerDraft)
 const submitAskUserQuestionAnswers = useStore((s) => s.submitAskUserQuestionAnswers)
 const retryLastTurn = useStore((s) => s.retryLastTurn)
 const stopAgentRun = useStore((s) => s.stopAgentRun)
 const bottomRef = useRef<HTMLDivElement>(null)
 const selectedRun = useMemo(() => {
 if (!selectedRunId) return null
 return agentRuns[selectedRunId] ?? null
 }, [agentRuns, selectedRunId])
 const selectedSubagentRun = useMemo(() => {
 if (!selectedRun || selectedRun.runScope !== 'subagent') return null
 return selectedRun
 }, [selectedRun])
 const selectedDispatchRun = useMemo(() => {
 if (!selectedRun || selectedRun.runScope !== 'dispatch') return null
 return selectedRun
 }, [selectedRun])
 const displayMessages = useMemo(() => {
 if (!selectedSubagentRun) return messages
 return selectedSubagentRun.messages
 }, [messages, selectedSubagentRun])
 const [displayedTokenCount, setDisplayedTokenCount] = useState(() =>
 streamingMetrics.hasTokenUsage ? streamingMetrics.totalTokens : 0,
 )
 const [creatingSession, setCreatingSession] = useState(false)
 const displayedTokenCountRef = useRef(
 streamingMetrics.hasTokenUsage ? streamingMetrics.totalTokens : 0,
 )
 const [elapsedSeconds, setElapsedSeconds] = useState(0)

 // 找到最后一条用户消息用于重试逻辑
 const lastUserIndex = useMemo(() => {
 for (let i = messages.length - 1; i >= 0; i--) {
 if (messages[i].role === 'user') return i
 }
 return -1
 }, [messages])
 const lastUserMessageId = useMemo(() => {
 if (lastUserIndex < 0) return null
 return messages[lastUserIndex]?.id || null
 }, [messages, lastUserIndex])
 const canRetry = useMemo(() => {
 if (lastUserIndex < 0) return false
 return messages.slice(lastUserIndex + 1).some((m) => m.role !== 'user')
 }, [messages, lastUserIndex])
 const lastRetryableAssistantError = useMemo(() => {
 if (lastUserIndex < 0) return null
 for (let i = messages.length - 1; i >= 0; i--) {
 if (i <= lastUserIndex) break
 const msg = messages[i]
 if (msg.role !== 'assistant') continue
 const isErrorMessage = msg.isError || /^错误[:：]\s*/u.test(msg.content)
 if (!isErrorMessage) continue
 if (msg.retryable === false) continue
 return msg
 }
 return null
 }, [messages, lastUserIndex])
 const lastRetryableAssistantErrorId = lastRetryableAssistantError?.id || null
 const backgroundPendingQuestions = useMemo(() => {
 return Object.values(pendingAskUserQuestionsBySession)
 .filter((item) => item.sessionId !== sessionId)
 .sort((a, b) => b.attentionRequestedAt - a.attentionRequestedAt)
 }, [pendingAskUserQuestionsBySession, sessionId])
 const backgroundPendingQuestion = backgroundPendingQuestions[0] || null
 const canEnableNotifications = useMemo(() => {
 if (askUserQuestionNotificationPreference !== 'default') return false
 return typeof window !== 'undefined' && 'Notification' in window
 }, [askUserQuestionNotificationPreference])

 // 自动滚动到底部（100ms 防抖，避免 streaming 时频繁触发重排）
 useEffect(() => {
 const id = setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
 return () => clearTimeout(id)
 }, [displayMessages])

 useEffect(() => {
 if (!isStreaming || !streamingMetrics.startedAt) {
   setElapsedSeconds(0)
   return
 }

 const startedAt = streamingMetrics.startedAt
 const tick = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
 tick()
 const timer = window.setInterval(tick, 1000)
 return () => window.clearInterval(timer)
 }, [isStreaming, streamingMetrics.startedAt])



 const compactTokenText = useMemo(() => {
 if (!streamingMetrics.hasTokenUsage) return null
 return compactTokenFormatter.format(displayedTokenCount)
 }, [displayedTokenCount, streamingMetrics.hasTokenUsage])

 useEffect(() => {
 if (!isStreaming || !streamingMetrics.hasTokenUsage) {
 displayedTokenCountRef.current = 0
 setDisplayedTokenCount(0)
 return
 }

 const targetCount = streamingMetrics.totalTokens
 if (targetCount <= displayedTokenCountRef.current) {
 displayedTokenCountRef.current = targetCount
 setDisplayedTokenCount(targetCount)
 return
 }

 const startCount = displayedTokenCountRef.current
 const startAt = Date.now()
 const durationMs = 360
 let rafId: number
 const tick = () => {
 const elapsed = Date.now() - startAt
 const progress = Math.min(elapsed / durationMs, 1)
 const easedProgress = 1 - Math.pow(1 - progress, 3)
 const nextCount = Math.round(
 startCount + (targetCount - startCount) * easedProgress,
 )
 displayedTokenCountRef.current = nextCount
 setDisplayedTokenCount(nextCount)
 if (progress < 1) {
 rafId = requestAnimationFrame(tick)
 }
 }
 rafId = requestAnimationFrame(tick)
 return () => cancelAnimationFrame(rafId)
 }, [isStreaming, streamingMetrics.hasTokenUsage, streamingMetrics.totalTokens])

 const handleRetry = useCallback(async () => {
 if (isStreaming || !canRetry) return
 const confirmed = await confirm({
 title: '确认重试',
 message: '重试后将清空上一轮智能体已输出内容，是否继续？',
 confirmText: '重试',
 destructive: true,
 })
 if (!confirmed) return
 startTransition(() => {
 retryLastTurn()
 })
 }, [isStreaming, canRetry, retryLastTurn, confirm])

 const handleStopSelectedSubagent = useCallback(async () => {
 if (!selectedSubagentRun?.agentId || selectedSubagentRun.status !== 'running') return
 const confirmed = await confirm({
 title: `终止 ${selectedSubagentRun.agentName}`,
 message: '将停止当前子 Agent，已生成内容会保留在对话中，是否继续？',
 confirmText: '终止',
 destructive: true,
 })
 if (!confirmed) return
 stopAgentRun(selectedSubagentRun.runId, selectedSubagentRun.agentId)
 }, [confirm, selectedSubagentRun, stopAgentRun])

 const handleEnableNotifications = useCallback(async () => {
 if (typeof window === 'undefined' || !('Notification' in window)) return
 const permission = await window.Notification.requestPermission()
 if (permission === 'granted') {
 setAskUserQuestionNotificationPreference('enabled')
 return
 }
 if (permission === 'denied') {
 setAskUserQuestionNotificationPreference('denied')
 }
 }, [setAskUserQuestionNotificationPreference])

 const handleCreateSession = useCallback(async () => {
 if (creatingSession) return
 setCreatingSession(true)
 try {
 await createNewSession()
 } finally {
 setCreatingSession(false)
 }
 }, [createNewSession, creatingSession])

 const isNoSession = !sessionId
 const showBootstrapState = appBootstrapping
 const showConversationContent = !appBootstrapping
 const selectedRunDuration =
 selectedSubagentRun?.status === 'running'
 ? formatDuration(Math.max(0, Date.now() - selectedSubagentRun.startTime))
 : typeof selectedSubagentRun?.latestExecutionTimeMs === 'number'
 ? formatDuration(selectedSubagentRun.latestExecutionTimeMs)
 : null
 const selectedDispatchDuration =
 selectedDispatchRun?.status === 'running'
 ? formatDuration(Math.max(0, Date.now() - selectedDispatchRun.startTime))
 : typeof selectedDispatchRun?.latestExecutionTimeMs === 'number'
 ? formatDuration(selectedDispatchRun.latestExecutionTimeMs)
 : null
 const selectedDispatchLedger = useMemo(() => {
 if (!selectedDispatchRun) return []
 return renderDispatchLedgerBadges(selectedDispatchRun)
 }, [selectedDispatchRun])

 return (
 <div className="flex flex-col flex-1 min-h-0">
 {backgroundPendingQuestion && (
 <PendingQuestionBanner
 pending={backgroundPendingQuestion}
 additionalCount={Math.max(0, backgroundPendingQuestions.length - 1)}
 canEnableNotifications={canEnableNotifications}
 onSwitch={() => {
 startTransition(() => {
 void switchSession(backgroundPendingQuestion.sessionId)
 })
 }}
 onEnableNotifications={() => {
 void handleEnableNotifications()
 }}
 />
 )}
 {/* 消息列表 */}
 <div className="flex-1 overflow-y-auto px-4 py-6">
 <div className="relative max-w-3xl mx-auto">
 <div
 className={`transition-all duration-300 ${
 showBootstrapState
 ? 'opacity-100 translate-y-0'
 : 'pointer-events-none absolute inset-x-0 top-0 opacity-0 -translate-y-2'
 }`}
 >
{showBootstrapState && (
<div className="min-h-[60vh] px-1 py-4">
<div className="mx-auto max-w-2xl">
 <div className="skeleton-surface rounded-xl p-6 shadow-md">
<div className="flex items-center gap-4">
 <div className="h-14 w-14 rounded-lg bg-[var(--bg-elevated)] dark:bg-[var(--bg-overlay)]" />
 <div className="flex-1 space-y-2">
 <div className="skeleton-line h-4 w-40 rounded-full animate-pulse" />
 <div className="skeleton-line-soft h-3 w-72 max-w-full rounded-full animate-pulse" />
 </div>
 </div>
 <div className="mt-8 space-y-4">
 <div className="ml-auto max-w-[62%] rounded-xl rounded-br-xl bg-[color-mix(in_srgb,var(--bg-elevated)_92%,var(--bg-base))] px-5 py-4">
 <div className="skeleton-line h-3 w-28 rounded-full animate-pulse" />
 </div>
 <div className="skeleton-surface max-w-[72%] rounded-xl rounded-bl-xl px-5 py-4">
 <div className="space-y-2">
 <div className="skeleton-line h-3 w-5/6 rounded-full animate-pulse" />
 <div className="skeleton-line-soft h-3 w-2/3 rounded-full animate-pulse" />
 </div>
 </div>
 <div className="ml-auto max-w-[54%] rounded-xl rounded-br-xl bg-[color-mix(in_srgb,var(--bg-elevated)_92%,var(--bg-base))] px-5 py-4">
 <div className="skeleton-line h-3 w-24 rounded-full animate-pulse" />
 </div>
 </div>
 </div>
</div>
 </div>
 )}
 </div>

 <div
 className={`transition-all duration-300 ${
 showConversationContent ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
 }`}
 >
 {showConversationContent &&
 displayMessages.length === 0 &&
 !isNoSession &&
 !selectedSubagentRun && (
 <div className="min-h-[60vh] py-6 space-y-3">
 <WelcomeHint />
 <RecipeCenter />
 </div>
 )}

 {showConversationContent && isNoSession && (
 <div className="min-h-[60vh] py-6 space-y-5">
 <RecipeCenter />
 <div className="flex flex-col items-center justify-center text-[var(--text-muted)]">
 <h2 className="text-xl font-semibold text-[var(--text-secondary)] mb-2">或先开一个自由会话</h2>
 <p className="text-sm text-center max-w-md">
 你也可以直接进入普通对话，上传数据后自然语言描述分析需求。
 </p>
 <Button
 type="button"
 variant="secondary"
 onClick={() => { void handleCreateSession() }}
 disabled={creatingSession}
 loading={creatingSession}
 className="mt-5 rounded-xl px-4 py-2 text-sm shadow-sm"
 >
 {creatingSession ? '新建中...' : '新建会话'}
 </Button>
 </div>
 </div>
 )}
 {showConversationContent && <SkillProgressPanel />}
 {showConversationContent && selectedSubagentRun && (
 <div
 id="agent-run-thread-panel"
 className="mb-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-4 py-3 shadow-sm"
 >
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0 flex-1">
 <div className="flex flex-wrap items-start gap-2">
 <span className="text-xs font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">
 子 Agent 视图
 </span>
 <span
 className={`inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-semibold leading-none ${selectedRunStatusClass[selectedSubagentRun.status]}`}
 >
 {selectedRunStatusLabel[selectedSubagentRun.status]}
 </span>
 </div>
 <div className="mt-2 flex flex-wrap items-start gap-x-3 gap-y-1">
 <span className="text-sm font-semibold text-[var(--text-primary)]">
 {selectedSubagentRun.agentName}
 </span>
 <span className="text-xs text-[var(--text-secondary)]">
 尝试 {selectedSubagentRun.attempt}
 </span>
 {selectedRunDuration && (
 <span className="text-xs text-[var(--text-secondary)]">
 耗时 {selectedRunDuration}
 </span>
 )}
 </div>
 <p className="mt-2 text-xs text-[var(--text-secondary)] break-words">
 {selectedSubagentRun.task || '等待任务描述...'}
 </p>
 {selectedSubagentRun.progressMessage &&
 selectedSubagentRun.progressMessage !== selectedSubagentRun.task && (
 <p className="mt-1 text-xs text-[var(--text-muted)] break-words">
 {selectedSubagentRun.progressMessage}
 </p>
 )}
 </div>
 {selectedSubagentRun.status === 'running' && selectedSubagentRun.agentId && (
 <Button
 type="button"
 variant="danger"
 className="shrink-0 rounded-lg px-3"
 onClick={() => {
 void handleStopSelectedSubagent()
 }}
 >
 终止子 Agent
 </Button>
 )}
 </div>
 </div>
 )}
 {showConversationContent && selectedDispatchRun && (
 <div
 id="agent-run-thread-panel"
 className="mb-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-4 py-3 shadow-sm"
 >
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0 flex-1">
 <div className="flex flex-wrap items-start gap-2">
 <span className="text-xs font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">
 派发账本
 </span>
 <span
 className={`inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-semibold leading-none ${selectedRunStatusClass[selectedDispatchRun.status]}`}
 >
 {selectedRunStatusLabel[selectedDispatchRun.status]}
 </span>
 </div>
 <div className="mt-2 flex flex-wrap items-start gap-x-3 gap-y-1">
 <span className="text-sm font-semibold text-[var(--text-primary)]">
 {selectedDispatchRun.agentName}
 </span>
 <span className="text-xs text-[var(--text-secondary)]">
 尝试 {selectedDispatchRun.attempt}
 </span>
 {selectedDispatchDuration && (
 <span className="text-xs text-[var(--text-secondary)]">
 耗时 {selectedDispatchDuration}
 </span>
 )}
 </div>
 <p className="mt-2 text-xs text-[var(--text-secondary)] break-words">
 {selectedDispatchRun.progressMessage || selectedDispatchRun.summary || selectedDispatchRun.task}
 </p>
 {selectedDispatchLedger.length > 0 && (
 <div className="mt-3 flex flex-wrap gap-2">
 {selectedDispatchLedger.map((item) => (
 <span
 key={item}
 className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2 py-1 text-[11px] text-[var(--text-secondary)]"
 >
 {item}
 </span>
 ))}
 </div>
 )}
 {renderDispatchLedgerSection(selectedDispatchRun.dispatchLedger)}
 {renderDispatchFailureSection('预检失败明细', selectedDispatchRun.preflightFailures)}
 {renderDispatchFailureSection('路由失败明细', selectedDispatchRun.routingFailures)}
 {renderDispatchFailureSection('执行失败明细', selectedDispatchRun.executionFailures)}
 </div>
 </div>
 </div>
 )}
 {showConversationContent &&
 selectedSubagentRun &&
 displayMessages.length === 0 && (
 <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-6 text-sm text-[var(--text-secondary)]">
 当前子 Agent 还没有产出可展示的消息。
 </div>
 )}
 {/* 所有消息按原始顺序展示 */}
 {showConversationContent && displayMessages.map((msg) => {
 const isUser = msg.role === 'user'
 const isLastUser = isUser && msg.id === lastUserMessageId
 const showRetry =
 isUser &&
 msg.id === lastUserMessageId &&
 canRetry &&
 !lastRetryableAssistantErrorId

 return (
 <div key={msg.id} style={{ contentVisibility: 'auto', containIntrinsicSize: '0 200px' }}>
 <MessageBubble
 message={msg}
 showRetry={showRetry}
 onRetry={handleRetry}
 retryDisabled={isStreaming}
 />
 {/* 在最新消息后显示 IntentTimelineItem */}
 {isLastUser && currentIntentAnalysis && (
 <IntentTimelineItem
 analysis={currentIntentAnalysis}
 onApplySuggestion={setComposerDraft}
 isActive={!isStreaming}
 />
 )}
 </div>
 )
 })}
 </div>

 {isStreaming && (
 <div className="flex items-center gap-2 text-[var(--text-muted)] text-sm ml-11">
 <Loader2 size={14} className="animate-spin" />
 <span>Nini is working...</span>
 <span className="text-[var(--text-muted)]/90">{elapsedSeconds}s</span>
 {compactTokenText && (
 <span className="text-[var(--text-muted)]/90">·</span>
 )}
 {compactTokenText && (
 <span
 data-testid="streaming-token-usage"
 className="inline-flex items-center tabular-nums text-[var(--text-muted)]/90"
 >
 ↓ {compactTokenText} tokens
 </span>
 )}
 </div>
 )}
 {!isStreaming && lastRetryableAssistantError && (
 <div className="ml-11 mb-4 rounded-xl border border-[var(--error)] bg-[var(--accent-subtle)] px-4 py-3 text-sm">
 <div className="font-medium text-[var(--error)]">
 {lastRetryableAssistantError.errorHint || '模型调用异常，请稍后重试。'}
 </div>
 <Button
 variant="danger"
 onClick={handleRetry}
 className="mt-2 rounded-lg border border-[var(--error)] px-3 py-1 text-xs text-[var(--error)]"
 >
 重试上一轮
 </Button>
 </div>
 )}

 <div ref={bottomRef} />
 </div>
 </div>

 {/* 输入区 */}
 {!appBootstrapping && !isNoSession && pendingAskUserQuestion && (
 <AskUserQuestionPanel
 pending={pendingAskUserQuestion}
 onSubmit={submitAskUserQuestionAnswers}
 />
 )}
 {!appBootstrapping && !isNoSession && <ChatInputArea />}
 </div>
 )
}
