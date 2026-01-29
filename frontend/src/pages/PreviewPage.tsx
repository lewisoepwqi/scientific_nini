import React from 'react';
import { FilePreview } from '@components/upload/FilePreview';
import { useDatasetStore, useUIStore } from '@store/index';
import { cn } from '@utils/helpers';
import { Database, ArrowRight, BarChart3 } from 'lucide-react';

interface PreviewPageProps {
  className?: string;
}

export const PreviewPage: React.FC<PreviewPageProps> = ({ className }) => {
  const { currentDataset } = useDatasetStore();
  const { setCurrentPage } = useUIStore();

  if (!currentDataset) {
    return (
      <div className={cn('flex flex-col items-center justify-center h-full', className)}>
        <div className="w-24 h-24 bg-gray-100 rounded-full flex items-center justify-center mb-6">
          <Database className="w-12 h-12 text-gray-400" />
        </div>
        <h2 className="text-2xl font-bold text-gray-700 mb-3">暂无数据</h2>
        <p className="text-gray-500 mb-6">请先上传一个数据文件</p>
        <button
          onClick={() => setCurrentPage('upload')}
          className="px-6 py-2.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
        >
          去上传数据
        </button>
      </div>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">数据预览</h2>
          <p className="text-gray-500 mt-1">
            查看数据结构和统计信息，为后续分析做准备
          </p>
        </div>
        <button
          onClick={() => setCurrentPage('chart')}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors shadow-lg hover:shadow-xl"
        >
          <BarChart3 className="w-5 h-5" />
          开始分析
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {/* 数据预览 */}
      <FilePreview />
    </div>
  );
};

export default PreviewPage;
