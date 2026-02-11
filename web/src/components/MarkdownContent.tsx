/**
 * Markdown 渲染组件：支持把 .plotly.json 作为内嵌交互图显示。
 */
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import PlotlyFromUrl from './PlotlyFromUrl'

interface Props {
  content: string
  className?: string
}

function isPlotlyJsonPath(src: string): boolean {
  const clean = src.split('#')[0]?.split('?')[0]?.toLowerCase() || ''
  return clean.endsWith('.plotly.json')
}

const markdownComponents: Components = {
  img({ src, alt }) {
    if (!src) return null
    if (isPlotlyJsonPath(src)) {
      return <PlotlyFromUrl url={src} alt={alt} />
    }
    return (
      <img
        src={src}
        alt={alt || ''}
        loading="lazy"
        className="rounded-lg border border-gray-200 bg-white"
      />
    )
  },
}

export default function MarkdownContent({ content, className }: Props) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
