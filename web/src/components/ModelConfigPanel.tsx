/**
 * 模型配置面板 —— 查看、编辑、保存模型提供商配置，测试连接。
 * 模型选择支持搜索过滤和远程模型列表获取。
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import {
  X, CheckCircle, XCircle, Loader2, Zap, RefreshCw,
  Edit3, Save, ChevronDown, ChevronUp, Search, Star, GripVertical,
} from 'lucide-react'
import { useStore } from '../store'

interface ModelProvider {
  id: string
  name: string
  configured: boolean
  current_model: string
  available_models: string[]
  api_key_hint: string
  base_url: string
  priority: number
  config_source: 'db' | 'env' | 'none'
}

interface TestResult {
  loading: boolean
  success?: boolean
  message?: string
}

interface EditForm {
  api_key: string
  model: string
  base_url: string
}

interface SaveStatus {
  loading: boolean
  success?: boolean
  message?: string
}

interface RemoteModels {
  loading: boolean
  models: string[]
  source: 'remote' | 'static' | null
}

interface ModelPurpose {
  id: string
  label: string
}

interface ActivePurposeModel {
  provider_id: string
  provider_name: string
  model: string
}

interface PurposeRoute {
  provider_id: string | null
  model: string | null
  base_url: string | null
}

interface ProviderOption {
  id: string
  name: string
}

interface Props {
  open: boolean
  onClose: () => void
}

/**
 * 模型搜索下拉框 —— 支持搜索过滤、远程模型列表、自定义输入。
 */
function ModelCombobox({
  value,
  onChange,
  staticModels,
  providerId,
  size = 'md',
}: {
  value: string
  onChange: (val: string) => void
  staticModels: string[]
  providerId: string
  size?: 'sm' | 'md'
}) {
  const [query, setQuery] = useState(value)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [remote, setRemote] = useState<RemoteModels>({
    loading: false,
    models: [],
    source: null,
  })
  const inputRef = useRef<HTMLInputElement>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // 展开时获取远程模型列表
  useEffect(() => {
    if (!dropdownOpen) return
    let cancelled = false
    setRemote((prev) => ({ ...prev, loading: true }))

    fetch(`/api/models/${providerId}/available`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        if (data.success && data.data) {
          setRemote({
            loading: false,
            models: data.data.models || [],
            source: data.data.source || 'static',
          })
        } else {
          setRemote({ loading: false, models: staticModels, source: 'static' })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRemote({ loading: false, models: staticModels, source: 'static' })
        }
      })

    return () => { cancelled = true }
  }, [dropdownOpen, providerId, staticModels])

  // 点击外部关闭
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClick)
      return () => document.removeEventListener('mousedown', handleClick)
    }
  }, [dropdownOpen])

  // 同步外部 value 变化
  useEffect(() => {
    setQuery(value)
  }, [value])

  const allModels = remote.models.length > 0 ? remote.models : staticModels
  const filtered = query
    ? allModels.filter((m) => m.toLowerCase().includes(query.toLowerCase()))
    : allModels

  const handleSelect = (model: string) => {
    setQuery(model)
    onChange(model)
    setDropdownOpen(false)
  }

  const handleInputChange = (val: string) => {
    setQuery(val)
    onChange(val)
    if (!dropdownOpen) setDropdownOpen(true)
  }

  const compact = size === 'sm'
  const inputClassName = compact
    ? 'w-full h-8 pl-7 pr-7 text-xs border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300'
    : 'w-full pl-8 pr-8 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300'
  const iconSize = compact ? 12 : 14

  return (
    <div className="relative" ref={wrapperRef}>
      <div className="relative">
        <Search size={iconSize} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          name={`${providerId}-model-search`}
          autoComplete="off"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          onFocus={() => setDropdownOpen(true)}
          placeholder="搜索或输入模型名称..."
          className={inputClassName}
        />
        <button
          type="button"
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        >
          <ChevronDown size={iconSize} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {dropdownOpen && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {remote.loading ? (
            <div className="flex items-center gap-2 px-3 py-3 text-xs text-gray-400">
              <Loader2 size={12} className="animate-spin" />
              正在获取模型列表...
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-3 py-3 text-xs text-gray-400">
              {query ? (
                <span>
                  无匹配结果，按 Enter 使用自定义模型：
                  <button
                    className="ml-1 text-blue-500 hover:underline"
                    onClick={() => handleSelect(query)}
                  >
                    {query}
                  </button>
                </span>
              ) : '无可用模型'}
            </div>
          ) : (
            <>
              {remote.source === 'remote' && (
                <div className="px-3 py-1.5 text-[10px] text-emerald-600 bg-emerald-50 border-b">
                  远程获取 · {allModels.length} 个模型
                </div>
              )}
              {filtered.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => handleSelect(m)}
                  className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 transition-colors ${
                    m === value ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
                  }`}
                >
                  {m}
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * 提供商搜索下拉框 —— 与模型下拉保持一致的输入与面板样式。
 */
function ProviderCombobox({
  value,
  onChange,
  options,
  placeholder = '搜索提供商...',
  disabled = false,
}: {
  value: string
  onChange: (val: string) => void
  options: ProviderOption[]
  placeholder?: string
  disabled?: boolean
}) {
  const [query, setQuery] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  const selected = value ? options.find((item) => item.id === value) : undefined
  const selectedLabel = selected?.name || ''

  useEffect(() => {
    if (!dropdownOpen) {
      setQuery(selectedLabel)
    }
  }, [dropdownOpen, selectedLabel])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClick)
      return () => document.removeEventListener('mousedown', handleClick)
    }
  }, [dropdownOpen])

  const queryText = query.trim().toLowerCase()
  const filtered = queryText
    ? options.filter(
      (item) =>
        item.name.toLowerCase().includes(queryText) || item.id.toLowerCase().includes(queryText),
    )
    : options

  const pickProvider = (providerId: string) => {
    const picked = options.find((item) => item.id === providerId)
    setQuery(picked?.name || '')
    onChange(providerId)
    setDropdownOpen(false)
  }

  return (
    <div className="relative" ref={wrapperRef}>
      <div className="relative">
        <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            if (!dropdownOpen) setDropdownOpen(true)
          }}
          onFocus={() => !disabled && setDropdownOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              if (!queryText) {
                pickProvider('')
                return
              }
              if (filtered.length > 0) {
                pickProvider(filtered[0].id)
              }
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full h-8 pl-7 pr-7 text-xs border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300 disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => !disabled && setDropdownOpen(!dropdownOpen)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 disabled:opacity-50"
          disabled={disabled}
        >
          <ChevronDown size={12} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {dropdownOpen && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          <button
            type="button"
            onClick={() => pickProvider('')}
            className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 transition-colors ${
              !value ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
            }`}
          >
            自动（跟随全局）
          </button>
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-xs text-gray-400">无匹配提供商</div>
          ) : (
            filtered.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => pickProvider(item.id)}
                className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 transition-colors ${
                  item.id === value ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
                }`}
              >
                {item.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export default function ModelConfigPanel({ open, onClose }: Props) {
  const activeModel = useStore((s) => s.activeModel)
  const fetchActiveModel = useStore((s) => s.fetchActiveModel)
  const setPreferredProvider = useStore((s) => s.setPreferredProvider)

  type PanelTab = 'overview' | 'providers'
  type ProviderFilter = 'all' | 'configured' | 'unconfigured'

  // 从 activeModel 中获取当前全局首选
  const [routingPreferredProvider, setRoutingPreferredProvider] = useState<string | null>(null)
  const defaultProvider = routingPreferredProvider ?? activeModel?.preferred_provider ?? null

  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [purposes, setPurposes] = useState<ModelPurpose[]>([])
  const [purposeRoutes, setPurposeRoutes] = useState<Record<string, PurposeRoute>>({})
  const [activeByPurpose, setActiveByPurpose] = useState<Record<string, ActivePurposeModel>>({})
  const [purposeSaving, setPurposeSaving] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(false)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ api_key: '', model: '', base_url: '' })
  const [saveStatus, setSaveStatus] = useState<Record<string, SaveStatus>>({})
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [defaultLoading, setDefaultLoading] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<PanelTab>('overview')
  const [providerQuery, setProviderQuery] = useState('')
  const [providerFilter, setProviderFilter] = useState<ProviderFilter>('all')
  const [priorityDrafts, setPriorityDrafts] = useState<Record<string, number>>({})
  const [prioritySaving, setPrioritySaving] = useState(false)
  const [priorityMessage, setPriorityMessage] = useState<{ success: boolean; text: string } | null>(null)
  const [draggingProviderId, setDraggingProviderId] = useState<string | null>(null)
  const [dragOverProviderId, setDragOverProviderId] = useState<string | null>(null)

  const fetchModels = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/models')
      const data = await resp.json()
      if (data.success && Array.isArray(data.data)) {
        const loadedProviders = data.data as ModelProvider[]
        setProviders(loadedProviders)
        setPriorityDrafts(
          loadedProviders.reduce<Record<string, number>>((acc, item) => {
            acc[item.id] = item.priority
            return acc
          }, {}),
        )
      }
    } catch (e) {
      console.error('获取模型列表失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchRouting = useCallback(async () => {
    try {
      const resp = await fetch('/api/models/routing')
      const data = await resp.json()
      if (!data.success || !data.data) return
      const payload = data.data as {
        preferred_provider?: string | null
        purpose_routes?: Record<string, PurposeRoute>
        active_by_purpose?: Record<string, ActivePurposeModel>
        purposes?: ModelPurpose[]
      }
      setRoutingPreferredProvider(payload.preferred_provider || null)
      setPurposeRoutes(payload.purpose_routes || {})
      setActiveByPurpose(payload.active_by_purpose || {})
      setPurposes(Array.isArray(payload.purposes) ? payload.purposes : [])
    } catch (e) {
      console.error('获取用途模型路由失败:', e)
    }
  }, [])

  useEffect(() => {
    if (open) {
      fetchModels()
      fetchRouting()
      setTestResults({})
      setEditingId(null)
      setSaveStatus({})
      setExpandedId(null)
      setActiveTab('overview')
      setProviderQuery('')
      setProviderFilter('all')
      setPriorityMessage(null)
    }
  }, [open, fetchModels, fetchRouting])

  const handleTest = useCallback(async (providerId: string) => {
    setTestResults((prev) => ({
      ...prev,
      [providerId]: { loading: true },
    }))
    try {
      const resp = await fetch(`/api/models/${providerId}/test`, { method: 'POST' })
      const data = await resp.json()
      setTestResults((prev) => ({
        ...prev,
        [providerId]: {
          loading: false,
          success: data.success,
          message: data.success ? data.data?.message : data.error,
        },
      }))
    } catch (e) {
      setTestResults((prev) => ({
        ...prev,
        [providerId]: { loading: false, success: false, message: `请求失败: ${e}` },
      }))
    }
  }, [])

  const startEdit = useCallback((p: ModelProvider) => {
    setEditingId(p.id)
    setExpandedId(p.id)
    setEditForm({
      api_key: '',
      model: p.current_model || '',
      base_url: p.base_url || '',
    })
  }, [])

  const cancelEdit = useCallback(() => {
    setEditingId(null)
  }, [])

  const handleSave = useCallback(async (providerId: string) => {
    setSaveStatus((prev) => ({ ...prev, [providerId]: { loading: true } }))
    try {
      const normalizedApiKey = editForm.api_key.trim()
      const body: Record<string, unknown> = {
        provider_id: providerId,
        model: editForm.model || undefined,
        base_url: editForm.base_url || undefined,
      }
      // 仅在用户输入了新 Key 时才发送
      if (normalizedApiKey) {
        body.api_key = normalizedApiKey
      }

      const resp = await fetch('/api/models/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await resp.json()

      if (data.success) {
        setSaveStatus((prev) => ({
          ...prev,
          [providerId]: { loading: false, success: true, message: '配置已保存并生效' },
        }))
        setEditingId(null)
        // 刷新列表
        await fetchModels()
        await fetchActiveModel()
        await fetchRouting()
        window.dispatchEvent(new Event('nini:model-config-updated'))
      } else {
        setSaveStatus((prev) => ({
          ...prev,
          [providerId]: { loading: false, success: false, message: data.error || '保存失败' },
        }))
      }
    } catch (e) {
      setSaveStatus((prev) => ({
        ...prev,
        [providerId]: { loading: false, success: false, message: `请求失败: ${e}` },
      }))
    }
  }, [editForm, fetchActiveModel, fetchModels, fetchRouting])

  const handleSetDefault = useCallback(async (providerId: string) => {
    setDefaultLoading(providerId)
    try {
      await setPreferredProvider(providerId)
      await fetchRouting()
    } finally {
      setDefaultLoading(null)
    }
  }, [fetchRouting, setPreferredProvider])

  const handleClearDefault = useCallback(async () => {
    setDefaultLoading('clear')
    try {
      await setPreferredProvider('')
      await fetchRouting()
    } finally {
      setDefaultLoading(null)
    }
  }, [fetchRouting, setPreferredProvider])

  const handlePurposeFieldChange = useCallback(
    (purposeId: string, patch: Partial<PurposeRoute>) => {
      setPurposeRoutes((prev) => {
        const current = prev[purposeId] || { provider_id: null, model: null, base_url: null }
        const next: PurposeRoute = { ...current, ...patch }
        if (!next.provider_id) {
          next.model = null
          next.base_url = null
        }
        return { ...prev, [purposeId]: next }
      })
    },
    [],
  )

  const handleSavePurposeRoute = useCallback(async (purposeId: string) => {
    const route = purposeRoutes[purposeId] || { provider_id: null, model: null, base_url: null }
    setPurposeSaving((prev) => ({ ...prev, [purposeId]: true }))
    try {
      const resp = await fetch('/api/models/routing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          purpose_routes: {
            [purposeId]: {
              provider_id: route.provider_id,
              model: route.model,
              base_url: route.base_url,
            },
          },
        }),
      })
      const data = await resp.json()
      if (!data.success) {
        console.error(`保存用途模型路由失败(${purposeId}):`, data.error)
      }
      await fetchRouting()
      await fetchActiveModel()
      window.dispatchEvent(new Event('nini:model-config-updated'))
    } catch (e) {
      console.error(`保存用途模型路由失败(${purposeId}):`, e)
    } finally {
      setPurposeSaving((prev) => ({ ...prev, [purposeId]: false }))
    }
  }, [fetchActiveModel, fetchRouting, purposeRoutes])

  const handleSavePriorities = useCallback(async () => {
    setPrioritySaving(true)
    setPriorityMessage(null)
    try {
      const payload = providers.reduce<Record<string, number>>((acc, item) => {
        acc[item.id] = Math.max(0, priorityDrafts[item.id] ?? item.priority)
        return acc
      }, {})
      const resp = await fetch('/api/models/priorities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priorities: payload }),
      })
      const data = await resp.json()
      if (data.success) {
        await fetchModels()
        await fetchRouting()
        await fetchActiveModel()
        window.dispatchEvent(new Event('nini:model-config-updated'))
        setPriorityMessage({ success: true, text: '优先级已保存并生效' })
      } else {
        setPriorityMessage({ success: false, text: data.error || '优先级保存失败' })
      }
    } catch (e) {
      setPriorityMessage({ success: false, text: `请求失败: ${e}` })
    } finally {
      setPrioritySaving(false)
    }
  }, [fetchActiveModel, fetchModels, fetchRouting, priorityDrafts, providers])

  const reorderProviders = useCallback((sourceId: string, targetId: string) => {
    if (!sourceId || !targetId || sourceId === targetId) return

    setProviders((prev) => {
      const sourceIndex = prev.findIndex((item) => item.id === sourceId)
      const targetIndex = prev.findIndex((item) => item.id === targetId)
      if (sourceIndex < 0 || targetIndex < 0) return prev

      const next = [...prev]
      const [moved] = next.splice(sourceIndex, 1)
      next.splice(targetIndex, 0, moved)

      setPriorityDrafts(
        next.reduce<Record<string, number>>((acc, item, index) => {
          acc[item.id] = index
          return acc
        }, {}),
      )
      return next
    })
  }, [])

  if (!open) return null

  const sourceLabel = (s: string) => {
    if (s === 'db') return '用户配置'
    if (s === 'env') return '环境变量'
    return '未配置'
  }

  const configuredProviders = providers.filter((p) => p.configured)
  const providerOptions = providers.map((item) => ({ id: item.id, name: item.name }))
  const defaultProviderInfo = providers.find((p) => p.id === defaultProvider) || null
  const routingPurposes = purposes.filter((purpose) => purpose.id !== 'chat')
  const purposeOverrideCount = routingPurposes.filter((purpose) =>
    Boolean(purposeRoutes[purpose.id]?.provider_id),
  ).length
  const providerQueryText = providerQuery.trim().toLowerCase()
  const visibleProviders = providers.filter((p) => {
    if (providerFilter === 'configured' && !p.configured) return false
    if (providerFilter === 'unconfigured' && p.configured) return false
    if (!providerQueryText) return true
    return (
      p.name.toLowerCase().includes(providerQueryText) ||
      p.id.toLowerCase().includes(providerQueryText) ||
      p.current_model.toLowerCase().includes(providerQueryText)
    )
  })
  const hasPriorityChanges = providers.some(
    (item) => (priorityDrafts[item.id] ?? item.priority) !== item.priority,
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[86vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-blue-600" />
            <div>
              <h2 className="text-lg font-semibold text-gray-800">模型配置</h2>
              <p className="text-xs text-gray-500 mt-0.5">按“全局默认 → 用途路由 → 提供商细节”配置更高效</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                fetchModels()
                fetchRouting()
              }}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
              title="刷新"
            >
              <RefreshCw size={16} />
            </button>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="px-6 pt-4 pb-3 border-b bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex items-center gap-1 rounded-xl border border-gray-200 bg-gray-50 p-1">
              <button
                onClick={() => setActiveTab('overview')}
                className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                  activeTab === 'overview'
                    ? 'bg-white text-blue-700 border border-blue-200 shadow-sm'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
              >
                总览与路由
              </button>
              <button
                onClick={() => setActiveTab('providers')}
                className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                  activeTab === 'providers'
                    ? 'bg-white text-blue-700 border border-blue-200 shadow-sm'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
              >
                提供商配置
              </button>
            </div>
            <div className="text-[11px] text-gray-500">
              先定路由，再维护提供商细节，减少切换成本
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <Loader2 size={20} className="animate-spin mr-2" />
              加载中...
            </div>
          ) : providers.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              无法获取模型列表，请检查服务是否正常运行
            </div>
          ) : activeTab === 'overview' ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                  <div className="text-xs text-gray-500">已配置提供商</div>
                  <div className="text-2xl font-semibold text-gray-800 mt-1">
                    {configuredProviders.length}
                    <span className="text-sm font-normal text-gray-400 ml-1">/ {providers.length}</span>
                  </div>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                  <div className="text-xs text-gray-500">当前全局默认</div>
                  <div className="text-base font-semibold text-gray-800 mt-1 truncate">
                    {defaultProviderInfo?.name || '自动（按优先级）'}
                  </div>
                  <div className="text-[11px] text-gray-500 mt-1 truncate">
                    {defaultProviderInfo?.current_model || activeModel?.model || '系统自动选择可用模型'}
                  </div>
                </div>
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                  <div className="text-xs text-gray-500">用途路由覆盖</div>
                  <div className="text-2xl font-semibold text-gray-800 mt-1">
                    {purposeOverrideCount}
                    <span className="text-sm font-normal text-gray-400 ml-1">/ {routingPurposes.length}</span>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-blue-100 bg-blue-50/40 p-4">
                <div className="text-sm font-medium text-gray-800">全局默认提供商</div>
                <div className="text-xs text-gray-500 mt-1 mb-3">
                  未被用途路由覆盖的请求会使用此默认提供商；留空时按系统优先级自动选择。
                </div>
                <div className="space-y-2">
                  <button
                    onClick={handleClearDefault}
                    disabled={defaultLoading === 'clear'}
                    className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-xs transition-colors ${
                      !defaultProvider
                        ? 'border-blue-300 bg-blue-100 text-blue-700'
                        : 'border-gray-200 bg-white text-gray-600 hover:border-blue-200'
                    }`}
                  >
                    <span>自动（按优先级）</span>
                    {defaultLoading === 'clear' ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : !defaultProvider ? (
                      <CheckCircle size={12} className="text-blue-600" />
                    ) : null}
                  </button>
                  {configuredProviders.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleSetDefault(p.id)}
                      disabled={defaultLoading === p.id}
                      className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-xs transition-colors ${
                        defaultProvider === p.id
                          ? 'border-blue-300 bg-blue-100 text-blue-700'
                          : 'border-gray-200 bg-white text-gray-700 hover:border-blue-200'
                      }`}
                    >
                      <span className="truncate">{p.name} · {p.current_model || '默认模型'}</span>
                      {defaultLoading === p.id ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : defaultProvider === p.id ? (
                        <CheckCircle size={12} className="text-blue-600" />
                      ) : null}
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <div className="text-sm font-medium text-gray-800">用途模型路由</div>
                <div className="text-xs text-gray-500 mt-1 mb-3">
                  主对话请使用输入框旁模型下拉或上方“全局默认提供商”；此处仅配置非主对话用途。
                </div>
                <div className="space-y-2">
                  {routingPurposes.map((purpose) => {
                    const route = purposeRoutes[purpose.id] || {
                      provider_id: null,
                      model: null,
                      base_url: null,
                    }
                    const selectedProvider = route.provider_id || ''
                    const selectedModel = route.model || ''
                    const providerModels =
                      providers.find((item) => item.id === selectedProvider)?.available_models || []
                    const active = activeByPurpose[purpose.id]
                    return (
                      <div key={purpose.id} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                          <div className="md:col-span-2">
                            <div className="text-xs font-medium text-gray-700">{purpose.label}</div>
                            <div className="text-[10px] text-gray-400 mt-1">ID: {purpose.id}</div>
                          </div>
                          <div className="md:col-span-3">
                            <label className="text-[10px] text-gray-500 mb-1 block">提供商</label>
                            <ProviderCombobox
                              value={selectedProvider}
                              onChange={(providerId) =>
                                handlePurposeFieldChange(purpose.id, {
                                  provider_id: providerId || null,
                                  model: null,
                                  base_url: null,
                                })
                              }
                              options={providerOptions}
                              disabled={!!purposeSaving[purpose.id]}
                              placeholder="搜索或选择提供商..."
                            />
                          </div>
                          <div className="md:col-span-4">
                            <label className="text-[10px] text-gray-500 mb-1 block">模型</label>
                            {selectedProvider ? (
                              <ModelCombobox
                                value={selectedModel}
                                onChange={(val) =>
                                  handlePurposeFieldChange(purpose.id, { model: val || null })
                                }
                                staticModels={providerModels}
                                providerId={selectedProvider}
                                size="sm"
                              />
                            ) : (
                              <input
                                value=""
                                readOnly
                                placeholder="先选择提供商"
                                className="w-full h-8 px-2 text-xs border rounded-lg bg-white text-gray-400"
                              />
                            )}
                          </div>
                          <div className="md:col-span-2 text-[11px] text-gray-500">
                            <div className="text-[10px] text-gray-400 mb-1">当前生效</div>
                            <div className="truncate">{active?.provider_name || '未配置'}</div>
                            {active?.model && <div className="truncate text-gray-400 mt-0.5">{active.model}</div>}
                          </div>
                          <div className="md:col-span-1 flex md:justify-end items-end">
                            <button
                              type="button"
                              onClick={() => handleSavePurposeRoute(purpose.id)}
                              disabled={!!purposeSaving[purpose.id]}
                              className="w-full md:w-auto px-3 py-1.5 rounded border text-[11px] hover:bg-blue-50 disabled:opacity-50"
                            >
                              {purposeSaving[purpose.id] ? (
                                <span className="inline-flex items-center gap-1">
                                  <Loader2 size={11} className="animate-spin" />
                                  保存中
                                </span>
                              ) : (
                                '保存'
                              )}
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
                <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
                  <div className="relative md:col-span-3">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                      value={providerQuery}
                      onChange={(e) => setProviderQuery(e.target.value)}
                      placeholder="搜索提供商名称、ID 或模型..."
                      className="w-full pl-8 pr-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                  </div>
                  <select
                    value={providerFilter}
                    onChange={(e) => setProviderFilter(e.target.value as ProviderFilter)}
                    className="h-10 px-3 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-300 md:col-span-1"
                  >
                    <option value="all">全部状态</option>
                    <option value="configured">仅已配置</option>
                    <option value="unconfigured">仅未配置</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleSavePriorities}
                    disabled={prioritySaving || !hasPriorityChanges}
                    className="h-10 px-3 text-sm rounded-lg border bg-white hover:bg-blue-50 hover:border-blue-300 disabled:opacity-50 disabled:cursor-not-allowed md:col-span-1"
                  >
                    {prioritySaving ? (
                      <span className="inline-flex items-center gap-1">
                        <Loader2 size={14} className="animate-spin" />
                        保存中
                      </span>
                    ) : (
                      '保存优先级'
                    )}
                  </button>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 mt-2 text-[11px] text-gray-500">
                  <span>显示 {visibleProviders.length} / {providers.length} 个提供商</span>
                  <span>拖拽列表可调整顺序；自动路由按优先级升序选择（1 为最高）</span>
                </div>
                {priorityMessage && (
                  <div
                    className={`mt-2 text-xs px-3 py-1.5 rounded-lg ${
                      priorityMessage.success
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {priorityMessage.text}
                  </div>
                )}
              </div>

              {visibleProviders.length === 0 ? (
                <div className="text-center py-16 text-sm text-gray-400">没有匹配的提供商</div>
              ) : (
                visibleProviders.map((p) => {
                  const test = testResults[p.id]
                  const save = saveStatus[p.id]
                  const isEditing = editingId === p.id
                  const isExpanded = expandedId === p.id

                  return (
                    <div
                      key={p.id}
                      onDragOver={(e) => {
                        if (!draggingProviderId) return
                        e.preventDefault()
                        if (dragOverProviderId !== p.id) {
                          setDragOverProviderId(p.id)
                        }
                      }}
                      onDrop={(e) => {
                        e.preventDefault()
                        const sourceId = draggingProviderId || e.dataTransfer.getData('text/plain')
                        reorderProviders(sourceId, p.id)
                        setDraggingProviderId(null)
                        setDragOverProviderId(null)
                      }}
                      className={`rounded-xl border p-4 transition-colors ${
                        dragOverProviderId === p.id && draggingProviderId && draggingProviderId !== p.id
                          ? 'ring-2 ring-blue-200 border-blue-300'
                          : ''
                      } ${
                        p.configured
                          ? 'border-emerald-200 bg-emerald-50/40'
                          : 'border-gray-200 bg-gray-50/60'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div
                          className="flex items-center gap-3 cursor-pointer flex-1 min-w-0"
                          onClick={() => setExpandedId(isExpanded ? null : p.id)}
                        >
                          {p.configured ? (
                            <CheckCircle size={18} className="text-emerald-500 flex-shrink-0" />
                          ) : (
                            <XCircle size={18} className="text-gray-300 flex-shrink-0" />
                          )}
                          <div className="min-w-0">
                            <div className="font-medium text-gray-800 truncate">{p.name}</div>
                            <div className="text-xs text-gray-500 mt-0.5 truncate">
                              {p.current_model || '未设置模型'}
                              {p.api_key_hint && <span className="ml-2">Key: {p.api_key_hint}</span>}
                            </div>
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className="px-1.5 py-0.5 rounded bg-white/80 border text-[10px] text-gray-500">
                                {sourceLabel(p.config_source)}
                              </span>
                              <span className="px-1.5 py-0.5 rounded bg-white/80 border text-[10px] text-gray-500">
                                优先级 #{(priorityDrafts[p.id] ?? p.priority) + 1}
                              </span>
                              {defaultProvider === p.id && (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-50 border border-amber-200 text-[10px] text-amber-700">
                                  <Star size={10} className="fill-amber-500 text-amber-500" />
                                  默认
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.effectAllowed = 'move'
                              e.dataTransfer.setData('text/plain', p.id)
                              setDraggingProviderId(p.id)
                              setDragOverProviderId(p.id)
                            }}
                            onDragEnd={() => {
                              setDraggingProviderId(null)
                              setDragOverProviderId(null)
                            }}
                            className="p-1 rounded hover:bg-gray-100 text-gray-400 cursor-grab active:cursor-grabbing"
                            title="拖拽调整优先级"
                          >
                            <GripVertical size={14} />
                          </button>
                          {isExpanded ? (
                            <ChevronUp size={14} className="text-gray-400 flex-shrink-0" />
                          ) : (
                            <ChevronDown size={14} className="text-gray-400 flex-shrink-0" />
                          )}
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="mt-3 pt-3 border-t border-gray-200 space-y-3">
                          {isEditing ? (
                            <div className="space-y-2">
                              <input
                                type="text"
                                tabIndex={-1}
                                autoComplete="username"
                                className="hidden"
                                value=""
                                readOnly
                                aria-hidden="true"
                              />
                              <input
                                type="password"
                                tabIndex={-1}
                                autoComplete="new-password"
                                className="hidden"
                                value=""
                                readOnly
                                aria-hidden="true"
                              />
                              {p.id !== 'ollama' && (
                                <div>
                                  <label className="text-xs text-gray-500 mb-1 block">API Key</label>
                                  <input
                                    type="password"
                                    name={`${p.id}-api-key`}
                                    autoComplete="new-password"
                                    value={editForm.api_key}
                                    onChange={(e) =>
                                      setEditForm({ ...editForm, api_key: e.target.value })
                                    }
                                    placeholder={
                                      p.api_key_hint
                                        ? `当前: ${p.api_key_hint}（留空保持不变）`
                                        : '输入 API Key'
                                    }
                                    className="w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
                                  />
                                </div>
                              )}
                              <div>
                                <label className="text-xs text-gray-500 mb-1 block">模型名称</label>
                                <ModelCombobox
                                  value={editForm.model}
                                  onChange={(val) => setEditForm({ ...editForm, model: val })}
                                  staticModels={p.available_models}
                                  providerId={p.id}
                                />
                              </div>
                              <div>
                                <label className="text-xs text-gray-500 mb-1 block">Base URL（可选）</label>
                                <input
                                  type="text"
                                  name={`${p.id}-base-url`}
                                  autoComplete="off"
                                  value={editForm.base_url}
                                  onChange={(e) =>
                                    setEditForm({ ...editForm, base_url: e.target.value })
                                  }
                                  placeholder="留空使用默认端点"
                                  className="w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
                                />
                              </div>
                              <div className="flex items-center gap-2 pt-1">
                                <button
                                  onClick={() => handleSave(p.id)}
                                  disabled={save?.loading}
                                  className="flex items-center gap-1 px-4 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                                >
                                  {save?.loading ? (
                                    <Loader2 size={12} className="animate-spin" />
                                  ) : (
                                    <Save size={12} />
                                  )}
                                  保存
                                </button>
                                <button
                                  onClick={cancelEdit}
                                  className="px-4 py-1.5 text-xs rounded-lg border hover:bg-gray-100 transition-colors"
                                >
                                  取消
                                </button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="grid grid-cols-1 md:grid-cols-4 gap-2 text-xs">
                                <div className="rounded-lg border border-gray-200 bg-white p-2">
                                  <div className="text-gray-400">当前模型</div>
                                  <div className="text-gray-700 mt-1 break-all">
                                    {p.current_model || '未设置'}
                                  </div>
                                </div>
                                <div className="rounded-lg border border-gray-200 bg-white p-2">
                                  <div className="text-gray-400">Base URL</div>
                                  <div className="text-gray-700 mt-1 break-all">{p.base_url || '默认端点'}</div>
                                </div>
                                <div className="rounded-lg border border-gray-200 bg-white p-2">
                                  <div className="text-gray-400">可选模型</div>
                                  <div className="text-gray-700 mt-1">{p.available_models.length} 个</div>
                                </div>
                                <div className="rounded-lg border border-gray-200 bg-white p-2">
                                  <div className="text-gray-400">优先级（1 最高）</div>
                                  <input
                                    type="number"
                                    min={1}
                                    value={(priorityDrafts[p.id] ?? p.priority) + 1}
                                    onClick={(e) => e.stopPropagation()}
                                    onChange={(e) => {
                                      const parsed = Number.parseInt(e.target.value, 10)
                                      const nextPriority = Number.isFinite(parsed) && parsed > 0 ? parsed - 1 : 0
                                      setPriorityDrafts((prev) => ({ ...prev, [p.id]: nextPriority }))
                                    }}
                                    className="mt-1 w-full h-8 px-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
                                  />
                                </div>
                              </div>
                              <div className="flex flex-wrap items-center gap-2">
                                <button
                                  onClick={() => startEdit(p)}
                                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border hover:bg-blue-50 hover:border-blue-300 transition-colors"
                                >
                                  <Edit3 size={12} />
                                  编辑配置
                                </button>
                                <button
                                  onClick={() => handleTest(p.id)}
                                  disabled={!p.configured || test?.loading}
                                  className="px-3 py-1.5 text-xs rounded-lg border disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-50 hover:border-blue-300 transition-colors"
                                >
                                  {test?.loading ? (
                                    <span className="inline-flex items-center gap-1">
                                      <Loader2 size={12} className="animate-spin" />
                                      测试中
                                    </span>
                                  ) : (
                                    '测试连接'
                                  )}
                                </button>
                                {p.configured && defaultProvider !== p.id && (
                                  <button
                                    onClick={() => handleSetDefault(p.id)}
                                    disabled={defaultLoading === p.id}
                                    className="px-3 py-1.5 text-xs rounded-lg border hover:bg-amber-50 hover:border-amber-300 text-gray-600"
                                  >
                                    {defaultLoading === p.id ? (
                                      <span className="inline-flex items-center gap-1">
                                        <Loader2 size={12} className="animate-spin" />
                                        设置中
                                      </span>
                                    ) : (
                                      '设为默认'
                                    )}
                                  </button>
                                )}
                                {defaultProvider === p.id && (
                                  <button
                                    onClick={handleClearDefault}
                                    disabled={defaultLoading === 'clear'}
                                    className="px-3 py-1.5 text-xs rounded-lg border hover:bg-gray-100 text-gray-500"
                                  >
                                    {defaultLoading === 'clear' ? (
                                      <span className="inline-flex items-center gap-1">
                                        <Loader2 size={12} className="animate-spin" />
                                        清除中
                                      </span>
                                    ) : (
                                      '清除默认'
                                    )}
                                  </button>
                                )}
                              </div>
                            </>
                          )}

                          {save && !save.loading && (
                            <div
                              className={`text-xs px-3 py-1.5 rounded-lg ${
                                save.success
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-red-100 text-red-700'
                              }`}
                            >
                              {save.message}
                            </div>
                          )}

                          {test && !test.loading && (
                            <div
                              className={`text-xs px-3 py-1.5 rounded-lg ${
                                test.success
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-red-100 text-red-700'
                              }`}
                            >
                              {test.message}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })
              )}
            </>
          )}
        </div>

        {/* 底部提示 */}
        <div className="px-6 py-3 border-t text-xs text-gray-400 text-center">
          先在“总览与路由”完成策略配置，再到“提供商配置”维护密钥与端点，可显著减少误操作。
        </div>
      </div>
    </div>
  )
}
