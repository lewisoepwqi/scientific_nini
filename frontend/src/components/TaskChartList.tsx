import React, { useEffect, useState } from 'react';
import { History, RefreshCw } from 'lucide-react';
import { cn } from '@utils/helpers';
import { visualizationApi } from '@services/visualizationApi';
import { ChartConfigActions } from './ChartConfigActions';
import type { TaskChartItem } from '@store/taskStore';

interface TaskChartListProps {
  taskId: string;
  className?: string;
  onLoaded?: (charts: TaskChartItem[]) => void;
}

export const TaskChartList: React.FC<TaskChartListProps> = ({ taskId, className, onLoaded }) => {
  const [charts, setCharts] = useState<TaskChartItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadCharts = async () => {
    setLoading(true);
    try {
      const response = await visualizationApi.listTaskVisualizations(taskId);
      if (response?.success && response.data) {
        setCharts(response.data as TaskChartItem[]);
        onLoaded?.(response.data as TaskChartItem[]);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCharts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  return (
    <div className={cn('bg-white rounded-xl border border-gray-200 p-6', className)}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          <History className="w-5 h-5" />
          图表历史
        </h3>
        <button
          onClick={loadCharts}
          className={cn(
            'px-3 py-1.5 text-sm rounded-lg border flex items-center gap-1',
            loading ? 'text-gray-400 border-gray-200' : 'text-gray-600 hover:bg-gray-50 border-gray-200'
          )}
        >
          <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
          {loading ? '加载中' : '刷新'}
        </button>
      </div>

      {charts.length === 0 ? (
        <p className="text-sm text-gray-500">暂无历史图表</p>
      ) : (
        <div className="space-y-2">
          {charts.map((chart) => (
            <div
              key={chart.id}
              className="border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between"
            >
              <div>
                <p className="text-sm font-medium text-gray-900">图表 {chart.id.slice(0, 8)}</p>
                <p className="text-xs text-gray-500">配置版本：{chart.configId || '—'}</p>
              </div>
              <ChartConfigActions configId={chart.configId} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
