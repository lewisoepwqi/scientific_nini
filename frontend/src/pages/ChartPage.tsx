import React from 'react';
import { ChartConfigPanel } from '@components/chart/ChartConfigPanel';
import { ChartDisplay } from '@components/chart/ChartDisplay';
import { useChart } from '@hooks/useChart';
import { useDatasetStore, useUIStore } from '@store/index';
import { cn } from '@utils/helpers';
import { Database, ArrowLeft, BarChart3 } from 'lucide-react';

interface ChartPageProps {
  className?: string;
}

export const ChartPage: React.FC<ChartPageProps> = ({ className }) => {
  const { currentDataset } = useDatasetStore();
  const { setCurrentPage } = useUIStore();
  
  const {
    isGenerating,
    generateChart,
  } = useChart();

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
        <div className="flex items-center gap-4">
          <button
            onClick={() => setCurrentPage('preview')}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h2 className="text-2xl font-bold text-gray-900">图表生成</h2>
            <p className="text-gray-500 mt-1">
              配置参数，生成专业的科研图表
            </p>
          </div>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 配置面板 */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl border border-gray-200 p-6 sticky top-6">
            <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <BarChart3 className="w-5 h-5" />
              图表配置
            </h3>
            <ChartConfigPanel onGenerate={generateChart} />
          </div>
        </div>

        {/* 图表展示区 */}
        <div className="lg:col-span-2">
          <ChartDisplay
            onGenerate={generateChart}
            isGenerating={isGenerating}
          />
        </div>
      </div>
    </div>
  );
};

export default ChartPage;
