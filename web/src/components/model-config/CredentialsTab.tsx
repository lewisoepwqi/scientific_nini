/**
 * 凭证管理 Tab —— 仅负责 API Key、模型名称、Base URL 的录入与测试。
 * 不涉及策略配置（"设为默认"功能已移至路由策略 Tab）。
 * 数据从 store.modelProviders 读取，不自行 fetch。
 */
import { useState, useCallback } from 'react'
import {
  CheckCircle, XCircle, Loader2, Edit3, Save, Search,
} from 'lucide-react'
import { useStore } from '../../store'
import ModelCombobox from './ModelCombobox'
import type { EditForm, SaveStatus, TestResult } from './types'

type ProviderFilter = 'all' | 'configured' | 'unconfigured'

function sourceLabel(s: string) {
  if (s === 'db') return '用户配置'
  if (s === 'env') return '环境变量'
  return '未配置'
}

interface CredentialsTabProps {
  onConfigSaved: () => void
}

export default function CredentialsTab({ onConfigSaved }: CredentialsTabProps) {
  const modelProviders = useStore((s) => s.modelProviders)
  const modelProvidersLoading = useStore((s) => s.modelProvidersLoading)
  const fetchActiveModel = useStore((s) => s.fetchActiveModel)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ api_key: '', model: '', base_url: '' })
  const [saveStatus, setSaveStatus] = useState<Record<string, SaveStatus>>({})
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [providerQuery, setProviderQuery] = useState('')
  const [providerFilter, setProviderFilter] = useState<ProviderFilter>('all')

  const startEdit = useCallback((p: { id: string; current_model: string; base_url: string }) => {
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
        await fetchActiveModel()
        window.dispatchEvent(new Event('nini:model-config-updated'))
        onConfigSaved()
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
  }, [editForm, fetchActiveModel, onConfigSaved])

  const handleTest = useCallback(async (providerId: string) => {
    setTestResults((prev) => ({ ...prev, [providerId]: { loading: true } }))
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

  if (modelProvidersLoading && modelProviders.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400">
        <Loader2 size={20} className="animate-spin mr-2" />
        加载中...
      </div>
    )
  }

  const providerQueryText = providerQuery.trim().toLowerCase()
  const visibleProviders = modelProviders.filter((p) => {
    if (providerFilter === 'configured' && !p.configured) return false
    if (providerFilter === 'unconfigured' && p.configured) return false
    if (!providerQueryText) return true
    return (
      p.name.toLowerCase().includes(providerQueryText) ||
      p.id.toLowerCase().includes(providerQueryText) ||
      p.current_model.toLowerCase().includes(providerQueryText)
    )
  })

  return (
    <div className="space-y-4">
      {/* 搜索与过滤 */}
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
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
        </div>
        <div className="text-[11px] text-gray-500 mt-2">
          显示 {visibleProviders.length} / {modelProviders.length} 个提供商
        </div>
      </div>

      {/* 提供商列表 */}
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
              className={`rounded-xl border p-4 transition-colors ${
                p.configured
                  ? 'border-emerald-200 bg-emerald-50/40'
                  : 'border-gray-200 bg-gray-50/60'
              }`}
            >
              <div
                className="flex items-center justify-between cursor-pointer"
                onClick={() => setExpandedId(isExpanded ? null : p.id)}
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
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
                    </div>
                  </div>
                </div>
                <div className="text-gray-400">
                  {isExpanded
                    ? <span className="text-xs">▲</span>
                    : <span className="text-xs">▼</span>
                  }
                </div>
              </div>

              {isExpanded && (
                <div className="mt-3 pt-3 border-t border-gray-200 space-y-3">
                  {isEditing ? (
                    <div className="space-y-2">
                      {/* 防 autocomplete 的隐藏字段 */}
                      <input type="text" tabIndex={-1} autoComplete="username" className="hidden" value="" readOnly aria-hidden="true" />
                      <input type="password" tabIndex={-1} autoComplete="new-password" className="hidden" value="" readOnly aria-hidden="true" />

                      {p.id !== 'ollama' && (
                        <div>
                          <label className="text-xs text-gray-500 mb-1 block">API Key</label>
                          <input
                            type="password"
                            name={`${p.id}-api-key`}
                            autoComplete="new-password"
                            value={editForm.api_key}
                            onChange={(e) => setEditForm({ ...editForm, api_key: e.target.value })}
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
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                        <div className="rounded-lg border border-gray-200 bg-white p-2">
                          <div className="text-gray-400">当前模型</div>
                          <div className="text-gray-700 mt-1 break-all">{p.current_model || '未设置'}</div>
                        </div>
                        <div className="rounded-lg border border-gray-200 bg-white p-2">
                          <div className="text-gray-400">Base URL</div>
                          <div className="text-gray-700 mt-1 break-all">{p.base_url || '默认端点'}</div>
                        </div>
                        <div className="rounded-lg border border-gray-200 bg-white p-2">
                          <div className="text-gray-400">可选模型</div>
                          <div className="text-gray-700 mt-1">{p.available_models.length} 个</div>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => startEdit(p)}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border hover:bg-blue-50 hover:border-blue-300 transition-colors"
                        >
                          <Edit3 size={12} />
                          编辑凭证
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
                      </div>
                    </>
                  )}

                  {save && !save.loading && (
                    <div className={`text-xs px-3 py-1.5 rounded-lg ${save.success ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                      {save.message}
                    </div>
                  )}
                  {test && !test.loading && (
                    <div className={`text-xs px-3 py-1.5 rounded-lg ${test.success ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                      {test.message}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })
      )}
    </div>
  )
}
