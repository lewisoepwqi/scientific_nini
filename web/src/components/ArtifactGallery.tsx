/**
 * 产物画廊组件 —— 网格缩略图视图，支持类型筛选、批量选择和下载。
 */
import { useState, useMemo, useCallback } from 'react'
import { useStore, type WorkspaceFile } from '../store'
import {
  Image,
  FileText,
  FileCode,
  File,
  Download,
  Check,
  Filter,
  Eye,
  EyeOff,
} from 'lucide-react'

type FilterType = 'all' | 'chart' | 'report' | 'data'

function getFilterLabel(type: FilterType): string {
  switch (type) {
    case 'all': return '全部'
    case 'chart': return '图表'
    case 'report': return '报告'
    case 'data': return '数据'
  }
}

function isImageFile(name: string): boolean {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  return ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)
}

function isChartFile(file: WorkspaceFile): boolean {
  const name = file.name.toLowerCase()
  const ext = name.split('.').pop() || ''
  const metaType = String(file.meta?.type || '').toLowerCase()
  return (
    file.kind === 'artifact' && (
      ['html', 'htm', 'png', 'jpg', 'jpeg', 'svg', 'webp'].includes(ext) ||
      name.endsWith('.plotly.json') ||
      (ext === 'json' && metaType === 'chart')
    )
  )
}

function isReportFile(file: WorkspaceFile): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  return ['md', 'txt', 'pdf'].includes(ext)
}

function isDataFile(file: WorkspaceFile): boolean {
  const name = file.name.toLowerCase()
  const ext = name.split('.').pop()?.toLowerCase() || ''
  const metaType = String(file.meta?.type || '').toLowerCase()
  if (name.endsWith('.plotly.json') || (ext === 'json' && metaType === 'chart')) {
    return false
  }
  return ['csv', 'xlsx', 'xls', 'tsv', 'json'].includes(ext)
}

function ThumbnailIcon({ file }: { file: WorkspaceFile }) {
  const name = file.name.toLowerCase()

  if (isImageFile(name)) {
    // 直接使用文件 URL 作为缩略图
    return (
      <img
        src={file.download_url}
        alt={file.name}
        className="w-full h-full object-cover"
        loading="lazy"
      />
    )
  }

  // 非图片文件用图标
  const ext = name.split('.').pop() || ''
  if (name.endsWith('.plotly.json')) {
    return <FileCode size={28} className="text-orange-400" />
  }
  if (['html', 'htm'].includes(ext)) {
    return <FileCode size={28} className="text-orange-400" />
  }
  if (['md', 'txt', 'pdf'].includes(ext)) {
    return <FileText size={28} className="text-blue-400" />
  }
  if (['csv', 'xlsx', 'xls', 'tsv', 'json'].includes(ext)) {
    return <FileText size={28} className="text-emerald-400" />
  }
  return <File size={28} className="text-gray-400" />
}

export default function ArtifactGallery() {
  const sessionId = useStore((s) => s.sessionId)
  const workspaceFiles = useStore((s) => s.workspaceFiles)
  const openPreview = useStore((s) => s.openPreview)
  const [filter, setFilter] = useState<FilterType>('all')
  const [showInternal, setShowInternal] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  // 只显示产物（默认隐藏内部产物）
  const artifacts = useMemo(() => {
    return workspaceFiles.filter((f) => {
      if (f.kind !== 'artifact') return false
      if (!showInternal && f.meta?.visibility === 'internal') return false
      return true
    })
  }, [workspaceFiles, showInternal])

  // 按类型过滤
  const filteredArtifacts = useMemo(() => {
    switch (filter) {
      case 'chart': return artifacts.filter(isChartFile)
      case 'report': return artifacts.filter(isReportFile)
      case 'data': return artifacts.filter(isDataFile)
      default: return artifacts
    }
  }, [artifacts, filter])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleBatchDownload = useCallback(async () => {
    if (selectedIds.size === 0 || !sessionId) return
    const selectedPaths = filteredArtifacts
      .filter((file) => selectedIds.has(file.id))
      .map((file) => file.path)
      .filter((path): path is string => Boolean(path))
    if (selectedPaths.length === 0) return
    setDownloadError(null)
    setDownloading(true)
    try {
      const resp = await fetch(`/api/workspace/${sessionId}/download-zip`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(selectedPaths),
      })
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }
      const blob = await resp.blob()
      const contentDisposition = resp.headers.get('Content-Disposition') || ''
      const filenameMatch = contentDisposition.match(/filename="(.+?)"/i)
      const filename = filenameMatch?.[1] || `workspace_${sessionId.slice(0, 8)}.zip`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      setSelectedIds(new Set())
    } catch (e) {
      console.error('批量下载失败:', e)
      setDownloadError('打包下载失败，请稍后重试')
    } finally {
      setDownloading(false)
    }
  }, [filteredArtifacts, selectedIds, sessionId])

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-400 text-xs">
        <Image size={24} className="mb-2 opacity-50" />
        <p>暂无产物</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* 筛选栏 */}
      <div className="flex items-center gap-1.5 px-2 py-2 flex-shrink-0">
        <Filter size={12} className="text-gray-400 flex-shrink-0" />
        {(['all', 'chart', 'report', 'data'] as FilterType[]).map((type) => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors ${
              filter === type
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            }`}
          >
            {getFilterLabel(type)}
          </button>
        ))}
        <button
          onClick={() => setShowInternal(!showInternal)}
          className={`ml-auto p-1 rounded transition-colors ${
            showInternal ? 'text-blue-600 bg-blue-50' : 'text-gray-400 hover:text-gray-600'
          }`}
          title={showInternal ? '隐藏内部产物' : '显示内部产物'}
        >
          {showInternal ? <Eye size={12} /> : <EyeOff size={12} />}
        </button>
      </div>

      {/* 网格 */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        <div className="grid grid-cols-2 gap-2">
          {filteredArtifacts.map((file) => {
            const isSelected = selectedIds.has(file.id)
            return (
              <div
                key={file.id}
                className={`relative rounded-lg border overflow-hidden cursor-pointer transition-all ${
                  isSelected ? 'border-blue-500 ring-1 ring-blue-300' : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                {/* 选择复选框 */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleSelect(file.id)
                  }}
                  className={`absolute top-1.5 left-1.5 z-10 w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                    isSelected
                      ? 'bg-blue-500 border-blue-500 text-white'
                      : 'bg-white/80 border-gray-300 hover:border-blue-400'
                  }`}
                >
                  {isSelected && <Check size={10} />}
                </button>

                {/* 缩略图 */}
                <div
                  className="aspect-square bg-gray-50 flex items-center justify-center overflow-hidden"
                  onClick={() => openPreview(file.id)}
                >
                  <ThumbnailIcon file={file} />
                </div>

                {/* 文件名 */}
                <div className="px-1.5 py-1 border-t bg-white">
                  <div className="text-[10px] text-gray-700 truncate" title={file.name}>
                    {file.name}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 批量操作栏 */}
      {selectedIds.size > 0 && (
        <div className="px-2 py-2 border-t bg-blue-50 flex-shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-xs text-blue-700">
              已选 {selectedIds.size} 个
            </span>
            <button
              onClick={handleBatchDownload}
              disabled={downloading}
              className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded-md text-xs hover:bg-blue-700 disabled:bg-blue-300 transition-colors"
            >
              <Download size={12} />
              {downloading ? '打包中...' : '批量下载'}
            </button>
          </div>
          {downloadError && (
            <p className="text-[10px] text-red-500 mt-1">{downloadError}</p>
          )}
        </div>
      )}
    </div>
  )
}
