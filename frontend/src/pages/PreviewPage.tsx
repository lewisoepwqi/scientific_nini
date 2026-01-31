import React, { useState } from 'react';
import { FilePreview } from '@components/upload/FilePreview';
import { useDatasetStore, useTaskStore, useUIStore } from '@store/index';
import { cn } from '@utils/helpers';
import { Database, ArrowRight, BarChart3 } from 'lucide-react';
import { ExportButton } from '@components/ExportButton';
import { ShareDialog } from '@components/ShareDialog';
import { ExportTemplateSelect } from '@components/ExportTemplateSelect';
import { exportApi } from '@services/exportApi';

interface PreviewPageProps {
  className?: string;
}

export const PreviewPage: React.FC<PreviewPageProps> = ({ className }) => {
  const { currentDataset } = useDatasetStore();
  const { currentTask, taskCharts } = useTaskStore();
  const { setCurrentPage } = useUIStore();
  const [exportId, setExportId] = useState('');
  const [exportInfo, setExportInfo] = useState<string | null>(null);

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

      {/* 分享与复现 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-6 space-y-3">
          <h3 className="font-semibold text-gray-900">分享包复现</h3>
          <div className="flex gap-2">
            <input
              value={exportId}
              onChange={(event) => setExportId(event.target.value)}
              placeholder="输入分享包 ID"
              className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
            <button
              onClick={async () => {
                const response = await exportApi.getExport(exportId);
                if (response?.success && response.data) {
                  setExportInfo(`配置版本引用：${response.data.datasetVersionRef}`);
                } else {
                  setExportInfo('分享包不存在或加载失败');
                }
              }}
              className="px-3 py-2 text-sm text-white bg-primary-500 rounded-lg"
            >
              加载
            </button>
          </div>
          {exportInfo && <p className="text-sm text-gray-600">{exportInfo}</p>}
        </div>
        <div className="space-y-3">
          <ExportTemplateSelect />
          {currentTask && taskCharts[currentTask.id]?.[0] && (
            <ExportButton visualizationId={taskCharts[currentTask.id][0].id} />
          )}
          {currentTask && <ShareDialog taskId={currentTask.id} />}
        </div>
      </div>
    </div>
  );
};

export default PreviewPage;
