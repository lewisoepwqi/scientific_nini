/**
 * Markdown 渲染组件：支持把 .plotly.json 作为内嵌交互图显示。
 */
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useMemo, type ReactNode } from 'react'
import { useStore } from '../store'
import PlotlyFromUrl from './PlotlyFromUrl'

interface Props {
  content: string
  className?: string
}

function isPlotlyJsonPath(src: string): boolean {
  const clean = src.split('#')[0]?.split('?')[0]?.toLowerCase() || ''
  return clean.endsWith('.plotly.json')
}

function normalizePathSegment(name: string): string {
  try {
    // 先解码再编码，避免对已编码名称再次编码（%E8 -> %25E8）。
    return encodeURIComponent(decodeURIComponent(name))
  } catch {
    return encodeURIComponent(name)
  }
}

function normalizeArtifactUrl(url: string): string {
  if (!url.startsWith('/api/artifacts/')) {
    return url
  }

  const trimmed = url.trim()
  const [withoutHash, hash = ''] = trimmed.split('#', 2)
  const [withoutQuery, query = ''] = withoutHash.split('?', 2)
  const match = withoutQuery.match(/^\/api\/artifacts\/([^/]+)\/(.+)$/)
  if (!match) {
    return trimmed
  }
  const [, sessionId, filename] = match
  const normalizedPath = `/api/artifacts/${sessionId}/${normalizePathSegment(filename)}`
  const queryPart = query ? `?${query}` : ''
  const hashPart = hash ? `#${hash}` : ''
  return `${normalizedPath}${queryPart}${hashPart}`
}

function normalizeMarkdownArtifactLinks(content: string): string {
  // 修复 markdown 中未编码的 /api/artifacts/ 链接（中文/空格会导致解析失败，整行按文本显示）。
  return content.replace(/(!?\[[^\]]*\])\((\/api\/artifacts\/[^)\n]+)\)/g, (_, label, rawUrl) => {
    const normalizedUrl = normalizeArtifactUrl(rawUrl)
    return `${label}(${normalizedUrl})`
  })
}

/**
 * 转换图片路径为正确的 URL。
 * - 相对路径如 ./产物/xxx.png → /api/artifacts/{sessionId}/xxx.png
 * - 绝对 URL (http/https) 保持不变
 * - 以 / 开头的路径保持不变
 */
function resolveImageUrl(src: string, sessionId: string | null): string {
  // 已经是绝对 URL，直接返回
  if (src.startsWith('http://') || src.startsWith('https://') || src.startsWith('/')) {
    return normalizeArtifactUrl(src)
  }

  // 需要 sessionId 来转换相对路径
  if (!sessionId) {
    return src
  }

  // 处理 ./产物/xxx.png 或 ./artifacts/xxx.png 格式的路径
  if (src.startsWith('./')) {
    const path = src.slice(2) // 移除 ./
    // 提取文件名（移除目录前缀）
    const filename = path.split('/').pop() || path
    return `/api/artifacts/${sessionId}/${normalizePathSegment(filename)}`
  }

  // 其他情况，直接返回原路径
  return src
}

/**
 * 创建 markdown 组件配置，接收 sessionId 用于路径转换。
 */
function createMarkdownComponents(sessionId: string | null): Components {
  return {
    img({ src, alt }) {
      if (!src) return null
      // 转换路径
      const resolvedSrc = resolveImageUrl(src, sessionId)

      if (isPlotlyJsonPath(resolvedSrc)) {
        return <PlotlyFromUrl url={resolvedSrc} alt={alt} />
      }
      return (
        <img
          src={resolvedSrc}
          alt={alt || ''}
          loading="lazy"
          className="rounded-lg border border-gray-200 bg-white"
        />
      )
    },
    /**
     * 自定义段落渲染：检查子元素是否包含 plotly 图表，
     * 如果包含则使用 div 代替 p 标签，避免 DOM 嵌套警告。
     */
    p({ children }) {
      return <ParagraphWrapper>{children}</ParagraphWrapper>
    },
  }
}

/**
 * 段落包装组件：递归检查子元素中是否包含 Plotly 图表。
 * 如果包含，则使用 div 渲染；否则使用 p 标签。
 */
function ParagraphWrapper({ children }: { children: ReactNode }) {
  const hasPlotly = useMemo(() => checkForPlotly(children), [children])

  if (hasPlotly) {
    return <div className="mb-4 last:mb-0">{children}</div>
  }
  return <p className="mb-4 last:mb-0">{children}</p>
}

/**
 * 递归检查 React 节点树中是否包含 Plotly 图表。
 * 通过检查 Context 值或组件类型来识别。
 */
function checkForPlotly(node: ReactNode): boolean {
  // 基本情况
  if (node === null || node === undefined || typeof node === 'boolean') {
    return false
  }

  // 字符串或数字不可能是 Plotly
  if (typeof node === 'string' || typeof node === 'number') {
    return false
  }

  // 数组：检查任一子元素
  if (Array.isArray(node)) {
    return node.some(checkForPlotly)
  }

  // React 元素
  if (typeof node === 'object' && 'type' in node) {
    const element = node as {
      type: unknown
      props?: { children?: ReactNode }
    }

    // 检查是否是 PlotlyFromUrl 组件
    if (element.type === PlotlyFromUrl) {
      return true
    }

    // 检查 type 是否为函数且名称匹配
    if (typeof element.type === 'function') {
      const fn = element.type as { name?: string; displayName?: string }
      if (fn.name === 'PlotlyFromUrl' || fn.displayName === 'PlotlyFromUrl') {
        return true
      }
    }

    // 递归检查子元素
    if (element.props?.children) {
      return checkForPlotly(element.props.children)
    }
  }

  return false
}

export default function MarkdownContent({ content, className }: Props) {
  const sessionId = useStore((s) => s.sessionId)
  const components = useMemo(() => createMarkdownComponents(sessionId), [sessionId])
  const normalizedContent = useMemo(() => normalizeMarkdownArtifactLinks(content), [content])

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {normalizedContent}
      </ReactMarkdown>
    </div>
  )
}
