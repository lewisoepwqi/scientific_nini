import React, { useState } from 'react';
import { Bot, CheckCircle2, XCircle } from 'lucide-react';
import { suggestionApi } from '@services/suggestionApi';
import { cn } from '@utils/helpers';
import type { SuggestionItem } from '../types/task';

interface SuggestionPanelProps {
  taskId: string;
  onStatusChange?: (status: 'accepted' | 'rejected') => void;
}

export const SuggestionPanel: React.FC<SuggestionPanelProps> = ({ taskId, onStatusChange }) => {
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState<SuggestionItem | null>(null);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const response = await suggestionApi.createSuggestion(taskId);
      if (response?.success && response.data) {
        setSuggestion(response.data);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async () => {
    setLoading(true);
    try {
      await suggestionApi.acceptSuggestion(taskId);
      onStatusChange?.('accepted');
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await suggestionApi.rejectSuggestion(taskId);
      onStatusChange?.('rejected');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          <Bot className="w-5 h-5" />
          AI 建议
        </h3>
        <button
          onClick={handleGenerate}
          className={cn(
            'px-3 py-1.5 text-sm rounded-lg border',
            loading ? 'text-gray-400 border-gray-200' : 'text-gray-600 hover:bg-gray-50 border-gray-200'
          )}
        >
          {loading ? '生成中...' : '生成建议'}
        </button>
      </div>

      {!suggestion ? (
        <p className="text-sm text-gray-500">暂无建议，请点击生成。</p>
      ) : (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">清洗建议</p>
            <ul className="text-sm text-gray-600 list-disc list-inside">
              {suggestion.cleaning.map((item, index) => (
                <li key={`clean-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">统计方法</p>
            <ul className="text-sm text-gray-600 list-disc list-inside">
              {suggestion.statistics.map((item, index) => (
                <li key={`stat-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">图表推荐</p>
            <ul className="text-sm text-gray-600 list-disc list-inside">
              {suggestion.chartRecommendations.map((item, index) => (
                <li key={`chart-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1">注意事项</p>
            <ul className="text-sm text-gray-600 list-disc list-inside">
              {suggestion.notes.map((item, index) => (
                <li key={`note-${index}`}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleAccept}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-green-700 bg-green-50 rounded-lg hover:bg-green-100 disabled:opacity-50"
            >
              <CheckCircle2 className="w-4 h-4" />
              采纳
            </button>
            <button
              onClick={handleReject}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-700 bg-red-50 rounded-lg hover:bg-red-100 disabled:opacity-50"
            >
              <XCircle className="w-4 h-4" />
              不采纳
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
