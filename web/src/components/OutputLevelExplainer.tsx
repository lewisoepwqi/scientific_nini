/**
 * 输出等级首次解释 —— 当用户首次遇到输出等级徽章时展示。
 * 包含 o1-o4 完整含义说明，关闭后标记已看。
 */
import { useOnboardStore } from "../store/onboard-store";
import { Lightbulb } from "lucide-react";
import Button from "./ui/Button";

const OUTPUT_LEVELS = [
 {
 level: "o1",
 label: "建议级",
 color: "bg-[var(--bg-elevated)] text-[var(--text-secondary)] dark:bg-[var(--bg-overlay)] dark:text-[var(--text-muted)]",
 desc: "仅供参考的初步思路，未经验证",
 },
 {
 level: "o2",
 label: "草稿级",
 color: "bg-[var(--accent-subtle)] text-[var(--domain-profile)]",
 desc: "初步分析结果，可能需要修正",
 },
 {
 level: "o3",
 label: "可审阅级",
 color: "bg-[var(--accent-subtle)] text-[var(--success)] dark:text-[var(--success)]",
 desc: "经过验证的分析结果，建议人工审阅后使用",
 },
 {
 level: "o4",
 label: "可导出级",
 color: "bg-[var(--accent-subtle)] text-[var(--domain-analysis)]",
 desc: "最终成果，可直接用于报告或论文",
 },
] as const;

export default function OutputLevelExplainer() {
 const markSeen = useOnboardStore((s) => s.markSeen);

 return (
 <div className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] p-3 dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)]">
 <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] mb-2">
 <Lightbulb size={12} />
 <span>输出等级说明</span>
 </div>
 <div className="space-y-1.5">
 {OUTPUT_LEVELS.map((item) => (
 <div key={item.level} className="flex items-center gap-2 text-xs">
 <span
 className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${item.color}`}
 >
 {item.level.toUpperCase()} · {item.label}
 </span>
 <span className="text-[var(--text-secondary)]">{item.desc}</span>
 </div>
 ))}
 </div>
 <Button
 type="button"
 variant="ghost"
 onClick={() => markSeen("output_level")}
 className="mt-2 px-2 py-1 text-xs"
 >
 知道了
 </Button>
 </div>
 );
}
