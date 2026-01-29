import React from 'react';
import { Upload, FileSpreadsheet, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { useFileUpload } from '@hooks/useFileUpload';
import { useDatasetStore } from '@store/index';
import { cn, formatFileSize } from '@utils/helpers';

interface FileUploadProps {
  onUploadSuccess?: () => void;
  className?: string;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  onUploadSuccess,
  className,
}) => {
  const { getRootProps, getInputProps, isDragActive, isDragReject, isUploading, errorMessage } =
    useFileUpload({
      onSuccess: onUploadSuccess,
    });

  const { uploadProgress } = useDatasetStore();

  return (
    <div className={cn('w-full', className)}>
      {/* 拖拽区域 */}
      <div
        {...getRootProps()}
        className={cn(
          'relative border-2 border-dashed rounded-2xl p-8 transition-all duration-300 cursor-pointer',
          'hover:border-primary-400 hover:bg-primary-50/50',
          isDragActive && 'border-primary-500 bg-primary-50',
          isDragReject && 'border-red-400 bg-red-50',
          isUploading && 'pointer-events-none opacity-70',
          'focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2'
        )}
      >
        <input {...getInputProps()} />

        <div className="flex flex-col items-center justify-center text-center space-y-4">
          {/* 图标 */}
          <div
            className={cn(
              'w-16 h-16 rounded-full flex items-center justify-center transition-colors',
              isDragActive ? 'bg-primary-100' : 'bg-gray-100',
              isDragReject && 'bg-red-100'
            )}
          >
            {isUploading ? (
              <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
            ) : isDragReject ? (
              <AlertCircle className="w-8 h-8 text-red-500" />
            ) : (
              <Upload
                className={cn(
                  'w-8 h-8 transition-colors',
                  isDragActive ? 'text-primary-500' : 'text-gray-400'
                )}
              />
            )}
          </div>

          {/* 文字提示 */}
          <div className="space-y-2">
            <p className="text-lg font-medium text-gray-700">
              {isUploading
                ? '正在上传...'
                : isDragActive
                ? '松开以上传文件'
                : '拖拽文件到此处，或点击选择文件'}
            </p>
            <p className="text-sm text-gray-500">
              支持 CSV、Excel (.xlsx, .xls)、TXT 格式，最大 100MB
            </p>
          </div>

          {/* 支持的格式标签 */}
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-green-50 text-green-700 text-xs font-medium rounded-full">
              <FileSpreadsheet className="w-3 h-3" />
              CSV
            </span>
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-full">
              <FileSpreadsheet className="w-3 h-3" />
              Excel
            </span>
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-600 text-xs font-medium rounded-full">
              TXT
            </span>
          </div>
        </div>
      </div>

      {/* 错误提示 */}
      {errorMessage && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <p className="text-sm text-red-700">{errorMessage}</p>
        </div>
      )}

      {/* 上传进度 */}
      {uploadProgress && (
        <div className="mt-4 p-4 bg-primary-50 border border-primary-200 rounded-lg space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {uploadProgress.status === 'completed' ? (
                <CheckCircle2 className="w-5 h-5 text-green-500" />
              ) : uploadProgress.status === 'error' ? (
                <AlertCircle className="w-5 h-5 text-red-500" />
              ) : (
                <Loader2 className="w-5 h-5 text-primary-500 animate-spin" />
              )}
              <span className="text-sm font-medium text-gray-700">
                {uploadProgress.message}
              </span>
            </div>
            <span className="text-sm text-gray-500">
              {formatFileSize(uploadProgress.loaded)} /{' '}
              {formatFileSize(uploadProgress.total)}
            </span>
          </div>

          {/* 进度条 */}
          <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-300',
                uploadProgress.status === 'completed'
                  ? 'bg-green-500'
                  : uploadProgress.status === 'error'
                  ? 'bg-red-500'
                  : 'bg-primary-500'
              )}
              style={{ width: `${uploadProgress.percentage}%` }}
            />
          </div>

          {/* 百分比 */}
          <div className="text-right">
            <span
              className={cn(
                'text-sm font-medium',
                uploadProgress.status === 'completed'
                  ? 'text-green-600'
                  : uploadProgress.status === 'error'
                  ? 'text-red-600'
                  : 'text-primary-600'
              )}
            >
              {uploadProgress.percentage}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileUpload;
