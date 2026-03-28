import type { PendingAskUserQuestion } from "../store";
import Button from "./ui/Button";

interface PendingQuestionBannerProps {
 pending: PendingAskUserQuestion;
 additionalCount: number;
 canEnableNotifications: boolean;
 onSwitch: () => void;
 onEnableNotifications: () => void;
}

export default function PendingQuestionBanner({
 pending,
 additionalCount,
 canEnableNotifications,
 onSwitch,
 onEnableNotifications,
}: PendingQuestionBannerProps) {
 return (
 <div className="border-b border-[var(--warning)] bg-[var(--accent-subtle)]/80 px-4 py-3">
 <div className="mx-auto flex max-w-3xl flex-col gap-3 rounded-2xl border border-[var(--warning)] bg-[var(--bg-base)] px-4 py-3 shadow-sm md:flex-row md:items-center md:justify-between">
 <div className="min-w-0">
 <div className="text-sm font-semibold text-[var(--warning)]">
 会话“{pending.sessionTitle}”正在等待你的回答
 </div>
 <div className="mt-1 text-xs text-[var(--warning)]">
 回答后会自动继续执行。
 {additionalCount > 0 ? ` 另有 ${additionalCount} 个会话待处理。` : ""}
 </div>
 </div>
 <div className="flex flex-wrap items-center gap-2">
 {canEnableNotifications && (
 <Button
 type="button"
 variant="secondary"
 onClick={onEnableNotifications}
 className="rounded-xl px-3 py-1.5 text-xs"
 >
 启用系统通知
 </Button>
 )}
 <Button
 type="button"
 variant="primary"
 onClick={onSwitch}
 className="rounded-xl px-3 py-1.5 text-xs"
 >
 切换并处理
 </Button>
 </div>
 </div>
 </div>
 );
}
