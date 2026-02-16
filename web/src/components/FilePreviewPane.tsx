/**
 * 文件预览面板 —— 作为工作区中的动态标签页内容展示。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Download, X, Loader2 } from 'lucide-react'
import { useStore } from '../store'
import MarkdownContent from './MarkdownContent'
import PlotlyFromUrl from './PlotlyFromUrl'
import { resolveDownloadUrl } from './downloadUtils'

interface PreviewData {
  id: string
  kind: string
  preview_type: string
  name?: string
  mime_type?: string
  data?: string
  content?: string
  ext?: string
  total_lines?: number
  preview_lines?: number
  size?: number
  download_url?: string
  message?: string
}

function toInlinePreviewUrl(url: string): string {
  const hashIndex = url.indexOf('#')
  const hash = hashIndex >= 0 ? url.slice(hashIndex) : ''
  const base = hashIndex >= 0 ? url.slice(0, hashIndex) : url
  if (/(?:\?|&)inline=/.test(base)) {
    return url
  }
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}inline=1${hash}`
}

export default function FilePreviewPane() {
  const sessionId = useStore((s) => s.sessionId)
  const previewFileId = useStore((s) => s.previewFileId)
  const previewTabs = useStore((s) => s.previewTabs)
  const closePreview = useStore((s) => s.closePreview)
  const workspaceFiles = useStore((s) => s.workspaceFiles)
  const [cache, setCache] = useState<Record<string, PreviewData>>({})
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const fileInfo = useMemo(
    () => workspaceFiles.find((f) => f.id === previewFileId),
    [workspaceFiles, previewFileId],
  )

  useEffect(() => {
    setCache((prev) => {
      const next: Record<string, PreviewData> = {}
      for (const id of previewTabs) {
        if (prev[id]) next[id] = prev[id]
      }
      return next
    })
    setErrors((prev) => {
      const next: Record<string, string> = {}
      for (const id of previewTabs) {
        if (prev[id]) next[id] = prev[id]
      }
      return next
    })
  }, [previewTabs])

  useEffect(() => {
    if (!sessionId || !previewFileId) return
    if (cache[previewFileId] || errors[previewFileId]) return

    let cancelled = false
    setLoadingId(previewFileId)
    fetch(`/api/sessions/${sessionId}/workspace/files/${previewFileId}/preview`)
      .then((resp) => resp.json())
      .then((payload) => {
        if (cancelled) return
        if (payload.success && payload.data) {
          setCache((prev) => ({ ...prev, [previewFileId]: payload.data as PreviewData }))
          return
        }
        const err = typeof payload.error === 'string' ? payload.error : '无法加载预览'
        setErrors((prev) => ({ ...prev, [previewFileId]: err }))
      })
      .catch(() => {
        if (cancelled) return
        setErrors((prev) => ({ ...prev, [previewFileId]: '网络错误' }))
      })
      .finally(() => {
        if (cancelled) return
        setLoadingId((curr) => (curr === previewFileId ? null : curr))
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, previewFileId, cache, errors])

  const handleClose = useCallback(() => {
    if (!previewFileId) return
    closePreview(previewFileId)
  }, [closePreview, previewFileId])

  if (!previewFileId) return null

  const preview = cache[previewFileId]
  const error = errors[previewFileId]
  const isLoading = loadingId === previewFileId && !preview && !error
  const resolvedDownloadUrl = resolveDownloadUrl(
    fileInfo?.download_url,
    preview?.name || fileInfo?.name,
  )

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="text-xs font-medium text-gray-700 truncate">
            {preview?.name || fileInfo?.name || '文件预览'}
          </h3>
          {preview?.ext && (
            <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
              .{preview.ext}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {resolvedDownloadUrl && (
            <a
              href={resolvedDownloadUrl}
              target="_blank"
              rel="noreferrer"
              className="p-1 rounded hover:bg-gray-100 text-gray-500"
              title="下载"
            >
              <Download size={13} />
            </a>
          )}
          <button
            onClick={handleClose}
            className="p-1 rounded hover:bg-gray-100 text-gray-500"
            title="关闭预览"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto p-3">
        {isLoading && (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={20} className="animate-spin text-blue-500" />
          </div>
        )}
        {!isLoading && error && (
          <div className="flex items-center justify-center h-full text-red-500 text-sm">
            {error}
          </div>
        )}
        {!isLoading && !error && preview && (
          <PreviewContent preview={preview} />
        )}
      </div>
    </div>
  )
}

function PreviewContent({ preview }: { preview: PreviewData }) {
  switch (preview.preview_type) {
    case 'image':
      return (
        <div className="flex items-center justify-center">
          <img
            src={preview.data}
            alt={preview.name}
            className="max-w-full max-h-[72vh] object-contain rounded"
          />
        </div>
      )
    case 'image_too_large':
      return (
        <div className="text-center text-gray-500 py-12">
          <p className="text-sm">图片过大，无法预览</p>
          <p className="text-xs mt-1 text-gray-400">
            文件大小: {preview.size ? `${(preview.size / 1024 / 1024).toFixed(1)} MB` : '未知'}
          </p>
        </div>
      )
    case 'plotly_chart':
      if (preview.download_url) {
        return <PlotlyFromUrl url={preview.download_url} alt={preview.name} />
      }
      return <div className="text-center text-gray-500 py-12 text-sm">图表地址不可用</div>
    case 'text': {
      const isMarkdown = preview.ext === 'md' || preview.ext === 'markdown'
      return (
        <div>
          {isMarkdown ? (
            <div className="markdown-body prose prose-sm max-w-none">
              <MarkdownContent content={preview.content || ''} />
            </div>
          ) : (
            <pre className="text-xs font-mono bg-gray-50 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">
              {preview.content}
            </pre>
          )}
          {preview.total_lines && preview.preview_lines && preview.total_lines > preview.preview_lines && (
            <div className="mt-2 text-[10px] text-gray-400 text-center">
              显示前 {preview.preview_lines} 行 / 共 {preview.total_lines} 行
            </div>
          )}
        </div>
      )
    }
    case 'html':
      return (
        <iframe
          srcDoc={preview.content}
          className="w-full h-[72vh] border rounded-lg"
          sandbox="allow-scripts"
          title={preview.name}
        />
      )
    case 'pdf':
      if (preview.download_url) {
        return (
          <iframe
            src={toInlinePreviewUrl(preview.download_url)}
            className="w-full h-[72vh] border rounded-lg"
            title={preview.name}
          />
        )
      }
      return (
        <div className="text-center text-gray-500 py-12 text-sm">PDF 预览地址不可用</div>
      )
    case 'unsupported':
      return (
        <div className="text-center text-gray-500 py-12">
          <p className="text-sm">不支持预览此类型文件</p>
          <p className="text-xs mt-1 text-gray-400">
            类型: {preview.ext || '未知'} · 大小: {preview.size ? `${(preview.size / 1024).toFixed(1)} KB` : '未知'}
          </p>
        </div>
      )
    case 'unavailable':
    case 'error':
      return (
        <div className="text-center text-gray-500 py-12 text-sm">
          {preview.message || '无法预览'}
        </div>
      )
    default:
      return (
        <div className="text-center text-gray-400 py-12 text-sm">
          未知预览类型
        </div>
      )
  }
}
