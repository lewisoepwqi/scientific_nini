/**
 * 会话列表（侧边栏）—— 支持多会话管理、切换、重命名与删除。
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import { useStore } from '../store'
import { MessageSquarePlus, MessageSquare, Trash2, X } from 'lucide-react'
import MemoryPanel from './MemoryPanel'

interface Props {
  onClose?: () => void
}

export default function SessionList({ onClose }: Props) {
  const sessionId = useStore((s) => s.sessionId)
  const sessions = useStore((s) => s.sessions)
  const fetchSessions = useStore((s) => s.fetchSessions)
  const createNewSession = useStore((s) => s.createNewSession)
  const switchSession = useStore((s) => s.switchSession)
  const deleteSession = useStore((s) => s.deleteSession)
  const updateSessionTitle = useStore((s) => s.updateSessionTitle)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const editRef = useRef<HTMLInputElement>(null)

  // 组件挂载时加载会话列表
  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  // 编辑状态时自动聚焦
  useEffect(() => {
    if (editingId) editRef.current?.focus()
  }, [editingId])

  const handleDoubleClick = useCallback((id: string, title: string) => {
    setEditingId(id)
    setEditTitle(title === '新会话' ? '' : title)
  }, [])

  const handleRenameSubmit = useCallback(async (id: string) => {
    const trimmed = editTitle.trim()
    if (trimmed) {
      await updateSessionTitle(id, trimmed)
    }
    setEditingId(null)
  }, [editTitle, updateSessionTitle])

  const handleClick = useCallback((id: string) => {
    switchSession(id)
    onClose?.()
  }, [switchSession, onClose])

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-800">Nini</h1>
          <p className="text-xs text-gray-400 mt-0.5">科研数据分析 AI Agent</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-500 md:hidden">
            <X size={18} />
          </button>
        )}
      </div>

      <div className="p-3 border-b">
        <button
          onClick={() => { createNewSession(); onClose?.() }}
          className="w-full flex items-center justify-center gap-2 rounded-lg border border-gray-200
                     px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <MessageSquarePlus size={14} />
          新建会话
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {sessions.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">暂无会话记录</p>
        )}
        {sessions.map((s) => {
          const isActive = s.id === sessionId
          // 优先显示真实标题，无标题时显示友好占位符
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

          return (
            <div key={s.id} className="group flex items-center gap-1 overflow-hidden">
              <button
                type="button"
                className={`flex-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm cursor-pointer transition-colors text-left min-w-0 ${
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
                onClick={() => handleClick(s.id)}
                onDoubleClick={() => handleDoubleClick(s.id, s.title)}
              >
                <MessageSquare size={14} className="flex-shrink-0" />
                <span className="flex-1 truncate text-left" title={s.title || s.id}>
                  {displayTitle}
                </span>
                <span className="text-xs text-gray-400 flex-shrink-0 ml-auto">
                  {s.message_count}
                </span>
              </button>
              <button
                type="button"
                onClick={() => deleteSession(s.id)}
                className="opacity-0 group-hover:opacity-100 p-1.5 rounded hover:bg-red-100
                           text-gray-400 hover:text-red-500 transition-all flex-shrink-0 w-7 h-7 flex items-center justify-center"
                title="删除会话"
              >
                <Trash2 size={14} />
              </button>
            </div>
          )
        })}
      </div>

      <MemoryPanel />
    </div>
  )
}
