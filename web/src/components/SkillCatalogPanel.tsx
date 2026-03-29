/**
 * 工具清单面板 —— 仅展示模型可调用的 Function Tools。
 *
 * 使用 DetailPanel 基础组件（推入式面板，无遮罩）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useStore, type SkillItem } from '../store'
import { RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { DetailPanel } from './ui'
import Button from './ui/Button'

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
 session: '会话资源',
 other: '其他',
}

/**
 * 新基础工具名称集合（工具基础层重构）
 * 用于高亮显示新工具系统的基础工具
 */
const NEW_BASE_TOOLS = new Set([
 'task_state',
 'dataset_catalog',
 'dataset_transform',
 'stat_test',
 'stat_model',
 'stat_interpret',
 'chart_session',
 'report_session',
 'workspace_session',
 'code_session',
])

function groupTools(tools: SkillItem[]): Array<[string, SkillItem[]]> {
 const map = new Map<string, SkillItem[]>()
 for (const tool of tools) {
 const category = tool.category || 'other'
 if (!map.has(category)) map.set(category, [])
 map.get(category)!.push(tool)
 }

 const order = ['data', 'statistics', 'visualization', 'export', 'report', 'workflow', 'utility', 'session', 'other']
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

 const availableToolCount = functionTools.filter((s) => s.enabled && s.expose_to_llm !== false).length

 return (
 <DetailPanel isOpen={open} onClose={onClose} title="工具清单">
 {/* 工具栏：数量 + 刷新 */}
 <div
 className="flex items-center justify-between px-4 py-2 text-[11px] text-[var(--text-muted)]"
 style={{ borderBottom: '1px solid var(--border-subtle)' }}
 >
 <span>{availableToolCount} 个可调用 / {functionTools.length} 个工具</span>
 <Button
 type="button"
 variant="ghost"
 onClick={fetchSkills}
 className="h-8 w-8 p-0"
 title="刷新"
 >
 <RefreshCw size={13} />
 </Button>
 </div>

 {/* 说明栏 */}
 <div className="px-4 py-2 text-[11px] text-[var(--text-muted)]" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
 仅显示模型可直接调用的工具；Markdown 技能请在技能管理中维护。
 </div>

 {/* 工具列表 */}
 <div className="flex-1 overflow-y-auto px-4 py-3">
 <div className="space-y-1">
 {groupedTools.map(([cat, items]) => {
 const isOpen = openCats.has(cat)
 const label = CATEGORY_LABELS[cat] || cat
 const visibleCount = items.filter((s) => s.enabled && s.expose_to_llm !== false).length
 return (
 <div key={cat} className="border border-[var(--border-subtle)] rounded-lg">
 <Button
 type="button"
 variant="ghost"
 onClick={() => toggleCat(cat)}
 className="w-full px-3 py-2 text-left flex items-center gap-2"
 >
 {isOpen ? (
 <ChevronDown size={14} className="text-[var(--text-muted)]" />
 ) : (
 <ChevronRight size={14} className="text-[var(--text-muted)]" />
 )}
 <span className="text-[12px] font-medium text-[var(--text-primary)]">{label}</span>
 <span className="ml-auto text-[11px] text-[var(--text-muted)]">
 {visibleCount < items.length ? `${visibleCount}/${items.length}` : items.length}
 </span>
 </Button>
 {isOpen && (
 <div className="px-3 py-2 space-y-1.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
 {items.map((tool) => (
 <div key={tool.name} className="text-[11px] flex items-start gap-2">
 <span className={`font-mono flex-shrink-0 ${tool.enabled ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] line-through'} ${NEW_BASE_TOOLS.has(tool.name) ? 'text-[var(--accent)] font-medium' : ''}`}>
 {tool.name}
 </span>
 <span className="text-[var(--text-muted)] flex-1">{tool.description}</span>
 {tool.expose_to_llm === false && (
 <span className="text-[10px] text-[var(--warning)] flex-shrink-0 bg-[var(--bg-elevated)] px-1 rounded">仅内部</span>
 )}
 {NEW_BASE_TOOLS.has(tool.name) && tool.expose_to_llm !== false && (
 <span className="text-[10px] text-[var(--accent)] flex-shrink-0 bg-[var(--accent-subtle)] px-1 rounded">基础</span>
 )}
 </div>
 ))}
 </div>
 )}
 </div>
 )
 })}
 {groupedTools.length === 0 && (
 <div className="text-[12px] text-[var(--text-muted)] text-center py-6">暂无可调用工具</div>
 )}
 </div>
 </div>
 </DetailPanel>
 )
}
