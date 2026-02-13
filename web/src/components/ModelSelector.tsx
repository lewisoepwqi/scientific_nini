/**
 * 模型选择器 —— 下拉点选后设为全局首选模型（持久化）。
 */
import { useEffect, useState, useRef, useCallback } from 'react'
import { useStore } from '../store'
import { ChevronDown, Check, Bot } from 'lucide-react'

interface ProviderOption {
  id: string
  name: string
  configured: boolean
  current_model: string
}

interface ModelSelectorProps {
  compact?: boolean
  menuDirection?: 'up' | 'down'
  align?: 'left' | 'right'
}

export default function ModelSelector({
  compact = false,
  menuDirection = 'down',
  align = 'right',
}: ModelSelectorProps) {
  const activeModel = useStore((s) => s.activeModel)
  const fetchActiveModel = useStore((s) => s.fetchActiveModel)
  const setPreferredProvider = useStore((s) => s.setPreferredProvider)

  const [open, setOpen] = useState(false)
  const [providers, setProviders] = useState<ProviderOption[]>([])
  const dropdownRef = useRef<HTMLDivElement>(null)

  // 初始化：获取当前活跃模型
  useEffect(() => {
    fetchActiveModel()
  }, [fetchActiveModel])

  // 获取可用提供商列表
  const fetchProviders = useCallback(async () => {
    try {
      const resp = await fetch('/api/models')
      const data = await resp.json()
      if (data.success && Array.isArray(data.data)) {
        setProviders(
          data.data.map((p: Record<string, unknown>) => ({
            id: p.id as string,
            name: p.name as string,
            configured: p.configured as boolean,
            current_model: p.current_model as string,
          }))
        )
      }
    } catch (e) {
      console.error('获取模型提供商列表失败:', e)
    }
  }, [])

  // 打开下拉时加载提供商列表
  useEffect(() => {
    if (open) fetchProviders()
  }, [open, fetchProviders])

  // 模型配置更新后同步刷新显示与下拉数据
  useEffect(() => {
    const handleModelConfigUpdated = () => {
      void fetchActiveModel()
      if (open) {
        void fetchProviders()
      }
    }
    window.addEventListener('nini:model-config-updated', handleModelConfigUpdated)
    return () => window.removeEventListener('nini:model-config-updated', handleModelConfigUpdated)
  }, [fetchActiveModel, fetchProviders, open])

  // 点击外部关闭下拉
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [open])

  const handleSelect = async (providerId: string) => {
    await setPreferredProvider(providerId)
    setOpen(false)
  }

  // 显示文本
  const displayText = activeModel
    ? activeModel.model || activeModel.provider_name || '未知模型'
    : '加载中...'

  const configuredProviders = providers.filter((p) => p.configured)
  const triggerClass = compact
    ? 'h-8 px-2.5 text-xs border-gray-200 text-gray-600'
    : 'px-2.5 py-1 text-xs border-gray-200 text-gray-600'
  const maxWidthClass = compact ? 'max-w-[150px]' : 'max-w-[120px]'
  const menuPositionClass =
    menuDirection === 'up'
      ? `${align === 'right' ? 'right-0' : 'left-0'} bottom-full mb-1`
      : `${align === 'right' ? 'right-0' : 'left-0'} top-full mt-1`

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 触发按钮 */}
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 rounded-2xl hover:bg-gray-100 transition-colors border ${triggerClass}`}
        title="切换模型"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Bot size={13} className="text-blue-500 flex-shrink-0" />
        <span className={`truncate ${maxWidthClass}`}>{displayText}</span>
        <ChevronDown size={12} className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* 下拉菜单 */}
      {open && (
        <div className={`absolute ${menuPositionClass} w-72 bg-white rounded-xl shadow-lg border border-gray-200 py-1 z-50`}>
          {/* 自动选择（按优先级） */}
          <button
            onClick={() => handleSelect('')}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 transition-colors"
          >
            <div className="w-4 flex justify-center">
              {!activeModel?.preferred_provider && <Check size={12} className="text-blue-500" />}
            </div>
            <div className="flex-1 text-left">
              <div className="text-gray-800 font-medium">自动（按优先级）</div>
              <div className="text-gray-400 mt-0.5">系统自动选择可用模型</div>
            </div>
          </button>

          <div className="border-t border-gray-100 my-1" />

          {configuredProviders.length === 0 ? (
            <div className="px-3 py-3 text-xs text-gray-400 text-center">
              暂无已配置的模型提供商
            </div>
          ) : (
            configuredProviders.map((p) => {
              const isActive = activeModel?.preferred_provider === p.id
              return (
                <button
                  key={p.id}
                  onClick={() => handleSelect(p.id)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 transition-colors"
                >
                  <div className="w-4 flex justify-center">
                    {isActive && <Check size={12} className="text-blue-500" />}
                  </div>
                  <div className="flex-1 text-left">
                    <span className="text-gray-800 font-medium">{p.name}</span>
                    <div className="text-gray-400 mt-0.5">{p.current_model || '默认模型'}</div>
                  </div>
                </button>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
