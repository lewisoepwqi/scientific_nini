/**
 * 工具清单弹窗 —— 仅展示模型可调用的 Function Tools。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useStore, type SkillItem } from '../store'
import { X, RefreshCw, Wrench, ChevronDown, ChevronRight } from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
}

const CATEGORY_LABELS: Record<string, string> = {
  data: '数据操作',
  statistics: '统计检验',
  visualization: '可视化',
  export: '导出',
  report: '报告',
  workflow: '工作流',
  utility: '通用工具',
  other: '其他',
}

function groupTools(tools: SkillItem[]): Array<[string, SkillItem[]]> {
  const map = new Map<string, SkillItem[]>()
  for (const tool of tools) {
    const category = tool.category || 'other'
    if (!map.has(category)) map.set(category, [])
    map.get(category)!.push(tool)
  }

  const order = ['data', 'statistics', 'visualization', 'export', 'report', 'workflow', 'utility', 'other']
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
  const [openCats, setOpenCats] = useState<Set<string>>(new Set(['data']))

  const functionTools = useMemo(
    () => skills.filter((item) => item.type === 'function'),
    [skills],
  )
  const groupedTools = useMemo(() => groupTools(functionTools), [functionTools])

  useEffect(() => {
    if (!open) return
    fetchSkills()
  }, [open, fetchSkills])

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

  const availableToolCount = functionTools.filter((s) => s.enabled && s.expose_to_llm !== false).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[82vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            <Wrench size={18} className="text-blue-600" />
            <h2 className="text-base font-semibold text-gray-800">工具清单（Function Tools）</h2>
            <span className="text-xs text-gray-400">
              {availableToolCount} 个可调用 / {functionTools.length} 个工具
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={fetchSkills}
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

        <div className="px-5 py-2 text-[11px] text-gray-500 border-b bg-gray-50">
          这里仅显示模型可直接调用的工具；Markdown 技能请在“技能管理”中维护。
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3">
          <div className="space-y-1">
            {groupedTools.map(([cat, items]) => {
              const isOpen = openCats.has(cat)
              const label = CATEGORY_LABELS[cat] || cat
              const visibleCount = items.filter((s) => s.enabled && s.expose_to_llm !== false).length
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
                    <span className="ml-auto text-xs text-gray-400">
                      {visibleCount < items.length ? `${visibleCount}/${items.length}` : items.length}
                    </span>
                  </button>
                  {isOpen && (
                    <div className="border-t px-3 py-2 space-y-1.5">
                      {items.map((tool) => (
                        <div key={tool.name} className="text-xs flex items-start gap-2">
                          <span className={`font-mono flex-shrink-0 ${tool.enabled ? 'text-gray-700' : 'text-gray-400 line-through'}`}>
                            {tool.name}
                          </span>
                          <span className="text-gray-400 flex-1">{tool.description}</span>
                          {tool.expose_to_llm === false && (
                            <span className="text-[10px] text-amber-500 flex-shrink-0 bg-amber-50 px-1 rounded">仅内部</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {groupedTools.length === 0 && (
              <div className="text-xs text-gray-400 text-center py-6">暂无可调用工具</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
