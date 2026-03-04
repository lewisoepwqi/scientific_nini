import { isRecord } from "./utils";

export interface NormalizedToolResult {
  message: string;
  status: "success" | "error";
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

export function normalizeToolResult(rawContent: unknown): NormalizedToolResult {
  if (typeof rawContent !== "string" || !rawContent.trim()) {
    return { message: "", status: "success" };
  }

  try {
    const parsed = JSON.parse(rawContent);
    if (isRecord(parsed)) {
      if (typeof parsed.error === "string" && parsed.error) {
        return { message: parsed.error, status: "error" };
      }
      if (parsed.success === false) {
        const msg =
          typeof parsed.message === "string" && parsed.message
            ? parsed.message
            : "工具执行失败";
        return { message: msg, status: "error" };
      }

      const askUserQuestionMessage = formatAskUserQuestionResult(parsed);
      if (askUserQuestionMessage) {
        return { message: askUserQuestionMessage, status: "success" };
      }

      if (typeof parsed.message === "string" && parsed.message) {
        return { message: parsed.message, status: "success" };
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
