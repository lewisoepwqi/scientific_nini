import React, { useState } from 'react';
import { Download } from 'lucide-react';
import { exportApi } from '@services/exportApi';

interface ExportButtonProps {
  visualizationId: string;
  onExported?: (exportId: string) => void;
}

export const ExportButton: React.FC<ExportButtonProps> = ({ visualizationId, onExported }) => {
  const [loading, setLoading] = useState(false);

  const handleExport = async () => {
    setLoading(true);
    try {
      const response = await exportApi.createExport(visualizationId);
      if (response?.success && response.data?.id) {
        onExported?.(response.data.id);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
    >
      <Download className="w-4 h-4" />
      {loading ? '导出中' : '导出分享包'}
    </button>
  );
};
