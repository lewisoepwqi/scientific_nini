/**
 * 设置独立页面 —— 侧边导航（AI 配置 / 外观 / 关于）
 *
 * AI 配置区：服务商列表，点击展开内联配置，无子屏跳转。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Bot,
  Check,
  ChevronDown,
  ExternalLink,
  Info,
  Loader2,
  Moon,
  Palette,
  Plug,
  Server,
  Sparkles,
  Sun,
  Trash2,
  Monitor,
  Zap,
  AlertTriangle,
} from "lucide-react";
import { useStore } from "../../store";
import type { ModelProviderInfo } from "../../store/types";
import { deleteProviderConfig } from "../../store/api-actions";
import { ConfirmDialog } from "../ui";
import UpdatePanel from "../UpdatePanel";
import Button from "../ui/Button";
import PageHeader from "./PageHeader";
import { getResolvedTheme, setTheme, type ThemeMode } from "../../theme";

// ---- 导航区段定义 ----
const SECTIONS = [
  { id: "ai", label: "AI 配置", icon: Bot },
  { id: "appearance", label: "外观", icon: Palette },
  { id: "about", label: "关于", icon: Info },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

// ---- 已知模型友好名称映射 ----
const MODEL_DISPLAY_NAMES: Record<string, Record<string, string>> = {
  deepseek: {
    "deepseek-chat": "DeepSeek V3",
    "deepseek-reasoner": "DeepSeek R1",
    "deepseek-coder-v2": "DeepSeek Coder V2",
  },
  zhipu: {
    "glm-4-plus": "GLM-4 Plus",
    "glm-4-flash": "GLM-4 Flash",
    "glm-4-air": "GLM-4 Air",
    "glm-4": "GLM-4",
    "glm-z1-flash": "GLM-Z1 Flash",
  },
  dashscope: {
    "qwen-max": "通义千问 Max",
    "qwen-plus": "通义千问 Plus",
    "qwen-turbo": "通义千问 Turbo",
    "qwen-long": "通义千问 Long",
  },
};

function getModelLabel(providerId: string, modelId: string): string {
  return MODEL_DISPLAY_NAMES[providerId]?.[modelId] ?? modelId;
}

// ---- 服务商视觉标识 ----
const PROVIDER_META: Record<string, { icon: typeof Bot; color: string }> = {
  deepseek: { icon: Zap, color: "var(--accent)" },
  zhipu: { icon: Sparkles, color: "var(--domain-analysis)" },
  dashscope: { icon: Server, color: "var(--domain-cost)" },
  ollama: { icon: Bot, color: "var(--domain-workspace)" },
};

function getProviderMeta(id: string) {
  return PROVIDER_META[id] ?? { icon: Plug, color: "var(--text-muted)" };
}

function getApiModeLabel(apiMode?: string | null): string {
  if (apiMode === "standard") return "普通模式";
  if (apiMode === "coding_plan") return "Coding Plan";
  return "";
}

function getProviderModeBaseUrl(
  providerId: string,
  apiMode: string
): string | null {
  if (providerId === "zhipu") {
    if (apiMode === "standard")
      return "https://open.bigmodel.cn/api/paas/v4/chat/completions";
    if (apiMode === "coding_plan")
      return "https://open.bigmodel.cn/api/coding/paas/v4";
  }
  if (providerId === "dashscope") {
    if (apiMode === "standard")
      return "https://dashscope.aliyuncs.com/compatible-mode/v1";
    if (apiMode === "coding_plan")
      return "https://coding.dashscope.aliyuncs.com/v1";
  }
  return null;
}

// ---- 摘要行：已配置时显示关键信息，未配置时显示描述 ----
function getProviderSummary(p: ModelProviderInfo): string {
  if (!p.configured) return p.description;
  const parts: string[] = [];
  const modeLabel = getApiModeLabel(p.api_mode);
  if (modeLabel) parts.push(modeLabel);
  if (p.current_model && p.id !== "ollama") {
    parts.push(getModelLabel(p.id, p.current_model));
  }
  if (p.id === "ollama" && p.base_url) {
    parts.push(p.base_url);
  }
  return parts.length > 0 ? parts.join(" · ") : p.description;
}

// ---- Props ----
interface Props {
  onBack: () => void;
}

export default function SettingsPage({ onBack }: Props) {
  const [activeSection, setActiveSection] = useState<SectionId>("ai");

  return (
    <div className="h-full flex flex-col">
      <PageHeader title="设置" onBack={onBack} />

      <div className="flex-1 flex min-h-0">
        {/* 左侧导航 */}
        <nav className="w-[180px] flex-shrink-0 border-r border-[var(--border-subtle)] bg-[var(--bg-base)] py-3">
          <div className="space-y-0.5 px-2">
            {SECTIONS.map((section) => {
              const Icon = section.icon;
              const isActive = activeSection === section.id;
              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSection(section.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 text-[13px] rounded-[6px] transition-[background-color,color] duration-100 text-left ${
                    isActive
                      ? "bg-[var(--accent-subtle)] text-[var(--accent)] font-medium"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                  }`}
                >
                  <Icon size={15} className="flex-shrink-0" />
                  {section.label}
                </button>
              );
            })}
          </div>
        </nav>

        {/* 右侧内容区 */}
        <div className="flex-1 overflow-y-auto">
          {activeSection === "ai" && <AIConfigSection />}
          {activeSection === "appearance" && <AppearanceSection />}
          {activeSection === "about" && <AboutSection />}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// AI 配置区 —— 服务商列表 + 手风琴配置
// ============================================================

function AIConfigSection() {
  const modelProviders = useStore((s) => s.modelProviders);
  const fetchModelProviders = useStore((s) => s.fetchModelProviders);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);

  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    void fetchModelProviders();
    void fetchActiveModel();
  }, [fetchModelProviders, fetchActiveModel]);

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const handleConfigSaved = useCallback(() => {
    void fetchModelProviders();
    void fetchActiveModel();
    setExpandedId(null);
    window.dispatchEvent(new Event("nini:model-config-updated"));
  }, [fetchModelProviders, fetchActiveModel]);

  return (
    <div className="max-w-2xl mx-auto px-8 py-8 space-y-4">
      <h2 className="text-[16px] font-semibold text-[var(--text-primary)] leading-tight m-0">
        AI 配置
      </h2>

      <div className="space-y-1">
        {modelProviders.map((p) => (
          <ProviderCard
            key={p.id}
            provider={p}
            isExpanded={expandedId === p.id}
            onToggle={() => toggleExpand(p.id)}
            onSaved={handleConfigSaved}
          />
        ))}
      </div>
    </div>
  );
}

// ---- 服务商卡片 ----

function ProviderCard({
  provider,
  isExpanded,
  onToggle,
  onSaved,
}: {
  provider: ModelProviderInfo;
  isExpanded: boolean;
  onToggle: () => void;
  onSaved: () => void;
}) {
  const meta = getProviderMeta(provider.id);
  const ProviderIcon = meta.icon;
  const summary = getProviderSummary(provider);

  return (
    <div
      className={`rounded-[8px] border transition-[border-color] duration-100 ${
        isExpanded
          ? "border-[var(--border-strong)]"
          : "border-[var(--border-default)]"
      }`}
    >
      {/* 标题行 */}
      <button
        type="button"
        onClick={onToggle}
        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-[background-color] duration-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--accent)] rounded-[8px] ${
          isExpanded
            ? "bg-[var(--bg-elevated)]"
            : "bg-[var(--bg-base)] hover:bg-[var(--bg-hover)]"
        }`}
        aria-expanded={isExpanded}
      >
        {/* 图标 */}
        <div
          className="h-8 w-8 rounded-[6px] flex items-center justify-center flex-shrink-0"
          style={{
            backgroundColor: `color-mix(in srgb, ${meta.color} 12%, transparent)`,
          }}
        >
          <ProviderIcon size={15} style={{ color: meta.color }} />
        </div>

        {/* 名称 + 摘要 */}
        <div className="flex-1 min-w-0">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">
            {provider.name}
          </span>
          <span className="text-[12px] text-[var(--text-muted)] ml-2">
            {summary}
          </span>
        </div>

        {/* 已配置标记 */}
        {provider.configured && !isExpanded && (
          <Check size={14} className="text-[var(--success)] flex-shrink-0" />
        )}

        {/* 展开箭头 */}
        <ChevronDown
          size={14}
          className={`text-[var(--text-muted)] flex-shrink-0 transition-transform duration-150 ${
            isExpanded ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* 展开内容 */}
      {isExpanded && (
        <div className="border-t border-[var(--border-subtle)]">
          <ProviderConfigPanel provider={provider} onSaved={onSaved} />
        </div>
      )}
    </div>
  );
}

// ---- 服务商配置面板 ----

function ProviderConfigPanel({
  provider,
  onSaved,
}: {
  provider: ModelProviderInfo;
  onSaved: () => void;
}) {
  const isOllama = provider.id === "ollama";
  const supportsApiMode = (provider.supported_api_modes?.length ?? 0) > 0;
  const locked =
    provider.configured && provider.can_edit_in_place === false;

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
      const resolvedBaseUrl =
        supportsApiMode && selectedApiMode
          ? getProviderModeBaseUrl(provider.id, selectedApiMode)
          : null;
      const body: Record<string, unknown> = { provider_id: provider.id };
      if (supportsApiMode) body.api_mode = selectedApiMode || undefined;
      if (!isOllama && apiKey.trim()) body.api_key = apiKey.trim();
      if (resolvedBaseUrl) body.base_url = resolvedBaseUrl;
      else if (baseUrl.trim()) body.base_url = baseUrl.trim();

      // 测试连接
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
      if (!testData.success) return;

      // 保存配置
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

  const isSaveDisabled =
    locked ||
    saving ||
    testing ||
    (!isOllama && !apiKey.trim() && !provider.configured) ||
    (supportsApiMode && !selectedApiMode) ||
    (isOllama && !baseUrl.trim());

  const inputCls =
    "w-full max-w-sm h-[28px] rounded-[6px] text-[13px] px-2 bg-[var(--bg-base)] text-[var(--text-primary)] border border-[var(--border-default)] outline-none transition-[border-color,box-shadow] duration-100 placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)]";

  return (
    <div className="px-4 py-4 space-y-3 bg-[var(--bg-elevated)]">
      {/* 锁定提示 */}
      {locked && (
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--warning)]">
          <AlertTriangle size={12} className="flex-shrink-0" />
          <span>配置已锁定，如需修改请先移除后重新配置</span>
        </div>
      )}

      {/* 只读详情（锁定时） */}
      {locked && (
        <div className="space-y-1.5 text-[12px]">
          <InfoRow label="接口模式" value={getApiModeLabel(provider.api_mode)} />
          {!isOllama && (
            <InfoRow label="API Key" value={provider.api_key_hint || "已配置"} mono />
          )}
          <InfoRow label="Base URL" value={provider.base_url || "默认"} />
          <InfoRow label="当前模型" value={provider.current_model || "未选择"} />
        </div>
      )}

      {/* 可编辑表单 */}
      {!locked && (
        <>
          <a
            href={provider.key_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[12px] text-[var(--accent)] hover:underline"
          >
            <ExternalLink size={11} />
            {isOllama
              ? "查看 Ollama 安装教程"
              : `在 ${provider.key_url.replace("https://", "")} 获取密钥`}
          </a>

          {supportsApiMode && (
            <div>
              <label className="text-[11px] text-[var(--text-muted)] mb-1 block">
                接口模式
              </label>
              <div className="flex rounded-[6px] border border-[var(--border-default)] overflow-hidden w-fit">
                {(provider.supported_api_modes ?? []).map((mode, i) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSelectedApiMode(mode)}
                    className={`px-3 py-[5px] text-[12px] font-medium transition-[background-color,color] duration-100 ${
                      i > 0 ? "border-l border-[var(--border-default)]" : ""
                    } ${
                      selectedApiMode === mode
                        ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                        : "bg-[var(--bg-base)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    {getApiModeLabel(mode)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!isOllama && (
            <div>
              <label className="text-[11px] text-[var(--text-muted)] mb-1 block">
                密钥
              </label>
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
                className={inputCls}
              />
            </div>
          )}

          {isOllama && (
            <div>
              <label className="text-[11px] text-[var(--text-muted)] mb-1 block">
                服务器地址
              </label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:11434"
                className={inputCls}
              />
            </div>
          )}
        </>
      )}

      {/* 操作按钮 */}
      <div className="flex items-center gap-2 pt-1">
        <Button
          variant="primary"
          size="sm"
          onClick={() => void handleTestAndSave()}
          disabled={isSaveDisabled}
          loading={saving}
        >
          {testing ? "测试连接中..." : saving ? "保存中..." : "测试并保存"}
        </Button>
        {(provider.configured || locked) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirmRemoveOpen(true)}
            disabled={removing || saving || provider.can_delete_config === false}
            className="text-[var(--error)] hover:text-[var(--error)]"
          >
            {removing ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Trash2 size={12} />
            )}
            {provider.can_delete_config === false ? "环境变量配置" : "移除"}
          </Button>
        )}
      </div>

      {/* 反馈 */}
      {saveError && (
        <p className="text-[11px] text-[var(--error)] m-0">{saveError}</p>
      )}
      {testResult && (
        <p
          className={`text-[11px] m-0 ${
            testResult.success ? "text-[var(--success)]" : "text-[var(--error)]"
          }`}
        >
          {testResult.message}
        </p>
      )}

      <ConfirmDialog
        isOpen={confirmRemoveOpen && provider.can_delete_config !== false}
        onCancel={() => setConfirmRemoveOpen(false)}
        onConfirm={() => void handleRemove()}
        title="确认移除配置"
        description={`确认移除「${provider.name}」配置？移除后如需重新使用需要再次配置。`}
        confirmLabel={removing ? "移除中..." : "确认移除"}
        destructive
      />
    </div>
  );
}

// ---- 通用信息行 ----

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--text-muted)]">{label}</span>
      <span className={`text-[var(--text-primary)] ${mono ? "font-mono text-[11px]" : ""}`}>
        {value}
      </span>
    </div>
  );
}

// ============================================================
// 外观区
// ============================================================

function AppearanceSection() {
  const [currentTheme, setCurrentTheme] = useState<ThemeMode>(() => {
    try {
      const stored = localStorage.getItem("nini-theme");
      if (stored === "light" || stored === "dark" || stored === "system") {
        return stored;
      }
    } catch {
      // localStorage 不可用
    }
    return "system";
  });

  const resolvedTheme = getResolvedTheme();

  const handleThemeChange = (mode: ThemeMode) => {
    setCurrentTheme(mode);
    setTheme(mode);
  };

  const themeOptions: Array<{
    value: ThemeMode;
    label: string;
    description: string;
    icon: typeof Sun;
  }> = [
    { value: "light", label: "浅色", description: "始终使用浅色主题", icon: Sun },
    { value: "dark", label: "深色", description: "始终使用深色主题", icon: Moon },
    {
      value: "system",
      label: "跟随系统",
      description: `当前系统为${resolvedTheme === "dark" ? "深色" : "浅色"}模式`,
      icon: Monitor,
    },
  ];

  return (
    <div className="max-w-lg mx-auto px-8 py-8 space-y-5">
      <h2 className="text-[16px] font-semibold text-[var(--text-primary)] leading-tight m-0">
        外观
      </h2>

      <div>
        <label className="text-[12px] text-[var(--text-secondary)] block font-medium mb-2">
          主题模式
        </label>
        <div className="space-y-1.5">
          {themeOptions.map((opt) => {
            const Icon = opt.icon;
            const isActive = currentTheme === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => handleThemeChange(opt.value)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-[8px] border text-left transition-[background-color,border-color] duration-100 ${
                  isActive
                    ? "border-[var(--accent)] bg-[var(--accent-subtle)]"
                    : "border-[var(--border-default)] hover:bg-[var(--bg-hover)]"
                }`}
              >
                <div
                  className={`h-7 w-7 rounded-[6px] flex items-center justify-center flex-shrink-0 ${
                    isActive ? "bg-[var(--accent)]/15" : "bg-[var(--bg-overlay)]"
                  }`}
                >
                  <Icon
                    size={15}
                    className={isActive ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div
                    className={`text-[13px] ${
                      isActive ? "text-[var(--accent)] font-medium" : "text-[var(--text-primary)]"
                    }`}
                  >
                    {opt.label}
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)]">{opt.description}</div>
                </div>
                {isActive && <Check size={15} className="text-[var(--accent)] flex-shrink-0" />}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 关于区
// ============================================================

function AboutSection() {
  return (
    <div className="max-w-lg mx-auto px-8 py-8 space-y-5">
      <h2 className="text-[16px] font-semibold text-[var(--text-primary)] leading-tight m-0">
        关于
      </h2>

      <div className="rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-9 w-9 rounded-[8px] bg-[var(--accent-subtle)] flex items-center justify-center">
            <Bot size={18} className="text-[var(--accent)]" />
          </div>
          <div>
            <div className="text-[14px] font-semibold text-[var(--text-primary)]">Nini</div>
            <div className="text-[11px] text-[var(--text-muted)]">本地优先的科研 AI 研究伙伴</div>
          </div>
        </div>
        <div className="border-t border-[var(--border-subtle)] pt-3 space-y-2 text-[12px]">
          <InfoRow label="版本" value="见软件更新状态" />
          <InfoRow label="许可" value="开源项目" />
        </div>
      </div>

      <UpdatePanel />

      <p className="text-[12px] text-[var(--text-muted)] leading-relaxed m-0">
        Nini 是一款面向科研人员的 AI 助手，支持数据分析、文献辅助、代码执行等功能。
        所有数据处理均在本地完成，保障科研数据安全。
      </p>
    </div>
  );
}
