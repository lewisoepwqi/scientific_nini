/**
 * 文件预览弹窗 —— 支持图片/文本/JSON/HTML/PDF/Markdown 渲染。
 */
import { useEffect, useState, useCallback } from 'react'
import { useStore } from '../store'
import { apiFetch } from '../store/auth'
import { Download, Loader2 } from 'lucide-react'
import BaseModal from './BaseModal'
import LazyMarkdownContent from './LazyMarkdownContent'
import PlotlyFromUrl from './PlotlyFromUrl'
import { resolveDownloadUrl } from './downloadUtils'

interface PreviewData {
  id: string
  kind: string
  preview_type: string
  name?: string
  mime_type?: string
  data?: string       // base64 图片
  content?: string    // 文本/HTML
  ext?: string
  total_lines?: number
  preview_lines?: number
  size?: number
  download_url?: string
  message?: string
}

export default function FilePreviewModal() {
  const previewFileId = useStore((s) => s.previewFileId)
  const sessionId = useStore((s) => s.sessionId)
  const closePreview = useStore((s) => s.closePreview)
  const workspaceFiles = useStore((s) => s.workspaceFiles)

  const [preview, setPreview] = useState<PreviewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 获取文件信息（用于下载 URL）
  const fileInfo = workspaceFiles.find((f) => f.id === previewFileId)
  const resolvedDownloadUrl = resolveDownloadUrl(
    fileInfo?.download_url,
    preview?.name || fileInfo?.name,
  )

  useEffect(() => {
    if (!previewFileId || !sessionId || !fileInfo?.path) {
      setPreview(null)
      return
    }

    setLoading(true)
    setError(null)
    apiFetch(`/api/workspace/${sessionId}/files/${fileInfo.path}/preview`)
      .then((resp) => resp.json())
      .then((payload) => {
        if (payload.success && payload.data) {
          setPreview(payload.data as PreviewData)
        } else {
          setError(payload.error || '无法加载预览')
        }
      })
      .catch(() => setError('网络错误'))
      .finally(() => setLoading(false))
  }, [previewFileId, sessionId, fileInfo?.path])

  const handleClose = useCallback(() => {
    closePreview()
    setPreview(null)
    setError(null)
  }, [closePreview])

  // Escape 由 BaseModal 处理，无需手动监听

  if (!previewFileId) return null

  return (
    <BaseModal
      open={!!previewFileId}
      onClose={handleClose}
      title={preview?.name || fileInfo?.name || '文件预览'}
      maxWidthClass="max-w-3xl"
      contentClass="max-h-[92vh]"
    >
          {/* 头部工具栏 */}
          <div className="flex items-center justify-between px-4 py-3 border-b dark:border-slate-700 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">
                {preview?.name || fileInfo?.name || '文件预览'}
              </h3>
              {preview?.ext && (
                <span className="text-[10px] bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 px-1.5 py-0.5 rounded">
                  .{preview.ext}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {resolvedDownloadUrl && (
                <a
                  href={resolvedDownloadUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400"
                  title="下载"
                  aria-label="下载文件"
                >
                  <Download size={14} />
                </a>
              )}
            </div>
          </div>

          {/* 内容区域 */}
          <div className="flex-1 overflow-auto min-h-0 p-4">
            {loading && (
              <div className="flex items-center justify-center h-64">
                <Loader2 size={24} className="animate-spin text-blue-500" />
              </div>
            )}

            {error && (
              <div className="flex items-center justify-center h-64 text-red-500 text-sm">
                {error}
              </div>
            )}

            {!loading && !error && preview && (
              <PreviewContent preview={preview} />
            )}
          </div>
    </BaseModal>
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
            className="max-w-full max-h-[70vh] object-contain rounded"
          />
        </div>
      )

    case 'image_too_large':
      return (
        <div className="text-center text-slate-500 dark:text-slate-400 py-12">
          <p className="text-sm">图片过大，无法预览</p>
          <p className="text-xs mt-1 text-slate-400 dark:text-slate-500">
            文件大小: {preview.size ? `${(preview.size / 1024 / 1024).toFixed(1)} MB` : '未知'}
          </p>
        </div>
      )

    case 'plotly_chart':
      if (preview.download_url) {
        return <PlotlyFromUrl url={preview.download_url} alt={preview.name} />
      }
      return <div className="text-center text-slate-500 dark:text-slate-400 py-12 text-sm">图表地址不可用</div>

    case 'text':
      if (preview.ext === 'md' || preview.ext === 'markdown') {
        return (
          <div>
            <div className="markdown-body prose prose-sm max-w-none">
              <LazyMarkdownContent content={preview.content || ''} />
            </div>
            {preview.total_lines && preview.preview_lines && preview.total_lines > preview.preview_lines && (
              <div className="mt-2 text-[10px] text-slate-400 dark:text-slate-500 text-center">
                显示前 {preview.preview_lines} 行 / 共 {preview.total_lines} 行
              </div>
            )}
          </div>
        )
      }
      return (
        <div>
          <pre className="text-xs font-mono bg-slate-50 dark:bg-slate-800 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap break-words">
            {preview.content}
          </pre>
          {preview.total_lines && preview.preview_lines && preview.total_lines > preview.preview_lines && (
            <div className="mt-2 text-[10px] text-slate-400 dark:text-slate-500 text-center">
              显示前 {preview.preview_lines} 行 / 共 {preview.total_lines} 行
            </div>
          )}
        </div>
      )

    case 'html':
      return (
        <iframe
          srcDoc={preview.content}
          className="w-full h-[70vh] border rounded-lg"
          sandbox="allow-scripts"
          title={preview.name}
        />
      )

    case 'pdf':
      if (preview.download_url) {
        return (
          <iframe
            src={preview.download_url}
            className="w-full h-[70vh] border rounded-lg"
            title={preview.name}
          />
        )
      }
      return (
        <div className="text-center py-12 text-sm text-slate-500 dark:text-slate-400">PDF 预览地址不可用</div>
      )

    case 'unsupported':
      return (
        <div className="text-center text-slate-500 dark:text-slate-400 py-12">
          <p className="text-sm">不支持预览此类型文件</p>
          <p className="text-xs mt-1 text-slate-400 dark:text-slate-500">
            类型: {preview.ext || '未知'} · 大小: {preview.size ? `${(preview.size / 1024).toFixed(1)} KB` : '未知'}
          </p>
        </div>
      )

    case 'unavailable':
    case 'error':
      return (
        <div className="text-center text-slate-500 dark:text-slate-400 py-12">
          <p className="text-sm">{preview.message || '无法预览'}</p>
        </div>
      )

    default:
      return (
        <div className="text-center text-slate-400 dark:text-slate-500 py-12">
          <p className="text-sm">未知预览类型</p>
        </div>
      )
  }
}
