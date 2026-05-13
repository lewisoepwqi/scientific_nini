import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SessionTabs from "./SessionTabs";

// mock store
const mockState = {
  sessionId: "s1",
  openTabIds: ["s1", "s2"],
  tabTitles: { s1: "文献综述", s2: "数据分析" },
  runningSessions: new Set<string>(),
  switchSession: vi.fn(),
  closeTab: vi.fn(),
};

vi.mock("../store", () => ({
  useStore: (selector: (s: typeof mockState) => unknown) => selector(mockState),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SessionTabs", () => {
  it("渲染两个 Tab", () => {
    render(<SessionTabs />);
    expect(screen.getByText("文献综述")).toBeTruthy();
    expect(screen.getByText("数据分析")).toBeTruthy();
  });

  it("openTabIds 为空时不渲染", () => {
    mockState.openTabIds = [];
    const { container } = render(<SessionTabs />);
    expect(container.firstChild).toBeNull();
    mockState.openTabIds = ["s1", "s2"];
  });

  it("活跃 Tab aria-selected=true，非活跃 false", () => {
    render(<SessionTabs />);
    const tabs = screen.getAllByRole("tab");
    const active = tabs.find((t) => t.textContent?.includes("文献综述"))!;
    const inactive = tabs.find((t) => t.textContent?.includes("数据分析"))!;
    expect(active.getAttribute("aria-selected")).toBe("true");
    expect(inactive.getAttribute("aria-selected")).toBe("false");
  });

  it("点击非活跃 Tab 调用 switchSession", () => {
    render(<SessionTabs />);
    const tabs = screen.getAllByRole("tab");
    const inactive = tabs.find((t) => t.textContent?.includes("数据分析"))!;
    fireEvent.click(inactive);
    expect(mockState.switchSession).toHaveBeenCalledWith("s2");
  });

  it("点击活跃 Tab 不调用 switchSession", () => {
    render(<SessionTabs />);
    const tabs = screen.getAllByRole("tab");
    const active = tabs.find((t) => t.textContent?.includes("文献综述"))!;
    fireEvent.click(active);
    expect(mockState.switchSession).not.toHaveBeenCalled();
  });

  it("点击关闭按钮调用 closeTab 并阻止切换会话", () => {
    render(<SessionTabs />);
    const closeBtn = screen.getByRole("button", { name: /关闭 文献综述/ });
    fireEvent.click(closeBtn);
    expect(mockState.closeTab).toHaveBeenCalledWith("s1");
    expect(mockState.switchSession).not.toHaveBeenCalled();
  });
});
