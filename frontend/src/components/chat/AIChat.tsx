import React, { useRef, useEffect } from 'react';
import {
  Send,
  Bot,
  User,
  Lightbulb,
  BarChart3,
  Calculator,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { useAIChat } from '@hooks/useAIChat';
import { useAIChatStore } from '@store/index';
import { cn } from '@utils/helpers';

interface AIChatProps {
  className?: string;
}

const suggestionChips = [
  { icon: <BarChart3 className="w-4 h-4" />, text: '帮我生成一个散点图' },
  { icon: <Calculator className="w-4 h-4" />, text: '进行 t 检验分析' },
  { icon: <Lightbulb className="w-4 h-4" />, text: '分析数据特征' },
];

export const AIChat: React.FC<AIChatProps> = ({ className }) => {
  const {
    messages,
    inputMessage,
    setInputMessage,
    isLoading,
    isStreaming,
    sendMessageStream,
  } = useAIChat();

  const { clearMessages } = useAIChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 自动聚焦输入框
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputMessage.trim() && !isLoading && !isStreaming) {
      sendMessageStream(inputMessage);
    }
  };

  const handleSuggestionClick = (text: string) => {
    if (!isLoading && !isStreaming) {
      sendMessageStream(text);
    }
  };

  return (
    <div className={cn('flex flex-col h-full bg-white rounded-xl border border-gray-200 overflow-hidden', className)}>
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-primary-50 to-white">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-primary-100 rounded-full flex items-center justify-center">
            <Bot className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">AI 数据分析助手</h3>
            <p className="text-xs text-gray-500">
              {isStreaming ? '正在思考...' : '随时为你提供帮助'}
            </p>
          </div>
        </div>
        <button
          onClick={clearMessages}
          className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
          title="清空对话"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              'flex gap-3',
              message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
            )}
          >
            {/* 头像 */}
            <div
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                message.role === 'user'
                  ? 'bg-primary-100'
                  : 'bg-gradient-to-br from-primary-400 to-primary-600'
              )}
            >
              {message.role === 'user' ? (
                <User className="w-4 h-4 text-primary-600" />
              ) : (
                <Bot className="w-4 h-4 text-white" />
              )}
            </div>

            {/* 消息内容 */}
            <div
              className={cn(
                'max-w-[80%] rounded-2xl px-4 py-3',
                message.role === 'user'
                  ? 'bg-primary-500 text-white'
                  : 'bg-gray-100 text-gray-800'
              )}
            >
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
              
              {/* 流式响应指示器 */}
              {message.isStreaming && (
                <span className="inline-flex gap-1 mt-2">
                  <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </span>
              )}

              {/* 建议按钮 */}
              {message.suggestions && message.suggestions.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {message.suggestions.map((suggestion, i) => (
                    <button
                      key={i}
                      onClick={() => handleSuggestionClick(suggestion)}
                      className="text-xs px-3 py-1.5 bg-white/20 hover:bg-white/30 rounded-full transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* 建议芯片 */}
      <div className="px-4 py-2 border-t border-gray-100">
        <div className="flex gap-2 overflow-x-auto pb-2">
          {suggestionChips.map((chip, index) => (
            <button
              key={index}
              onClick={() => handleSuggestionClick(chip.text)}
              disabled={isLoading || isStreaming}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-50 text-primary-700 text-xs font-medium rounded-full whitespace-nowrap hover:bg-primary-100 transition-colors disabled:opacity-50"
            >
              {chip.icon}
              {chip.text}
            </button>
          ))}
        </div>
      </div>

      {/* 输入框 */}
      <form onSubmit={handleSubmit} className="p-4 border-t border-gray-100">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="输入你的问题..."
            disabled={isLoading || isStreaming}
            className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-400 disabled:bg-gray-50 disabled:text-gray-400"
          />
          <button
            type="submit"
            disabled={!inputMessage.trim() || isLoading || isStreaming}
            className={cn(
              'px-4 py-2.5 rounded-xl transition-all',
              !inputMessage.trim() || isLoading || isStreaming
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-primary-500 text-white hover:bg-primary-600 shadow-lg hover:shadow-primary-500/30'
            )}
          >
            {isLoading || isStreaming ? (
              <RefreshCw className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AIChat;
