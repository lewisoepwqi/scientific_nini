import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ArtifactGallery from './ArtifactGallery'

const apiFetch = vi.fn()
let mockState: Record<string, unknown>
const originalCreateElement = document.createElement.bind(document)

vi.mock('../store', () => ({
 useStore: (selector: (state: Record<string, unknown>) => unknown) => selector(mockState),
}))

vi.mock('../store/auth', () => ({
 apiFetch: (...args: unknown[]) => apiFetch(...args),
}))

describe('ArtifactGallery', () => {
 beforeEach(() => {
 apiFetch.mockReset()
 mockState = {
 sessionId: 'session-1',
 openPreview: vi.fn(),
 workspaceFiles: [
 {
 id: 'report-1',
 name: 'analysis_report.docx',
 kind: 'result',
 path: 'artifacts/exports/analysis_report.docx',
 size: 128,
 download_url: '/api/workspace/session-1/files/artifacts/exports/analysis_report.docx',
 meta: {
 type: 'report',
 project_artifact: { id: 'pa-1', artifact_type: 'report', version: 2, format: 'docx' },
 },
 },
 {
 id: 'chart-1',
 name: 'trend_chart.html',
 kind: 'result',
 path: 'artifacts/trend_chart.html',
 size: 256,
 download_url: '/api/workspace/session-1/files/artifacts/trend_chart.html',
 meta: { type: 'chart' },
 },
 ],
 }
 vi.stubGlobal('URL', {
 createObjectURL: vi.fn(() => 'blob:test'),
 revokeObjectURL: vi.fn(),
 })
 vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
 if (tagName === 'a') {
 return { click: vi.fn(), href: '', download: '' } as unknown as HTMLAnchorElement
 }
 return originalCreateElement(tagName)
 }) as typeof document.createElement)
 })

 it('报告筛选应保留 docx 报告产物', () => {
 render(<ArtifactGallery />)

 fireEvent.click(screen.getByRole('button', { name: '报告' }))

 expect(screen.getByText('analysis_report.docx')).toBeInTheDocument()
 expect(screen.queryByText('trend_chart.html')).not.toBeInTheDocument()
 expect(screen.getByText('v2')).toBeInTheDocument()
 expect(screen.getAllByText(/docx/i).length).toBeGreaterThan(0)
 })

 it('正式产物批量下载应调用项目产物打包接口', async () => {
 apiFetch.mockResolvedValue({
 ok: true,
 headers: { get: () => 'attachment; filename="project_artifacts_session-1.zip"' },
 blob: async () => new Blob(['zip']),
 })

 const { container } = render(<ArtifactGallery />)
 const buttons = container.querySelectorAll('button')
 fireEvent.click(buttons[7])
 fireEvent.click(screen.getByRole('button', { name: /批量下载/u }))

 await waitFor(() => {
 expect(apiFetch).toHaveBeenCalledWith(
 '/api/workspace/session-1/project-artifacts/download-zip',
 expect.objectContaining({ method: 'POST' }),
 )
 })
 })
})
