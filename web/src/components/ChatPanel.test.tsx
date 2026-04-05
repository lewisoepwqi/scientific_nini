import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPanel from './ChatPanel'

let mockState: Record<string, unknown>
const mockConfirm = vi.fn()

vi.mock('../store', () => ({
 useStore: (selector: (state: Record<string, unknown>) => unknown) => selector(mockState),
}))

vi.mock('../store/confirm-store', () => ({
 useConfirm: () => mockConfirm,
}))

vi.mock('./MessageBubble', () => ({
 default: () => <div>message</div>,
}))

vi.mock('./ChatInputArea', () => ({
 default: () => <div>input</div>,
}))

vi.mock('./AskUserQuestionPanel', () => ({
 default: () => <div>question-panel</div>,
}))

vi.mock('./IntentTimelineItem', () => ({
 default: () => <div>intent-timeline</div>,
}))

vi.mock('./RecipeCenter', () => ({
 default: () => <div>recipe-center</div>,
}))

describe('ChatPanel', () => {
 beforeEach(() => {
 vi.useFakeTimers()
 vi.setSystemTime(new Date('2026-03-04T12:00:37Z'))
 Element.prototype.scrollIntoView = vi.fn()
 mockState = {
 sessionId: 'session-1',
 appBootstrapping: false,
 messages: [],
 isStreaming: true,
 switchSession: vi.fn(),
 createNewSession: vi.fn(),
 pendingAskUserQuestionsBySession: {},
 pendingAskUserQuestion: null,
 askUserQuestionNotificationPreference: 'default',
 setAskUserQuestionNotificationPreference: vi.fn(),
 currentIntentAnalysis: null,
 agentRuns: {},
 selectedRunId: null,
 stopAgentRun: vi.fn(),
 _streamingMetrics: {
 startedAt: new Date('2026-03-04T12:00:00Z').getTime(),
 turnId: 'turn-1',
 totalTokens: 820,
 hasTokenUsage: true,
 },
 setComposerDraft: vi.fn(),
 submitAskUserQuestionAnswers: vi.fn(),
 retryLastTurn: vi.fn(),
 }
 mockConfirm.mockReset()
 mockConfirm.mockResolvedValue(true)
 })

 afterEach(() => {
 vi.useRealTimers()
 })

 it('streaming 时应显示运行时长和 token 消耗', () => {
 render(<ChatPanel />)

 expect(screen.getByText('Nini is working...')).toBeInTheDocument()
 expect(screen.getByText('37s')).toBeInTheDocument()
 expect(screen.getByTestId('streaming-token-usage')).toHaveTextContent('↓ 820 tokens')
 })

 it('没有 token usage 时只显示运行时长', () => {
 mockState = {
 ...mockState,
 _streamingMetrics: {
 startedAt: new Date('2026-03-04T12:00:00Z').getTime(),
 turnId: 'turn-1',
 totalTokens: 0,
 hasTokenUsage: false,
 },
 }

 render(<ChatPanel />)

 expect(screen.getByText('37s')).toBeInTheDocument()
 expect(screen.queryByText(/tokens/u)).not.toBeInTheDocument()
 })

 it('token 增长后应以滚动计数方式变化并使用紧凑格式', () => {
 const { rerender } = render(<ChatPanel />)

 mockState = {
 ...mockState,
 _streamingMetrics: {
 startedAt: new Date('2026-03-04T12:00:00Z').getTime(),
 turnId: 'turn-1',
 totalTokens: 14200,
 hasTokenUsage: true,
 },
 }

 rerender(<ChatPanel />)

 expect(screen.getByTestId('streaming-token-usage')).toHaveTextContent('↓ 820 tokens')

 act(() => {
 vi.advanceTimersByTime(180)
 })
 expect(screen.getByTestId('streaming-token-usage')).not.toHaveTextContent('↓ 820 tokens')

 act(() => {
 vi.advanceTimersByTime(220)
 })
 expect(screen.getByTestId('streaming-token-usage')).toHaveTextContent('↓ 14.2K tokens')
 })

 it('后台会话存在待回答问题时应显示切换提醒条', () => {
 mockState = {
 ...mockState,
 pendingAskUserQuestionsBySession: {
 'session-2': {
 sessionId: 'session-2',
 sessionTitle: '后台会话',
 toolCallId: 'tool-ask-1',
 questions: [],
 questionCount: 1,
 createdAt: Date.now(),
 attentionRequestedAt: Date.now(),
 },
 },
 }

 render(<ChatPanel />)

 expect(screen.getByText('会话“后台会话”正在等待你的回答')).toBeInTheDocument()
 expect(screen.getByRole('button', { name: '切换并处理' })).toBeInTheDocument()
 })

 it('选中运行中的子 agent 时应通过确认对话框终止', async () => {
 const stopAgentRun = vi.fn()
 mockState = {
 ...mockState,
 isStreaming: false,
 selectedRunId: 'agent:turn-1:search:1',
 agentRuns: {
 'agent:turn-1:search:1': {
 runId: 'agent:turn-1:search:1',
 turnId: 'turn-1',
 parentRunId: 'root:turn-1',
 runScope: 'subagent',
 agentId: 'search',
 agentName: '文献检索',
 status: 'running',
 task: '检索近五年论文',
 attempt: 2,
 retryCount: 1,
 startTime: new Date('2026-03-04T12:00:10Z').getTime(),
 updatedAt: new Date('2026-03-04T12:00:36Z').getTime(),
 latestExecutionTimeMs: null,
 progressMessage: '正在汇总候选文献',
 messages: [],
 },
 },
 stopAgentRun,
 }

 render(<ChatPanel />)

 expect(screen.getByText('子 Agent 视图')).toBeInTheDocument()
 expect(screen.getByText('文献检索')).toBeInTheDocument()
 expect(screen.getByRole('button', { name: '终止子 Agent' })).toBeInTheDocument()

 await act(async () => {
 fireEvent.click(screen.getByRole('button', { name: '终止子 Agent' }))
 })

 expect(mockConfirm).toHaveBeenCalledWith(
 expect.objectContaining({
 title: '终止 文献检索',
 confirmText: '终止',
 destructive: true,
 }),
 )
 expect(stopAgentRun).toHaveBeenCalledWith('agent:turn-1:search:1', 'search')
 })
})
