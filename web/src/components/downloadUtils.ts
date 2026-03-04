/**
 * 下载地址工具：Markdown 文件优先走 bundle 接口，保证图文资源完整。
 */

function isMarkdownFile(name: string | undefined): boolean {
  if (!name) return false
  const lower = name.toLowerCase()
  return lower.endsWith('.md') || lower.endsWith('.markdown')
}

export function resolveDownloadUrl(downloadUrl: string | undefined, name?: string): string | undefined {
  if (!downloadUrl) return downloadUrl
  if (!isMarkdownFile(name)) return downloadUrl

  // 兼容旧 artifact 下载地址。
  const artifactMatch = downloadUrl.match(/^\/api\/artifacts\/([^/]+)\/(.+)$/)
  if (artifactMatch) {
    const sessionId = artifactMatch[1]
    const filename = artifactMatch[2]
    return `/api/workspace/${sessionId}/artifacts/${filename}/bundle`
  }

  const workspaceArtifactMatch = downloadUrl.match(/^\/api\/workspace\/([^/]+)\/artifacts\/(.+)$/)
  if (workspaceArtifactMatch) {
    const sessionId = workspaceArtifactMatch[1]
    const filename = workspaceArtifactMatch[2]
    return `/api/workspace/${sessionId}/artifacts/${filename}/bundle`
  }

  const workspaceFilesMatch = downloadUrl.match(/^\/api\/workspace\/([^/]+)\/files\/(.+)$/)
  if (workspaceFilesMatch) {
    const sessionId = workspaceFilesMatch[1]
    const path = workspaceFilesMatch[2]
    return `/api/workspace/${sessionId}/files/${path}?bundle=1`
  }

  const noteMatch = downloadUrl.match(/^\/api\/workspace\/([^/]+)\/notes\/(.+)$/)
  if (noteMatch) {
    const sessionId = noteMatch[1]
    const filename = noteMatch[2]
    return `/api/workspace/${sessionId}/files/notes/${filename}?bundle=1`
  }

  return downloadUrl
}
