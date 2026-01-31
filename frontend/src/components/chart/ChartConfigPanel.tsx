import React, { useState } from 'react';
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
  Layers,
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useChartStore, useDatasetStore } from '@store/index';
import { cn } from '@utils/helpers';
import type { ChartType, JournalStyle, ChartLayer } from '../../types';
import { CHART_COMPATIBILITY, MAX_OVERLAY_LAYERS } from '../../types';

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

// 叠加层配置卡片组件
interface LayerConfigCardProps {
  layer: ChartLayer;
  index: number;
  compatibleTypes: ChartType[];
  numericColumns: { name: string }[];
  allColumns: { name: string; type: string }[];
  primaryXColumn: string | null;
  primaryYColumn: string | null;
  onUpdate: (updates: Partial<ChartLayer>) => void;
  onRemove: () => void;
}

const LayerConfigCard: React.FC<LayerConfigCardProps> = ({
  layer,
  index,
  compatibleTypes,
  numericColumns,
  allColumns,
  primaryXColumn,
  primaryYColumn,
  onUpdate,
  onRemove,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const getChartTypeLabel = (type: ChartType) => {
    return chartTypes.find((t) => t.value === type)?.label || type;
  };

  return (
    <div className="border border-gray-200 rounded-lg bg-gray-50 overflow-hidden">
      {/* 层标题栏 */}
      <div
        className="flex items-center justify-between p-3 bg-white cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-gray-500" />
          <span className="text-sm font-medium">
            叠加层 {index + 1}: {getChartTypeLabel(layer.chartType)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="p-1 text-red-500 hover:bg-red-50 rounded"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </div>
      </div>

      {/* 层配置内容 */}
      {isExpanded && (
        <div className="p-3 space-y-3 border-t border-gray-200">
          {/* 图表类型 */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500">图表类型</label>
            <select
              value={layer.chartType}
              onChange={(e) => onUpdate({ chartType: e.target.value as ChartType })}
              className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
            >
              {compatibleTypes.map((type) => (
                <option key={type} value={type}>
                  {getChartTypeLabel(type)}
                </option>
              ))}
            </select>
          </div>

          {/* 层名称 */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500">层名称</label>
            <input
              type="text"
              value={layer.name}
              onChange={(e) => onUpdate({ name: e.target.value })}
              placeholder="输入层名称..."
              className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
            />
          </div>

          {/* X 轴 */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500">X 轴</label>
            <select
              value={layer.xColumn || ''}
              onChange={(e) => onUpdate({ xColumn: e.target.value || null })}
              className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
            >
              <option value="">
                {primaryXColumn ? `使用主图层 (${primaryXColumn})` : '选择列...'}
              </option>
              {allColumns.map((col) => (
                <option key={col.name} value={col.name}>
                  {col.name}
                </option>
              ))}
            </select>
          </div>

          {/* Y 轴 */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500">Y 轴</label>
            <select
              value={layer.yColumn || ''}
              onChange={(e) => onUpdate({ yColumn: e.target.value || null })}
              className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
            >
              <option value="">
                {primaryYColumn ? `使用主图层 (${primaryYColumn})` : '选择列...'}
              </option>
              {numericColumns.map((col) => (
                <option key={col.name} value={col.name}>
                  {col.name}
                </option>
              ))}
            </select>
          </div>

          {/* Y 轴尺度 */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500">Y 轴尺度</label>
            <select
              value={layer.yAxisMode || 'primary'}
              onChange={(e) => onUpdate({ yAxisMode: e.target.value as 'primary' | 'secondary' })}
              className="w-full px-2 py-1.5 border border-gray-200 rounded text-sm"
            >
              <option value="primary">使用主图表 Y 轴</option>
              <option value="secondary">使用右侧第二 Y 轴</option>
            </select>
          </div>

          {/* 透明度 */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500">透明度: {layer.opacity}</label>
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.1}
              value={layer.opacity}
              onChange={(e) => onUpdate({ opacity: parseFloat(e.target.value) })}
              className="w-full"
            />
          </div>

          {/* 颜色覆盖 */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500">自定义颜色（可选）</label>
            <div className="flex gap-2">
              {layer.colorOverride ? (
                <>
                  <input
                    type="color"
                    value={layer.colorOverride}
                    onChange={(e) => onUpdate({ colorOverride: e.target.value })}
                    className="w-10 h-8 border border-gray-200 rounded cursor-pointer"
                  />
                  <button
                    onClick={() => onUpdate({ colorOverride: null })}
                    className="px-2 py-1 text-xs text-gray-500 border border-gray-200 rounded hover:bg-gray-100"
                  >
                    使用默认
                  </button>
                </>
              ) : (
                <button
                  onClick={() => onUpdate({ colorOverride: '#3B82F6' })}
                  className="px-3 py-1.5 text-xs text-primary-600 border border-primary-200 rounded hover:bg-primary-50"
                >
                  设置自定义颜色
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const ChartConfigPanel: React.FC<ChartConfigPanelProps> = ({
  className,
  onGenerate,
}) => {
  const { config, updateConfig, addLayer, updateLayer, removeLayer, clearLayers } = useChartStore();
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

  // 获取兼容的图表类型
  const compatibleTypes = CHART_COMPATIBILITY[config.chartType] || [];
  const canAddLayer = compatibleTypes.length > 0 && (config.layers?.length || 0) < MAX_OVERLAY_LAYERS;

  // 处理主图表类型变更
  const handleChartTypeChange = (newType: ChartType) => {
    // 清除不兼容的叠加层
    const newCompatible = CHART_COMPATIBILITY[newType] || [];
    if (config.layers && config.layers.length > 0) {
      const hasIncompatible = config.layers.some(
        (layer) => !newCompatible.includes(layer.chartType)
      );
      if (hasIncompatible) {
        clearLayers();
      }
    }
    updateConfig({ chartType: newType });
  };

  // 添加新叠加层
  const handleAddLayer = () => {
    if (!canAddLayer) return;

    // 默认使用第一个兼容的类型
    const defaultType = compatibleTypes[0];
    const newLayer: Omit<ChartLayer, 'id'> = {
      chartType: defaultType,
      name: `叠加层 ${(config.layers?.length || 0) + 1}`,
      xColumn: null,
      yColumn: null,
      groupColumn: null,
      colorColumn: null,
      opacity: 0.7,
      colorOverride: null,
      yAxisMode: 'primary',
    };
    addLayer(newLayer);
  };

  // 判断图表类型按钮是否禁用（叠加模式下，不兼容的类型禁用）
  const isTypeDisabled = (type: ChartType) => {
    if (!config.layers || config.layers.length === 0) return false;
    return !compatibleTypes.includes(type);
  };

  return (
    <div className={cn('space-y-6', className)}>
      {/* 图表类型选择 */}
      <div className="space-y-3">
        <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
          <BarChart3 className="w-4 h-4" />
          主图表类型
        </label>
        <div className="grid grid-cols-4 gap-2">
          {chartTypes.map((type) => {
            const disabled = isTypeDisabled(type.value);
            return (
              <button
                key={type.value}
                onClick={() => !disabled && handleChartTypeChange(type.value)}
                disabled={disabled}
                className={cn(
                  'flex flex-col items-center gap-1 p-3 rounded-lg border transition-all',
                  disabled
                    ? 'border-gray-100 bg-gray-50 text-gray-300 cursor-not-allowed'
                    : config.chartType === type.value
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-gray-200 hover:border-primary-200 hover:bg-gray-50'
                )}
                title={disabled ? '与现有叠加层不兼容' : undefined}
              >
                {type.icon}
                <span className="text-xs">{type.label}</span>
              </button>
            );
          })}
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

      {/* 叠加图层管理 */}
      {compatibleTypes.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
              <Layers className="w-4 h-4" />
              叠加图层
            </label>
            <button
              onClick={handleAddLayer}
              disabled={!canAddLayer}
              className={cn(
                'flex items-center gap-1 px-2 py-1 text-xs rounded transition-all',
                canAddLayer
                  ? 'bg-primary-500 text-white hover:bg-primary-600'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              )}
            >
              <Plus className="w-3 h-3" />
              添加叠加层
            </button>
          </div>

          {/* 叠加层列表 */}
          {config.layers && config.layers.length > 0 ? (
            <div className="space-y-2">
              {config.layers.map((layer, index) => (
                <LayerConfigCard
                  key={layer.id}
                  layer={layer}
                  index={index}
                  compatibleTypes={compatibleTypes}
                  numericColumns={numericColumns}
                  allColumns={allColumns}
                  primaryXColumn={config.xColumn}
                  primaryYColumn={config.yColumn}
                  onUpdate={(updates) => updateLayer(layer.id, updates)}
                  onRemove={() => removeLayer(layer.id)}
                />
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-400 text-center py-2">
              点击上方按钮添加叠加层（如趋势线、柱状统计等）
            </p>
          )}
        </div>
      )}

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
        {config.layers && config.layers.length > 0
          ? `生成叠加图表 (${config.layers.length + 1} 层)`
          : '生成图表'}
      </button>
    </div>
  );
};

export default ChartConfigPanel;
