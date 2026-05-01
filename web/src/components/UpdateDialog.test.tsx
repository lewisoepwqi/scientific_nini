import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UpdateDialog from "./UpdateDialog";
import { useStore } from "../store";
import { useUpdateStore } from "../store/update";

describe("UpdateDialog", () => {
  beforeEach(() => {
    useStore.setState({ runningSessions: new Set<string>() });
    useUpdateStore.setState({
      check: {
        current_version: "0.1.1",
        latest_version: "0.1.2",
        update_available: true,
        important: true,
        status: "available",
        notes: ["修复问题"],
        asset_size: 1024,
        error: null,
      },
      download: {
        status: "ready",
        version: "0.1.2",
        progress: 100,
        downloaded_bytes: 1024,
        total_bytes: 1024,
        installer_path: "setup.exe",
        verified: true,
        error: null,
      },
      dialogOpen: true,
      checking: false,
      downloading: false,
      applying: false,
      error: null,
    });
  });

  it("verifying 状态显示正在校验文案", () => {
    useUpdateStore.setState({
      download: {
        status: "verifying",
        progress: 95,
        downloaded_bytes: 50000000,
        total_bytes: 52428800,
        installer_path: null,
        verified: false,
        error: null,
      },
    });

    render(<UpdateDialog />);
    expect(screen.getByText("正在校验…")).toBeInTheDocument();
  });

  it("ready 状态允许启动升级", () => {
    const applyUpdate = vi.fn();
    useUpdateStore.setState({ applyUpdate });

    render(<UpdateDialog />);
    fireEvent.click(screen.getByRole("button", { name: /立即重启并升级/u }));

    expect(applyUpdate).toHaveBeenCalled();
  });

  it("任务运行中禁止升级", () => {
    useStore.setState({ runningSessions: new Set(["session-1"]) });

    render(<UpdateDialog />);

    expect(screen.getByText(/暂不能重启升级/u)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /立即重启并升级/u })).toBeDisabled();
  });
});
