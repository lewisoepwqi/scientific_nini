/**
 * CostPanel - Token 消耗与成本展示面板
 *
 * 使用 DetailPanel 基础组件（推入式面板，无遮罩）。
 * 显示当前会话的实时 Token 使用量、预估成本以及历史成本统计信息。
 */
import { useEffect, useState } from "react";
import { useStore, type TokenUsage, type AggregateCostSummary, type ModelTokenUsage } from "../store";
import {
 Coins,
 TrendingUp,
 Calculator,
 Clock,
 BarChart3,
} from "lucide-react";
import { DetailPanel } from "./ui";
import Button from "./ui/Button";

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

 useEffect(() => {
 if (!isOpen || !sessionId) return;
 void fetchTokenUsage(sessionId);
 void fetchCostHistory();
 const interval = setInterval(() => {
 void fetchTokenUsage(sessionId);
 void fetchCostHistory();
 }, 10000);
 return () => clearInterval(interval);
 }, [isOpen, sessionId, fetchTokenUsage, fetchCostHistory]);

 const formatNumber = (num: number) => new Intl.NumberFormat("zh-CN").format(num);

 const formatCost = (cost: number) => {
 if (cost === 0) return "0.00";
 if (cost < 0.0001) return "< 0.0001";
 if (cost < 0.01) return cost.toFixed(4);
 return cost.toFixed(2);
 };

 return (
 <DetailPanel isOpen={isOpen} onClose={onClose} title="成本统计">
 {/* 标签页切换 */}
 <div role="tablist" aria-label="成本统计" className="flex" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
 <Button
 variant="ghost"
 type="button"
 role="tab"
 aria-selected={activeTab === "current"}
 aria-controls="cost-panel-current"
 id="cost-tab-current"
 onClick={() => setActiveTab("current")}
 className={`flex-1 px-4 py-2 text-[12px] font-medium ${
 activeTab === "current"
 ? "text-[var(--accent)] border-b-2 border-[var(--accent)]"
 : "text-[var(--text-secondary)]"
 }`}
 >
 当前会话
 </Button>
 <Button
 variant="ghost"
 type="button"
 role="tab"
 aria-selected={activeTab === "history"}
 aria-controls="cost-panel-history"
 id="cost-tab-history"
 onClick={() => setActiveTab("history")}
 className={`flex-1 px-4 py-2 text-[12px] font-medium ${
 activeTab === "history"
 ? "text-[var(--accent)] border-b-2 border-[var(--accent)]"
 : "text-[var(--text-secondary)]"
 }`}
 >
 历史统计
 </Button>
 </div>

 {/* 内容 */}
 <div
 role="tabpanel"
 aria-labelledby={`cost-tab-${activeTab}`}
 id={`cost-panel-${activeTab}`}
 className="flex-1 overflow-y-auto p-4"
 >
 {activeTab === "current" ? (
 <CurrentSessionTab tokenUsage={tokenUsage} formatNumber={formatNumber} formatCost={formatCost} />
 ) : (
 <HistoryTab aggregateCost={aggregateCost} formatNumber={formatNumber} formatCost={formatCost} />
 )}
 </div>

 {/* 底部提示 */}
 <div className="px-4 py-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
 <p className="text-[11px] text-[var(--text-muted)] text-center">
 成本为估算值，仅供参考
 </p>
 </div>
 </DetailPanel>
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
 <div className="flex flex-col items-center justify-center h-64 text-[var(--text-muted)]">
 <Calculator className="w-12 h-12 mb-3 opacity-50" />
 <p className="text-[13px]">暂无 Token 使用数据</p>
 <p className="text-[11px] mt-1 opacity-70">开始对话后将自动统计</p>
 </div>
 );
 }

 const modelBreakdown = Object.values(tokenUsage.model_breakdown || {});

 return (
 <div className="space-y-4">
 {/* 总览卡片 */}
 <div className="bg-[var(--accent-subtle)] rounded-lg p-4 border border-[var(--border-subtle)]">
 <div className="flex items-center gap-2 mb-2">
 <TrendingUp className="w-4 h-4 text-[var(--accent)]" />
 <span className="text-[12px] font-medium text-[var(--text-primary)]">预估成本</span>
 </div>
 <div className="text-2xl font-bold text-[var(--accent)]">
 ¥{formatCost(tokenUsage.estimated_cost_cny)}
 </div>
 <div className="text-[11px] text-[var(--text-muted)] mt-1">
 ${formatCost(tokenUsage.estimated_cost_usd)} USD
 </div>
 </div>

 {/* Token 统计 */}
 <div className="grid grid-cols-2 gap-3">
 <StatCard label="输入 Tokens" value={formatNumber(tokenUsage.input_tokens)} icon={<BarChart3 className="w-4 h-4" />} />
 <StatCard label="输出 Tokens" value={formatNumber(tokenUsage.output_tokens)} icon={<BarChart3 className="w-4 h-4" />} />
 <StatCard label="总 Tokens" value={formatNumber(tokenUsage.total_tokens)} icon={<Calculator className="w-4 h-4" />} className="col-span-2" />
 </div>

 {/* 模型使用详情 */}
 {modelBreakdown.length > 0 && (
 <div className="mt-4">
 <h3 className="text-[12px] font-medium text-[var(--text-primary)] mb-3 flex items-center gap-2">
 <Clock className="w-4 h-4 text-[var(--text-muted)]" />
 模型使用详情
 </h3>
 <div className="space-y-2">
 {modelBreakdown.map((model: ModelTokenUsage) => (
 <div key={model.model_id} className="bg-[var(--bg-elevated)] rounded-lg p-3 text-[12px]">
 <div className="flex items-center justify-between mb-1">
 <span className="font-medium text-[var(--text-primary)]">{model.model_id}</span>
 <span className="text-[11px] text-[var(--text-secondary)]">{model.call_count} 次调用</span>
 </div>
 <div className="text-[11px] text-[var(--text-muted)] space-y-1">
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
 <div className="flex flex-col items-center justify-center h-64 text-[var(--text-muted)]">
 <Clock className="w-12 h-12 mb-3 opacity-50" />
 <p className="text-[13px]">暂无历史数据</p>
 </div>
 );
 }

 return (
 <div className="space-y-4">
 {/* 总览 */}
 <div className="bg-[var(--bg-elevated)] rounded-lg p-4 border border-[var(--border-subtle)]">
 <div className="flex items-center gap-2 mb-2">
 <Coins className="w-4 h-4 text-[var(--warning)]" />
 <span className="text-[12px] font-medium text-[var(--text-primary)]">累计成本</span>
 </div>
 <div className="text-2xl font-bold text-[var(--warning)]">
 ¥{formatCost(aggregateCost.total_cost_cny)}
 </div>
 <div className="text-[11px] text-[var(--text-muted)] mt-1">
 ${formatCost(aggregateCost.total_cost_usd)} USD
 </div>
 </div>

 {/* 统计网格 */}
 <div className="grid grid-cols-2 gap-3">
 <StatCard label="总会话数" value={formatNumber(aggregateCost.total_sessions)} icon={<Calculator className="w-4 h-4" />} />
 <StatCard label="平均成本/会话" value={`¥${formatCost(aggregateCost.average_cost_per_session)}`} icon={<TrendingUp className="w-4 h-4" />} />
 <StatCard label="总 Tokens" value={formatNumber(aggregateCost.total_tokens)} icon={<BarChart3 className="w-4 h-4" />} />
 <StatCard label="输入/输出" value={`${formatNumber(aggregateCost.total_input_tokens)} / ${formatNumber(aggregateCost.total_output_tokens)}`} icon={<BarChart3 className="w-4 h-4" />} />
 </div>

 {/* 最常用模型 */}
 {aggregateCost.most_used_model && (
 <div className="bg-[var(--accent-subtle)] rounded-lg p-3 border border-[var(--border-subtle)]">
 <div className="text-[11px] text-[var(--accent)] mb-1">最常用模型</div>
 <div className="font-medium text-[13px] text-[var(--text-primary)]">
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
 <div className={`bg-[var(--bg-elevated)] rounded-lg p-3 border border-[var(--border-subtle)] ${className}`}>
 <div className="flex items-center gap-1.5 text-[var(--text-muted)] mb-1">
 {icon}
 <span className="text-[11px]">{label}</span>
 </div>
 <div className="text-[14px] font-semibold text-[var(--text-primary)]">
 {value}
 </div>
 </div>
 );
}
