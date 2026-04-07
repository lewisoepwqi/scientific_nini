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

 it('选中 dispatch 线程时应展示派发账本和预检失败明细', () => {
 mockState = {
 ...mockState,
 isStreaming: false,
 selectedRunId: 'dispatch:call-1',
 agentRuns: {
 'dispatch:call-1': {
 runId: 'dispatch:call-1',
 turnId: 'turn-1',
 parentRunId: 'root:turn-1',
 runScope: 'dispatch',
 agentId: 'dispatch_agents',
 agentName: '任务派发',
 status: 'running',
 task: '多 Agent 任务派发',
 attempt: 1,
 retryCount: 0,
 startTime: new Date('2026-03-04T12:00:10Z').getTime(),
 updatedAt: new Date('2026-03-04T12:00:36Z').getTime(),
 latestExecutionTimeMs: null,
 progressMessage: '第 1/2 波次预检：可执行 2 个，预检失败 1 个',
 preflightFailureCount: 1,
 routingFailureCount: 1,
 executionFailureCount: 0,
 runnableCount: 2,
 preflightFailures: [
 {
 agent_id: 'statistician',
 task: '执行正态性检验',
 error: '模型额度不足',
 },
 ],
 routingFailures: [
 {
 agent_id: 'router_guard',
 task: '识别干预标记',
 error: '未找到可用 agent',
 },
 ],
 executionFailures: [
 {
 agent_id: 'viz_designer',
 task: '绘制散点图',
 error: 'Plotly 导出失败',
 },
 ],
 dispatchLedger: [
 {
 agent_id: 'data_cleaner',
 agent_name: '数据清洗',
 task: '标准化列名',
 status: 'success',
 stop_reason: '',
 summary: '已完成清洗',
 error: '',
 execution_time_ms: 1200,
 artifact_count: 1,
 document_count: 0,
 },
 {
 agent_id: 'scheduler',
 agent_name: '调度器',
 task: '等待人工确认',
 status: 'stopped',
 stop_reason: 'user_stopped',
 summary: '用户手动终止',
 error: '',
 execution_time_ms: 50,
 artifact_count: 0,
 document_count: 0,
 },
 ],
 messages: [],
 },
 },
 }

 render(<ChatPanel />)

 expect(screen.getByText('派发账本')).toBeInTheDocument()
 expect(screen.getByText('任务派发')).toBeInTheDocument()
 expect(screen.getByText('可执行 2')).toBeInTheDocument()
 expect(screen.getByText('预检失败 1')).toBeInTheDocument()
 expect(screen.getByText('路由失败 1')).toBeInTheDocument()
 expect(screen.getByText('子任务账本')).toBeInTheDocument()
 expect(screen.getByText('数据清洗')).toBeInTheDocument()
 expect(screen.getByText('已完成清洗')).toBeInTheDocument()
 expect(screen.getByText('成功')).toBeInTheDocument()
 expect(screen.getByText('调度器')).toBeInTheDocument()
 expect(screen.getByText('用户手动终止')).toBeInTheDocument()
 expect(screen.getByText('已停止')).toBeInTheDocument()
 expect(screen.getByText('预检失败明细')).toBeInTheDocument()
 expect(screen.getByText('执行正态性检验')).toBeInTheDocument()
 expect(screen.getByText('模型额度不足')).toBeInTheDocument()
 expect(screen.getByText('路由失败明细')).toBeInTheDocument()
 expect(screen.getByText('识别干预标记')).toBeInTheDocument()
 expect(screen.getByText('未找到可用 agent')).toBeInTheDocument()
 expect(screen.getByText('执行失败明细')).toBeInTheDocument()
 expect(screen.getByText('绘制散点图')).toBeInTheDocument()
 expect(screen.getByText('Plotly 导出失败')).toBeInTheDocument()
 expect(screen.queryByRole('button', { name: '终止子 Agent' })).not.toBeInTheDocument()
 })
})
