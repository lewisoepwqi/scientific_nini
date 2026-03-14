/**
 * 会话列表（侧边栏）—— 支持多会话管理、切换、重命名与删除。
 */
import { useEffect, useState, useCallback, useRef, type KeyboardEvent } from 'react'
import { useStore } from '../store'
import { Loader2, MessageSquarePlus, Pencil, Trash2, X } from 'lucide-react'
import * as api from '../store/api-actions'
import type { SessionItem } from '../store/types'
import { onSessionsChanged } from '../store/session-lifecycle'

interface Props {
  onClose?: () => void
}

export default function SessionList({ onClose }: Props) {
  const sessionId = useStore((s) => s.sessionId)
  const runningSessions = useStore((s) => s.runningSessions)
  const pendingAskUserQuestionsBySession = useStore(
    (s) => s.pendingAskUserQuestionsBySession,
  )
  const appBootstrapping = useStore((s) => s.appBootstrapping)
  const createNewSession = useStore((s) => s.createNewSession)
  const switchSession = useStore((s) => s.switchSession)
  const deleteSession = useStore((s) => s.deleteSession)
  const updateSessionTitle = useStore((s) => s.updateSessionTitle)
  const clearMessages = useStore((s) => s.clearMessages)

  const PAGE_SIZE = 50

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [pagedSessions, setPagedSessions] = useState<SessionItem[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [focusedIndex, setFocusedIndex] = useState(-1)
  const [pendingDelete, setPendingDelete] = useState<{ id: string; title: string } | null>(null)
  const [hiddenSessionIds, setHiddenSessionIds] = useState<Record<string, true>>({})
  const [creatingSession, setCreatingSession] = useState(false)
  const [firstPageResolved, setFirstPageResolved] = useState(false)
  const editRef = useRef<HTMLInputElement>(null)
  const deleteTimerRef = useRef<number | null>(null)
  const offsetRef = useRef(0)
  const listRef = useRef<HTMLDivElement>(null)
  const requestIdRef = useRef(0)
  const loadingMoreRef = useRef(false)
  const deletingIdsRef = useRef<Set<string>>(new Set())

  const loadPage = useCallback(async (reset: boolean) => {
    if (loadingMoreRef.current && !reset) return
    const query = debouncedQuery.trim()
    const requestId = ++requestIdRef.current
    loadingMoreRef.current = true
    setLoadingMore(true)
    const offset = reset ? 0 : offsetRef.current
    try {
      const result = await api.fetchSessions({
        q: query || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      if (requestId !== requestIdRef.current) {
        return
      }
      if (reset) {
        setPagedSessions(result)
        offsetRef.current = result.length
        setFirstPageResolved(true)
      } else {
        setPagedSessions((prev) => [...prev, ...result])
        offsetRef.current += result.length
      }
      setHasMore(result.length === PAGE_SIZE)
    } finally {
      if (requestId === requestIdRef.current) {
        loadingMoreRef.current = false
        setLoadingMore(false)
      }
    }
  }, [debouncedQuery, PAGE_SIZE])

  // 编辑状态时自动聚焦
  useEffect(() => {
    if (editingId) editRef.current?.focus()
  }, [editingId])

  // 搜索输入防抖，避免大量会话时频繁重算
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(searchQuery)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [searchQuery])

  useEffect(() => {
    offsetRef.current = 0
    setHasMore(true)
    setFocusedIndex(-1)
    setFirstPageResolved(false)
    void loadPage(true)
  }, [debouncedQuery, loadPage])

  useEffect(() => {
    // 当前会话变化后清空“焦点高亮”，避免误认为选中跳转
    setFocusedIndex(-1)
  }, [sessionId])

  useEffect(() => {
    const off = onSessionsChanged((event) => {
      if (event.reason === 'create' && event.sessionId) {
        const newId = event.sessionId
        const newTitle = event.title || '新会话'
        setHiddenSessionIds((prev) => {
          const next = { ...prev }
          delete next[newId]
          return next
        })
        setPagedSessions((prev) => {
          if (prev.some((item) => item.id === newId)) return prev
          return [
            {
              id: newId,
              title: newTitle,
              message_count: 0,
              source: "memory",
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              last_message_at: new Date().toISOString(),
            },
            ...prev,
          ]
        })
      }
      if (event.reason === 'rename' && event.sessionId && event.title) {
        setPagedSessions((prev) => prev.map((item) => (
          item.id === event.sessionId ? { ...item, title: event.title ?? item.title } : item
        )))
      }
      offsetRef.current = 0
      setHasMore(true)
      void loadPage(true)
    })
    return off
  }, [loadPage])

  const handleDoubleClick = useCallback((id: string, title: string) => {
    setEditingId(id)
    setEditTitle(title === '新会话' ? '' : title)
  }, [])

  const handleRenameSubmit = useCallback(async (id: string) => {
    const trimmed = editTitle.trim()
    const exists = pagedSessions.some((item) => item.id === id)
    if (!exists || deletingIdsRef.current.has(id)) {
      setEditingId(null)
      return
    }
    if (trimmed) {
      await updateSessionTitle(id, trimmed)
      setPagedSessions((prev) => prev.map((item) => (item.id === id ? { ...item, title: trimmed } : item)))
    }
    setEditingId(null)
  }, [editTitle, pagedSessions, updateSessionTitle])

  const handleClick = useCallback((id: string) => {
    switchSession(id)
    onClose?.()
  }, [switchSession, onClose])

  const filteredSessions = pagedSessions.filter((s) => {
    if (hiddenSessionIds[s.id]) return false
    return true
  })
  const visibleSessions = filteredSessions

  useEffect(() => {
    if (focusedIndex >= visibleSessions.length) {
      setFocusedIndex(visibleSessions.length > 0 ? visibleSessions.length - 1 : -1)
    }
  }, [focusedIndex, visibleSessions.length])

  const runDelete = useCallback(async (id: string) => {
    if (deletingIdsRef.current.has(id)) return
    deletingIdsRef.current.add(id)
    try {
      const success = await deleteSession(id)
      if (!success) {
        setHiddenSessionIds((prev) => {
          const next = { ...prev }
          delete next[id]
          return next
        })
        setPendingDelete((prev) => (prev?.id === id ? null : prev))
        return
      }
      setPagedSessions((prev) => prev.filter((item) => item.id !== id))
      setPendingDelete((prev) => (prev?.id === id ? null : prev))
      setHiddenSessionIds((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    } finally {
      deletingIdsRef.current.delete(id)
    }
  }, [deleteSession])

  useEffect(() => {
    return () => {
      if (deleteTimerRef.current !== null) {
        window.clearTimeout(deleteTimerRef.current)
      }
    }
  }, [])

  const queueDelete = useCallback((id: string, title: string) => {
    if (pendingDelete && pendingDelete.id !== id) return
    if (deleteTimerRef.current !== null) {
      window.clearTimeout(deleteTimerRef.current)
    }
    setHiddenSessionIds((prev) => ({ ...prev, [id]: true }))
    if (sessionId === id) {
      const nextSession = pagedSessions.find((item) => (
        item.id !== id &&
        !hiddenSessionIds[item.id] &&
        item.id !== pendingDelete?.id
      ))
      if (nextSession) {
        void switchSession(nextSession.id)
      } else {
        clearMessages()
      }
    }
    setPendingDelete({ id, title: title || '新会话' })
    deleteTimerRef.current = window.setTimeout(() => {
      void runDelete(id)
      deleteTimerRef.current = null
    }, 5000)
  }, [clearMessages, hiddenSessionIds, pagedSessions, pendingDelete, runDelete, sessionId, switchSession])

  const undoDelete = useCallback(() => {
    const rollbackId = pendingDelete?.id ?? null
    if (deleteTimerRef.current !== null) {
      window.clearTimeout(deleteTimerRef.current)
      deleteTimerRef.current = null
    }
    if (rollbackId) {
      setHiddenSessionIds((prev) => {
        const next = { ...prev }
        delete next[rollbackId]
        return next
      })
    }
    setPendingDelete(null)
  }, [pendingDelete])

  const confirmDeleteNow = useCallback(() => {
    if (!pendingDelete) return
    if (deleteTimerRef.current !== null) {
      window.clearTimeout(deleteTimerRef.current)
      deleteTimerRef.current = null
    }
    void runDelete(pendingDelete.id)
  }, [pendingDelete, runDelete])

  useEffect(() => {
    if (!pendingDelete) return
    const stillVisible = pagedSessions.some((item) => item.id === pendingDelete.id)
    if (!stillVisible) {
      setPendingDelete(null)
    }
  }, [pagedSessions, pendingDelete])

  const handleListKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (editingId || visibleSessions.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setFocusedIndex((prev) => Math.min(prev + 1, visibleSessions.length - 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setFocusedIndex((prev) => Math.max(prev - 1, 0))
      return
    }
    if (event.key === 'Enter' && focusedIndex >= 0) {
      event.preventDefault()
      const target = visibleSessions[focusedIndex]
      if (target) handleClick(target.id)
      return
    }
    if (event.key === 'Escape') {
      setFocusedIndex(-1)
    }
  }, [editingId, visibleSessions, focusedIndex, handleClick])

  const formatRelativeTime = useCallback((iso?: string) => {
    if (!iso) return ''
    const ts = Date.parse(iso)
    if (Number.isNaN(ts)) return ''
    const deltaMs = Date.now() - ts
    const minute = 60 * 1000
    const hour = 60 * minute
    const day = 24 * hour
    if (deltaMs < minute) return '此刻'
    if (deltaMs < hour) return `${Math.max(1, Math.floor(deltaMs / minute))}分钟前`
    if (deltaMs < day) return '今天'
    if (deltaMs < 2 * day) return '昨天'
    if (deltaMs < 7 * day) return `${Math.floor(deltaMs / day)}天前`
    const dt = new Date(ts)
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
  }, [])

  const handleScroll = useCallback(() => {
    if (!listRef.current || loadingMore || !hasMore) return
    const el = listRef.current
    const remain = el.scrollHeight - el.scrollTop - el.clientHeight
    if (remain < 120) {
      void loadPage(false)
    }
  }, [hasMore, loadPage, loadingMore])

  const handleCreateSession = useCallback(async () => {
    if (creatingSession) return
    setCreatingSession(true)
    try {
      await createNewSession()
      onClose?.()
    } finally {
      setCreatingSession(false)
    }
  }, [createNewSession, creatingSession, onClose])

  const showListSkeleton = !firstPageResolved || appBootstrapping
  const showEmptyState = firstPageResolved && !appBootstrapping && filteredSessions.length === 0
  const showSessionRows = firstPageResolved && !appBootstrapping

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-slate-50/80 to-white">
      <div className="p-4 border-b border-slate-200/70 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-slate-800">Nini</h1>
          <p className="text-xs text-slate-500 mt-0.5">科研数据分析 AI Agent</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 text-slate-500 md:hidden">
            <X size={18} />
          </button>
        )}
      </div>

      <div className="p-3 border-b border-slate-200/70 space-y-2">
        <button
          onClick={() => { void handleCreateSession() }}
          disabled={creatingSession}
          className="w-full flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white
                     px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
        >
          {creatingSession ? <Loader2 size={14} className="animate-spin" /> : <MessageSquarePlus size={14} />}
          {creatingSession ? '创建中...' : '新建会话'}
        </button>
        <input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="搜索会话标题或 ID"
          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700
                     placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-200 shadow-sm"
        />
      </div>

      {/* 会话列表 */}
      <div
        ref={listRef}
        className="relative flex-1 overflow-y-auto p-3 outline-none"
        tabIndex={0}
        onKeyDown={handleListKeyDown}
        onScroll={handleScroll}
      >
        <div
          className={`space-y-2.5 transition-all duration-300 ${
            showListSkeleton
              ? 'opacity-100 translate-y-0'
              : 'pointer-events-none absolute inset-x-3 top-3 opacity-0 -translate-y-1'
          }`}
        >
          {showListSkeleton && Array.from({ length: 7 }).map((_, index) => (
            <div
              key={`session-skeleton-${index}`}
              className="rounded-xl border border-slate-200/70 bg-white/80 px-3 py-3 shadow-[0_1px_0_rgba(15,23,42,0.03)]"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div
                    className={`h-3 rounded-full bg-slate-200/80 animate-pulse ${
                      index % 3 === 0 ? 'w-2/3' : index % 3 === 1 ? 'w-3/4' : 'w-1/2'
                    }`}
                  />
                </div>
                <div className="h-3 w-12 rounded-full bg-slate-100 animate-pulse" />
              </div>
            </div>
          ))}
        </div>

        <div
          className={`space-y-1.5 transition-all duration-300 ${
            showListSkeleton ? 'opacity-0 translate-y-1' : 'opacity-100 translate-y-0'
          }`}
        >
          {showEmptyState && (
            <div className="rounded-xl border border-dashed border-slate-200 bg-white/80 px-4 py-6 text-center">
              <p className="text-xs text-slate-400">暂无会话记录</p>
              <p className="text-[11px] text-slate-300 mt-1">点击上方“新建会话”开始</p>
            </div>
          )}
          {showSessionRows && visibleSessions.map((s, idx) => {
            const isActive = s.id === sessionId
            const isFocused = idx === focusedIndex
            const displayTitle = s.title && s.title !== '新会话' ? s.title : '新会话'

            if (editingId === s.id) {
              return (
                <div key={s.id} className="flex items-center gap-1">
                  <input
                    ref={editRef}
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => handleRenameSubmit(s.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameSubmit(s.id)
                      if (e.key === 'Escape') setEditingId(null)
                    }}
                    className="flex-1 rounded-lg px-3 py-2 text-sm border border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-300"
                    placeholder="输入会话名称"
                  />
                </div>
              )
            }

            const isRunning = runningSessions.has(s.id)
            const hasPendingQuestion = Boolean(pendingAskUserQuestionsBySession[s.id])

            return (
              <div
                key={s.id}
                className={`group flex items-center gap-2 overflow-hidden rounded-xl px-2.5 border ${
                  isActive
                    ? 'bg-sky-50/80 border-sky-200/80 shadow-[0_1px_0_rgba(14,165,233,0.08)]'
                    : isFocused
                      ? 'bg-white border-slate-300/90 ring-1 ring-slate-200'
                      : 'bg-white/90 border-slate-200/80 hover:bg-slate-50/90'
                }`}
              >
                <button
                  type="button"
                  className={`flex-1 min-w-0 px-1 py-2.5 text-sm cursor-pointer transition-colors text-left ${
                    isActive ? 'text-slate-900' : 'text-slate-700'
                  }`}
                  onClick={() => handleClick(s.id)}
                  onDoubleClick={() => handleDoubleClick(s.id, s.title)}
                  onFocus={() => setFocusedIndex(idx)}
                  onBlur={() => setFocusedIndex((prev) => (prev === idx ? -1 : prev))}
                >
                  <span className="block min-w-0">
                    <span className="block truncate text-left" title={s.title || s.id}>
                      {displayTitle}
                    </span>
                  </span>
                </button>
                <div className="w-24 flex items-center justify-end flex-shrink-0">
                  {hasPendingQuestion ? (
                    <span className="inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-medium text-rose-700">
                      待回答
                    </span>
                  ) : isRunning ? (
                    <Loader2 size={13} className="animate-spin text-sky-400 flex-shrink-0" />
                  ) : (
                    <>
                      <span className="text-[11px] text-slate-400 text-right group-hover:hidden">
                        {formatRelativeTime(s.created_at || s.updated_at || s.last_message_at)}
                      </span>
                      <div className="hidden group-hover:flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => handleDoubleClick(s.id, s.title)}
                          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-all w-7 h-7 flex items-center justify-center"
                          title="重命名会话"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={() => queueDelete(s.id, displayTitle)}
                          className="p-1.5 rounded-lg hover:bg-rose-100 text-slate-400 hover:text-rose-500 transition-all w-7 h-7 flex items-center justify-center"
                          title="删除会话"
                          disabled={pendingDelete?.id === s.id}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {pendingDelete && (
        <div className="m-3 rounded-xl border border-amber-200 bg-gradient-to-r from-amber-50 to-amber-100/70 px-3 py-2.5 text-xs text-amber-900 shadow-sm">
          已标记删除「{pendingDelete.title}」，5 秒内可撤销
          <button
            type="button"
            onClick={undoDelete}
            className="ml-2 inline-flex items-center rounded-md border border-amber-300/80 bg-white/80 px-2 py-0.5 font-medium text-amber-800 hover:bg-white"
          >
            撤销
          </button>
          <button
            type="button"
            onClick={confirmDeleteNow}
            className="ml-1 inline-flex items-center rounded-md border border-rose-300/80 bg-rose-50 px-2 py-0.5 font-medium text-rose-700 hover:bg-rose-100"
          >
            立即删除
          </button>
        </div>
      )}

      <div className="px-3 pb-3 text-[11px] text-slate-400">
        {firstPageResolved && !appBootstrapping ? `共 ${filteredSessions.length} 条会话` : '正在恢复会话...'}
      </div>
    </div>
  )
}
