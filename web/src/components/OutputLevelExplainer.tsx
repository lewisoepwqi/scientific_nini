/**
 * 输出等级首次解释 —— 当用户首次遇到输出等级徽章时展示。
 * 包含 o1-o4 完整含义说明，关闭后标记已看。
 */
import { useOnboardStore } from "../store/onboard-store";
import { Lightbulb } from "lucide-react";

const OUTPUT_LEVELS = [
  {
    level: "o1",
    label: "建议级",
    color: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400",
    desc: "仅供参考的初步思路，未经验证",
  },
  {
    level: "o2",
    label: "草稿级",
    color: "bg-sky-50 text-sky-700 dark:bg-sky-900/20 dark:text-sky-400",
    desc: "初步分析结果，可能需要修正",
  },
  {
    level: "o3",
    label: "可审阅级",
    color: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400",
    desc: "经过验证的分析结果，建议人工审阅后使用",
  },
  {
    level: "o4",
    label: "可导出级",
    color: "bg-violet-50 text-violet-700 dark:bg-violet-900/20 dark:text-violet-400",
    desc: "最终成果，可直接用于报告或论文",
  },
] as const;

export default function OutputLevelExplainer() {
  const markSeen = useOnboardStore((s) => s.markSeen);

  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-600 dark:bg-slate-800">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
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
            <span className="text-slate-500 dark:text-slate-400">{item.desc}</span>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => markSeen("output_level")}
        className="mt-2 rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200 transition-colors"
      >
        知道了
      </button>
    </div>
  );
}
