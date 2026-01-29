import React, { useRef, useCallback } from 'react';
import createPlotlyComponent from 'react-plotly.js/factory';
import Plotly from 'plotly.js-dist-min';
import {
  Download,
  Save,
  RefreshCw,
  Settings,
  Image as ImageIcon,
  FileCode,
} from 'lucide-react';
import { useChartStore, useDatasetStore } from '@store/index';
import { cn } from '@utils/helpers';
import { api } from '@services/api';

const Plot = createPlotlyComponent(Plotly);

interface ChartDisplayProps {
  className?: string;
  onGenerate?: () => void;
  isGenerating?: boolean;
}

export const ChartDisplay: React.FC<ChartDisplayProps> = ({
  className,
  onGenerate,
  isGenerating = false,
}) => {
  const { chartData, config } = useChartStore();
  const { currentDataset } = useDatasetStore();
  const plotRef = useRef<HTMLDivElement>(null);

  /**
   * 导出图表
   */
  const handleExport = useCallback(
    async (format: 'png' | 'svg' | 'jpeg') => {
      if (!plotRef.current) return;

      const plotElement = plotRef.current.querySelector('.js-plotly-plot') as HTMLElement;
      if (!plotElement) return;

      // 使用 Plotly 的 toImage 方法
      try {
        const imageData = await Plotly.toImage(plotElement, {
          format,
          width: config.width,
          height: config.height,
          scale: 2,
        });

        // 下载图片
        const link = document.createElement('a');
        link.href = imageData;
        link.download = `chart_${Date.now()}.${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } catch (error) {
        console.error('导出失败:', error);
      }
    },
    [config.width, config.height]
  );

  /**
   * 保存图表到后端
   */
  const handleSave = useCallback(async () => {
    if (!chartData || !currentDataset) return;

    try {
      const chart = {
        id: Math.random().toString(36).substring(7),
        name: config.title || '未命名图表',
        config: { ...config },
        data: chartData,
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      await api.chart.saveChart(chart);
      alert('图表已保存！');
    } catch (error) {
      console.error('保存失败:', error);
      alert('保存失败，请重试');
    }
  }, [chartData, config, currentDataset]);

  // 如果没有数据，显示空状态
  if (!chartData) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center h-full min-h-[400px] bg-gray-50 rounded-xl border-2 border-dashed border-gray-200',
          className
        )}
      >
        <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center mb-4">
          <Settings className="w-10 h-10 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-600 mb-2">暂无图表</h3>
        <p className="text-sm text-gray-500 mb-4">
          在左侧面板配置图表参数，然后点击生成按钮
        </p>
        <button
          onClick={onGenerate}
          disabled={isGenerating || !config.xColumn || !config.yColumn}
          className={cn(
            'flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-all',
            isGenerating || !config.xColumn || !config.yColumn
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-primary-500 text-white hover:bg-primary-600'
          )}
        >
          {isGenerating ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              生成中...
            </>
          ) : (
            <>
              <RefreshCw className="w-4 h-4" />
              生成图表
            </>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* 工具栏 */}
      <div className="flex items-center justify-between bg-white rounded-lg border border-gray-200 p-3">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-gray-900">{config.title}</h3>
        </div>
        <div className="flex items-center gap-2">
          {/* 重新生成 */}
          <button
            onClick={onGenerate}
            disabled={isGenerating}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('w-4 h-4', isGenerating && 'animate-spin')} />
            重新生成
          </button>

          {/* 导出下拉菜单 */}
          <div className="relative group">
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors">
              <Download className="w-4 h-4" />
              导出
            </button>
            <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
              <button
                onClick={() => handleExport('png')}
                className="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 first:rounded-t-lg"
              >
                <ImageIcon className="w-4 h-4" />
                导出为 PNG
              </button>
              <button
                onClick={() => handleExport('svg')}
                className="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                <FileCode className="w-4 h-4" />
                导出为 SVG
              </button>
              <button
                onClick={() => handleExport('jpeg')}
                className="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 last:rounded-b-lg"
              >
                <ImageIcon className="w-4 h-4" />
                导出为 JPEG
              </button>
            </div>
          </div>

          {/* 保存 */}
          <button
            onClick={handleSave}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-primary-500 rounded-lg hover:bg-primary-600 transition-colors"
          >
            <Save className="w-4 h-4" />
            保存
          </button>
        </div>
      </div>

      {/* 图表容器 */}
      <div
        ref={plotRef}
        className="bg-white rounded-xl border border-gray-200 overflow-hidden"
      >
        <Plot
          data={chartData.data}
          layout={{
            ...chartData.layout,
            autosize: true,
          }}
          config={{
            ...chartData.config,
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
          }}
          style={{ width: '100%', height: config.height }}
          useResizeHandler={true}
        />
      </div>

      {/* 图表信息 */}
      <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-600">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <span className="text-gray-500">图表类型:</span>{' '}
            <span className="font-medium">{config.chartType}</span>
          </div>
          <div>
            <span className="text-gray-500">X 轴:</span>{' '}
            <span className="font-medium">{config.xColumn}</span>
          </div>
          <div>
            <span className="text-gray-500">Y 轴:</span>{' '}
            <span className="font-medium">{config.yColumn}</span>
          </div>
          <div>
            <span className="text-gray-500">期刊样式:</span>{' '}
            <span className="font-medium">{config.journalStyle}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChartDisplay;
