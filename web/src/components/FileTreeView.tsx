/**
 * 目录树导航组件 —— 按用户心智分为数据/文档/结果三类，并显示自定义文件夹。
 */
import { useState, useMemo, useEffect } from 'react'
import { useStore, type WorkspaceFile } from '../store'
import FileListItem from './FileListItem'
import { ChevronDown, ChevronRight, Database, Package, StickyNote, Folder, FolderPlus } from 'lucide-react'
import Button from './ui/Button'

interface FolderGroup {
 label: string
 kind: string
 icon: React.ReactNode
 files: WorkspaceFile[]
}

function FolderNode({ group }: { group: FolderGroup }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-transparent border-none cursor-pointer hover:bg-[var(--bg-hover)] transition-colors"
      >
        {expanded ? (
          <ChevronDown size={12} className="text-[var(--text-muted)] flex-shrink-0" />
        ) : (
          <ChevronRight size={12} className="text-[var(--text-muted)] flex-shrink-0" />
        )}
        {group.icon}
        <span className="text-xs font-medium text-[var(--text-secondary)]">{group.label}</span>
        <span className="text-[10px] text-[var(--text-muted)] ml-auto">{group.files.length}</span>
      </button>

      {expanded && group.files.length > 0 && (
 <div className="ml-3 border-l border-[var(--border-subtle)] pl-1">
 {group.files.map((file) => (
 <FileListItem key={file.id} file={file} />
 ))}
 </div>
 )}

 {expanded && group.files.length === 0 && (
 <div className="ml-8 text-[10px] text-[var(--text-muted)] py-1">无文件</div>
 )}
 </div>
 )
}

export default function FileTreeView() {
 const workspaceFiles = useStore((s) => s.workspaceFiles)
 const workspaceFolders = useStore((s) => s.workspaceFolders)
 const fileSearchQuery = useStore((s) => s.fileSearchQuery)
 const fetchFolders = useStore((s) => s.fetchFolders)
 const createFolder = useStore((s) => s.createFolder)
 const [showNewFolder, setShowNewFolder] = useState(false)
 const [newFolderName, setNewFolderName] = useState('')

 useEffect(() => {
 fetchFolders()
 }, [fetchFolders])

 const filteredFiles = useMemo(() => {
 if (!fileSearchQuery.trim()) return workspaceFiles
 const q = fileSearchQuery.trim().toLowerCase()
 return workspaceFiles.filter((f) => f.name.toLowerCase().includes(q))
 }, [workspaceFiles, fileSearchQuery])

 // 默认三分类目录
 const defaultGroups: FolderGroup[] = useMemo(() => [
 {
 label: '数据集',
 kind: 'dataset',
 icon: <Database size={13} className="text-[var(--success)] flex-shrink-0" />,
 files: filteredFiles.filter((f) => f.kind === 'dataset' && !f.folder),
 },
 {
 label: '文档',
 kind: 'document',
 icon: <StickyNote size={13} className="text-[var(--accent)] flex-shrink-0" />,
 files: filteredFiles.filter((f) => f.kind === 'document' && !f.folder),
 },
 {
 label: '结果',
 kind: 'result',
 icon: <Package size={13} className="text-[var(--domain-analysis)] flex-shrink-0" />,
 files: filteredFiles.filter((f) => f.kind === 'result' && !f.folder),
 },
 ], [filteredFiles])

 // 自定义文件夹
 const customGroups: FolderGroup[] = useMemo(() => {
 return workspaceFolders.map((folder) => ({
 label: folder.name,
 kind: `folder-${folder.id}`,
 icon: <Folder size={13} className="text-[var(--warning)] flex-shrink-0" />,
 files: filteredFiles.filter((f) => f.folder === folder.id),
 }))
 }, [workspaceFolders, filteredFiles])

 const handleCreateFolder = async () => {
 if (!newFolderName.trim()) return
 await createFolder(newFolderName.trim())
 setNewFolderName('')
 setShowNewFolder(false)
 }

 if (filteredFiles.length === 0 && workspaceFolders.length === 0) {
 return (
 <div className="text-center text-xs text-[var(--text-muted)] py-8">
 {fileSearchQuery ? '没有匹配的文件' : '暂无文件'}
 </div>
 )
 }

 return (
 <div className="space-y-1">
 {defaultGroups.map((group) => (
 <FolderNode key={group.kind} group={group} />
 ))}

 {customGroups.length > 0 && (
 <div className="pt-1 border-t border-[var(--border-subtle)] mt-1">
 {customGroups.map((group) => (
 <FolderNode key={group.kind} group={group} />
 ))}
 </div>
 )}

 {/* 新建文件夹 */}
 <div className="pt-1">
 {showNewFolder ? (
 <div className="flex items-center gap-1 px-2">
 <input
 value={newFolderName}
 onChange={(e) => setNewFolderName(e.target.value)}
 onKeyDown={(e) => {
 if (e.key === 'Enter') handleCreateFolder()
 if (e.key === 'Escape') { setShowNewFolder(false); setNewFolderName('') }
 }}
 aria-label="新建文件夹名称"
                 placeholder="文件夹名称"
 className="flex-1 px-2 py-1 text-xs border border-[var(--border-default)] rounded focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
 autoFocus
 />
 <Button
 variant="primary"
 onClick={handleCreateFolder}
 className="px-2 py-1 text-[10px] rounded"
 >
 创建
 </Button>
 </div>
 ) : (
 <Button
 variant="ghost"
 onClick={() => setShowNewFolder(true)}
 className="flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md w-full"
 >
 <FolderPlus size={12} />
 新建文件夹
 </Button>
 )}
 </div>
 </div>
 )
}
