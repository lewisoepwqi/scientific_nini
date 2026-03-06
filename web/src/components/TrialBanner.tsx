/**
 * 试用状态横幅组件。
 * - 试用剩余 > 3 天：灰色中性提示
 * - 试用剩余 ≤ 3 天：黄色警告
 * - 已配置自有密钥 / 试用到期：不渲染（到期由 trial_expired 事件处理）
 */
import { useEffect, useState } from "react";
import { AlertTriangle, Clock, X } from "lucide-react";

interface TrialStatus {
  activated: boolean;
  days_remaining: number;
  expired: boolean;
  has_own_key: boolean;
}

interface Props {
  onOpenSettings?: () => void;
}

export default function TrialBanner({ onOpenSettings }: Props) {
  const [status, setStatus] = useState<TrialStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const fetchStatus = async () => {
    try {
      const resp = await fetch("/api/trial/status");
      const data = await resp.json();
      if (data.success) {
        setStatus(data.data as TrialStatus);
      }
    } catch {
      // 静默失败
    }
  };

  useEffect(() => {
    void fetchStatus();
    // 每 60 秒刷新一次（防止跨天时状态过期）
    const interval = setInterval(() => void fetchStatus(), 60_000);
    return () => clearInterval(interval);
  }, []);

  // 监听配置更新事件，刷新横幅状态
  useEffect(() => {
    const handler = () => void fetchStatus();
    window.addEventListener("nini:model-config-updated", handler);
    return () => window.removeEventListener("nini:model-config-updated", handler);
  }, []);

  if (
    dismissed ||
    !status ||
    status.has_own_key ||          // 已配置自有密钥：不显示
    !status.activated ||           // 未激活：不显示（首次消息前）
    status.expired                 // 已到期：由阻断提示处理
  ) {
    return null;
  }

  const isWarning = status.days_remaining <= 3;

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 text-xs ${
        isWarning
          ? "bg-amber-50 border-b border-amber-200 text-amber-700"
          : "bg-gray-50 border-b border-gray-200 text-gray-500"
      }`}
    >
      {isWarning ? (
        <AlertTriangle size={13} className="text-amber-500 flex-shrink-0" />
      ) : (
        <Clock size={13} className="text-gray-400 flex-shrink-0" />
      )}

      <span className="flex-1">
        {isWarning ? (
          <>
            <span className="font-medium">试用将在 {status.days_remaining} 天后到期</span>
            ，建议现在配置自己的密钥
          </>
        ) : (
          <>试用中 · 剩余 {status.days_remaining} 天</>
        )}
      </span>

      {onOpenSettings && (
        <button
          onClick={onOpenSettings}
          className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
            isWarning
              ? "bg-amber-100 hover:bg-amber-200 text-amber-700"
              : "bg-gray-200 hover:bg-gray-300 text-gray-600"
          }`}
        >
          配置密钥
        </button>
      )}

      <button
        onClick={() => setDismissed(true)}
        className="p-0.5 rounded hover:bg-black/5 flex-shrink-0"
        aria-label="关闭"
      >
        <X size={12} />
      </button>
    </div>
  );
}
