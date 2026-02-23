/**
 * 模型配置面板 —— 三 Tab 清晰分工。
 * - 凭证管理：填写 API Key、模型名、Base URL，测试连接
 * - 路由策略：设置全局默认供应商，为特定功能指定专用模型
 * - 优先级：拖拽排序决定自动路由优先顺序
 */
import { useEffect } from "react";
import { X, Zap, RefreshCw } from "lucide-react";
import { useStore } from "../store";
import CredentialsTab from "./model-config/CredentialsTab";
import RoutingTab from "./model-config/RoutingTab";
import PriorityTab from "./model-config/PriorityTab";
import { useState } from "react";

type PanelTab = "credentials" | "routing" | "priority";

const TAB_LABELS: Record<PanelTab, string> = {
  credentials: "凭证管理",
  routing: "路由策略",
  priority: "优先级",
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ModelConfigPanel({ open, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<PanelTab>("credentials");
  const modelProviders = useStore((s) => s.modelProviders);
  const fetchModelProviders = useStore((s) => s.fetchModelProviders);
  const fetchActiveModel = useStore((s) => s.fetchActiveModel);

  // 面板打开时：若 providers 为空则触发加载，同时刷新 activeModel
  useEffect(() => {
    if (open) {
      void fetchActiveModel();
      if (modelProviders.length === 0) {
        void fetchModelProviders();
      }
    }
  }, [open, fetchActiveModel, fetchModelProviders, modelProviders.length]);

  if (!open) return null;

  const handleRefresh = () => {
    void fetchModelProviders();
    void fetchActiveModel();
  };

  // 凭证保存后刷新 providers 列表（store 事件监听也会触发，此处作兜底）
  const handleConfigSaved = () => {
    void fetchModelProviders();
  };

  // 路由策略变更后刷新 activeModel（store setPreferredProvider 已自动刷新，此处作兜底）
  const handleRoutingChanged = () => {
    void fetchActiveModel();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[86vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-blue-600" />
            <div>
              <h2 className="text-lg font-semibold text-gray-800">模型配置</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                在「凭证管理」填写密钥，在「路由策略」为各功能指定模型
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
              title="刷新"
            >
              <RefreshCw size={16} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Tab 切换栏 */}
        <div className="px-6 pt-4 pb-3 border-b bg-white">
          <div className="inline-flex items-center gap-1 rounded-xl border border-gray-200 bg-gray-50 p-1">
            {(Object.keys(TAB_LABELS) as PanelTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                  activeTab === tab
                    ? "bg-white text-blue-700 border border-blue-200 shadow-sm"
                    : "text-gray-600 hover:text-gray-800"
                }`}
              >
                {TAB_LABELS[tab]}
              </button>
            ))}
          </div>
        </div>

        {/* Tab 内容区 */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {activeTab === "credentials" && (
            <CredentialsTab onConfigSaved={handleConfigSaved} />
          )}
          {activeTab === "routing" && (
            <RoutingTab onRoutingChanged={handleRoutingChanged} />
          )}
          {activeTab === "priority" && <PriorityTab />}
        </div>

        {/* 底部说明 */}
        <div className="px-6 py-3 border-t text-xs text-gray-400 text-center">
          先在「凭证管理」填写密钥，再在「路由策略」为各功能指定供应商和模型，最后在「优先级」调整自动选择的备选顺序。
        </div>
      </div>
    </div>
  );
}
