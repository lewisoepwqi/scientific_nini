/**
 * IntentTimelineItem - Intent 时间线项
 * 
 * 在对话时间线中展示系统理解过程，深化前端 Intent 交互体验
 */

import {
  BrainCircuit,
  Target,
  Wrench,
  Puzzle,
  HelpCircle,
  CheckCircle2,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Zap,
} from "lucide-react";
import { useState } from "react";
import { type IntentAnalysisView } from "../store";

interface Props {
  analysis: IntentAnalysisView;
  onApplySuggestion: (value: string) => void;
  isActive?: boolean;
}

export default function IntentTimelineItem({
  analysis,
  onApplySuggestion,
  isActive = false,
}: Props) {
  const [expanded, setExpanded] = useState(true);
  const [showDetails, setShowDetails] = useState(false);

  const hasClarification = analysis.clarification_needed;
  const topCapability = analysis.capability_candidates[0];
  const topSkill = analysis.skill_candidates[0];

  return (
    <div
      className={`my-3 rounded-2xl border transition-all ${
        isActive
          ? "border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm"
          : "border-slate-200 bg-slate-50/50"
      }`}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3"
      >
        <div className="flex items-center gap-2">
          <div
            className={`flex h-7 w-7 items-center justify-center rounded-lg ${
              isActive ? "bg-sky-100 text-sky-600" : "bg-slate-200 text-slate-600"
            }`}
          >
            <BrainCircuit size={14} />
          </div>
          <div className="text-left">
            <div className="text-sm font-medium text-slate-800">
              {hasClarification ? "需要澄清" : "意图理解"}
            </div>
            <div className="text-xs text-slate-500">
              {analysis.analysis_method === "rule_based_v2"
                ? "基于规则 v2"
                : "规则版"}{" "}
              · {analysis.capability_candidates.length} 个候选能力
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasClarification && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
              需确认
            </span>
          )}
          {expanded ? (
            <ChevronDown size={16} className="text-slate-400" />
          ) : (
            <ChevronUp size={16} className="text-slate-400" />
          )}
        </div>
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="border-t border-slate-200/70 px-4 pb-4">
          {/* 理解结果摘要 */}
          <div className="mt-3 space-y-3">
            {/* 主要意图 */}
            {(topCapability || topSkill) && (
              <div className="flex items-start gap-3 rounded-xl bg-white/60 p-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-sky-100 text-sky-600">
                  <Target size={12} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-slate-500">系统判断您的意图是</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {topCapability ? (
                      <button
                        onClick={() =>
                          onApplySuggestion(
                            `请帮我做${(topCapability.payload as {display_name?: string} | undefined)?.display_name || topCapability.name}`
                          )
                        }
                        className="inline-flex items-center gap-1 rounded-lg bg-sky-50 px-2 py-1 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100"
                      >
                        {(topCapability.payload as {display_name?: string} | undefined)?.display_name || topCapability.name}
                        <span className="text-[10px] opacity-70">
                          ({topCapability.score.toFixed(1)})
                        </span>
                      </button>
                    ) : null}
                    {topSkill ? (
                      <button
                        onClick={() => onApplySuggestion(`/${topSkill.name} `)}
                        className="inline-flex items-center gap-1 rounded-lg bg-amber-50 px-2 py-1 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100"
                      >
                        <Puzzle size={12} />
                        {topSkill.name}
                      </button>
                    ) : null}
                  </div>
                  {topCapability && (
                    <div className="mt-1 text-xs text-slate-500">
                      {topCapability.reason}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 推荐工具 */}
            {analysis.tool_hints.length > 0 && (
              <div className="flex items-start gap-3 rounded-xl bg-white/60 p-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-emerald-600">
                  <Wrench size={12} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-slate-500">推荐使用的工具</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {analysis.tool_hints.slice(0, 4).map((tool) => (
                      <span
                        key={tool}
                        className="inline-flex rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700"
                      >
                        {tool}
                      </span>
                    ))}
                    {analysis.tool_hints.length > 4 && (
                      <span className="text-xs text-slate-400">
                        +{analysis.tool_hints.length - 4} 更多
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* 激活技能 */}
            {analysis.active_skills.length > 0 && (
              <div className="flex items-start gap-3 rounded-xl bg-white/60 p-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-600">
                  <Sparkles size={12} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-slate-500">已激活技能</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {analysis.active_skills.map((skill) => (
                      <button
                        key={skill.name}
                        onClick={() => onApplySuggestion(`/${skill.name} `)}
                        className="inline-flex items-center gap-1 rounded-md border border-purple-200 bg-white px-2 py-0.5 text-xs font-medium text-purple-700 transition-colors hover:bg-purple-50"
                      >
                        {skill.name}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 澄清建议 */}
            {hasClarification && (
              <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-600">
                  <HelpCircle size={12} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-amber-800">需要您的确认</div>
                  <div className="mt-1 text-sm text-amber-900">
                    {analysis.clarification_question}
                  </div>
                  {analysis.clarification_options.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {analysis.clarification_options.map((option) => (
                        <button
                          key={option.label}
                          onClick={() => onApplySuggestion(`我想做${option.label}`)}
                          className="inline-flex rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 transition-colors hover:bg-amber-100"
                          title={option.description}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 如果没有澄清需求，显示确认 */}
            {!hasClarification && topCapability && (
              <div className="flex items-center gap-2 rounded-xl bg-emerald-50/70 p-3 text-sm text-emerald-700">
                <CheckCircle2 size={14} />
                <span>意图已明确，将基于上述理解继续分析</span>
              </div>
            )}
          </div>

          {/* 详细信息折叠 */}
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="mt-3 flex w-full items-center justify-center gap-1 rounded-lg py-2 text-xs text-slate-500 transition-colors hover:bg-slate-100"
          >
            {showDetails ? "收起详情" : "查看详情"}
            {showDetails ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>

          {/* 详细信息 */}
          {showDetails && (
            <div className="mt-3 space-y-3 rounded-xl bg-slate-100/70 p-3">
              {/* 所有能力候选 */}
              {analysis.capability_candidates.length > 1 ? (
                <div>
                  <div className="text-xs font-medium text-slate-700">所有能力候选</div>
                  <div className="mt-1 space-y-1">
                    {analysis.capability_candidates.slice(1).map((candidate) => (
                      <div
                        key={candidate.name}
                        className="flex items-center justify-between rounded-lg bg-white/60 px-2 py-1.5 text-xs"
                      >
                        <span className="text-slate-700">
                          {(candidate.payload as {display_name?: string} | undefined)?.display_name || candidate.name}
                        </span>
                        <span className="text-slate-400">{candidate.score.toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {/* 显式技能调用 */}
              {analysis.explicit_skill_calls.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-slate-700">显式技能调用</div>
                  <div className="mt-1 space-y-1">
                    {analysis.explicit_skill_calls.map((call, idx) => (
                      <button
                        key={`${call.name}-${idx}`}
                        onClick={() =>
                          onApplySuggestion(
                            `/${call.name}${call.arguments ? ` ${call.arguments}` : ""}`
                          )
                        }
                        className="w-full rounded-lg bg-white/60 px-2 py-1.5 text-left text-xs text-slate-700 transition-colors hover:bg-white"
                      >
                        <span className="font-medium">/{call.name}</span>
                        {call.arguments && (
                          <span className="text-slate-500"> {call.arguments}</span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* 允许的工具 */}
              {analysis.allowed_tools.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-slate-700">技能推荐工具</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {analysis.allowed_tools.map((tool) => (
                      <span
                        key={tool}
                        className="rounded bg-white/60 px-1.5 py-0.5 text-[10px] text-slate-600"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 分析方法 */}
              <div className="flex items-center gap-1 text-[10px] text-slate-400">
                <Zap size={10} />
                分析方法: {analysis.analysis_method}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
