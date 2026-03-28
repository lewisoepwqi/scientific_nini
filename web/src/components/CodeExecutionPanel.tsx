/**
 * 代码执行历史面板 —— 垂直时间线样式，可折叠步骤卡片。
 *
 * 参考 Figma Make ExecutionHistory 组件，
 * 所有颜色使用 .impeccable.md CSS token。
 */
import { useEffect, useCallback, useState } from "react";
import { useStore, type CodeExecution } from "../store";
import {
  Copy,
  Check,
  AlertCircle,
  CheckCircle,
  Terminal,
  RotateCcw,
  FileCode,
  BarChart3,
  FileText,
  Database,
  Image,
  Code,
  BookOpen,
  Hash,
  Cpu,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import Button from "./ui/Button";

/** 工具显示名映射 */
const TOOL_NAME_DISPLAY: Record<string, string> = {
  task_state: "任务状态",
  dataset_catalog: "数据目录",
  dataset_transform: "数据转换",
  stat_test: "统计检验",
  stat_model: "统计建模",
  stat_interpret: "统计解读",
  chart_session: "图表会话",
  report_session: "报告会话",
  workspace_session: "工作区会话",
  code_session: "代码会话",
  run_code: "代码执行",
  run_r_code: "R代码执行",
  create_chart: "创建图表",
  generate_report: "生成报告",
  export_report: "导出报告",
  fetch_url: "网页获取",
  image_analysis: "图像分析",
  load_dataset: "加载数据",
  preview_data: "数据预览",
  data_summary: "数据摘要",
  clean_data: "数据清洗",
};

/** 工具 → 图标 + 域色 token 映射 */
const TOOL_ICON_MAP: Record<
  string,
  { icon: React.ElementType; color: string }
> = {
  // 统计类 → domain-analysis
  stat_test: { icon: BarChart3, color: "var(--domain-analysis)" },
  stat_model: { icon: BarChart3, color: "var(--domain-analysis)" },
  stat_interpret: { icon: Hash, color: "var(--domain-analysis)" },
  // 图表 → domain-analysis
  chart_session: { icon: Image, color: "var(--domain-analysis)" },
  create_chart: { icon: Image, color: "var(--domain-analysis)" },
  // 代码执行 → domain-analysis
  code_session: { icon: FileCode, color: "var(--domain-analysis)" },
  run_code: { icon: FileCode, color: "var(--domain-analysis)" },
  run_r_code: { icon: FileCode, color: "var(--domain-analysis)" },
  // 报告 → domain-report
  report_session: { icon: FileText, color: "var(--domain-report)" },
  generate_report: { icon: FileText, color: "var(--domain-report)" },
  export_report: { icon: FileText, color: "var(--domain-report)" },
  // 工作区 → domain-workspace
  workspace_session: { icon: Database, color: "var(--domain-workspace)" },
  // 知识库 → domain-knowledge
  fetch_url: { icon: BookOpen, color: "var(--domain-knowledge)" },
  // 数据 → domain-profile
  load_dataset: { icon: Database, color: "var(--domain-profile)" },
  preview_data: { icon: FileText, color: "var(--domain-profile)" },
  data_summary: { icon: Hash, color: "var(--domain-profile)" },
  clean_data: { icon: Cpu, color: "var(--domain-profile)" },
  // 图像 → domain-cost
  image_analysis: { icon: Image, color: "var(--domain-cost)" },
};

function getToolIcon(toolName?: string) {
  if (!toolName) return { icon: Cpu, color: "var(--text-muted)" };
  return TOOL_ICON_MAP[toolName] ?? { icon: Code, color: "var(--text-secondary)" };
}

function getToolDisplayName(toolName?: string): string {
  if (!toolName) return "代码执行";
  return TOOL_NAME_DISPLAY[toolName] ?? toolName;
}

type Tone = "accent" | "success" | "warning" | "error";

function toneToken(tone: Tone): string {
  switch (tone) {
    case "success":
      return "var(--success)";
    case "warning":
      return "var(--warning)";
    case "error":
      return "var(--error)";
    default:
      return "var(--accent)";
  }
}

function toneSurfaceStyle(tone: Tone, weight = 10) {
  return {
    backgroundColor: `color-mix(in srgb, ${toneToken(tone)} ${weight}%, var(--bg-base))`,
  };
}

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

/** 复制按钮 */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 回退方案
    }
  }, [text]);

  return (
    <Button
      variant="ghost"
      onClick={handleCopy}
      className="p-0.5 rounded"
      title="复制"
      aria-label="复制"
    >
      {copied ? (
        <Check size={12} className="text-[var(--success)]" />
      ) : (
        <Copy size={12} className="text-[var(--text-muted)]" />
      )}
    </Button>
  );
}

/** 状态图标 —— 16px，圆形背景 var(--bg-elevated) */
function StatusIcon({ status }: { status: string }) {
  const isError = status === "error";
  const isRunning = status === "running";

  return (
    <div
      className={`w-6 h-6 rounded-full border flex items-center justify-center flex-shrink-0 z-10 ${
        isError ? "border-[var(--error)]" : "border-[var(--border-default)]"
      }`}
      style={isError ? toneSurfaceStyle("error", 12) : { backgroundColor: "var(--bg-elevated)" }}
    >
      {isRunning ? (
        <Loader2 size={16} className="text-[var(--accent)] animate-spin" />
      ) : isError ? (
        <AlertCircle size={16} className="text-[var(--error)]" />
      ) : (
        <CheckCircle size={16} className="text-[var(--success)]" />
      )}
    </div>
  );
}

/** 单条执行步骤（时间线卡片） */
function ExecutionItem({ exec }: { exec: CodeExecution }) {
  const [expanded, setExpanded] = useState(false);
  const [argsExpanded, setArgsExpanded] = useState(false);
  const isError = exec.status === "error";
  const isRetry = !!exec.retry_of_execution_id;
  const { icon: ToolIcon, color: toolColor } = getToolIcon(exec.tool_name);
  const cardStyle = isError ? toneSurfaceStyle("error", 8) : undefined;
  const headerStyle = isError ? toneSurfaceStyle("error", 10) : undefined;

  return (
    <div className="flex gap-3 items-start">
      {/* 左侧：时间轴线 + 状态图标 */}
      <div className="flex-shrink-0 flex flex-col items-center w-6 pt-1.5">
        <StatusIcon status={exec.status} />
        {/* 竖线由父级统一渲染 */}
      </div>

      {/* 右侧：步骤卡片 */}
      <div
        className={`flex-1 min-w-0 rounded-md border overflow-hidden mb-1 shadow-sm ${
          isError ? "border-[var(--error)]" : "border-[var(--border-default)]"
        }`}
        style={cardStyle}
      >
        {/* 头部行：点击折叠/展开 */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className={`w-full flex items-center gap-2 px-3 h-9 text-left transition-colors cursor-pointer ${
            isError ? "hover:opacity-90" : "hover:bg-[var(--bg-hover)]"
          }`}
          style={headerStyle}
        >
          <ToolIcon
            size={14}
            className="flex-shrink-0"
            style={{ color: toolColor }}
          />
          <span className="text-xs font-medium text-[var(--text-primary)] truncate">
            {getToolDisplayName(exec.tool_name)}
          </span>
          {exec.language && (
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              ({exec.language})
            </span>
          )}
          {isRetry && (
            <RotateCcw
              size={10}
              className="text-[var(--accent)] flex-shrink-0"
              aria-label="重试执行"
            />
          )}
          {exec.context_token_count != null && (
            <span
              className="text-[10px] text-[var(--text-muted)]"
              title="执行时上下文 Token 数"
            >
              {exec.context_token_count.toLocaleString()} tok
            </span>
          )}
          <span className="text-[10px] text-[var(--text-muted)] ml-auto flex-shrink-0">
            {formatTime(exec.created_at)}
          </span>
          {expanded ? (
            <ChevronUp size={14} className="text-[var(--text-muted)] flex-shrink-0" />
          ) : (
            <ChevronDown size={14} className="text-[var(--text-muted)] flex-shrink-0" />
          )}
        </button>

        {/* 展开的内容 */}
        {expanded && (
          <div className="border-t border-[var(--border-default)]">
            {/* 工具参数 */}
            {exec.tool_args && Object.keys(exec.tool_args).length > 0 && (
              <div className="border-b border-[var(--border-default)]">
                <button
                  onClick={() => setArgsExpanded((v) => !v)}
                  className="w-full flex items-center gap-1 px-3 py-1 bg-[var(--bg-elevated)] text-[10px] text-[var(--text-muted)] font-medium hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
                >
                  <span>{argsExpanded ? "▼" : "▶"}</span>
                  <span>TOOL ARGS</span>
                </button>
                {argsExpanded && (
                  <pre className="text-[11px] font-mono px-3 py-2 overflow-x-auto bg-[var(--bg-elevated)] text-[var(--text-secondary)] max-h-32 overflow-y-auto">
                    {JSON.stringify(exec.tool_args, null, 2)}
                  </pre>
                )}
              </div>
            )}

            {/* 脚本资源 */}
            {exec.script_resource_id && (
              <div
                className="px-3 py-1.5 border-b border-[var(--border-default)] text-[10px] text-[var(--domain-analysis)] flex items-center gap-2"
                style={toneSurfaceStyle("accent", 9)}
              >
                <span className="font-medium">脚本资源：</span>
                <code className="px-1.5 py-0.5 rounded bg-[var(--bg-base)]/75">
                  {exec.script_resource_id}
                </code>
              </div>
            )}

            {/* 输出资源 */}
            {exec.output_resource_ids && exec.output_resource_ids.length > 0 && (
              <div
                className="px-3 py-1.5 border-b border-[var(--border-default)] text-[10px] text-[var(--success)] flex items-center gap-2"
                style={toneSurfaceStyle("success", 9)}
              >
                <span className="font-medium">输出资源：</span>
                <div className="flex gap-1 flex-wrap">
                  {exec.output_resource_ids.map((id) => (
                    <code
                      key={id}
                      className="px-1.5 py-0.5 rounded bg-[var(--bg-base)]/75"
                    >
                      {id}
                    </code>
                  ))}
                </div>
              </div>
            )}

            {/* 重试信息 */}
            {isRetry && exec.retry_of_execution_id && (
              <div
                className="px-3 py-1.5 border-b border-[var(--border-default)] text-[10px] text-[var(--accent)] flex items-center gap-2"
                style={toneSurfaceStyle("accent", 10)}
              >
                <RotateCcw size={10} />
                <span>重试于执行记录：</span>
                <code className="px-1.5 py-0.5 rounded bg-[var(--bg-base)]/75">
                  {exec.retry_of_execution_id.slice(0, 8)}...
                </code>
              </div>
            )}

            {/* 错误定位 */}
            {isError && exec.error_location && (
              <div
                className="px-3 py-1.5 border-b border-[var(--error)] text-[10px] text-[var(--error)]"
                style={toneSurfaceStyle("error", 14)}
              >
                <span className="font-medium">错误位置：</span>
                <span>第 {exec.error_location.line} 行</span>
                {exec.error_location.column && (
                  <span>，第 {exec.error_location.column} 列</span>
                )}
              </div>
            )}

            {/* 恢复提示 */}
            {isError && exec.recovery_hint && (
              <div
                className="px-3 py-1.5 border-b border-[var(--warning)] text-[10px] text-[var(--warning)]"
                style={toneSurfaceStyle("warning", 12)}
              >
                <span className="font-medium">恢复建议：</span>
                <span>{exec.recovery_hint}</span>
              </div>
            )}

            {/* 执行意图 */}
            {exec.intent && (
              <div
                className="px-3 py-2 border-b border-[var(--border-default)] text-[11px] text-[var(--accent)]"
                style={toneSurfaceStyle("accent", 9)}
              >
                <span className="font-medium">执行意图：</span>
                <span>{exec.intent}</span>
              </div>
            )}

            {/* 请求（代码） */}
            {exec.code && (
              <div className="relative">
                <div className="flex items-center justify-between px-3 py-1 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
                  <span className="text-[10px] text-[var(--text-muted)] font-medium">
                    REQUEST
                  </span>
                  <CopyButton text={exec.code} />
                </div>
                <pre className="text-xs font-mono px-3 py-2 overflow-x-auto bg-[var(--bg-elevated)] text-[var(--text-secondary)] max-h-[200px] overflow-y-auto">
                  {exec.code}
                </pre>
              </div>
            )}

            {/* 响应（输出） */}
            {exec.output && (
              <div className="relative border-t border-[var(--border-default)]">
                <div className="flex items-center justify-between px-3 py-1 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
                  <span
                    className={`text-[10px] font-medium ${
                      isError
                        ? "text-[var(--error)]"
                        : "text-[var(--text-muted)]"
                    }`}
                  >
                    RESPONSE
                  </span>
                </div>
                <pre
                  className={`text-xs font-mono px-3 py-2 overflow-x-auto max-h-[200px] overflow-y-auto whitespace-pre-wrap break-words ${
                    isError
                      ? "text-[var(--error)]"
                      : "bg-[var(--bg-base)] text-[var(--text-secondary)]"
                  }`}
                  style={isError ? toneSurfaceStyle("error", 12) : undefined}
                >
                  {exec.output}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CodeExecutionPanel() {
  const sessionId = useStore((s) => s.sessionId);
  const codeExecutions = useStore((s) => s.codeExecutions);
  const fetchCodeExecutions = useStore((s) => s.fetchCodeExecutions);

  useEffect(() => {
    if (sessionId) {
      fetchCodeExecutions();
    }
  }, [sessionId, fetchCodeExecutions]);

  if (codeExecutions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-[var(--text-muted)] text-xs px-4">
        <Terminal size={24} className="mb-2 opacity-50" />
        <p>暂无执行历史</p>
        <p className="text-[10px] mt-1">代码执行记录将显示在此处</p>
      </div>
    );
  }

  return (
    <div className="px-3 py-2">
      {/* 步骤计数 */}
      <div className="flex items-center justify-between px-1 py-1 mb-2">
        <span className="text-[11px] text-[var(--text-muted)]">
          共 {codeExecutions.length} 步执行记录
        </span>
      </div>

      {/* 垂直时间线 */}
      <div className="relative">
        {/* 时间轴竖线：2px，var(--border-default) */}
        <div
          className="absolute left-[11px] top-6 bottom-4 w-0.5"
          style={{ background: "var(--border-default)" }}
        />

        {/* 步骤列表 */}
        <div className="flex flex-col">
          {codeExecutions.map((exec) => (
            <ExecutionItem key={exec.id} exec={exec} />
          ))}
        </div>
      </div>
    </div>
  );
}
