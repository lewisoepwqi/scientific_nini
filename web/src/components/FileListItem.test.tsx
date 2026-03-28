import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FileListItem from './FileListItem'

const mockDeleteWorkspaceFile = vi.fn()
const mockRenameWorkspaceFile = vi.fn()
const mockOpenPreview = vi.fn()

vi.mock('../store', () => ({
  useStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      deleteWorkspaceFile: mockDeleteWorkspaceFile,
      renameWorkspaceFile: mockRenameWorkspaceFile,
      openPreview: mockOpenPreview,
    }),
}))

vi.mock('./downloadUtils', () => ({
  resolveDownloadUrl: (url: string) => url,
  downloadFileFromUrl: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../store/confirm-store', () => ({
  useConfirm: () => () => Promise.resolve(true),
}))

describe('FileListItem', () => {
  const file = {
    id: 'file-id-123',
    name: 'report.md',
    kind: 'document' as const,
    path: 'notes/report.md',
    size: 128,
    download_url: '/api/workspace/test/notes/report.md',
  }

  beforeEach(() => {
    mockDeleteWorkspaceFile.mockReset()
    mockRenameWorkspaceFile.mockReset()
    mockOpenPreview.mockReset()
  })

  it('重命名时应使用文件路径而不是文件 id', async () => {
    render(<FileListItem file={file} />)

    await act(async () => {
      fireEvent.click(screen.getByTitle('重命名'))
    })
    const input = screen.getByDisplayValue('report.md')
    await act(async () => {
      fireEvent.change(input, { target: { value: 'renamed.md' } })
      fireEvent.keyDown(input, { key: 'Enter' })
    })

    expect(mockRenameWorkspaceFile).toHaveBeenCalledWith('notes/report.md', 'renamed.md')
    expect(mockRenameWorkspaceFile).not.toHaveBeenCalledWith('file-id-123', 'renamed.md')
  })

  it('删除时应使用文件路径而不是文件 id', async () => {
    render(<FileListItem file={file} />)

    await act(async () => {
      fireEvent.click(screen.getByTitle('删除'))
    })

    expect(mockDeleteWorkspaceFile).toHaveBeenCalledWith('notes/report.md')
    expect(mockDeleteWorkspaceFile).not.toHaveBeenCalledWith('file-id-123')
  })

  it('点击文件名区域应打开预览', async () => {
    render(<FileListItem file={file} />)

    await act(async () => {
      fireEvent.click(screen.getByText('report.md'))
    })

    expect(mockOpenPreview).toHaveBeenCalledWith('file-id-123')
  })

  it('点击文件图标应打开预览（图标在可点击区域内）', async () => {
    const pdfFile = {
      ...file,
      name: 'report.pdf',
      path: 'artifacts/report.pdf',
      download_url: '/api/workspace/test/artifacts/report.pdf',
    }
    render(<FileListItem file={pdfFile} />)

    // 点击包含图标的区域（通过 aria-label 定位可点击按钮）
    const clickableArea = screen.getByLabelText('预览 report.pdf')
    await act(async () => {
      fireEvent.click(clickableArea)
    })

    expect(mockOpenPreview).toHaveBeenCalledWith('file-id-123')
  })

  it('点击操作按钮不应触发预览（stopPropagation）', async () => {
    render(<FileListItem file={file} />)

    // 点击重命名按钮
    await act(async () => {
      fireEvent.click(screen.getByTitle('重命名'))
    })

    // 预览不应被触发
    expect(mockOpenPreview).not.toHaveBeenCalled()
  })

  it('点击下载链接不应触发预览（stopPropagation）', async () => {
    render(<FileListItem file={file} />)

    // 点击下载按钮
    await act(async () => {
      fireEvent.click(screen.getByTitle('下载'))
    })

    // 预览不应被触发
    expect(mockOpenPreview).not.toHaveBeenCalled()
  })
})
