import { describe, expect, it } from "vitest";
import {
  getWsStatusMeta,
  resolveWsClosedStatus,
  type WsConnectionStatus,
} from "./websocket-status";

describe("websocket-status", () => {
  it("关闭后在可见页面且仍可重试时应进入重连中状态", () => {
    expect(resolveWsClosedStatus(3, 10, false)).toBe("reconnecting");
  });

  it("重试耗尽后应进入失败状态，而不是继续显示连接中", () => {
    expect(resolveWsClosedStatus(10, 10, false)).toBe("failed");
  });

  it("页面隐藏时应标记为未连接，等待重新可见后重连", () => {
    expect(resolveWsClosedStatus(2, 10, true)).toBe("disconnected");
  });

  it.each([
    ["connecting", "连接中..."],
    ["connected", "已连接"],
    ["reconnecting", "重连中..."],
    ["disconnected", "未连接"],
    ["failed", "连接已断开"],
  ] satisfies Array<[WsConnectionStatus, string]>)(
    "应为 %s 提供准确文案",
    (status, label) => {
      expect(getWsStatusMeta(status).label).toBe(label);
    },
  );
});
