import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import CodeExecutionPanel from './CodeExecutionPanel'
import { useStore, type CodeExecution } from '../store'

vi.mock('./downloadBundle', () => ({
  downloadSingleBundle: vi.fn().mockResolvedValue(undefined),
  downloadBatchBundle: vi.fn().mockResolvedValue(undefined),
}))

import { downloadSingleBundle, downloadBatchBundle } from './downloadBundle'

function makeExec(overrides: Partial<CodeExecution>): CodeExecution {
  return {
    id: 'abc12345',
    session_id: 'sess',
    code: 'x = 1',
    output: 'ok',
    status: 'success',
    language: 'python',
    tool_name: 'run_code',
    tool_args: { purpose: 'exploration' },
    created_at: '2026-04-19T10:00:00Z',
    output_resource_ids: [],
    intent: '测试',
    ...overrides,
  } as CodeExecution
}

describe('CodeExecutionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useStore.setState({
      sessionId: 'sess',
      codeExecutions: [],
      fetchCodeExecutions: vi.fn(),
    } as any)
  })

  it('shows empty state with new copy when no records', () => {
    render(<CodeExecutionPanel />)
    expect(screen.getByText('暂无代码记录')).toBeInTheDocument()
  })

  it('keeps run_code / run_r_code / code_session records and filters others', () => {
    useStore.setState({
      codeExecutions: [
        makeExec({ id: 'k1', tool_name: 'run_code', intent: '保留RC' }),
        makeExec({ id: 'k2', tool_name: 'run_r_code', language: 'r', intent: '保留RR' }),
        makeExec({ id: 'k3', tool_name: 'code_session', intent: '保留CS' }),
        makeExec({ id: 'd1', tool_name: 'stat_test', intent: '过滤' }),
      ],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByText(/保留RC/)).toBeInTheDocument()
    expect(screen.getByText(/保留RR/)).toBeInTheDocument()
    expect(screen.getByText(/保留CS/)).toBeInTheDocument()
    expect(screen.queryByText(/过滤/)).not.toBeInTheDocument()
    expect(screen.getByText(/共 3 份代码归档/)).toBeInTheDocument()
  })

  it('groups records by language when both python and r present', () => {
    useStore.setState({
      codeExecutions: [
        makeExec({ id: 'py1', tool_name: 'code_session', language: 'python', intent: 'py任务' }),
        makeExec({ id: 'r1', tool_name: 'run_r_code', language: 'r', intent: 'r任务' }),
      ],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByTestId('lang-header-python')).toBeInTheDocument()
    expect(screen.getByTestId('lang-header-r')).toBeInTheDocument()
    expect(screen.getByText(/py任务/)).toBeInTheDocument()
    expect(screen.getByText(/r任务/)).toBeInTheDocument()
  })

  it('hides language headers when only one language present', () => {
    useStore.setState({
      codeExecutions: [
        makeExec({ id: 'py1', tool_name: 'code_session', language: 'python' }),
        makeExec({ id: 'py2', tool_name: 'code_session', language: 'python' }),
      ],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.queryByTestId('lang-header-python')).not.toBeInTheDocument()
    expect(screen.queryByTestId('lang-header-r')).not.toBeInTheDocument()
  })

  it('renders purpose-based title for visualization', () => {
    useStore.setState({
      codeExecutions: [
        makeExec({
          tool_args: { purpose: 'visualization' },
          intent: '销售图表',
        }),
      ],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByText(/图表：销售图表/)).toBeInTheDocument()
  })

  it('calls downloadSingleBundle on single download click', async () => {
    useStore.setState({
      codeExecutions: [makeExec({ id: 'exec999' })],
    } as any)
    render(<CodeExecutionPanel />)
    const btn = screen.getByTitle('下载可复现 zip')
    fireEvent.click(btn)
    await waitFor(() => {
      expect(downloadSingleBundle).toHaveBeenCalledWith('sess', 'exec999')
    })
  })

  it('calls downloadBatchBundle on batch download click', async () => {
    useStore.setState({
      codeExecutions: [makeExec({})],
    } as any)
    render(<CodeExecutionPanel />)
    const btn = screen.getByTitle('下载全部代码档案')
    fireEvent.click(btn)
    await waitFor(() => {
      expect(downloadBatchBundle).toHaveBeenCalledWith('sess')
    })
  })

  it('shows count with new copy', () => {
    useStore.setState({
      codeExecutions: [makeExec({ id: 'a' }), makeExec({ id: 'b' })],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByText(/共 2 份代码归档/)).toBeInTheDocument()
  })
})
