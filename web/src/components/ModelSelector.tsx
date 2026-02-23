/**
 * 模型选择器 —— 两级级联：供应商 → 模型。
 * 点选供应商展开其模型列表，点选模型后通过 setChatRoute 持久化。
 * 数据从 store.modelProviders 读取，与 ModelConfigPanel 共享同一数据源。
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { useStore } from "../store";
import { ChevronDown, ChevronRight, Check, Bot, Loader2 } from "lucide-react";

interface ProviderModels {
  loading: boolean;
  models: string[];
}

interface ModelSelectorProps {
  compact?: boolean;
  menuDirection?: "up" | "down";
  align?: "left" | "right";
}

export default function ModelSelector({
  compact = false,
  menuDirection = "down",
  align = "right",
}: ModelSelectorProps) {
  const activeModel = useStore((s) => s.activeModel);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);
  const setChatRoute = useStore((s) => s.setChatRoute);
  const modelProviders = useStore((s) => s.modelProviders);
  const fetchModelProviders = useStore((s) => s.fetchModelProviders);

  const [open, setOpen] = useState(false);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [providerModels, setProviderModels] = useState<
    Record<string, ProviderModels>
  >({});
  const providerModelsRef = useRef(providerModels);
  providerModelsRef.current = providerModels;
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 初始化：获取当前活跃模型
  useEffect(() => {
    void fetchActiveModel();
  }, [fetchActiveModel]);

  // 打开下拉时：若 providers 为空则触发加载
  useEffect(() => {
    if (open && modelProviders.length === 0) {
      void fetchModelProviders();
    }
  }, [open, modelProviders.length, fetchModelProviders]);

  // 点击外部关闭下拉
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setExpandedProvider(null);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  // 展开供应商时动态获取远程模型列表
  const fetchProviderModels = useCallback(
    async (providerId: string) => {
      // 已有远程加载结果的（source 标记为 fetched）跳过
      const cached = providerModelsRef.current[providerId];
      if (cached && !cached.loading) return;

      const provider = modelProviders.find((p) => p.id === providerId);
      const staticModels = provider?.available_models || [];
      setProviderModels((prev) => ({
        ...prev,
        [providerId]: { loading: true, models: staticModels },
      }));

      try {
        const resp = await fetch(`/api/models/${providerId}/available`);
        const data = await resp.json();
        if (
          data.success &&
          data.data?.models &&
          Array.isArray(data.data.models)
        ) {
          setProviderModels((prev) => ({
            ...prev,
            [providerId]: {
              loading: false,
              models: data.data.models as string[],
            },
          }));
        } else {
          setProviderModels((prev) => ({
            ...prev,
            [providerId]: { loading: false, models: staticModels },
          }));
        }
      } catch {
        setProviderModels((prev) => ({
          ...prev,
          [providerId]: { loading: false, models: staticModels },
        }));
      }
    },
    [modelProviders],
  );

  // 提供商配置变化后清空模型缓存，避免显示过期模型列表
  useEffect(() => {
    providerModelsRef.current = {};
    setProviderModels({});
    if (open && expandedProvider) {
      void fetchProviderModels(expandedProvider);
    }
  }, [modelProviders, open, expandedProvider, fetchProviderModels]);

  // 监听全局模型配置更新事件，强制失效缓存
  useEffect(() => {
    const handleModelConfigUpdated = () => {
      providerModelsRef.current = {};
      setProviderModels({});
      if (open && expandedProvider) {
        void fetchProviderModels(expandedProvider);
      }
    };
    window.addEventListener("nini:model-config-updated", handleModelConfigUpdated);
    return () => {
      window.removeEventListener("nini:model-config-updated", handleModelConfigUpdated);
    };
  }, [open, expandedProvider, fetchProviderModels]);

  const handleExpandProvider = useCallback(
    (providerId: string) => {
      if (expandedProvider === providerId) {
        setExpandedProvider(null);
        return;
      }
      setExpandedProvider(providerId);
      void fetchProviderModels(providerId);
    },
    [expandedProvider, fetchProviderModels],
  );

  const handleSelectModel = async (providerId: string, model: string) => {
    await setChatRoute(providerId, model);
    setOpen(false);
    setExpandedProvider(null);
  };

  const handleSelectAuto = async () => {
    await setChatRoute("", null);
    setOpen(false);
    setExpandedProvider(null);
  };

  // 显示文本
  const displayText = activeModel
    ? activeModel.model || activeModel.provider_name || "未知模型"
    : "加载中...";

  const configuredProviders = modelProviders.filter((p) => p.configured);
  const triggerClass = compact
    ? "h-8 px-2.5 text-xs border-gray-200 text-gray-600"
    : "px-2.5 py-1 text-xs border-gray-200 text-gray-600";
  const maxWidthClass = compact ? "max-w-[150px]" : "max-w-[120px]";
  const menuPositionClass =
    menuDirection === "up"
      ? `${align === "right" ? "right-0" : "left-0"} bottom-full mb-1`
      : `${align === "right" ? "right-0" : "left-0"} top-full mt-1`;

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
        <ChevronDown
          size={12}
          className={`text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {/* 下拉菜单 */}
      {open && (
        <div
          className={`absolute ${menuPositionClass} w-80 bg-white rounded-xl shadow-lg border border-gray-200 py-1 z-50 max-h-96 overflow-y-auto`}
        >
          {/* 自动选择（按优先级） */}
          <button
            onClick={handleSelectAuto}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 transition-colors"
          >
            <div className="w-4 flex justify-center">
              {!activeModel?.preferred_provider && (
                <Check size={12} className="text-blue-500" />
              )}
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
              const isActiveProvider = activeModel?.preferred_provider === p.id;
              const isExpanded = expandedProvider === p.id;
              const models = providerModels[p.id];

              return (
                <div key={p.id}>
                  {/* 供应商行 */}
                  <button
                    onClick={() => handleExpandProvider(p.id)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 transition-colors"
                  >
                    <div className="w-4 flex justify-center">
                      {isActiveProvider && (
                        <Check size={12} className="text-blue-500" />
                      )}
                    </div>
                    <div className="flex-1 text-left">
                      <span className="text-gray-800 font-medium">
                        {p.name}
                      </span>
                      <div className="text-gray-400 mt-0.5">
                        {p.current_model || "默认模型"}
                      </div>
                    </div>
                    <ChevronRight
                      size={12}
                      className={`text-gray-400 transition-transform ${isExpanded ? "rotate-90" : ""}`}
                    />
                  </button>

                  {/* 模型子列表 */}
                  {isExpanded && (
                    <div className="bg-gray-50 border-y border-gray-100">
                      {models?.loading ? (
                        <div className="flex items-center gap-2 px-6 py-2 text-xs text-gray-400">
                          <Loader2 size={11} className="animate-spin" />
                          加载模型列表...
                        </div>
                      ) : (models?.models || []).length === 0 ? (
                        <div className="px-6 py-2 text-xs text-gray-400">
                          暂无可用模型
                        </div>
                      ) : (
                        (models?.models || []).map((model) => {
                          const isActiveModel =
                            isActiveProvider && activeModel?.model === model;
                          return (
                            <button
                              key={model}
                              onClick={() => handleSelectModel(p.id, model)}
                              className="w-full flex items-center gap-2 pl-9 pr-3 py-1.5 text-xs hover:bg-blue-50 transition-colors"
                            >
                              <div className="w-4 flex justify-center">
                                {isActiveModel && (
                                  <Check size={10} className="text-blue-500" />
                                )}
                              </div>
                              <span className="text-gray-700 truncate">
                                {model}
                              </span>
                            </button>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
