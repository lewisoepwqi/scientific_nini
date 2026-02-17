/**
 * Agent 回合分组组件 —— 将同一 turnId 的消息分为"中间步骤"和"最终回复"。
 * 中间步骤默认折叠，最终回复正常显示。
 */
import React, { useState } from "react";
import { type Message } from "../store";
import MessageBubble from "./MessageBubble";
import { ChevronDown, ChevronRight } from "lucide-react";

interface Props {
  messages: Message[];
}

function AgentTurnGroup({ messages }: Props) {
  const [expanded, setExpanded] = useState(false);

  // 找到最终回复：最后一条 assistant 消息（非 tool 角色）
  // 以及附带的 chart/data/image 等产物消息
  const lastAssistantIdx = findLastAssistantIndex(messages);

  // 如果只有 1-2 条消息，或没有工具调用，不需要折叠
  const toolMessages = messages.filter((m) => m.role === "tool");
  if (toolMessages.length === 0 || messages.length <= 2) {
    return (
      <>
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </>
    );
  }

  // 分离中间步骤和最终回复
  // 分析思路消息（isReasoning）不折叠到中间步骤，始终显示
  const allIntermediate =
    lastAssistantIdx >= 0
      ? messages.slice(0, lastAssistantIdx)
      : messages.slice(0, -1);
  const reasoningMessages = allIntermediate.filter((m) => m.isReasoning);
  const intermediateMessages = allIntermediate.filter((m) => !m.isReasoning);
  const finalMessages =
    lastAssistantIdx >= 0
      ? messages.slice(lastAssistantIdx)
      : messages.slice(-1);

  // 提取工具调用摘要
  const toolNames = toolMessages.map((m) => m.toolName || "工具调用");
  const stepSummary = `执行了 ${toolNames.length} 个步骤：${toolNames.join(" → ")}`;

  return (
    <div>
      {/* 分析思路始终显示 */}
      {reasoningMessages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {/* 折叠的中间步骤 */}
      {intermediateMessages.length > 0 && (
        <div className="mb-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500
                       hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span>{stepSummary}</span>
          </button>

          {expanded && (
            <div className="ml-3 pl-3 border-l-2 border-gray-200 mt-1 space-y-1">
              {intermediateMessages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* 最终回复 */}
      {finalMessages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
    </div>
  );
}

function findLastAssistantIndex(messages: Message[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (
      messages[i].role === "assistant" &&
      !messages[i].toolName &&
      !messages[i].isReasoning
    ) {
      return i;
    }
  }
  return -1;
}

export default React.memo(AgentTurnGroup);
