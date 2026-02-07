/**
 * 工作流模板管理面板 —— 列出已保存的模板，支持一键应用和删除。
 */
import { useEffect, useState, useCallback } from 'react'
import { Play, Trash2, Zap, X } from 'lucide-react'

interface WorkflowStep {
  tool_name: string
  arguments: Record<string, unknown>
  description: string
}

interface WorkflowTemplate {
  id: string
  name: string
  description: string
  steps: WorkflowStep[]
  created_at: string
}

interface Props {
  open: boolean
  onClose: () => void
  onApply?: (templateId: string) => void
}

export default function WorkflowPanel({ open, onClose, onApply }: Props) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const fetchTemplates = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/workflows')
      const payload = await resp.json()
      if (payload.success && Array.isArray(payload.data)) {
        setTemplates(payload.data)
      }
    } catch (e) {
      console.error('获取工作流模板失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) fetchTemplates()
  }, [open, fetchTemplates])

  const handleDelete = async (id: string) => {
    try {
      await fetch(`/api/workflows/${id}`, { method: 'DELETE' })
      setTemplates((prev) => prev.filter((t) => t.id !== id))
    } catch (e) {
      console.error('删除工作流模板失败:', e)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-amber-500" />
            <h2 className="text-base font-semibold text-gray-800">工作流模板</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {loading ? (
            <div className="text-center text-sm text-gray-400 py-8">加载中...</div>
          ) : templates.length === 0 ? (
            <div className="text-center text-sm text-gray-400 py-8">
              <p>暂无已保存的工作流模板</p>
              <p className="mt-1 text-xs">完成一次分析后，告诉 Nini "保存为模板"即可创建</p>
            </div>
          ) : (
            <div className="space-y-3">
              {templates.map((t) => (
                <div
                  key={t.id}
                  className="border border-gray-200 rounded-xl p-3 hover:border-gray-300 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="font-medium text-sm text-gray-800">{t.name}</div>
                      {t.description && (
                        <div className="text-xs text-gray-500 mt-0.5">{t.description}</div>
                      )}
                      <div className="text-xs text-gray-400 mt-1">
                        {t.steps.length} 个步骤：
                        {t.steps.map((s) => s.tool_name).join(' → ')}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 ml-2">
                      {onApply && (
                        <button
                          onClick={() => onApply(t.id)}
                          className="p-1.5 rounded-lg text-blue-500 hover:bg-blue-50 transition-colors"
                          title="应用此模板"
                        >
                          <Play size={14} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(t.id)}
                        className="p-1.5 rounded-lg text-red-400 hover:bg-red-50 transition-colors"
                        title="删除"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {/* 展开步骤详情 */}
                  <button
                    onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                    className="text-xs text-blue-500 hover:text-blue-600 mt-1"
                  >
                    {expandedId === t.id ? '收起步骤' : '查看步骤详情'}
                  </button>
                  {expandedId === t.id && (
                    <div className="mt-2 pl-3 border-l-2 border-gray-200 space-y-1">
                      {t.steps.map((step, idx) => (
                        <div key={idx} className="text-xs text-gray-600">
                          <span className="text-gray-400">{idx + 1}.</span>{' '}
                          <span className="font-medium">{step.tool_name}</span>
                          {Object.keys(step.arguments).length > 0 && (
                            <span className="text-gray-400 ml-1">
                              ({Object.entries(step.arguments).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
