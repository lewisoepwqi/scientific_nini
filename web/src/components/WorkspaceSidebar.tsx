/**
 * 独立工作区侧边栏 —— 右侧面板，包含 Tab 切换（文件 / 执行历史），支持列表/树状视图切换。
 */
import { useState, useMemo, useCallback } from 'react'
import { useStore } from '../store'
import FileListItem from './FileListItem'
import FileTreeView from './FileTreeView'
import ArtifactGallery from './ArtifactGallery'
import CodeExecutionPanel from './CodeExecutionPanel'
import FilePreviewPane from './FilePreviewPane'
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
} from 'lucide-react'

export default function WorkspaceSidebar() {
  const sessionId = useStore((s) => s.sessionId)
  const workspaceFiles = useStore((s) => s.workspaceFiles)
  const workspacePanelTab = useStore((s) => s.workspacePanelTab)
  const previewTabs = useStore((s) => s.previewTabs)
  const previewFileId = useStore((s) => s.previewFileId)
  const fileSearchQuery = useStore((s) => s.fileSearchQuery)
  const setWorkspacePanelTab = useStore((s) => s.setWorkspacePanelTab)
  const setFileSearchQuery = useStore((s) => s.setFileSearchQuery)
  const setActivePreview = useStore((s) => s.setActivePreview)
  const closePreview = useStore((s) => s.closePreview)
  const toggleWorkspacePanel = useStore((s) => s.toggleWorkspacePanel)
  const fetchWorkspaceFiles = useStore((s) => s.fetchWorkspaceFiles)
  const fetchDatasets = useStore((s) => s.fetchDatasets)
  const isUploading = useStore((s) => s.isUploading)
  const uploadProgress = useStore((s) => s.uploadProgress)
  const uploadingFileName = useStore((s) => s.uploadingFileName)
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

  const handleDownloadAllFiles = useCallback(async () => {
    if (!sessionId) return
    const fileIds = workspaceFiles.map((f) => f.id).filter(Boolean)
    if (fileIds.length === 0) return
    setDownloadAllError(null)
    setDownloadingAll(true)
    try {
      const resp = await fetch(`/api/sessions/${sessionId}/workspace/batch-download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_ids: fileIds }),
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
      <div className="h-full flex flex-col items-center justify-center text-gray-400 text-xs px-4">
        <FolderOpen size={24} className="mb-2 opacity-50" />
        <p>请先选择或创建会话</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-white" onDragOver={handleDragOver} onDrop={handleDrop}>
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-2 border-b flex-shrink-0">
        <span className="text-xs font-medium text-gray-600">工作区</span>
        <div className="flex items-center gap-1">
          <button
            onClick={handleDownloadAllFiles}
            disabled={downloadingAll || workspaceFiles.length === 0}
            className="p-1 rounded hover:bg-gray-100 text-gray-400"
            title="下载全部文件"
          >
            {downloadingAll ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
          </button>
          <button
            onClick={() => {
              fetchWorkspaceFiles()
              fetchDatasets()
            }}
            className="p-1 rounded hover:bg-gray-100 text-gray-400"
            title="刷新"
          >
            <RefreshCw size={12} />
          </button>
          <button
            onClick={toggleWorkspacePanel}
            className="p-1 rounded hover:bg-gray-100 text-gray-400 md:hidden"
            title="关闭面板"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* 上传进度 */}
      {isUploading && (
        <div className="px-3 py-2 border-b bg-emerald-50 flex-shrink-0">
          <div className="flex items-center gap-1.5 text-[11px] text-emerald-700 mb-1">
            <Loader2 size={11} className="animate-spin" />
            <span className="truncate">{uploadingFileName || '正在上传文件'}</span>
            <span className="ml-auto">{uploadProgress}%</span>
          </div>
          <div className="h-1.5 bg-emerald-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {downloadAllError && (
        <div className="px-3 py-1.5 border-b bg-red-50 text-[11px] text-red-500 flex-shrink-0">
          {downloadAllError}
        </div>
      )}

      {/* Tab 切换 */}
      <div className="flex border-b flex-shrink-0 overflow-x-auto">
        <button
          onClick={() => {
            setWorkspacePanelTab('files')
            setActivePreview(null)
          }}
          className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
            workspacePanelTab === 'files' && !previewFileId
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <FolderOpen size={13} />
          文件
        </button>
        <button
          onClick={() => {
            setWorkspacePanelTab('executions')
            setActivePreview(null)
          }}
          className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
            workspacePanelTab === 'executions' && !previewFileId
              ? 'text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Terminal size={13} />
          执行历史
        </button>
        {previewTabs.map((id) => (
          <button
            key={id}
            onClick={() => setActivePreview(id)}
            className={`flex items-center gap-1 px-2 py-2 text-xs border-l transition-colors ${
              previewFileId === id
                ? 'text-blue-600 bg-blue-50 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <span className="max-w-[90px] truncate" title={previewTabNames[id] || id}>
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
              className="p-0.5 rounded hover:bg-gray-200"
              title="关闭标签"
            >
              <X size={11} />
            </span>
          </button>
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
                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  value={fileSearchQuery}
                  onChange={(e) => setFileSearchQuery(e.target.value)}
                  placeholder="搜索文件..."
                  className="w-full pl-7 pr-7 py-1.5 text-xs rounded-md border border-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-400 focus:border-blue-400"
                />
                {fileSearchQuery && (
                  <button
                    onClick={() => setFileSearchQuery('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
              <button
                onClick={() => {
                  const modes: Array<'list' | 'tree' | 'gallery'> = ['list', 'tree', 'gallery']
                  const idx = modes.indexOf(viewMode)
                  setViewMode(modes[(idx + 1) % modes.length])
                }}
                className={`p-1.5 rounded hover:bg-gray-100 transition-colors ${
                  viewMode !== 'list' ? 'text-blue-600 bg-blue-50' : 'text-gray-400'
                }`}
                title={
                  viewMode === 'list' ? '切换到目录树视图' :
                  viewMode === 'tree' ? '切换到画廊视图' : '切换到列表视图'
                }
              >
                {viewMode === 'list' ? <FolderTree size={13} /> :
                 viewMode === 'tree' ? <LayoutGrid size={13} /> : <List size={13} />}
              </button>
            </div>

            {/* 文件视图 */}
            <div className="flex-1 overflow-y-auto px-1">
              {viewMode === 'list' ? (
                filteredFiles.length === 0 ? (
                  <div className="text-center text-xs text-gray-400 py-8">
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
            <div className="px-3 py-1.5 border-t text-[10px] text-gray-400 flex-shrink-0">
              共 {workspaceFiles.length} 个文件
              {fileSearchQuery && ` · 显示 ${filteredFiles.length} 个`}
            </div>
          </div>
        )}

        {!previewFileId && workspacePanelTab === 'executions' && (
          <CodeExecutionPanel />
        )}
      </div>
    </div>
  )
}
