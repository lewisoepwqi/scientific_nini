/**
 * 下载地址工具：Markdown 文件优先走 bundle 接口，保证图文资源完整。
 */
import { appendApiToken, apiFetch } from '../store/auth'

function appendQueryParam(url: string, key: string, value: string): string {
  const hashIndex = url.indexOf('#')
  const hash = hashIndex >= 0 ? url.slice(hashIndex) : ''
  const base = hashIndex >= 0 ? url.slice(0, hashIndex) : url
  if (new RegExp(`(?:\\?|&)${key}=`).test(base)) {
    return url
  }
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}${key}=${encodeURIComponent(value)}${hash}`
}

function inferFilenameFromUrl(url: string): string | undefined {
  const [base] = url.split('?', 1)
  const lastSegment = base.split('/').filter(Boolean).pop()
  if (!lastSegment) return undefined
  try {
    return decodeURIComponent(lastSegment)
  } catch {
    return lastSegment
  }
}

function parseFilenameFromDisposition(contentDisposition: string): string | undefined {
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = contentDisposition.match(/filename="?([^"]+)"?/i)
  return plainMatch?.[1]
}

function isMarkdownFile(name: string | undefined): boolean {
  if (!name) return false
  const lower = name.toLowerCase()
  return lower.endsWith('.md') || lower.endsWith('.markdown')
}

export function resolveDownloadUrl(downloadUrl: string | undefined, name?: string): string | undefined {
  if (!downloadUrl) return downloadUrl

  const withToken = (url: string): string => appendApiToken(url) || url

  // 兼容旧 artifact 下载地址 → 迁移到新 /api/workspace/{sid}/files/ 格式
  const artifactMatch = downloadUrl.match(/^\/api\/artifacts\/([^/]+)\/(.+)$/)
  if (artifactMatch) {
    const sessionId = artifactMatch[1]
    const filename = artifactMatch[2]
    if (isMarkdownFile(name)) {
      return withToken(`/api/workspace/${sessionId}/files/${filename}?bundle=1`)
    }
    return withToken(`/api/workspace/${sessionId}/files/${filename}?download=1`)
  }

  const workspaceArtifactMatch = downloadUrl.match(/^\/api\/workspace\/([^/]+)\/artifacts\/(.+)$/)
  if (workspaceArtifactMatch) {
    const sessionId = workspaceArtifactMatch[1]
    const filename = workspaceArtifactMatch[2]
    if (isMarkdownFile(name)) {
      return withToken(`/api/workspace/${sessionId}/files/artifacts/${filename}?bundle=1`)
    }
    return withToken(`/api/workspace/${sessionId}/files/artifacts/${filename}?download=1`)
  }

  const workspaceFilesMatch = downloadUrl.match(/^\/api\/workspace\/([^/]+)\/files\/(.+)$/)
  if (workspaceFilesMatch) {
    const sessionId = workspaceFilesMatch[1]
    const path = workspaceFilesMatch[2]
    if (isMarkdownFile(name)) {
      return withToken(`/api/workspace/${sessionId}/files/${path}?bundle=1`)
    }
    return withToken(`/api/workspace/${sessionId}/files/${path}?download=1`)
  }

  // 兼容旧 notes 下载地址 → 迁移到新格式
  const noteMatch = downloadUrl.match(/^\/api\/workspace\/([^/]+)\/notes\/(.+)$/)
  if (noteMatch) {
    const sessionId = noteMatch[1]
    const filename = noteMatch[2]
    if (isMarkdownFile(name)) {
      return withToken(`/api/workspace/${sessionId}/files/notes/${filename}?bundle=1`)
    }
    return withToken(`/api/workspace/${sessionId}/files/notes/${filename}?download=1`)
  }

  if (isMarkdownFile(name)) return withToken(downloadUrl)
  return withToken(appendQueryParam(downloadUrl, 'download', '1'))
}

export async function downloadFileFromUrl(
  downloadUrl: string | undefined,
  fallbackName?: string,
): Promise<void> {
  if (!downloadUrl) {
    throw new Error('下载地址不可用')
  }
  const response = await apiFetch(downloadUrl)
  if (!response.ok) {
    throw new Error(`下载失败（HTTP ${response.status}）`)
  }
  const blob = await response.blob()
  const contentDisposition = response.headers.get('Content-Disposition') || ''
  const filename =
    parseFilenameFromDisposition(contentDisposition) ||
    fallbackName ||
    inferFilenameFromUrl(downloadUrl) ||
    'download'

  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}
