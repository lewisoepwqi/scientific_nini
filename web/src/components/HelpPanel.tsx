/**
 * 帮助面板 —— 统一展示分析能力与工具清单。
 *
 * 使用 CommandSheet 作为容器，内部分两个 Tab 切换：
 * - 分析能力：复用 CapabilityPanel 的分组渲染逻辑
 * - 工具清单：复用 SkillCatalogPanel 的分组渲染逻辑
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useStore, type CapabilityItem, type SkillItem } from '../store'
import { RefreshCw, Sparkles, Zap, ChevronDown, ChevronRight } from 'lucide-react'
import CommandSheet from './ui/CommandSheet'
import Button from './ui/Button'

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface Props {
  isOpen: boolean
  onClose: () => void
}

/* ------------------------------------------------------------------ */
/*  分析能力 — 分类与分组                                               */
/* ------------------------------------------------------------------ */

/** 能力分类图标 */
function getCategoryIcon(icon?: string) {
  return icon || <Sparkles size={16} className="text-[var(--accent)]" />
}

/** 根据能力名称推断所属分类 */
function getCapabilityCategory(cap: CapabilityItem): string {
  const name = cap.name
  if (name.includes('analysis') || name.includes('分析')) return 'analysis'
  if (name.includes('exploration') || name.includes('exploration')) return 'exploration'
  if (name.includes('cleaning') || name.includes('清洗')) return 'cleaning'
  if (name.includes('visualization') || name.includes('可视化')) return 'visualization'
  if (name.includes('report') || name.includes('报告')) return 'report'
  return 'other'
}

const CAP_CATEGORY_LABELS: Record<string, string> = {
  analysis: '统计分析',
  exploration: '数据探索',
  cleaning: '数据清洗',
  visualization: '可视化',
  report: '报告生成',
  other: '其他',
}

/** 按分类分组能力，保持固定顺序 */
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
  // 添加不在预定义顺序中的分类
  for (const [key, items] of map) {
    if (!order.includes(key)) grouped.push([key, items])
  }
  return grouped
}

/* ------------------------------------------------------------------ */
/*  工具清单 — 分类与分组                                               */
/* ------------------------------------------------------------------ */

const TOOL_CATEGORY_LABELS: Record<string, string> = {
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

/** 新基础工具名称集合（用于高亮显示） */
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

/** 按分类分组工具，保持固定顺序 */
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

/* ------------------------------------------------------------------ */
/*  Tab 键定义                                                          */
/* ------------------------------------------------------------------ */

const TABS = [
  { key: 'capabilities' as const, label: '分析能力' },
  { key: 'tools' as const, label: '工具清单' },
]

type TabKey = (typeof TABS)[number]['key']

const TAB_HELP_TEXT: Record<TabKey, string> = {
  capabilities: '按研究任务查看 Nini 能做什么，适合先确认分析方向。',
  tools: '查看底层工具和可用状态，适合排查当前能否直接执行。',
}

/* ------------------------------------------------------------------ */
/*  分析能力 Tab 内容                                                    */
/* ------------------------------------------------------------------ */

function CapabilityTabContent() {
  const capabilities = useStore((s) => s.capabilities)
  const fetchCapabilities = useStore((s) => s.fetchCapabilities)

  const grouped = useMemo(() => groupCapabilities(capabilities), [capabilities])

  // 初次挂载时拉取数据
  useEffect(() => {
    fetchCapabilities()
  }, [fetchCapabilities])

  return (
    <>
      {/* 工具栏 */}
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <span className="text-[11px] text-[var(--text-muted)]">
          共 {capabilities.length} 项能力，按分析任务分类
        </span>
        <Button
          variant="ghost"
          onClick={fetchCapabilities}
          className="h-8 w-8 p-0"
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
            const label = CAP_CATEGORY_LABELS[cat] || cat
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
                        <span className="text-base flex items-center">{getCategoryIcon(cap.icon)}</span>
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
            <div className="text-[12px] text-[var(--text-muted)] text-center py-6">暂时还没有可用能力，请稍后刷新再试</div>
          )}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/*  工具清单 Tab 内容                                                    */
/* ------------------------------------------------------------------ */

function ToolsTabContent() {
  const skills = useStore((s) => s.skills)
  const fetchSkills = useStore((s) => s.fetchSkills)
  const [openCats, setOpenCats] = useState<Set<string>>(new Set(['data']))

  // 仅筛选 function 类型的工具
  const functionTools = useMemo(
    () => skills.filter((item) => item.type === 'function'),
    [skills],
  )
  const groupedTools = useMemo(() => groupTools(functionTools), [functionTools])

  // 初次挂载时拉取数据
  useEffect(() => {
    fetchSkills()
  }, [fetchSkills])

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
    <>
      {/* 工具栏 */}
      <div
        className="flex items-center justify-between px-4 py-2 text-[11px] text-[var(--text-muted)]"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <span>当前可调用 {availableToolCount} / {functionTools.length} 个工具</span>
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

      {/* 工具列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="space-y-1">
          {groupedTools.map(([cat, items]) => {
            const isOpen = openCats.has(cat)
            const label = TOOL_CATEGORY_LABELS[cat] || cat
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
                        <span
                          className={`font-mono flex-shrink-0 ${
                            tool.enabled ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] line-through'
                          } ${NEW_BASE_TOOLS.has(tool.name) ? 'text-[var(--accent)] font-medium' : ''}`}
                        >
                          {tool.name}
                        </span>
                        <span className="text-[var(--text-muted)] flex-1">{tool.description}</span>
                        {tool.expose_to_llm === false && (
                          <span className="text-[10px] text-[var(--warning)] flex-shrink-0 bg-[var(--bg-elevated)] px-1 rounded">
                            仅内部
                          </span>
                        )}
                        {NEW_BASE_TOOLS.has(tool.name) && tool.expose_to_llm !== false && (
                          <span className="text-[10px] text-[var(--accent)] flex-shrink-0 bg-[var(--accent-subtle)] px-1 rounded">
                            基础
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          {groupedTools.length === 0 && (
            <div className="text-[12px] text-[var(--text-muted)] text-center py-6">暂时还没有可调用工具，请稍后刷新再试</div>
          )}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/*  主组件                                                              */
/* ------------------------------------------------------------------ */

export function HelpContent() {
  const [activeTab, setActiveTab] = useState<TabKey>('capabilities')

  return (
    <>
      {/* Tab 栏 */}
      <div
        role="tablist"
        aria-label="帮助内容分类"
        className="flex flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            role="tab"
            aria-selected={activeTab === tab.key}
            aria-controls={`help-panel-${tab.key}`}
            id={`help-tab-${tab.key}`}
            className="flex-1 px-4 py-2 text-[13px] font-medium transition-colors"
            style={{
              color: activeTab === tab.key ? 'var(--accent)' : 'var(--text-muted)',
              borderBottom: activeTab === tab.key ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'none',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div
        className="px-4 py-3"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <p className="text-[12px] text-[var(--text-primary)]">
          在这里查看 Nini 能做什么，以及当前有哪些工具可用。
        </p>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          {TAB_HELP_TEXT[activeTab]}
        </p>
      </div>

      {/* Tab 内容 */}
      <div
        role="tabpanel"
        id={`help-panel-${activeTab}`}
        aria-labelledby={`help-tab-${activeTab}`}
        className="flex-1 flex flex-col overflow-hidden"
      >
        {activeTab === 'capabilities' && <CapabilityTabContent />}
        {activeTab === 'tools' && <ToolsTabContent />}
      </div>
    </>
  )
}

export default function HelpPanel({ isOpen, onClose }: Props) {
  return (
    <CommandSheet isOpen={isOpen} onClose={onClose} title="帮助与说明">
      <HelpContent />
    </CommandSheet>
  )
}
