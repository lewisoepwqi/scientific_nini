import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RecipeCenter from "./RecipeCenter";

const sendMessage = vi.fn();
let mockState: Record<string, unknown>;

vi.mock("../store", () => ({
  useStore: (
    selector: (
      state: Record<string, unknown>,
    ) => unknown,
  ) => selector(mockState),
}));

describe("RecipeCenter", () => {
  beforeEach(() => {
    sendMessage.mockReset();
    mockState = {
      recipesLoaded: true,
      isStreaming: false,
      sendMessage,
      recipes: [
        {
          recipe_id: "literature_review",
          name: "文献综述提纲",
          summary: "快速生成综述提纲。",
          scenario: "适合开题前梳理研究现状。",
          example_input: "帮我围绕肠道菌群做综述提纲",
          recommended_triggers: ["文献综述"],
          input_fields: [
            {
              key: "topic",
              label: "研究主题",
              required: true,
              placeholder: "请输入主题",
              example: "肠道菌群与抑郁症",
            },
          ],
          steps: [
            { id: "1", title: "明确范围", description: "定义边界" },
            { id: "2", title: "规划检索", description: "整理关键词" },
            { id: "3", title: "输出提纲", description: "形成写作结构" },
          ],
          default_outputs: [{ id: "outline", label: "综述提纲", type: "markdown" }],
          recovery: { max_retries: 1, user_hint: "缩小范围", fallback_action: "补充边界" },
        },
      ],
    };
  });

  it("点击模板启动时应携带 recipe 元数据调用 sendMessage", () => {
    render(<RecipeCenter />);

    fireEvent.change(screen.getByPlaceholderText("请输入主题"), {
      target: { value: "肠道菌群与抑郁症" },
    });
    fireEvent.click(screen.getByRole("button", { name: "以模板启动" }));

    expect(sendMessage).toHaveBeenCalledWith(
      expect.stringContaining("文献综述提纲"),
      {
        recipeId: "literature_review",
        recipeInputs: { topic: "肠道菌群与抑郁症" },
      },
    );
  });
});
