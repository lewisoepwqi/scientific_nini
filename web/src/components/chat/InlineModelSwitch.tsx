/**
 * InlineModelSwitch — 输入框工具栏内嵌模型快速切换。
 *
 * 轻量级下拉按钮，显示当前模型简称，点击弹出三档选项。
 * 仅处理 builtin 快速/深度切换 + 已配置供应商的首选模型快速切换。
 * 完整模型管理仍通过 AI 设置面板。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "../../store";
import Button from "../ui/Button";
import {
  Bot,
  Check,
  ChevronDown,
  Loader2,
  Sparkles,
} from "lucide-react";

/* ─── Builtin 两档选项 ─── */
const BUILTIN_OPTIONS = [
  { id: "fast", label: "快速", desc: "更快，适合日常使用" },
  { id: "deep", label: "深度", desc: "更强，适合复杂任务" },
] as const;

/* ─── 组件 ─── */

interface InlineModelSwitchProps {
  onOpenSettings?: () => void;
}

export default function InlineModelSwitch({ onOpenSettings }: InlineModelSwitchProps) {
  const activeModel = useStore((s) => s.activeModel);
  const runtimeModel = useStore((s) => s.runtimeModel);
  const modelFallback = useStore((s) => s.modelFallback);
  const isStreaming = useStore((s) => s.isStreaming);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);
  const fetchModelProviders = useStore((s) => s.fetchModelProviders);
  const modelProviders = useStore((s) => s.modelProviders);
  const setChatRoute = useStore((s) => s.setChatRoute);

  const [menuOpen, setMenuOpen] = useState(false);
  const [switchingKey, setSwitchingKey] = useState<string | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // 初始化加载
  useEffect(() => {
    void fetchActiveModel();
    void fetchModelProviders();
  }, [fetchActiveModel, fetchModelProviders]);

  // 点击外部关闭
  useEffect(() => {
    if (!menuOpen) return;
    const handlePointerDown = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [menuOpen]);

  // 当前显示文本
  const activeProvider = modelProviders.find((p) => p.is_active);
  const effectiveRuntimeModel =
    runtimeModel?.model && (isStreaming || Boolean(modelFallback)) ? runtimeModel : null;
  const displayText =
    effectiveRuntimeModel?.model ||
    activeModel?.model ||
    activeProvider?.current_model ||
    "模型";
  const selectedProviderId = activeModel?.provider_id || activeProvider?.id || null;
  const selectedModel = activeModel?.model || activeProvider?.current_model || null;

  // 已配置的供应商（排除 builtin）
  const configuredProviders = modelProviders.filter((p) => p.configured);

  /** 截断模型名，适合 120px 按钮 */
  const shortName = (() => {
    // builtin 模式显示中文标签
    if (selectedProviderId === "builtin") {
      const opt = BUILTIN_OPTIONS.find((o) => o.id === selectedModel);
      if (opt) return opt.label;
    }
    // 提取短名：取最后一个 / 或 - 后的部分，最长 12 字符
    const raw = displayText || "模型";
    const parts = raw.split(/[/-]/);
    const last = parts[parts.length - 1] || raw;
    return last.length > 12 ? last.slice(0, 11) + "…" : last;
  })();

  const handleToggleMenu = useCallback(() => {
    const next = !menuOpen;
    setMenuOpen(next);
    if (next) {
      void fetchActiveModel();
      void fetchModelProviders();
    }
  }, [menuOpen, fetchActiveModel, fetchModelProviders]);

  const handleSelect = useCallback(
    async (providerId: string, model: string | null) => {
      const key = `${providerId}:${model ?? ""}`;
      setSwitchingKey(key);
      try {
        const success = await setChatRoute(providerId, model);
        if (!success) return;
        window.dispatchEvent(new Event("nini:model-config-updated"));
        setMenuOpen(false);
      } finally {
        setSwitchingKey(null);
      }
    },
    [setChatRoute],
  );

  return (
    <div className="relative" ref={wrapperRef}>
      {/* 触发按钮 */}
      <Button
        variant="secondary"
        onClick={handleToggleMenu}
        className="flex items-center gap-[6px] transition-colors"
        aria-label="快速切换模型"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
      >
        <Bot size={14} className="text-[var(--accent)] shrink-0" />
        <div className="flex items-center">
          <span className="text-[12px] font-medium text-[var(--text-secondary)] leading-[16px] text-center font-['Inter']">{shortName}</span>
        </div>
        <ChevronDown 
          size={12}
          className={`text-[var(--text-muted)] opacity-50 transition-transform ${menuOpen ? "rotate-180" : ""}`} 
        />
      </Button>

      {/* 下拉菜单 */}
      {menuOpen && (
        <div
          className="absolute bottom-[calc(100%+6px)] right-0 z-30 w-[200px] rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] shadow-[0_12px_40px_rgba(15,23,42,0.14)] overflow-hidden"
          role="menu"
        >
          {/* 标题 */}
          <div className="px-3 py-2 text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)] border-b border-[var(--border-subtle)]">
            模型切换
          </div>

          {/* Builtin 选项 */}
          <div className="px-1.5 py-1.5">
            {BUILTIN_OPTIONS.map((option) => {
              const optionKey = `builtin:${option.id}`;
              const isSelected =
                selectedProviderId === "builtin" && selectedModel === option.id;
              const isSwitching = switchingKey === optionKey;

              return (
                <button
                  key={optionKey}
                  onClick={() => void handleSelect("builtin", option.id)}
                  disabled={switchingKey !== null}
                  className="flex w-full items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors hover:bg-[var(--bg-hover)] disabled:opacity-50"
                  role="menuitem"
                >
                  {/* 左侧图标/Check */}
                  <span className="flex-shrink-0 w-4 flex items-center justify-center">
                    {isSwitching ? (
                      <Loader2 size={12} className="animate-spin text-[var(--accent)]" />
                    ) : isSelected ? (
                      <Check size={12} className="text-[var(--accent)]" />
                    ) : (
                      <Sparkles size={12} className="text-[var(--text-muted)]" />
                    )}
                  </span>
                  {/* 文字 */}
                  <div className="min-w-0 flex-1">
                    <div className="text-[12px] font-medium text-[var(--text-primary)]">
                      {option.label}
                    </div>
                    <div className="text-[10px] text-[var(--text-muted)]">{option.desc}</div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* 已配置供应商快速切换（仅显示首选模型） */}
          {configuredProviders.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)] border-t border-[var(--border-subtle)]">
                已配置
              </div>
              <div className="px-1.5 pb-1.5">
                {configuredProviders.slice(0, 3).map((provider) => {
                  const model = provider.current_model;
                  if (!model) return null;
                  const optionKey = `${provider.id}:${model}`;
                  const isSelected =
                    provider.id === selectedProviderId && model === selectedModel;
                  const isSwitching = switchingKey === optionKey;

                  return (
                    <button
                      key={provider.id}
                      onClick={() => void handleSelect(provider.id, model)}
                      disabled={switchingKey !== null}
                      className="flex w-full items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors hover:bg-[var(--bg-hover)] disabled:opacity-50"
                      role="menuitem"
                    >
                      <span className="flex-shrink-0 w-4 flex items-center justify-center">
                        {isSwitching ? (
                          <Loader2 size={12} className="animate-spin text-[var(--accent)]" />
                        ) : isSelected ? (
                          <Check size={12} className="text-[var(--accent)]" />
                        ) : (
                          <Bot size={12} className="text-[var(--text-muted)]" />
                        )}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-[12px] font-medium text-[var(--text-primary)] truncate">
                          {provider.name}
                        </div>
                        <div className="text-[10px] text-[var(--text-muted)] truncate">{model}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {/* 底部：AI 设置 */}
          <div className="border-t border-[var(--border-subtle)] px-1.5 py-1.5">
            <button
              onClick={() => {
                setMenuOpen(false);
                onOpenSettings?.();
              }}
              className="flex w-full items-center gap-2 px-2.5 py-1.5 rounded-lg text-[11px] text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)]"
              role="menuitem"
            >
              <Bot size={11} />
              <span>管理 AI 设置…</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
