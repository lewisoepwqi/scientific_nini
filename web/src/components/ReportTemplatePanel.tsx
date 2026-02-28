/**
 * ReportTemplatePanel - 发表级报告模板面板
 * 
 * 统一报告结构，支持期刊风格选择和导出
 */

import { useState } from "react";
import {
  FileText,
  BookOpen,
  Download,
  Settings,
  CheckCircle2,
  Loader2,
  X,
  Newspaper,
} from "lucide-react";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string | null;
}

interface ReportSection {
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
    features: ["简短摘要", "方法简述", "突出主要发现"],
    color: "from-emerald-500 to-teal-600",
  },
  {
    id: "science",
    name: "Science",
    description: "跨学科综合期刊风格",
    features: ["清晰的问题陈述", "广泛的方法描述", "深入讨论"],
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
    features: ["患者特征", "严格的统计分析", "临床意义"],
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
    features: ["假设驱动", "详细方法","结果与讨论分开"],
    color: "from-sky-500 to-cyan-600",
  },
];

const DEFAULT_SECTIONS: ReportSection[] = [
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
    description: "研究背景、目的和假设",
    required: true,
    selected: true,
  },
  {
    id: "methods",
    title: "方法 (Methods)",
    description: "详细的实验设计、数据收集和统计分析方法",
    required: true,
    selected: true,
  },
  {
    id: "results",
    title: "结果 (Results)",
    description: "主要发现，包含图表和统计数据",
    required: true,
    selected: true,
  },
  {
    id: "discussion",
    title: "讨论 (Discussion)",
    description: "结果解释、与现有研究比较、意义和局限性",
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
  {
    id: "references",
    title: "参考文献 (References)",
    description: "引用的文献列表",
    required: false,
    selected: false,
  },
];

export default function ReportTemplatePanel({ isOpen, onClose, sessionId }: Props) {
  const [selectedTemplate, setSelectedTemplate] = useState("nature");
  const [sections, setSections] = useState<ReportSection[]>(DEFAULT_SECTIONS);
  const [detailLevel, setDetailLevel] = useState<"brief" | "standard" | "detailed">("standard");
  const [includeFigures, setIncludeFigures] = useState(true);
  const [includeTables, setIncludeTables] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);

  const toggleSection = (id: string) => {
    setSections((prev) =>
      prev.map((s) => (s.id === id && !s.required ? { ...s, selected: !s.selected } : s))
    );
  };

  const selectAllSections = () => {
    setSections((prev) => prev.map((s) => ({ ...s, selected: true })));
  };

  const generateReport = async () => {
    if (!sessionId) return;
    setGenerating(true);
    
    // 模拟报告生成
    await new Promise((resolve) => setTimeout(resolve, 2000));
    
    setGenerating(false);
    setGenerated(true);
    setTimeout(() => setGenerated(false), 3000);
  };

  const downloadReport = (format: "md" | "docx" | "pdf") => {
    // 构建报告配置
    const config = {
      template: selectedTemplate,
      sections: sections.filter((s) => s.selected).map((s) => s.id),
      detailLevel,
      includeFigures,
      includeTables,
    };
    
    console.log(`下载 ${format.toUpperCase()} 格式报告:`, config);
    // 实际实现中应调用后端 API
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
              <Newspaper size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">发表级报告生成</h2>
              <p className="text-xs text-slate-400">选择期刊风格，统一报告结构</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            <X size={20} />
          </button>
        </div>

        <div className="grid max-h-[70vh] grid-cols-[1fr,320px] overflow-hidden">
          {/* Left Panel - Template Selection */}
          <div className="overflow-y-auto border-r border-slate-200 p-6">
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
                <div className="text-sm font-medium text-slate-800">{template.name} 特点</div>
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
              onClick={generateReport}
              disabled={generating || !sessionId}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:opacity-50"
            >
              {generating ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  生成中...
                </>
              ) : generated ? (
                <>
                  <CheckCircle2 size={16} />
                  已生成
                </>
              ) : (
                <>
                  <FileText size={16} />
                  生成报告
                </>
              )}
            </button>
          </div>

          {/* Right Panel - Section Selection */}
          <div className="overflow-y-auto bg-slate-50/50 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800">报告章节</h3>
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
                  <div className="text-xs text-slate-500">自动插入生成的图表</div>
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
                    onClick={() => downloadReport(format)}
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
          </div>
        </div>
      </div>
    </div>
  );
}
