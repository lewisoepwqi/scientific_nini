/**
 * 应用根组件 —— 三栏布局（会话列表 + 对话面板 + 工作区面板），支持移动端响应式。
 */
import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useStore } from "./store";
import { useIsDesktop } from "./hooks";
import ChatPanel from "./components/ChatPanel";
import SessionList from "./components/SessionList";
import AuthGate from "./components/AuthGate";
import ErrorBoundary from "./components/ErrorBoundary";
import { getWsStatusMeta } from "./store/websocket-status";
import { AUTH_INVALID_EVENT } from "./store/auth";
import { initTheme, getStoredTheme, setTheme, type ThemeMode } from "./theme";
import {
  BookOpen,
  Loader2,
  Wifi,
  WifiOff,
  Settings,
  Menu,
  Wrench,
  PanelRightOpen,
  PanelRightClose,
  Sparkles,
  User,
  FileText,
  Coins,
  Library,
  Sun,
  Moon,
} from "lucide-react";

const ModelConfigPanel = lazy(() => import("./components/ModelConfigPanel"));
const SkillCatalogPanel = lazy(() => import("./components/SkillCatalogPanel"));
const CapabilityPanel = lazy(() => import("./components/CapabilityPanel"));
const MarkdownSkillManagerPanel = lazy(
  () => import("./components/MarkdownSkillManagerPanel"),
);
const WorkspaceSidebar = lazy(() => import("./components/WorkspaceSidebar"));
const MemoryPanel = lazy(() => import("./components/MemoryPanel"));
const ResearchProfilePanel = lazy(
  () => import("./components/ResearchProfilePanel"),
);
const ArticleDraftPanel = lazy(() => import("./components/ArticleDraftPanel"));
const CostPanel = lazy(() => import("./components/CostPanel"));
const KnowledgePanel = lazy(() => import("./components/KnowledgePanel"));
const AgentExecutionPanel = lazy(() => import("./components/AgentExecutionPanel"));
const WorkflowTopology = lazy(() => import("./components/WorkflowTopology"));
const HypothesisTracker = lazy(() => import("./components/HypothesisTracker"));

export default function App() {
  const connect = useStore((s) => s.connect);
  const bootstrapApp = useStore((s) => s.bootstrapApp);
  const submitApiKey = useStore((s) => s.submitApiKey);
  const clearAuthState = useStore((s) => s.clearAuthState);
  const wsStatus = useStore((s) => s.wsStatus);
  const apiKeyRequired = useStore((s) => s.apiKeyRequired);
  const authReady = useStore((s) => s.authReady);
  const authError = useStore((s) => s.authError);
  const appBootstrapping = useStore((s) => s.appBootstrapping);
  const workspacePanelOpen = useStore((s) => s.workspacePanelOpen);
  const toggleWorkspacePanel = useStore((s) => s.toggleWorkspacePanel);
  type PanelType =
    | "settings"
    | "tools"
    | "capabilities"
    | "skills"
    | "profile"
    | "report"
    | "cost"
    | "knowledge";
  const [activePanel, setActivePanel] = useState<PanelType | null>(null);
  const closePanel = useCallback(() => setActivePanel(null), []);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [workspacePanelWidth, setWorkspacePanelWidth] = useState(420);
  const [resizingWorkspace, setResizingWorkspace] = useState(false);
  const isDesktop = useIsDesktop();
  const [themeMode, setThemeMode] = useState<ThemeMode>(getStoredTheme());
  const sessionId = useStore((s) => s.sessionId);
  const pendingAskUserQuestionsBySession = useStore(
    (s) => s.pendingAskUserQuestionsBySession,
  );
  const sendMessage = useStore((s) => s.sendMessage);
  const activeAgents = useStore((s) => s.activeAgents);
  const completedAgents = useStore((s) => s.completedAgents);
  const hypotheses = useStore((s) => s.hypotheses);

  useEffect(() => {
    void bootstrapApp();
  }, [bootstrapApp]);

  // 暗色模式初始化
  useEffect(() => {
    return initTheme();
  }, []);

  const handleToggleTheme = useCallback(() => {
    const modes: ThemeMode[] = ['light', 'dark', 'system'];
    const current = getStoredTheme();
    const nextIndex = (modes.indexOf(current) + 1) % modes.length;
    const next = modes[nextIndex];
    setTheme(next);
    setThemeMode(next);
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail =
        event instanceof CustomEvent &&
        typeof event.detail?.message === "string"
          ? event.detail.message
          : undefined;
      void clearAuthState(detail);
    };
    window.addEventListener(AUTH_INVALID_EVENT, handler);
    return () => window.removeEventListener(AUTH_INVALID_EVENT, handler);
  }, [clearAuthState]);

  // 监听试用到期 / ModelSelector 点击事件，自动弹出 AI 设置面板
  useEffect(() => {
    const handler = () => setActivePanel("settings");
    window.addEventListener("nini:trial-expired", handler);
    window.addEventListener("nini:open-settings", handler);
    return () => {
      window.removeEventListener("nini:trial-expired", handler);
      window.removeEventListener("nini:open-settings", handler);
    };
  }, []);

  useEffect(() => {
    const reconnectIfVisible = () => {
      if (document.hidden) return;
      connect();
    };

    document.addEventListener("visibilitychange", reconnectIfVisible);
    window.addEventListener("focus", reconnectIfVisible);
    return () => {
      document.removeEventListener("visibilitychange", reconnectIfVisible);
      window.removeEventListener("focus", reconnectIfVisible);
    };
  }, [connect]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const pendingCount = Object.keys(pendingAskUserQuestionsBySession).length;
    const baseTitle = "Nini";
    document.title = pendingCount > 0 ? `(${pendingCount}) ${baseTitle}` : baseTitle;
  }, [pendingAskUserQuestionsBySession]);

  const wsStatusMeta = getWsStatusMeta(wsStatus);

  const handleWorkspaceResizeStart = useCallback(() => {
    setResizingWorkspace(true);
  }, []);

  const handleStartDraftDialog = useCallback(
    (config: {
      template: string;
      sections: string[];
      detail_level: "brief" | "standard" | "detailed";
      include_figures: boolean;
      include_tables: boolean;
      title: string;
    }) => {
      // 构建提示消息
      const sectionsText = config.sections
        .map((s) => {
          const map: Record<string, string> = {
            abstract: "摘要",
            introduction: "引言",
            methods: "方法",
            results: "结果",
            discussion: "讨论",
            conclusion: "结论",
            limitations: "局限性",
          };
          return map[s] || s;
        })
        .join("、");

      const detailMap = {
        brief: "简洁版",
        standard: "标准版",
        detailed: "详细版",
      };

      const prompt = `/article_draft

请为我生成科研文章初稿。

配置要求：
- 期刊风格：${config.template.toUpperCase()}
- 生成章节：${sectionsText}
- 详细程度：${detailMap[config.detail_level]}
- 包含图表：${config.include_figures ? "是" : "否"}
- 包含表格：${config.include_tables ? "是" : "否"}

请根据会话中的数据分析结果，按照上述配置生成结构完整的科研论文初稿。`;

      sendMessage(prompt);
    },
    [sendMessage],
  );

  useEffect(() => {
    if (!resizingWorkspace) return;
    const onMouseMove = (event: MouseEvent) => {
      const width = window.innerWidth - event.clientX;
      const clamped = Math.max(340, Math.min(960, width));
      setWorkspacePanelWidth(clamped);
    };
    const onMouseUp = () => setResizingWorkspace(false);

    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [resizingWorkspace]);

  const workspacePanelFallback = (
    <div className="flex h-full items-center justify-center bg-white/80 dark:bg-slate-900/80">
      <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-500 dark:text-slate-400 shadow-sm">
        <Loader2 size={12} className="animate-spin" />
        正在打开工作区...
      </div>
    </div>
  );

  const dialogFallback = (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/10 backdrop-blur-[2px]">
      <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-500 dark:text-slate-400 shadow-lg">
        <Loader2 size={12} className="animate-spin" />
        正在加载面板...
      </div>
    </div>
  );

  return (
    <ErrorBoundary>
      <div className="flex h-screen bg-white dark:bg-slate-900">
        {apiKeyRequired && !authReady && !appBootstrapping && (
          <AuthGate error={authError} loading={appBootstrapping} onSubmit={submitApiKey} />
        )}
        {/* 桌面端侧边栏 */}
        <nav aria-label="会话列表" className="w-64 border-r border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800 flex-shrink-0 hidden md:flex flex-col">
          <SessionList />
        </nav>

        {/* 移动端侧边栏（覆盖式） */}
        {sidebarOpen && (
          <>
            <div
              className="fixed inset-0 z-40 bg-black/30 md:hidden"
              onClick={() => setSidebarOpen(false)}
            />
            <div className="fixed inset-y-0 left-0 z-50 w-72 bg-gray-50 dark:bg-slate-800 shadow-xl md:hidden flex flex-col">
              <SessionList onClose={() => setSidebarOpen(false)} />
            </div>
          </>
        )}

        {/* 主面板 */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* 顶栏 */}
          <header className="h-12 border-b border-gray-200 dark:border-slate-700 flex items-center justify-between px-4 bg-white dark:bg-slate-900 flex-shrink-0">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-500 dark:text-slate-400 transition-colors md:hidden focus-visible:ring-2 focus-visible:ring-blue-500"
                aria-label="打开会话列表"
              >
                <Menu size={18} />
              </button>
              <span className="text-sm font-medium text-gray-600 dark:text-slate-300">对话</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setActivePanel("capabilities")}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-purple-600 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="分析能力"
                title="分析能力"
              >
                <Sparkles size={16} />
              </button>
              <button
                onClick={() => setActivePanel("report")}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-emerald-600 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="生成文章初稿"
                title="生成文章初稿"
              >
                <FileText size={16} />
              </button>
              <button
                onClick={() => setActivePanel("cost")}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-amber-600 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="成本统计"
                title="成本统计"
              >
                <Coins size={16} />
              </button>
              <button
                onClick={() => setActivePanel("profile")}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-sky-600 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="研究画像"
                title="研究画像"
              >
                <User size={16} />
              </button>
              <button
                onClick={() => setActivePanel("tools")}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-500 dark:text-slate-400 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="工具清单"
                title="工具清单"
              >
                <Wrench size={16} />
              </button>
              <button
                onClick={() => setActivePanel("knowledge")}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-indigo-600 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="知识库"
                title="知识库"
              >
                <Library size={16} />
              </button>
              <button
                onClick={() => setActivePanel("skills")}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-500 dark:text-slate-400 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="技能管理"
                title="技能管理"
              >
                <BookOpen size={16} />
              </button>
              <button
                onClick={() => setActivePanel("settings")}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-500 dark:text-slate-400 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label="模型配置"
                title="模型配置"
              >
                <Settings size={16} />
              </button>
              <button
                onClick={handleToggleTheme}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-500 dark:text-slate-400 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                aria-label={`切换主题（当前：${themeMode === 'system' ? '跟随系统' : themeMode === 'dark' ? '深色' : '浅色'}）`}
                title={`主题：${themeMode === 'system' ? '跟随系统' : themeMode === 'dark' ? '深色' : '浅色'}`}
              >
                {themeMode === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
              </button>
              <button
                onClick={toggleWorkspacePanel}
                className={`p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none ${
                  workspacePanelOpen
                    ? "text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400"
                    : "text-gray-500 dark:text-slate-400"
                }`}
                aria-label={workspacePanelOpen ? "关闭工作区" : "打开工作区"}
                title={workspacePanelOpen ? "关闭工作区" : "打开工作区"}
              >
                {workspacePanelOpen ? (
                  <PanelRightClose size={16} />
                ) : (
                  <PanelRightOpen size={16} />
                )}
              </button>
              <div className="flex items-center gap-1.5 text-xs" aria-live="polite">
                {wsStatusMeta.tone === "success" && (
                  <>
                    <Wifi size={12} className="text-emerald-500" />
                    <span className="text-emerald-600 hidden sm:inline">
                      {wsStatusMeta.label}
                    </span>
                  </>
                )}
                {wsStatusMeta.tone === "progress" && (
                  <>
                    <Loader2 size={12} className="animate-spin text-sky-500" />
                    <span className="text-sky-600 hidden sm:inline">
                      {wsStatusMeta.label}
                    </span>
                  </>
                )}
                {wsStatusMeta.tone === "warning" && (
                  <>
                    <Loader2 size={12} className="animate-spin text-amber-500" />
                    <span className="text-amber-600 hidden sm:inline">
                      {wsStatusMeta.label}
                    </span>
                  </>
                )}
                {wsStatusMeta.tone === "danger" && (
                  <>
                    <WifiOff size={12} className="text-red-400" />
                    <span className="text-red-500 hidden sm:inline">
                      {wsStatusMeta.label}
                    </span>
                  </>
                )}
                {wsStatusMeta.tone === "muted" && (
                  <>
                    <WifiOff size={12} className="text-gray-400" />
                    <span className="text-gray-500 hidden sm:inline">
                      {wsStatusMeta.label}
                    </span>
                  </>
                )}
              </div>
            </div>
          </header>

          {/* 多 Agent 执行状态面板（WorkflowTopology 在 ≥2 个 Agent 时自动渲染） */}
          {(Object.keys(activeAgents).length > 0 || completedAgents.length > 0) && (
            <div className="px-4 pt-3 space-y-2">
              <Suspense fallback={null}>
                <WorkflowTopology />
              </Suspense>
              <Suspense fallback={null}>
                <AgentExecutionPanel />
              </Suspense>
            </div>
          )}

          {/* 假设推理追踪面板（hypothesis_driven 范式激活时显示） */}
          {hypotheses.length > 0 && (
            <div className="px-4 pt-2">
              <Suspense fallback={null}>
                <HypothesisTracker />
              </Suspense>
            </div>
          )}

          {/* 对话面板 */}
          <ChatPanel />
        </main>

        {/* 工作区面板 —— 仅渲染一个实例，避免重复挂载 */}
        {workspacePanelOpen && isDesktop && (
          <aside
            aria-label="工作区"
            className="border-l border-gray-200 dark:border-slate-700 flex-shrink-0 flex flex-col relative bg-white dark:bg-slate-900"
            style={{ width: `${workspacePanelWidth}px` }}
          >
            <div
              onMouseDown={handleWorkspaceResizeStart}
              className="absolute left-0 top-0 h-full w-1.5 -translate-x-1/2 cursor-col-resize z-20 bg-transparent hover:bg-blue-200/40 active:bg-blue-300/60"
              title="拖拽调整宽度"
            />
            <div className="flex-1 min-h-0">
              <Suspense fallback={workspacePanelFallback}>
                <WorkspaceSidebar />
              </Suspense>
            </div>
            <Suspense fallback={null}>
              <MemoryPanel />
            </Suspense>
          </aside>
        )}

        {/* 移动端工作区面板（覆盖式抽屉） */}
        {workspacePanelOpen && !isDesktop && (
          <>
            <div
              className="fixed inset-0 z-40 bg-black/30"
              onClick={toggleWorkspacePanel}
            />
            <div className="fixed inset-y-0 right-0 z-50 w-80 bg-white dark:bg-slate-900 shadow-xl flex flex-col">
              <div className="flex-1 min-h-0">
                <Suspense fallback={workspacePanelFallback}>
                  <WorkspaceSidebar />
                </Suspense>
              </div>
              <Suspense fallback={null}>
                <MemoryPanel />
              </Suspense>
            </div>
          </>
        )}

        {/* 弹窗面板 — 按需挂载，仅渲染当前激活的面板 */}
        {activePanel !== null && (
          <Suspense fallback={dialogFallback}>
            {activePanel === "settings" && (
              <ModelConfigPanel open={true} onClose={closePanel} />
            )}
            {activePanel === "tools" && (
              <SkillCatalogPanel open={true} onClose={closePanel} />
            )}
            {activePanel === "capabilities" && (
              <CapabilityPanel open={true} onClose={closePanel} />
            )}
            {activePanel === "skills" && (
              <MarkdownSkillManagerPanel open={true} onClose={closePanel} />
            )}
            {activePanel === "profile" && (
              <ResearchProfilePanel isOpen={true} onClose={closePanel} />
            )}
            {activePanel === "report" && (
              <ArticleDraftPanel
                isOpen={true}
                onClose={closePanel}
                sessionId={sessionId}
                onStartDraftDialog={handleStartDraftDialog}
              />
            )}
            {activePanel === "cost" && (
              <CostPanel isOpen={true} onClose={closePanel} />
            )}
            {activePanel === "knowledge" && (
              <KnowledgePanel isOpen={true} onClose={closePanel} />
            )}
          </Suspense>
        )}
      </div>
    </ErrorBoundary>
  );
}
