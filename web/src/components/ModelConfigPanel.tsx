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
 Sparkles,
 Trash2,
 X,
} from "lucide-react";
import { useStore } from "../store";
import type { ActiveModelInfo, ModelProviderInfo } from "../store/types";
import { deleteProviderConfig } from "../store/api-actions";
import { CommandSheet, ConfirmDialog } from "./ui";
import Button from "./ui/Button";

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

function getApiModeLabel(apiMode?: string | null): string {
 if (apiMode === "standard") return "普通";
 if (apiMode === "coding_plan") return "Coding Plan";
 if (apiMode === "unknown") return "未知";
 return "未选择";
}

function getProviderModeBaseUrl(
 providerId: string,
 apiMode: string
): string | null {
 if (providerId === "zhipu") {
 if (apiMode === "standard") {
 return "https://open.bigmodel.cn/api/paas/v4/chat/completions";
 }
 if (apiMode === "coding_plan") {
 return "https://open.bigmodel.cn/api/coding/paas/v4";
 }
 }
 if (providerId === "dashscope") {
 if (apiMode === "standard") {
 return "https://dashscope.aliyuncs.com/compatible-mode/v1";
 }
 if (apiMode === "coding_plan") {
 return "https://coding.dashscope.aliyuncs.com/v1";
 }
 }
 return null;
}

type Screen = "status" | "select-provider" | "configure";

interface BuiltinUsage {
 fast_calls_used: number;
 deep_calls_used: number;
 fast_limit: number;
 deep_limit: number;
}

interface Props {
 open: boolean;
 onClose: () => void;
}

export default function ModelConfigPanel({ open, onClose }: Props) {
 const modelProviders = useStore((s) => s.modelProviders);
 const activeModel = useStore((s) => s.activeModel);
 const fetchModelProviders = useStore((s) => s.fetchModelProviders);
 const fetchActiveModel = useStore((s) => s.fetchActiveModel);

 const [screen, setScreen] = useState<Screen>("status");
 const [selectedProvider, setSelectedProvider] =
 useState<ModelProviderInfo | null>(null);
 const [builtinUsage, setBuiltinUsage] = useState<BuiltinUsage | null>(null);

 const fetchBuiltinUsage = useCallback(async () => {
 try {
 const resp = await fetch("/api/trial/status");
 const data = await resp.json();
 if (data.success && data.data) {
 const d = data.data as Record<string, number>;
 setBuiltinUsage({
 fast_calls_used: d.fast_calls_used ?? 0,
 deep_calls_used: d.deep_calls_used ?? 0,
 fast_limit: d.fast_limit ?? 50,
 deep_limit: d.deep_limit ?? 20,
 });
 }
 } catch {
 // 静默失败
 }
 }, []);

 useEffect(() => {
 if (open) {
 void fetchModelProviders();
 void fetchActiveModel();
 void fetchBuiltinUsage();
 setScreen("status");
 }
 }, [open, fetchModelProviders, fetchActiveModel, fetchBuiltinUsage]);

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

 return (
 <CommandSheet isOpen={open} onClose={onClose} title="AI 设置">
 {/* 标题栏 */}
 <div className="flex items-center justify-between px-5 py-4 border-b">
 <div className="flex items-center gap-2">
 {screen !== "status" && (
 <Button
 variant="ghost"
 onClick={() =>
 setScreen(
 screen === "configure" ? "select-provider" : "status"
 )
 }
 className="p-1 rounded-lg mr-1"
 aria-label="返回"
 >
 <ArrowLeft size={16} />
 </Button>
 )}
 <Bot size={18} className="text-[var(--accent)]" />
 <h2 className="text-base font-semibold text-[var(--text-primary)]">
 {screen === "status" && "AI 设置"}
 {screen === "select-provider" && "选择服务商"}
 {screen === "configure" &&
 `配置 ${selectedProvider?.name ?? ""}`}
 </h2>
 </div>
 <Button
 variant="ghost"
 onClick={onClose}
 className="p-1.5 rounded-lg"
 aria-label="关闭"
 >
 <X size={18} />
 </Button>
 </div>

 {/* 内容区 */}
 <div className="flex-1 overflow-y-auto">
 {screen === "status" && (
 <StatusScreen
 activeModel={activeModel}
 activeProvider={activeProvider}
 providers={modelProviders}
 builtinUsage={builtinUsage}
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
 </CommandSheet>
 );
}

// ---- 屏 1：当前状态 ----

function UsageBar({
 label,
 used,
 limit,
}: {
 label: string;
 used: number;
 limit: number;
}) {
 const pct = Math.min(100, Math.round((used / limit) * 100));
 const isWarning = pct >= 80;
 const isExhausted = used >= limit;
 return (
 <div className="space-y-0.5">
 <div className="flex justify-between text-[11px]">
 <span className={isExhausted ? "text-[var(--error)] font-medium" : "text-[var(--text-secondary)]"}>
 {label}
 </span>
 <span
 className={
 isExhausted
 ? "text-[var(--error)] font-medium"
 : isWarning
 ? "text-[var(--warning)]"
 : "text-[var(--text-muted)]"
 }
 >
 {used} / {limit}
 </span>
 </div>
 <div className="h-1.5 rounded-full bg-[var(--bg-overlay)] overflow-hidden">
 <div
 className={`h-full rounded-full transition-all ${
 isExhausted
 ? "bg-[var(--error)]"
 : isWarning
 ? "bg-[var(--warning)]"
 : "bg-[var(--accent)]"
 }`}
 style={{ width: `${pct}%` }}
 />
 </div>
 </div>
 );
}

function StatusScreen({
 activeModel,
 activeProvider,
 providers,
 builtinUsage,
 onSwitch,
}: {
 activeModel: ActiveModelInfo | null;
 activeProvider: ModelProviderInfo | null;
 providers: ModelProviderInfo[];
 builtinUsage: BuiltinUsage | null;
 onSwitch: () => void;
}) {
 const isBuiltin = activeModel?.provider_id === "builtin";

 // 系统内置模式
 if (isBuiltin) {
 const fastExhausted =
 builtinUsage && builtinUsage.fast_calls_used >= builtinUsage.fast_limit;
 const deepExhausted =
 builtinUsage && builtinUsage.deep_calls_used >= builtinUsage.deep_limit;
 const anyExhausted = fastExhausted || deepExhausted;

 return (
 <div className="px-5 py-6 space-y-4">
 <div
 className={`rounded-xl border p-4 ${
 anyExhausted
 ? "border-[var(--warning)] bg-[var(--warning-subtle)]"
 : "border-[var(--accent-subtle)] bg-[var(--accent-subtle)]/60"
 }`}
 >
 <div className="flex items-center gap-2 mb-3">
 <Sparkles
 size={16}
 className={anyExhausted ? "text-[var(--warning)]" : "text-[var(--accent)]"}
 />
 <span className="text-sm font-medium text-[var(--text-primary)]">系统内置</span>
 <span
 className={`text-[10px] px-1.5 py-0.5 rounded-full ${
 anyExhausted
 ? "bg-[var(--warning-subtle)] text-[var(--warning)]"
 : "bg-[var(--accent-subtle)] text-[var(--accent)]"
 }`}
 >
 当前使用
 </span>
 </div>
 <div className="text-xs text-[var(--text-secondary)] mb-3">
 模式：<span className="text-[var(--text-secondary)]">{activeModel?.model ?? "快速"}</span>
 </div>
 {builtinUsage && (
 <div className="space-y-2">
 <UsageBar
 label="快速模式"
 used={builtinUsage.fast_calls_used}
 limit={builtinUsage.fast_limit}
 />
 <UsageBar
 label="深度模式"
 used={builtinUsage.deep_calls_used}
 limit={builtinUsage.deep_limit}
 />
 {anyExhausted && (
 <p className="text-[11px] text-[var(--warning)] pt-1">
 部分模式已用完试用额度，配置自己的密钥可无限使用
 </p>
 )}
 </div>
 )}
 </div>
 <Button
 variant="ghost"
 onClick={onSwitch}
 className="w-full flex items-center justify-between px-4 py-2.5 rounded-xl border"
 >
 配置自己的密钥 / 切换服务商
 <ChevronRight size={16} className="text-[var(--text-muted)]" />
 </Button>
 <div className="text-xs text-[var(--text-muted)] text-center">
 {(() => { const n = providers.filter((p) => p.configured).length; return n > 0 ? `共 ${n} 个自有供应商已配置` : "支持 DeepSeek · 智谱 GLM · 通义千问 · 本地 Ollama"; })()}
 </div>
 </div>
 );
 }

 // 外部供应商已激活
 if (activeProvider) {
 return (
 <div className="px-5 py-6 space-y-4">
 <div className="rounded-xl border border-[var(--success)] bg-[var(--success-subtle)] p-4">
 <div className="flex items-center gap-2 mb-3">
 <CheckCircle2 size={16} className="text-[var(--success)]" />
 <span className="text-sm font-medium text-[var(--text-primary)]">
 {activeProvider.name}
 </span>
 </div>
 <div className="text-xs text-[var(--text-secondary)] space-y-1">
 {activeProvider.id !== "ollama" ? (
 <div>
 密钥：
 <span className="font-mono text-[var(--text-secondary)]">
 {activeProvider.api_key_hint || "已配置"}
 </span>
 </div>
 ) : (
 <div>
 服务地址：
 <span className="font-mono text-[var(--text-secondary)]">
 {activeProvider.base_url || "http://localhost:11434"}
 </span>
 </div>
 )}
 <div>
 当前模型：
 <span className="text-[var(--text-secondary)]">
 {activeProvider.id !== "ollama"
 ? getModelDisplayName(
 activeProvider.id,
 activeProvider.current_model
 )[0]
 : activeProvider.current_model || "自动检测"}
 </span>
 </div>
 {activeProvider.api_mode && (
 <div>
 接口模式：
 <span className="text-[var(--text-secondary)]">
 {getApiModeLabel(activeProvider.api_mode)}
 </span>
 </div>
 )}
 </div>
 </div>

 <Button
 variant="ghost"
 onClick={onSwitch}
 className="w-full flex items-center justify-between px-4 py-2.5 rounded-xl border"
 >
 切换服务商
 <ChevronRight size={16} className="text-[var(--text-muted)]" />
 </Button>

 <div className="text-xs text-[var(--text-muted)] text-center">
 共 {providers.filter((p) => p.configured).length} 个供应商已配置
 </div>
 </div>
 );
 }

 // 试用模式
 return (
 <div className="px-5 py-6 space-y-4">
 <div className="rounded-xl border border-[var(--warning)] bg-[var(--accent-subtle)] p-4 text-sm text-[var(--warning)]">
 <div className="font-medium mb-1">当前使用试用模式</div>
 <div className="text-xs text-[var(--warning)]">
 配置自己的密钥，不消耗试用额度，可无限使用
 </div>
 </div>
 <Button
 variant="primary"
 onClick={onSwitch}
 className="w-full flex items-center justify-between px-4 py-3 rounded-xl"
 >
 配置自己的密钥
 <ChevronRight size={16} />
 </Button>
 <div className="text-xs text-[var(--text-muted)] text-center">
 支持 DeepSeek · 智谱 GLM · 通义千问 · 本地 Ollama
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
 <p className="text-xs text-[var(--text-secondary)]">
 选择服务商后填写密钥，密钥获取链接在下一页提供
 </p>
 <div className="grid grid-cols-2 gap-3">
 {providers.map((p) => (
 <button
 type="button"
 key={p.id}
 onClick={() => onSelect(p)}
 className={`flex flex-col items-start p-4 rounded-xl border text-left transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent)] ${
 p.configured
 ? "border-[var(--success)] bg-[var(--accent-subtle)]/40 hover:bg-[var(--accent-subtle)]/60"
 : "border-[var(--border-subtle)] bg-transparent hover:bg-[var(--bg-hover)]"
 }`}
 >
 <div className="flex items-center justify-between w-full mb-1">
 <span className="text-sm font-medium text-[var(--text-primary)]">{p.name}</span>
 {p.configured && (
 <CheckCircle2 size={13} className="text-[var(--success)]" />
 )}
 </div>
 <span className="text-[11px] text-[var(--text-muted)] whitespace-normal">
 {p.configured && p.api_mode
 ? `${getApiModeLabel(p.api_mode)} · ${p.current_model || p.description}`
 : p.configured && p.current_model
 ? p.current_model
 : p.description}
 </span>
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
 const supportsApiMode = (provider.supported_api_modes?.length ?? 0) > 0;
 const lockedConfig = provider.configured && provider.can_edit_in_place === false;
 const [apiKey, setApiKey] = useState("");
 const [baseUrl, setBaseUrl] = useState(
 provider.base_url || (isOllama ? "http://localhost:11434" : "")
 );
 const [selectedApiMode, setSelectedApiMode] = useState<string>(
 provider.configured && provider.api_mode && provider.api_mode !== "unknown"
 ? provider.api_mode
 : ""
 );
 const [saving, setSaving] = useState(false);
 const [testing, setTesting] = useState(false);
 const [saveError, setSaveError] = useState<string | null>(null);
 const [testResult, setTestResult] = useState<{
 success: boolean;
 message: string;
 } | null>(null);
 const [removing, setRemoving] = useState(false);
 const [confirmRemoveOpen, setConfirmRemoveOpen] = useState(false);

 const handleTestAndSave = async () => {
 setSaving(true);
 setSaveError(null);
 setTestResult(null);
 try {
 // 先用临时配置测试，成功后再保存，避免测试失败也落库。
 const resolvedBaseUrl =
 supportsApiMode && selectedApiMode
 ? getProviderModeBaseUrl(provider.id, selectedApiMode)
 : null;
 const body: Record<string, unknown> = {
 provider_id: provider.id,
 };
 if (supportsApiMode) {
 body.api_mode = selectedApiMode || undefined;
 }
 if (!isOllama && apiKey.trim()) {
 body.api_key = apiKey.trim();
 }
 if (resolvedBaseUrl) {
 body.base_url = resolvedBaseUrl;
 } else if (baseUrl.trim()) {
 body.base_url = baseUrl.trim();
 }
 setTesting(true);
 const testResp = await fetch(`/api/models/${provider.id}/test`, {
 method: "POST",
 headers: { "Content-Type": "application/json" },
 body: JSON.stringify(body),
 });
 const testData = await testResp.json();
 setTestResult({
 success: testData.success,
 message: testData.success
 ? testData.data?.message ?? "连接成功"
 : testData.error ?? "连接测试失败",
 });
 if (!testData.success) {
 return;
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

 setTimeout(onSaved, 600);
 } catch (e) {
 setSaveError(`请求失败: ${String(e)}`);
 } finally {
 setSaving(false);
 setTesting(false);
 }
 };

 const handleRemove = async () => {
 setRemoving(true);
 try {
 const ok = await deleteProviderConfig(provider.id);
 if (ok) {
 window.dispatchEvent(new Event("nini:model-config-updated"));
 onSaved();
 } else {
 setSaveError("移除配置失败，请重试");
 }
 } finally {
 setRemoving(false);
 setConfirmRemoveOpen(false);
 }
 };

 return (
 <div className="px-5 py-5 space-y-4">
 {lockedConfig ? (
 <>
 <div className="rounded-xl border border-[var(--warning)] bg-[var(--accent-subtle)]/70 p-4 text-sm text-[var(--warning)]">
 <div className="font-medium">当前配置已锁定</div>
 <div className="mt-1 text-xs text-[var(--warning)]">
 如需修改模式、密钥、模型或端点，请先移除当前配置后重新配置。
 </div>
 </div>
 <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)]/70 p-4 space-y-3 text-sm">
 <div>
 <div className="text-xs text-[var(--text-muted)]">接口模式</div>
 <div className="mt-1 text-[var(--text-secondary)]">
 {getApiModeLabel(provider.api_mode)}
 </div>
 </div>
 {!isOllama && (
 <div>
 <div className="text-xs text-[var(--text-muted)]">API Key</div>
 <div className="mt-1 font-mono text-[var(--text-secondary)]">
 {provider.api_key_hint || "已配置"}
 </div>
 </div>
 )}
 <div>
 <div className="text-xs text-[var(--text-muted)]">Base URL</div>
 <div className="mt-1 break-all text-[var(--text-secondary)]">
 {provider.base_url || "默认端点"}
 </div>
 </div>
 <div>
 <div className="text-xs text-[var(--text-muted)]">当前模型</div>
 <div className="mt-1 text-[var(--text-secondary)]">
 {provider.current_model || "未选择"}
 </div>
 </div>
 </div>
 </>
 ) : (
 <>
 {/* 密钥获取引导 */}
 {!isOllama && (
 <a
 href={provider.key_url}
 target="_blank"
 rel="noopener noreferrer"
 className="flex items-center gap-1.5 text-xs text-[var(--accent)] hover:underline"
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
 className="flex items-center gap-1.5 text-xs text-[var(--accent)] hover:underline"
 >
 <ExternalLink size={12} />
 查看 Ollama 安装教程
 </a>
 )}

 {supportsApiMode && (
 <div>
 <label className="text-xs text-[var(--text-secondary)] mb-1.5 block">
 接口模式
 </label>
 <div className="grid grid-cols-2 gap-2">
 {(provider.supported_api_modes ?? []).map((mode) => (
 <Button
 key={mode}
 variant="ghost"
 type="button"
 onClick={() => setSelectedApiMode(mode)}
 className={`rounded-xl border px-3 py-2.5 text-sm transition-colors ${
 selectedApiMode === mode
 ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]"
 : ""
 }`}
 >
 {getApiModeLabel(mode)}
 </Button>
 ))}
 </div>
 <div className="mt-1 text-[11px] text-[var(--text-muted)]">
 必须先选择模式，保存后如需变更请删除配置后重配
 </div>
 </div>
 )}

 {/* 密钥输入（非 Ollama） */}
 {!isOllama && (
 <div>
 <label className="text-xs text-[var(--text-secondary)] mb-1 block">密钥</label>
 <input
 type="password"
 autoComplete="new-password"
 value={apiKey}
 onChange={(e) => setApiKey(e.target.value)}
 placeholder={
 provider.api_key_hint
 ? `当前：${provider.api_key_hint}`
 : "粘贴你的密钥"
 }
 className="w-full px-3 py-2.5 text-sm border rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--accent)] dark:bg-[var(--bg-elevated)] dark:border-[var(--border-default)] dark:text-[var(--text-disabled)] dark:placeholder:text-[var(--text-muted)]"
 />
 </div>
 )}

 {/* Ollama 服务地址 */}
 {isOllama && (
 <div>
 <label className="text-xs text-[var(--text-secondary)] mb-1 block">
 服务器地址
 </label>
 <input
 type="text"
 value={baseUrl}
 onChange={(e) => setBaseUrl(e.target.value)}
 placeholder="http://localhost:11434"
 className="w-full px-3 py-2.5 text-sm border rounded-xl focus:outline-none focus:ring-2 focus:ring-[var(--accent)] dark:bg-[var(--bg-elevated)] dark:border-[var(--border-default)] dark:text-[var(--text-disabled)] dark:placeholder:text-[var(--text-muted)]"
 />
 </div>
 )}
 </>
 )}

 {/* 保存按钮 */}
 <Button
 variant="primary"
 onClick={() => void handleTestAndSave()}
 disabled={
 lockedConfig ||
 saving ||
 testing ||
 (!isOllama && !apiKey.trim() && !provider.configured) ||
 (supportsApiMode && !selectedApiMode) ||
 (isOllama && !baseUrl.trim())
 }
 className="w-full py-2.5 rounded-xl"
 >
 {saving ? (
 <span className="flex items-center justify-center gap-2">
 <Loader2 size={14} className="animate-spin" />
 {testing ? "测试连接中..." : "保存中..."}
 </span>
 ) : (
 "测试并保存"
 )}
 </Button>

 {saveError && (
 <div className="text-xs text-[var(--error)] bg-[var(--accent-subtle)] border border-[var(--error)] px-3 py-2 rounded-lg">
 {saveError}
 </div>
 )}
 {testResult && (
 <div
 className={`text-xs px-3 py-2 rounded-lg border ${
 testResult.success
 ? "bg-[var(--accent-subtle)] border-[var(--success)] text-[var(--success)]"
 : "bg-[var(--accent-subtle)] border-[var(--error)] text-[var(--error)]"
 }`}
 >
 {testResult.message}
 </div>
 )}

 {(provider.configured || lockedConfig) && (
 <div className="pt-2 border-t border-[var(--border-subtle)]">
 <Button
 variant="danger"
 onClick={() => setConfirmRemoveOpen(true)}
 disabled={removing || saving || provider.can_delete_config === false}
 className="flex items-center gap-1.5 text-xs"
 >
 {removing ? (
 <Loader2 size={12} className="animate-spin" />
 ) : (
 <Trash2 size={12} />
 )}
 {provider.can_delete_config === false
 ? "当前为环境变量配置，请通过环境变量修改"
 : "移除此供应商配置"}
 </Button>
 </div>
 )}

 <ConfirmDialog
 isOpen={confirmRemoveOpen && provider.can_delete_config !== false}
 onCancel={() => setConfirmRemoveOpen(false)}
 onConfirm={() => void handleRemove()}
 title="确认移除配置"
 description={`确认移除「${provider.name}${provider.api_mode ? ` · ${getApiModeLabel(provider.api_mode)}` : ""}」配置？移除后将删除当前 API 配置；如需切换普通模式或 Coding Plan，需要重新配置。`}
 confirmLabel={removing ? "移除中..." : "确认移除"}
 destructive
 />
 </div>
 );
}
