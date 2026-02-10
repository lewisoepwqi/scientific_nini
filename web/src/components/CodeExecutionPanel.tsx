/**
 * 代码执行历史面板 —— 显示 Agent 的代码执行 Request/Response 记录。
 */
import { useEffect, useCallback } from 'react'
import { useStore, type CodeExecution } from '../store'
import { Copy, Check, AlertCircle, CheckCircle, Terminal } from 'lucide-react'
import { useState } from 'react'

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
  const isError = exec.status === 'error'

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
        <span className="text-gray-500 font-mono">{exec.language || 'python'}</span>
        <span className="text-gray-400 ml-auto">{formatTime(exec.created_at)}</span>
      </button>

      {/* 展开的内容 */}
      {expanded && (
        <div className="border-t">
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
