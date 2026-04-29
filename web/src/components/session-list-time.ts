import type { SessionItem } from "../store/types";

export function getSessionActivityIso(session: SessionItem): string | undefined {
  return session.last_message_at || session.updated_at || session.created_at;
}

export function formatSessionRelativeTime(iso?: string, nowMs = Date.now()): string {
  if (!iso) return "";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "";
  const deltaMs = Math.max(0, nowMs - ts);
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (deltaMs < minute) return "此刻";
  if (deltaMs < hour) return `${Math.max(1, Math.floor(deltaMs / minute))}分钟前`;
  if (deltaMs < day) return "今天";
  if (deltaMs < 2 * day) return "昨天";
  if (deltaMs < 7 * day) return `${Math.floor(deltaMs / day)}天前`;
  const dt = new Date(ts);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(
    dt.getDate(),
  ).padStart(2, "0")}`;
}
