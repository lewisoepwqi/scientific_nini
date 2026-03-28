import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../store";

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
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 dark:focus-visible:ring-slate-500";

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
        void sendMessage(prompt, {
          recipeId: selectedRecipe.recipe_id,
          recipeInputs: inputs,
        });
      }
    },
    [selectedRecipe, isStreaming, inputs, sendMessage],
  );

  if (!recipesLoaded) {
    return (
      <div
        role="status"
        className="rounded-xl border border-slate-200/80 dark:border-slate-700 bg-white/85 dark:bg-slate-800 p-6 text-sm text-slate-500 dark:text-slate-400"
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
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-lg focus:bg-slate-800 focus:px-3 focus:py-1.5 focus:text-sm focus:text-white focus:shadow-md"
      >
        跳过模板选择，直达输入框
      </a>

      <div className="rounded-xl border border-slate-200/60 dark:border-slate-700/60 bg-white/90 dark:bg-slate-900 p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
              Recipe Center
            </div>
            <h2 className="mt-1.5 text-lg font-semibold text-slate-800 dark:text-slate-200">从高频科研任务直接开始</h2>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">
              先用模板收敛问题，再进入自由对话。
            </p>
          </div>
          <div className="rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-1 text-xs text-slate-500 dark:text-slate-400">
            自由对话仍然可用
          </div>
        </div>

        <div role="tablist" aria-label="选择模板" className="mt-4 grid gap-2 md:grid-cols-3">
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
                className={`rounded-xl border px-3.5 py-3.5 text-left transition ${focusRing} ${
                  selected
                    ? "border-slate-300 dark:border-slate-500 bg-slate-50 dark:bg-slate-800"
                    : "border-slate-200/80 dark:border-slate-700/60 bg-transparent hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50/50 dark:hover:bg-slate-800/50"
                }`}
              >
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{recipe.name}</div>
                <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-400">{recipe.summary}</p>
                <div className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
                  输出：
                  {recipe.default_outputs.map((output) => output.label).join(" / ")}
                </div>
              </button>
            );
          })}
        </div>

        <div
          role="tabpanel"
          aria-label={`${selectedRecipe.name} 详情`}
          onKeyDown={handleFormKeyDown}
          className="mt-4 grid gap-5 rounded-xl border border-slate-200/60 dark:border-slate-700/60 bg-slate-50/40 dark:bg-slate-800/40 p-4 md:grid-cols-[1.2fr_0.8fr]"
        >
          <div>
            <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{selectedRecipe.name}</div>
            <p className="mt-1.5 text-sm leading-6 text-slate-500 dark:text-slate-400">{selectedRecipe.scenario}</p>
            <div className="mt-4 space-y-3">
              {selectedRecipe.input_fields.map((field) => (
                <label key={field.key} className="block">
                  <div className="mb-1 text-xs font-medium text-slate-700 dark:text-slate-300">
                    {field.label}
                    {field.required ? (
                      <span aria-label="必填" className="text-red-400 dark:text-red-500"> *</span>
                    ) : null}
                  </div>
                  <input
                    value={inputs[field.key] ?? ""}
                    onChange={(event) =>
                      setInputs((prev) => ({ ...prev, [field.key]: event.target.value }))
                    }
                    placeholder={field.placeholder || field.example}
                    aria-required={field.required || undefined}
                    className={`w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-200 outline-none transition ${focusRing}`}
                  />
                </label>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
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
                  void sendMessage(prompt, {
                    recipeId: selectedRecipe.recipe_id,
                    recipeInputs: inputs,
                  });
                }}
                className={`rounded-lg bg-slate-800 dark:bg-slate-200 px-4 py-2 text-sm font-medium text-white dark:text-slate-900 transition hover:bg-slate-700 dark:hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-60 ${focusRing}`}
              >
                以模板启动
              </button>
              <div className="rounded-lg border border-slate-200/80 dark:border-slate-700/60 bg-white dark:bg-slate-800 px-4 py-2 text-xs leading-5 text-slate-400 dark:text-slate-500">
                示例：{selectedRecipe.example_input}
              </div>
            </div>
          </div>

          <div className="p-1">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              执行步骤
            </div>
            <ol className="mt-3 space-y-2">
              {selectedRecipe.steps.map((step, index) => (
                <li key={step.id} className="rounded-lg px-3 py-2.5">
                  <div className="text-xs font-medium text-slate-400 dark:text-slate-500">Step {index + 1}</div>
                  <div className="mt-0.5 text-sm font-medium text-slate-700 dark:text-slate-300">{step.title}</div>
                  <div className="mt-0.5 text-xs leading-5 text-slate-400 dark:text-slate-500">{step.description}</div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
