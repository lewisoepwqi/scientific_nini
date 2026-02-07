/**
 * 应用根组件 —— 左右分栏布局（侧边栏 + 对话面板），支持移动端响应式。
 */
import { useEffect, useState } from 'react'
import { useStore } from './store'
import ChatPanel from './components/ChatPanel'
import SessionList from './components/SessionList'
import ModelConfigPanel from './components/ModelConfigPanel'
import ModelSelector from './components/ModelSelector'
import WorkflowPanel from './components/WorkflowPanel'
import { Wifi, WifiOff, Settings, Menu, Zap } from 'lucide-react'

export default function App() {
  const connect = useStore((s) => s.connect)
  const initApp = useStore((s) => s.initApp)
  const wsConnected = useStore((s) => s.wsConnected)
  const [showSettings, setShowSettings] = useState(false)
  const [showWorkflows, setShowWorkflows] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const sendMessage = useStore((s) => s.sendMessage)

  // 应用初始化：恢复会话并建立 WebSocket 连接
  useEffect(() => {
    // 先初始化应用（恢复会话），然后建立 WebSocket 连接
    initApp().then(() => {
      connect()
    })
  }, [initApp, connect])

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
            <ModelSelector />
            <button
              onClick={() => setShowWorkflows(true)}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
              title="工作流模板"
            >
              <Zap size={16} />
            </button>
            <button
              onClick={() => setShowSettings(true)}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
              title="模型配置"
            >
              <Settings size={16} />
            </button>
            <div className="flex items-center gap-1.5 text-xs">
              {wsConnected ? (
                <>
                  <Wifi size={12} className="text-emerald-500" />
                  <span className="text-emerald-600 hidden sm:inline">已连接</span>
                </>
              ) : (
                <>
                  <WifiOff size={12} className="text-red-400" />
                  <span className="text-red-500 hidden sm:inline">连接中...</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* 对话面板 */}
        <ChatPanel />
      </div>

      {/* 模型配置弹窗 */}
      <ModelConfigPanel open={showSettings} onClose={() => setShowSettings(false)} />

      {/* 工作流模板弹窗 */}
      <WorkflowPanel
        open={showWorkflows}
        onClose={() => setShowWorkflows(false)}
        onApply={(templateId) => {
          setShowWorkflows(false)
          sendMessage(`应用工作流模板 ${templateId}`)
        }}
      />
    </div>
  )
}
