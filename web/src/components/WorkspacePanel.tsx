/**
 * 会话工作空间面板：展示数据集与文件产物。
 */
import { useMemo } from 'react'
import { useStore } from '../store'
import { Database, FolderOpen, RefreshCw, Download } from 'lucide-react'
import { resolveDownloadUrl } from './downloadUtils'

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export default function WorkspacePanel() {
  const sessionId = useStore((s) => s.sessionId)
  const datasets = useStore((s) => s.datasets)
  const files = useStore((s) => s.workspaceFiles)
  const fetchDatasets = useStore((s) => s.fetchDatasets)
  const fetchWorkspaceFiles = useStore((s) => s.fetchWorkspaceFiles)
  const loadDataset = useStore((s) => s.loadDataset)

  const fileCountText = useMemo(() => {
    if (files.length === 0) return '暂无文件'
    return `${files.length} 个文件`
  }, [files.length])

  if (!sessionId) return null

  return (
    <div className="mt-2 rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-medium text-gray-700">
          <FolderOpen size={14} />
          当前会话工作空间
        </div>
        <button
          onClick={() => {
            fetchDatasets()
            fetchWorkspaceFiles()
          }}
          className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600 hover:bg-gray-100"
        >
          <RefreshCw size={12} />
          刷新
        </button>
      </div>

      <div className="mt-2">
        <div className="flex items-center gap-1.5 text-[11px] text-gray-600">
          <Database size={12} />
          数据集 {datasets.length} 个
        </div>
        <div className="mt-1.5 max-h-24 overflow-auto space-y-1">
          {datasets.length === 0 && <div className="text-[11px] text-gray-400">暂无上传数据集</div>}
          {datasets.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between rounded-md bg-white px-2 py-1 text-[11px] border border-gray-200"
            >
              <div className="min-w-0">
                <div className="truncate text-gray-700">{item.name}</div>
                <div className="text-gray-400">
                  {item.row_count} 行 × {item.column_count} 列
                </div>
              </div>
              {item.loaded ? (
                <span className="text-emerald-600">已加载</span>
              ) : (
                <button
                  onClick={() => loadDataset(item.id)}
                  className="rounded border border-blue-200 px-1.5 py-0.5 text-blue-600 hover:bg-blue-50"
                >
                  加载
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-2">
        <div className="text-[11px] text-gray-600">文件产物 {fileCountText}</div>
        <div className="mt-1.5 max-h-24 overflow-auto space-y-1">
          {files.length === 0 && <div className="text-[11px] text-gray-400">暂无工作空间文件</div>}
          {files.map((item) => {
            const href = resolveDownloadUrl(item.download_url, item.name) || item.download_url
            return (
            <div
              key={item.id}
              className="flex items-center justify-between rounded-md bg-white px-2 py-1 text-[11px] border border-gray-200"
            >
              <div className="min-w-0">
                <div className="truncate text-gray-700">{item.name}</div>
                <div className="text-gray-400">
                  {item.kind} · {formatSize(item.size)}
                </div>
              </div>
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded border border-gray-200 px-1.5 py-0.5 text-gray-600 hover:bg-gray-100"
                title="下载文件"
              >
                <Download size={11} />
                下载
              </a>
            </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
