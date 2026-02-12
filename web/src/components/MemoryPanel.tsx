/**
 * 记忆面板 —— 展示会话记忆文件状态与上下文 Token 用量。
 * 位于工作区面板下方，支持上沿拖动调整整体高度，每个文件支持独立拖动调整内容区高度。
 */
import { useEffect, useState, useCallback, useRef } from 'react'
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

const MEMORY_PANEL_HEIGHT_KEY = 'nini.memoryPanel.height'
const MEMORY_PANEL_DEFAULT_HEIGHT = 220
const MEMORY_PANEL_MIN_HEIGHT = 60
const MEMORY_PANEL_MAX_HEIGHT = 600

const FILE_CONTENT_DEFAULT_HEIGHT = 120
const FILE_CONTENT_MIN_HEIGHT = 40
const FILE_CONTENT_MAX_HEIGHT = 400

function clampHeight(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback
  return Math.min(max, Math.max(min, Math.round(value)))
}

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

// ---- 每个文件的内容区高度拖动 hook ----

function useVerticalResize(defaultHeight: number, min: number, max: number) {
  const [height, setHeight] = useState(defaultHeight)
  const resizingRef = useRef(false)
  const startYRef = useRef(0)
  const startHeightRef = useRef(defaultHeight)

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return
      const delta = e.clientY - startYRef.current
      setHeight(clampHeight(startHeightRef.current + delta, min, max, defaultHeight))
    }
    const onMouseUp = () => {
      if (!resizingRef.current) return
      resizingRef.current = false
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [min, max, defaultHeight])

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizingRef.current = true
    startYRef.current = e.clientY
    startHeightRef.current = height
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ns-resize'
  }, [height])

  return { height, onMouseDown }
}

// ---- 单个记忆文件 ----

function MemoryFileItem({ file }: { file: MemoryFile }) {
  const sessionId = useStore((s) => s.sessionId)
  const [expanded, setExpanded] = useState(false)
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const { height: contentHeight, onMouseDown: onContentResizeStart } = useVerticalResize(
    FILE_CONTENT_DEFAULT_HEIGHT,
    FILE_CONTENT_MIN_HEIGHT,
    FILE_CONTENT_MAX_HEIGHT,
  )

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
        <div className="px-2 pb-1">
          <div className="text-[10px] text-gray-400 mb-1">
            {formatTime(file.modified_at)}
          </div>
          {loading ? (
            <div className="text-[10px] text-gray-400 animate-pulse">加载中...</div>
          ) : content !== null ? (
            <>
              <pre
                className="text-[10px] font-mono text-gray-600 bg-gray-50 rounded p-2 overflow-y-auto overflow-x-auto whitespace-pre-wrap break-words"
                style={{ height: `${contentHeight}px` }}
              >
                {content}
              </pre>
              {/* 文件内容区底部拖动手柄 */}
              <div
                onMouseDown={onContentResizeStart}
                className="h-3 cursor-ns-resize group flex items-center justify-center hover:bg-blue-50 rounded-b transition-colors"
                title="拖动调整内容区高度"
              >
                <div className="w-6 h-0.5 rounded-full bg-gray-200 group-hover:bg-blue-400 transition-colors" />
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  )
}

// ---- 面板主体 ----

export default function MemoryPanel() {
  const sessionId = useStore((s) => s.sessionId)
  const memoryFiles = useStore((s) => s.memoryFiles)
  const fetchMemoryFiles = useStore((s) => s.fetchMemoryFiles)
  const [collapsed, setCollapsed] = useState(true)
  const [contextTokens, setContextTokens] = useState<number | null>(null)
  const [panelHeight, setPanelHeight] = useState<number>(MEMORY_PANEL_DEFAULT_HEIGHT)
  const resizingRef = useRef(false)
  const startYRef = useRef(0)
  const startHeightRef = useRef(MEMORY_PANEL_DEFAULT_HEIGHT)

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
      // 忽略错误
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

  // 从 localStorage 恢复面板高度
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(MEMORY_PANEL_HEIGHT_KEY)
      if (!saved) return
      const parsed = Number(saved)
      if (Number.isFinite(parsed)) {
        setPanelHeight(clampHeight(parsed, MEMORY_PANEL_MIN_HEIGHT, MEMORY_PANEL_MAX_HEIGHT, MEMORY_PANEL_DEFAULT_HEIGHT))
      }
    } catch {
      // 忽略
    }
  }, [])

  // 持久化面板高度
  useEffect(() => {
    try {
      window.localStorage.setItem(
        MEMORY_PANEL_HEIGHT_KEY,
        String(clampHeight(panelHeight, MEMORY_PANEL_MIN_HEIGHT, MEMORY_PANEL_MAX_HEIGHT, MEMORY_PANEL_DEFAULT_HEIGHT)),
      )
    } catch {
      // 忽略
    }
  }, [panelHeight])

  // 面板上沿拖动（向上拖 = 面板变高）
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return
      const delta = startYRef.current - e.clientY
      setPanelHeight(
        clampHeight(startHeightRef.current + delta, MEMORY_PANEL_MIN_HEIGHT, MEMORY_PANEL_MAX_HEIGHT, MEMORY_PANEL_DEFAULT_HEIGHT),
      )
    }
    const onMouseUp = () => {
      if (!resizingRef.current) return
      resizingRef.current = false
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  const handlePanelResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizingRef.current = true
    startYRef.current = e.clientY
    startHeightRef.current = panelHeight
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'ns-resize'
  }, [panelHeight])

  if (!sessionId) return null

  return (
    <div className="flex-shrink-0 border-t border-gray-200 flex flex-col">
      {/* 上沿拖动条 */}
      {!collapsed && (
        <div
          onMouseDown={handlePanelResizeStart}
          className="h-1.5 cursor-ns-resize group flex items-center justify-center hover:bg-blue-50 transition-colors flex-shrink-0"
          title="拖动调整记忆面板高度"
        >
          <div className="w-8 h-0.5 rounded-full bg-gray-300 group-hover:bg-blue-400 transition-colors" />
        </div>
      )}

      {/* 标题栏 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-4 py-2 text-xs font-medium text-gray-500 hover:bg-gray-50 transition-colors flex-shrink-0"
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

      {/* 展开内容 */}
      {!collapsed && (
        <div className="flex flex-col min-h-0 px-2 pb-2" style={{ height: `${panelHeight}px` }}>
          <div className="flex items-center justify-end mb-1 flex-shrink-0">
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
          <div className="flex-1 overflow-y-auto min-h-0">
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
        </div>
      )}
    </div>
  )
}
