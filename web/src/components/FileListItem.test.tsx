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
}))

describe('FileListItem', () => {
  const file = {
    id: 'file-id-123',
    name: 'report.md',
    kind: 'note' as const,
    path: 'notes/report.md',
    size: 128,
    download_url: '/api/workspace/test/notes/report.md',
  }

  beforeEach(() => {
    mockDeleteWorkspaceFile.mockReset()
    mockRenameWorkspaceFile.mockReset()
    mockOpenPreview.mockReset()
    vi.stubGlobal('confirm', vi.fn(() => true))
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
})
