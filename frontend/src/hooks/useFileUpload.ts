import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { api } from '@services/api';
import { useDatasetStore, useUIStore } from '@store/index';
import { generateId } from '@utils/helpers';
import type { ColumnInfo, ColumnType, ParseOptions } from '../types';

interface UseFileUploadOptions {
  maxFiles?: number;
  maxSize?: number;
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}

export function useFileUpload(options: UseFileUploadOptions = {}) {
  const { maxFiles = 1, maxSize = 100 * 1024 * 1024 } = options;
  
  const { addDataset, setUploadProgress, clearUploadProgress } = useDatasetStore();
  const { addNotification } = useUIStore();
  
  const [isUploading, setIsUploading] = useState(false);

  const mapColumnType = (
    dtype?: string,
    uniqueCount?: number,
    totalRows?: number
  ): ColumnType => {
    if (!dtype) return 'text';
    const normalized = dtype.toLowerCase();
    if (normalized.includes('int') || normalized.includes('float') || normalized.includes('double')) {
      return 'numeric';
    }
    if (normalized.includes('date') || normalized.includes('time')) {
      return 'datetime';
    }
    if (normalized.includes('bool') || normalized.includes('category')) {
      return 'categorical';
    }
    if (normalized.includes('object') || normalized.includes('string')) {
      const safeUniqueCount = Number.isFinite(uniqueCount) ? (uniqueCount as number) : undefined;
      const safeTotalRows = Number.isFinite(totalRows) ? (totalRows as number) : undefined;
      if (safeUniqueCount !== undefined) {
        if (safeUniqueCount <= 20) {
          return 'categorical';
        }
        if (safeTotalRows && safeTotalRows > 0 && safeUniqueCount / safeTotalRows <= 0.05) {
          return 'categorical';
        }
      }
      return 'text';
    }
    return 'text';
  };

  const normalizeColumns = (
    columns: Array<Record<string, unknown>>,
    totalRows?: number
  ): ColumnInfo[] => {
    return columns.map((column) => ({
      name: String(column.name ?? ''),
      type: mapColumnType(
        (column as { dtype?: string }).dtype,
        Number((column as { unique_count?: number }).unique_count),
        totalRows
      ),
      nullable: Boolean((column as { nullable?: boolean }).nullable),
      uniqueCount: Number((column as { unique_count?: number }).unique_count ?? 0),
      sample: Array.isArray((column as { sample_values?: unknown[] }).sample_values)
        ? (column as { sample_values?: unknown[] }).sample_values
        : [],
    }));
  };

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;

      setIsUploading(true);
      const file = acceptedFiles[0];

      try {
        // 设置初始进度
        setUploadProgress({
          loaded: 0,
          total: file.size,
          percentage: 0,
          status: 'uploading',
          message: '正在上传文件...',
        });

        // 解析选项
        const parseOptions: ParseOptions = {
          hasHeader: true,
          headerRow: 0,
        };

        // 上传文件
        const response = await api.upload.uploadFile(
          file,
          parseOptions,
          (progressEvent) => {
            const loaded = progressEvent.loaded;
            const total = progressEvent.total || file.size;
            const percentage = Math.round((loaded / total) * 100);
            
            setUploadProgress({
              loaded,
              total,
              percentage,
              status: percentage < 100 ? 'uploading' : 'processing',
              message: percentage < 100 ? '正在上传文件...' : '正在处理数据...',
            });
          }
        );

        if (response.success && response.data) {
          const responseData = response.data as Record<string, unknown>;
          const datasetId = String(responseData.id ?? '');
          const fallbackName = file.name.replace(/\.[^/.]+$/, '');
          let previewData: Record<string, unknown>[] = [];
          let rowCount = Number(responseData.row_count ?? responseData.rowCount ?? 0);
          const initialColumns = Array.isArray(responseData.columns)
            ? normalizeColumns(responseData.columns as Array<Record<string, unknown>>, rowCount || undefined)
            : [];
          let previewColumns = initialColumns;
          let columnCount = Number(responseData.column_count ?? responseData.columnCount ?? initialColumns.length);

          try {
            if (datasetId) {
              const previewResponse = await api.upload.previewFile(datasetId, 50);
              if (previewResponse.success && previewResponse.data) {
                const previewPayload = previewResponse.data as Record<string, unknown>;
                const previewRowCount = Number(previewPayload.total_rows ?? rowCount);
                const columns = Array.isArray(previewPayload.columns)
                  ? normalizeColumns(
                      previewPayload.columns as Array<Record<string, unknown>>,
                      previewRowCount || undefined
                    )
                  : [];
                previewColumns = columns.length > 0 ? columns : previewColumns;
                previewData = Array.isArray(previewPayload.data)
                  ? (previewPayload.data as Record<string, unknown>[])
                  : [];
                rowCount = previewRowCount;
                columnCount = previewColumns.length || columnCount;
              }
            }
          } catch (previewError) {
            console.warn('预览数据获取失败:', previewError);
          }

          // 构建数据集信息
          const dataset = {
            id: datasetId || generateId(),
            name: String(responseData.name ?? fallbackName),
            fileName: String(responseData.filename ?? file.name),
            fileSize: Number(responseData.file_size ?? file.size),
            rowCount,
            columnCount,
            columns: previewColumns,
            uploadTime: responseData.created_at ? new Date(String(responseData.created_at)) : new Date(),
            previewData,
          };

          addDataset(dataset);
          
          setUploadProgress({
            loaded: file.size,
            total: file.size,
            percentage: 100,
            status: 'completed',
            message: '上传成功！',
          });

          addNotification({
            type: 'success',
            message: `文件 "${file.name}" 上传成功！`,
          });

          options.onSuccess?.();
          
          // 延迟清除进度
          setTimeout(clearUploadProgress, 2000);
        } else {
          throw new Error(response.error?.message || '上传失败');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '上传失败';
        
        setUploadProgress({
          loaded: 0,
          total: file.size,
          percentage: 0,
          status: 'error',
          message: errorMessage,
        });

        addNotification({
          type: 'error',
          message: `上传失败: ${errorMessage}`,
        });

        options.onError?.(error instanceof Error ? error : new Error(errorMessage));
      } finally {
        setIsUploading(false);
      }
    },
    [addDataset, setUploadProgress, clearUploadProgress, addNotification, options]
  );

  const { getRootProps, getInputProps, isDragActive, isDragReject, fileRejections } =
    useDropzone({
      onDrop,
      accept: {
        'text/csv': ['.csv'],
        'application/vnd.ms-excel': ['.xls'],
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
        'text/plain': ['.txt', '.tsv'],
      },
      maxFiles,
      maxSize,
      multiple: maxFiles > 1,
    });

  // 获取错误信息
  const getErrorMessage = () => {
    if (fileRejections.length > 0) {
      const rejection = fileRejections[0];
      const errors = rejection.errors;
      if (errors[0]?.code === 'file-too-large') {
        return `文件大小超过限制 (${(maxSize / 1024 / 1024).toFixed(0)}MB)`;
      }
      if (errors[0]?.code === 'file-invalid-type') {
        return '不支持的文件格式，请上传 CSV 或 Excel 文件';
      }
      return errors[0]?.message || '文件上传失败';
    }
    return null;
  };

  return {
    getRootProps,
    getInputProps,
    isDragActive,
    isDragReject,
    isUploading,
    errorMessage: getErrorMessage(),
  };
}
