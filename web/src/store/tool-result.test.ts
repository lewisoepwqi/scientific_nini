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

  it("ask_user_question 结果应优先展示选项 description，并保留多题结果", () => {
    const normalized = normalizeToolResult(
      JSON.stringify({
        success: true,
        data: {
          questions: [
            {
              question: "你更关注哪类结果？",
              header: "分析偏好",
              options: [
                { label: "effect_size", description: "效应量与置信区间" },
                { label: "p_value", description: "显著性检验结果" },
              ],
            },
            {
              question: "是否导出图表？",
              header: "输出格式",
              options: [
                { label: "svg", description: "导出 SVG 矢量图" },
                { label: "png", description: "导出 PNG 位图" },
              ],
              multiSelect: true,
            },
          ],
          answers: {
            "你更关注哪类结果？": "effect_size",
            "是否导出图表？": "svg, png",
          },
        },
      }),
      "ask_user_question",
    );

    expect(normalized.status).toBe("success");
    expect(normalized.message).toContain("分析偏好：你更关注哪类结果？");
    expect(normalized.message).toContain("→ 效应量与置信区间");
    expect(normalized.message).toContain("输出格式：是否导出图表？");
    expect(normalized.message).toContain("→ 导出 SVG 矢量图");
    expect(normalized.message).toContain("→ 导出 PNG 位图");
    expect(normalized.message).not.toContain("→ effect_size");
    expect(normalized.message).not.toContain("→ svg, png");
  });
});
