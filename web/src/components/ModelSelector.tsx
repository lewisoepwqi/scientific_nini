/**
 * 模型选择器。
 * 默认提供对话内快速切换；完整配置仍通过 AI 设置面板处理。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../store";
import Button from "./ui/Button";
import {
 Bot,
 Check,
 ChevronDown,
 Loader2,
 Settings2,
 Sparkles,
} from "lucide-react";

interface ModelSelectorProps {
 compact?: boolean;
 onOpenSettings?: () => void;
}

interface ProviderModelsState {
 loading: boolean;
 models: string[];
 error: boolean;
}

interface BuiltinUsage {
 fast_calls_used: number;
 deep_calls_used: number;
 fast_limit: number;
 deep_limit: number;
}

const BUILTIN_PROVIDER_ID = "builtin";
const BUILTIN_PROVIDER_NAME = "系统内置";
const BUILTIN_MODE_OPTIONS = [
 {
 id: "fast",
 label: "快速",
 description: "更快，适合日常使用",
 },
 {
 id: "deep",
 label: "深度",
 description: "更强，适合复杂任务",
 },
] as const;

function isBuiltinModeSelected(
 selectedProviderId: string | null,
 selectedModel: string | null,
 optionId: string,
 optionLabel: string,
): boolean {
 if (selectedProviderId !== BUILTIN_PROVIDER_ID) return false;
 const normalized = (selectedModel || "").trim().toLowerCase();
 return normalized === optionId || normalized === optionLabel.trim().toLowerCase();
}

export default function ModelSelector({
 compact = false,
 onOpenSettings,
}: ModelSelectorProps) {
 const activeModel = useStore((s) => s.activeModel);
 const runtimeModel = useStore((s) => s.runtimeModel);
 const modelFallback = useStore((s) => s.modelFallback);
 const isStreaming = useStore((s) => s.isStreaming);
 const fetchActiveModel = useStore((s) => s.fetchActiveModel);
 const fetchModelProviders = useStore((s) => s.fetchModelProviders);
 const modelProviders = useStore((s) => s.modelProviders);
 const modelProvidersLoading = useStore((s) => s.modelProvidersLoading);
 const setChatRoute = useStore((s) => s.setChatRoute);

 const [menuOpen, setMenuOpen] = useState(false);
 const [builtinUsage, setBuiltinUsage] = useState<BuiltinUsage | null>(null);
 const [switchingKey, setSwitchingKey] = useState<string | null>(null);
 const [expandedProviderId, setExpandedProviderId] = useState<string | null>(null);
 const [providerModels, setProviderModels] = useState<
 Record<string, ProviderModelsState>
 >({});
 // 缓存各供应商已加载的模型数量，避免每次打开时从 0 → 1 → 真实数量闪烁
 const [cachedModelCounts, setCachedModelCounts] = useState<Record<string, number>>(() => {
 try {
 const raw = localStorage.getItem("nini:provider_model_counts");
 return raw ? (JSON.parse(raw) as Record<string, number>) : {};
 } catch {
 return {};
 }
 });
 const wrapperRef = useRef<HTMLDivElement>(null);

 useEffect(() => {
 void fetchActiveModel();
 void fetchModelProviders();
 }, [fetchActiveModel, fetchModelProviders]);

 // 监听配置更新，刷新显示
 useEffect(() => {
 const handler = () => {
 setProviderModels({});
 setCachedModelCounts({});
 try {
 localStorage.removeItem("nini:provider_model_counts");
 } catch {
 // localStorage 不可用时忽略
 }
 void fetchActiveModel();
 void fetchModelProviders();
 };
 window.addEventListener("nini:model-config-updated", handler);
 return () => window.removeEventListener("nini:model-config-updated", handler);
 }, [fetchActiveModel, fetchModelProviders]);

 useEffect(() => {
 if (!menuOpen) return;

 const handlePointerDown = (event: MouseEvent) => {
 if (
 wrapperRef.current &&
 !wrapperRef.current.contains(event.target as Node)
 ) {
 setMenuOpen(false);
 }
 };

 const handleEscape = (event: KeyboardEvent) => {
 if (event.key === "Escape") {
 setMenuOpen(false);
 }
 };

 document.addEventListener("mousedown", handlePointerDown);
 document.addEventListener("keydown", handleEscape);
 return () => {
 document.removeEventListener("mousedown", handlePointerDown);
 document.removeEventListener("keydown", handleEscape);
 };
 }, [menuOpen]);

 // 空闲时优先显示用户当前选择的模型；仅在生成中显示实际运行模型
 const activeProvider = modelProviders.find((p) => p.is_active);
 const effectiveRuntimeModel =
 runtimeModel?.model && (isStreaming || Boolean(modelFallback))
 ? runtimeModel
 : null;
 const displayText =
 effectiveRuntimeModel?.model ||
 activeModel?.model ||
 (activeProvider ? activeProvider.current_model : null) ||
 "试用中";
 const displayProvider =
 effectiveRuntimeModel?.provider_name ||
 activeModel?.provider_name ||
 activeProvider?.name ||
 "系统默认";
 const configuredProviders = useMemo(
 () => modelProviders.filter((provider) => provider.configured),
 [modelProviders],
 );
 const selectedProviderId =
 activeModel?.provider_id || activeProvider?.id || null;
 const selectedModel =
 activeModel?.model || activeProvider?.current_model || null;

 const triggerClass = compact
 ? "h-8 px-2.5 text-xs"
 : "px-2.5 py-1 text-xs";
 const menuWidthClass = compact ? "w-[300px]" : "w-[340px]";

 const buildFallbackModels = useCallback(
 (providerId: string) => {
 const provider = configuredProviders.find((item) => item.id === providerId);
 if (!provider) return [];

 return Array.from(
 new Set(
 [provider.current_model, ...(provider.available_models ?? [])].filter(
 (model): model is string => Boolean(model && model.trim()),
 ),
 ),
 );
 },
 [configuredProviders],
 );

 const fetchBuiltinUsage = async () => {
 try {
 const resp = await fetch("/api/trial/status");
 const data = await resp.json();
 if (data.success && data.data) {
 const d = data.data as Record<string, number>;
 setBuiltinUsage({
 fast_calls_used: d.fast_calls_used ?? 0,
 deep_calls_used: d.deep_calls_used ?? 0,
 fast_limit: d.fast_limit ?? 100,
 deep_limit: d.deep_limit ?? 50,
 });
 }
 } catch {
 // 静默失败
 }
 };

 const handleToggleMenu = () => {
 const nextOpen = !menuOpen;
 setMenuOpen(nextOpen);
 if (nextOpen) {
 void fetchModelProviders();
 void fetchActiveModel();
 void fetchBuiltinUsage();
 }
 };

 const loadProviderModels = useCallback(
 async (providerId: string) => {
 const current = providerModels[providerId];
 if (current?.loading) return;
 if (current && current.models.length > 0 && !current.error) return;

 const fallbackModels = buildFallbackModels(providerId);
 setProviderModels((prev) => ({
 ...prev,
 [providerId]: {
 loading: true,
 models: prev[providerId]?.models ?? fallbackModels,
 error: false,
 },
 }));

 try {
 const resp = await fetch(`/api/models/${providerId}/available`);
 const data = await resp.json();
 const remoteModels =
 data.success && Array.isArray(data.data?.models)
 ? (data.data.models as string[])
 : [];
 const models = Array.from(
 new Set([...remoteModels, ...fallbackModels].filter(Boolean)),
 );
 setProviderModels((prev) => ({
 ...prev,
 [providerId]: {
 loading: false,
 models,
 error: models.length === 0,
 },
 }));
 if (models.length > 0) {
 setCachedModelCounts((prev) => {
 const next = { ...prev, [providerId]: models.length };
 try {
 localStorage.setItem("nini:provider_model_counts", JSON.stringify(next));
 } catch {
 // localStorage 不可用时忽略
 }
 return next;
 });
 }
 } catch {
 setProviderModels((prev) => ({
 ...prev,
 [providerId]: {
 loading: false,
 models: fallbackModels,
 error: true,
 },
 }));
 }
 },
 [buildFallbackModels, providerModels],
 );

 useEffect(() => {
 if (!activeProvider?.id) return;
 void loadProviderModels(activeProvider.id);
 }, [activeProvider?.id, loadProviderModels]);

 const handleToggleProvider = (providerId: string) => {
 if (expandedProviderId === providerId) {
 setExpandedProviderId(null);
 return;
 }
 setExpandedProviderId(providerId);
 if (providerId !== BUILTIN_PROVIDER_ID) {
 void loadProviderModels(providerId);
 }
 };

 const handleSelectRoute = async (providerId: string | null, model: string | null) => {
 const optionKey = `${providerId ?? "auto"}:${model ?? ""}`;
 setSwitchingKey(optionKey);
 try {
 const success = await setChatRoute(providerId ?? "", model);
 if (!success) {
 return;
 }
 window.dispatchEvent(new Event("nini:model-config-updated"));
 setMenuOpen(false);
 } finally {
 setSwitchingKey(null);
 }
 };

 useEffect(() => {
 if (!menuOpen) return;

 const preferredExpandedId =
 (selectedProviderId &&
 (selectedProviderId === BUILTIN_PROVIDER_ID ||
 configuredProviders.some((provider) => provider.id === selectedProviderId)) &&
 selectedProviderId) ||
 BUILTIN_PROVIDER_ID ||
 configuredProviders[0]?.id ||
 null;

 setExpandedProviderId((prev) => prev ?? preferredExpandedId);
 if (preferredExpandedId && preferredExpandedId !== BUILTIN_PROVIDER_ID) {
 void loadProviderModels(preferredExpandedId);
 }
 }, [menuOpen, selectedProviderId, configuredProviders]);

 return (
 <div className="relative" ref={wrapperRef}>
 <Button
 variant="ghost"
 onClick={handleToggleMenu}
 className={`flex items-center gap-1.5 ${triggerClass}`}
 title={`快速切换模型，当前 ${displayText}`}
 aria-label="快速切换模型"
 aria-haspopup="menu"
 aria-expanded={menuOpen}
 >
 <Bot size={13} className="text-[var(--accent)] flex-shrink-0" />
 <span className="truncate max-w-[120px]">{displayText}</span>
 <ChevronDown
 size={12}
 className={`text-[var(--text-muted)] transition-transform ${menuOpen ? "rotate-180" : ""}`}
 />
 </Button>

 {menuOpen ? (
 <div
 className={`absolute bottom-[calc(100%+10px)] right-0 z-30 flex max-h-[min(34rem,calc(100vh-8rem))] flex-col overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--bg-base)] shadow-[0_18px_50px_rgba(15,23,42,0.16)] ${menuWidthClass}`}
 >
 <div className="border-b border-[var(--border-subtle)] bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.14),_transparent_55%),linear-gradient(180deg,_rgba(248,250,252,0.96),_rgba(255,255,255,1))] dark:bg-[var(--bg-elevated)] px-4 py-3">
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0">
 <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-muted)]">
 快速切换
 </div>
 <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
 <span className="truncate">{displayText}</span>
 {effectiveRuntimeModel?.model &&
 effectiveRuntimeModel.model !== selectedModel ? (
 <span className="rounded-full bg-[var(--accent-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--warning)]">
 实际运行
 </span>
 ) : null}
 </div>
 <div className="mt-1 text-xs text-[var(--text-secondary)]">
 {displayProvider}
 </div>
 </div>
 <div className="rounded-full border border-[var(--accent-subtle)] bg-[var(--bg-base)]/80 dark:bg-[var(--bg-overlay)] p-1.5 text-[var(--accent)] shadow-sm">
 <Sparkles size={14} />
 </div>
 </div>
 </div>

 <div className="flex-1 overflow-y-auto px-2 py-2">
 <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">
 系统内置
 </div>

 <div
 className={`mt-1 overflow-hidden rounded-xl border transition-colors ${
 selectedProviderId === BUILTIN_PROVIDER_ID
 ? "border-[var(--accent-subtle)] bg-[var(--accent-subtle)]/70 shadow-sm"
 : "border-[var(--border-default)] bg-[var(--bg-base)]"
 }`}
 >
 <Button
 variant="ghost"
 type="button"
 onClick={() => handleToggleProvider(BUILTIN_PROVIDER_ID)}
 className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors ${
 expandedProviderId === BUILTIN_PROVIDER_ID ? "bg-[var(--bg-elevated)] dark:bg-[var(--bg-overlay)]/50" : ""
 }`}
 >
 <div
 className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl ${
 selectedProviderId === BUILTIN_PROVIDER_ID
 ? "bg-[var(--accent-subtle)] text-[var(--accent)] dark:text-[var(--accent)]"
 : "bg-[var(--accent-subtle)] text-[var(--domain-profile)] dark:text-[var(--domain-profile)]"
 }`}
 >
 <Sparkles size={14} />
 </div>
 <div className="min-w-0 flex-1">
 <div className="flex items-center gap-2">
 <span className="truncate text-sm font-medium text-[var(--text-primary)]">
 {BUILTIN_PROVIDER_NAME}
 </span>
 {selectedProviderId === BUILTIN_PROVIDER_ID ? (
 <span className="rounded-full bg-[var(--accent-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--accent)]">
 当前对话
 </span>
 ) : null}
 </div>
 <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
 <span className="truncate">
 {selectedProviderId === BUILTIN_PROVIDER_ID
 ? selectedModel || "请选择模式"
 : "快速 / 深度"}
 </span>
 <span className="text-[var(--text-muted)]">·</span>
 <span className="whitespace-nowrap">2 个模式</span>
 </div>
 </div>
 <ChevronDown
 size={14}
 className={`flex-shrink-0 text-[var(--text-muted)] transition-transform ${
 expandedProviderId === BUILTIN_PROVIDER_ID ? "rotate-180" : ""
 }`}
 />
 </Button>

 {expandedProviderId === BUILTIN_PROVIDER_ID ? (
 <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-2">
 {BUILTIN_MODE_OPTIONS.map((option) => {
 const optionKey = `${BUILTIN_PROVIDER_ID}:${option.id}`;
 const isSelected = isBuiltinModeSelected(
 selectedProviderId,
 selectedModel,
 option.id,
 option.label,
 );

 // 剩余次数计算
 const used = builtinUsage
 ? option.id === "fast"
 ? builtinUsage.fast_calls_used
 : builtinUsage.deep_calls_used
 : null;
 const limit = builtinUsage
 ? option.id === "fast"
 ? builtinUsage.fast_limit
 : builtinUsage.deep_limit
 : null;
 const remaining = used !== null && limit !== null ? limit - used : null;
 const isExhausted = remaining !== null && remaining <= 0;
 const isLow = remaining !== null && remaining > 0 && remaining <= Math.ceil((limit ?? 0) * 0.2);

 return (
 <Button
 key={optionKey}
 variant="ghost"
 type="button"
 onClick={() =>
 void handleSelectRoute(BUILTIN_PROVIDER_ID, option.id)
 }
 disabled={switchingKey !== null}
 className={`mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors ${
 isSelected
 ? "border border-[var(--accent-subtle)] bg-[var(--accent-subtle)] text-[var(--text-primary)] shadow-sm"
 : ""
 }`}
 >
 <div
 className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg ${
 isSelected
 ? "bg-[var(--accent-subtle)] text-[var(--accent)] dark:text-[var(--accent)]"
 : "bg-[var(--bg-elevated)] text-[var(--text-muted)] dark:bg-[var(--bg-overlay)] dark:text-[var(--text-muted)]"
 }`}
 >
 {switchingKey === optionKey ? (
 <Loader2 size={13} className="animate-spin" />
 ) : isSelected ? (
 <Check size={13} />
 ) : (
 <Sparkles size={13} />
 )}
 </div>
 <div className="min-w-0 flex-1">
 <div className="truncate text-sm font-medium">
 {option.label}
 </div>
 <div
 className={`truncate text-[11px] ${
 isSelected ? "text-[var(--text-secondary)]" : "text-[var(--text-secondary)]"
 }`}
 >
 {option.description}
 </div>
 </div>
 {remaining !== null && (
 <span
 className={`flex-shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
 isExhausted
 ? "bg-[var(--accent-subtle)] text-[var(--error)]"
 : isLow
 ? "bg-[var(--accent-subtle)] text-[var(--warning)]"
 : "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
 }`}
 >
 {isExhausted ? "已用完" : `剩余 ${remaining}`}
 </span>
 )}
 {isSelected && remaining === null ? <Check size={14} /> : null}
 </Button>
 );
 })}
 </div>
 ) : null}
 </div>

 <div className="px-2 pb-1 pt-3 text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">
 已配置模型
 </div>

 {modelProvidersLoading && configuredProviders.length === 0 ? (
 <div className="flex items-center gap-2 px-3 py-4 text-xs text-[var(--text-muted)]">
 <Loader2 size={12} className="animate-spin" />
 正在加载可切换模型...
 </div>
 ) : configuredProviders.length > 0 ? (
 configuredProviders.map((provider) => {
 const loadedState = providerModels[provider.id];
 const models = loadedState?.models ?? buildFallbackModels(provider.id);
 const isExpanded = expandedProviderId === provider.id;
 const selectedInProvider = provider.id === selectedProviderId;
 const loadedCount = models.length;

 return (
 <div
 key={provider.id}
 className={`mt-1 overflow-hidden rounded-xl border transition-colors ${
 selectedInProvider
 ? "border-[var(--accent-subtle)] bg-[var(--accent-subtle)]/70 shadow-sm"
 : "border-[var(--border-default)] bg-[var(--bg-base)]"
 }`}
 >
 <Button
 variant="ghost"
 type="button"
 onClick={() => handleToggleProvider(provider.id)}
 className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors ${
 isExpanded ? "bg-[var(--bg-elevated)] dark:bg-[var(--bg-overlay)]/50" : ""
 }`}
 >
 <div
 className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl ${
 selectedInProvider
 ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
 : "bg-[var(--accent-subtle)] text-[var(--accent)]"
 }`}
 >
 <Bot size={14} />
 </div>
 <div className="min-w-0 flex-1">
 <div className="flex items-center gap-2">
 <span className="truncate text-sm font-medium text-[var(--text-primary)]">
 {provider.name}
 </span>
 {provider.id === activeProvider?.id ? (
 <span className="rounded-full bg-[var(--accent-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--success)]">
 默认
 </span>
 ) : null}
 {selectedInProvider ? (
 <span className="rounded-full bg-[var(--accent-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--accent)]">
 当前对话
 </span>
 ) : null}
 </div>
 <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
 <span className="truncate">
 {selectedInProvider
 ? selectedModel || provider.current_model || "请选择模型"
 : provider.current_model || "展开后选择模型"}
 </span>
 <span className="text-[var(--text-muted)]">·</span>
 <span className="whitespace-nowrap">
 {loadedState?.loading
 ? "加载中"
 : `${loadedCount || cachedModelCounts[provider.id] || buildFallbackModels(provider.id).length} 个模型`}
 </span>
 </div>
 </div>
 <ChevronDown
 size={14}
 className={`flex-shrink-0 text-[var(--text-muted)] transition-transform ${
 isExpanded ? "rotate-180" : ""
 }`}
 />
 </Button>

 {isExpanded ? (
 <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-2">
 {loadedState?.loading ? (
 <div className="flex items-center gap-2 px-3 py-3 text-xs text-[var(--text-muted)]">
 <Loader2 size={12} className="animate-spin" />
 正在获取 {provider.name} 的模型列表...
 </div>
 ) : models.length > 0 ? (
 <>
 <div className="max-h-60 overflow-y-auto pr-1">
 {models.map((model) => {
 const optionKey = `${provider.id}:${model}`;
 const isSelected =
 provider.id === selectedProviderId &&
 model === selectedModel;

 return (
 <Button
 key={optionKey}
 variant="ghost"
 type="button"
 onClick={() =>
 void handleSelectRoute(provider.id, model)
 }
 disabled={switchingKey !== null}
 className={`mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors ${
 isSelected
 ? "border border-[var(--accent-subtle)] bg-[var(--accent-subtle)] text-[var(--text-primary)] shadow-sm"
 : ""
 }`}
 >
 <div
 className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg ${
 isSelected
 ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
 : "bg-[var(--bg-elevated)] dark:bg-[var(--bg-overlay)] text-[var(--text-secondary)]"
 }`}
 >
 {switchingKey === optionKey ? (
 <Loader2 size={13} className="animate-spin" />
 ) : isSelected ? (
 <Check size={13} />
 ) : (
 <span className="text-[11px] font-semibold">
 {provider.name.slice(0, 1)}
 </span>
 )}
 </div>
 <div className="min-w-0 flex-1">
 <div className="truncate text-sm font-medium">
 {model}
 </div>
 <div
 className={`truncate text-[11px] ${
 isSelected
 ? "text-[var(--text-secondary)]"
 : "text-[var(--text-secondary)]"
 }`}
 >
 {provider.name}
 </div>
 </div>
 {isSelected ? <Check size={14} /> : null}
 </Button>
 );
 })}
 </div>
 {loadedState?.error ? (
 <div className="px-3 pt-2 text-[11px] text-[var(--warning)]">
 模型列表获取失败，当前显示的是已知模型。
 </div>
 ) : null}
 </>
 ) : (
 <div className="px-3 py-3 text-xs text-[var(--text-secondary)]">
 暂未获取到可选模型，请到 AI 设置里检查该供应商配置。
 </div>
 )}
 </div>
 ) : null}
 </div>
 );
 })
 ) : (
 <div className="rounded-xl border border-dashed border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 text-xs text-[var(--text-secondary)]">
 当前还没有可快速切换的已配置模型。
 </div>
 )}
 </div>

 <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-elevated)]/80 dark:bg-[var(--bg-elevated)]/80 p-2">
 <Button
 variant="ghost"
 type="button"
 onClick={() => {
 setMenuOpen(false);
 onOpenSettings?.();
 }}
 className="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm"
 >
 <span className="flex items-center gap-2">
 <Settings2 size={14} className="text-[var(--text-muted)]" />
 管理 AI 设置
 </span>
 <ChevronDown size={14} className="-rotate-90 text-[var(--text-muted)]" />
 </Button>
 </div>
 </div>
 ) : null}
 </div>
 );
}
