/**
 * 独立工作区侧边栏 —— 右侧面板，包含 Tab 切换（文件 / 执行历史 / 任务），支持列表/树状视图切换。
 */
import { useState, useMemo, useCallback } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useStore } from '../store'
import FileListItem from './FileListItem'
import FileTreeView from './FileTreeView'
import ArtifactGallery from './ArtifactGallery'
import CodeExecutionPanel from './CodeExecutionPanel'
import FilePreviewPane from './FilePreviewPane'
import AnalysisTasksPanel from './AnalysisTasksPanel'
import DispatchLedgerOverviewPanel from './DispatchLedgerOverviewPanel'
import {
 FolderOpen,
 Terminal,
 Search,
 X,
 RefreshCw,
 List,
 FolderTree,
 LayoutGrid,
 Download,
 Loader2,
 ListChecks,
} from 'lucide-react'
import Button from './ui/Button'

export default function WorkspaceSidebar() {
 // 数据 selector 合并，使用 useShallow 减少重渲染
 const {
 sessionId,
 workspaceFiles,
 workspacePanelTab,
 analysisTasks,
 previewTabs,
 previewFileId,
 fileSearchQuery,
 isUploading,
 uploadProgress,
 uploadingFileName,
 } = useStore(
 useShallow((s) => ({
 sessionId: s.sessionId,
 workspaceFiles: s.workspaceFiles,
 workspacePanelTab: s.workspacePanelTab,
 analysisTasks: s.analysisTasks,
 previewTabs: s.previewTabs,
 previewFileId: s.previewFileId,
 fileSearchQuery: s.fileSearchQuery,
 isUploading: s.isUploading,
 uploadProgress: s.uploadProgress,
 uploadingFileName: s.uploadingFileName,
 })),
 )
 // 函数 selector 保持独立引用（Zustand 保证函数引用稳定，不会触发重渲染）
 const setWorkspacePanelTab = useStore((s) => s.setWorkspacePanelTab)
 const setFileSearchQuery = useStore((s) => s.setFileSearchQuery)
 const setActivePreview = useStore((s) => s.setActivePreview)
 const closePreview = useStore((s) => s.closePreview)
 const toggleWorkspacePanel = useStore((s) => s.toggleWorkspacePanel)
 const fetchWorkspaceFiles = useStore((s) => s.fetchWorkspaceFiles)
 const fetchDatasets = useStore((s) => s.fetchDatasets)
 const [viewMode, setViewMode] = useState<'list' | 'tree' | 'gallery'>('list')
 const [downloadingAll, setDownloadingAll] = useState(false)
 const [downloadAllError, setDownloadAllError] = useState<string | null>(null)

 // 本地过滤（搜索）
 const filteredFiles = useMemo(() => {
 if (!fileSearchQuery.trim()) return workspaceFiles
 const q = fileSearchQuery.trim().toLowerCase()
 return workspaceFiles.filter((f) => f.name.toLowerCase().includes(q))
 }, [workspaceFiles, fileSearchQuery])

 const previewTabNames = useMemo(() => {
 const names: Record<string, string> = {}
 for (const file of workspaceFiles) {
 names[file.id] = file.name
 }
 return names
 }, [workspaceFiles])
 const hasPreviewTabs = previewTabs.length > 0

 const handleDownloadAllFiles = useCallback(async () => {
 if (!sessionId) return
 const paths = workspaceFiles.map((f) => f.path).filter((path): path is string => Boolean(path))
 if (paths.length === 0) return
 setDownloadAllError(null)
 setDownloadingAll(true)
 try {
 const resp = await fetch(`/api/workspace/${sessionId}/download-zip`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify(paths),
 })
 if (!resp.ok) {
 throw new Error(`HTTP ${resp.status}`)
 }
 const blob = await resp.blob()
 const contentDisposition = resp.headers.get('Content-Disposition') || ''
 const filenameMatch = contentDisposition.match(/filename="(.+?)"/i)
 const filename = filenameMatch?.[1] || `workspace_${sessionId.slice(0, 8)}_all.zip`
 const url = URL.createObjectURL(blob)
 const a = document.createElement('a')
 a.href = url
 a.download = filename
 a.click()
 URL.revokeObjectURL(url)
 } catch (e) {
 console.error('下载全部文件失败:', e)
 setDownloadAllError('下载全部文件失败，请稍后重试')
 } finally {
 setDownloadingAll(false)
 }
 }, [sessionId, workspaceFiles])

 // 拖拽上传处理
 const handleDragOver = useCallback((e: React.DragEvent) => {
 e.preventDefault()
 e.stopPropagation()
 }, [])

 const handleDrop = useCallback(async (e: React.DragEvent) => {
 e.preventDefault()
 e.stopPropagation()
 const files = Array.from(e.dataTransfer.files)
 const upload = useStore.getState().uploadFile
 for (const file of files) {
 await upload(file)
 }
 }, [])

 if (!sessionId) {
 return (
 <div className="h-full flex flex-col items-center justify-center text-[var(--text-muted)] text-xs px-4">
 <FolderOpen size={24} className="mb-2 opacity-50" />
 <p>请先选择或创建会话</p>
 </div>
 )
 }

 return (
 <div className="h-full flex flex-col bg-[var(--bg-base)]" onDragOver={handleDragOver} onDrop={handleDrop}>
 {/* 头部 */}
 <header className="h-12 flex items-center justify-between px-3 border-b border-[var(--border-subtle)] flex-shrink-0">
 <span className="text-sm font-semibold text-[var(--text-primary)]">工作区</span>
 <div className="flex items-center gap-1">
 <Button
 variant="ghost"
 size="icon-sm"
 onClick={() => {
 fetchWorkspaceFiles()
 fetchDatasets()
 }}
 title="刷新"
 aria-label="刷新工作区"
 >
 <RefreshCw size={14} />
 </Button>
 <Button
 variant="ghost"
 size="icon-md"
 onClick={toggleWorkspacePanel}
 className="md:hidden"
 title="关闭面板"
 aria-label="关闭面板"
 >
 <X size={16} />
 </Button>
 </div>
 </header>
 {isUploading && (
 <div className="px-3 py-2 border-b border-[var(--border-default)] bg-[var(--accent-subtle)] flex-shrink-0">
 <div className="flex items-center gap-1.5 text-[11px] text-[var(--success)] mb-1">
 <Loader2 size={11} className="animate-spin" />
 <span className="truncate">{uploadingFileName || '正在上传文件'}</span>
 <span className="ml-auto">{uploadProgress}%</span>
 </div>
 <div className="h-1.5 bg-[var(--accent-subtle)] rounded-full overflow-hidden">
 <div
 className="h-full bg-[var(--success)] transition-all"
 style={{ width: `${uploadProgress}%` }}
 />
 </div>
 </div>
 )}

 {downloadAllError && (
 <div
 className="mx-3 mt-3 rounded-lg border border-[var(--error)] px-3 py-2 text-[11px] text-[var(--error)] flex-shrink-0"
 style={{ backgroundColor: 'color-mix(in srgb, var(--error) 10%, var(--bg-base))' }}
 >
 {downloadAllError}
 </div>
 )}

 {/* Tab 切换：任务 → 执行历史 → 文件 */}
 <div
 className={`flex flex-shrink-0 relative overflow-x-auto overflow-y-hidden border-b border-[var(--border-default)] scroll-smooth ${
 hasPreviewTabs ? '' : 'overflow-x-hidden'
 }`}
 >
 <Button
 variant="ghost"
 onClick={() => {
 setWorkspacePanelTab('tasks')
 setActivePreview(null)
 }}
 className={`${
 hasPreviewTabs ? 'inline-flex shrink-0 min-w-[86px]' : 'flex flex-1 min-w-0'
 } items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap rounded-none !transition-none relative ${
 workspacePanelTab === 'tasks' && !previewFileId
 ? '!text-[var(--accent)] !bg-[var(--accent-subtle)]/50 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-[var(--accent)]'
 : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
 }`}
 >
 <ListChecks size={13} />
 任务
 {analysisTasks.length > 0 && (
 <span className="inline-flex items-center justify-center min-w-4 h-4 px-1 rounded-full text-[10px] bg-[var(--accent-subtle)] text-[var(--accent)]">
 {analysisTasks.length}
 </span>
 )}
 </Button>
 <Button
 variant="ghost"
 onClick={() => {
 setWorkspacePanelTab('executions')
 setActivePreview(null)
 }}
 className={`${
 hasPreviewTabs ? 'inline-flex shrink-0 min-w-[98px]' : 'flex flex-1 min-w-0'
 } items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap rounded-none !transition-none relative ${
 workspacePanelTab === 'executions' && !previewFileId
 ? '!text-[var(--accent)] !bg-[var(--accent-subtle)]/50 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-[var(--accent)]'
 : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
 }`}
 >
 <Terminal size={13} />
 执行历史
 </Button>
 <Button
 variant="ghost"
 onClick={() => {
 setWorkspacePanelTab('files')
 setActivePreview(null)
 }}
 className={`${
 hasPreviewTabs ? 'inline-flex shrink-0 min-w-[82px]' : 'flex flex-1 min-w-0'
 } items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap rounded-none !transition-none relative ${
 workspacePanelTab === 'files' && !previewFileId
 ? '!text-[var(--accent)] !bg-[var(--accent-subtle)]/50 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-[var(--accent)]'
 : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
 }`}
 >
 <FolderOpen size={13} />
 文件
 </Button>
 {previewTabs.map((id) => (
 <Button
 variant="ghost"
 key={id}
 onClick={() => setActivePreview(id)}
 className={`inline-flex shrink-0 items-center gap-1 px-2 py-2 text-xs whitespace-nowrap ${
 previewFileId === id
 ? 'text-[var(--accent)] bg-[var(--accent-subtle)] border-b-2 border-[var(--accent)]'
 : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] border-b-2 border-transparent'
 }`}
 >
 <span className="max-w-[120px] truncate" title={previewTabNames[id] || id}>
 {previewTabNames[id] || '预览文件'}
 </span>
 <span
 role="button"
 tabIndex={0}
 onClick={(e) => {
 e.stopPropagation()
 closePreview(id)
 }}
 onKeyDown={(e) => {
 if (e.key === 'Enter' || e.key === ' ') {
 e.preventDefault()
 e.stopPropagation()
 closePreview(id)
 }
 }}
 className="shrink-0 p-1 rounded hover:bg-[var(--bg-overlay)] dark:hover:bg-[var(--bg-overlay)]"
 title="关闭标签"
 >
 <X size={14} />
 </span>
 </Button>
 ))}
 </div>

 {/* Tab 内容 */}
 <div className="flex-1 overflow-y-auto min-h-0">
 {previewFileId && (
 <FilePreviewPane />
 )}

 {!previewFileId && workspacePanelTab === 'files' && (
 <div className="flex flex-col h-full">
 {/* 搜索框 + 视图切换 */}
 <div className="px-2 py-2 flex-shrink-0 flex items-center gap-1.5">
 <div className="relative flex-1">
 <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
 <input
 name="workspace-file-search"
 autoComplete="off"
 value={fileSearchQuery}
 onChange={(e) => setFileSearchQuery(e.target.value)}
 placeholder="搜索文件..."
 className="w-full pl-7 pr-7 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-base)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] focus:border-[var(--accent)]"
 />
 {fileSearchQuery && (
 <Button
 variant="ghost"
 onClick={() => setFileSearchQuery('')}
 className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 rounded"
 >
 <X size={12} />
 </Button>
 )}
 </div>
 <Button
 variant="ghost"
 onClick={() => {
 const modes: Array<'list' | 'tree' | 'gallery'> = ['list', 'tree', 'gallery']
 const idx = modes.indexOf(viewMode)
 setViewMode(modes[(idx + 1) % modes.length])
 }}
 className={`p-2 rounded ${
 viewMode !== 'list' ? 'text-[var(--accent)] bg-[var(--accent-subtle)]' : ''
 }`}
 title={
 viewMode === 'list' ? '切换到目录树视图' :
 viewMode === 'tree' ? '切换到画廊视图' : '切换到列表视图'
 }
 >
 {viewMode === 'list' ? <FolderTree size={14} /> :
 viewMode === 'tree' ? <LayoutGrid size={14} /> : <List size={14} />}
 </Button>
 <Button
 variant="ghost"
 size="icon-sm"
 onClick={handleDownloadAllFiles}
 disabled={downloadingAll || workspaceFiles.length === 0}
 title="打包下载全部文件"
 aria-label="打包下载全部文件"
 >
 {downloadingAll ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
 </Button>
 </div>

 {/* 文件视图 */}
 <div className="flex-1 overflow-y-auto px-1">
 {viewMode === 'list' ? (
 filteredFiles.length === 0 ? (
 <div className="text-center text-xs text-[var(--text-muted)] py-8">
 {fileSearchQuery ? '没有匹配的文件' : '暂无文件'}
 </div>
 ) : (
 <div className="space-y-0.5">
 {filteredFiles.map((file) => (
 <FileListItem key={file.id} file={file} />
 ))}
 </div>
 )
 ) : viewMode === 'tree' ? (
 <FileTreeView />
 ) : (
 <ArtifactGallery />
 )}
 </div>

 {/* 文件统计 */}
 <div className="px-3 py-1.5 border-t border-[var(--border-default)] text-[10px] text-[var(--text-muted)] flex-shrink-0">
 共 {workspaceFiles.length} 个文件
 {fileSearchQuery && ` · 显示 ${filteredFiles.length} 个`}
 </div>
 </div>
 )}

 {!previewFileId && workspacePanelTab === 'executions' && (
 <CodeExecutionPanel />
 )}

{!previewFileId && workspacePanelTab === 'tasks' && (
 <div className="h-full min-h-0 flex flex-col">
 <DispatchLedgerOverviewPanel />
 <div className="min-h-0 flex-1">
 <AnalysisTasksPanel />
 </div>
 </div>
)}
 </div>
 </div>
 )
}
