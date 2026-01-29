import React, { useState } from 'react';
import { FileSpreadsheet, Database, Calendar, Hash, Type } from 'lucide-react';
import { useDatasetStore } from '@store/index';
import { cn, formatFileSize, formatNumber, formatDate } from '@utils/helpers';
import type { ColumnInfo, ColumnType } from '../../types';

interface FilePreviewProps {
  className?: string;
}

const getColumnTypeIcon = (type: ColumnType) => {
  switch (type) {
    case 'numeric':
      return <Hash className="w-4 h-4" />;
    case 'categorical':
      return <Type className="w-4 h-4" />;
    case 'datetime':
      return <Calendar className="w-4 h-4" />;
    default:
      return <Type className="w-4 h-4" />;
  }
};

const getColumnTypeColor = (type: ColumnType) => {
  switch (type) {
    case 'numeric':
      return 'bg-blue-50 text-blue-700 border-blue-200';
    case 'categorical':
      return 'bg-green-50 text-green-700 border-green-200';
    case 'datetime':
      return 'bg-purple-50 text-purple-700 border-purple-200';
    default:
      return 'bg-gray-50 text-gray-700 border-gray-200';
  }
};

const getColumnTypeLabel = (type: ColumnType) => {
  switch (type) {
    case 'numeric':
      return '数值';
    case 'categorical':
      return '类别';
    case 'datetime':
      return '日期';
    default:
      return '文本';
  }
};

export const FilePreview: React.FC<FilePreviewProps> = ({ className }) => {
  const { currentDataset } = useDatasetStore();
  const [selectedColumn, setSelectedColumn] = useState<ColumnInfo | null>(null);

  if (!currentDataset) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center p-12 text-center',
          className
        )}
      >
        <Database className="w-16 h-16 text-gray-300 mb-4" />
        <h3 className="text-lg font-medium text-gray-600">暂无数据</h3>
        <p className="text-sm text-gray-500 mt-2">请先上传一个数据文件</p>
      </div>
    );
  }

  const safeColumns = currentDataset.columns ?? [];
  const safePreviewData = currentDataset.previewData ?? [];
  const safeRowCount = currentDataset.rowCount || 0;
  const averageRowSize =
    safeRowCount > 0 ? (currentDataset.fileSize / safeRowCount) * 1024 : 0;

  return (
    <div className={cn('space-y-6', className)}>
      {/* 文件信息卡片 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-soft">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-primary-50 rounded-xl flex items-center justify-center">
              <FileSpreadsheet className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                {currentDataset.name}
              </h3>
              <p className="text-sm text-gray-500">{currentDataset.fileName}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-500">
              上传时间: {formatDate(currentDataset.uploadTime)}
            </p>
            <p className="text-sm text-gray-500">
              大小: {formatFileSize(currentDataset.fileSize)}
            </p>
          </div>
        </div>

        {/* 数据统计 */}
        <div className="grid grid-cols-3 gap-4 mt-6 pt-6 border-t border-gray-100">
          <div className="text-center">
            <p className="text-2xl font-bold text-primary-600">
              {formatNumber(safeRowCount, 0)}
            </p>
            <p className="text-sm text-gray-500">行数</p>
          </div>
          <div className="text-center border-x border-gray-100">
            <p className="text-2xl font-bold text-primary-600">
              {currentDataset.columnCount}
            </p>
            <p className="text-sm text-gray-500">列数</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-primary-600">
              {formatNumber(averageRowSize, 0)}
            </p>
            <p className="text-sm text-gray-500">平均行大小 (KB)</p>
          </div>
        </div>
      </div>

      {/* 列信息 */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-soft overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h4 className="font-semibold text-gray-900">数据列信息</h4>
          <p className="text-sm text-gray-500 mt-1">
            点击列名查看详细统计信息
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 p-6">
          {safeColumns.map((column) => (
            <button
              key={column.name}
              onClick={() => setSelectedColumn(column)}
              className={cn(
                'p-4 rounded-lg border text-left transition-all hover:shadow-md',
                selectedColumn?.name === column.name
                  ? 'border-primary-400 bg-primary-50'
                  : 'border-gray-200 hover:border-primary-200'
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className={cn(
                    'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded border',
                    getColumnTypeColor(column.type)
                  )}
                >
                  {getColumnTypeIcon(column.type)}
                  {getColumnTypeLabel(column.type)}
                </span>
                {column.nullable && (
                  <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                    可空
                  </span>
                )}
              </div>
              <p className="font-medium text-gray-900 truncate" title={column.name}>
                {column.name}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {column.uniqueCount} 唯一值
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* 选中列的详细统计 */}
      {selectedColumn && selectedColumn.type === 'numeric' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-soft">
          <div className="flex items-center justify-between mb-4">
            <h4 className="font-semibold text-gray-900">
              "{selectedColumn.name}" 统计信息
            </h4>
            <button
              onClick={() => setSelectedColumn(null)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              关闭
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">最小值</p>
              <p className="text-lg font-semibold text-gray-900">
                {formatNumber(selectedColumn.min || 0)}
              </p>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">最大值</p>
              <p className="text-lg font-semibold text-gray-900">
                {formatNumber(selectedColumn.max || 0)}
              </p>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">平均值</p>
              <p className="text-lg font-semibold text-gray-900">
                {formatNumber(selectedColumn.mean || 0)}
              </p>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">标准差</p>
              <p className="text-lg font-semibold text-gray-900">
                {formatNumber(selectedColumn.std || 0)}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mt-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">中位数</p>
              <p className="text-lg font-semibold text-gray-900">
                {formatNumber(selectedColumn.median || 0)}
              </p>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">唯一值数量</p>
              <p className="text-lg font-semibold text-gray-900">
                {formatNumber(selectedColumn.uniqueCount, 0)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 数据预览表格 */}
      {safePreviewData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-soft overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100">
            <h4 className="font-semibold text-gray-900">数据预览</h4>
            <p className="text-sm text-gray-500 mt-1">
              显示前 {safePreviewData.length} 行数据
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {safeColumns.map((col) => (
                    <th
                      key={col.name}
                      className="px-4 py-3 text-left font-medium text-gray-700 border-b border-gray-200"
                    >
                      <div className="flex items-center gap-1">
                        {getColumnTypeIcon(col.type)}
                        <span className="truncate max-w-[150px]" title={col.name}>
                          {col.name}
                        </span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {safePreviewData.map((row, index) => (
                  <tr
                    key={index}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    {safeColumns.map((col) => (
                      <td
                        key={col.name}
                        className="px-4 py-3 text-gray-600 border-b border-gray-100"
                      >
                        <span className="truncate max-w-[150px] block" title={String(row[col.name])}>
                          {row[col.name] === null || row[col.name] === undefined
                            ? '-'
                            : String(row[col.name])}
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default FilePreview;
