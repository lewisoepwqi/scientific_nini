import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WidgetRenderer from "./WidgetRenderer";

const sendMessage = vi.fn();

vi.mock("../store", () => ({
 useStore: (selector: (state: { sendMessage: typeof sendMessage }) => unknown) =>
 selector({ sendMessage }),
}));

describe("WidgetRenderer", () => {
 beforeEach(() => {
 sendMessage.mockReset();
 });

 it("仅在 html 变化时写入 iframe srcdoc", () => {
 const srcdocSetter = vi.fn();
 const srcdocGetter = vi.fn(() => "");
 Object.defineProperty(HTMLIFrameElement.prototype, "srcdoc", {
 configurable: true,
 get: srcdocGetter,
 set: srcdocSetter,
 });

 const { rerender } = render(
 <WidgetRenderer title="统计摘要卡" html="<section>alpha</section>" />,
 );

 rerender(<WidgetRenderer title="统计摘要卡" html="<section>alpha</section>" />);
 rerender(<WidgetRenderer title="统计摘要卡" html="<section>beta</section>" />);

 expect(srcdocSetter).toHaveBeenCalledTimes(2);
 });

 it("收到 iframe 高度消息后应更新高度", () => {
 render(<WidgetRenderer title="统计摘要卡" html="<section>alpha</section>" />);

 const iframe = screen.getByTitle("统计摘要卡") as HTMLIFrameElement;
 const iframeWindow = {};
 Object.defineProperty(iframe, "contentWindow", {
 configurable: true,
 value: iframeWindow,
 });

 act(() => {
 window.dispatchEvent(
 new MessageEvent("message", {
 source: iframeWindow as MessageEventSource,
 data: { type: "iframe-height", height: 360 },
 }),
 );
 });

 expect(iframe.style.height).toBe("360px");
 });

 it("收到 send-prompt 消息后应转发到现有发送接口", () => {
 render(<WidgetRenderer title="统计摘要卡" html="<section>alpha</section>" />);

 const iframe = screen.getByTitle("统计摘要卡") as HTMLIFrameElement;
 const iframeWindow = {};
 Object.defineProperty(iframe, "contentWindow", {
 configurable: true,
 value: iframeWindow,
 });

 act(() => {
 window.dispatchEvent(
 new MessageEvent("message", {
 source: iframeWindow as MessageEventSource,
 data: { type: "send-prompt", text: "深入分析这个变量" },
 }),
 );
 });

 expect(sendMessage).toHaveBeenCalledWith("深入分析这个变量");
 });
});
