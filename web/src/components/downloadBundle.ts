/**
 * 代码档案 bundle 下载工具：通过浏览器触发 zip 下载。
 */
import { downloadFileFromUrl } from './downloadUtils'

export function downloadSingleBundle(sessionId: string, executionId: string): Promise<void> {
  const url = `/api/workspace/${sessionId}/executions/${executionId}/bundle`
  return downloadFileFromUrl(url, `execution-${executionId.slice(0, 8)}.zip`)
}

export function downloadBatchBundle(sessionId: string): Promise<void> {
  const url = `/api/workspace/${sessionId}/executions/bundle`
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  return downloadFileFromUrl(url, `code-archive-${sessionId.slice(0, 8)}-${date}.zip`)
}
