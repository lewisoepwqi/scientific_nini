/**
 * ArticleDraftPanel - 文章初稿生成面板
 *
 * 基于对话内容智能生成科研文章初稿
 */

import { useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  Download,
  Settings,
  X,
  PenTool,
} from "lucide-react";

interface DraftConfig {
  template: string;
  sections: string[];
  detail_level: "brief" | "standard" | "detailed";
  include_figures: boolean;
  include_tables: boolean;
  title: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string | null;
  onStartDraftDialog?: (config: DraftConfig) => void;
}

interface DraftSection {
  id: string;
  title: string;
  description: string;
  required: boolean;
  selected: boolean;
}

const JOURNAL_TEMPLATES = [
  {
    id: "nature",
    name: "Nature",
    description: "强调创新性和广泛影响",
    features: ["简短精炼摘要", "突出主要发现", "强调广泛意义"],
    color: "from-emerald-500 to-teal-600",
  },
  {
    id: "science",
    name: "Science",
    description: "跨学科综合期刊风格",
    features: ["清晰的问题陈述", "简洁的方法描述", "突出科学意义"],
    color: "from-blue-500 to-indigo-600",
  },
  {
    id: "cell",
    name: "Cell",
    description: "生命科学领域权威",
    features: ["详细实验设计", "完整结果展示", "机制探讨"],
    color: "from-purple-500 to-pink-600",
  },
  {
    id: "nejm",
    name: "NEJM",
    description: "临床医学顶刊风格",
    features: ["患者特征描述", "严格的统计分析", "临床意义突出"],
    color: "from-red-500 to-rose-600",
  },
  {
    id: "lancet",
    name: "Lancet",
    description: "全球健康视角",
    features: ["公共卫生影响", "全球适用性", "政策建议"],
    color: "from-amber-500 to-orange-600",
  },
  {
    id: "apa",
    name: "APA",
    description: "心理学标准格式",
    features: ["假设驱动", "详细方法", "统计严谨"],
    color: "from-sky-500 to-cyan-600",
  },
];

const DEFAULT_SECTIONS: DraftSection[] = [
  {
    id: "abstract",
    title: "摘要 (Abstract)",
    description: "研究背景、方法、主要结果和结论的简要概述",
    required: true,
    selected: true,
  },
  {
    id: "introduction",
    title: "引言 (Introduction)",
    description: "研究背景、目的和要解决的问题",
    required: true,
    selected: true,
  },
  {
    id: "methods",
    title: "方法 (Methods)",
    description: "数据来源、样本特征和统计分析方法",
    required: true,
    selected: true,
  },
  {
    id: "results",
    title: "结果 (Results)",
    description: "主要发现，包含统计数据和图表",
    required: true,
    selected: true,
  },
  {
    id: "discussion",
    title: "讨论 (Discussion)",
    description: "结果解释、意义和局限性",
    required: true,
    selected: true,
  },
  {
    id: "conclusion",
    title: "结论 (Conclusion)",
    description: "主要发现的总结和实践建议",
    required: false,
    selected: true,
  },
  {
    id: "limitations",
    title: "局限性 (Limitations)",
    description: "研究的局限性和未来研究方向",
    required: false,
    selected: true,
  },
];

export default function ArticleDraftPanel({ isOpen, onClose, sessionId, onStartDraftDialog }: Props) {
  const [selectedTemplate, setSelectedTemplate] = useState("nature");
  const [sections, setSections] = useState<DraftSection[]>(DEFAULT_SECTIONS);
  const [detailLevel, setDetailLevel] = useState<"brief" | "standard" | "detailed">("standard");
  const [includeFigures, setIncludeFigures] = useState(true);
  const [includeTables, setIncludeTables] = useState(true);

  const toggleSection = (id: string) => {
    setSections((prev) =>
      prev.map((s) => (s.id === id && !s.required ? { ...s, selected: !s.selected } : s))
    );
  };

  const selectAllSections = () => {
    setSections((prev) => prev.map((s) => ({ ...s, selected: true })));
  };

  const startDialogDraft = () => {
    if (!sessionId || !onStartDraftDialog) return;

    const config: DraftConfig = {
      template: selectedTemplate,
      sections: sections.filter((s) => s.selected).map((s) => s.id),
      detail_level: detailLevel,
      include_figures: includeFigures,
      include_tables: includeTables,
      title: "基于对话的文章初稿",
    };

    // 关闭面板并触发对话模式
    onClose();
    onStartDraftDialog(config);
  };

  const downloadDraft = async (format: "md" | "docx" | "pdf") => {
    if (!sessionId) {
      alert("请先选择会话");
      return;
    }

    try {
      const response = await fetch(`/api/report/export?session_id=${sessionId}`, {
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
        console.error("下载失败:", data.error || data.message);
        alert(`下载失败: ${data.error || data.message || "未找到可导出的文件"}`);
      }
    } catch (error) {
      console.error("下载请求失败:", error);
      alert("下载请求失败，请检查网络连接");
    }
  };

  if (!isOpen) return null;

  const selectedCount = sections.filter((s) => s.selected).length;
  const template = JOURNAL_TEMPLATES.find((t) => t.id === selectedTemplate);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-gradient-to-r from-slate-900 to-slate-800 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-white">
              <PenTool size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">生成文章初稿</h2>
              <p className="text-xs text-slate-400">基于对话内容智能生成完整文章</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            <X size={20} />
          </button>
        </div>

        <div className="grid h-[calc(90vh-80px)] grid-cols-[1fr,320px] overflow-hidden">
          {/* Left Panel - Template Selection */}
          <div className="h-full overflow-y-auto border-r border-slate-200 p-6">
            <div className="mb-6">
              <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <BookOpen size={16} className="text-sky-600" />
                选择期刊风格
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {JOURNAL_TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setSelectedTemplate(t.id)}
                    className={`relative rounded-xl border p-4 text-left transition-all ${
                      selectedTemplate === t.id
                        ? "border-sky-500 bg-sky-50 ring-1 ring-sky-500"
                        : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div
                        className={`h-8 w-8 rounded-lg bg-gradient-to-br ${t.color} text-white flex items-center justify-center text-xs font-bold`}
                      >
                        {t.name[0]}
                      </div>
                      {selectedTemplate === t.id && (
                        <CheckCircle2 size={16} className="text-sky-600" />
                      )}
                    </div>
                    <div className="mt-2 font-medium text-slate-800">{t.name}</div>
                    <div className="text-xs text-slate-500">{t.description}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Selected Template Features */}
            {template && (
              <div className="mb-6 rounded-xl bg-slate-50 p-4">
                <div className="text-sm font-medium text-slate-800">{template.name} 风格特点</div>
                <ul className="mt-2 space-y-1">
                  {template.features.map((feature, idx) => (
                    <li key={idx} className="flex items-center gap-2 text-xs text-slate-600">
                      <span className="h-1 w-1 rounded-full bg-sky-500" />
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Detail Level */}
            <div className="mb-6">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Settings size={16} className="text-sky-600" />
                详细程度
              </h3>
              <div className="flex gap-2">
                {[
                  { value: "brief" as const, label: "简洁", desc: "适合快报" },
                  { value: "standard" as const, label: "标准", desc: "常规论文" },
                  { value: "detailed" as const, label: "详细", desc: "完整报告" },
                ].map((level) => (
                  <button
                    key={level.value}
                    onClick={() => setDetailLevel(level.value)}
                    className={`flex-1 rounded-xl border p-3 text-center transition-all ${
                      detailLevel === level.value
                        ? "border-sky-500 bg-sky-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className="text-sm font-medium">{level.label}</div>
                    <div className="text-[10px] text-slate-500">{level.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Generate Button */}
            <button
              onClick={startDialogDraft}
              disabled={!sessionId}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              <PenTool size={16} />
              开始对话生成
            </button>
          </div>

          {/* Right Panel - Section Selection */}
          <div className="h-full overflow-y-auto bg-slate-50/50 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800">文章章节</h3>
              <button
                onClick={selectAllSections}
                className="text-xs text-sky-600 hover:text-sky-700"
              >
                全选
              </button>
            </div>

            <div className="space-y-2">
              {sections.map((section) => (
                <label
                  key={section.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-all ${
                    section.selected
                      ? "border-sky-200 bg-sky-50/50"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={section.selected}
                    onChange={() => toggleSection(section.id)}
                    disabled={section.required}
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500 disabled:opacity-50"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">
                        {section.title}
                      </span>
                      {section.required && (
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                          必需
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">{section.description}</div>
                  </div>
                </label>
              ))}
            </div>

            <div className="mt-6 space-y-3">
              <h3 className="text-sm font-semibold text-slate-800">包含内容</h3>

              <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-white p-3">
                <input
                  type="checkbox"
                  checked={includeFigures}
                  onChange={(e) => setIncludeFigures(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                />
                <div>
                  <div className="text-sm font-medium text-slate-700">包含图表</div>
                  <div className="text-xs text-slate-500">自动嵌入生成的图表</div>
                </div>
              </label>

              <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-white p-3">
                <input
                  type="checkbox"
                  checked={includeTables}
                  onChange={(e) => setIncludeTables(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                />
                <div>
                  <div className="text-sm font-medium text-slate-700">包含数据表</div>
                  <div className="text-xs text-slate-500">关键统计结果表格</div>
                </div>
              </label>
            </div>

            {/* Export Options */}
            <div className="mt-6">
              <h3 className="mb-3 text-sm font-semibold text-slate-800">导出格式</h3>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { format: "md" as const, label: "Markdown", ext: ".md" },
                  { format: "docx" as const, label: "Word", ext: ".docx" },
                  { format: "pdf" as const, label: "PDF", ext: ".pdf" },
                ].map(({ format, label, ext }) => (
                  <button
                    key={format}
                    onClick={() => downloadDraft(format)}
                    className="flex flex-col items-center gap-1 rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-sky-300 hover:bg-sky-50"
                  >
                    <Download size={16} className="text-slate-600" />
                    <span className="text-xs font-medium">{label}</span>
                    <span className="text-[10px] text-slate-400">{ext}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-6 rounded-xl bg-slate-100 p-3 text-xs text-slate-600">
              <div className="font-medium text-slate-700">已选择</div>
              <div className="mt-1">
                {selectedCount} 个章节 · {template?.name} 风格 · {" "}
                {detailLevel === "brief" ? "简洁" : detailLevel === "standard" ? "标准" : "详细"}版本
              </div>
            </div>

            {/* Info hint */}
            <div className="mt-4 rounded-xl bg-blue-50 p-3 text-xs text-blue-700">
              <div className="font-medium">提示</div>
              <p className="mt-1">
                点击"开始对话生成"后，将进入对话模式。AI 会分析您的对话历史，
                并询问相关配置，最终在对话中完成文章初稿的生成。
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
