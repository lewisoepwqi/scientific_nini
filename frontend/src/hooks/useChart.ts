import { useState, useCallback, useEffect } from 'react';
import { api } from '@services/api';
import { useChartStore, useDatasetStore, useUIStore } from '@store/index';
import { getJournalStyle } from '@utils/helpers';
import type { ChartConfig, ChartData, ChartType } from '../types';

interface UseChartOptions {
  autoGenerate?: boolean;
}

export function useChart(options: UseChartOptions = {}) {
  const { autoGenerate = false } = options;

  const {
    config,
    updateConfig,
    setCurrentChart,
    setIsGenerating,
    setChartData: setStoreChartData,
  } = useChartStore();
  const { currentDataset } = useDatasetStore();
  const { addNotification } = useUIStore();

  const [chartData, setChartData] = useState<ChartData | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * 生成图表
   */
  const generateChart = useCallback(async () => {
    if (!currentDataset) {
      setError('请先上传数据');
      setStoreChartData(null);
      return null;
    }

    if (!config.xColumn || !config.yColumn) {
      setError('请选择 X 轴和 Y 轴数据列');
      setStoreChartData(null);
      return null;
    }

    setIsGenerating(true);
    setError(null);

    try {
      const numericColumns = currentDataset.columns
        .filter((col) => col.type === 'numeric')
        .map((col) => col.name);

      const heatmapColumns =
        config.chartType === 'heatmap' || config.chartType === 'correlation'
          ? (config.xColumn && config.yColumn ? [config.xColumn, config.yColumn] : numericColumns)
          : undefined;

      const response = await api.chart.generateChart(currentDataset.id, config, {
        columns: heatmapColumns,
      });

      if (response.success && response.data) {
        // 应用期刊样式
        const journalStyle = getJournalStyle(config.journalStyle);
        let styledData: ChartData = {
          ...response.data,
          layout: {
            ...response.data.layout,
            ...journalStyle.layout,
            font: {
              ...journalStyle.layout.font,
              ...response.data.layout?.font,
            },
          },
        };

        // 处理 LINE 类型的 mode（主图表和叠加层都需要处理）
        // 注意：后端已经为 LINE 类型设置了 mode="lines+markers"，
        // 但为了兼容性，前端也进行处理
        if (config.chartType === 'line' || (config.layers && config.layers.some(l => l.chartType === 'line'))) {
          styledData = {
            ...styledData,
            data: styledData.data.map((trace) => {
              // 如果 trace 名称包含"叠加层"且是 line 类型，或主图表是 line 类型
              const isLineTrace = config.chartType === 'line' ||
                (trace.name && config.layers?.some(l => l.chartType === 'line' && trace.name?.includes(l.name)));
              const traceMode = (trace as { mode?: string }).mode;
              if (isLineTrace && traceMode && traceMode.includes('markers') && !traceMode.includes('lines')) {
                return {
                  ...trace,
                  mode: traceMode.replace('markers', 'lines+markers'),
                } as typeof trace;
              }
              return trace;
            }),
          };
        }

        setChartData(styledData);
        setStoreChartData(styledData);
        addNotification({
          type: 'success',
          message: '图表生成成功！',
        });
        return styledData;
      } else {
        throw new Error(response.error?.message || '图表生成失败');
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '图表生成失败';
      setError(errorMessage);
      setStoreChartData(null);
      addNotification({
        type: 'error',
        message: errorMessage,
      });
      return null;
    } finally {
      setIsGenerating(false);
    }
  }, [currentDataset, config, setIsGenerating, setStoreChartData, addNotification]);

  /**
   * 更新图表配置
   */
  const updateChartConfig = useCallback(
    (updates: Partial<ChartConfig>) => {
      updateConfig(updates);
    },
    [updateConfig]
  );

  /**
   * 更改图表类型
   */
  const changeChartType = useCallback(
    (type: ChartType) => {
      updateConfig({ chartType: type });
    },
    [updateConfig]
  );

  /**
   * 导出图表
   */
  const exportChart = useCallback(
    async (format: 'svg' | 'png' | 'pdf' | 'html') => {
      if (!currentDataset) {
        addNotification({
          type: 'error',
          message: '请先上传数据',
        });
        return;
      }

      try {
        const blob = await api.chart.exportChart(currentDataset.id, format, {
          width: config.width,
          height: config.height,
        });

        // 下载文件
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `chart_${Date.now()}.${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        addNotification({
          type: 'success',
          message: `图表已导出为 ${format.toUpperCase()} 格式`,
        });
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : '导出失败';
        addNotification({
          type: 'error',
          message: errorMessage,
        });
      }
    },
    [currentDataset, config.width, config.height, addNotification]
  );

  /**
   * 保存当前图表
   */
  const saveCurrentChart = useCallback(
    async (name: string) => {
      if (!chartData) {
        addNotification({
          type: 'error',
          message: '请先生成图表',
        });
        return;
      }

      try {
        const chart = {
          id: Math.random().toString(36).substring(7),
          name,
          config: { ...config },
          data: chartData,
          createdAt: new Date(),
          updatedAt: new Date(),
        };

        await api.chart.saveChart(chart);
        setCurrentChart(chart);

        addNotification({
          type: 'success',
          message: '图表已保存',
        });
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : '保存失败';
        addNotification({
          type: 'error',
          message: errorMessage,
        });
      }
    },
    [chartData, config, setCurrentChart, addNotification]
  );

  // 自动生成功能
  useEffect(() => {
    if (autoGenerate && currentDataset && config.xColumn && config.yColumn) {
      generateChart();
    }
  }, [autoGenerate, currentDataset, config.xColumn, config.yColumn, generateChart]);

  return {
    config,
    chartData,
    error,
    isGenerating: useChartStore.getState().isGenerating,
    generateChart,
    updateChartConfig,
    changeChartType,
    exportChart,
    saveCurrentChart,
  };
}
