/**
 * 技能清单弹窗 —— 展示技能分类与可用工作流模板。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useStore, type SkillItem } from '../store'
import { X, RefreshCw, Wrench, Workflow, ChevronDown, ChevronRight } from 'lucide-react'

interface WorkflowTemplate {
  id: string
  name: string
  description: string
  steps: Array<{
    tool_name: string
  }>
}

interface Props {
  open: boolean
  onClose: () => void
}

const CATEGORY_LABELS: Record<string, string> = {
  data: '数据操作',
  statistics: '统计检验',
  visualization: '可视化',
  code: '代码执行',
  export: '导出报告',
  composite: '复合分析',
  workflow: '工作流',
  other: '其他',
  markdown: 'Markdown',
}

function groupSkills(skills: SkillItem[]): Array<[string, SkillItem[]]> {
  const map = new Map<string, SkillItem[]>()
  for (const s of skills) {
    const cat = s.type === 'markdown' ? 'markdown' : (s.category || 'other')
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat)!.push(s)
  }
  const order = ['workflow', 'data', 'statistics', 'visualization', 'code', 'export', 'composite', 'other', 'markdown']
  const grouped: Array<[string, SkillItem[]]> = []
  for (const key of order) {
    const items = map.get(key)
    if (items && items.length > 0) grouped.push([key, items])
  }
  for (const [key, items] of map) {
    if (!order.includes(key)) grouped.push([key, items])
  }
  return grouped
}

export default function SkillCatalogPanel({ open, onClose }: Props) {
  const skills = useStore((s) => s.skills)
  const fetchSkills = useStore((s) => s.fetchSkills)
  const [openCats, setOpenCats] = useState<Set<string>>(new Set(['workflow']))
  const [loadingWorkflows, setLoadingWorkflows] = useState(false)
  const [workflowTemplates, setWorkflowTemplates] = useState<WorkflowTemplate[]>([])

  const grouped = useMemo(() => groupSkills(skills), [skills])

  const fetchWorkflows = useCallback(async () => {
    setLoadingWorkflows(true)
    try {
      const resp = await fetch('/api/workflows')
      const payload = await resp.json()
      if (payload.success && Array.isArray(payload.data)) {
        setWorkflowTemplates(payload.data)
      } else {
        setWorkflowTemplates([])
      }
    } catch (e) {
      console.error('获取工作流列表失败:', e)
      setWorkflowTemplates([])
    } finally {
      setLoadingWorkflows(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    fetchSkills()
    fetchWorkflows()
  }, [open, fetchSkills, fetchWorkflows])

  const toggleCat = useCallback((cat: string) => {
    setOpenCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) {
        next.delete(cat)
      } else {
        next.add(cat)
      }
      return next
    })
  }, [])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[82vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            <Wrench size={18} className="text-blue-600" />
            <h2 className="text-base font-semibold text-gray-800">技能清单</h2>
            <span className="text-xs text-gray-400">({skills.length})</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                fetchSkills()
                fetchWorkflows()
              }}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
              title="刷新"
            >
              <RefreshCw size={14} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
              title="关闭"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-4">
          <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-3">
            <div className="flex items-center gap-2 mb-2">
              <Workflow size={15} className="text-blue-600" />
              <div className="text-sm font-medium text-blue-900">可用工作流模板</div>
            </div>
            {loadingWorkflows ? (
              <div className="text-xs text-blue-700/70">加载中...</div>
            ) : workflowTemplates.length === 0 ? (
              <div className="text-xs text-blue-700/70">当前暂无已保存模板</div>
            ) : (
              <div className="space-y-1.5">
                {workflowTemplates.map((wf) => (
                  <div key={wf.id} className="rounded-lg border border-blue-100 bg-white/80 px-2.5 py-2">
                    <div className="text-sm text-gray-800 font-medium">{wf.name}</div>
                    {wf.description && (
                      <div className="text-xs text-gray-500 mt-0.5">{wf.description}</div>
                    )}
                    <div className="text-[11px] text-gray-400 mt-1">
                      {wf.steps.length} 步：{wf.steps.map((s) => s.tool_name).join(' → ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="text-xs text-gray-500 mb-2">技能分类</div>
            <div className="space-y-1">
              {grouped.map(([cat, items]) => {
                const isOpen = openCats.has(cat)
                const label = CATEGORY_LABELS[cat] || cat
                return (
                  <div key={cat} className="border border-gray-200 rounded-lg">
                    <button
                      onClick={() => toggleCat(cat)}
                      className="w-full px-3 py-2 text-left flex items-center gap-2 hover:bg-gray-50 transition-colors"
                    >
                      {isOpen ? (
                        <ChevronDown size={14} className="text-gray-400" />
                      ) : (
                        <ChevronRight size={14} className="text-gray-400" />
                      )}
                      <span className="text-sm font-medium text-gray-700">{label}</span>
                      <span className="ml-auto text-xs text-gray-400">{items.length}</span>
                    </button>
                    {isOpen && (
                      <div className="border-t px-3 py-2 space-y-1">
                        {items.map((s) => (
                          <div key={s.name} className="text-xs text-gray-600 flex items-start gap-2">
                            <span className={`font-mono ${s.enabled ? 'text-gray-700' : 'text-gray-400 line-through'}`}>
                              {s.name}
                            </span>
                            <span className="text-gray-400">{s.description}</span>
                            {s.expose_to_llm === false && (
                              <span className="text-[10px] text-amber-500 flex-shrink-0">hidden</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
              {grouped.length === 0 && (
                <div className="text-xs text-gray-400">暂无技能</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
