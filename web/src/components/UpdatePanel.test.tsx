import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UpdatePanel from "./UpdatePanel";
import { useUpdateStore } from "../store/update";

describe("UpdatePanel", () => {
  beforeEach(() => {
    useUpdateStore.setState({
      check: {
        current_version: "0.1.1",
        latest_version: "0.1.2",
        update_available: true,
        important: true,
        status: "available",
        notes: ["更新"],
        asset_size: 1024,
        error: null,
      },
      download: {
        status: "idle",
        progress: 0,
        downloaded_bytes: 0,
        total_bytes: null,
        installer_path: null,
        verified: false,
        error: null,
      },
      dialogOpen: false,
      busy: false,
      error: null,
    });
  });

  it("展示更新信息并触发下载", () => {
    const downloadUpdate = vi.fn();
    useUpdateStore.setState({ downloadUpdate });

    render(<UpdatePanel />);
    expect(screen.getByText(/可更新到 0.1.2/u)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /下载更新/u }));

    expect(downloadUpdate).toHaveBeenCalled();
  });
});
