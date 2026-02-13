/**
 * 模型配置面板 —— 查看、编辑、保存模型提供商配置，测试连接。
 * 模型选择支持搜索过滤和远程模型列表获取。
 */
import { useEffect, useState, useCallback, useRef } from 'react'
import {
  X, CheckCircle, XCircle, Loader2, Zap, RefreshCw,
  Edit3, Save, ChevronDown, ChevronUp, Search, Star,
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
}: {
  value: string
  onChange: (val: string) => void
  staticModels: string[]
  providerId: string
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

  return (
    <div className="relative" ref={wrapperRef}>
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          name={`${providerId}-model-search`}
          autoComplete="off"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          onFocus={() => setDropdownOpen(true)}
          placeholder="搜索或输入模型名称..."
          className="w-full pl-8 pr-8 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <button
          type="button"
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        >
          <ChevronDown size={14} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
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

export default function ModelConfigPanel({ open, onClose }: Props) {
  const activeModel = useStore((s) => s.activeModel)
  const fetchActiveModel = useStore((s) => s.fetchActiveModel)
  const setPreferredProvider = useStore((s) => s.setPreferredProvider)

  // 从 activeModel 中获取当前全局首选
  const defaultProvider = activeModel?.preferred_provider || null

  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [loading, setLoading] = useState(false)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ api_key: '', model: '', base_url: '' })
  const [saveStatus, setSaveStatus] = useState<Record<string, SaveStatus>>({})
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [defaultLoading, setDefaultLoading] = useState<string | null>(null)

  const fetchModels = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/models')
      const data = await resp.json()
      if (data.success && Array.isArray(data.data)) {
        setProviders(data.data)
      }
    } catch (e) {
      console.error('获取模型列表失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      fetchModels()
      setTestResults({})
      setEditingId(null)
      setSaveStatus({})
    }
  }, [open, fetchModels])

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
  }, [editForm, fetchActiveModel, fetchModels])

  const handleSetDefault = useCallback(async (providerId: string) => {
    setDefaultLoading(providerId)
    try {
      await setPreferredProvider(providerId)
    } finally {
      setDefaultLoading(null)
    }
  }, [setPreferredProvider])

  const handleClearDefault = useCallback(async () => {
    setDefaultLoading('clear')
    try {
      await setPreferredProvider('')
    } finally {
      setDefaultLoading(null)
    }
  }, [setPreferredProvider])

  if (!open) return null

  const sourceLabel = (s: string) => {
    if (s === 'db') return '用户配置'
    if (s === 'env') return '环境变量'
    return '未配置'
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-800">模型配置</h2>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={fetchModels} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500" title="刷新">
              <RefreshCw size={16} />
            </button>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* 模型列表 */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-400">
              <Loader2 size={20} className="animate-spin mr-2" />
              加载中...
            </div>
          ) : providers.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              无法获取模型列表，请检查服务是否正常运行
            </div>
          ) : (
            providers.map((p) => {
              const test = testResults[p.id]
              const save = saveStatus[p.id]
              const isEditing = editingId === p.id
              const isExpanded = expandedId === p.id

              return (
                <div
                  key={p.id}
                  className={`rounded-xl border p-4 transition-colors ${
                    p.configured ? 'border-emerald-200 bg-emerald-50/50' : 'border-gray-200 bg-gray-50/50'
                  }`}
                >
                  {/* 头部行 */}
                  <div className="flex items-center justify-between">
                    <div
                      className="flex items-center gap-3 cursor-pointer flex-1"
                      onClick={() => setExpandedId(isExpanded ? null : p.id)}
                    >
                      {p.configured ? (
                        <CheckCircle size={18} className="text-emerald-500" />
                      ) : (
                        <XCircle size={18} className="text-gray-300" />
                      )}
                      <div>
                        <div className="font-medium text-gray-800">{p.name}</div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          模型: {p.current_model || '未设置'}
                          {p.api_key_hint && <span className="ml-2">Key: {p.api_key_hint}</span>}
                          <span className="ml-2 text-gray-400">({sourceLabel(p.config_source)})</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">#{p.priority + 1}</span>
                      {isExpanded ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
                    </div>
                  </div>


                  {/* 展开区域 */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-gray-200 space-y-3">
                      {isEditing ? (
                        /* 编辑模式 */
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
                                onChange={(e) => setEditForm({ ...editForm, api_key: e.target.value })}
                                placeholder={p.api_key_hint ? `当前: ${p.api_key_hint}（留空保持不变）` : '输入 API Key'}
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
                              onChange={(e) => setEditForm({ ...editForm, base_url: e.target.value })}
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
                              {save?.loading ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
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
                        /* 查看模式 */
                        <div className="flex items-center gap-2">
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
                            {test?.loading ? <Loader2 size={12} className="animate-spin" /> : '测试连接'}
                          </button>
                        </div>
                      )}

                      {/* 保存状态 */}
                      {save && !save.loading && (
                        <div className={`text-xs px-3 py-1.5 rounded-lg ${save.success ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                          {save.message}
                        </div>
                      )}

                      {/* 测试结果 */}
                      {test && !test.loading && (
                        <div className={`text-xs px-3 py-1.5 rounded-lg ${test.success ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                          {test.message}
                        </div>
                      )}

                      {/* 默认提供商设置 */}
                      {!isEditing && p.configured && (
                        <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
                          {defaultProvider === p.id ? (
                            <div className="flex items-center gap-2 text-xs text-yellow-600">
                              <Star size={12} className="fill-yellow-500 text-yellow-500" />
                              <span>当前默认提供商</span>
                              <button
                                onClick={handleClearDefault}
                                disabled={defaultLoading === 'clear'}
                                className="ml-2 text-gray-400 hover:text-gray-600 underline"
                              >
                                {defaultLoading === 'clear' ? (
                                  <Loader2 size={10} className="animate-spin" />
                                ) : (
                                  '清除'
                                )}
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => handleSetDefault(p.id)}
                              disabled={defaultLoading === p.id}
                              className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600 transition-colors"
                            >
                              {defaultLoading === p.id ? (
                                <Loader2 size={12} className="animate-spin" />
                              ) : (
                                <Star size={12} />
                              )}
                              设为默认提供商
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* 底部提示 */}
        <div className="px-6 py-3 border-t text-xs text-gray-400 text-center">
          点击展开配置卡片，编辑并保存 API Key。模型选择支持搜索过滤和自定义输入。
        </div>
      </div>
    </div>
  )
}
