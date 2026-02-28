import { BrainCircuit, Loader2, Radar, Sparkles } from "lucide-react";

import { type IntentAnalysisView } from "../store";

interface Props {
  analysis: IntentAnalysisView | null;
  loading: boolean;
  onApplySuggestion: (value: string) => void;
}

function renderTagList(items: string[]) {
  return items.map((item) => (
    <span
      key={item}
      className="inline-flex rounded-full border border-slate-200 bg-white/80 px-2 py-1 text-[11px] font-medium text-slate-600"
    >
      {item}
    </span>
  ));
}

export default function IntentSummaryCard({
  analysis,
  loading,
  onApplySuggestion,
}: Props) {
  if (!loading && !analysis) return null;

  return (
    <div className="mb-5 overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-amber-50/50 shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200/70 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm">
            <BrainCircuit size={16} />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-800">系统理解</div>
            <div className="text-[11px] text-slate-500">
              在正式回答前，先给出当前回合的意图判断与推荐路径
            </div>
          </div>
        </div>
        <div className="text-[10px] uppercase tracking-[0.24em] text-slate-400">
          {analysis?.analysis_method || "rule_based_v1"}
        </div>
      </div>

      {loading && !analysis && (
        <div className="flex items-center gap-2 px-4 py-4 text-sm text-slate-500">
          <Loader2 size={14} className="animate-spin" />
          正在解析本轮需求与可行路径…
        </div>
      )}

      {analysis && (
        <div className="space-y-4 px-4 py-4">
          <div className="rounded-2xl border border-slate-200 bg-white/85 px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Query</div>
            <div className="mt-1 text-sm text-slate-700">{analysis.query || "当前输入为空"}</div>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.35fr_1fr]">
            <section className="rounded-2xl border border-slate-200 bg-white/85 px-4 py-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                <Radar size={14} className="text-sky-600" />
                候选能力
              </div>
              <div className="mt-3 space-y-2">
                {analysis.capability_candidates.length > 0 ? (
                  analysis.capability_candidates.slice(0, 3).map((candidate) => {
                    const payload = candidate.payload || {};
                    const displayName =
                      typeof payload.display_name === "string" && payload.display_name.trim()
                        ? payload.display_name.trim()
                        : candidate.name;
                    return (
                      <div
                        key={candidate.name}
                        className="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <button
                            type="button"
                            onClick={() => onApplySuggestion(`请帮我做${displayName}`)}
                            className="text-left text-sm font-medium text-slate-800 transition-colors hover:text-sky-700"
                          >
                            {displayName}
                          </button>
                          <div className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-700">
                            {candidate.score.toFixed(1)}
                          </div>
                        </div>
                        <div className="mt-1 text-xs text-slate-500">{candidate.reason}</div>
                      </div>
                    );
                  })
                ) : (
                  <div className="text-xs text-slate-400">当前没有足够强的能力命中。</div>
                )}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white/85 px-4 py-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                <Sparkles size={14} className="text-amber-600" />
                推荐路径
              </div>
              <div className="mt-3 space-y-3">
                <div>
                  <div className="mb-2 text-[11px] text-slate-400">推荐工具</div>
                  <div className="flex flex-wrap gap-2">
                    {analysis.tool_hints.length > 0 ? (
                      renderTagList(analysis.tool_hints.slice(0, 6))
                    ) : (
                      <span className="text-xs text-slate-400">暂无显式工具提示</span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-[11px] text-slate-400">激活技能</div>
                  <div className="flex flex-wrap gap-2">
                    {analysis.active_skills.length > 0 ? (
                      analysis.active_skills.map((item) => (
                        <button
                          key={item.name}
                          type="button"
                          onClick={() => onApplySuggestion(`/${item.name} `)}
                          className="inline-flex rounded-full border border-slate-200 bg-white/80 px-2 py-1 text-[11px] font-medium text-slate-600 transition-colors hover:border-sky-200 hover:text-sky-700"
                        >
                          {item.name}
                        </button>
                      ))
                    ) : (
                      <span className="text-xs text-slate-400">本轮没有激活 Markdown skill</span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-[11px] text-slate-400">显式技能调用</div>
                  <div className="space-y-1.5">
                    {analysis.explicit_skill_calls.length > 0 ? (
                      analysis.explicit_skill_calls.map((call) => (
                        <div
                          key={`${call.name}-${call.arguments}`}
                          className="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-xs text-slate-600"
                        >
                          <button
                            type="button"
                            onClick={() =>
                              onApplySuggestion(
                                `/${call.name}${call.arguments ? ` ${call.arguments}` : " "}`,
                              )
                            }
                            className="text-left transition-colors hover:text-sky-700"
                          >
                            <span className="font-medium text-slate-800">/{call.name}</span>
                            {call.arguments ? ` ${call.arguments}` : ""}
                          </button>
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-slate-400">当前没有显式 `/skill` 调用。</div>
                    )}
                  </div>
                </div>
              </div>
            </section>
          </div>

          {(analysis.allowed_tools.length > 0 || analysis.clarification_needed) && (
            <div className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
              <section className="rounded-2xl border border-slate-200 bg-white/85 px-4 py-3">
                <div className="text-xs font-semibold text-slate-700">技能推荐工具</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {analysis.allowed_tools.length > 0 ? (
                    renderTagList(analysis.allowed_tools)
                  ) : (
                    <span className="text-xs text-slate-400">当前没有技能工具推荐。</span>
                  )}
                </div>
                {analysis.allowed_tool_sources.length > 0 && (
                  <div className="mt-3 text-[11px] text-slate-500">
                    来源：{analysis.allowed_tool_sources.join("、")}
                  </div>
                )}
              </section>

              <section className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3">
                <div className="text-xs font-semibold text-amber-800">澄清建议</div>
                {analysis.clarification_needed ? (
                  <>
                    <div className="mt-2 text-sm text-amber-900">
                      {analysis.clarification_question}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {analysis.clarification_options.length > 0 ? (
                        analysis.clarification_options.map((option) => (
                          <button
                            key={option.label}
                            type="button"
                            onClick={() => onApplySuggestion(`我想做${option.label}`)}
                            className="inline-flex rounded-full border border-amber-200 bg-white px-2.5 py-1 text-[11px] font-medium text-amber-800 transition-colors hover:border-amber-300 hover:bg-amber-100"
                            title={option.description}
                          >
                            {option.label}
                          </button>
                        ))
                      ) : (
                        <span className="text-xs text-amber-700">需要补充更具体的分析目标。</span>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="mt-2 text-sm text-slate-500">当前需求已经足够明确，可直接进入分析。</div>
                )}
              </section>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
