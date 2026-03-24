import { describe, expect, it } from "vitest";

import { normalizeToolResult } from "./tool-result";

describe("normalizeToolResult", () => {
  it("generate_widget 应提取结构化组件数据", () => {
    const normalized = normalizeToolResult(
      JSON.stringify({
        success: true,
        data: {
          title: "统计摘要卡",
          html: "<section>demo</section>",
          description: "展示核心指标",
        },
      }),
      "generate_widget",
    );

    expect(normalized.status).toBe("success");
    expect(normalized.message).toBe("已生成内嵌组件：统计摘要卡");
    expect(normalized.widget).toEqual({
      title: "统计摘要卡",
      html: "<section>demo</section>",
      description: "展示核心指标",
    });
  });
});
