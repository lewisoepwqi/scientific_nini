/**
 * 能力面板 —— 展示用户层面的 Capabilities（区别于底层的 Tools）。
 *
 * 三层架构说明：
 * - Capabilities: 用户可理解的能力（如"差异分析"、"相关性分析"）
 * - Tools: 模型可调用的原子函数（如 t_test, anova）
 * - Skills: 完整工作流项目（Markdown + 脚本 + 参考文档）
 */
import { useEffect, useMemo } from 'react'
import { useStore, type CapabilityItem } from '../store'
import { X, Sparkles, RefreshCw, Zap } from 'lucide-react'

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

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[82vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-purple-600" />
            <h2 className="text-base font-semibold text-gray-800">分析能力</h2>
            <span className="text-xs text-gray-400">{capabilities.length} 个能力</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={fetchCapabilities}
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
          Capabilities 是用户层面的"能力"，帮助您快速开始常见分析任务。
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3">
          <div className="space-y-4">
            {grouped.map(([cat, items]) => {
              const label = CATEGORY_LABELS[cat] || cat
              return (
                <div key={cat}>
                  <h3 className="text-xs font-medium text-gray-500 mb-2 px-1">{label}</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {items.map((cap) => (
                      <div
                        key={cap.name}
                        className="p-3 border border-gray-200 rounded-lg transition-colors group"
                      >
                        <div className="flex items-start gap-2">
                          <span className="text-lg">{getCategoryIcon(cap.icon)}</span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <div className="font-medium text-sm text-gray-800">
                                {cap.display_name}
                              </div>
                              <span
                                className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                                  cap.is_executable
                                    ? 'bg-emerald-50 text-emerald-700'
                                    : 'bg-amber-50 text-amber-700'
                                }`}
                              >
                                {cap.is_executable ? '可执行' : '规划中'}
                              </span>
                            </div>
                            <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                              {cap.description}
                            </div>
                            <div className="flex items-center gap-1 mt-1.5">
                              <Zap size={10} className="text-amber-500" />
                              <span className="text-[10px] text-gray-400">
                                {cap.required_tools.length} 个工具
                              </span>
                            </div>
                            {!cap.is_executable && cap.execution_message && (
                              <div className="mt-1.5 text-[10px] text-amber-700">
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
              <div className="text-xs text-gray-400 text-center py-6">暂无可用的分析能力</div>
            )}
          </div>
        </div>

        <div className="px-5 py-3 border-t bg-gray-50 text-[11px] text-gray-400">
          当前面板用于展示能力目录；仅标记为“可执行”的能力才支持直接接入执行流程。
        </div>
      </div>
    </div>
  )
}
