import { describe, expect, it, vi } from "vitest";

import { runDeferredUiUpdate } from "./app-transitions";

describe("runDeferredUiUpdate", () => {
  it("应调用预加载器并执行更新", async () => {
    const steps: string[] = [];
    const preload = vi.fn(async () => {
      steps.push("preload");
    });
    const update = vi.fn(() => {
      steps.push("update");
    });

    runDeferredUiUpdate(update, preload);
    await Promise.resolve();

    expect(preload).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
    expect(steps).toContain("preload");
    expect(steps).toContain("update");
  });

  it("预加载失败时也应继续执行更新", async () => {
    const preload = vi.fn(async () => {
      throw new Error("load failed");
    });
    const update = vi.fn();

    runDeferredUiUpdate(update, preload);
    await Promise.resolve();

    expect(preload).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
  });
});
