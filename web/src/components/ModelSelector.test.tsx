import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ModelSelector from "./ModelSelector";

let mockState: Record<string, unknown>;

vi.mock("../store", () => ({
  useStore: (selector: (state: Record<string, unknown>) => unknown) => selector(mockState),
}));

describe("ModelSelector", () => {
  beforeEach(() => {
    mockState = {
      activeModel: {
        provider_id: "zhipu",
        provider_name: "智谱 GLM",
        model: "glm-5",
        preferred_provider: "zhipu",
      },
      runtimeModel: null,
      modelFallback: null,
      isStreaming: false,
      fetchActiveModel: vi.fn().mockResolvedValue(undefined),
      fetchModelProviders: vi.fn().mockResolvedValue(undefined),
      modelProviders: [],
      modelProvidersLoading: false,
      setChatRoute: vi.fn().mockResolvedValue(true),
    };
  });

  it("空闲且无降级时应显示用户选择的模型", () => {
    render(<ModelSelector />);

    expect(screen.getByRole("button", { name: "快速切换模型" })).toHaveTextContent("glm-5");
  });

  it("发生降级后即使流式结束也应显示实际运行模型", () => {
    mockState = {
      ...mockState,
      runtimeModel: {
        provider_id: "deepseek",
        provider_name: "DeepSeek",
        model: "deepseek-chat",
        preferred_provider: "zhipu",
      },
      modelFallback: {
        purpose: "planning",
        attempt: 2,
        to_provider_id: "deepseek",
        to_provider_name: "DeepSeek",
        to_model: "deepseek-chat",
        occurred_at: Date.now(),
      },
    };

    render(<ModelSelector />);

    expect(screen.getByRole("button", { name: "快速切换模型" })).toHaveTextContent(
      "deepseek-chat",
    );
  });
});
