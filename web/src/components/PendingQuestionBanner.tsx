import type { PendingAskUserQuestion } from "../store";

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
    <div className="border-b border-amber-200 dark:border-amber-800 bg-amber-50/80 dark:bg-amber-900/15 px-4 py-3">
      <div className="mx-auto flex max-w-3xl flex-col gap-3 rounded-2xl border border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-800 px-4 py-3 shadow-sm md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-amber-800">
            会话“{pending.sessionTitle}”正在等待你的回答
          </div>
          <div className="mt-1 text-xs text-amber-700">
            回答后会自动继续执行。
            {additionalCount > 0 ? ` 另有 ${additionalCount} 个会话待处理。` : ""}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEnableNotifications && (
            <button
              type="button"
              onClick={onEnableNotifications}
              className="rounded-xl border border-amber-200 bg-amber-100 px-3 py-1.5 text-xs font-medium text-amber-800 transition-colors hover:bg-amber-200"
            >
              启用系统通知
            </button>
          )}
          <button
            type="button"
            onClick={onSwitch}
            className="rounded-xl bg-amber-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-amber-600"
          >
            切换并处理
          </button>
        </div>
      </div>
    </div>
  );
}
