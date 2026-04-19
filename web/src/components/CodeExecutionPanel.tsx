/**
 * 代码档案面板 —— 聚焦 run_code / run_r_code 记录，支持单条与批量下载。
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
  BarChart3,
  Package,
  Wrench,
  Search,
  Download,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import Button from "./ui/Button";
import { downloadSingleBundle, downloadBatchBundle } from "./downloadBundle";

/** purpose → 图标 + 中文前缀 + 域色 token */
const PURPOSE_META: Record<
  string,
  { icon: React.ElementType; label: string; color: string }
> = {
  visualization: { icon: BarChart3, label: "图表", color: "var(--domain-analysis)" },
  export: { icon: Package, label: "导出", color: "var(--domain-report)" },
  transformation: { icon: Wrench, label: "数据转换", color: "var(--domain-profile)" },
  exploration: { icon: Search, label: "探索分析", color: "var(--domain-analysis)" },
};

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

function getCardTitle(exec: CodeExecution): {
  prefix: string;
  intent: string;
  Icon: React.ElementType;
  color: string;
} {
  const purpose = String((exec.tool_args as any)?.purpose || "exploration");
  const meta = PURPOSE_META[purpose] ?? PURPOSE_META.exploration;
  const intent =
    exec.intent?.trim() ||
    (exec.tool_args as any)?.label ||
    (exec.tool_args as any)?.intent ||
    "未命名";
  return { prefix: meta.label, intent, Icon: meta.icon, color: meta.color };
}

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

function StatusIcon({ status }: { status: string }) {
  const isError = status === "error";
  const isRunning = status === "running";
  return (
    <div
      className={`w-6 h-6 rounded-full border flex items-center justify-center flex-shrink-0 z-10 ${
        isError ? "border-[var(--error)]" : "border-[var(--border-default)]"
      }`}
      style={
        isError ? toneSurfaceStyle("error", 12) : { backgroundColor: "var(--bg-elevated)" }
      }
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

function ExecutionItem({ exec, sessionId }: { exec: CodeExecution; sessionId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [argsExpanded, setArgsExpanded] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const isError = exec.status === "error";
  const isRetry = !!exec.retry_of_execution_id;
  const { prefix, intent, Icon, color } = getCardTitle(exec);
  const cardStyle = isError ? toneSurfaceStyle("error", 8) : undefined;
  const headerStyle = isError ? toneSurfaceStyle("error", 10) : undefined;

  const handleDownload = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      setDownloading(true);
      try {
        await downloadSingleBundle(sessionId, exec.id);
      } finally {
        setDownloading(false);
      }
    },
    [sessionId, exec.id],
  );

  return (
    <div className="flex gap-3 items-start">
      <div className="flex-shrink-0 flex flex-col items-center w-6 pt-1.5">
        <StatusIcon status={exec.status} />
      </div>
      <div
        className={`flex-1 min-w-0 rounded-md border overflow-hidden mb-1 shadow-sm ${
          isError ? "border-[var(--error)]" : "border-[var(--border-default)]"
        }`}
        style={cardStyle}
      >
        <div
          className={`w-full flex items-center gap-2 px-3 h-9 transition-colors ${
            isError ? "hover:opacity-90" : "hover:bg-[var(--bg-hover)]"
          }`}
          style={headerStyle}
        >
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-2 flex-1 min-w-0 text-left cursor-pointer"
          >
            <Icon size={14} className="flex-shrink-0" style={{ color }} />
            <span className="text-xs font-medium text-[var(--text-primary)] truncate">
              {prefix}：{intent}
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
            <span className="text-[10px] text-[var(--text-muted)] ml-auto flex-shrink-0">
              {formatTime(exec.created_at)}
            </span>
          </button>
          <Button
            variant="ghost"
            onClick={handleDownload}
            disabled={downloading}
            className="p-0.5 rounded flex-shrink-0"
            title="下载可复现 zip"
            aria-label="下载"
          >
            {downloading ? (
              <Loader2 size={12} className="animate-spin text-[var(--text-muted)]" />
            ) : (
              <Download size={12} className="text-[var(--text-muted)]" />
            )}
          </Button>
          <button onClick={() => setExpanded((v) => !v)} className="cursor-pointer">
            {expanded ? (
              <ChevronUp size={14} className="text-[var(--text-muted)]" />
            ) : (
              <ChevronDown size={14} className="text-[var(--text-muted)]" />
            )}
          </button>
        </div>

        {expanded && (
          <div className="border-t border-[var(--border-default)]">
            {(exec.tool_args as any)?.dataset_name && (
              <div
                className="px-3 py-1.5 border-b border-[var(--border-default)] text-[10px] text-[var(--domain-profile)] flex items-center gap-2"
                style={toneSurfaceStyle("accent", 8)}
              >
                <span className="font-medium">输入数据：</span>
                <code className="px-1.5 py-0.5 rounded bg-[var(--bg-base)]/75">
                  {(exec.tool_args as any).dataset_name}
                </code>
              </div>
            )}

            {exec.output_resource_ids && exec.output_resource_ids.length > 0 && (
              <div
                className="px-3 py-1.5 border-b border-[var(--border-default)] text-[10px] text-[var(--success)] flex items-center gap-2 flex-wrap"
                style={toneSurfaceStyle("success", 9)}
              >
                <span className="font-medium">生成产物：</span>
                {exec.output_resource_ids.map((id) => (
                  <code key={id} className="px-1.5 py-0.5 rounded bg-[var(--bg-base)]/75">
                    {id.slice(0, 10)}
                  </code>
                ))}
              </div>
            )}

            {exec.code && (
              <div className="relative">
                <div className="flex items-center justify-between px-3 py-1 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
                  <span className="text-[10px] text-[var(--text-muted)] font-medium">
                    代码
                  </span>
                  <CopyButton text={exec.code} />
                </div>
                <pre className="text-xs font-mono px-3 py-2 overflow-x-auto bg-[var(--bg-elevated)] text-[var(--text-secondary)] max-h-[200px] overflow-y-auto">
                  {exec.code}
                </pre>
              </div>
            )}

            {exec.output && (
              <div className="relative border-t border-[var(--border-default)]">
                <div className="flex items-center justify-between px-3 py-1 bg-[var(--bg-elevated)] border-b border-[var(--border-default)]">
                  <span
                    className={`text-[10px] font-medium ${
                      isError ? "text-[var(--error)]" : "text-[var(--text-muted)]"
                    }`}
                  >
                    运行结果
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

            {exec.tool_args && Object.keys(exec.tool_args).length > 0 && (
              <div className="border-t border-[var(--border-default)]">
                <button
                  onClick={() => setArgsExpanded((v) => !v)}
                  className="w-full flex items-center gap-1 px-3 py-1 bg-[var(--bg-elevated)] text-[10px] text-[var(--text-muted)] font-medium hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
                >
                  <span>{argsExpanded ? "▼" : "▶"}</span>
                  <span>参数详情</span>
                </button>
                {argsExpanded && (
                  <pre className="text-[11px] font-mono px-3 py-2 overflow-x-auto bg-[var(--bg-elevated)] text-[var(--text-secondary)] max-h-32 overflow-y-auto">
                    {JSON.stringify(exec.tool_args, null, 2)}
                  </pre>
                )}
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
  const [batchDownloading, setBatchDownloading] = useState(false);

  useEffect(() => {
    if (sessionId) fetchCodeExecutions();
  }, [sessionId, fetchCodeExecutions]);

  const filtered = codeExecutions.filter(
    (e) => e.tool_name === "run_code" || e.tool_name === "run_r_code",
  );

  const handleBatchDownload = useCallback(async () => {
    if (!sessionId) return;
    setBatchDownloading(true);
    try {
      await downloadBatchBundle(sessionId);
    } finally {
      setBatchDownloading(false);
    }
  }, [sessionId]);

  if (filtered.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-[var(--text-muted)] text-xs px-4">
        <Terminal size={24} className="mb-2 opacity-50" />
        <p>暂无代码记录</p>
        <p className="text-[10px] mt-1 text-center">
          当 Agent 运行分析或绘制图表时，
          <br />
          执行过的 Python / R 代码会归档于此，可下载复现
        </p>
      </div>
    );
  }

  return (
    <div className="px-3 py-2">
      <div className="flex items-center justify-between px-1 py-1 mb-2">
        <span className="text-[11px] text-[var(--text-muted)]">
          共 {filtered.length} 份代码归档
        </span>
        <Button
          variant="ghost"
          onClick={handleBatchDownload}
          disabled={batchDownloading || !sessionId}
          className="text-[11px] flex items-center gap-1 px-2 py-0.5"
          title="下载全部代码档案"
        >
          {batchDownloading ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Download size={12} />
          )}
          <span>全部下载</span>
        </Button>
      </div>
      <div className="relative">
        <div
          className="absolute left-[11px] top-6 bottom-4 w-0.5"
          style={{ background: "var(--border-default)" }}
        />
        <div className="flex flex-col">
          {filtered.map((exec) => (
            <ExecutionItem key={exec.id} exec={exec} sessionId={sessionId || ""} />
          ))}
        </div>
      </div>
    </div>
  );
}
