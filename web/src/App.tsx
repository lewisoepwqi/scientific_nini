/**
 * 应用根组件 —— 三栏布局（会话列表 + 对话面板 + 工作区面板），支持移动端响应式。
 */
import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useStore } from "./store";
import ChatPanel from "./components/ChatPanel";
import SessionList from "./components/SessionList";
import { getWsStatusMeta } from "./store/websocket-status";
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

export default function App() {
  const connect = useStore((s) => s.connect);
  const initApp = useStore((s) => s.initApp);
  const wsStatus = useStore((s) => s.wsStatus);
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
  const sessionId = useStore((s) => s.sessionId);
  const pendingAskUserQuestionsBySession = useStore(
    (s) => s.pendingAskUserQuestionsBySession,
  );
  const sendMessage = useStore((s) => s.sendMessage);

  // 应用初始化：恢复会话并建立 WebSocket 连接
  useEffect(() => {
    // 先初始化应用（恢复会话），然后建立 WebSocket 连接
    initApp().then(() => {
      connect();
    });
  }, [initApp, connect]);

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
    <div className="flex h-full items-center justify-center bg-white/80">
      <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 shadow-sm">
        <Loader2 size={12} className="animate-spin" />
        正在打开工作区...
      </div>
    </div>
  );

  const dialogFallback = (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/10 backdrop-blur-[2px]">
      <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 shadow-lg">
        <Loader2 size={12} className="animate-spin" />
        正在加载面板...
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-white">
      {/* 桌面端侧边栏 */}
      <div className="w-64 border-r bg-gray-50 flex-shrink-0 hidden md:flex flex-col">
        <SessionList />
      </div>

      {/* 移动端侧边栏（覆盖式） */}
      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/30 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 z-50 w-72 bg-gray-50 shadow-xl md:hidden flex flex-col">
            <SessionList onClose={() => setSidebarOpen(false)} />
          </div>
        </>
      )}

      {/* 主面板 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶栏 */}
        <div className="h-12 border-b flex items-center justify-between px-4 bg-white flex-shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors md:hidden"
              title="会话列表"
            >
              <Menu size={18} />
            </button>
            <span className="text-sm font-medium text-gray-600">对话</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setActivePanel("capabilities")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-purple-600 transition-colors"
              title="分析能力"
            >
              <Sparkles size={16} />
            </button>
            <button
              onClick={() => setActivePanel("report")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-emerald-600 transition-colors"
              title="生成文章初稿"
            >
              <FileText size={16} />
            </button>
            <button
              onClick={() => setActivePanel("cost")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-amber-600 transition-colors"
              title="成本统计"
            >
              <Coins size={16} />
            </button>
            <button
              onClick={() => setActivePanel("profile")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-sky-600 transition-colors"
              title="研究画像"
            >
              <User size={16} />
            </button>
            <button
              onClick={() => setActivePanel("tools")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
              title="工具清单"
            >
              <Wrench size={16} />
            </button>
            <button
              onClick={() => setActivePanel("knowledge")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-indigo-600 transition-colors"
              title="知识库"
            >
              <Library size={16} />
            </button>
            <button
              onClick={() => setActivePanel("skills")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
              title="技能管理"
            >
              <BookOpen size={16} />
            </button>
            <button
              onClick={() => setActivePanel("settings")}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
              title="模型配置"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={toggleWorkspacePanel}
              className={`p-1.5 rounded-lg hover:bg-gray-100 transition-colors ${
                workspacePanelOpen
                  ? "text-blue-600 bg-blue-50"
                  : "text-gray-500"
              }`}
              title={workspacePanelOpen ? "关闭工作区" : "打开工作区"}
            >
              {workspacePanelOpen ? (
                <PanelRightClose size={16} />
              ) : (
                <PanelRightOpen size={16} />
              )}
            </button>
            <div className="flex items-center gap-1.5 text-xs">
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
        </div>

        {/* 对话面板 */}
        <ChatPanel />
      </div>

      {/* 桌面端工作区面板 */}
      {workspacePanelOpen && (
        <div
          className="border-l flex-shrink-0 hidden md:flex flex-col relative"
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
        </div>
      )}

      {/* 移动端工作区面板（覆盖式抽屉） */}
      {workspacePanelOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/30 md:hidden"
            onClick={toggleWorkspacePanel}
          />
          <div className="fixed inset-y-0 right-0 z-50 w-80 bg-white shadow-xl md:hidden flex flex-col">
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

      {/* 模型配置弹窗 */}
      {activePanel !== null && (
        <Suspense fallback={dialogFallback}>
          <ModelConfigPanel
            open={activePanel === "settings"}
            onClose={closePanel}
          />
          <SkillCatalogPanel
            open={activePanel === "tools"}
            onClose={closePanel}
          />
          <CapabilityPanel
            open={activePanel === "capabilities"}
            onClose={closePanel}
          />
          <MarkdownSkillManagerPanel
            open={activePanel === "skills"}
            onClose={closePanel}
          />
          <ResearchProfilePanel
            isOpen={activePanel === "profile"}
            onClose={closePanel}
          />
          <ArticleDraftPanel
            isOpen={activePanel === "report"}
            onClose={closePanel}
            sessionId={sessionId}
            onStartDraftDialog={handleStartDraftDialog}
          />
          <CostPanel
            isOpen={activePanel === "cost"}
            onClose={closePanel}
          />
          <KnowledgePanel
            isOpen={activePanel === "knowledge"}
            onClose={closePanel}
          />
        </Suspense>
      )}
    </div>
  );
}
