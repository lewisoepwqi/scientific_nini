/**
 * 能力面板 —— 展示用户层面的 Capabilities（区别于底层的 Tools）。
 *
 * 使用 DetailPanel 基础组件（推入式面板，无遮罩）。
 *
 * 三层架构说明：
 * - Capabilities: 用户可理解的能力（如"差异分析"、"相关性分析"）
 * - Tools: 模型可调用的原子函数（如 t_test, anova）
 * - Skills: 完整工作流项目（Markdown + 脚本 + 参考文档）
 */
import { useEffect, useMemo } from 'react'
import { useStore, type CapabilityItem } from '../store'
import { RefreshCw, Zap } from 'lucide-react'
import { DetailPanel } from './ui'
import Button from './ui/Button'

interface Props {
 open: boolean
 onClose: () => void
}

function getCategoryIcon(icon?: string) {
 return icon || '✨'
}

function getCapabilityCategory(cap: CapabilityItem): string {
 const name = cap.name
 if (name.includes('analysis') || name.includes('分析')) return 'analysis'
 if (name.includes('exploration') || name.includes('exploration')) return 'exploration'
 if (name.includes('cleaning') || name.includes('清洗')) return 'cleaning'
 if (name.includes('visualization') || name.includes('可视化')) return 'visualization'
 if (name.includes('report') || name.includes('报告')) return 'report'
 return 'other'
}

const CATEGORY_LABELS: Record<string, string> = {
 analysis: '统计分析',
 exploration: '数据探索',
 cleaning: '数据清洗',
 visualization: '可视化',
 report: '报告生成',
 other: '其他',
}

function groupCapabilities(caps: CapabilityItem[]): Array<[string, CapabilityItem[]]> {
 const map = new Map<string, CapabilityItem[]>()
 for (const cap of caps) {
 const category = getCapabilityCategory(cap)
 if (!map.has(category)) map.set(category, [])
 map.get(category)!.push(cap)
 }

 const order = ['analysis', 'exploration', 'cleaning', 'visualization', 'report', 'other']
 const grouped: Array<[string, CapabilityItem[]]> = []
 for (const key of order) {
 const items = map.get(key)
 if (items && items.length > 0) grouped.push([key, items])
 }
 for (const [key, items] of map) {
 if (!order.includes(key)) grouped.push([key, items])
 }
 return grouped
}

export default function CapabilityPanel({ open, onClose }: Props) {
 const capabilities = useStore((s) => s.capabilities)
 const fetchCapabilities = useStore((s) => s.fetchCapabilities)

 const grouped = useMemo(() => groupCapabilities(capabilities), [capabilities])

 useEffect(() => {
 if (!open) return
 fetchCapabilities()
 }, [open, fetchCapabilities])

 return (
 <DetailPanel isOpen={open} onClose={onClose} title="分析能力">
 {/* 工具栏 */}
 <div
 className="flex items-center justify-between px-4 py-2"
 style={{ borderBottom: '1px solid var(--border-subtle)' }}
 >
 <span className="text-[11px] text-[var(--text-muted)]">
 {capabilities.length} 个能力 · 用户层面的分析能力目录
 </span>
 <Button
 variant="ghost"
 onClick={fetchCapabilities}
 className="h-[24px] w-[24px] p-0"
 title="刷新"
 aria-label="刷新能力列表"
 >
 <RefreshCw size={13} />
 </Button>
 </div>

 {/* 能力列表 */}
 <div className="flex-1 overflow-y-auto px-4 py-3">
 <div className="space-y-4">
 {grouped.map(([cat, items]) => {
 const label = CATEGORY_LABELS[cat] || cat
 return (
 <div key={cat}>
 <h3 className="text-[11px] font-medium text-[var(--text-muted)] mb-2 px-1">{label}</h3>
 <div className="space-y-2">
 {items.map((cap) => (
 <div
 key={cap.name}
 className="p-3 border border-[var(--border-subtle)] rounded-lg"
 >
 <div className="flex items-start gap-2">
 <span className="text-base">{getCategoryIcon(cap.icon)}</span>
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2">
 <div className="font-medium text-[13px] text-[var(--text-primary)]">
 {cap.display_name}
 </div>
 <span
 className={`rounded-full px-1.5 py-0.5 text-[10px] ${
 cap.is_executable
 ? 'bg-[var(--accent-subtle)] text-[var(--accent)]'
 : 'bg-[var(--bg-overlay)] text-[var(--text-muted)]'
 }`}
 >
 {cap.is_executable ? '可执行' : '规划中'}
 </span>
 </div>
 <div className="text-[12px] text-[var(--text-secondary)] mt-0.5 line-clamp-2">
 {cap.description}
 </div>
 <div className="flex items-center gap-1 mt-1.5">
 <Zap size={10} className="text-[var(--warning)]" />
 <span className="text-[10px] text-[var(--text-muted)]">
 {cap.required_tools.length} 个工具
 </span>
 </div>
 {!cap.is_executable && cap.execution_message && (
 <div className="mt-1.5 text-[10px] text-[var(--warning)]">
 {cap.execution_message}
 </div>
 )}
 </div>
 </div>
 </div>
 ))}
 </div>
 </div>
 )
 })}
 {grouped.length === 0 && (
 <div className="text-[12px] text-[var(--text-muted)] text-center py-6">暂无可用的分析能力</div>
 )}
 </div>
 </div>
 </DetailPanel>
 )
}
