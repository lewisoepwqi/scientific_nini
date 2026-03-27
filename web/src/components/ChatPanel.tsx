/**
 * 对话主面板 —— 消息列表 + 输入框，居中限宽。
 * 输入区提取为 ChatInputArea，避免每次击键触发消息列表重渲染。
 * 所有消息按原始顺序展示，保持思考-行动-回答的连贯性。
 *
 * 注意：分析计划仍只在工作区的“任务”Tab 中展示，Skill 进度面板会在对话区顶部显示
 */
import { useEffect, useRef, useMemo, useCallback, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useStore } from '../store'
import MessageBubble from './MessageBubble'
import ChatInputArea from './ChatInputArea'
import AskUserQuestionPanel from './AskUserQuestionPanel'
import PendingQuestionBanner from './PendingQuestionBanner'
import IntentTimelineItem from './IntentTimelineItem'
import { Loader2 } from 'lucide-react'
import RecipeCenter from './RecipeCenter'
import DeepTaskProgressCard from './DeepTaskProgressCard'
import SkillProgressPanel from './SkillProgressPanel'

const compactTokenFormatter = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  compactDisplay: 'short',
  maximumFractionDigits: 1,
})

export default function ChatPanel() {
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
  const bottomRef = useRef<HTMLDivElement>(null)
  const [displayedTokenCount, setDisplayedTokenCount] = useState(() =>
    streamingMetrics.hasTokenUsage ? streamingMetrics.totalTokens : 0,
  )
  const [creatingSession, setCreatingSession] = useState(false)
  const displayedTokenCountRef = useRef(
    streamingMetrics.hasTokenUsage ? streamingMetrics.totalTokens : 0,
  )
  const [now, setNow] = useState(() => Date.now())

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

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (!isStreaming || !streamingMetrics.startedAt) return

    setNow(Date.now())
    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 1000)

    return () => window.clearInterval(timer)
  }, [isStreaming, streamingMetrics.startedAt])

  const elapsedSeconds = useMemo(() => {
    if (!isStreaming || !streamingMetrics.startedAt) return 0
    return Math.max(0, Math.floor((now - streamingMetrics.startedAt) / 1000))
  }, [isStreaming, now, streamingMetrics.startedAt])

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
    const timer = window.setInterval(() => {
      const elapsed = Date.now() - startAt
      const progress = Math.min(elapsed / durationMs, 1)
      const easedProgress = 1 - Math.pow(1 - progress, 3)
      const nextCount = Math.round(
        startCount + (targetCount - startCount) * easedProgress,
      )

      displayedTokenCountRef.current = nextCount
      setDisplayedTokenCount(nextCount)

      if (progress >= 1) {
        window.clearInterval(timer)
      }
    }, 16)

    return () => window.clearInterval(timer)
  }, [isStreaming, streamingMetrics.hasTokenUsage, streamingMetrics.totalTokens])

  const handleRetry = useCallback(() => {
    if (isStreaming || !canRetry) return
    const confirmed = window.confirm('重试后将清空上一轮智能体已输出内容，是否继续？')
    if (!confirmed) return
    retryLastTurn()
  }, [isStreaming, canRetry, retryLastTurn])

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

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {backgroundPendingQuestion && (
        <PendingQuestionBanner
          pending={backgroundPendingQuestion}
          additionalCount={Math.max(0, backgroundPendingQuestions.length - 1)}
          canEnableNotifications={canEnableNotifications}
          onSwitch={() => {
            void switchSession(backgroundPendingQuestion.sessionId)
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
                <div className="rounded-[28px] border border-slate-200/80 bg-white/90 dark:border-slate-700/60 dark:bg-slate-800/90 p-6 shadow-[0_18px_45px_-32px_rgba(15,23,42,0.45)]">
                  <div className="flex items-center gap-4">
                    <div className="h-14 w-14 rounded-2xl bg-gradient-to-br from-sky-100 to-teal-50 dark:from-sky-900/40 dark:to-teal-900/40" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-40 rounded-full bg-slate-200 dark:bg-slate-600 animate-pulse" />
                      <div className="h-3 w-72 max-w-full rounded-full bg-slate-100 dark:bg-slate-700 animate-pulse" />
                    </div>
                  </div>
                  <div className="mt-8 space-y-4">
                    <div className="ml-auto max-w-[62%] rounded-3xl rounded-br-xl bg-slate-100/90 dark:bg-slate-700/70 px-5 py-4">
                      <div className="h-3 w-28 rounded-full bg-slate-200 dark:bg-slate-600 animate-pulse" />
                    </div>
                    <div className="max-w-[72%] rounded-3xl rounded-bl-xl border border-slate-200/80 bg-white dark:border-slate-600/60 dark:bg-slate-800 px-5 py-4">
                      <div className="space-y-2">
                        <div className="h-3 w-5/6 rounded-full bg-slate-200 dark:bg-slate-600 animate-pulse" />
                        <div className="h-3 w-2/3 rounded-full bg-slate-100 dark:bg-slate-700 animate-pulse" />
                      </div>
                    </div>
                    <div className="ml-auto max-w-[54%] rounded-3xl rounded-br-xl bg-slate-100/90 dark:bg-slate-700/70 px-5 py-4">
                      <div className="h-3 w-24 rounded-full bg-slate-200 dark:bg-slate-600 animate-pulse" />
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
          {showConversationContent && messages.length === 0 && !isNoSession && (
            <div className="min-h-[60vh] py-6">
              <RecipeCenter />
            </div>
          )}

          {showConversationContent && isNoSession && (
            <div className="min-h-[60vh] py-6 space-y-5">
              <RecipeCenter />
              <div className="flex flex-col items-center justify-center text-gray-400 dark:text-slate-500">
                <h2 className="text-xl font-semibold text-gray-600 dark:text-slate-300 mb-2">或先开一个自由会话</h2>
                <p className="text-sm text-center max-w-md">
                  你也可以直接进入普通对话，上传数据后自然语言描述分析需求。
                </p>
                <button
                  type="button"
                  onClick={() => { void handleCreateSession() }}
                  disabled={creatingSession}
                  className="mt-5 rounded-xl border border-slate-200 bg-white dark:border-slate-600 dark:bg-slate-800 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
                >
                  {creatingSession ? '新建中...' : '新建会话'}
                </button>
              </div>
            </div>
          )}
          {showConversationContent && <DeepTaskProgressCard />}
          {showConversationContent && <SkillProgressPanel />}
          {/* 所有消息按原始顺序展示 */}
          {showConversationContent && messages.map((msg) => {
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
            <div className="flex items-center gap-2 text-gray-400 dark:text-slate-500 text-sm ml-11">
              <Loader2 size={14} className="animate-spin" />
              <span>Nini is working...</span>
              <span className="text-gray-400/90 dark:text-slate-500/90">{elapsedSeconds}s</span>
              {compactTokenText && (
                <span className="text-gray-400/90 dark:text-slate-500/90">·</span>
              )}
              {compactTokenText && (
                <span
                  data-testid="streaming-token-usage"
                  className="inline-flex items-center tabular-nums text-gray-400/90 dark:text-slate-500/90"
                >
                  ↓ {compactTokenText} tokens
                </span>
              )}
            </div>
          )}
          {!isStreaming && lastRetryableAssistantError && (
            <div className="ml-11 mb-4 rounded-xl border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20 px-4 py-3 text-sm">
              <div className="font-medium text-red-700 dark:text-red-400">
                {lastRetryableAssistantError.errorHint || '模型调用异常，请稍后重试。'}
              </div>
              <button
                onClick={handleRetry}
                className="mt-2 inline-flex items-center rounded-lg border border-red-200 bg-white dark:border-red-800 dark:bg-slate-800 px-3 py-1 text-xs font-medium text-red-700 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
              >
                重试上一轮
              </button>
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
