/**
 * AI 设置面板 —— 面向科研用户的简洁三屏设计。
 * 屏 1：已配置状态（含试用模式）
 * 屏 2：选择服务商（4 张卡片）
 * 屏 3：填写密钥 / 本地 Ollama 配置
 */
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Loader2,
  X,
} from "lucide-react";
import { useStore } from "../store";
import type { ModelProviderInfo } from "../store/types";

// 已知模型的友好名称映射：{ provider_id: { model_id: [显示名, 描述] } }
const MODEL_DISPLAY_NAMES: Record<string, Record<string, [string, string]>> = {
  deepseek: {
    "deepseek-chat": ["DeepSeek V3", "快速、经济"],
    "deepseek-reasoner": ["DeepSeek R1", "深度推理"],
    "deepseek-coder-v2": ["DeepSeek Coder V2", "代码专项"],
  },
  zhipu: {
    "glm-4-plus": ["GLM-4 Plus", "旗舰模型"],
    "glm-4-flash": ["GLM-4 Flash", "快速（含免费额度）"],
    "glm-4-air": ["GLM-4 Air", "轻量高效"],
    "glm-4": ["GLM-4", "标准模型"],
    "glm-z1-flash": ["GLM-Z1 Flash", "快速推理"],
  },
  dashscope: {
    "qwen-max": ["通义千问 Max", "旗舰模型"],
    "qwen-plus": ["通义千问 Plus", "推荐，均衡"],
    "qwen-turbo": ["通义千问 Turbo", "快速、经济"],
    "qwen-long": ["通义千问 Long", "长文档分析"],
  },
};

function getModelDisplayName(
  providerId: string,
  modelId: string
): [string, string] {
  return MODEL_DISPLAY_NAMES[providerId]?.[modelId] ?? [modelId, ""];
}

type Screen = "status" | "select-provider" | "configure";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ModelConfigPanel({ open, onClose }: Props) {
  const modelProviders = useStore((s) => s.modelProviders);
  const fetchModelProviders = useStore((s) => s.fetchModelProviders);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);

  const [screen, setScreen] = useState<Screen>("status");
  const [selectedProvider, setSelectedProvider] =
    useState<ModelProviderInfo | null>(null);

  useEffect(() => {
    if (open) {
      void fetchModelProviders();
      void fetchActiveModel();
      setScreen("status");
    }
  }, [open, fetchModelProviders, fetchActiveModel]);

  const activeProvider = modelProviders.find((p) => p.is_active) ?? null;

  const handleSelectProvider = (provider: ModelProviderInfo) => {
    setSelectedProvider(provider);
    setScreen("configure");
  };

  const handleConfigSaved = useCallback(() => {
    void fetchModelProviders();
    void fetchActiveModel();
    setScreen("status");
    window.dispatchEvent(new Event("nini:model-config-updated"));
  }, [fetchModelProviders, fetchActiveModel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col max-h-[90vh]">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            {screen !== "status" && (
              <button
                onClick={() =>
                  setScreen(
                    screen === "configure" ? "select-provider" : "status"
                  )
                }
                className="p-1 rounded-lg hover:bg-gray-100 text-gray-500 mr-1"
              >
                <ArrowLeft size={16} />
              </button>
            )}
            <Bot size={18} className="text-blue-600" />
            <h2 className="text-base font-semibold text-gray-800">
              {screen === "status" && "AI 设置"}
              {screen === "select-provider" && "选择服务商"}
              {screen === "configure" &&
                `配置 ${selectedProvider?.name ?? ""}`}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
          >
            <X size={18} />
          </button>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto">
          {screen === "status" && (
            <StatusScreen
              activeProvider={activeProvider}
              providers={modelProviders}
              onSwitch={() => setScreen("select-provider")}
            />
          )}
          {screen === "select-provider" && (
            <SelectProviderScreen
              providers={modelProviders}
              onSelect={handleSelectProvider}
            />
          )}
          {screen === "configure" && selectedProvider && (
            <ConfigureScreen
              provider={selectedProvider}
              onSaved={handleConfigSaved}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ---- 屏 1：当前状态 ----

function StatusScreen({
  activeProvider,
  providers,
  onSwitch,
}: {
  activeProvider: ModelProviderInfo | null;
  providers: ModelProviderInfo[];
  onSwitch: () => void;
}) {
  if (!activeProvider) {
    return (
      <div className="px-5 py-6 space-y-4">
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <div className="font-medium mb-1">当前使用试用模式</div>
          <div className="text-xs text-amber-600">
            配置自己的密钥，不消耗试用额度，可无限使用
          </div>
        </div>
        <button
          onClick={onSwitch}
          className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors text-sm font-medium"
        >
          配置自己的密钥
          <ChevronRight size={16} />
        </button>
        <div className="text-xs text-gray-400 text-center">
          支持 DeepSeek · 智谱 GLM · 通义千问 · 本地 Ollama
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-6 space-y-4">
      <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 size={16} className="text-emerald-500" />
          <span className="text-sm font-medium text-gray-800">
            {activeProvider.name}
          </span>
        </div>
        <div className="text-xs text-gray-500 space-y-1">
          <div>
            密钥：
            <span className="font-mono text-gray-700">
              {activeProvider.api_key_hint || "已配置"}
            </span>
          </div>
          <div>
            当前模型：
            <span className="text-gray-700">
              {activeProvider.id !== "ollama"
                ? getModelDisplayName(
                    activeProvider.id,
                    activeProvider.current_model
                  )[0]
                : activeProvider.current_model || "自动检测"}
            </span>
          </div>
        </div>
      </div>

      <button
        onClick={onSwitch}
        className="w-full flex items-center justify-between px-4 py-2.5 rounded-xl border hover:bg-gray-50 transition-colors text-sm text-gray-600"
      >
        切换服务商
        <ChevronRight size={16} className="text-gray-400" />
      </button>

      <div className="text-xs text-gray-400 text-center">
        共 {providers.filter((p) => p.configured).length} 个供应商已配置
      </div>
    </div>
  );
}

// ---- 屏 2：选择服务商 ----

function SelectProviderScreen({
  providers,
  onSelect,
}: {
  providers: ModelProviderInfo[];
  onSelect: (p: ModelProviderInfo) => void;
}) {
  return (
    <div className="px-5 py-5 space-y-3">
      <p className="text-xs text-gray-500">
        选择服务商后填写密钥，密钥获取链接在下一页提供
      </p>
      <div className="grid grid-cols-2 gap-3">
        {providers.map((p) => (
          <button
            key={p.id}
            onClick={() => onSelect(p)}
            className={`flex flex-col items-start p-4 rounded-xl border text-left hover:border-blue-300 hover:bg-blue-50/50 transition-colors ${
              p.is_active
                ? "border-blue-300 bg-blue-50"
                : p.configured
                  ? "border-emerald-200 bg-emerald-50/40"
                  : "border-gray-200 bg-gray-50/60"
            }`}
          >
            <div className="flex items-center justify-between w-full mb-1">
              <span className="text-sm font-medium text-gray-800">{p.name}</span>
              {p.is_active && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700">
                  使用中
                </span>
              )}
              {!p.is_active && p.configured && (
                <CheckCircle2 size={13} className="text-emerald-500" />
              )}
            </div>
            <span className="text-[11px] text-gray-400">{p.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ---- 屏 3：填写密钥 ----

function ConfigureScreen({
  provider,
  onSaved,
}: {
  provider: ModelProviderInfo;
  onSaved: () => void;
}) {
  const isOllama = provider.id === "ollama";
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(
    isOllama ? provider.base_url || "http://localhost:11434" : ""
  );
  const [selectedModel, setSelectedModel] = useState(
    provider.current_model || ""
  );
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsFetchError, setModelsFetchError] = useState(false);
  const [customModel, setCustomModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  // Ollama：初始自动检测
  const [ollamaDetected, setOllamaDetected] = useState(false);

  const fetchModels = useCallback(
    async (keyOverride?: string, urlOverride?: string) => {
      setModelsLoading(true);
      setModelsFetchError(false);
      try {
        // 先保存临时配置（密钥）以便后端能调用供应商 API
        if (!isOllama && (keyOverride ?? apiKey)) {
          await fetch("/api/models/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              provider_id: provider.id,
              api_key: keyOverride ?? apiKey,
              is_active: false, // 仅预存，不激活
            }),
          });
        }
        const url = urlOverride ?? baseUrl;
        const queryParam = isOllama && url ? `?base_url=${encodeURIComponent(url)}` : "";
        const resp = await fetch(
          `/api/models/${provider.id}/available${queryParam}`
        );
        const data = await resp.json();
        if (data.success && Array.isArray(data.data?.models)) {
          const models: string[] = data.data.models;
          setAvailableModels(models);
          if (!selectedModel && models.length > 0) {
            setSelectedModel(models[0]);
          }
          if (isOllama) setOllamaDetected(true);
        } else {
          setModelsFetchError(true);
        }
      } catch {
        setModelsFetchError(true);
      } finally {
        setModelsLoading(false);
      }
    },
    [provider.id, isOllama, apiKey, baseUrl, selectedModel]
  );

  // Ollama 自动检测
  useEffect(() => {
    if (isOllama) {
      void fetchModels();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTestAndSave = async () => {
    setSaving(true);
    setSaveError(null);
    setTestResult(null);
    try {
      // 保存配置（激活该供应商）
      const body: Record<string, unknown> = {
        provider_id: provider.id,
        model: selectedModel || customModel || undefined,
      };
      if (!isOllama && apiKey.trim()) {
        body.api_key = apiKey.trim();
      }
      if (isOllama && baseUrl.trim()) {
        body.base_url = baseUrl.trim();
      }
      const saveResp = await fetch("/api/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const saveData = await saveResp.json();
      if (!saveData.success) {
        setSaveError(saveData.error || "保存失败，请重试");
        return;
      }

      // 测试连接
      setTesting(true);
      const testResp = await fetch(`/api/models/${provider.id}/test`, {
        method: "POST",
      });
      const testData = await testResp.json();
      setTestResult({
        success: testData.success,
        message: testData.success
          ? testData.data?.message ?? "连接成功"
          : testData.error ?? "连接测试失败",
      });

      if (testData.success) {
        setTimeout(onSaved, 600);
      }
    } catch (e) {
      setSaveError(`请求失败: ${String(e)}`);
    } finally {
      setSaving(false);
      setTesting(false);
    }
  };

  const handleFetchModels = () => {
    void fetchModels();
  };

  const displayModels = availableModels.length > 0 ? availableModels : [];

  return (
    <div className="px-5 py-5 space-y-4">
      {/* 密钥获取引导 */}
      {!isOllama && (
        <a
          href={provider.key_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-xs text-blue-600 hover:underline"
        >
          <ExternalLink size={12} />
          在 {provider.key_url.replace("https://", "")} 获取密钥
        </a>
      )}
      {isOllama && (
        <a
          href={provider.key_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-xs text-blue-600 hover:underline"
        >
          <ExternalLink size={12} />
          查看 Ollama 安装教程
        </a>
      )}

      {/* 密钥输入（非 Ollama） */}
      {!isOllama && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">密钥</label>
          <input
            type="password"
            autoComplete="new-password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              provider.api_key_hint
                ? `当前：${provider.api_key_hint}（留空保持不变）`
                : "粘贴你的密钥"
            }
            className="w-full px-3 py-2.5 text-sm border rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
          {/* 密钥填写后拉取模型列表 */}
          {apiKey.trim() && availableModels.length === 0 && !modelsLoading && (
            <button
              onClick={() => void fetchModels(apiKey.trim())}
              className="mt-2 text-xs text-blue-600 hover:underline"
            >
              获取可用模型列表
            </button>
          )}
        </div>
      )}

      {/* Ollama 服务地址 */}
      {isOllama && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">
            服务器地址
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434"
              className="flex-1 px-3 py-2.5 text-sm border rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
            <button
              onClick={handleFetchModels}
              disabled={modelsLoading}
              className="px-3 py-2 text-xs border rounded-xl hover:bg-gray-50 disabled:opacity-50 whitespace-nowrap"
            >
              {modelsLoading ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                "检测模型"
              )}
            </button>
          </div>
        </div>
      )}

      {/* 模型选择 */}
      {modelsLoading && (
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Loader2 size={12} className="animate-spin" />
          获取模型列表中...
        </div>
      )}

      {modelsFetchError && isOllama && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
          未检测到 Ollama 服务，请确认已安装并启动
          <a
            href={provider.key_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 underline"
          >
            查看教程
          </a>
        </div>
      )}

      {displayModels.length > 0 && (
        <div>
          <label className="text-xs text-gray-500 mb-1.5 block">
            选择模型
          </label>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {displayModels.map((modelId) => {
              const [displayName, desc] = getModelDisplayName(
                provider.id,
                modelId
              );
              return (
                <label
                  key={modelId}
                  className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                    selectedModel === modelId
                      ? "border-blue-300 bg-blue-50"
                      : "border-gray-200 hover:bg-gray-50"
                  }`}
                >
                  <input
                    type="radio"
                    name="model"
                    value={modelId}
                    checked={selectedModel === modelId}
                    onChange={() => setSelectedModel(modelId)}
                    className="text-blue-600"
                  />
                  <div>
                    <div className="text-sm text-gray-800">{displayName}</div>
                    {desc && (
                      <div className="text-[11px] text-gray-400">{desc}</div>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        </div>
      )}

      {/* 模型列表拉取失败时的手动输入降级 */}
      {modelsFetchError && !isOllama && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">
            手动输入模型名（模型列表获取失败）
          </label>
          <input
            type="text"
            value={customModel}
            onChange={(e) => setCustomModel(e.target.value)}
            placeholder="如：deepseek-chat"
            className="w-full px-3 py-2 text-sm border rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>
      )}

      {/* 保存按钮 */}
      <button
        onClick={() => void handleTestAndSave()}
        disabled={
          saving ||
          testing ||
          (!isOllama && !apiKey.trim() && !provider.configured) ||
          (isOllama && !ollamaDetected && displayModels.length === 0)
        }
        className="w-full py-2.5 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {saving ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 size={14} className="animate-spin" />
            {testing ? "测试连接中..." : "保存中..."}
          </span>
        ) : (
          "测试并保存"
        )}
      </button>

      {saveError && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 px-3 py-2 rounded-lg">
          {saveError}
        </div>
      )}
      {testResult && (
        <div
          className={`text-xs px-3 py-2 rounded-lg border ${
            testResult.success
              ? "bg-emerald-50 border-emerald-200 text-emerald-700"
              : "bg-red-50 border-red-200 text-red-700"
          }`}
        >
          {testResult.message}
        </div>
      )}
    </div>
  );
}
