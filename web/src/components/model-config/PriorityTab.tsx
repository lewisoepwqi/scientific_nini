/**
 * 优先级排序 Tab —— 纯拖拽排序，只有一个"保存顺序"按钮。
 * 不再提供数字输入框，消除双重编辑方式的混乱。
 * 数据从 store.modelProviders 读取初始顺序。
 */
import { useState, useEffect, useCallback } from 'react'
import { Loader2, GripVertical, CheckCircle, XCircle } from 'lucide-react'
import { useStore } from '../../store'
import type { ModelProviderInfo } from '../../store'

export default function PriorityTab() {
  const modelProviders = useStore((s) => s.modelProviders)

  // 本地排序状态（拖拽更新此数组）
  const [orderedList, setOrderedList] = useState<ModelProviderInfo[]>([])
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ success: boolean; text: string } | null>(null)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)
  // 跟踪是否有未保存的变更
  const [hasChanges, setHasChanges] = useState(false)

  // 当 store 数据更新时重新初始化排序列表（按 priority 升序）
  useEffect(() => {
    const sorted = [...modelProviders].sort((a, b) => a.priority - b.priority)
    setOrderedList(sorted)
    setHasChanges(false)
  }, [modelProviders])

  const reorderList = useCallback((sourceId: string, targetId: string) => {
    if (!sourceId || !targetId || sourceId === targetId) return
    setOrderedList((prev) => {
      const sourceIdx = prev.findIndex((item) => item.id === sourceId)
      const targetIdx = prev.findIndex((item) => item.id === targetId)
      if (sourceIdx < 0 || targetIdx < 0) return prev
      const next = [...prev]
      const [moved] = next.splice(sourceIdx, 1)
      next.splice(targetIdx, 0, moved)
      return next
    })
    setHasChanges(true)
    setMessage(null)
  }, [])

  const handleSave = useCallback(async () => {
    setSaving(true)
    setMessage(null)
    try {
      const priorities = orderedList.reduce<Record<string, number>>((acc, item, index) => {
        acc[item.id] = index
        return acc
      }, {})
      const resp = await fetch('/api/models/priorities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priorities }),
      })
      const data = await resp.json()
      if (data.success) {
        window.dispatchEvent(new Event('nini:model-config-updated'))
        setMessage({ success: true, text: '优先级已保存并生效' })
        setHasChanges(false)
      } else {
        setMessage({ success: false, text: data.error || '优先级保存失败' })
      }
    } catch (e) {
      setMessage({ success: false, text: `请求失败: ${e}` })
    } finally {
      setSaving(false)
    }
  }, [orderedList])

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center justify-between mb-1">
          <div>
            <div className="text-sm font-medium text-gray-800">自动路由优先级</div>
            <div className="text-xs text-gray-500 mt-1">
              拖拽行调整顺序。当多个供应商均可用时，系统按此顺序选择第一个响应的供应商。
            </div>
          </div>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !hasChanges}
            className="ml-4 flex-shrink-0 px-4 py-1.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? (
              <span className="inline-flex items-center gap-1.5">
                <Loader2 size={14} className="animate-spin" />
                保存中
              </span>
            ) : (
              '保存顺序'
            )}
          </button>
        </div>

        {message && (
          <div className={`mt-3 text-xs px-3 py-1.5 rounded-lg ${
            message.success ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
          }`}>
            {message.text}
          </div>
        )}

        {hasChanges && (
          <div className="mt-2 text-[11px] text-amber-600 bg-amber-50 rounded px-2 py-1">
            顺序已调整，点击「保存顺序」生效
          </div>
        )}
      </div>

      <div className="space-y-2">
        {orderedList.map((p, index) => (
          <div
            key={p.id}
            onDragOver={(e) => {
              if (!draggingId) return
              e.preventDefault()
              if (dragOverId !== p.id) setDragOverId(p.id)
            }}
            onDrop={(e) => {
              e.preventDefault()
              const sourceId = draggingId || e.dataTransfer.getData('text/plain')
              reorderList(sourceId, p.id)
              setDraggingId(null)
              setDragOverId(null)
            }}
            className={`flex items-center gap-3 rounded-xl border p-3 transition-colors ${
              dragOverId === p.id && draggingId && draggingId !== p.id
                ? 'ring-2 ring-blue-200 border-blue-300 bg-blue-50'
                : p.configured
                  ? 'border-emerald-200 bg-emerald-50/40'
                  : 'border-gray-200 bg-gray-50/60'
            }`}
          >
            {/* 拖拽手柄 */}
            <button
              type="button"
              draggable
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = 'move'
                e.dataTransfer.setData('text/plain', p.id)
                setDraggingId(p.id)
                setDragOverId(p.id)
              }}
              onDragEnd={() => {
                setDraggingId(null)
                setDragOverId(null)
              }}
              className="p-1 rounded hover:bg-gray-200 text-gray-400 cursor-grab active:cursor-grabbing flex-shrink-0"
              title="拖拽调整顺序"
            >
              <GripVertical size={16} />
            </button>

            {/* 顺序序号 */}
            <div className="w-6 text-center text-xs font-mono text-gray-400 flex-shrink-0">
              #{index + 1}
            </div>

            {/* 状态图标 */}
            {p.configured ? (
              <CheckCircle size={16} className="text-emerald-500 flex-shrink-0" />
            ) : (
              <XCircle size={16} className="text-gray-300 flex-shrink-0" />
            )}

            {/* 提供商信息 */}
            <div className="flex-1 min-w-0">
              <div className="font-medium text-sm text-gray-800 truncate">{p.name}</div>
              <div className="text-xs text-gray-500 truncate">
                {p.configured
                  ? (p.current_model || '未设置模型')
                  : '未配置 · 不参与自动路由'
                }
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="text-[11px] text-gray-400 text-center">
        未配置的供应商不参与自动路由，无论排位如何都不会被选中
      </div>
    </div>
  )
}
