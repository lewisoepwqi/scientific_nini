import React from 'react';
import {
  BarChart3,
  ScatterChart,
  LineChart,
  BoxSelect,
  Activity,
  Grid3X3,
  Palette,
  Settings,
  Type,
  BarChart,
  Thermometer,
} from 'lucide-react';
import { useChartStore, useDatasetStore } from '@store/index';
import { cn } from '@utils/helpers';
import type { ChartType, JournalStyle } from '../../types';

interface ChartConfigPanelProps {
  className?: string;
  onGenerate?: () => void;
}

const chartTypes: { value: ChartType; label: string; icon: React.ReactNode }[] = [
  { value: 'scatter', label: '散点图', icon: <ScatterChart className="w-4 h-4" /> },
  { value: 'line', label: '折线图', icon: <LineChart className="w-4 h-4" /> },
  { value: 'bar', label: '柱状图', icon: <BarChart3 className="w-4 h-4" /> },
  { value: 'box', label: '箱线图', icon: <BoxSelect className="w-4 h-4" /> },
  { value: 'violin', label: '小提琴图', icon: <Activity className="w-4 h-4" /> },
  { value: 'histogram', label: '直方图', icon: <BarChart className="w-4 h-4" /> },
  { value: 'heatmap', label: '热图', icon: <Grid3X3 className="w-4 h-4" /> },
  { value: 'correlation', label: '相关性矩阵', icon: <Thermometer className="w-4 h-4" /> },
];

const journalStyles: { value: JournalStyle; label: string; color: string }[] = [
  { value: 'default', label: '默认', color: 'bg-gray-500' },
  { value: 'nature', label: 'Nature', color: 'bg-nature-primary' },
  { value: 'science', label: 'Science', color: 'bg-science-primary' },
  { value: 'cell', label: 'Cell', color: 'bg-cell-primary' },
];

const significanceMethods = [
  { value: 't-test', label: 't 检验' },
  { value: 'anova', label: 'ANOVA' },
  { value: 'mann-whitney', label: 'Mann-Whitney U' },
  { value: 'kruskal-wallis', label: 'Kruskal-Wallis' },
];

export const ChartConfigPanel: React.FC<ChartConfigPanelProps> = ({
  className,
  onGenerate,
}) => {
  const { config, updateConfig } = useChartStore();
  const { currentDataset } = useDatasetStore();

  if (!currentDataset) {
    return (
      <div className={cn('p-6 text-center', className)}>
        <p className="text-gray-500">请先上传数据</p>
      </div>
    );
  }

  const numericColumns = currentDataset.columns.filter((c) => c.type === 'numeric');
  const isCategoricalColumn = (col: (typeof currentDataset.columns)[number]) => {
    if (col.type === 'categorical') return true;
    if (col.type !== 'text') return false;
    if (!col.uniqueCount || col.uniqueCount <= 0) return false;
    if (col.uniqueCount <= 20) return true;
    return currentDataset.rowCount > 0
      ? col.uniqueCount / currentDataset.rowCount <= 0.05
      : false;
  };
  const categoricalColumns = currentDataset.columns.filter(isCategoricalColumn);
  const allColumns = currentDataset.columns;

  return (
    <div className={cn('space-y-6', className)}>
      {/* 图表类型选择 */}
      <div className="space-y-3">
        <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <BarChart3 className="w-4 h-4" />
          图表类型
        </label>
        <div className="grid grid-cols-4 gap-2">
          {chartTypes.map((type) => (
            <button
              key={type.value}
              onClick={() => updateConfig({ chartType: type.value })}
              className={cn(
                'flex flex-col items-center gap-1 p-3 rounded-lg border transition-all',
                config.chartType === type.value
                  ? 'border-primary-500 bg-primary-50 text-primary-700'
                  : 'border-gray-200 hover:border-primary-200 hover:bg-gray-50'
              )}
            >
              {type.icon}
              <span className="text-xs">{type.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 数据列选择 */}
      <div className="space-y-4">
        <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <Settings className="w-4 h-4" />
          数据配置
        </label>

        {/* X 轴 */}
        <div className="space-y-2">
          <label className="text-xs text-gray-500">X 轴</label>
          <select
            value={config.xColumn || ''}
            onChange={(e) => updateConfig({ xColumn: e.target.value || null })}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
          >
            <option value="">选择列...</option>
            {allColumns.map((col) => (
              <option key={col.name} value={col.name}>
                {col.name} ({col.type === 'numeric' ? '数值' : col.type === 'categorical' ? '类别' : '文本'})
              </option>
            ))}
          </select>
        </div>

        {/* Y 轴 */}
        <div className="space-y-2">
          <label className="text-xs text-gray-500">Y 轴</label>
          <select
            value={config.yColumn || ''}
            onChange={(e) => updateConfig({ yColumn: e.target.value || null })}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
          >
            <option value="">选择列...</option>
            {numericColumns.map((col) => (
              <option key={col.name} value={col.name}>
                {col.name} (数值)
              </option>
            ))}
          </select>
        </div>

        {/* 分组列 */}
        <div className="space-y-2">
          <label className="text-xs text-gray-500">分组列（可选）</label>
          <select
            value={config.groupColumn || ''}
            onChange={(e) => updateConfig({ groupColumn: e.target.value || null })}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
          >
            <option value="">无分组</option>
            {categoricalColumns.map((col) => (
              <option key={col.name} value={col.name}>
                {col.name} (类别)
              </option>
            ))}
          </select>
        </div>

        {/* 颜色列 */}
        <div className="space-y-2">
          <label className="text-xs text-gray-500">颜色列（可选）</label>
          <select
            value={config.colorColumn || ''}
            onChange={(e) => updateConfig({ colorColumn: e.target.value || null })}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
          >
            <option value="">默认颜色</option>
            {categoricalColumns.map((col) => (
              <option key={col.name} value={col.name}>
                {col.name} (类别)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 期刊样式 */}
      <div className="space-y-3">
        <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <Palette className="w-4 h-4" />
          期刊样式
        </label>
        <div className="grid grid-cols-2 gap-2">
          {journalStyles.map((style) => (
            <button
              key={style.value}
              onClick={() => updateConfig({ journalStyle: style.value })}
              className={cn(
                'flex items-center gap-2 p-3 rounded-lg border transition-all',
                config.journalStyle === style.value
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 hover:border-primary-200'
              )}
            >
              <span className={cn('w-4 h-4 rounded-full', style.color)} />
              <span className="text-sm">{style.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 统计选项 */}
      <div className="space-y-4">
        <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <Activity className="w-4 h-4" />
          统计选项
        </label>

        {/* 显示统计信息 */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={config.showStatistics}
            onChange={(e) => updateConfig({ showStatistics: e.target.checked })}
            className="w-4 h-4 text-primary-600 rounded focus:ring-primary-400"
          />
          <span className="text-sm text-gray-700">显示统计信息</span>
        </label>

        {/* 显著性标记 */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={config.showSignificance}
            onChange={(e) => updateConfig({ showSignificance: e.target.checked })}
            className="w-4 h-4 text-primary-600 rounded focus:ring-primary-400"
          />
          <span className="text-sm text-gray-700">显示显著性标记</span>
        </label>

        {/* 显著性检验方法 */}
        {config.showSignificance && (
          <div className="space-y-2 pl-6">
            <label className="text-xs text-gray-500">检验方法</label>
            <select
              value={config.significanceMethod}
              onChange={(e) =>
                updateConfig({
                  significanceMethod: e.target.value as typeof config.significanceMethod,
                })
              }
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
            >
              {significanceMethods.map((method) => (
                <option key={method.value} value={method.value}>
                  {method.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* 外观选项 */}
      <div className="space-y-4">
        <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <Type className="w-4 h-4" />
          外观设置
        </label>

        {/* 标题 */}
        <div className="space-y-2">
          <label className="text-xs text-gray-500">图表标题</label>
          <input
            type="text"
            value={config.title}
            onChange={(e) => updateConfig({ title: e.target.value })}
            placeholder="输入图表标题..."
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
          />
        </div>

        {/* 尺寸 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs text-gray-500">宽度 (px)</label>
            <input
              type="number"
              value={config.width}
              onChange={(e) => updateConfig({ width: parseInt(e.target.value) || 800 })}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs text-gray-500">高度 (px)</label>
            <input
              type="number"
              value={config.height}
              onChange={(e) => updateConfig({ height: parseInt(e.target.value) || 600 })}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
            />
          </div>
        </div>

        {/* 字体大小 */}
        <div className="space-y-2">
          <label className="text-xs text-gray-500">字体大小</label>
          <input
            type="range"
            min={8}
            max={24}
            value={config.fontSize}
            onChange={(e) => updateConfig({ fontSize: parseInt(e.target.value) })}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>8px</span>
            <span>{config.fontSize}px</span>
            <span>24px</span>
          </div>
        </div>

        {/* 显示选项 */}
        <div className="flex gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={config.showGrid}
              onChange={(e) => updateConfig({ showGrid: e.target.checked })}
              className="w-4 h-4 text-primary-600 rounded focus:ring-primary-400"
            />
            <span className="text-sm text-gray-700">显示网格</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={config.showLegend}
              onChange={(e) => updateConfig({ showLegend: e.target.checked })}
              className="w-4 h-4 text-primary-600 rounded focus:ring-primary-400"
            />
            <span className="text-sm text-gray-700">显示图例</span>
          </label>
        </div>
      </div>

      {/* 生成按钮 */}
      <button
        onClick={onGenerate}
        disabled={!config.xColumn || !config.yColumn}
        className={cn(
          'w-full py-3 px-4 rounded-lg font-medium transition-all',
          !config.xColumn || !config.yColumn
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-primary-500 text-white hover:bg-primary-600 shadow-lg hover:shadow-xl'
        )}
      >
        生成图表
      </button>
    </div>
  );
};

export default ChartConfigPanel;
