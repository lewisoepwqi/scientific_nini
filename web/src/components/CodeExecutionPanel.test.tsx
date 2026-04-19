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

  it('filters out non run_code / run_r_code tool records', () => {
    useStore.setState({
      codeExecutions: [
        makeExec({ id: 'keep1', tool_name: 'run_code', intent: '保留' }),
        makeExec({ id: 'drop1', tool_name: 'stat_test', intent: '过滤' }),
      ],
    } as any)
    render(<CodeExecutionPanel />)
    expect(screen.getByText(/保留/)).toBeInTheDocument()
    expect(screen.queryByText(/过滤/)).not.toBeInTheDocument()
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
