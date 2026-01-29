import React from 'react';
import { Sidebar } from '@components/common/Sidebar';
import { Header } from '@components/common/Header';
import { NotificationContainer } from '@components/common/Notification';
import { UploadPage } from '@pages/UploadPage';
import { PreviewPage } from '@pages/PreviewPage';
import { ChartPage } from '@pages/ChartPage';
import { AnalysisPage } from '@pages/AnalysisPage';
import { ChatPage } from '@pages/ChatPage';
import { useUIStore } from '@store/index';

// 页面组件映射
const pageComponents: Record<string, React.FC> = {
  upload: UploadPage,
  preview: PreviewPage,
  chart: ChartPage,
  analysis: AnalysisPage,
  chat: ChatPage,
};

function App() {
  const { currentPage } = useUIStore();

  const CurrentPageComponent = pageComponents[currentPage] || UploadPage;

  return (
    <div className="flex h-screen bg-gray-50">
      {/* 侧边栏 */}
      <Sidebar />

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶部导航 */}
        <Header />

        {/* 页面内容 */}
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-7xl mx-auto">
            <CurrentPageComponent />
          </div>
        </main>
      </div>

      {/* 通知容器 */}
      <NotificationContainer />
    </div>
  );
}

export default App;
