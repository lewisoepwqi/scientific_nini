/**
 * 对话主面板 —— 消息列表 + 输入框，居中限宽，输入框自适应高度。
 * 按 turnId 对 Agent 消息进行分组折叠。
 */
import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useStore, type Message } from '../store'
import MessageBubble from './MessageBubble'
import AgentTurnGroup from './AgentTurnGroup'
import FileUpload from './FileUpload'
import ModelSelector from './ModelSelector'
import { Send, Loader2, Square, Archive } from 'lucide-react'

/** 消息分组：用户消息独立，同一 turnId 的 agent 消息合并为一组 */
interface MessageGroup {
  type: 'user' | 'agent-turn'
  messages: Message[]
  key: string
}

interface ContextSizeData {
  total_context_tokens?: number
  compress_threshold_tokens?: number
  compress_target_tokens?: number
}

function groupMessages(messages: Message[]): MessageGroup[] {
  const groups: MessageGroup[] = []
  let currentTurnId: string | null = null
  let currentGroup: Message[] = []

  const flushGroup = () => {
    if (currentGroup.length > 0) {
      groups.push({
        type: 'agent-turn',
        messages: currentGroup,
        key: currentTurnId || currentGroup[0].id,
      })
      currentGroup = []
      currentTurnId = null
    }
  }

  for (const msg of messages) {
    if (msg.role === 'user') {
      flushGroup()
      groups.push({ type: 'user', messages: [msg], key: msg.id })
      continue
    }

    // agent/tool 消息：按 turnId 分组
    const turnId = msg.turnId || null

    if (turnId && turnId === currentTurnId) {
      // 同一 turn，加入当前组
      currentGroup.push(msg)
    } else {
      // 新 turn 或无 turnId
      flushGroup()
      currentTurnId = turnId
      currentGroup = [msg]
    }
  }

  flushGroup()
  return groups
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, value))
}

function computeRemainingRatio(totalTokens: number, thresholdTokens: number, targetTokens: number): number {
  if (thresholdTokens <= 0) return 1
  if (thresholdTokens <= targetTokens) {
    return clamp01((thresholdTokens - totalTokens) / thresholdTokens)
  }
  if (totalTokens <= targetTokens) return 1
  const windowSize = thresholdTokens - targetTokens
  return clamp01(1 - (totalTokens - targetTokens) / windowSize)
}

export default function ChatPanel() {
  const sessionId = useStore((s) => s.sessionId)
  const messages = useStore((s) => s.messages)
  const contextCompressionTick = useStore((s) => s.contextCompressionTick)
  const isStreaming = useStore((s) => s.isStreaming)
  const sendMessage = useStore((s) => s.sendMessage)
  const stopStreaming = useStore((s) => s.stopStreaming)
  const retryLastTurn = useStore((s) => s.retryLastTurn)
  const uploadFile = useStore((s) => s.uploadFile)
  const compressCurrentSession = useStore((s) => s.compressCurrentSession)
  const isUploading = useStore((s) => s.isUploading)
  const [input, setInput] = useState('')
  const [isDragActive, setIsDragActive] = useState(false)
  const [isCompressing, setIsCompressing] = useState(false)
  const [contextRemainingRatio, setContextRemainingRatio] = useState(1)
  const [contextTokens, setContextTokens] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const dragDepthRef = useRef(0)

  const messageGroups = useMemo(() => groupMessages(messages), [messages])
  const lastUserMessageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') return messages[i].id
    }
    return null
  }, [messages])
  const canRetry = useMemo(() => {
    let lastUserIndex = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        lastUserIndex = i
        break
      }
    }
    if (lastUserIndex < 0) return false
    return messages.slice(lastUserIndex + 1).some((m) => m.role !== 'user')
  }, [messages])

  const refreshContextBudget = useCallback(async () => {
    if (!sessionId) {
      setContextRemainingRatio(1)
      setContextTokens(null)
      return
    }
    try {
      const resp = await fetch(`/api/sessions/${sessionId}/context-size`)
      const payload = await resp.json()
      if (!payload.success) return
      const data = (payload.data || {}) as ContextSizeData
      const totalTokens = typeof data.total_context_tokens === 'number' ? data.total_context_tokens : 0
      const thresholdTokens =
        typeof data.compress_threshold_tokens === 'number' ? data.compress_threshold_tokens : 30000
      const targetTokens =
        typeof data.compress_target_tokens === 'number' ? data.compress_target_tokens : 15000
      setContextTokens(totalTokens)
      setContextRemainingRatio(computeRemainingRatio(totalTokens, thresholdTokens, targetTokens))
    } catch {
      // 忽略网络异常，保留当前进度
    }
  }, [sessionId])

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 会话上下文空间估计
  useEffect(() => {
    void refreshContextBudget()
  }, [refreshContextBudget, messages.length])

  // 切换会话后重置进度条
  useEffect(() => {
    setContextRemainingRatio(1)
    setContextTokens(null)
  }, [sessionId])

  // 自动或手动压缩后回到初始进度，再同步一次最新值
  useEffect(() => {
    if (contextCompressionTick <= 0) return
    setContextRemainingRatio(1)
    void refreshContextBudget()
  }, [contextCompressionTick, refreshContextBudget])

  // 输入框自适应高度
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [input, adjustHeight])

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || isStreaming) return
    sendMessage(text)
    setInput('')
    // 重置高度
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [input, isStreaming, sendMessage])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleStop = useCallback(() => {
    if (!isStreaming) return
    stopStreaming()
  }, [isStreaming, stopStreaming])

  const handleRetry = useCallback(() => {
    if (isStreaming || !canRetry) return
    const confirmed = window.confirm('重试后将清空上一轮智能体已输出内容，是否继续？')
    if (!confirmed) return
    retryLastTurn()
  }, [isStreaming, canRetry, retryLastTurn])

  const handleCompress = useCallback(async () => {
    if (isStreaming || isCompressing) return
    const confirmed = window.confirm('将压缩当前会话的早期消息并归档，是否继续？')
    if (!confirmed) return
    setIsCompressing(true)
    const result = await compressCurrentSession()
    setIsCompressing(false)
    if (result.success) {
      setContextRemainingRatio(1)
      void refreshContextBudget()
    }
    const feedback: Message = {
      id: `compress-${Date.now()}`,
      role: 'assistant',
      content: result.success ? result.message : `错误: ${result.message}`,
      timestamp: Date.now(),
    }
    useStore.setState((s) => ({ messages: [...s.messages, feedback] }))
  }, [isStreaming, isCompressing, compressCurrentSession, refreshContextBudget])

  const uploadFilesSequentially = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        await uploadFile(file)
      }
    },
    [uploadFile],
  )

  const isFileDragEvent = useCallback((e: React.DragEvent) => {
    return Array.from(e.dataTransfer.types || []).includes('Files')
  }, [])

  const handleComposerDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return
      e.preventDefault()
      if (isUploading) return
      dragDepthRef.current += 1
      setIsDragActive(true)
    },
    [isFileDragEvent, isUploading],
  )

  const handleComposerDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return
      e.preventDefault()
      if (isUploading) return
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
      if (dragDepthRef.current === 0) {
        setIsDragActive(false)
      }
    },
    [isFileDragEvent, isUploading],
  )

  const handleComposerDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return
      e.preventDefault()
      if (isUploading) return
      if (!isDragActive) setIsDragActive(true)
    },
    [isDragActive, isFileDragEvent, isUploading],
  )

  const handleComposerDrop = useCallback(
    (e: React.DragEvent) => {
      if (!isFileDragEvent(e)) return
      e.preventDefault()
      if (isUploading) return
      dragDepthRef.current = 0
      setIsDragActive(false)
      const files = Array.from(e.dataTransfer.files || [])
      if (files.length > 0) {
        void uploadFilesSequentially(files)
      }
    },
    [isFileDragEvent, isUploading, uploadFilesSequentially],
  )

  const compressLevel =
    contextRemainingRatio > 0.66 ? 'safe' : contextRemainingRatio > 0.33 ? 'warning' : 'critical'
  const compressProgressColor =
    compressLevel === 'safe'
      ? 'rgba(16, 185, 129, 0.28)'
      : compressLevel === 'warning'
        ? 'rgba(249, 115, 22, 0.26)'
        : 'rgba(239, 68, 68, 0.26)'
  const compressTextColor =
    compressLevel === 'safe'
      ? 'text-emerald-700'
      : compressLevel === 'warning'
        ? 'text-orange-700'
        : 'text-red-700'
  const contextUsageRatio = clamp01(1 - contextRemainingRatio)
  const usagePercent = Math.round(contextUsageRatio * 100)

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center min-h-[60vh] text-gray-400">
              <div className="text-5xl mb-4">🔬</div>
              <h2 className="text-xl font-semibold text-gray-600 mb-2">Nini 科研分析助手</h2>
              <p className="text-sm text-center max-w-md">
                上传数据文件，然后用自然语言描述你的分析需求。
                <br />
                例如："帮我对 treatment 组和 control 组做 t 检验"
              </p>
            </div>
          )}

          {messageGroups.map((group) => {
            if (group.type === 'user') {
              const userMessage = group.messages[0]
              const showRetry = userMessage.id === lastUserMessageId && canRetry
              return (
                <MessageBubble
                  key={group.key}
                  message={userMessage}
                  showRetry={showRetry}
                  onRetry={handleRetry}
                  retryDisabled={isStreaming}
                />
              )
            }
            // Agent turn 分组
            return <AgentTurnGroup key={group.key} messages={group.messages} />
          })}

          {isStreaming && (
            <div className="flex items-center gap-2 text-gray-400 text-sm ml-11">
              <Loader2 size={14} className="animate-spin" />
              思考中...
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* 输入区 */}
      <div className="border-t bg-white px-4 py-3">
        <div className="max-w-3xl mx-auto">
          <div
            className="relative rounded-2xl border border-gray-200 bg-white px-3 py-2 shadow-sm"
            onDragEnter={handleComposerDragEnter}
            onDragLeave={handleComposerDragLeave}
            onDragOver={handleComposerDragOver}
            onDrop={handleComposerDrop}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="描述你的分析需求..."
              rows={1}
              className="w-full resize-none border-0 bg-transparent px-1 py-1.5 text-sm
                         focus:outline-none placeholder:text-gray-400"
              style={{ minHeight: '42px' }}
            />

            <div className="mt-2 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <FileUpload />
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <ModelSelector compact menuDirection="up" align="right" />
                <button
                  onClick={() => void handleCompress()}
                  disabled={isStreaming || isCompressing || messages.length < 4}
                  className={`relative h-8 px-2.5 rounded-2xl border text-xs inline-flex items-center gap-1.5
                             overflow-hidden transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                               compressTextColor
                             } ${
                               compressLevel === 'safe'
                                 ? 'border-emerald-200 hover:bg-emerald-50/60'
                                 : compressLevel === 'warning'
                                   ? 'border-orange-200 hover:bg-orange-50/60'
                                   : 'border-red-200 hover:bg-red-50/60'
                             }`}
                  title={
                    contextTokens === null
                      ? '压缩会话'
                      : `压缩会话（占用 ${usagePercent}% · 当前 ${contextTokens.toLocaleString()} tok）`
                  }
                >
                  <span
                    className="absolute left-0 top-0 h-full rounded-2xl transition-all duration-300 ease-out"
                    style={{
                      width: `${usagePercent}%`,
                      backgroundColor: compressProgressColor,
                    }}
                  />
                  <span className="relative z-10 inline-flex items-center gap-1.5">
                  <Archive size={12} />
                  <span>{isCompressing ? '压缩中' : '压缩'}</span>
                  <span className="text-[10px] tabular-nums">{usagePercent}%</span>
                  </span>
                </button>
                {isStreaming ? (
                  <button
                    onClick={handleStop}
                    className="flex-shrink-0 w-10 h-10 rounded-2xl bg-red-500 text-white
                               flex items-center justify-center hover:bg-red-600 transition-colors"
                    title="停止生成"
                  >
                    <Square size={14} />
                  </button>
                ) : (
                  <button
                    onClick={handleSend}
                    disabled={!input.trim()}
                    className="flex-shrink-0 w-10 h-10 rounded-2xl bg-blue-600 text-white
                               flex items-center justify-center
                               hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed
                               transition-colors"
                  >
                    <Send size={16} />
                  </button>
                )}
              </div>
            </div>

            {isDragActive && (
              <div className="pointer-events-none absolute inset-0 rounded-2xl border-2 border-blue-500 bg-blue-50/80 flex items-center justify-center text-sm font-medium text-blue-600">
                释放以上传文件（支持多文件）
              </div>
            )}
          </div>

          <div className="mt-1 px-1 text-[11px] text-gray-400">
            Enter 发送，Shift + Enter 换行，可直接拖拽文件到输入框
          </div>
        </div>
      </div>
    </div>
  )
}
