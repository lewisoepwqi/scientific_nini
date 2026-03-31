/**
 * ArticleDraftPopover - 文章初稿紧凑弹出层
 *
 * 从 ChatInputArea 工具栏触发，提供快速的文章初稿配置与生成入口。
 */

import { useState, useRef, useEffect, useCallback } from "react";
import {
  PenTool,
  Check,
  Download,
  ChevronDown,
} from "lucide-react";
import { apiFetch } from "../store/auth";

/* ------------------------------------------------------------------ */
/*  类型 & 常量（复用 ArticleDraftPanel 中的定义）                      */
/* ------------------------------------------------------------------ */

interface DraftConfig {
  template: string;
  sections: string[];
  detail_level: "brief" | "standard" | "detailed";
  include_figures: boolean;
  include_tables: boolean;
  title: string;
}

interface DraftSection {
  id: string;
  title: string;
  description: string;
  required: boolean;
  selected: boolean;
}

interface Props {
  sessionId: string | null;
  onStartDraft: (config: DraftConfig) => void;
}

const JOURNAL_TEMPLATES = [
  { id: "nature", name: "Nature", color: "bg-[var(--domain-report)]" },
  { id: "science", name: "Science", color: "bg-[var(--domain-profile)]" },
  { id: "cell", name: "Cell", color: "bg-[var(--domain-knowledge)]" },
  { id: "nejm", name: "NEJM", color: "bg-[var(--error)]" },
  { id: "lancet", name: "Lancet", color: "bg-[var(--domain-cost)]" },
  { id: "apa", name: "APA", color: "bg-[var(--domain-analysis)]" },
];

const DEFAULT_SECTIONS: DraftSection[] = [
  { id: "abstract", title: "摘要", description: "简要概述", required: true, selected: true },
  { id: "introduction", title: "引言", description: "背景与目的", required: true, selected: true },
  { id: "methods", title: "方法", description: "数据与分析", required: true, selected: true },
  { id: "results", title: "结果", description: "主要发现", required: true, selected: true },
  { id: "discussion", title: "讨论", description: "解释与意义", required: true, selected: true },
  { id: "conclusion", title: "结论", description: "总结与建议", required: false, selected: true },
  { id: "limitations", title: "局限性", description: "不足与展望", required: false, selected: true },
];

const DETAIL_LEVELS: {
  value: "brief" | "standard" | "detailed";
  label: string;
}[] = [
  { value: "brief", label: "简洁" },
  { value: "standard", label: "标准" },
  { value: "detailed", label: "详细" },
];

const EXPORT_FORMATS = [
  { format: "md" as const, label: "Markdown" },
  { format: "docx" as const, label: "Word" },
  { format: "pdf" as const, label: "PDF" },
];

/* ------------------------------------------------------------------ */
/*  组件                                                               */
/* ------------------------------------------------------------------ */

export default function ArticleDraftPopover({ sessionId, onStartDraft }: Props) {
  const [open, setOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState("nature");
  const [sections, setSections] = useState<DraftSection[]>(DEFAULT_SECTIONS);
  const [detailLevel, setDetailLevel] = useState<"brief" | "standard" | "detailed">("standard");
  const [includeFigures, setIncludeFigures] = useState(true);
  const [includeTables, setIncludeTables] = useState(true);
  const [exportOpen, setExportOpen] = useState(false);

  // 点击外部关闭
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    // 延迟绑定，避免触发按钮的 click 立即关闭
    const timer = setTimeout(() => {
      document.addEventListener("mousedown", handleClickOutside);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  // ESC 关闭
  useEffect(() => {
    if (!open) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [open]);

  // 切换章节选中
  const toggleSection = useCallback((id: string) => {
    setSections((prev) =>
      prev.map((s) => (s.id === id && !s.required ? { ...s, selected: !s.selected } : s)),
    );
  }, []);

  // 生成到对话
  const handleStartDraft = useCallback(() => {
    const config: DraftConfig = {
      template: selectedTemplate,
      sections: sections.filter((s) => s.selected).map((s) => s.id),
      detail_level: detailLevel,
      include_figures: includeFigures,
      include_tables: includeTables,
      title: "基于对话的文章初稿",
    };
    setOpen(false);
    onStartDraft(config);
  }, [selectedTemplate, sections, detailLevel, includeFigures, includeTables, onStartDraft]);

  // 导出下载（复用 ArticleDraftPanel 逻辑）
  const handleExport = useCallback(
    async (format: "md" | "docx" | "pdf") => {
      if (!sessionId) return;
      setExportOpen(false);
      try {
        const response = await apiFetch(`/api/report/export?session_id=${sessionId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            format,
            filename: `${selectedTemplate}_article_draft`,
          }),
        });
        const data = await response.json();
        if (data.success && data.data?.download_url) {
          const link = document.createElement("a");
          link.href = data.data.download_url;
          link.download = data.data.filename || `${selectedTemplate}_article_draft.${format}`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        } else {
          alert(`导出失败: ${data.error || data.message || "未找到可导出的文件"}`);
        }
      } catch {
        alert("导出请求失败，请检查网络连接");
      }
    },
    [sessionId, selectedTemplate],
  );

  return (
    <div className="relative" ref={containerRef}>
      {/* 触发按钮 */}
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={`h-8 w-8 rounded-md border inline-flex items-center justify-center
          transition-colors ${
            open
              ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]"
              : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          }`}
        title="生成文章初稿"
        aria-label="生成文章初稿"
      >
        <PenTool size={14} />
      </button>

      {/* Popover 内容 */}
      {open && (
        <div
          className="absolute left-0 bottom-[calc(100%+8px)] z-30 w-[320px] rounded-xl border
            border-[var(--border-default)] bg-[var(--bg-base)] shadow-lg
            dark:bg-[var(--bg-elevated)]"
          style={{ maxHeight: "min(520px, calc(100vh - 120px))", overflowY: "auto" }}
        >
          {/* 标题栏 */}
          <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-[var(--border-default)]
            bg-[var(--bg-base)] px-3 py-2 dark:bg-[var(--bg-elevated)]">
            <PenTool size={14} className="text-[var(--accent)]" />
            <span className="text-sm font-medium text-[var(--text-primary)]">文章初稿</span>
          </div>

          <div className="space-y-3 p-3">
            {/* 期刊模板 - 紧凑横向卡片 */}
            <div>
              <div className="mb-1.5 text-xs font-medium text-[var(--text-secondary)]">期刊风格</div>
              <div className="flex flex-wrap gap-1.5">
                {JOURNAL_TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setSelectedTemplate(t.id)}
                    className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs
                      transition-colors ${
                        selectedTemplate === t.id
                          ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                          : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                      }`}
                  >
                    <span
                      className={`inline-block h-3 w-3 rounded-sm text-[8px] leading-[12px]
                        text-center font-bold text-white ${t.color}`}
                    >
                      {t.name[0]}
                    </span>
                    {t.name}
                  </button>
                ))}
              </div>
            </div>

            {/* 章节选择 */}
            <div>
              <div className="mb-1.5 text-xs font-medium text-[var(--text-secondary)]">文章章节</div>
              <div className="space-y-1">
                {sections.map((section) => (
                  <label
                    key={section.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1
                      text-xs hover:bg-[var(--bg-hover)]"
                  >
                    <input
                      type="checkbox"
                      checked={section.selected}
                      onChange={() => toggleSection(section.id)}
                      disabled={section.required}
                      className="h-3.5 w-3.5 rounded border-[var(--border-strong)] text-[var(--accent)]
                        focus:ring-[var(--accent)] disabled:opacity-50"
                    />
                    <span className="text-[var(--text-primary)]">{section.title}</span>
                    {section.required && (
                      <span className="text-[10px] text-[var(--text-muted)]">必选</span>
                    )}
                  </label>
                ))}
              </div>
            </div>

            {/* 详细程度 */}
            <div>
              <div className="mb-1.5 text-xs font-medium text-[var(--text-secondary)]">详细程度</div>
              <div className="flex gap-1.5">
                {DETAIL_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    type="button"
                    onClick={() => setDetailLevel(level.value)}
                    className={`flex-1 rounded-md border px-2 py-1 text-xs text-center transition-colors ${
                      detailLevel === level.value
                        ? "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]"
                        : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    {level.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 图表/表格包含开关 */}
            <div className="flex gap-3">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-[var(--text-primary)]">
                <input
                  type="checkbox"
                  checked={includeFigures}
                  onChange={(e) => setIncludeFigures(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-[var(--border-strong)] text-[var(--accent)]
                    focus:ring-[var(--accent)]"
                />
                包含图表
              </label>
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-[var(--text-primary)]">
                <input
                  type="checkbox"
                  checked={includeTables}
                  onChange={(e) => setIncludeTables(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-[var(--border-strong)] text-[var(--accent)]
                    focus:ring-[var(--accent)]"
                />
                包含表格
              </label>
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-2 pt-1">
              {/* 生成到对话 */}
              <button
                type="button"
                onClick={handleStartDraft}
                disabled={!sessionId}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[var(--accent)]
                  px-3 py-1.5 text-xs font-medium text-white transition-colors
                  hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Check size={12} />
                生成到对话
              </button>

              {/* 导出下拉 */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setExportOpen((prev) => !prev)}
                  disabled={!sessionId}
                  className="flex h-full items-center gap-1 rounded-lg border border-[var(--border-default)]
                    bg-[var(--bg-base)] px-2 py-1.5 text-xs text-[var(--text-secondary)]
                    transition-colors hover:bg-[var(--bg-hover)] disabled:cursor-not-allowed
                    disabled:opacity-50 dark:bg-[var(--bg-elevated)]"
                >
                  <Download size={12} />
                  <ChevronDown size={10} />
                </button>

                {exportOpen && (
                  <div
                    className="absolute right-0 bottom-[calc(100%+4px)] z-10 w-28 rounded-lg border
                      border-[var(--border-default)] bg-[var(--bg-base)] py-1 shadow-md
                      dark:bg-[var(--bg-elevated)]"
                  >
                    {EXPORT_FORMATS.map(({ format, label }) => (
                      <button
                        key={format}
                        type="button"
                        onClick={() => void handleExport(format)}
                        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-xs
                          text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                      >
                        <Download size={10} />
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
