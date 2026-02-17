/**
 * 对话主面板 —— 消息列表 + 输入框，居中限宽。
 * 输入区提取为 ChatInputArea，避免每次击键触发消息列表重渲染。
 * 按 turnId 对 Agent 消息进行分组折叠。
 */
import { useEffect, useRef, useMemo, useCallback } from 'react'
import { useStore, type Message } from '../store'
import MessageBubble from './MessageBubble'
import AgentTurnGroup from './AgentTurnGroup'
import ChatInputArea from './ChatInputArea'
import { Loader2 } from 'lucide-react'
import AnalysisPlanHeader from './AnalysisPlanHeader'
import { isAnalysisPlanHeaderV2Enabled } from '../featureFlags'

/** 消息分组：用户消息独立，同一 turnId 的 agent 消息合并为一组 */
interface MessageGroup {
  type: 'user' | 'agent-turn'
  messages: Message[]
  key: string
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

export default function ChatPanel() {
  const messages = useStore((s) => s.messages)
  const isStreaming = useStore((s) => s.isStreaming)
  const analysisPlanProgress = useStore((s) => s.analysisPlanProgress)
  const retryLastTurn = useStore((s) => s.retryLastTurn)
  const bottomRef = useRef<HTMLDivElement>(null)
  const planHeaderEnabled = useMemo(() => isAnalysisPlanHeaderV2Enabled(), [])
  const showPlanHeader = Boolean(
    planHeaderEnabled &&
      analysisPlanProgress &&
      analysisPlanProgress.total_steps > 0,
  )

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

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleRetry = useCallback(() => {
    if (isStreaming || !canRetry) return
    const confirmed = window.confirm('重试后将清空上一轮智能体已输出内容，是否继续？')
    if (!confirmed) return
    retryLastTurn()
  }, [isStreaming, canRetry, retryLastTurn])

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {showPlanHeader && analysisPlanProgress && (
        <AnalysisPlanHeader plan={analysisPlanProgress} />
      )}

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
      <ChatInputArea />
    </div>
  )
}
