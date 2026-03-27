/**
 * 凭证管理 Tab —— 仅负责 API Key、Base URL 的录入与测试连接。
 * 不涉及模型选择或策略配置。
 * 数据从 store.modelProviders 读取，不自行 fetch。
 */
import { useState, useCallback, useEffect, useRef } from "react";
import {
  CheckCircle,
  XCircle,
  Loader2,
  Edit3,
  Save,
  Search,
  ChevronDown,
  Trash2,
} from "lucide-react";
import { useStore } from "../../store";
import { deleteProviderConfig } from "../../store/api-actions";
import type { SaveStatus, TestResult } from "./types";

interface EditForm {
  api_key: string;
  base_url: string;
}

type ProviderFilter = "all" | "configured" | "unconfigured";

const FILTER_OPTIONS: { value: ProviderFilter; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "configured", label: "仅已配置" },
  { value: "unconfigured", label: "仅未配置" },
];

function sourceLabel(s: string) {
  if (s === "db") return "用户配置";
  if (s === "env") return "环境变量";
  return "未配置";
}

function apiModeLabel(apiMode?: string | null) {
  if (apiMode === "standard") return "普通";
  if (apiMode === "coding_plan") return "Coding Plan";
  if (apiMode === "unknown") return "未知";
  return "未设置";
}

interface CredentialsTabProps {
  onConfigSaved: () => void;
}

export default function CredentialsTab({ onConfigSaved }: CredentialsTabProps) {
  const modelProviders = useStore((s) => s.modelProviders);
  const modelProvidersLoading = useStore((s) => s.modelProvidersLoading);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm>({
    api_key: "",
    base_url: "",
  });
  const [saveStatus, setSaveStatus] = useState<Record<string, SaveStatus>>({});
  const [testResults, setTestResults] = useState<Record<string, TestResult>>(
    {},
  );
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [providerQuery, setProviderQuery] = useState("");
  const [providerFilter, setProviderFilter] = useState<ProviderFilter>("all");
  const [filterDropdownOpen, setFilterDropdownOpen] = useState(false);
  const [dynamicModelCounts, setDynamicModelCounts] = useState<
    Record<string, { loading: boolean; count: number | null }>
  >({});
  const filterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (filterRef.current && !filterRef.current.contains(e.target as Node)) {
        setFilterDropdownOpen(false);
      }
    }
    if (filterDropdownOpen) {
      document.addEventListener("mousedown", handleClick);
      return () => document.removeEventListener("mousedown", handleClick);
    }
  }, [filterDropdownOpen]);

  const fetchModelCount = useCallback(
    async (providerId: string) => {
      if (
        dynamicModelCounts[providerId]?.count !== null &&
        dynamicModelCounts[providerId]?.count !== undefined
      )
        return;
      setDynamicModelCounts((prev) => ({
        ...prev,
        [providerId]: { loading: true, count: null },
      }));
      try {
        const resp = await fetch(`/api/models/${providerId}/available`);
        const data = await resp.json();
        const count =
          data.success && data.data?.models
            ? (data.data.models as string[]).length
            : null;
        setDynamicModelCounts((prev) => ({
          ...prev,
          [providerId]: { loading: false, count },
        }));
      } catch {
        setDynamicModelCounts((prev) => ({
          ...prev,
          [providerId]: { loading: false, count: null },
        }));
      }
    },
    [dynamicModelCounts],
  );

  const handleExpand = useCallback(
    (providerId: string, isExpanded: boolean) => {
      if (isExpanded) {
        setExpandedId(null);
      } else {
        setExpandedId(providerId);
        void fetchModelCount(providerId);
      }
    },
    [fetchModelCount],
  );

  const startEdit = useCallback((p: { id: string; base_url: string }) => {
    setEditingId(p.id);
    setExpandedId(p.id);
    setEditForm({
      api_key: "",
      base_url: p.base_url || "",
    });
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
  }, []);

  const handleSave = useCallback(
    async (providerId: string) => {
      setSaveStatus((prev) => ({ ...prev, [providerId]: { loading: true } }));
      try {
        const normalizedApiKey = editForm.api_key.trim();
        const body: Record<string, unknown> = {
          provider_id: providerId,
          base_url: editForm.base_url || undefined,
        };
        if (normalizedApiKey) {
          body.api_key = normalizedApiKey;
        }

        const resp = await fetch("/api/models/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await resp.json();

        if (data.success) {
          setSaveStatus((prev) => ({
            ...prev,
            [providerId]: {
              loading: false,
              success: true,
              message: "配置已保存并生效",
            },
          }));
          setEditingId(null);
          await fetchActiveModel();
          window.dispatchEvent(new Event("nini:model-config-updated"));
          onConfigSaved();
        } else {
          setSaveStatus((prev) => ({
            ...prev,
            [providerId]: {
              loading: false,
              success: false,
              message: data.error || "保存失败",
            },
          }));
        }
      } catch (e) {
        setSaveStatus((prev) => ({
          ...prev,
          [providerId]: {
            loading: false,
            success: false,
            message: `请求失败: ${e}`,
          },
        }));
      }
    },
    [editForm, fetchActiveModel, onConfigSaved],
  );

  const handleTest = useCallback(async (providerId: string) => {
    setTestResults((prev) => ({ ...prev, [providerId]: { loading: true } }));
    try {
      const resp = await fetch(`/api/models/${providerId}/test`, {
        method: "POST",
      });
      const data = await resp.json();
      setTestResults((prev) => ({
        ...prev,
        [providerId]: {
          loading: false,
          success: data.success,
          message: data.success ? data.data?.message : data.error,
        },
      }));
    } catch (e) {
      setTestResults((prev) => ({
        ...prev,
        [providerId]: {
          loading: false,
          success: false,
          message: `请求失败: ${e}`,
        },
      }));
    }
  }, []);

  const handleDelete = useCallback(
    async (providerId: string) => {
      setRemovingId(providerId);
      try {
        const ok = await deleteProviderConfig(providerId);
        setSaveStatus((prev) => ({
          ...prev,
          [providerId]: ok
            ? { loading: false, success: true, message: "配置已移除" }
            : { loading: false, success: false, message: "移除失败" },
        }));
        if (ok) {
          await fetchActiveModel();
          onConfigSaved();
        }
      } finally {
        setRemovingId(null);
      }
    },
    [fetchActiveModel, onConfigSaved],
  );

  if (modelProvidersLoading && modelProviders.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400 dark:text-slate-500">
        <Loader2 size={20} className="animate-spin mr-2" />
        加载中...
      </div>
    );
  }

  const providerQueryText = providerQuery.trim().toLowerCase();
  const visibleProviders = modelProviders.filter((p) => {
    if (providerFilter === "configured" && !p.configured) return false;
    if (providerFilter === "unconfigured" && p.configured) return false;
    if (!providerQueryText) return true;
    return (
      p.name.toLowerCase().includes(providerQueryText) ||
      p.id.toLowerCase().includes(providerQueryText) ||
      p.current_model.toLowerCase().includes(providerQueryText)
    );
  });

  return (
    <div className="space-y-4">
      {/* 搜索与过滤 */}
      <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800 p-3">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <div className="relative md:col-span-3">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500"
            />
            <input
              value={providerQuery}
              onChange={(e) => setProviderQuery(e.target.value)}
              placeholder="搜索提供商名称、ID 或模型..."
              className="w-full pl-8 pr-3 py-2 text-sm border rounded-lg bg-white dark:bg-slate-900 dark:border-slate-600 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
          </div>
          <div className="relative md:col-span-1" ref={filterRef}>
            <button
              type="button"
              onClick={() => setFilterDropdownOpen(!filterDropdownOpen)}
              className="w-full h-10 px-3 pr-8 text-sm text-left border rounded-lg bg-white dark:bg-slate-900 dark:border-slate-600 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-300"
            >
              {FILTER_OPTIONS.find((o) => o.value === providerFilter)?.label}
            </button>
            <ChevronDown
              size={14}
              className={`absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500 pointer-events-none transition-transform ${filterDropdownOpen ? "rotate-180" : ""}`}
            />
            {filterDropdownOpen && (
              <div className="absolute z-10 w-full mt-1 bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg shadow-lg overflow-hidden">
                {FILTER_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => {
                      setProviderFilter(opt.value);
                      setFilterDropdownOpen(false);
                    }}
                    className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors ${
                      opt.value === providerFilter
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400 font-medium"
                        : "text-gray-700 dark:text-slate-300"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="text-[11px] text-gray-500 dark:text-slate-400 mt-2">
          显示 {visibleProviders.length} / {modelProviders.length} 个提供商
        </div>
      </div>

      {/* 提供商列表 */}
      {visibleProviders.length === 0 ? (
        <div className="text-center py-16 text-sm text-gray-400 dark:text-slate-500">
          没有匹配的提供商
        </div>
      ) : (
        visibleProviders.map((p) => {
          const test = testResults[p.id];
          const save = saveStatus[p.id];
          const isEditing = editingId === p.id;
          const isExpanded = expandedId === p.id;
          const lockedConfig = p.configured && p.can_edit_in_place === false;

          return (
            <div
              key={p.id}
              className={`rounded-xl border p-4 transition-colors ${
                p.configured
                  ? "border-emerald-200 dark:border-emerald-800 bg-emerald-50/40 dark:bg-emerald-900/20"
                  : "border-gray-200 dark:border-slate-700 bg-gray-50/60 dark:bg-slate-800/60"
              }`}
            >
              <div
                className="flex items-center justify-between cursor-pointer"
                onClick={() => handleExpand(p.id, isExpanded)}
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  {p.configured ? (
                    <CheckCircle
                      size={18}
                      className="text-emerald-500 dark:text-emerald-400 flex-shrink-0"
                    />
                  ) : (
                    <XCircle
                      size={18}
                      className="text-gray-400 dark:text-slate-600 flex-shrink-0"
                    />
                  )}
                  <div className="min-w-0">
                    <div className="font-medium text-gray-800 dark:text-slate-200 truncate">
                      {p.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-slate-400 mt-0.5 truncate">
                      {p.api_key_hint ? `Key: ${p.api_key_hint}` : "未配置密钥"}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      <span className="px-1.5 py-0.5 rounded bg-white/80 dark:bg-slate-800/80 border dark:border-slate-600 text-[10px] text-gray-500 dark:text-slate-400">
                        {sourceLabel(p.config_source)}
                      </span>
                      {p.api_mode && (
                        <span className="px-1.5 py-0.5 rounded bg-white/80 dark:bg-slate-800/80 border dark:border-slate-600 text-[10px] text-gray-500 dark:text-slate-400">
                          {apiModeLabel(p.api_mode)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="text-gray-400 dark:text-slate-500">
                  {isExpanded ? (
                    <span className="text-xs">▲</span>
                  ) : (
                    <span className="text-xs">▼</span>
                  )}
                </div>
              </div>

              {isExpanded && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-slate-700 space-y-3">
                  {isEditing ? (
                    <div className="space-y-2">
                      {/* 防 autocomplete 的隐藏字段 */}
                      <input
                        type="text"
                        tabIndex={-1}
                        autoComplete="username"
                        className="hidden"
                        value=""
                        readOnly
                        aria-hidden="true"
                      />
                      <input
                        type="password"
                        tabIndex={-1}
                        autoComplete="new-password"
                        className="hidden"
                        value=""
                        readOnly
                        aria-hidden="true"
                      />

                      {p.id !== "ollama" && (
                        <div>
                          <label className="text-xs text-gray-500 dark:text-slate-400 mb-1 block">
                            API Key
                          </label>
                          <input
                            type="password"
                            name={`${p.id}-api-key`}
                            autoComplete="new-password"
                            value={editForm.api_key}
                            onChange={(e) =>
                              setEditForm({
                                ...editForm,
                                api_key: e.target.value,
                              })
                            }
                            placeholder={
                              p.api_key_hint
                                ? `当前: ${p.api_key_hint}（留空保持不变）`
                                : "输入 API Key"
                            }
                            className="w-full px-3 py-2 text-sm border dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
                          />
                        </div>
                      )}
                      <div>
                        <label className="text-xs text-gray-500 dark:text-slate-400 mb-1 block">
                          Base URL（可选）
                        </label>
                        <input
                          type="text"
                          name={`${p.id}-base-url`}
                          autoComplete="off"
                          value={editForm.base_url}
                          onChange={(e) =>
                            setEditForm({
                              ...editForm,
                              base_url: e.target.value,
                            })
                          }
                          placeholder="留空使用默认端点"
                          className="w-full px-3 py-2 text-sm border dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300"
                        />
                      </div>
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          onClick={() => handleSave(p.id)}
                          disabled={save?.loading}
                          className="flex items-center gap-1 px-4 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                        >
                          {save?.loading ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Save size={12} />
                          )}
                          保存
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="px-4 py-1.5 text-xs rounded-lg border dark:border-slate-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  ) : lockedConfig ? (
                    <>
                      <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-3 text-xs text-amber-700 dark:text-amber-400">
                        当前配置已锁定，如需修改模式或密钥，请先移除后重新配置。
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2">
                          <div className="text-gray-400 dark:text-slate-500">Base URL</div>
                          <div className="text-gray-700 dark:text-slate-300 mt-1 break-all">
                            {p.base_url || "默认端点"}
                          </div>
                        </div>
                        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2">
                          <div className="text-gray-400 dark:text-slate-500">当前模式</div>
                          <div className="text-gray-700 dark:text-slate-300 mt-1">
                            {apiModeLabel(p.api_mode)}
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => handleTest(p.id)}
                          disabled={!p.configured || test?.loading}
                          className="px-3 py-1.5 text-xs rounded-lg border dark:border-slate-600 dark:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-300 dark:hover:border-blue-600 transition-colors"
                        >
                          {test?.loading ? (
                            <span className="inline-flex items-center gap-1">
                              <Loader2 size={12} className="animate-spin" />
                              测试中
                            </span>
                          ) : (
                            "测试连接"
                          )}
                        </button>
                        <button
                          onClick={() => void handleDelete(p.id)}
                          disabled={removingId === p.id || p.can_delete_config === false}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          {removingId === p.id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Trash2 size={12} />
                          )}
                          {p.can_delete_config === false ? "环境变量配置不可删除" : "移除配置"}
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2">
                          <div className="text-gray-400 dark:text-slate-500">Base URL</div>
                          <div className="text-gray-700 dark:text-slate-300 mt-1 break-all">
                            {p.base_url || "默认端点"}
                          </div>
                        </div>
                        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2">
                          <div className="text-gray-400 dark:text-slate-500">可选模型</div>
                          <div className="text-gray-700 dark:text-slate-300 mt-1">
                            {dynamicModelCounts[p.id]?.loading ? (
                              <span className="inline-flex items-center gap-1 text-gray-400 dark:text-slate-500">
                                <Loader2 size={10} className="animate-spin" />
                                获取中
                              </span>
                            ) : (
                              `${dynamicModelCounts[p.id]?.count ?? (p.available_models?.length ?? 0)} 个`
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => startEdit(p)}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border dark:border-slate-600 dark:text-slate-300 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-300 dark:hover:border-blue-600 transition-colors"
                        >
                          <Edit3 size={12} />
                          编辑凭证
                        </button>
                        <button
                          onClick={() => handleTest(p.id)}
                          disabled={!p.configured || test?.loading}
                          className="px-3 py-1.5 text-xs rounded-lg border dark:border-slate-600 dark:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-300 dark:hover:border-blue-600 transition-colors"
                        >
                          {test?.loading ? (
                            <span className="inline-flex items-center gap-1">
                              <Loader2 size={12} className="animate-spin" />
                              测试中
                            </span>
                          ) : (
                            "测试连接"
                          )}
                        </button>
                      </div>
                    </>
                  )}

                  {save && !save.loading && (
                    <div
                      className={`text-xs px-3 py-1.5 rounded-lg ${save.success ? "bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400" : "bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400"}`}
                    >
                      {save.message}
                    </div>
                  )}
                  {test && !test.loading && (
                    <div
                      className={`text-xs px-3 py-1.5 rounded-lg ${test.success ? "bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400" : "bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400"}`}
                    >
                      {test.message}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
