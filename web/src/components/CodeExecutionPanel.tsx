/**
 * 代码执行历史面板 —— 显示 Agent 的代码执行 Request/Response 记录。
 */
import { useEffect, useCallback } from 'react'
import { useStore, type CodeExecution } from '../store'
import { Copy, Check, AlertCircle, CheckCircle, Terminal, RotateCcw, FileCode } from 'lucide-react'
import { useState } from 'react'

/**
 * 基础工具名称映射（新工具系统）
 * 将内部工具名映射为用户可读的显示名称
 */
const TOOL_NAME_DISPLAY: Record<string, string> = {
  // 新基础工具层
  'task_state': '任务状态',
  'dataset_catalog': '数据目录',
  'dataset_transform': '数据转换',
  'stat_test': '统计检验',
  'stat_model': '统计建模',
  'stat_interpret': '统计解读',
  'chart_session': '图表会话',
  'report_session': '报告会话',
  'workspace_session': '工作区会话',
  'code_session': '代码会话',
  // 旧工具名（向后兼容显示）
  'run_code': '代码执行',
  'run_r_code': 'R代码执行',
  'create_chart': '创建图表',
  'generate_report': '生成报告',
  'export_report': '导出报告',
}

function getToolDisplayName(toolName: string | undefined): string {
  if (!toolName) return '代码执行'
  return TOOL_NAME_DISPLAY[toolName] || toolName
}

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return isoStr
  }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // 回退方案
    }
  }, [text])

  return (
    <button
      onClick={handleCopy}
      className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
      title="复制代码"
    >
      {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
    </button>
  )
}

function ExecutionItem({ exec }: { exec: CodeExecution }) {
  const [expanded, setExpanded] = useState(true)
  const [argsExpanded, setArgsExpanded] = useState(false)
  const isError = exec.status === 'error'
  const isRetry = !!exec.retry_of_execution_id

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* 头部 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center gap-2 px-3 py-2 text-xs ${
          isError ? 'bg-red-50' : 'bg-gray-50'
        } hover:bg-gray-100 transition-colors`}
      >
        {isError ? (
          <AlertCircle size={12} className="text-red-500 flex-shrink-0" />
        ) : (
          <CheckCircle size={12} className="text-emerald-500 flex-shrink-0" />
        )}
        {/* 显示工具图标和名称 */}
        {exec.tool_name === 'code_session' ? (
          <FileCode size={12} className="text-purple-500 flex-shrink-0" />
        ) : null}
        <span className="text-gray-600 font-medium">{getToolDisplayName(exec.tool_name)}</span>
        {exec.language && (
          <span className="text-gray-400 font-mono text-[10px]">({exec.language})</span>
        )}
        {isRetry && (
          <span title="重试执行"><RotateCcw size={10} className="text-blue-400 flex-shrink-0" /></span>
        )}
        {exec.context_token_count != null && (
          <span className="text-[10px] text-gray-400" title="执行时上下文 Token 数">
            {exec.context_token_count.toLocaleString()} tok
          </span>
        )}
        <span className="text-gray-400 ml-auto">{formatTime(exec.created_at)}</span>
      </button>

      {/* 展开的内容 */}
      {expanded && (
        <div className="border-t">
          {/* 工具参数（折叠展示） */}
          {exec.tool_args && Object.keys(exec.tool_args).length > 0 && (
            <div className="border-b">
              <button
                onClick={() => setArgsExpanded(!argsExpanded)}
                className="w-full flex items-center gap-1 px-3 py-1 bg-gray-50 text-[10px] text-gray-400 font-medium hover:bg-gray-100 transition-colors"
              >
                <span>{argsExpanded ? '▼' : '▶'}</span>
                <span>TOOL ARGS</span>
              </button>
              {argsExpanded && (
                <pre className="text-[11px] font-mono px-3 py-2 overflow-x-auto bg-gray-50 text-gray-600 max-h-32 overflow-y-auto">
                  {JSON.stringify(exec.tool_args, null, 2)}
                </pre>
              )}
            </div>
          )}

          {/* 脚本资源关联信息 */}
          {exec.script_resource_id && (
            <div className="px-3 py-1.5 border-b bg-purple-50/60 text-[10px] text-purple-700 flex items-center gap-2">
              <span className="font-medium">脚本资源：</span>
              <code className="bg-purple-100 px-1.5 py-0.5 rounded">{exec.script_resource_id}</code>
            </div>
          )}

          {/* 输出资源关联信息 */}
          {exec.output_resource_ids && exec.output_resource_ids.length > 0 && (
            <div className="px-3 py-1.5 border-b bg-emerald-50/60 text-[10px] text-emerald-700 flex items-center gap-2">
              <span className="font-medium">输出资源：</span>
              <div className="flex gap-1 flex-wrap">
                {exec.output_resource_ids.map((id) => (
                  <code key={id} className="bg-emerald-100 px-1.5 py-0.5 rounded">{id}</code>
                ))}
              </div>
            </div>
          )}

          {/* 重试关联信息 */}
          {isRetry && exec.retry_of_execution_id && (
            <div className="px-3 py-1.5 border-b bg-blue-50/60 text-[10px] text-blue-700 flex items-center gap-2">
              <RotateCcw size={10} />
              <span>重试于执行记录：</span>
              <code className="bg-blue-100 px-1.5 py-0.5 rounded">{exec.retry_of_execution_id.slice(0, 8)}...</code>
            </div>
          )}

          {/* 错误定位信息 */}
          {isError && exec.error_location && (
            <div className="px-3 py-1.5 border-b bg-red-50 text-[10px] text-red-700">
              <span className="font-medium">错误位置：</span>
              <span>第 {exec.error_location.line} 行</span>
              {exec.error_location.column && (
                <span>，第 {exec.error_location.column} 列</span>
              )}
            </div>
          )}

          {/* 恢复提示 */}
          {isError && exec.recovery_hint && (
            <div className="px-3 py-1.5 border-b bg-yellow-50 text-[10px] text-yellow-800">
              <span className="font-medium">恢复建议：</span>
              <span>{exec.recovery_hint}</span>
            </div>
          )}

          {exec.intent && (
            <div className="px-3 py-2 border-b bg-blue-50/60 text-[11px] text-blue-700">
              <span className="font-medium">执行意图：</span>
              <span>{exec.intent}</span>
            </div>
          )}

          {/* Request（代码） */}
          {exec.code && (
            <div className="relative">
              <div className="flex items-center justify-between px-3 py-1 bg-gray-50 border-b">
                <span className="text-[10px] text-gray-400 font-medium">REQUEST</span>
                <CopyButton text={exec.code} />
              </div>
              <pre className="text-xs font-mono px-3 py-2 overflow-x-auto bg-gray-900 text-gray-100 max-h-40 overflow-y-auto">
                {exec.code}
              </pre>
            </div>
          )}

          {/* Response（输出） */}
          {exec.output && (
            <div className="relative border-t">
              <div className="flex items-center justify-between px-3 py-1 bg-gray-50 border-b">
                <span className={`text-[10px] font-medium ${isError ? 'text-red-500' : 'text-gray-400'}`}>
                  RESPONSE
                </span>
              </div>
              <pre
                className={`text-xs font-mono px-3 py-2 overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap break-words ${
                  isError ? 'bg-red-50 text-red-700' : 'bg-white text-gray-700'
                }`}
              >
                {exec.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function CodeExecutionPanel() {
  const sessionId = useStore((s) => s.sessionId)
  const codeExecutions = useStore((s) => s.codeExecutions)
  const fetchCodeExecutions = useStore((s) => s.fetchCodeExecutions)

  useEffect(() => {
    if (sessionId) {
      fetchCodeExecutions()
    }
  }, [sessionId, fetchCodeExecutions])

  if (codeExecutions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 text-xs px-4">
        <Terminal size={24} className="mb-2 opacity-50" />
        <p>暂无执行历史</p>
        <p className="text-[10px] mt-1">代码执行记录将显示在此处</p>
      </div>
    )
  }

  return (
    <div className="p-2 space-y-2">
      {codeExecutions.map((exec) => (
        <ExecutionItem key={exec.id} exec={exec} />
      ))}
    </div>
  )
}
