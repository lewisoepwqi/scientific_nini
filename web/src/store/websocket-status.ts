/**
 * WebSocket 连接状态工具。
 */

export type WsConnectionStatus =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "failed";

export function resolveWsClosedStatus(
  attempts: number,
  maxAttempts: number,
  hidden: boolean,
): WsConnectionStatus {
  if (hidden) return "disconnected";
  if (attempts < maxAttempts) return "reconnecting";
  return "failed";
}

export function getWsStatusMeta(status: WsConnectionStatus): {
  label: string;
  tone: "success" | "progress" | "warning" | "danger" | "muted";
} {
  switch (status) {
    case "connected":
      return { label: "已连接", tone: "success" };
    case "connecting":
      return { label: "连接中...", tone: "progress" };
    case "reconnecting":
      return { label: "重连中...", tone: "warning" };
    case "failed":
      return { label: "连接已断开", tone: "danger" };
    case "disconnected":
    default:
      return { label: "未连接", tone: "muted" };
  }
}
