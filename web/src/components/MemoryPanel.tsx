/**
 * 记忆面板 —— 展示会话记忆文件状态与跨会话长期记忆。
 *
 * 两个标签页：
 *   · 会话记忆：当前会话的 JSONL 记忆文件列表 + 内容展开
 *   · 长期记忆：跨会话高置信度记忆，按类型/重要性可视化
 */
import { useEffect, useState, useCallback, useRef } from "react";
import { useStore, type MemoryFile } from "../store";
import * as api from "../store/api-actions";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  FileText,
  Archive,
  RefreshCw,
  Database,
  Sparkles,
  Trash2,
  Search,
  Filter,
} from "lucide-react";

// ---- 常量 ----
const MEMORY_PANEL_HEIGHT_KEY = "nini.memoryPanel.height";
const MEMORY_PANEL_DEFAULT_HEIGHT = 240;
const MEMORY_PANEL_MIN_HEIGHT = 60;
const MEMORY_PANEL_MAX_HEIGHT = 600;

const FILE_CONTENT_DEFAULT_HEIGHT = 120;
const FILE_CONTENT_MIN_HEIGHT = 40;
const FILE_CONTENT_MAX_HEIGHT = 400;

// ---- 记忆类型配色系统 ----
const MEMORY_TYPE_CONFIG: Record<
  string,
  { label: string; badge: string; dot: string }
> = {
  finding: {
    label: "发现",
    badge: "bg-emerald-100 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-400",
  },
  statistic: {
    label: "统计",
    badge: "bg-sky-100 text-sky-700 border-sky-200",
    dot: "bg-sky-400",
  },
  decision: {
    label: "决策",
    badge: "bg-violet-100 text-violet-700 border-violet-200",
    dot: "bg-violet-400",
  },
  insight: {
    label: "洞察",
    badge: "bg-amber-100 text-amber-700 border-amber-200",
    dot: "bg-amber-400",
  },
};

// ---- 工具函数 ----
function clampHeight(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value)));
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function formatRelativeTime(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    const now = Date.now();
    const diffMs = now - d.getTime();
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffDays === 0) return "今天";
    if (diffDays === 1) return "昨天";
    if (diffDays < 7) return `${diffDays} 天前`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} 周前`;
    return `${Math.floor(diffDays / 30)} 月前`;
  } catch {
    return "";
  }
}

function FileIcon({ type }: { type: MemoryFile["type"] }) {
  switch (type) {
    case "memory":
      return <Database size={11} className="text-blue-400" />;
    case "knowledge":
      return <Brain size={11} className="text-purple-400" />;
    case "archive":
      return <Archive size={11} className="text-amber-400" />;
    default:
      return <FileText size={11} className="text-gray-400 dark:text-slate-500" />;
  }
}

// ---- 文件内容区高度拖动 ----
function useVerticalResize(defaultHeight: number, min: number, max: number) {
  const [height, setHeight] = useState(defaultHeight);
  const resizingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(defaultHeight);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return;
      const delta = e.clientY - startYRef.current;
      setHeight(clampHeight(startHeightRef.current + delta, min, max, defaultHeight));
    };
    const onMouseUp = () => {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [min, max, defaultHeight]);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      resizingRef.current = true;
      startYRef.current = e.clientY;
      startHeightRef.current = height;
      document.body.style.userSelect = "none";
      document.body.style.cursor = "ns-resize";
    },
    [height],
  );

  return { height, onMouseDown };
}

// ---- 单条记忆文件 ----
function MemoryFileItem({
  file,
  refreshVersion,
}: {
  file: MemoryFile;
  refreshVersion: number;
}) {
  const sessionId = useStore((s) => s.sessionId);
  const [expanded, setExpanded] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { height: contentHeight, onMouseDown: onContentResizeStart } = useVerticalResize(
    FILE_CONTENT_DEFAULT_HEIGHT,
    FILE_CONTENT_MIN_HEIGHT,
    FILE_CONTENT_MAX_HEIGHT,
  );

  const loadContent = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const resp = await fetch(
        `/api/sessions/${sessionId}/memory-files/${encodeURIComponent(file.name)}`,
      );
      const payload = await resp.json();
      if (payload.success && typeof payload.data?.content === "string") {
        setContent(payload.data.content);
      } else {
        setContent("(无法读取内容)");
      }
    } catch {
      setContent("(加载失败)");
    } finally {
      setLoading(false);
    }
  }, [sessionId, file.name]);

  const handleExpand = useCallback(async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (content === null) {
      await loadContent();
    }
  }, [expanded, content, loadContent]);

  useEffect(() => {
    setContent(null);
    if (expanded) {
      void loadContent();
    }
  }, [refreshVersion, expanded, loadContent]);

  return (
    <div className="border-b border-gray-100 dark:border-slate-700/50 last:border-b-0">
      <button
        onClick={handleExpand}
        className="flex w-full items-center gap-1.5 px-2.5 py-2 text-[11px] transition-colors hover:bg-stone-50 dark:hover:bg-slate-700/50"
      >
        {expanded ? (
          <ChevronDown size={10} className="flex-shrink-0 text-gray-400 dark:text-slate-500" />
        ) : (
          <ChevronRight size={10} className="flex-shrink-0 text-gray-400 dark:text-slate-500" />
        )}
        <FileIcon type={file.type} />
        <span className="flex-1 truncate text-left text-gray-700 dark:text-slate-300">{file.name}</span>
        <span className="flex-shrink-0 text-[10px] text-gray-400 dark:text-slate-500">{formatBytes(file.size)}</span>
      </button>
      {expanded && (
        <div className="px-2.5 pb-2">
          <div className="mb-1 text-[10px] text-gray-400 dark:text-slate-500">{formatTime(file.modified_at)}</div>
          {loading ? (
            <div className="animate-pulse text-[10px] text-gray-400 dark:text-slate-500">加载中…</div>
          ) : content !== null ? (
            <>
              <pre
                className="overflow-x-auto overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-stone-50 dark:bg-slate-800 p-2 font-mono text-[10px] text-gray-600 dark:text-slate-400"
                style={{ height: `${contentHeight}px` }}
              >
                {content}
              </pre>
              <div
                onMouseDown={onContentResizeStart}
                className="group flex h-3 cursor-ns-resize items-center justify-center rounded-b transition-colors hover:bg-amber-50 dark:hover:bg-amber-900/20"
                title="拖动调整内容区高度"
              >
                <div className="h-0.5 w-6 rounded-full bg-gray-200 dark:bg-slate-600 transition-colors group-hover:bg-amber-400" />
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

// ---- 长期记忆卡片 ----
function LtmCard({
  entry,
  onDelete,
}: {
  entry: api.LongTermMemoryEntry;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const cfg = MEMORY_TYPE_CONFIG[entry.memory_type] ?? {
    label: entry.memory_type,
    badge: "bg-gray-100 text-gray-600 border-gray-200",
    dot: "bg-gray-400",
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确认删除此条长期记忆？")) return;
    setDeleting(true);
    const ok = await api.deleteLongTermMemory(entry.id);
    if (ok) {
      onDelete(entry.id);
    } else {
      setDeleting(false);
    }
  };

  // 重要性分数色彩
  const importanceColor =
    entry.importance_score >= 0.8
      ? "bg-rose-400"
      : entry.importance_score >= 0.6
        ? "bg-amber-400"
        : entry.importance_score >= 0.4
          ? "bg-sky-400"
          : "bg-gray-300";

  return (
    <div
      className="group rounded-xl border border-gray-100 dark:border-slate-700 bg-white dark:bg-slate-800 transition-shadow hover:shadow-sm"
      style={{ borderLeft: "3px solid transparent", borderLeftColor: undefined }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2.5 text-left"
      >
        <div className="mb-1.5 flex items-start gap-2">
          {/* 类型标签 */}
          <span
            className={`mt-0.5 flex-shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${cfg.badge}`}
          >
            {cfg.label}
          </span>
          <p className="flex-1 text-[11px] font-medium leading-snug text-gray-700 dark:text-slate-300">
            {entry.summary}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* 重要性条 */}
          <div className="h-1 w-16 overflow-hidden rounded-full bg-gray-100 dark:bg-slate-700">
            <div
              className={`h-full rounded-full transition-all ${importanceColor}`}
              style={{ width: `${Math.round(entry.importance_score * 100)}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-gray-400 dark:text-slate-500">
            {Math.round(entry.importance_score * 100)}%
          </span>

          {/* 数据集 */}
          {entry.source_dataset && (
            <span className="truncate rounded bg-stone-100 dark:bg-slate-700 px-1.5 py-0.5 text-[10px] text-stone-500 dark:text-slate-400">
              {entry.source_dataset}
            </span>
          )}

          {/* 时间 */}
          <span className="ml-auto flex-shrink-0 text-[10px] text-gray-400 dark:text-slate-500">
            {formatRelativeTime(entry.created_at)}
          </span>
        </div>
      </button>

      {/* 展开详情 */}
      {expanded && (
        <div className="border-t border-gray-100 dark:border-slate-700 px-3 py-2.5">
          <p className="mb-2 whitespace-pre-wrap text-[11px] leading-relaxed text-gray-600 dark:text-slate-400">
            {entry.content}
          </p>
          <div className="flex items-center justify-between">
            <div className="flex flex-wrap gap-1">
              {entry.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded bg-stone-100 dark:bg-slate-700 px-1.5 py-0.5 text-[10px] text-stone-500 dark:text-slate-400"
                >
                  #{tag}
                </span>
              ))}
            </div>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-red-400 opacity-60 transition-all group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 disabled:opacity-50"
            >
              <Trash2 size={10} />
              删除
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---- 长期记忆视图 ----
function LongTermMemoryView({ visible }: { visible: boolean }) {
  const [entries, setEntries] = useState<api.LongTermMemoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<api.LongTermMemoryStats | null>(null);
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const loadedRef = useRef(false);

  const load = useCallback(
    async (query?: string) => {
      setLoading(true);
      try {
        const [memResult, statsResult] = await Promise.all([
          api.fetchLongTermMemories({
            query: query || undefined,
            memory_type: filterType !== "all" ? filterType : undefined,
            limit: 30,
          }),
          api.fetchLongTermMemoryStats(),
        ]);
        setEntries(memResult.memories);
        setStats(statsResult);
      } finally {
        setLoading(false);
      }
    },
    [filterType],
  );

  useEffect(() => {
    if (visible && !loadedRef.current) {
      loadedRef.current = true;
      void load();
    }
  }, [visible, load]);

  useEffect(() => {
    if (visible && loadedRef.current) {
      void load(searchQuery);
    }
  }, [filterType, searchQuery, visible, load]);

  const handleSearch = () => {
    setSearchQuery(searchInput);
  };

  const handleDelete = (id: string) => {
    setEntries((prev) => prev.filter((e) => e.id !== id));
    setStats((prev) =>
      prev
        ? { ...prev, total_memories: Math.max(0, prev.total_memories - 1) }
        : prev,
    );
  };

  const TYPES = ["all", "finding", "statistic", "decision", "insight"];

  return (
    <div className="flex flex-col gap-2">
      {/* 统计摘要 */}
      {stats && (
        <div className="flex items-center gap-3 rounded-xl border border-gray-100 dark:border-slate-700 bg-stone-50 dark:bg-slate-800 px-3 py-2">
          <Sparkles size={12} className="flex-shrink-0 text-amber-400" />
          <span className="text-[10px] text-stone-500 dark:text-slate-400">
            共 <span className="font-semibold text-stone-700 dark:text-slate-300">{stats.total_memories}</span> 条长期记忆
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            {Object.entries(stats.type_distribution).map(([type, count]) => {
              const cfg = MEMORY_TYPE_CONFIG[type];
              if (!cfg) return null;
              return (
                <span key={type} className={`rounded-full border px-1.5 py-0.5 text-[10px] ${cfg.badge}`}>
                  {count}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* 搜索框 */}
      <div className="flex items-center gap-1.5 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2.5 py-1.5">
        <Search size={11} className="flex-shrink-0 text-gray-400 dark:text-slate-500" />
        <input
          type="text"
          placeholder="搜索记忆内容…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          className="flex-1 bg-transparent text-[11px] text-gray-700 dark:text-slate-300 placeholder-gray-300 dark:placeholder-slate-600 focus:outline-none"
        />
        {searchInput && (
          <button
            onClick={() => {
              setSearchInput("");
              setSearchQuery("");
            }}
            className="text-gray-300 dark:text-slate-600 hover:text-gray-500 dark:hover:text-slate-400"
          >
            ×
          </button>
        )}
      </div>

      {/* 类型筛选 */}
      <div className="flex gap-1 overflow-x-auto pb-0.5">
        <Filter size={11} className="mt-1 flex-shrink-0 text-gray-400 dark:text-slate-500" />
        {TYPES.map((t) => {
          const cfg = MEMORY_TYPE_CONFIG[t];
          return (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`flex-shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-all ${
                filterType === t
                  ? (cfg?.badge ?? "bg-stone-200 text-stone-600 border-stone-300")
                  : "border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-500 dark:text-slate-400 hover:border-gray-300 dark:hover:border-slate-600"
              }`}
            >
              {cfg?.label ?? "全部"}
            </button>
          );
        })}
      </div>

      {/* 内容区 */}
      {loading ? (
        <div className="flex items-center justify-center py-6">
          <RefreshCw size={14} className="animate-spin text-amber-400" />
          <span className="ml-2 text-[11px] text-gray-400 dark:text-slate-500">加载中…</span>
        </div>
      ) : entries.length === 0 ? (
        <div className="py-6 text-center text-[11px] text-gray-400 dark:text-slate-500">
          {searchQuery ? "未找到匹配的记忆" : "暂无长期记忆"}
          {!searchQuery && (
            <p className="mt-1 text-[10px] text-gray-300 dark:text-slate-600">完成分析后系统将自动提取关键发现</p>
          )}
        </div>
      ) : (
        <div className="space-y-1.5">
          {entries.map((entry) => (
            <LtmCard key={entry.id} entry={entry} onDelete={handleDelete} />
          ))}
        </div>
      )}

      {/* 刷新 */}
      <button
        onClick={() => {
          loadedRef.current = false;
          void load(searchQuery);
        }}
        className="mx-auto flex items-center gap-1 text-[10px] text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
      >
        <RefreshCw size={10} />
        刷新
      </button>
    </div>
  );
}

// ---- 面板主体 ----
export default function MemoryPanel() {
  const sessionId = useStore((s) => s.sessionId);
  const memoryFiles = useStore((s) => s.memoryFiles);
  const fetchMemoryFiles = useStore((s) => s.fetchMemoryFiles);
  const [collapsed, setCollapsed] = useState(true);
  const [activeTab, setActiveTab] = useState<"session" | "longterm">("session");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [contextTokens, setContextTokens] = useState<number | null>(null);
  const [panelHeight, setPanelHeight] = useState<number>(MEMORY_PANEL_DEFAULT_HEIGHT);
  const resizingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(MEMORY_PANEL_DEFAULT_HEIGHT);

  const fetchContextTokens = useCallback(async () => {
    if (!sessionId) return;
    try {
      const resp = await fetch(`/api/sessions/${sessionId}/context-size`);
      const payload = await resp.json();
      if (!payload.success) return;
      const tokenCount =
        typeof payload.data?.total_context_tokens === "number"
          ? payload.data.total_context_tokens
          : typeof payload.data?.token_count === "number"
            ? payload.data.token_count
            : null;
      if (typeof tokenCount === "number") {
        setContextTokens(tokenCount);
      }
    } catch {
      // 忽略错误
    }
  }, [sessionId]);

  const handleRefresh = useCallback(async () => {
    if (!sessionId) return;
    setRefreshing(true);
    try {
      await Promise.all([fetchMemoryFiles(), fetchContextTokens()]);
      setRefreshVersion((v) => v + 1);
    } finally {
      setRefreshing(false);
    }
  }, [sessionId, fetchMemoryFiles, fetchContextTokens]);

  useEffect(() => {
    if (sessionId && !collapsed && activeTab === "session") {
      void handleRefresh();
    }
  }, [sessionId, collapsed, activeTab, handleRefresh]);

  useEffect(() => {
    setContextTokens(null);
  }, [sessionId]);

  // 持久化面板高度
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(MEMORY_PANEL_HEIGHT_KEY);
      if (!saved) return;
      const parsed = Number(saved);
      if (Number.isFinite(parsed)) {
        setPanelHeight(
          clampHeight(parsed, MEMORY_PANEL_MIN_HEIGHT, MEMORY_PANEL_MAX_HEIGHT, MEMORY_PANEL_DEFAULT_HEIGHT),
        );
      }
    } catch {
      // 忽略
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        MEMORY_PANEL_HEIGHT_KEY,
        String(
          clampHeight(
            panelHeight,
            MEMORY_PANEL_MIN_HEIGHT,
            MEMORY_PANEL_MAX_HEIGHT,
            MEMORY_PANEL_DEFAULT_HEIGHT,
          ),
        ),
      );
    } catch {
      // 忽略
    }
  }, [panelHeight]);

  // 面板上沿拖动
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return;
      const delta = startYRef.current - e.clientY;
      setPanelHeight(
        clampHeight(
          startHeightRef.current + delta,
          MEMORY_PANEL_MIN_HEIGHT,
          MEMORY_PANEL_MAX_HEIGHT,
          MEMORY_PANEL_DEFAULT_HEIGHT,
        ),
      );
    };
    const onMouseUp = () => {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  const handlePanelResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      resizingRef.current = true;
      startYRef.current = e.clientY;
      startHeightRef.current = panelHeight;
      document.body.style.userSelect = "none";
      document.body.style.cursor = "ns-resize";
    },
    [panelHeight],
  );

  if (!sessionId) return null;

  // Token 用量颜色
  const tokenColor =
    contextTokens !== null && contextTokens > 80000
      ? "text-red-500"
      : contextTokens !== null && contextTokens > 40000
        ? "text-amber-500"
        : "text-gray-400 dark:text-slate-500";

  return (
    <div className="flex flex-shrink-0 flex-col border-t border-gray-200 dark:border-slate-700">
      {/* 上沿拖动条 */}
      {!collapsed && (
        <div
          onMouseDown={handlePanelResizeStart}
          className="group flex h-1.5 flex-shrink-0 cursor-ns-resize items-center justify-center transition-colors hover:bg-amber-50 dark:hover:bg-amber-900/20"
          title="拖动调整记忆面板高度"
        >
          <div className="h-0.5 w-8 rounded-full bg-gray-300 dark:bg-slate-600 transition-colors group-hover:bg-amber-400" />
        </div>
      )}

      {/* 标题栏 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full flex-shrink-0 items-center gap-2 px-4 py-2 text-xs font-medium text-gray-500 dark:text-slate-400 transition-colors hover:bg-gray-50 dark:hover:bg-slate-800"
      >
        <Brain size={13} className="text-violet-400" />
        <span>记忆状态</span>
        <div className="ml-auto flex items-center gap-2">
          {contextTokens !== null && (
            <span className={`font-mono text-[10px] ${tokenColor}`}>
              {contextTokens >= 1000
                ? `${(contextTokens / 1000).toFixed(1)}k`
                : contextTokens}{" "}
              tok
            </span>
          )}
          {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        </div>
      </button>

      {/* 展开内容 */}
      {!collapsed && (
        <div
          className="flex flex-col gap-0 overflow-hidden"
          style={{ height: `${panelHeight}px` }}
        >
          {/* Tab 导航 */}
          <div className="flex flex-shrink-0 border-b border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-800">
            <button
              onClick={() => setActiveTab("session")}
              className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-1.5 text-[11px] font-medium transition-colors ${
                activeTab === "session"
                  ? "border-b-2 border-violet-400 text-violet-600 bg-white dark:bg-slate-900"
                  : "text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-300"
              }`}
            >
              <Database size={11} />
              会话记忆
            </button>
            <button
              onClick={() => setActiveTab("longterm")}
              className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-1.5 text-[11px] font-medium transition-colors ${
                activeTab === "longterm"
                  ? "border-b-2 border-amber-400 text-amber-600 bg-white dark:bg-slate-900"
                  : "text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-300"
              }`}
            >
              <Sparkles size={11} />
              长期记忆
            </button>
          </div>

          {/* 会话记忆 Tab */}
          {activeTab === "session" && (
            <div className="flex min-h-0 flex-1 flex-col px-2 pb-2">
              <div className="flex flex-shrink-0 items-center justify-end py-1">
                <button
                  onClick={() => void handleRefresh()}
                  className="rounded p-2 text-gray-400 dark:text-slate-500 hover:bg-gray-100 dark:hover:bg-slate-700"
                  title="刷新"
                >
                  <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                {memoryFiles.length === 0 ? (
                  <div className="py-4 text-center text-[10px] text-gray-400 dark:text-slate-500">暂无记忆文件</div>
                ) : (
                  <div className="rounded-xl border border-gray-100 dark:border-slate-700 bg-white dark:bg-slate-900">
                    {memoryFiles.map((file) => (
                      <MemoryFileItem
                        key={file.name}
                        file={file}
                        refreshVersion={refreshVersion}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 长期记忆 Tab */}
          {activeTab === "longterm" && (
            <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
              <LongTermMemoryView visible={activeTab === "longterm"} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
