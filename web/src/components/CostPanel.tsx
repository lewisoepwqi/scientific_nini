/**
 * CostPanel - Token 消耗与成本展示面板
 *
 * 显示当前会话的实时 Token 使用量、预估成本
 * 以及历史成本统计信息。
 */
import { useEffect, useState } from "react";
import { useStore, type TokenUsage, type AggregateCostSummary, type ModelTokenUsage } from "../store";
import {
  Coins,
  X,
  TrendingUp,
  Calculator,
  Clock,
  BarChart3,
} from "lucide-react";

interface CostPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function CostPanel({ isOpen, onClose }: CostPanelProps) {
  const sessionId = useStore((s) => s.sessionId);
  const tokenUsage = useStore((s) => s.tokenUsage);
  const aggregateCost = useStore((s) => s.aggregateCost);
  const fetchTokenUsage = useStore((s) => s.fetchTokenUsage);
  const fetchCostHistory = useStore((s) => s.fetchCostHistory);

  const [activeTab, setActiveTab] = useState<"current" | "history">("current");

  // 定期刷新 Token 使用数据
  useEffect(() => {
    if (!isOpen || !sessionId) return;

    // 立即获取一次
    void fetchTokenUsage(sessionId);
    void fetchCostHistory();

    // 每 10 秒刷新一次
    const interval = setInterval(() => {
      void fetchTokenUsage(sessionId);
      void fetchCostHistory();
    }, 10000);

    return () => clearInterval(interval);
  }, [isOpen, sessionId, fetchTokenUsage, fetchCostHistory]);

  if (!isOpen) return null;

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat("zh-CN").format(num);
  };

  const formatCost = (cost: number) => {
    if (cost < 0.01) return "< 0.01";
    return cost.toFixed(4);
  };

  return (
    <div className="fixed inset-y-0 right-0 w-80 bg-white dark:bg-gray-900 shadow-xl border-l border-gray-200 dark:border-gray-700 z-50 flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <Coins className="w-5 h-5 text-amber-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            成本统计
          </h2>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 标签页切换 */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab("current")}
          className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "current"
              ? "text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
          }`}
        >
          当前会话
        </button>
        <button
          onClick={() => setActiveTab("history")}
          className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "history"
              ? "text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
          }`}
        >
          历史统计
        </button>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "current" ? (
          <CurrentSessionTab
            tokenUsage={tokenUsage}
            formatNumber={formatNumber}
            formatCost={formatCost}
          />
        ) : (
          <HistoryTab
            aggregateCost={aggregateCost}
            formatNumber={formatNumber}
            formatCost={formatCost}
          />
        )}
      </div>

      {/* 底部提示 */}
      <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
          成本为估算值，仅供参考
        </p>
      </div>
    </div>
  );
}

// 当前会话标签页
function CurrentSessionTab({
  tokenUsage,
  formatNumber,
  formatCost,
}: {
  tokenUsage: TokenUsage | null;
  formatNumber: (num: number) => string;
  formatCost: (cost: number) => string;
}) {
  if (!tokenUsage || tokenUsage.total_tokens === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        <Calculator className="w-12 h-12 mb-3 opacity-50" />
        <p className="text-sm">暂无 Token 使用数据</p>
        <p className="text-xs mt-1 opacity-70">开始对话后将自动统计</p>
      </div>
    );
  }

  const modelBreakdown = Object.values(tokenUsage.model_breakdown || {});

  return (
    <div className="space-y-4">
      {/* 总览卡片 */}
      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-xl p-4 border border-blue-100 dark:border-blue-800">
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
            预估成本
          </span>
        </div>
        <div className="text-2xl font-bold text-blue-700 dark:text-blue-300">
          ¥{formatCost(tokenUsage.estimated_cost_cny)}
        </div>
        <div className="text-xs text-blue-600/70 dark:text-blue-400/70 mt-1">
          ${formatCost(tokenUsage.estimated_cost_usd)} USD
        </div>
      </div>

      {/* Token 统计 */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard
          label="输入 Tokens"
          value={formatNumber(tokenUsage.input_tokens)}
          icon={<BarChart3 className="w-4 h-4" />}
        />
        <StatCard
          label="输出 Tokens"
          value={formatNumber(tokenUsage.output_tokens)}
          icon={<BarChart3 className="w-4 h-4" />}
        />
        <StatCard
          label="总 Tokens"
          value={formatNumber(tokenUsage.total_tokens)}
          icon={<Calculator className="w-4 h-4" />}
          className="col-span-2"
        />
      </div>

      {/* 模型使用详情 */}
      {modelBreakdown.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-500" />
            模型使用详情
          </h3>
          <div className="space-y-2">
            {modelBreakdown.map((model: ModelTokenUsage) => (
              <div
                key={model.model_id}
                className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-sm"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-gray-700 dark:text-gray-300">
                    {model.model_id}
                  </span>
                  <span className="text-xs text-gray-500">
                    {model.call_count} 次调用
                  </span>
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                  <div className="flex justify-between">
                    <span>Tokens:</span>
                    <span>{formatNumber(model.total_tokens)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>成本:</span>
                    <span>¥{formatCost(model.cost_cny)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// 历史统计标签页
function HistoryTab({
  aggregateCost,
  formatNumber,
  formatCost,
}: {
  aggregateCost: AggregateCostSummary | null;
  formatNumber: (num: number) => string;
  formatCost: (cost: number) => string;
}) {
  if (!aggregateCost || aggregateCost.total_sessions === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        <Clock className="w-12 h-12 mb-3 opacity-50" />
        <p className="text-sm">暂无历史数据</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 总览卡片 */}
      <div className="bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 rounded-xl p-4 border border-amber-100 dark:border-amber-800">
        <div className="flex items-center gap-2 mb-2">
          <Coins className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <span className="text-sm font-medium text-amber-900 dark:text-amber-100">
            累计成本
          </span>
        </div>
        <div className="text-2xl font-bold text-amber-700 dark:text-amber-300">
          ¥{formatCost(aggregateCost.total_cost_cny)}
        </div>
        <div className="text-xs text-amber-600/70 dark:text-amber-400/70 mt-1">
          ${formatCost(aggregateCost.total_cost_usd)} USD
        </div>
      </div>

      {/* 统计网格 */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard
          label="总会话数"
          value={formatNumber(aggregateCost.total_sessions)}
          icon={<Calculator className="w-4 h-4" />}
        />
        <StatCard
          label="平均成本/会话"
          value={`¥${formatCost(aggregateCost.average_cost_per_session)}`}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatCard
          label="总 Tokens"
          value={formatNumber(aggregateCost.total_tokens)}
          icon={<BarChart3 className="w-4 h-4" />}
        />
        <StatCard
          label="输入/输出"
          value={`${formatNumber(aggregateCost.total_input_tokens)} / ${formatNumber(
            aggregateCost.total_output_tokens
          )}`}
          icon={<BarChart3 className="w-4 h-4" />}
        />
      </div>

      {/* 最常用模型 */}
      {aggregateCost.most_used_model && (
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 border border-blue-100 dark:border-blue-800">
          <div className="text-xs text-blue-600 dark:text-blue-400 mb-1">
            最常用模型
          </div>
          <div className="font-medium text-blue-900 dark:text-blue-100">
            {aggregateCost.most_used_model}
          </div>
        </div>
      )}
    </div>
  );
}

// 统计卡片组件
function StatCard({
  label,
  value,
  icon,
  className = "",
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-gray-50 dark:bg-gray-800 rounded-lg p-3 border border-gray-100 dark:border-gray-700 ${className}`}
    >
      <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400 mb-1">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <div className="text-base font-semibold text-gray-900 dark:text-gray-100">
        {value}
      </div>
    </div>
  );
}
