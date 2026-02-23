/**
 * 路由策略 Tab —— 配置全局默认提供商和按用途指定专用模型。
 * 全局默认：即时生效，无独立保存按钮。
 * 用途路由：每行独立保存。用途名称用中文展示，不显示原始 ID。
 */
import { useEffect, useState, useCallback } from 'react'
import { Loader2, CheckCircle } from 'lucide-react'
import { useStore } from '../../store'
import ModelCombobox from './ModelCombobox'
import ProviderCombobox from './ProviderCombobox'
import type { ModelPurpose, ActivePurposeModel, PurposeRoute, ProviderOption } from './types'

// 用途 ID 到中文名称的映射
const PURPOSE_LABELS: Record<string, string> = {
  title_generation: '标题生成',
  image_analysis: '图片识别',
  chat: '主对话',
  reasoning: '推理分析',
  embedding: '向量嵌入',
  interpretation: '结果解读',
}

function getPurposeLabel(id: string): string {
  return PURPOSE_LABELS[id] || id
}

interface RoutingTabProps {
  onRoutingChanged: () => void
}

export default function RoutingTab({ onRoutingChanged }: RoutingTabProps) {
  const modelProviders = useStore((s) => s.modelProviders)
  const activeModel = useStore((s) => s.activeModel)
  const setPreferredProvider = useStore((s) => s.setPreferredProvider)
  const fetchActiveModel = useStore((s) => s.fetchActiveModel)

  const [purposes, setPurposes] = useState<ModelPurpose[]>([])
  const [purposeRoutes, setPurposeRoutes] = useState<Record<string, PurposeRoute>>({})
  const [activeByPurpose, setActiveByPurpose] = useState<Record<string, ActivePurposeModel>>({})
  const [purposeSaving, setPurposeSaving] = useState<Record<string, boolean>>({})
  const [defaultLoading, setDefaultLoading] = useState(false)

  // 当前全局首选：直接从 activeModel 中读取
  const preferredProvider = activeModel?.preferred_provider ?? null

  const configuredProviders = modelProviders.filter((p) => p.configured)
  const providerOptions: ProviderOption[] = configuredProviders.map((p) => ({
    id: p.id,
    name: p.name,
  }))

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
      setPurposeRoutes(payload.purpose_routes || {})
      setActiveByPurpose(payload.active_by_purpose || {})
      setPurposes(Array.isArray(payload.purposes) ? payload.purposes : [])
    } catch (e) {
      console.error('获取用途模型路由失败:', e)
    }
  }, [])

  useEffect(() => {
    void fetchRouting()
  }, [fetchRouting])

  const handleSetDefault = useCallback(async (providerId: string) => {
    setDefaultLoading(true)
    try {
      await setPreferredProvider(providerId)
      await fetchRouting()
      onRoutingChanged()
    } finally {
      setDefaultLoading(false)
    }
  }, [fetchRouting, onRoutingChanged, setPreferredProvider])

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
      onRoutingChanged()
    } catch (e) {
      console.error(`保存用途模型路由失败(${purposeId}):`, e)
    } finally {
      setPurposeSaving((prev) => ({ ...prev, [purposeId]: false }))
    }
  }, [fetchActiveModel, fetchRouting, onRoutingChanged, purposeRoutes])

  // 过滤掉 chat 用途（主对话由 ModelSelector 或全局默认控制，不在这里配置）
  const routingPurposes = purposes.filter((p) => p.id !== 'chat')

  const defaultProviderInfo = modelProviders.find((p) => p.id === preferredProvider) || null

  return (
    <div className="space-y-5">
      {/* 全局默认提供商 */}
      <div className="rounded-xl border border-blue-100 bg-blue-50/40 p-4">
        <div className="text-sm font-medium text-gray-800">全局默认提供商</div>
        <div className="text-xs text-gray-500 mt-1 mb-3">
          未被专用路由覆盖的请求使用此提供商。留空时按优先级自动选择。
        </div>
        <div className="space-y-2">
          {/* 自动选项 */}
          <button
            onClick={() => handleSetDefault('')}
            disabled={defaultLoading}
            className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-xs transition-colors ${
              !preferredProvider
                ? 'border-blue-300 bg-blue-100 text-blue-700'
                : 'border-gray-200 bg-white text-gray-600 hover:border-blue-200'
            }`}
          >
            <span>自动（按优先级）</span>
            {defaultLoading && !preferredProvider ? (
              <Loader2 size={12} className="animate-spin" />
            ) : !preferredProvider ? (
              <CheckCircle size={12} className="text-blue-600" />
            ) : null}
          </button>

          {/* 已配置的供应商列表 */}
          {configuredProviders.map((p) => (
            <button
              key={p.id}
              onClick={() => handleSetDefault(p.id)}
              disabled={defaultLoading}
              className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-xs transition-colors ${
                preferredProvider === p.id
                  ? 'border-blue-300 bg-blue-100 text-blue-700'
                  : 'border-gray-200 bg-white text-gray-700 hover:border-blue-200'
              }`}
            >
              <span className="truncate">{p.name} · {p.current_model || '默认模型'}</span>
              {defaultLoading && preferredProvider === p.id ? (
                <Loader2 size={12} className="animate-spin" />
              ) : preferredProvider === p.id ? (
                <CheckCircle size={12} className="text-blue-600" />
              ) : null}
            </button>
          ))}

          {configuredProviders.length === 0 && (
            <div className="text-xs text-gray-400 text-center py-3">
              暂无已配置的提供商，请先在「凭证管理」Tab 填写 API Key。
            </div>
          )}
        </div>
      </div>

      {/* 用途专用模型路由 */}
      {routingPurposes.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-sm font-medium text-gray-800">按用途指定专用模型</div>
          <div className="text-xs text-gray-500 mt-1 mb-3">
            可选。为特定系统功能单独指定模型，不配置时沿用全局默认。
          </div>

          {defaultProviderInfo && (
            <div className="mb-3 text-[11px] text-blue-600 bg-blue-50 rounded-lg px-3 py-2">
              当前全局默认：{defaultProviderInfo.name} · {defaultProviderInfo.current_model || '默认模型'}
            </div>
          )}

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
                modelProviders.find((item) => item.id === selectedProvider)?.available_models || []
              const active = activeByPurpose[purpose.id]

              return (
                <div key={purpose.id} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                    <div className="md:col-span-2">
                      <div className="text-xs font-medium text-gray-700">
                        {getPurposeLabel(purpose.id)}
                      </div>
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
                      <div className="truncate">{active?.provider_name || '沿用全局'}</div>
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
      )}
    </div>
  )
}
