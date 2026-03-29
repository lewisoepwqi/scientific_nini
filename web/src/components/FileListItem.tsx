/**
 * 文件列表项组件：图标 + 名称 + 大小 + 操作按钮（下载/重命名/删除）。
 */
import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useStore, type WorkspaceFile } from '../store'
import { useConfirm } from '../store/confirm-store'
import { downloadFileFromUrl, resolveDownloadUrl } from './downloadUtils'
import {
 FileSpreadsheet,
 FileImage,
 FileText,
 FileCode,
 File,
 Download,
 Trash2,
 Pencil,
 Check,
 X,
} from 'lucide-react'
import Button from './ui/Button'

function formatSize(size: number): string {
 if (size < 1024) return `${size} B`
 if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
 return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function getFileIcon(file: WorkspaceFile) {
 const name = file.name.toLowerCase()
 const ext = name.split('.').pop() || ''

 if (['csv', 'xlsx', 'xls', 'tsv'].includes(ext)) {
 return <FileSpreadsheet size={14} className="text-[var(--success)] flex-shrink-0" />
 }
 if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) {
 return <FileImage size={14} className="text-[var(--domain-analysis)] flex-shrink-0" />
 }
 if (['html', 'htm'].includes(ext)) {
 return <FileCode size={14} className="text-[var(--warning)] flex-shrink-0" />
 }
 if (['md', 'txt', 'log'].includes(ext)) {
 return <FileText size={14} className="text-[var(--accent)] flex-shrink-0" />
 }
 if (['json', 'py', 'r'].includes(ext)) {
 return <FileCode size={14} className="text-[var(--warning)] flex-shrink-0" />
 }
 if (ext === 'pdf') {
 return <FileText size={14} className="text-[var(--error)] flex-shrink-0" />
 }
 return <File size={14} className="text-[var(--text-secondary)] flex-shrink-0" />
}

const kindLabels: Record<string, string> = {
 dataset: '数据集',
 document: '文档',
 result: '结果',
}

interface Props {
 file: WorkspaceFile
}

export default React.memo(function FileListItem({ file }: Props) {
 const confirm = useConfirm()
 const deleteWorkspaceFile = useStore((s) => s.deleteWorkspaceFile)
 const renameWorkspaceFile = useStore((s) => s.renameWorkspaceFile)
 const openPreview = useStore((s) => s.openPreview)
 const [isRenaming, setIsRenaming] = useState(false)
 const [renameValue, setRenameValue] = useState(file.name)
 const inputRef = useRef<HTMLInputElement>(null)

 useEffect(() => {
 if (isRenaming && inputRef.current) {
 inputRef.current.focus()
 inputRef.current.select()
 }
 }, [isRenaming])

 const handleRename = useCallback(async () => {
 const trimmed = renameValue.trim()
 if (trimmed && trimmed !== file.name && file.path) {
 await renameWorkspaceFile(file.path, trimmed)
 }
 setIsRenaming(false)
 }, [renameValue, file.name, file.path, renameWorkspaceFile])

 const handleDelete = useCallback(async () => {
 const ok = await confirm({
 title: "删除文件",
 message: `确定删除文件「${file.name}」？此操作不可撤销。`,
 confirmText: "删除",
 destructive: true,
 })
 if (!ok) return
 if (!file.path) return
 await deleteWorkspaceFile(file.path)
 }, [file.name, file.path, deleteWorkspaceFile, confirm])
 const downloadUrl = resolveDownloadUrl(file.download_url, file.name) || file.download_url
 const handleDownload = useCallback(
 async (e: React.MouseEvent<HTMLButtonElement>) => {
 e.stopPropagation()
 try {
 await downloadFileFromUrl(downloadUrl, file.name)
 } catch (error) {
 console.error('工作区文件下载失败:', error)
 }
 },
 [downloadUrl, file.name],
 )

 return (
 <div className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-[var(--bg-hover)] transition-colors">
 {/* 可点击区域：图标 + 文件名信息 */}
 {isRenaming ? (
 <>
 {getFileIcon(file)}
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-1">
 <input
 ref={inputRef}
 value={renameValue}
 onChange={(e) => setRenameValue(e.target.value)}
 onKeyDown={(e) => {
 if (e.key === 'Enter') handleRename()
 if (e.key === 'Escape') {
 setRenameValue(file.name)
 setIsRenaming(false)
 }
 }}
 aria-label={`重命名 ${file.name}`}
                 className="flex-1 min-w-0 text-xs rounded border border-[var(--accent)] px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
 />
 <Button variant="ghost" onClick={handleRename} className="p-2 text-[var(--success)] hover:text-[var(--success)]" aria-label="确认重命名">
 <Check size={12} />
 </Button>
 <Button
 variant="ghost"
 onClick={() => {
 setRenameValue(file.name)
 setIsRenaming(false)
 }}
 className="p-2"
 aria-label="取消重命名"
 >
 <X size={12} />
 </Button>
 </div>
 </div>
 </>
 ) : (
 <Button
 variant="ghost"
 className="flex flex-1 items-center gap-2 cursor-pointer min-w-0 text-left bg-transparent border-none p-0 focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-1 rounded"
 onClick={() => openPreview(file.id)}
 aria-label={`预览 ${file.name}`}
 >
 {getFileIcon(file)}
 <div className="flex-1 min-w-0">
 <div className="text-xs text-[var(--text-secondary)] truncate hover:text-[var(--accent)] transition-colors">{file.name}</div>
 <div className="text-[10px] text-[var(--text-muted)]">
 {kindLabels[file.kind] || file.kind} · {formatSize(file.size)}
 </div>
 </div>
 </Button>
 )}

 {/* 操作按钮：始终可见（触屏可点击），桌面端 hover 时更突出 */}
 {!isRenaming && (
 <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
 <Button
 variant="ghost"
 onClick={handleDownload}
 className="p-1.5 rounded"
 title="下载"
 aria-label="下载文件"
 >
 <Download size={12} />
 </Button>
 <Button
 variant="ghost"
 onClick={(e) => {
 e.stopPropagation()
 setRenameValue(file.name)
 setIsRenaming(true)
 }}
 className="p-1.5 rounded"
 title="重命名"
 aria-label="重命名文件"
 >
 <Pencil size={12} />
 </Button>
 <Button
 variant="ghost"
 onClick={(e) => {
 e.stopPropagation()
 handleDelete()
 }}
 className="p-1.5 rounded hover:bg-[var(--accent-subtle)] hover:text-[var(--error)]"
 title="删除"
 aria-label="删除文件"
 >
 <Trash2 size={12} />
 </Button>
 </div>
 )}
 </div>
 )
})
