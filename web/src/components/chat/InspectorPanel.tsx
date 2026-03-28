/**
 * InspectorPanel —— 右侧 Inspector，对话页 DetailPanel 的内容实例。
 *
 * 设计规范：.impeccable.md Chat Components §InspectorPanel
 * 三个 section：Task Progress / References & Documents / Task Health
 */
import {
 FileText,
 FileSpreadsheet,
 File,
 ClipboardList,
 Activity,
 BookOpen,
 Circle,
} from "lucide-react";
import { useStore } from "../../store";
import TaskTree from "./TaskTree";

/** 文件类型 → 图标颜色映射 */
function fileTypeIcon(name: string) {
 const ext = name.split(".").pop()?.toLowerCase();
 if (ext === "csv" || ext === "xlsx" || ext === "tsv") {
 return <FileSpreadsheet size={16} style={{ color: "var(--success)" }} />;
 }
 if (ext === "pdf") {
 return <FileText size={16} style={{ color: "var(--error)" }} />;
 }
 return <File size={16} style={{ color: "var(--text-muted)" }} />;
}

export default function InspectorPanel() {
 const analysisPlanProgress = useStore((s) => s.analysisPlanProgress);
 const analysisTasks = useStore((s) => s.analysisTasks);
 const harnessRunContext = useStore((s) => s.harnessRunContext);
 const completionCheck = useStore((s) => s.completionCheck);
 const blockedState = useStore((s) => s.blockedState);

 // 收集引用文件名
 const referencedFiles = harnessRunContext?.datasets?.map((d) => d.name) ?? [];

 return (
 <div className="flex flex-col h-full">
 {/* Section 1 — Task Progress */}
 <section className="px-4 py-3 border-b border-[var(--border-subtle)]">
 <div className="flex items-center gap-2 mb-2">
 <ClipboardList size={14} style={{ color: "var(--accent)" }} />
 <h3 className="text-sm font-medium text-[var(--text-primary)]">
 任务进度
 </h3>
 </div>
 <TaskTree plan={analysisPlanProgress} tasks={analysisTasks} />
 </section>

 {/* Section 2 — References & Documents */}
 <section className="px-4 py-3 border-b border-[var(--border-subtle)]">
 <div className="flex items-center gap-2 mb-2">
 <BookOpen size={14} style={{ color: "var(--domain-knowledge)" }} />
 <h3 className="text-sm font-medium text-[var(--text-primary)]">
 引用与文档
 </h3>
 </div>
 {referencedFiles.length === 0 ? (
 <div className="flex flex-col items-center py-4 text-[var(--text-muted)]">
 <Circle size={20} className="mb-1" />
 <span className="text-xs">尚未引用文件</span>
 </div>
 ) : (
 <div className="space-y-0.5">
 {referencedFiles.map((name) => (
 <div
 key={name}
 className="flex h-9 items-center gap-2 px-2 rounded hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
 >
 {fileTypeIcon(name)}
 <span className="text-[13px] text-[var(--text-primary)] truncate">
 {name}
 </span>
 </div>
 ))}
 </div>
 )}
 </section>

 {/* Section 3 — Task Health */}
 <section className="px-4 py-3">
 <div className="flex items-center gap-2 mb-2">
 <Activity size={14} style={{ color: "var(--domain-analysis)" }} aria-hidden="true" />
 <h3 className="text-sm font-medium text-[var(--text-primary)]">
 任务健康
 </h3>
 </div>
 {!blockedState && !completionCheck && analysisTasks.length === 0 ? (
 <div className="flex flex-col items-center py-4 text-[var(--text-muted)]">
 <Circle size={20} className="mb-1" />
 <span className="text-xs">暂无运行数据</span>
 </div>
 ) : (
 <div className="space-y-2 text-xs">
 {blockedState && (
 <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-overlay)] p-2">
 <div className="font-medium text-[var(--warning)]">阻塞中</div>
 <div className="mt-1 text-[var(--text-secondary)]">
 {blockedState.message ?? blockedState.reasonCode ?? "未知原因"}
 </div>
 {blockedState.suggestedAction && (
 <div className="mt-1 text-[var(--text-muted)]">
 建议：{blockedState.suggestedAction}
 </div>
 )}
 </div>
 )}
 {completionCheck && (
 <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-overlay)] p-2">
 <div className="font-medium text-[var(--text-secondary)]">完成检查</div>
 <div className="mt-1 text-[var(--text-muted)]">
 {completionCheck.passed ? "已通过" : "未通过"}（第 {completionCheck.attempt} 次检查）
 </div>
 </div>
 )}
 {analysisTasks.length > 0 && (
 <div className="text-[var(--text-muted)]">
 共 {analysisTasks.length} 个任务，
 {analysisTasks.filter((t) => t.status === "done").length} 已完成
 </div>
 )}
 </div>
 )}
 </section>
 </div>
 );
}
