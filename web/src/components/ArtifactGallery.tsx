/**
 * 产物画廊组件 —— 网格缩略图视图，支持类型筛选、批量选择和下载。
 */
import { useState, useMemo, useCallback } from 'react'
import { useStore, type WorkspaceFile } from '../store'
import {
 Image,
 FileText,
 FileCode,
 File,
 Download,
 Check,
 Filter,
 Eye,
 EyeOff,
} from 'lucide-react'
import { apiFetch } from '../store/auth'
import Button from './ui/Button'

type FilterType = 'all' | 'chart' | 'report' | 'data' | 'script' | 'transform'

function getFilterLabel(type: FilterType): string {
 switch (type) {
 case 'all': return '全部'
 case 'chart': return '图表'
 case 'report': return '报告'
 case 'data': return '数据'
 case 'script': return '脚本'
 case 'transform': return '转换'
 }
}

function isImageFile(name: string): boolean {
 const ext = name.split('.').pop()?.toLowerCase() || ''
 return ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)
}

function isChartFile(file: WorkspaceFile): boolean {
 const name = file.name.toLowerCase()
 const ext = name.split('.').pop() || ''
 const metaType = String(file.meta?.type || '').toLowerCase()
 return (
 file.kind === 'result' && (
 ['html', 'htm', 'png', 'jpg', 'jpeg', 'svg', 'webp'].includes(ext) ||
 name.endsWith('.plotly.json') ||
 (ext === 'json' && metaType === 'chart')
 )
 )
}

function isReportFile(file: WorkspaceFile): boolean {
 const ext = file.name.split('.').pop()?.toLowerCase() || ''
 const metaType = String(file.meta?.type || '').toLowerCase()
 const projectArtifact = getProjectArtifactMeta(file)
 const artifactType = String(projectArtifact?.artifact_type || '').toLowerCase()
 return ['md', 'txt', 'pdf', 'docx', 'pptx', 'tex'].includes(ext)
 || metaType === 'report'
 || artifactType === 'report'
}

function isDataFile(file: WorkspaceFile): boolean {
 const name = file.name.toLowerCase()
 const ext = name.split('.').pop()?.toLowerCase() || ''
 const metaType = String(file.meta?.type || '').toLowerCase()
 // 脚本和转换记录不算数据文件
 if (file.resource_type === 'script' || file.resource_type === 'transform') {
 return false
 }
 if (name.endsWith('.plotly.json') || (ext === 'json' && metaType === 'chart')) {
 return false
 }
 return ['csv', 'xlsx', 'xls', 'tsv', 'json'].includes(ext)
}

function isScriptFile(file: WorkspaceFile): boolean {
 // 通过 resource_type 或文件扩展名判断
 if (file.resource_type === 'script') return true
 const ext = file.name.split('.').pop()?.toLowerCase() || ''
 return ['py', 'r', 'R'].includes(ext)
}

function isTransformFile(file: WorkspaceFile): boolean {
 // 数据转换记录
 if (file.resource_type === 'transform') return true
 // 也可以通过 meta 中的 transform_id 判断
 return !!file.meta?.transform_id
}

function getProjectArtifactMeta(file: WorkspaceFile): Record<string, unknown> | null {
 const raw = file.meta?.project_artifact
 return raw && typeof raw === 'object' ? raw as Record<string, unknown> : null
}

function ThumbnailIcon({ file }: { file: WorkspaceFile }) {
 const name = file.name.toLowerCase()

 if (isImageFile(name)) {
 // 直接使用文件 URL 作为缩略图
 return (
 <img
 src={file.download_url}
 alt={file.name}
 className="w-full h-full object-cover"
 loading="lazy"
 />
 )
 }

 // 非图片文件用图标
 const ext = name.split('.').pop() || ''
 // 脚本文件
 if (file.resource_type === 'script' || ['py', 'r', 'R'].includes(ext)) {
 return <FileCode size={28} className="text-[var(--domain-analysis)]" />
 }
 // 数据转换记录
 if (file.resource_type === 'transform') {
 return <FileCode size={28} className="text-cyan-400" />
 }
 if (name.endsWith('.plotly.json')) {
 return <FileCode size={28} className="text-orange-400" />
 }
 if (['html', 'htm'].includes(ext)) {
 return <FileCode size={28} className="text-orange-400" />
 }
 if (['md', 'txt', 'pdf', 'docx', 'pptx', 'tex'].includes(ext)) {
 return <FileText size={28} className="text-[var(--accent)]" />
 }
 if (['csv', 'xlsx', 'xls', 'tsv', 'json'].includes(ext)) {
 return <FileText size={28} className="text-[var(--success)]" />
 }
 return <File size={28} className="text-[var(--text-muted)]" />
}

export default function ArtifactGallery() {
 const sessionId = useStore((s) => s.sessionId)
 const workspaceFiles = useStore((s) => s.workspaceFiles)
 const openPreview = useStore((s) => s.openPreview)
 const [filter, setFilter] = useState<FilterType>('all')
 const [showInternal, setShowInternal] = useState(false)
 const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
 const [downloading, setDownloading] = useState(false)
 const [downloadError, setDownloadError] = useState<string | null>(null)

 // 只显示结果文件（默认隐藏内部结果）
 const artifacts = useMemo(() => {
 return workspaceFiles.filter((f) => {
 if (f.kind !== 'result') return false
 if (!showInternal && f.meta?.visibility === 'internal') return false
 return true
 })
 }, [workspaceFiles, showInternal])

 // 按类型过滤
 const filteredArtifacts = useMemo(() => {
 switch (filter) {
 case 'chart': return artifacts.filter(isChartFile)
 case 'report': return artifacts.filter(isReportFile)
 case 'data': return artifacts.filter(isDataFile)
 case 'script': return artifacts.filter(isScriptFile)
 case 'transform': return artifacts.filter(isTransformFile)
 default: return artifacts
 }
 }, [artifacts, filter])

 const toggleSelect = useCallback((id: string) => {
 setSelectedIds((prev) => {
 const next = new Set(prev)
 if (next.has(id)) next.delete(id)
 else next.add(id)
 return next
 })
 }, [])

 const handleBatchDownload = useCallback(async () => {
 if (selectedIds.size === 0 || !sessionId) return
 const selectedFiles = filteredArtifacts.filter((file) => selectedIds.has(file.id))
 const projectArtifactIds = selectedFiles
 .map((file) => {
 const meta = getProjectArtifactMeta(file)
 return typeof meta?.id === 'string' ? meta.id : null
 })
 .filter((id): id is string => Boolean(id))
 const selectedPaths = selectedFiles
 .map((file) => file.path)
 .filter((path): path is string => Boolean(path))
 if (selectedPaths.length === 0 && projectArtifactIds.length === 0) return
 setDownloadError(null)
 setDownloading(true)
 try {
 const useProjectArtifacts = projectArtifactIds.length === selectedFiles.length
 const resp = await apiFetch(
 useProjectArtifacts
 ? `/api/workspace/${sessionId}/project-artifacts/download-zip`
 : `/api/workspace/${sessionId}/download-zip`,
 {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify(useProjectArtifacts ? projectArtifactIds : selectedPaths),
 },
 )
 if (!resp.ok) {
 throw new Error(`HTTP ${resp.status}`)
 }
 const blob = await resp.blob()
 const contentDisposition = resp.headers.get('Content-Disposition') || ''
 const filenameMatch = contentDisposition.match(/filename="(.+?)"/i)
 const filename = filenameMatch?.[1] || `workspace_${sessionId.slice(0, 8)}.zip`
 const url = URL.createObjectURL(blob)
 const a = document.createElement('a')
 a.href = url
 a.download = filename
 a.click()
 URL.revokeObjectURL(url)
 setSelectedIds(new Set())
 } catch (e) {
 console.error('批量下载失败:', e)
 setDownloadError('打包下载失败，请稍后重试')
 } finally {
 setDownloading(false)
 }
 }, [filteredArtifacts, selectedIds, sessionId])

 if (artifacts.length === 0) {
 return (
 <div className="flex flex-col items-center justify-center py-12 text-[var(--text-muted)] text-xs">
 <Image size={24} className="mb-2 opacity-50" />
 <p>暂无结果</p>
 </div>
 )
 }

 return (
 <div className="flex flex-col h-full">
 {/* 筛选栏 */}
 <div className="flex items-center gap-1.5 px-2 py-2 flex-shrink-0">
 <Filter size={12} className="text-[var(--text-muted)] flex-shrink-0" />
 {(['all', 'chart', 'report', 'data', 'script', 'transform'] as FilterType[]).map((type) => (
 <Button
 key={type}
 variant="ghost"
 type="button"
 onClick={() => setFilter(type)}
 className={`px-2 py-1.5 rounded-full text-[10px] font-medium ${
 filter === type
 ? 'bg-[var(--accent-subtle)] text-[var(--accent)]'
 : ''
 }`}
 >
 {getFilterLabel(type)}
 </Button>
 ))}
 <Button
 variant="ghost"
 type="button"
 onClick={() => setShowInternal(!showInternal)}
 className={`ml-auto p-2 rounded ${
 showInternal ? 'text-[var(--accent)] bg-[var(--accent-subtle)]' : ''
 }`}
 title={showInternal ? '隐藏内部产物' : '显示内部产物'}
 aria-label={showInternal ? '隐藏内部产物' : '显示内部产物'}
 >
 {showInternal ? <Eye size={12} /> : <EyeOff size={12} />}
 </Button>
 </div>

 {/* 网格 */}
 <div className="flex-1 overflow-y-auto px-2 pb-2">
 <ul className="grid grid-cols-2 gap-2 list-none p-0 m-0">
 {filteredArtifacts.map((file) => {
 const isSelected = selectedIds.has(file.id)
 return (
 <li
 key={file.id}
 className={`relative rounded-lg border overflow-hidden cursor-pointer transition-all ${
 isSelected ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]' : 'border-[var(--border-default)] hover:border-[var(--border-default)]'
 }`}
 >
 {/* 选择复选框 */}
 <Button
 variant="ghost"
 type="button"
 onClick={(e) => {
 e.stopPropagation()
 toggleSelect(file.id)
 }}
 className={`absolute top-1.5 left-1.5 z-10 w-5 h-5 rounded border flex items-center justify-center ${
 isSelected
 ? 'bg-[var(--accent)] border-[var(--accent)] text-white'
 : 'bg-[var(--bg-base)]/80 border-[var(--border-strong)]'
 }`}
 aria-label="选择文件"
 >
 {isSelected && <Check size={10} />}
 </Button>

 {/* 缩略图：使用 <button> 确保键盘可访问 (WCAG 2.1.1) */}
 <Button
 variant="ghost"
 type="button"
 className="aspect-square bg-[var(--bg-elevated)] flex items-center justify-center overflow-hidden w-full p-0 focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-1"
 onClick={() => openPreview(file.id)}
 aria-label={`预览 ${file.name}`}
 >
 <ThumbnailIcon file={file} />
 </Button>

 {/* 文件名 */}
 <div className="px-1.5 py-1 border-t border-[var(--border-default)] bg-[var(--bg-base)]">
 <div className="text-[10px] text-[var(--text-secondary)] truncate" title={file.name}>
 {file.name}
 </div>
 {(() => {
 const meta = getProjectArtifactMeta(file)
 const version = typeof meta?.version === 'number' ? meta.version : null
 const format = typeof meta?.format === 'string' ? meta.format : null
 if (version === null && !format) return null
 return (
 <div className="mt-0.5 flex items-center gap-1 text-[9px] text-[var(--text-muted)]">
 {version !== null && <span>v{version}</span>}
 {format && <span className="uppercase">{format}</span>}
 </div>
 )
 })()}
 </div>
 </li>
 )
 })}
 </ul>
 </div>

 {/* 批量操作栏 */}
 {selectedIds.size > 0 && (
 <div className="px-2 py-2 border-t border-[var(--border-default)] bg-[var(--accent-subtle)] flex-shrink-0">
 <div className="flex items-center justify-between">
 <span className="text-xs text-[var(--accent)]">
 已选 {selectedIds.size} 个
 </span>
 <Button
 variant="primary"
 type="button"
 onClick={handleBatchDownload}
 disabled={downloading}
 className="flex items-center gap-1 px-3 py-1 rounded-md text-xs"
 icon={<Download size={12} />}
 >
 {downloading ? '打包中...' : '批量下载'}
 </Button>
 </div>
 {downloadError && (
 <p className="text-[10px] text-[var(--error)] mt-1">{downloadError}</p>
 )}
 </div>
 )}
 </div>
 )
}
