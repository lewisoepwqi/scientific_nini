import { useState, useCallback } from 'react';
import { api } from '@services/api';
import { useAIChatStore, useDatasetStore, useChartStore, useAnalysisStore } from '@store/index';
import { generateId } from '@utils/helpers';
import type { AIMessage } from '../types';

export function useAIChat() {
  const { messages, addMessage, updateMessage, setIsStreaming, setSuggestions } = useAIChatStore();
  const { currentDataset } = useDatasetStore();
  const { config: chartConfig } = useChartStore();
  const { results: analysisResults } = useAnalysisStore();

  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  /**
   * 发送消息（非流式）
   */
  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      setIsLoading(true);

      // 添加用户消息
      const userMessage: AIMessage = {
        id: generateId(),
        role: 'user',
        content: content.trim(),
        timestamp: new Date(),
      };
      addMessage(userMessage);
      setInputMessage('');

      try {
        const response = await api.ai.sendMessage(content, {
          datasetId: currentDataset?.id,
          chartConfig,
          analysisResults,
        });

        if (response.success && response.data) {
          const assistantMessage: AIMessage = {
            id: generateId(),
            role: 'assistant',
            content: response.data.response,
            timestamp: new Date(),
            suggestions: response.data.suggestions?.map((s) => s.title),
          };
          addMessage(assistantMessage);

          if (response.data.suggestions) {
            setSuggestions(response.data.suggestions);
          }
        } else {
          throw new Error(response.error?.message || '发送消息失败');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '发送消息失败';
        const errorAssistantMessage: AIMessage = {
          id: generateId(),
          role: 'assistant',
          content: `抱歉，我遇到了一些问题：${errorMessage}`,
          timestamp: new Date(),
        };
        addMessage(errorAssistantMessage);
      } finally {
        setIsLoading(false);
      }
    },
    [currentDataset, chartConfig, analysisResults, addMessage, setSuggestions]
  );

  /**
   * 发送消息（流式）
   */
  const sendMessageStream = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      setIsStreaming(true);
      setIsLoading(true);

      // 添加用户消息
      const userMessage: AIMessage = {
        id: generateId(),
        role: 'user',
        content: content.trim(),
        timestamp: new Date(),
      };
      addMessage(userMessage);
      setInputMessage('');

      // 创建助手消息（初始为空）
      const assistantMessageId = generateId();
      const assistantMessage: AIMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
      };
      addMessage(assistantMessage);

      try {
        let fullContent = '';
        await api.ai.sendMessageStream(
          content,
          (chunk) => {
            fullContent += chunk;
            updateMessage(assistantMessageId, {
              content: fullContent,
            });
          },
          {
            datasetId: currentDataset?.id,
            chartConfig,
            analysisResults,
          }
        );

        // 标记流式响应完成
        updateMessage(assistantMessageId, {
          isStreaming: false,
        });
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '发送消息失败';
        updateMessage(assistantMessageId, {
          content: `抱歉，我遇到了一些问题：${errorMessage}`,
          isStreaming: false,
        });
      } finally {
        setIsStreaming(false);
        setIsLoading(false);
      }
    },
    [currentDataset, chartConfig, analysisResults, addMessage, updateMessage, setIsStreaming]
  );

  /**
   * 获取分析建议
   */
  const getSuggestions = useCallback(async () => {
    if (!currentDataset) return;

    try {
      const response = await api.ai.getSuggestions(currentDataset.id);
      if (response.success && response.data) {
        setSuggestions(response.data);
      }
    } catch (error) {
      console.error('获取建议失败:', error);
    }
  }, [currentDataset, setSuggestions]);

  /**
   * 请求图表建议
   */
  const suggestChart = useCallback(
    async (goal?: string) => {
      if (!currentDataset) return;

      setIsLoading(true);
      try {
        const response = await api.ai.suggestChart(currentDataset.id, goal);
        if (response.success && response.data) {
          return response.data;
        }
      } catch (error) {
        console.error('获取图表建议失败:', error);
      } finally {
        setIsLoading(false);
      }
      return null;
    },
    [currentDataset]
  );

  return {
    messages,
    inputMessage,
    setInputMessage,
    isLoading,
    isStreaming: useAIChatStore.getState().isStreaming,
    sendMessage,
    sendMessageStream,
    getSuggestions,
    suggestChart,
  };
}
