import { useEffect, useMemo, useState, startTransition } from "react";
import type { PendingAskUserQuestion, QuestionType } from "../store";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import Button from "./ui/Button";

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
 answer = parts.join(",");
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
 startTransition(() => {
 onSubmit(answers);
 });
 };

 // 根据 question_type 计算每个问题的容器样式
 function getSectionStyle(questionType?: QuestionType): string {
 if (questionType === "risk_confirmation") {
 return "rounded-xl border border-[var(--error)] bg-[var(--error-subtle)] p-3";
 }
 return "rounded-xl border border-[var(--border-default)] p-3";
 }

 // 根据 question_type 计算选项按钮样式
 function getOptionStyle(questionType?: QuestionType, checked?: boolean): string {
 const isEmphasis =
 questionType === "approach_choice" || questionType === "ambiguous_requirement";
 if (isEmphasis) {
 return checked
 ? "flex cursor-pointer items-start gap-2 rounded-lg border border-[var(--accent)] bg-[var(--accent-subtle)] px-2.5 py-2"
 : "flex cursor-pointer items-start gap-2 rounded-lg border border-[var(--accent-subtle)] px-2.5 py-2 hover:bg-[var(--accent-subtle)]";
 }
 return "flex cursor-pointer items-start gap-2 rounded-lg border border-[var(--border-default)] px-2.5 py-2 hover:bg-[var(--bg-elevated)]";
 }

 function getTabStyle(index: number): string {
 if (errors[index]) {
 return "border-[var(--error)] bg-[var(--error-subtle)] text-[var(--error)] shadow-sm";
 }
 if (index === activeIndex) {
 return "border-[var(--accent)] bg-[var(--bg-base)] text-[var(--text-primary)] shadow-[0_10px_24px_rgba(13,148,136,0.14)] ring-1 ring-[color-mix(in_srgb,var(--accent)_18%,transparent)]";
 }
 if (skippedMap[index]) {
 return "border-[var(--warning)] bg-[var(--warning-subtle)] text-[var(--warning)]";
 }
 if (completionMap[index]) {
 return "border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]";
 }
 return "border-[var(--border-default)] bg-[var(--bg-elevated)]/70 text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-base)]";
 }

 function getTabNumberStyle(index: number): string {
 if (errors[index]) {
 return "bg-[var(--error-subtle)] text-[var(--error)]";
 }
 if (index === activeIndex) {
 return "bg-[var(--accent)] text-white shadow-sm";
 }
 if (skippedMap[index]) {
 return "bg-[var(--warning-subtle)] text-[var(--warning)]";
 }
 if (completionMap[index]) {
 return "bg-[var(--success-subtle)] text-[var(--success)]";
 }
 return "bg-[var(--bg-base)] text-[var(--text-secondary)]";
 }

 function getTabStatus(index: number): string {
 if (errors[index]) return "待完成";
 if (index === activeIndex) return "当前";
 if (skippedMap[index]) return "已跳过";
 if (completionMap[index]) return "已答";
 return "待答";
 }

 function getTabStatusStyle(index: number): string {
 if (errors[index]) {
 return "border-[var(--error)] bg-[var(--error-subtle)] text-[var(--error)]";
 }
 if (index === activeIndex) {
 return "border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]";
 }
 if (skippedMap[index]) {
 return "border-[var(--warning)] bg-[var(--warning-subtle)] text-[var(--warning)]";
 }
 if (completionMap[index]) {
 return "border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]";
 }
 return "border-[var(--border-default)] bg-[var(--bg-base)] text-[var(--text-muted)]";
 }

 return (
 <div className="border-t border-[var(--accent-subtle)] bg-[var(--accent-subtle)]/60 px-4 py-3">
 <div className="mx-auto max-w-3xl rounded-lg border border-[var(--accent-subtle)] bg-[var(--bg-base)] p-4 shadow-sm">
 <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
 <div className="text-sm font-semibold text-[var(--accent)]">
 需要你补充 {questionCount} 个信息点，回答后继续执行
 </div>
 <div className="text-xs font-medium text-[var(--accent)]">
 已完成 {completedCount} / {questionCount}
 </div>
 </div>

 {questionCount > 1 && (
 <div className="mb-4 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/70 p-2">
 <div
 className="flex flex-wrap gap-2"
 role="tablist"
 aria-label="待回答问题列表"
 >
 {pending.questions.map((question, index) => (
 <Button
 key={`${question.question}-${index}`}
 variant="ghost"
 type="button"
 id={`ask-user-question-tab-${index}`}
 role="tab"
 aria-selected={index === activeIndex}
 aria-current={index === activeIndex ? "step" : undefined}
 aria-controls={`ask-user-question-panel-${index}`}
 onClick={() => setActiveIndex(index)}
 className={`group inline-flex min-w-0 flex-1 items-start gap-3 rounded-2xl border px-3 py-3 text-left text-xs font-medium transition-all duration-150 sm:min-w-[11rem] ${getTabStyle(index)}`}
 >
 <span
 className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold transition-colors ${getTabNumberStyle(index)}`}
 >
 {completionMap[index] && !skippedMap[index] && index !== activeIndex ? (
 <CheckCircle2 size={14} aria-hidden="true" />
 ) : (
 index + 1
 )}
 </span>
 <span className="min-w-0 flex-1">
 <span className="block truncate text-sm font-semibold text-inherit">
 {question.header || question.question}
 </span>
 <span className="mt-1 block truncate text-[11px] text-[var(--text-secondary)]">
 {index === activeIndex ? "正在处理这个问题" : question.question}
 </span>
 </span>
 <span
 className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getTabStatusStyle(index)}`}
 >
 {getTabStatus(index)}
 </span>
 </Button>
 ))}
 </div>
 <div className="mt-2 flex items-center justify-between px-1 text-[11px] text-[var(--text-secondary)]">
 <span>
 当前处理：{activeQuestion.header || activeQuestion.question}
 </span>
 <span>点击任意问题可切换</span>
 </div>
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
 {questionCount > 1 && (
 <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-[var(--accent-subtle)] bg-[var(--accent-subtle)] px-2.5 py-1 text-[11px] font-semibold text-[var(--accent)]">
 <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--bg-base)] px-1.5 text-[10px]">
 第 {activeIndex + 1} 题
 </span>
 <span>当前问题</span>
 </div>
 )}
 {activeQuestion.question_type === "risk_confirmation" && (
 <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-[var(--error)]">
 <AlertTriangle size={14} />
 <span>此操作不可逆，请谨慎确认</span>
 </div>
 )}
 {activeQuestion.context && (
 <div className="mb-1 text-xs text-[var(--text-secondary)]">{activeQuestion.context}</div>
 )}
 {activeQuestion.header && (
 <div className="text-xs font-medium text-[var(--text-secondary)]">{activeQuestion.header}</div>
 )}
 <div className="text-sm font-medium text-[var(--text-primary)]">{activeQuestion.question}</div>
 </div>

 {isActiveSkipped && (
 <div className="mb-3 rounded-lg border border-[var(--warning)] bg-[var(--accent-subtle)] px-3 py-2 text-xs text-[var(--warning)]">
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
 <span className="block text-sm text-[var(--text-primary)]">{option.label}</span>
 <span className="block text-xs text-[var(--text-secondary)]">{option.description}</span>
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
 className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] text-[var(--text-primary)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
 />
 </div>
 )}

 {errors[activeIndex] && (
 <div className="mt-2 text-xs text-[var(--error)]">{errors[activeIndex]}</div>
 )}
 </section>
 )}

 <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
 <div className="flex items-center gap-2">
 <Button
 variant="secondary"
 type="button"
 onClick={() => setActiveIndex((prev) => Math.max(0, prev - 1))}
 disabled={activeIndex === 0}
 className="rounded-xl px-3 py-2 text-sm font-medium"
 >
 上一题
 </Button>
 <Button
 variant="secondary"
 type="button"
 onClick={() => setActiveIndex((prev) => Math.min(questionCount - 1, prev + 1))}
 disabled={activeIndex === questionCount - 1}
 className="rounded-xl px-3 py-2 text-sm font-medium"
 >
 下一题
 </Button>
 {!completionMap[activeIndex] && (
 <Button
 variant="ghost"
 type="button"
 onClick={skipCurrentQuestion}
 className="rounded-lg px-2 py-1 text-xs font-medium"
 >
 跳过此题
 </Button>
 )}
 </div>
 <div className="flex flex-col items-end gap-1">
 <Button
 variant="primary"
 type="button"
 onClick={handleSubmit}
 disabled={!isAllCompleted}
 className="rounded-xl px-4 py-2 text-sm font-medium"
 >
 提交回答并继续
 </Button>
 {!isAllCompleted && (
 <div className="text-[11px] text-[var(--text-muted)]">
 还需完成 {questionCount - completedCount} 题后才可提交
 </div>
 )}
 </div>
 </div>
 </div>
 </div>
 );
}
