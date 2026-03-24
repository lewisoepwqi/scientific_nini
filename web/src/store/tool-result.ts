import { isRecord } from "./utils";
import type { GeneratedWidgetPayload } from "./types";

/**
 * 资源引用信息（新资源系统）
 */
export interface ToolResultResourceRef {
  resource_id: string;
  resource_type: string;
  name: string;
}

export interface NormalizedToolResult {
  message: string;
  status: "success" | "error";
  /**
   * 工具执行创建或更新的资源引用
   * 用于新资源系统追踪资源生命周期
   */
  resourceRef?: ToolResultResourceRef;
  widget?: GeneratedWidgetPayload;
}

function extractWidgetPayload(
  toolName: string | undefined,
  parsed: Record<string, unknown>,
): GeneratedWidgetPayload | undefined {
  if (toolName !== "generate_widget") {
    return undefined;
  }

  const data = isRecord(parsed.data) ? parsed.data : null;
  if (!data) return undefined;

  const title = typeof data.title === "string" ? data.title : "";
  const html = typeof data.html === "string" ? data.html : "";
  if (!title.trim() || !html.trim()) {
    return undefined;
  }

  return {
    title,
    html,
    description: typeof data.description === "string" ? data.description : null,
  };
}

function formatAskUserQuestionResult(parsed: Record<string, unknown>): string | null {
  const data = isRecord(parsed.data) ? parsed.data : null;
  if (!data) return null;

  const rawQuestions = Array.isArray(data.questions) ? data.questions : [];
  const rawAnswers = isRecord(data.answers) ? data.answers : null;
  if (rawQuestions.length === 0 || !rawAnswers) return null;

  const lines: string[] = [];

  rawQuestions.forEach((item, index) => {
    if (!isRecord(item)) return;

    const question =
      typeof item.question === "string" ? item.question.trim() : "";
    const header = typeof item.header === "string" ? item.header.trim() : "";
    const fallbackLabel = header || question || `问题 ${index + 1}`;
    const answerCandidates = [question, header].filter(
      (value): value is string => typeof value === "string" && value.trim() !== "",
    );

    let answer = "";
    for (const key of answerCandidates) {
      const value = rawAnswers[key];
      if (typeof value === "string" && value.trim()) {
        answer = value.trim();
        break;
      }
    }
    if (!answer) return;

    // 先展示问题，再展示用户回答
    if (header && question) {
      // header 和 question 都存在且不同时，都展示
      if (header !== question) {
        lines.push(`${header}：${question}`);
      } else {
        lines.push(`${question}`);
      }
    } else {
      lines.push(`${fallbackLabel}`);
    }
    lines.push(`→ ${answer}`);

    // 多个问题之间加空行分隔
    if (index < rawQuestions.length - 1) {
      lines.push("");
    }
  });

  return lines.length > 0 ? lines.join("\n") : null;
}

/**
 * 从工具结果中提取资源引用信息
 * 支持新资源系统的 resource_id / resource_type 字段
 */
function extractResourceRef(parsed: Record<string, unknown>): ToolResultResourceRef | undefined {
  const data = isRecord(parsed.data) ? parsed.data : parsed;
  if (!data) return undefined;

  const resourceId = typeof data.resource_id === "string" ? data.resource_id : undefined;
  const resourceType = typeof data.resource_type === "string" ? data.resource_type : undefined;
  const name = typeof data.name === "string" ? data.name : resourceId;

  if (resourceId && resourceType) {
    return { resource_id: resourceId, resource_type: resourceType, name: name || resourceId };
  }
  return undefined;
}

export function normalizeToolResult(
  rawContent: unknown,
  toolName?: string,
): NormalizedToolResult {
  if (typeof rawContent !== "string" || !rawContent.trim()) {
    return { message: "", status: "success" };
  }

  try {
    const parsed = JSON.parse(rawContent);
    if (isRecord(parsed)) {
      // 提取资源引用信息
      const resourceRef = extractResourceRef(parsed);
      const widget = extractWidgetPayload(toolName, parsed);

      if (typeof parsed.error === "string" && parsed.error) {
        return { message: parsed.error, status: "error", resourceRef, widget };
      }
      if (parsed.success === false) {
        const msg =
          typeof parsed.message === "string" && parsed.message
            ? parsed.message
            : "工具执行失败";
        return { message: msg, status: "error", resourceRef, widget };
      }

      const askUserQuestionMessage = formatAskUserQuestionResult(parsed);
      if (askUserQuestionMessage) {
        return { message: askUserQuestionMessage, status: "success", resourceRef, widget };
      }

      if (typeof parsed.message === "string" && parsed.message) {
        return { message: parsed.message, status: "success", resourceRef, widget };
      }

      if (widget) {
        return {
          message: `已生成内嵌组件：${widget.title}`,
          status: "success",
          resourceRef,
          widget,
        };
      }

      // 如果有资源引用但没有 message，生成默认消息
      if (resourceRef) {
        return {
          message: `${resourceRef.resource_type} 资源已创建: ${resourceRef.name}`,
          status: "success",
          resourceRef,
          widget,
        };
      }
    }
  } catch {
    // 保持原始文本
  }

  const isError =
    rawContent.startsWith("错误:") ||
    rawContent.startsWith("Error:") ||
    rawContent.toLowerCase().includes("exception");
  return { message: rawContent, status: isError ? "error" : "success" };
}
