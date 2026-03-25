import { useEffect, useMemo, useState } from "react";
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

export default function RecipeCenter() {
  const recipes = useStore((s) => s.recipes);
  const recipesLoaded = useStore((s) => s.recipesLoaded);
  const sendMessage = useStore((s) => s.sendMessage);
  const isStreaming = useStore((s) => s.isStreaming);
  const [selectedRecipeId, setSelectedRecipeId] = useState<string | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});

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

  if (!recipesLoaded) {
    return (
      <div className="rounded-[28px] border border-slate-200/80 bg-white/85 p-6 text-sm text-slate-500 shadow-sm">
        正在加载 Recipe Center...
      </div>
    );
  }

  if (recipes.length === 0 || !selectedRecipe) {
    return null;
  }

  return (
    <div className="rounded-[28px] border border-slate-200/80 bg-white/90 p-5 shadow-[0_18px_45px_-32px_rgba(15,23,42,0.45)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-700">
            Recipe Center
          </div>
          <h2 className="mt-2 text-xl font-semibold text-slate-900">从高频科研任务直接开始</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            先用模板收敛问题，再进入自由对话。MVP 阶段提供 3 个稳定入口。
          </p>
        </div>
        <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
          自由对话仍然可用
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {recipes.map((recipe) => {
          const selected = recipe.recipe_id === selectedRecipe.recipe_id;
          return (
            <button
              key={recipe.recipe_id}
              type="button"
              onClick={() => setSelectedRecipeId(recipe.recipe_id)}
              className={`rounded-3xl border px-4 py-4 text-left transition ${
                selected
                  ? "border-emerald-500 bg-emerald-50/80 shadow-sm"
                  : "border-slate-200 bg-slate-50/70 hover:border-slate-300 hover:bg-white"
              }`}
            >
              <div className="text-sm font-semibold text-slate-900">{recipe.name}</div>
              <p className="mt-2 text-xs leading-5 text-slate-600">{recipe.summary}</p>
              <div className="mt-3 text-[11px] text-slate-500">
                输出：
                {recipe.default_outputs.map((output) => output.label).join(" / ")}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-5 grid gap-5 rounded-3xl border border-slate-200 bg-slate-50/70 p-4 md:grid-cols-[1.2fr_0.8fr]">
        <div>
          <div className="text-sm font-semibold text-slate-900">{selectedRecipe.name}</div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{selectedRecipe.scenario}</p>
          <div className="mt-4 space-y-3">
            {selectedRecipe.input_fields.map((field) => (
              <label key={field.key} className="block">
                <div className="mb-1 text-xs font-medium text-slate-700">
                  {field.label}
                  {field.required ? " *" : ""}
                </div>
                <input
                  value={inputs[field.key] ?? ""}
                  onChange={(event) =>
                    setInputs((prev) => ({ ...prev, [field.key]: event.target.value }))
                  }
                  placeholder={field.placeholder || field.example}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
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
              className="rounded-2xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              以模板启动
            </button>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-xs leading-5 text-slate-500">
              示例：{selectedRecipe.example_input}
            </div>
          </div>
        </div>

        <div className="rounded-3xl bg-white p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            执行步骤
          </div>
          <div className="mt-3 space-y-3">
            {selectedRecipe.steps.map((step, index) => (
              <div key={step.id} className="rounded-2xl border border-slate-200 px-3 py-3">
                <div className="text-xs font-semibold text-emerald-700">Step {index + 1}</div>
                <div className="mt-1 text-sm font-medium text-slate-900">{step.title}</div>
                <div className="mt-1 text-xs leading-5 text-slate-500">{step.description}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
