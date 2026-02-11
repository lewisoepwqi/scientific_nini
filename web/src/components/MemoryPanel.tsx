/**
 * 记忆面板 —— 展示会话记忆文件状态与上下文 Token 用量。
 */
import { useEffect, useState, useCallback } from 'react'
import { useStore, type MemoryFile } from '../store'
import {
  Brain,
  ChevronDown,
  ChevronRight,
  FileText,
  Archive,
  RefreshCw,
  Database,
} from 'lucide-react'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}

function FileIcon({ type }: { type: MemoryFile['type'] }) {
  switch (type) {
    case 'memory':
      return <Database size={12} className="text-blue-400" />
    case 'knowledge':
      return <Brain size={12} className="text-purple-400" />
    case 'archive':
      return <Archive size={12} className="text-amber-400" />
    default:
      return <FileText size={12} className="text-gray-400" />
  }
}

function MemoryFileItem({ file }: { file: MemoryFile }) {
  const sessionId = useStore((s) => s.sessionId)
  const [expanded, setExpanded] = useState(false)
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleExpand = useCallback(async () => {
    if (expanded) {
      setExpanded(false)
      return
    }
    setExpanded(true)
    if (content !== null) return
    if (!sessionId) return

    setLoading(true)
    try {
      const resp = await fetch(
        `/api/sessions/${sessionId}/memory-files/${encodeURIComponent(file.name)}`
      )
      const payload = await resp.json()
      if (payload.success && typeof payload.data?.content === 'string') {
        setContent(payload.data.content)
      } else {
        setContent('(无法读取内容)')
      }
    } catch {
      setContent('(加载失败)')
    } finally {
      setLoading(false)
    }
  }, [expanded, content, sessionId, file.name])

  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <button
        onClick={handleExpand}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-[11px] hover:bg-gray-50 transition-colors"
      >
        {expanded ? (
          <ChevronDown size={10} className="text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight size={10} className="text-gray-400 flex-shrink-0" />
        )}
        <FileIcon type={file.type} />
        <span className="text-gray-700 truncate flex-1 text-left">{file.name}</span>
        <span className="text-[10px] text-gray-400 flex-shrink-0">{formatBytes(file.size)}</span>
      </button>
      {expanded && (
        <div className="px-2 pb-2">
          <div className="text-[10px] text-gray-400 mb-1">
            {formatTime(file.modified_at)}
          </div>
          {loading ? (
            <div className="text-[10px] text-gray-400 animate-pulse">加载中...</div>
          ) : content !== null ? (
            <pre className="text-[10px] font-mono text-gray-600 bg-gray-50 rounded p-2 max-h-32 overflow-y-auto overflow-x-auto whitespace-pre-wrap break-words">
              {content}
            </pre>
          ) : null}
        </div>
      )}
    </div>
  )
}

export default function MemoryPanel() {
  const sessionId = useStore((s) => s.sessionId)
  const memoryFiles = useStore((s) => s.memoryFiles)
  const fetchMemoryFiles = useStore((s) => s.fetchMemoryFiles)
  const [collapsed, setCollapsed] = useState(true)
  const [contextTokens, setContextTokens] = useState<number | null>(null)

  const fetchContextTokens = useCallback(async () => {
    if (!sessionId) return
    try {
      const resp = await fetch(`/api/sessions/${sessionId}/context-size`)
      const payload = await resp.json()
      if (!payload.success) return
      const tokenCount =
        typeof payload.data?.total_context_tokens === 'number'
          ? payload.data.total_context_tokens
          : (typeof payload.data?.token_count === 'number' ? payload.data.token_count : null)
      if (typeof tokenCount === 'number') {
        setContextTokens(tokenCount)
      }
    } catch {
      // 忽略错误，保持当前展示
    }
  }, [sessionId])

  useEffect(() => {
    if (sessionId && !collapsed) {
      fetchMemoryFiles()
      void fetchContextTokens()
    }
  }, [sessionId, collapsed, fetchMemoryFiles, fetchContextTokens])

  useEffect(() => {
    setContextTokens(null)
  }, [sessionId])

  if (!sessionId) return null

  return (
    <div className="border-t border-gray-200">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-4 py-2 text-xs font-medium text-gray-500 hover:bg-gray-50 transition-colors"
      >
        <Brain size={13} className="text-purple-400" />
        <span>记忆状态</span>
        <div className="ml-auto flex items-center gap-1">
          {contextTokens !== null && (
            <span className="text-[10px] text-gray-400">{contextTokens.toLocaleString()} tok</span>
          )}
          {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        </div>
      </button>

      {!collapsed && (
        <div className="px-2 pb-2">
          <div className="flex items-center justify-end mb-1">
            <button
              onClick={() => {
                fetchMemoryFiles()
                void fetchContextTokens()
              }}
              className="p-1 rounded hover:bg-gray-100 text-gray-400"
              title="刷新"
            >
              <RefreshCw size={10} />
            </button>
          </div>
          {memoryFiles.length === 0 ? (
            <div className="text-[10px] text-gray-400 text-center py-2">暂无记忆文件</div>
          ) : (
            <div className="bg-white rounded border border-gray-100">
              {memoryFiles.map((file) => (
                <MemoryFileItem key={file.name} file={file} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
