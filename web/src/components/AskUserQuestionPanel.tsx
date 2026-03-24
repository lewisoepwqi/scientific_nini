import { useEffect, useMemo, useState } from "react";
import type { PendingAskUserQuestion, QuestionType } from "../store";

interface AskUserQuestionPanelProps {
  pending: PendingAskUserQuestion;
  onSubmit: (answers: Record<string, string>) => void;
}

export default function AskUserQuestionPanel({
  pending,
  onSubmit,
}: AskUserQuestionPanelProps) {
  const [selectedMap, setSelectedMap] = useState<Record<number, string[]>>({});
  const [textMap, setTextMap] = useState<Record<number, string>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});

  useEffect(() => {
    setSelectedMap({});
    setTextMap({});
    setErrors({});
  }, [pending.toolCallId]);

  const questionCount = pending.questions.length;

  const canSubmit = useMemo(() => {
    return pending.questions.every((question, index) => {
      const selected = selectedMap[index] || [];
      const text = (textMap[index] || "").trim();
      if (question.multiSelect) return selected.length > 0 || Boolean(text);
      return Boolean(selected[0]) || Boolean(text);
    });
  }, [pending.questions, selectedMap, textMap]);

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
    setErrors((prev) => ({ ...prev, [questionIndex]: "" }));
  };

  const setSingleOption = (questionIndex: number, label: string) => {
    setSelectedMap((prev) => ({ ...prev, [questionIndex]: [label] }));
    setErrors((prev) => ({ ...prev, [questionIndex]: "" }));
  };

  const setTextAnswer = (questionIndex: number, value: string) => {
    setTextMap((prev) => ({ ...prev, [questionIndex]: value }));
    if (value.trim()) {
      setErrors((prev) => ({ ...prev, [questionIndex]: "" }));
    }
  };

  const handleSubmit = () => {
    const nextErrors: Record<number, string> = {};
    const answers: Record<string, string> = {};

    pending.questions.forEach((question, index) => {
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
      return;
    }
    onSubmit(answers);
  };

  // 根据 question_type 计算每个问题的容器样式
  function getSectionStyle(questionType?: QuestionType): string {
    if (questionType === "risk_confirmation") {
      return "rounded-xl border border-red-300 bg-red-50/40 p-3";
    }
    return "rounded-xl border border-gray-200 p-3";
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
    return "flex cursor-pointer items-start gap-2 rounded-lg border border-gray-200 px-2.5 py-2 hover:bg-gray-50";
  }

  return (
    <div className="border-t border-blue-100 bg-blue-50/60 px-4 py-3">
      <div className="mx-auto max-w-3xl rounded-2xl border border-blue-200 bg-white p-4 shadow-sm">
        <div className="mb-3 text-sm font-semibold text-blue-700">
          需要你补充 {questionCount} 个信息点，回答后继续执行
        </div>

        <div className="space-y-4">
          {pending.questions.map((question, index) => {
            const selected = selectedMap[index] || [];
            const text = textMap[index] || "";
            const isRisk = question.question_type === "risk_confirmation";
            return (
              <section key={`${question.question}-${index}`} className={getSectionStyle(question.question_type)}>
                <div className="mb-2">
                  {isRisk && (
                    <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-red-600">
                      <span>⚠️</span>
                      <span>此操作不可逆，请谨慎确认</span>
                    </div>
                  )}
                  {question.context && (
                    <div className="mb-1 text-xs text-gray-500">{question.context}</div>
                  )}
                  {question.header && (
                    <div className="text-xs font-medium text-gray-500">{question.header}</div>
                  )}
                  <div className="text-sm font-medium text-gray-900">{question.question}</div>
                </div>

                <div className="space-y-2">
                  {question.options.map((option) => {
                    const checked = selected.includes(option.label);
                    return (
                      <label
                        key={option.label}
                        className={getOptionStyle(question.question_type, checked)}
                      >
                        <input
                          type={question.multiSelect ? "checkbox" : "radio"}
                          name={`ask-q-${index}`}
                          checked={checked}
                          onChange={() =>
                            question.multiSelect
                              ? toggleMultiOption(index, option.label)
                              : setSingleOption(index, option.label)
                          }
                          className="mt-1"
                        />
                        <span>
                          <span className="block text-sm text-gray-800">{option.label}</span>
                          <span className="block text-xs text-gray-500">{option.description}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>

                {question.allowTextInput !== false && (
                  <div className="mt-2">
                    <input
                      value={text}
                      onChange={(event) => setTextAnswer(index, event.target.value)}
                      placeholder="或输入自定义回答"
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
                    />
                  </div>
                )}

                {errors[index] && (
                  <div className="mt-2 text-xs text-red-600">{errors[index]}</div>
                )}
              </section>
            );
          })}
        </div>

        <div className="mt-4 flex justify-end">
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            提交回答并继续
          </button>
        </div>
      </div>
    </div>
  );
}
