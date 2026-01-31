import React, { useState } from 'react';
import { Copy } from 'lucide-react';
import { visualizationApi } from '@services/visualizationApi';

interface ChartConfigActionsProps {
  configId?: string | null;
  onCloned?: (newConfigId: string) => void;
}

export const ChartConfigActions: React.FC<ChartConfigActionsProps> = ({ configId, onCloned }) => {
  const [loading, setLoading] = useState(false);

  if (!configId) {
    return null;
  }

  const handleClone = async () => {
    setLoading(true);
    try {
      const response = await visualizationApi.cloneChartConfig(configId);
      if (response?.success && response.data?.id) {
        onCloned?.(response.data.id);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleClone}
      disabled={loading}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
    >
      <Copy className="w-4 h-4" />
      {loading ? '复制中' : '复制配置'}
    </button>
  );
};
