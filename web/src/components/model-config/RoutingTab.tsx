/**
 * 路由策略 Tab —— 为不同功能用途指定专用供应商和模型。
 * 所有用途（含 chat）统一在此配置，每行独立保存。
 * 用途名称用中文展示，不显示原始 ID。
 */
import { useEffect, useState, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { useStore } from "../../store";
import ModelCombobox from "./ModelCombobox";
import ProviderCombobox from "./ProviderCombobox";
import type {
  ModelPurpose,
  ActivePurposeModel,
  PurposeRoute,
  ProviderOption,
} from "./types";

// 用途 ID 到中文名称的映射
const PURPOSE_LABELS: Record<string, string> = {
  title_generation: "标题生成",
  image_analysis: "图片识别",
  chat: "主对话",
  reasoning: "推理分析",
  embedding: "向量嵌入",
  interpretation: "结果解读",
};

function getPurposeLabel(id: string): string {
  return PURPOSE_LABELS[id] || id;
}

interface RoutingTabProps {
  onRoutingChanged: () => void;
}

export default function RoutingTab({ onRoutingChanged }: RoutingTabProps) {
  const modelProviders = useStore((s) => s.modelProviders);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);

  const [purposes, setPurposes] = useState<ModelPurpose[]>([]);
  const [purposeRoutes, setPurposeRoutes] = useState<
    Record<string, PurposeRoute>
  >({});
  const [activeByPurpose, setActiveByPurpose] = useState<
    Record<string, ActivePurposeModel>
  >({});
  const [purposeSaving, setPurposeSaving] = useState<Record<string, boolean>>(
    {},
  );

  const configuredProviders = modelProviders.filter((p) => p.configured);
  const providerOptions: ProviderOption[] = configuredProviders.map((p) => ({
    id: p.id,
    name: p.name,
  }));

  const fetchRouting = useCallback(async () => {
    try {
      const resp = await fetch("/api/models/routing");
      const data = await resp.json();
      if (!data.success || !data.data) return;
      const payload = data.data as {
        preferred_provider?: string | null;
        purpose_routes?: Record<string, PurposeRoute>;
        active_by_purpose?: Record<string, ActivePurposeModel>;
        purposes?: ModelPurpose[];
      };
      setPurposeRoutes(payload.purpose_routes || {});
      setActiveByPurpose(payload.active_by_purpose || {});
      setPurposes(Array.isArray(payload.purposes) ? payload.purposes : []);
    } catch (e) {
      console.error("获取用途模型路由失败:", e);
    }
  }, []);

  useEffect(() => {
    void fetchRouting();
  }, [fetchRouting]);

  const handlePurposeFieldChange = useCallback(
    (purposeId: string, patch: Partial<PurposeRoute>) => {
      setPurposeRoutes((prev) => {
        const current = prev[purposeId] || {
          provider_id: null,
          model: null,
          base_url: null,
        };
        const next: PurposeRoute = { ...current, ...patch };
        if (!next.provider_id) {
          next.model = null;
          next.base_url = null;
        }
        return { ...prev, [purposeId]: next };
      });
    },
    [],
  );

  const handleSavePurposeRoute = useCallback(
    async (purposeId: string) => {
      const route = purposeRoutes[purposeId] || {
        provider_id: null,
        model: null,
        base_url: null,
      };
      setPurposeSaving((prev) => ({ ...prev, [purposeId]: true }));
      try {
        const requestBody: {
          purpose_routes: Record<string, PurposeRoute>;
          preferred_provider?: string | null;
        } = {
          purpose_routes: {
            [purposeId]: {
              provider_id: route.provider_id,
              model: route.model,
              base_url: route.base_url,
            },
          },
        };
        if (purposeId === "chat") {
          requestBody.preferred_provider = route.provider_id || null;
        }

        const resp = await fetch("/api/models/routing", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
        });
        const data = await resp.json();
        if (!data.success) {
          console.error(`保存用途模型路由失败(${purposeId}):`, data.error);
        }
        await fetchRouting();
        await fetchActiveModel();
        window.dispatchEvent(new Event("nini:model-config-updated"));
        onRoutingChanged();
      } catch (e) {
        console.error(`保存用途模型路由失败(${purposeId}):`, e);
      } finally {
        setPurposeSaving((prev) => ({ ...prev, [purposeId]: false }));
      }
    },
    [fetchActiveModel, fetchRouting, onRoutingChanged, purposeRoutes],
  );

  // 所有用途统一展示（含 chat）
  const routingPurposes = purposes;

  return (
    <div className="space-y-5">
      {routingPurposes.length > 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-sm font-medium text-gray-800">
            模型路由配置
          </div>
          <div className="text-xs text-gray-500 mt-1 mb-3">
            为不同功能指定供应商和模型，未配置的用途将按优先级自动选择。
          </div>

          <div className="space-y-2">
            {routingPurposes.map((purpose) => {
              const route = purposeRoutes[purpose.id] || {
                provider_id: null,
                model: null,
                base_url: null,
              };
              const selectedProvider = route.provider_id || "";
              const selectedModel = route.model || "";
              const providerModels =
                modelProviders.find((item) => item.id === selectedProvider)
                  ?.available_models || [];
              const active = activeByPurpose[purpose.id];

              return (
                <div
                  key={purpose.id}
                  className="rounded-lg border border-gray-100 bg-gray-50 p-3"
                >
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                    <div className="md:col-span-2">
                      <div className="text-xs font-medium text-gray-700">
                        {getPurposeLabel(purpose.id)}
                      </div>
                    </div>
                    <div className="md:col-span-3">
                      <label className="text-[10px] text-gray-500 mb-1 block">
                        提供商
                      </label>
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
                      <label className="text-[10px] text-gray-500 mb-1 block">
                        模型
                      </label>
                      {selectedProvider ? (
                        <ModelCombobox
                          value={selectedModel}
                          onChange={(val) =>
                            handlePurposeFieldChange(purpose.id, {
                              model: val || null,
                            })
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
                      <div className="text-[10px] text-gray-400 mb-1">
                        当前生效
                      </div>
                      <div className="truncate">
                        {active?.provider_name || "按优先级自动"}
                      </div>
                      {active?.model && (
                        <div className="truncate text-gray-400 mt-0.5">
                          {active.model}
                        </div>
                      )}
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
                          "保存"
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="text-center py-16 text-sm text-gray-400">
          加载用途列表中...
        </div>
      )}
    </div>
  );
}
