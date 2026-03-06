/**
 * 模型选择器 —— 简化版。
 * 显示当前激活供应商和已选主模型，点击跳转 AI 设置面板。
 * 不再展示多供应商并排下拉列表。
 */
import { useEffect } from "react";
import { useStore } from "../store";
import { Bot, ChevronDown } from "lucide-react";

interface ModelSelectorProps {
  compact?: boolean;
  onOpenSettings?: () => void;
}

export default function ModelSelector({
  compact = false,
  onOpenSettings,
}: ModelSelectorProps) {
  const activeModel = useStore((s) => s.activeModel);
  const runtimeModel = useStore((s) => s.runtimeModel);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);
  const modelProviders = useStore((s) => s.modelProviders);

  useEffect(() => {
    void fetchActiveModel();
  }, [fetchActiveModel]);

  // 监听配置更新，刷新显示
  useEffect(() => {
    const handler = () => void fetchActiveModel();
    window.addEventListener("nini:model-config-updated", handler);
    return () => window.removeEventListener("nini:model-config-updated", handler);
  }, [fetchActiveModel]);

  // 显示文字：优先运行时实际模型，其次激活模型，再次试用提示
  const activeProvider = modelProviders.find((p) => p.is_active);
  const displayText =
    runtimeModel?.model ||
    activeModel?.model ||
    (activeProvider ? activeProvider.current_model : null) ||
    "试用中";

  const triggerClass = compact
    ? "h-8 px-2.5 text-xs"
    : "px-2.5 py-1 text-xs";

  return (
    <button
      onClick={onOpenSettings}
      className={`flex items-center gap-1.5 rounded-2xl hover:bg-gray-100 transition-colors border border-gray-200 text-gray-600 ${triggerClass}`}
      title="AI 设置"
      aria-label="AI 设置"
    >
      <Bot size={13} className="text-blue-500 flex-shrink-0" />
      <span className="truncate max-w-[120px]">{displayText}</span>
      <ChevronDown size={12} className="text-gray-400" />
    </button>
  );
}
