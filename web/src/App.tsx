/**
 * 应用根组件 —— 三栏布局（会话列表 + 对话面板 + 工作区面板），支持移动端响应式。
 * 独立页面（知识库、技能、研究画像、设置）替换主内容区。
 */
import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useStore } from "./store";
import { useIsDesktop } from "./hooks";
import ChatPanel from "./components/ChatPanel";
import SessionTabs from "./components/SessionTabs";
import SessionList from "./components/SessionList";
import AuthGate from "./components/AuthGate";
import ErrorBoundary from "./components/ErrorBoundary";
import ConfirmDialog from "./components/ConfirmDialog";
import UpdateDialog from "./components/UpdateDialog";
import { AUTH_INVALID_EVENT } from "./store/auth";
import { useUpdateStore } from "./store/update";
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
  Coins,
  HelpCircle,
} from "lucide-react";

/* ---- 懒加载：独立页面 ---- */
const KnowledgePage = lazy(() => import("./components/pages/KnowledgePage"));
const SkillsPage = lazy(() => import("./components/pages/SkillsPage"));
const ResearchProfilePage = lazy(() => import("./components/pages/ResearchProfilePage"));
const SettingsPage = lazy(() => import("./components/pages/SettingsPage"));
const HelpPage = lazy(() => import("./components/pages/HelpPage"));

/* ---- 懒加载：浮层面板 ---- */
const CostPanel = lazy(() => import("./components/CostPanel"));

/* ---- 懒加载：工作区 ---- */
const WorkspaceSidebar = lazy(() => import("./components/WorkspaceSidebar"));
const MemoryPanel = lazy(() => import("./components/MemoryPanel"));

/* ---- 懒加载：聊天面板附属组件 ---- */
const AgentRunTabsPanel = lazy(() => import("./components/AgentRunTabsPanel"));
const HypothesisTracker = lazy(() => import("./components/HypothesisTracker"));

/* ---- 导航类型 ---- */
type PageType = "knowledge" | "skills" | "profile" | "settings" | "help";
type PanelType = "cost";

const PAGE_PRELOADERS: Record<PageType, () => Promise<unknown>> = {
  knowledge: () => import("./components/pages/KnowledgePage"),
  skills: () => import("./components/pages/SkillsPage"),
  profile: () => import("./components/pages/ResearchProfilePage"),
  settings: () => import("./components/pages/SettingsPage"),
  help: () => import("./components/pages/HelpPage"),
};

const PANEL_PRELOADERS: Record<PanelType, () => Promise<unknown>> = {
  cost: () => import("./components/CostPanel"),
};

function preloadPage(page: PageType): Promise<unknown> {
  return PAGE_PRELOADERS[page]();
}

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
  const checkForUpdates = useUpdateStore((s) => s.checkForUpdates);
  const submitApiKey = useStore((s) => s.submitApiKey);
  const clearAuthState = useStore((s) => s.clearAuthState);
  const apiKeyRequired = useStore((s) => s.apiKeyRequired);
  const authReady = useStore((s) => s.authReady);
  const authError = useStore((s) => s.authError);
  const appBootstrapping = useStore((s) => s.appBootstrapping);
  const workspacePanelOpen = useStore((s) => s.workspacePanelOpen);
  const toggleWorkspacePanel = useStore((s) => s.toggleWorkspacePanel);
  const createNewSession = useStore((s) => s.createNewSession);

  // 独立页面 vs 浮层面板
  const [activePage, setActivePage] = useState<PageType | null>(null);
  const [activePanel, setActivePanel] = useState<PanelType | null>(null);

  const closePage = useCallback(() => {
    runDeferredUiUpdate(() => {
      setActivePage(null);
    });
  }, []);

  const openPage = useCallback((page: PageType) => {
    runDeferredUiUpdate(() => {
      setActivePage(page);
      setActivePanel(null);
    }, () => preloadPage(page));
  }, []);

  const closePanel = useCallback(() => {
    runDeferredUiUpdate(() => {
      setActivePanel(null);
    });
  }, []);

  const openPanel = useCallback((panel: PanelType) => {
    runDeferredUiUpdate(() => {
      setActivePanel(panel);
      setActivePage(null);
    }, () => preloadPanel(panel));
  }, []);

  const handleWorkspacePanelToggle = useCallback(() => {
    runDeferredUiUpdate(() => {
      toggleWorkspacePanel();
    }, workspacePanelOpen ? null : preloadWorkspacePanels);
  }, [toggleWorkspacePanel, workspacePanelOpen]);

  // 全局导航活跃状态
  const activeNav = activePage ?? (activePanel ?? "chat");

  const handleNavNavigate = useCallback((id: string) => {
    if (id === "chat") {
      closePage();
      closePanel();
    } else if (id === "help") {
      openPage("help");
    } else if (id === "cost") {
      openPanel("cost");
    } else {
      openPage(id as PageType);
    }
  }, [closePage, closePanel, openPage, openPanel]);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [workspacePanelWidth, setWorkspacePanelWidth] = useState(420);
  const [resizingWorkspace, setResizingWorkspace] = useState(false);
  const isDesktop = useIsDesktop();
  const [themeMode, setThemeMode] = useState<ThemeMode>(getStoredTheme());
  const pendingAskUserQuestionsBySession = useStore(
    (s) => s.pendingAskUserQuestionsBySession,
  );
  const activeAgents = useStore((s) => s.activeAgents);
  const completedAgents = useStore((s) => s.completedAgents);
  const agentRunTabs = useStore((s) => s.agentRunTabs);
  const hypotheses = useStore((s) => s.hypotheses);

  useEffect(() => {
    void bootstrapApp();
  }, [bootstrapApp]);

  useEffect(() => {
    void checkForUpdates();
  }, [checkForUpdates]);

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

  // 监听试用到期 / ModelSelector 点击事件，自动弹出设置页面
  useEffect(() => {
    const handler = () => openPage("settings");
    window.addEventListener("nini:trial-expired", handler);
    window.addEventListener("nini:open-settings", handler);
    return () => {
      window.removeEventListener("nini:trial-expired", handler);
      window.removeEventListener("nini:open-settings", handler);
    };
  }, [openPage]);

  // 监听成本统计按钮事件，弹出成本面板
  useEffect(() => {
    const handler = () => openPanel("cost");
    window.addEventListener("nini:open-cost", handler);
    return () => {
      window.removeEventListener("nini:open-cost", handler);
    };
  }, [openPanel]);

  // 监听桌面壳菜单"新建会话"事件
  useEffect(() => {
    const handler = () => { void createNewSession(); };
    window.addEventListener("nini:new-session", handler);
    return () => window.removeEventListener("nini:new-session", handler);
  }, [createNewSession]);

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

  const pageFallback = (
    <div className="flex h-full items-center justify-center bg-[var(--bg-base)]">
      <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-xs text-[var(--text-secondary)] shadow-sm">
        <Loader2 size={12} className="animate-spin" />
        正在加载页面...
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

        {/* === 独立页面模式（非 skills）=== */}
        {activePage !== null && activePage !== "skills" && (
          <main
            className="flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] overflow-hidden min-w-0 flex flex-col"
          >
            <Suspense fallback={pageFallback}>
              {activePage === "knowledge" && <KnowledgePage onBack={closePage} />}
              {activePage === "profile" && <ResearchProfilePage onBack={closePage} />}
              {activePage === "settings" && <SettingsPage onBack={closePage} />}
              {activePage === "help" && <HelpPage onBack={closePage} />}
            </Suspense>
          </main>
        )}

        {/* === 技能页面模式：main + aside 平级 === */}
        {activePage === "skills" && (
          <div className="flex flex-1 min-w-0 gap-0">
            <Suspense fallback={pageFallback}>
              <SkillsPage onBack={closePage} />
            </Suspense>
          </div>
        )}

        {/* === 聊天模式 === */}
        {activePage === null && (
          <>
            {/* 桌面端侧边栏 */}
            <nav aria-label="会话列表" className="w-64 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] flex-shrink-0 hidden lg:flex flex-col overflow-hidden">
              <SessionList />
            </nav>

            {/* 移动端侧边栏（覆盖式） */}
            {sidebarOpen && (
              <>
                <div
                  className="fixed inset-0 z-40 bg-black/30 lg:hidden"
                  aria-hidden="true"
                  onClick={() => setSidebarOpen(false)}
                />
                <div className="fixed inset-y-0 left-0 z-50 w-72 bg-[var(--bg-base)] shadow-xl lg:hidden flex flex-col rounded-r-lg">
                  <SessionList onClose={() => setSidebarOpen(false)} />
                </div>
              </>
            )}

            {/* 主面板 */}
            <main className="flex-1 flex flex-col min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] overflow-hidden">
              {/* 会话 Tab 栏 */}
              <SessionTabs />
              {/* Toolbar — 三栏布局：左侧移动菜单 + 中间 Logo/标题/连接状态 + 右侧工作区开关 */}
              <header className="h-12 border-b border-[var(--border-subtle)] flex items-center px-4 bg-[var(--bg-base)] flex-shrink-0">
                {/* 左侧：移动端菜单（桌面端空占位） */}
                <div className="flex-1 flex items-center gap-1">
                  <button
                    onClick={() => setSidebarOpen(true)}
                    className="p-2.5 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-muted)] transition-colors lg:hidden"
                    aria-label="打开会话列表"
                  >
                    <Menu size={18} />
                  </button>
                  <button
                    onClick={() => setMobileNavOpen(true)}
                    className="p-2.5 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-muted)] transition-colors lg:hidden"
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

                {/* 右侧：成本统计 + 工作区开关 */}
                <div className="flex-1 flex justify-end items-center gap-1">
                  {/* 成本统计按钮 */}
                  <button
                    type="button"
                    onClick={() => window.dispatchEvent(new CustomEvent("nini:open-cost"))}
                    className={`p-2 rounded-md transition-colors ${
                      activeNav === "cost"
                        ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                        : "text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                    }`}
                    aria-label="成本统计"
                    title="成本统计"
                    aria-pressed={activeNav === "cost"}
                  >
                    <Coins size={16} />
                  </button>
                  <button
                    type="button"
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
              {(agentRunTabs.length > 1 || Object.keys(activeAgents).length > 0 || completedAgents.length > 0) && (
                <div className="px-4 pt-3">
                  <Suspense fallback={null}>
                    <AgentRunTabsPanel />
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
              <div className="flex flex-shrink-0 gap-0 -ml-2">
                <div
                  role="separator"
                  aria-orientation="vertical"
                  aria-label="调整工作区宽度"
                  onMouseDown={handleWorkspaceResizeStart}
                  className="panel-resizer"
                >
                  <span className="panel-resizer-grip" />
                </div>
                <aside
                  aria-label="工作区"
                  className="rounded-lg border border-[var(--border-subtle)] flex-shrink-0 flex flex-col bg-[var(--bg-base)] overflow-hidden"
                  style={{ width: `${workspacePanelWidth}px` }}
                >
                  <div className="flex-1 min-h-0 overflow-hidden">
                    <Suspense fallback={workspacePanelFallback}>
                      <WorkspaceSidebar />
                    </Suspense>
                  </div>
                  <Suspense fallback={null}>
                    <MemoryPanel />
                  </Suspense>
                </aside>
              </div>
            )}

            {/* 移动端工作区面板（覆盖式抽屉） */}
            {workspacePanelOpen && !isDesktop && (
              <>
                <div
                  className="fixed inset-0 z-40 bg-black/30"
                  aria-hidden="true"
                  onClick={handleWorkspacePanelToggle}
                />
                <div role="dialog" aria-label="工作区" className="fixed inset-y-0 right-0 z-50 w-80 bg-[var(--bg-base)] shadow-xl flex flex-col rounded-l-lg">
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
          </>
        )}

        {/* 移动端全屏导航覆盖层 */}
        {mobileNavOpen && (
          <div role="dialog" aria-label="导航菜单" className="fixed inset-0 z-50 lg:hidden flex flex-col bg-[var(--bg-base)]">
            <div className="flex items-center justify-between px-4 h-14 border-b border-[var(--border-subtle)] shrink-0">
              <span className="text-base font-semibold text-[var(--text-primary)]">导航</span>
              <button
                type="button"
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
                          type="button"
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
                type="button"
                onClick={handleToggleTheme}
                className="flex items-center gap-3 w-full px-3 py-3 rounded-xl text-left text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors"
              >
                {getResolvedTheme() === "dark" ? <Moon size={20} /> : <Sun size={20} />}
                <span className="text-sm font-medium">
                  {themeMode === "system" ? "跟随系统" : themeMode === "dark" ? "深色模式" : "浅色模式"}
                </span>
              </button>
              <button
                type="button"
                onClick={() => {
                  handleNavNavigate("help");
                  setMobileNavOpen(false);
                }}
                className={`flex items-center gap-3 w-full px-3 py-3 rounded-xl text-left transition-colors ${
                  activeNav === "help"
                    ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                }`}
              >
                <HelpCircle size={20} />
                <span className="text-sm font-medium">帮助</span>
              </button>
              <button
                type="button"
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

        {/* 浮层面板 — 按需挂载，仅渲染当前激活的面板 */}
        {activePanel !== null && (
          <Suspense fallback={dialogFallback}>
            {activePanel === "cost" && (
              <CostPanel isOpen={true} onClose={closePanel} />
            )}
          </Suspense>
        )}
      </div>
      {/* 全局确认对话框 */}
      <ConfirmDialog />
      <UpdateDialog />
    </ErrorBoundary>
  );
}
