/**
 * 应用根组件 —— 三栏布局（会话列表 + 对话面板 + 工作区面板），支持移动端响应式。
 */
import { Suspense, lazy, useCallback, useEffect, useState, startTransition } from "react";
import { useStore } from "./store";
import { useIsDesktop } from "./hooks";
import ChatPanel from "./components/ChatPanel";
import SessionList from "./components/SessionList";
import AuthGate from "./components/AuthGate";
import ErrorBoundary from "./components/ErrorBoundary";
import ConfirmDialog from "./components/ConfirmDialog";
import { AUTH_INVALID_EVENT } from "./store/auth";
import { runDeferredUiUpdate } from "./app-transitions";
import { initTheme, getStoredTheme, setTheme, getResolvedTheme, type ThemeMode } from "./theme";
import GlobalNav, { NiniLogo, NAV_GROUPS } from "./components/GlobalNav";
import { ConnectionBadge } from "./components/ui";
import {
  Loader2,
  Menu,
  PanelRightOpen,
  PanelRightClose,
  Compass,
  X,
  Sun,
  Moon,
  Settings,
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

type PanelType =
  | "settings"
  | "tools"
  | "capabilities"
  | "skills"
  | "profile"
  | "report"
  | "cost"
  | "knowledge";

const PANEL_PRELOADERS: Record<PanelType, () => Promise<unknown>> = {
  settings: () => import("./components/ModelConfigPanel"),
  tools: () => import("./components/SkillCatalogPanel"),
  capabilities: () => import("./components/CapabilityPanel"),
  skills: () => import("./components/MarkdownSkillManagerPanel"),
  profile: () => import("./components/ResearchProfilePanel"),
  report: () => import("./components/ArticleDraftPanel"),
  cost: () => import("./components/CostPanel"),
  knowledge: () => import("./components/KnowledgePanel"),
};

function preloadPanel(panel: PanelType): Promise<unknown> {
  return PANEL_PRELOADERS[panel]();
}

function preloadWorkspacePanels(): Promise<unknown[]> {
  return Promise.all([
    import("./components/WorkspaceSidebar"),
    import("./components/MemoryPanel"),
  ]);
}

export default function App() {
  const connect = useStore((s) => s.connect);
  const bootstrapApp = useStore((s) => s.bootstrapApp);
  const submitApiKey = useStore((s) => s.submitApiKey);
  const clearAuthState = useStore((s) => s.clearAuthState);
  const apiKeyRequired = useStore((s) => s.apiKeyRequired);
  const authReady = useStore((s) => s.authReady);
  const authError = useStore((s) => s.authError);
  const appBootstrapping = useStore((s) => s.appBootstrapping);
  const workspacePanelOpen = useStore((s) => s.workspacePanelOpen);
  const toggleWorkspacePanel = useStore((s) => s.toggleWorkspacePanel);
  const [activePanel, setActivePanel] = useState<PanelType | null>(null);
  const closePanel = useCallback(() => {
    runDeferredUiUpdate(() => {
      setActivePanel(null);
    });
  }, []);
  const openPanel = useCallback((panel: PanelType) => {
    runDeferredUiUpdate(() => {
      setActivePanel(panel);
    }, () => preloadPanel(panel));
  }, []);
  const handleWorkspacePanelToggle = useCallback(() => {
    runDeferredUiUpdate(() => {
      toggleWorkspacePanel();
    }, workspacePanelOpen ? null : preloadWorkspacePanels);
  }, [toggleWorkspacePanel, workspacePanelOpen]);

  // 全局导航活跃状态
  const activeNav =
    activePanel === "knowledge"
      ? "knowledge"
      : activePanel === "skills"
        ? "skills"
        : activePanel === "capabilities"
          ? "capabilities"
          : activePanel === "report"
            ? "report"
            : activePanel === "cost"
              ? "cost"
              : activePanel === "tools"
                ? "tools"
                : activePanel === "profile"
                  ? "profile"
                  : activePanel === "settings"
                    ? "settings"
                    : "chat";
  const handleNavNavigate = useCallback((id: string) => {
    if (id === "chat") {
      closePanel();
    } else {
      openPanel(id as PanelType);
    }
  }, [closePanel, openPanel]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
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
    const currentResolved = getResolvedTheme();
    const next = currentResolved === 'dark' ? 'light' : 'dark';
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
    const handler = () => openPanel("settings");
    window.addEventListener("nini:trial-expired", handler);
    window.addEventListener("nini:open-settings", handler);
    return () => {
      window.removeEventListener("nini:trial-expired", handler);
      window.removeEventListener("nini:open-settings", handler);
    };
  }, [openPanel]);

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

      startTransition(() => {
        sendMessage(prompt);
      });
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
    <div className="flex h-full items-center justify-center bg-[var(--bg-base)]/80 backdrop-blur-[2px]">
      <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-xs text-[var(--text-secondary)] shadow-sm">
        <Loader2 size={12} className="animate-spin" />
        正在打开工作区...
      </div>
    </div>
  );

  const dialogFallback = (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[var(--bg-app)]/40 backdrop-blur-[2px]">
      <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-xs text-[var(--text-secondary)] shadow-lg">
        <Loader2 size={12} className="animate-spin" />
        正在加载面板...
      </div>
    </div>
  );

  return (
    <ErrorBoundary>
      <div className="flex h-screen bg-[var(--bg-app)] p-2 gap-2">
        {apiKeyRequired && !authReady && !appBootstrapping && (
          <AuthGate error={authError} loading={appBootstrapping} onSubmit={submitApiKey} />
        )}
        {/* 全局导航 */}
        <GlobalNav
          themeMode={themeMode}
          onToggleTheme={handleToggleTheme}
          onNavigate={handleNavNavigate}
          activeNav={activeNav}
        />
        {/* 桌面端侧边栏 */}
        <nav aria-label="会话列表" className="w-64 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] flex-shrink-0 hidden md:flex flex-col overflow-hidden">
          <SessionList />
        </nav>

        {/* 移动端侧边栏（覆盖式） */}
        {sidebarOpen && (
          <>
            <div
              className="fixed inset-0 z-40 bg-black/30 md:hidden"
              onClick={() => setSidebarOpen(false)}
            />
            <div className="fixed inset-y-0 left-0 z-50 w-72 bg-[var(--bg-base)] shadow-xl md:hidden flex flex-col rounded-r-lg">
              <SessionList onClose={() => setSidebarOpen(false)} />
            </div>
          </>
        )}

        {/* 主面板 */}
        <main className="flex-1 flex flex-col min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] overflow-hidden">
          {/* Toolbar — 三栏布局：左侧移动菜单 + 中间 Logo/标题/连接状态 + 右侧工作区开关 */}
          <header className="h-12 border-b border-[var(--border-subtle)] flex items-center px-4 bg-[var(--bg-base)] flex-shrink-0">
            {/* 左侧：移动端菜单（桌面端空占位） */}
            <div className="flex-1 flex items-center gap-1">
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-2.5 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-muted)] transition-colors md:hidden"
                aria-label="打开会话列表"
              >
                <Menu size={18} />
              </button>
              <button
                onClick={() => setMobileNavOpen(true)}
                className="p-2.5 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-muted)] transition-colors md:hidden"
                aria-label="打开导航菜单"
              >
                <Compass size={18} />
              </button>
            </div>

            {/* 中间：Logo + 标题 + 连接状态 */}
            <div className="flex items-center gap-2 shrink-0 h-full py-2">
              <NiniLogo size={20} />
              <div className="flex items-center gap-2">
                <h2 className="font-semibold text-[15px] text-[var(--text-primary)] whitespace-nowrap m-0 leading-none">
                  Nini
                </h2>
                <ConnectionBadge className="mt-px" />
              </div>
            </div>

            {/* 右侧：工作区开关 */}
            <div className="flex-1 flex justify-end">
              <button
                onClick={handleWorkspacePanelToggle}
                className={`appearance-none flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-[background-color,color,border-color] border ${
                  workspacePanelOpen
                    ? "border-[color-mix(in_srgb,var(--accent)_25%,transparent)] bg-[var(--accent-subtle)] text-[var(--accent)] dark:border-transparent"
                    : "border-[var(--border-subtle)] hover:bg-[var(--bg-hover)] text-[var(--text-muted)] dark:border-transparent"
                }`}
                aria-label={workspacePanelOpen ? "关闭工作区" : "打开工作区"}
                title={workspacePanelOpen ? "关闭工作区" : "打开工作区"}
              >
                {workspacePanelOpen ? (
                  <PanelRightClose size={14} />
                ) : (
                  <PanelRightOpen size={14} />
                )}
                <span className="hidden sm:inline">工作区</span>
              </button>
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
            className="rounded-lg border border-[var(--border-subtle)] flex-shrink-0 flex flex-col relative bg-[var(--bg-base)]"
            style={{ width: `${workspacePanelWidth}px` }}
          >
            <div
              onMouseDown={handleWorkspaceResizeStart}
              className="absolute left-0 top-0 h-full w-2.5 -translate-x-1/2 cursor-col-resize z-20 bg-transparent hover:bg-[var(--accent-subtle)] active:bg-[var(--accent)]"
              title="拖拽调整宽度"
            />
            <div className="flex-1 min-h-0 overflow-hidden">
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
              onClick={handleWorkspacePanelToggle}
            />
            <div className="fixed inset-y-0 right-0 z-50 w-80 bg-[var(--bg-base)] shadow-xl flex flex-col rounded-l-lg">
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

        {/* 移动端全屏导航覆盖层 */}
        {mobileNavOpen && (
          <div className="fixed inset-0 z-50 md:hidden flex flex-col bg-[var(--bg-base)]">
            <div className="flex items-center justify-between px-4 h-14 border-b border-[var(--border-subtle)] shrink-0">
              <span className="text-base font-semibold text-[var(--text-primary)]">导航</span>
              <button
                onClick={() => setMobileNavOpen(false)}
                className="p-2 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-muted)] transition-colors"
                aria-label="关闭导航菜单"
              >
                <X size={20} />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto">
              <div className="p-4 space-y-1">
                {NAV_GROUPS.map((group, gi) => (
                  <div key={group.key}>
                    {gi > 0 && (
                      <div className="h-px my-2" style={{ background: "var(--border-subtle)" }} />
                    )}
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      const isActive = activeNav === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => { handleNavNavigate(item.id); setMobileNavOpen(false); }}
                          className={`flex items-center gap-3 w-full px-3 py-3 rounded-xl text-left transition-colors ${
                            isActive
                              ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                              : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                          }`}
                        >
                          <Icon size={20} />
                          <span className="text-sm font-medium">{item.label}</span>
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
            </nav>
            <div className="border-t border-[var(--border-subtle)] p-4 space-y-1">
              <button
                onClick={handleToggleTheme}
                className="flex items-center gap-3 w-full px-3 py-3 rounded-xl text-left text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors"
              >
                {getResolvedTheme() === "dark" ? <Moon size={20} /> : <Sun size={20} />}
                <span className="text-sm font-medium">
                  {themeMode === "system" ? "跟随系统" : themeMode === "dark" ? "深色模式" : "浅色模式"}
                </span>
              </button>
              <button
                onClick={() => {
                  handleNavNavigate("settings");
                  setMobileNavOpen(false);
                }}
                className={`flex items-center gap-3 w-full px-3 py-3 rounded-xl text-left transition-colors ${
                  activeNav === "settings"
                    ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                }`}
              >
                <Settings size={20} />
                <span className="text-sm font-medium">设置</span>
              </button>
            </div>
          </div>
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
      {/* 全局确认对话框 */}
      <ConfirmDialog />
    </ErrorBoundary>
  );
}
