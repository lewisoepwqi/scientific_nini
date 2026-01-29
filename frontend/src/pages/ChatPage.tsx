import React from 'react';
import { AIChat } from '@components/chat/AIChat';
import { useDatasetStore, useUIStore } from '@store/index';
import { cn } from '@utils/helpers';
import { Database, Sparkles } from 'lucide-react';

interface ChatPageProps {
  className?: string;
}

export const ChatPage: React.FC<ChatPageProps> = ({ className }) => {
  const { currentDataset } = useDatasetStore();
  const { setCurrentPage } = useUIStore();

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* 页面标题 */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-primary-500" />
          AI 数据分析助手
        </h2>
        <p className="text-gray-500 mt-1">
          与 AI 助手对话，获取智能分析建议和帮助
        </p>
      </div>

      {/* AI 聊天组件 */}
      <div className="flex-1 min-h-0">
        <AIChat className="h-full" />
      </div>

      {/* 提示信息 */}
      {!currentDataset && (
        <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-3">
          <Database className="w-5 h-5 text-amber-500" />
          <p className="text-sm text-amber-700">
            尚未上传数据，AI 助手的分析能力将受到限制。
            <button
              onClick={() => setCurrentPage('upload')}
              className="ml-2 text-amber-800 underline hover:no-underline"
            >
              去上传数据
            </button>
          </p>
        </div>
      )}
    </div>
  );
};

export default ChatPage;
