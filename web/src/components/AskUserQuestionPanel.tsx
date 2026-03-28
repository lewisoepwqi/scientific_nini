import { useEffect, useMemo, useState } from "react";
import type { PendingAskUserQuestion, QuestionType } from "../store";

const SKIPPED_ANSWER_VALUE = "已跳过";

interface AskUserQuestionPanelProps {
  pending: PendingAskUserQuestion;
  onSubmit: (answers: Record<string, string>) => void;
}

export default function AskUserQuestionPanel({
  pending,
  onSubmit,
}: AskUserQuestionPanelProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [selectedMap, setSelectedMap] = useState<Record<number, string[]>>({});
  const [textMap, setTextMap] = useState<Record<number, string>>({});
  const [skippedMap, setSkippedMap] = useState<Record<number, boolean>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});

  useEffect(() => {
    setActiveIndex(0);
    setSelectedMap({});
    setTextMap({});
    setSkippedMap({});
    setErrors({});
  }, [pending.toolCallId]);

  const questionCount = pending.questions.length;

  const completionMap = useMemo(() => {
    return pending.questions.map((question, index) => {
      if (skippedMap[index]) return true;
      const selected = selectedMap[index] || [];
      const text = (textMap[index] || "").trim();
      if (question.multiSelect) return selected.length > 0 || Boolean(text);
      return Boolean(selected[0]) || Boolean(text);
    });
  }, [pending.questions, selectedMap, skippedMap, textMap]);
  const completedCount = completionMap.filter(Boolean).length;
  const isAllCompleted = completedCount === questionCount;
  const activeQuestion = pending.questions[activeIndex];
  const isActiveSkipped = Boolean(skippedMap[activeIndex]);

  const toggleMultiOption = (questionIndex: number, label: string) => {
    setSelectedMap((prev) => {
      const prevSelected = prev[questionIndex] || [];
      if (prevSelected.includes(label)) {
        return {
          ...prev,
          [questionIndex]: prevSelected.filter((item) => item !== label),
        };
      }
      return {
        ...prev,
        [questionIndex]: [...prevSelected, label],
      };
    });
    setSkippedMap((prev) => ({ ...prev, [questionIndex]: false }));
    setErrors((prev) => ({ ...prev, [questionIndex]: "" }));
  };

  const setSingleOption = (questionIndex: number, label: string) => {
    setSelectedMap((prev) => ({ ...prev, [questionIndex]: [label] }));
    setSkippedMap((prev) => ({ ...prev, [questionIndex]: false }));
    setErrors((prev) => ({ ...prev, [questionIndex]: "" }));
  };

  const setTextAnswer = (questionIndex: number, value: string) => {
    setTextMap((prev) => ({ ...prev, [questionIndex]: value }));
    setSkippedMap((prev) => ({ ...prev, [questionIndex]: false }));
    if (value.trim()) {
      setErrors((prev) => ({ ...prev, [questionIndex]: "" }));
    }
  };

  const skipCurrentQuestion = () => {
    setSkippedMap((prev) => ({ ...prev, [activeIndex]: true }));
    setErrors((prev) => ({ ...prev, [activeIndex]: "" }));
    if (activeIndex < questionCount - 1) {
      setActiveIndex(activeIndex + 1);
    }
  };

  const handleSubmit = () => {
    if (!isAllCompleted) return;

    const nextErrors: Record<number, string> = {};
    const answers: Record<string, string> = {};

    pending.questions.forEach((question, index) => {
      if (skippedMap[index]) {
        answers[question.question] = SKIPPED_ANSWER_VALUE;
        return;
      }
      const selected = selectedMap[index] || [];
      const text = (textMap[index] || "").trim();
      let answer = "";

      if (question.multiSelect) {
        const parts = [...selected];
        if (text) parts.push(text);
        answer = parts.join(", ");
      } else if (text) {
        answer = text;
      } else {
        answer = selected[0] || "";
      }

      if (!answer.trim()) {
        nextErrors[index] = "请先完成该问题";
        return;
      }
      answers[question.question] = answer.trim();
    });

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      const firstInvalidIndex = pending.questions.findIndex((_, index) => nextErrors[index]);
      if (firstInvalidIndex >= 0) {
        setActiveIndex(firstInvalidIndex);
      }
      return;
    }
    onSubmit(answers);
  };

  // 根据 question_type 计算每个问题的容器样式
  function getSectionStyle(questionType?: QuestionType): string {
    if (questionType === "risk_confirmation") {
      return "rounded-xl border border-red-300 bg-red-50/40 p-3";
    }
    return "rounded-xl border border-slate-200 p-3";
  }

  // 根据 question_type 计算选项按钮样式
  function getOptionStyle(questionType?: QuestionType, checked?: boolean): string {
    const isEmphasis =
      questionType === "approach_choice" || questionType === "ambiguous_requirement";
    if (isEmphasis) {
      return checked
        ? "flex cursor-pointer items-start gap-2 rounded-lg border border-blue-400 bg-blue-50 px-2.5 py-2"
        : "flex cursor-pointer items-start gap-2 rounded-lg border border-blue-200 px-2.5 py-2 hover:bg-blue-50";
    }
    return "flex cursor-pointer items-start gap-2 rounded-lg border border-slate-200 px-2.5 py-2 hover:bg-slate-50";
  }

  function getTabStyle(index: number): string {
    if (errors[index]) {
      return "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400";
    }
    if (index === activeIndex) {
      return "border-blue-400 bg-blue-50 text-blue-700 shadow-sm dark:border-blue-600 dark:bg-blue-900/20 dark:text-blue-400";
    }
    if (skippedMap[index]) {
      return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400";
    }
    if (completionMap[index]) {
      return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400";
    }
    return "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700";
  }

  return (
    <div className="border-t border-blue-100 dark:border-blue-900/30 bg-blue-50/60 dark:bg-blue-900/15 px-4 py-3">
      <div className="mx-auto max-w-3xl rounded-2xl border border-blue-200 dark:border-blue-800 bg-white dark:bg-slate-800 p-4 shadow-sm">
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm font-semibold text-blue-700">
            需要你补充 {questionCount} 个信息点，回答后继续执行
          </div>
          <div className="text-xs font-medium text-blue-600">
            已完成 {completedCount} / {questionCount}
          </div>
        </div>

        {questionCount > 1 && (
          <div
            className="mb-4 flex flex-wrap gap-2"
            role="tablist"
            aria-label="待回答问题列表"
          >
            {pending.questions.map((question, index) => (
              <button
                key={`${question.question}-${index}`}
                type="button"
                id={`ask-user-question-tab-${index}`}
                role="tab"
                aria-selected={index === activeIndex}
                aria-controls={`ask-user-question-panel-${index}`}
                onClick={() => setActiveIndex(index)}
                className={`inline-flex min-w-0 items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs font-medium transition-colors ${getTabStyle(index)}`}
              >
                <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/80 text-[11px] font-semibold">
                  {index + 1}
                </span>
                <span className="min-w-0 truncate">
                  {question.header || question.question}
                </span>
                {completionMap[index] && (
                  <span className="shrink-0 text-[11px] font-semibold">
                    {skippedMap[index] ? "已跳过" : "已答"}
                  </span>
                )}
                {errors[index] && (
                  <span className="shrink-0 text-[11px] font-semibold">未完成</span>
                )}
              </button>
            ))}
          </div>
        )}

        {activeQuestion && (
          <section
            id={`ask-user-question-panel-${activeIndex}`}
            role="tabpanel"
            aria-labelledby={`ask-user-question-tab-${activeIndex}`}
            className={getSectionStyle(activeQuestion.question_type)}
          >
            <div className="mb-2">
              {activeQuestion.question_type === "risk_confirmation" && (
                <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-red-600">
                  <span>⚠️</span>
                  <span>此操作不可逆，请谨慎确认</span>
                </div>
              )}
              {activeQuestion.context && (
                <div className="mb-1 text-xs text-slate-500 dark:text-slate-400">{activeQuestion.context}</div>
              )}
              {activeQuestion.header && (
                <div className="text-xs font-medium text-slate-500 dark:text-slate-400">{activeQuestion.header}</div>
              )}
              <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{activeQuestion.question}</div>
            </div>

            {isActiveSkipped && (
              <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                当前问题已跳过；你仍可返回补充回答。
              </div>
            )}

            <div className="space-y-2">
              {activeQuestion.options.map((option) => {
                const checked = (selectedMap[activeIndex] || []).includes(option.label);
                return (
                  <label
                    key={option.label}
                    className={getOptionStyle(activeQuestion.question_type, checked)}
                  >
                    <input
                      type={activeQuestion.multiSelect ? "checkbox" : "radio"}
                      name={`ask-q-${activeIndex}`}
                      checked={checked}
                      onChange={() =>
                        activeQuestion.multiSelect
                          ? toggleMultiOption(activeIndex, option.label)
                          : setSingleOption(activeIndex, option.label)
                      }
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm text-slate-800 dark:text-slate-200">{option.label}</span>
                      <span className="block text-xs text-slate-500 dark:text-slate-400">{option.description}</span>
                    </span>
                  </label>
                );
              })}
            </div>

            {activeQuestion.allowTextInput !== false && (
              <div className="mt-2">
                <input
                  value={textMap[activeIndex] || ""}
                  onChange={(event) => setTextAnswer(activeIndex, event.target.value)}
                  placeholder="或输入自定义回答"
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 px-3 py-2 text-sm outline-none focus:border-blue-400"
                />
              </div>
            )}

            {errors[activeIndex] && (
              <div className="mt-2 text-xs text-red-600">{errors[activeIndex]}</div>
            )}
          </section>
        )}

        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveIndex((prev) => Math.max(0, prev - 1))}
              disabled={activeIndex === 0}
              className="rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              上一题
            </button>
            <button
              type="button"
              onClick={() => setActiveIndex((prev) => Math.min(questionCount - 1, prev + 1))}
              disabled={activeIndex === questionCount - 1}
              className="rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              下一题
            </button>
            {!completionMap[activeIndex] && (
              <button
                type="button"
                onClick={skipCurrentQuestion}
                className="rounded-lg px-2 py-1 text-xs font-medium text-slate-400 dark:text-slate-500 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-300"
              >
                跳过此题
              </button>
            )}
          </div>
          <div className="flex flex-col items-end gap-1">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!isAllCompleted}
              className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              提交回答并继续
            </button>
            {!isAllCompleted && (
              <div className="text-[11px] text-slate-400 dark:text-slate-500">
                还需完成 {questionCount - completedCount} 题后才可提交
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
