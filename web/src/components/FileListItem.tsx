/**
 * 文件列表项组件：图标 + 名称 + 大小 + 操作按钮（下载/重命名/删除）。
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { useStore, type WorkspaceFile } from '../store'
import { resolveDownloadUrl } from './downloadUtils'
import {
  FileSpreadsheet,
  FileImage,
  FileText,
  FileCode,
  File,
  Download,
  Trash2,
  Pencil,
  Check,
  X,
} from 'lucide-react'

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function getFileIcon(file: WorkspaceFile) {
  const name = file.name.toLowerCase()
  const ext = name.split('.').pop() || ''

  if (['csv', 'xlsx', 'xls', 'tsv'].includes(ext)) {
    return <FileSpreadsheet size={14} className="text-emerald-500 flex-shrink-0" />
  }
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) {
    return <FileImage size={14} className="text-purple-500 flex-shrink-0" />
  }
  if (['html', 'htm'].includes(ext)) {
    return <FileCode size={14} className="text-orange-500 flex-shrink-0" />
  }
  if (['md', 'txt', 'log'].includes(ext)) {
    return <FileText size={14} className="text-blue-500 flex-shrink-0" />
  }
  if (['json', 'py', 'r'].includes(ext)) {
    return <FileCode size={14} className="text-amber-500 flex-shrink-0" />
  }
  if (ext === 'pdf') {
    return <FileText size={14} className="text-red-500 flex-shrink-0" />
  }
  return <File size={14} className="text-gray-400 flex-shrink-0" />
}

const kindLabels: Record<string, string> = {
  dataset: '数据集',
  artifact: '产物',
  note: '笔记',
}

interface Props {
  file: WorkspaceFile
}

export default function FileListItem({ file }: Props) {
  const deleteWorkspaceFile = useStore((s) => s.deleteWorkspaceFile)
  const renameWorkspaceFile = useStore((s) => s.renameWorkspaceFile)
  const openPreview = useStore((s) => s.openPreview)
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState(file.name)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isRenaming])

  const handleRename = useCallback(async () => {
    const trimmed = renameValue.trim()
    if (trimmed && trimmed !== file.name) {
      await renameWorkspaceFile(file.id, trimmed)
    }
    setIsRenaming(false)
  }, [renameValue, file.id, file.name, renameWorkspaceFile])

  const handleDelete = useCallback(async () => {
    if (!window.confirm(`确定删除文件「${file.name}」？此操作不可撤销。`)) return
    await deleteWorkspaceFile(file.id)
  }, [file.id, file.name, deleteWorkspaceFile])
  const downloadUrl = resolveDownloadUrl(file.download_url, file.name) || file.download_url

  return (
    <div className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-100 transition-colors">
      {getFileIcon(file)}

      <div className="flex-1 min-w-0">
        {isRenaming ? (
          <div className="flex items-center gap-1">
            <input
              ref={inputRef}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRename()
                if (e.key === 'Escape') {
                  setRenameValue(file.name)
                  setIsRenaming(false)
                }
              }}
              className="flex-1 min-w-0 text-xs rounded border border-blue-300 px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <button onClick={handleRename} className="p-0.5 text-emerald-600 hover:text-emerald-700">
              <Check size={12} />
            </button>
            <button
              onClick={() => {
                setRenameValue(file.name)
                setIsRenaming(false)
              }}
              className="p-0.5 text-gray-400 hover:text-gray-600"
            >
              <X size={12} />
            </button>
          </div>
        ) : (
          <div
            className="cursor-pointer"
            onClick={() => openPreview(file.id)}
            title="点击预览"
          >
            <div className="text-xs text-gray-700 truncate hover:text-blue-600 transition-colors">{file.name}</div>
            <div className="text-[10px] text-gray-400">
              {kindLabels[file.kind] || file.kind} · {formatSize(file.size)}
            </div>
          </div>
        )}
      </div>

      {/* 操作按钮 */}
      {!isRenaming && (
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <a
            href={downloadUrl}
            target="_blank"
            rel="noreferrer"
            className="p-1 rounded hover:bg-gray-200 text-gray-500"
            title="下载"
          >
            <Download size={12} />
          </a>
          <button
            onClick={() => {
              setRenameValue(file.name)
              setIsRenaming(true)
            }}
            className="p-1 rounded hover:bg-gray-200 text-gray-500"
            title="重命名"
          >
            <Pencil size={12} />
          </button>
          <button
            onClick={handleDelete}
            className="p-1 rounded hover:bg-red-100 text-gray-500 hover:text-red-600"
            title="删除"
          >
            <Trash2 size={12} />
          </button>
        </div>
      )}
    </div>
  )
}
