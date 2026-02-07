/**
 * 文件下载组件 —— 渲染 agent 产出的可下载产物。
 */
import { type ArtifactInfo } from '../store'
import { Download, FileImage, FileText, FileCode, File } from 'lucide-react'

interface Props {
  artifacts: ArtifactInfo[]
}

function getIcon(artifact: ArtifactInfo) {
  const fmt = artifact.format || artifact.type || ''
  if (['png', 'jpeg', 'jpg', 'svg'].includes(fmt)) return <FileImage size={14} />
  if (['html', 'json'].includes(fmt)) return <FileCode size={14} />
  if (['md', 'txt', 'report'].includes(fmt) || artifact.type === 'report') return <FileText size={14} />
  return <File size={14} />
}

export default function ArtifactDownload({ artifacts }: Props) {
  if (!artifacts || artifacts.length === 0) return null

  return (
    <div className="mt-2 space-y-1.5">
      {artifacts.map((artifact, idx) => (
        <a
          key={`${artifact.name}-${idx}`}
          href={artifact.download_url}
          download={artifact.name}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200
                     bg-white hover:bg-blue-50 hover:border-blue-300 text-sm text-gray-700
                     transition-colors cursor-pointer mr-2"
        >
          {getIcon(artifact)}
          <span className="truncate max-w-[200px]">{artifact.name}</span>
          <Download size={12} className="text-gray-400 flex-shrink-0" />
        </a>
      ))}
    </div>
  )
}
