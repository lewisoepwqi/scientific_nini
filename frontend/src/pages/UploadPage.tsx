import React from 'react';
import { FileUpload } from '@components/upload/FileUpload';
import { FilePreview } from '@components/upload/FilePreview';
import { useDatasetStore, useUIStore } from '@store/index';
import { cn } from '@utils/helpers';

interface UploadPageProps {
  className?: string;
}

export const UploadPage: React.FC<UploadPageProps> = ({ className }) => {
  const { currentDataset } = useDatasetStore();
  const { setCurrentPage } = useUIStore();

  const handleUploadSuccess = () => {
    // 上传成功后自动跳转到数据预览页面
    setTimeout(() => {
      setCurrentPage('preview');
    }, 1500);
  };

  return (
    <div className={cn('space-y-8', className)}>
      {/* 页面标题 */}
      <div className="text-center py-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-3">
          上传你的数据
        </h2>
        <p className="text-gray-500 max-w-xl mx-auto">
          支持 CSV、Excel (.xlsx, .xls) 和文本文件。我们将自动识别数据类型并为你提供智能分析建议。
        </p>
      </div>

      {/* 上传区域 */}
      <div className="max-w-2xl mx-auto">
        <FileUpload onUploadSuccess={handleUploadSuccess} />
      </div>

      {/* 数据预览 */}
      {currentDataset && (
        <div className="mt-12">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-semibold text-gray-900">数据预览</h3>
            <button
              onClick={() => setCurrentPage('preview')}
              className="text-sm text-primary-600 hover:text-primary-700 font-medium"
            >
              查看完整数据 →
            </button>
          </div>
          <FilePreview />
        </div>
      )}

      {/* 支持的格式说明 */}
      {!currentDataset && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto mt-12">
          <div className="p-6 bg-white rounded-xl border border-gray-200 text-center">
            <div className="w-12 h-12 bg-green-50 rounded-xl flex items-center justify-center mx-auto mb-4">
              <span className="text-green-600 font-bold">CSV</span>
            </div>
            <h4 className="font-medium text-gray-900 mb-2">CSV 文件</h4>
            <p className="text-sm text-gray-500">
              逗号分隔值文件，最常见的数据交换格式
            </p>
          </div>
          <div className="p-6 bg-white rounded-xl border border-gray-200 text-center">
            <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mx-auto mb-4">
              <span className="text-blue-600 font-bold">XLSX</span>
            </div>
            <h4 className="font-medium text-gray-900 mb-2">Excel 文件</h4>
            <p className="text-sm text-gray-500">
              Microsoft Excel 电子表格，支持多工作表
            </p>
          </div>
          <div className="p-6 bg-white rounded-xl border border-gray-200 text-center">
            <div className="w-12 h-12 bg-gray-50 rounded-xl flex items-center justify-center mx-auto mb-4">
              <span className="text-gray-600 font-bold">TXT</span>
            </div>
            <h4 className="font-medium text-gray-900 mb-2">文本文件</h4>
            <p className="text-sm text-gray-500">
              制表符或自定义分隔符的文本数据
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default UploadPage;
