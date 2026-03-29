import { useCallback, useEffect, useMemo, useRef, useState, startTransition } from "react";
import { useStore } from "../store";
import Button from "./ui/Button";

function buildRecipePrompt(
 recipeName: string,
 inputEntries: ReadonlyArray<readonly [string, string]>,
 exampleInput: string,
): string {
 if (inputEntries.length === 0) {
 return exampleInput || `请按「${recipeName}」模板帮我推进。`;
 }
 const summary = inputEntries.map(([label, value]) => `${label}：${value}`).join("；");
 return `请按「${recipeName}」模板帮我推进。${summary}`;
}

/** 焦点环 — 统一 focus-visible 样式 */
const focusRing =
 "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]";

export default function RecipeCenter() {
 const recipes = useStore((s) => s.recipes);
 const recipesLoaded = useStore((s) => s.recipesLoaded);
 const sendMessage = useStore((s) => s.sendMessage);
 const isStreaming = useStore((s) => s.isStreaming);
 const [selectedRecipeId, setSelectedRecipeId] = useState<string | null>(null);
 const [inputs, setInputs] = useState<Record<string, string>>({});

 // 卡片按钮引用数组，用于键盘导航
 const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);

 useEffect(() => {
 if (selectedRecipeId || recipes.length === 0) return;
 setSelectedRecipeId(recipes[0].recipe_id);
 }, [recipes, selectedRecipeId]);

 const selectedRecipe = useMemo(
 () => recipes.find((recipe) => recipe.recipe_id === selectedRecipeId) ?? recipes[0] ?? null,
 [recipes, selectedRecipeId],
 );

 useEffect(() => {
 if (!selectedRecipe) return;
 setInputs((prev) => {
 const next: Record<string, string> = {};
 for (const field of selectedRecipe.input_fields) {
 next[field.key] = prev[field.key] ?? "";
 }
 return next;
 });
 }, [selectedRecipe]);

 /** 方向键在 recipe 卡片之间导航 */
 const handleCardKeyDown = useCallback(
 (e: React.KeyboardEvent, index: number) => {
 let next = -1;
 if (e.key === "ArrowRight" || e.key === "ArrowDown") {
 e.preventDefault();
 next = (index + 1) % recipes.length;
 } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
 e.preventDefault();
 next = (index - 1 + recipes.length) % recipes.length;
 }
 if (next >= 0) {
 setSelectedRecipeId(recipes[next].recipe_id);
 cardRefs.current[next]?.focus();
 }
 },
 [recipes],
 );

 /** Ctrl/Cmd+Enter 提交 */
 const handleFormKeyDown = useCallback(
 (e: React.KeyboardEvent) => {
 if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && selectedRecipe && !isStreaming) {
 e.preventDefault();
 const filledEntries = selectedRecipe.input_fields
 .map((field) => [field.label, (inputs[field.key] ?? "").trim()] as const)
 .filter(([, value]) => value);
 const prompt = buildRecipePrompt(
 selectedRecipe.name,
 filledEntries,
 selectedRecipe.example_input,
 );
 startTransition(() => {
 void sendMessage(prompt, {
 recipeId: selectedRecipe.recipe_id,
 recipeInputs: inputs,
 });
 });
 }
 },
 [selectedRecipe, isStreaming, inputs, sendMessage],
 );

 if (!recipesLoaded) {
 return (
 <div
 role="status"
 className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)]/85 p-6 text-sm text-[var(--text-secondary)]"
 >
 正在加载 Recipe Center...
 </div>
 );
 }

 if (recipes.length === 0 || !selectedRecipe) {
 return null;
 }

 return (
 <section aria-label="Recipe Center" className="relative">
 {/* Skip-nav：跳过 Recipe Center 直达聊天输入 */}
 <a
 href="#chat-input"
 className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-lg focus:bg-[var(--accent)] focus:px-3 focus:py-1.5 focus:text-sm focus:text-white focus:shadow-md"
 >
 跳过模板选择，直达输入框
 </a>

 <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)]/90 dark:bg-[var(--bg-elevated)] p-5 shadow-sm">
 <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
 <div>
 <div className="text-xs font-medium uppercase tracking-[0.18em] text-[var(--text-muted)]">
 Recipe Center
 </div>
 <h2 className="mt-1.5 text-lg font-semibold text-[var(--text-primary)]">从高频科研任务直接开始</h2>
 <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
 先用模板收敛问题，再进入自由对话。
 </p>
 </div>
 <div className="rounded-full border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1 text-xs text-[var(--text-secondary)]">
 自由对话仍然可用
 </div>
 </div>

 <div role="tablist" aria-label="选择模板" className="mt-4 grid gap-2 sm:grid-cols-2 md:grid-cols-3">
 {recipes.map((recipe, index) => {
 const selected = recipe.recipe_id === selectedRecipe.recipe_id;
 return (
 <button
          key={recipe.recipe_id}
          ref={(el) => { cardRefs.current[index] = el; }}
          type="button"
          role="tab"
          aria-selected={selected}
          onClick={() => setSelectedRecipeId(recipe.recipe_id)}
          onKeyDown={(e) => handleCardKeyDown(e, index)}
          className={`flex flex-col rounded-xl border px-3.5 py-3.5 text-left transition-colors ${focusRing} ${
            selected
              ? "border-[var(--domain-profile)] bg-[var(--accent-subtle)] ring-1 ring-[var(--domain-profile)]"
              : "border-[var(--border-default)] bg-[var(--bg-base)] hover:border-[var(--border-default)] hover:bg-[var(--bg-hover)]"
          }`}
        >
 <div className="text-sm font-semibold text-[var(--text-primary)]">{recipe.name}</div>
 <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{recipe.summary}</p>
 <div className="mt-3 text-[11px] text-[var(--text-secondary)]">
 输出：
 {recipe.default_outputs.map((output) => output.label).join(" /")}
 </div>
 </button>
 );
 })}
 </div>

 <div
 role="tabpanel"
 aria-label={`${selectedRecipe.name} 详情`}
 onKeyDown={handleFormKeyDown}
 className="mt-4 grid gap-5 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)]/40 p-4 md:grid-cols-[1.2fr_0.8fr]"
 >
 <div>
 <div className="text-sm font-medium text-[var(--text-primary)]">{selectedRecipe.name}</div>
 <p className="mt-1.5 text-sm leading-6 text-[var(--text-secondary)]">{selectedRecipe.scenario}</p>
 <div className="mt-4 space-y-3">
 {selectedRecipe.input_fields.map((field) => (
 <label key={field.key} className="block">
 <div className="mb-1 text-xs font-medium text-[var(--text-secondary)]">
 {field.label}
 {field.required ? (
 <span aria-label="必填" className="text-[var(--error)]"> *</span>
 ) : null}
 </div>
 <input
 value={inputs[field.key] ?? ""}
 onChange={(event) =>
 setInputs((prev) => ({ ...prev, [field.key]: event.target.value }))
 }
 placeholder={field.placeholder || field.example}
 aria-required={field.required || undefined}
 className={`w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition ${focusRing}`}
 />
 </label>
 ))}
 </div>
 <div className="mt-4 flex flex-wrap gap-3">
 <Button
 variant="primary"
 type="button"
 disabled={isStreaming}
 onClick={() => {
 const filledEntries = selectedRecipe.input_fields
 .map((field) => [field.label, (inputs[field.key] ?? "").trim()] as const)
 .filter(([, value]) => value);
 const prompt = buildRecipePrompt(
 selectedRecipe.name,
 filledEntries,
 selectedRecipe.example_input,
 );
 startTransition(() => {
 void sendMessage(prompt, {
 recipeId: selectedRecipe.recipe_id,
 recipeInputs: inputs,
 });
 });
 }}
 className="px-4 py-2 text-sm"
 >
 以模板启动
 </Button>
 <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/50 px-4 py-2 text-xs leading-5 text-[var(--text-muted)]">
 示例：{selectedRecipe.example_input}
 </div>
 </div>
 </div>

 <div className="p-1">
 <div className="text-xs font-medium uppercase tracking-[0.14em] text-[var(--text-muted)]">
 执行步骤
 </div>
 <ol className="mt-3 space-y-2">
 {selectedRecipe.steps.map((step, index) => (
 <li key={step.id} className="rounded-lg px-3 py-2.5">
 <div className="text-xs font-medium text-[var(--text-muted)]">Step {index + 1}</div>
 <div className="mt-0.5 text-sm font-medium text-[var(--text-secondary)]">{step.title}</div>
 <div className="mt-0.5 text-xs leading-5 text-[var(--text-muted)]">{step.description}</div>
 </li>
 ))}
 </ol>
 </div>
 </div>
 </div>
 </section>
 );
}
