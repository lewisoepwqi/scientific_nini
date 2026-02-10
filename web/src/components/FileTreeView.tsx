/**
 * 目录树导航组件 —— 按文件类型分为三个默认目录，并显示自定义文件夹。
 */
import { useState, useMemo, useEffect } from 'react'
import { useStore, type WorkspaceFile } from '../store'
import FileListItem from './FileListItem'
import { ChevronDown, ChevronRight, Database, Package, StickyNote, Folder, FolderPlus } from 'lucide-react'

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
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 hover:bg-gray-50 rounded-md transition-colors"
      >
        {expanded ? (
          <ChevronDown size={12} className="text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight size={12} className="text-gray-400 flex-shrink-0" />
        )}
        {group.icon}
        <span className="text-xs font-medium text-gray-600">{group.label}</span>
        <span className="text-[10px] text-gray-400 ml-auto">{group.files.length}</span>
      </button>

      {expanded && group.files.length > 0 && (
        <div className="ml-3 border-l border-gray-100 pl-1">
          {group.files.map((file) => (
            <FileListItem key={file.id} file={file} />
          ))}
        </div>
      )}

      {expanded && group.files.length === 0 && (
        <div className="ml-8 text-[10px] text-gray-400 py-1">无文件</div>
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
      icon: <Database size={13} className="text-emerald-500 flex-shrink-0" />,
      files: filteredFiles.filter((f) => f.kind === 'dataset' && !f.folder),
    },
    {
      label: '产物',
      kind: 'artifact',
      icon: <Package size={13} className="text-purple-500 flex-shrink-0" />,
      files: filteredFiles.filter((f) => f.kind === 'artifact' && !f.folder),
    },
    {
      label: '笔记',
      kind: 'note',
      icon: <StickyNote size={13} className="text-blue-500 flex-shrink-0" />,
      files: filteredFiles.filter((f) => f.kind === 'note' && !f.folder),
    },
  ], [filteredFiles])

  // 自定义文件夹
  const customGroups: FolderGroup[] = useMemo(() => {
    return workspaceFolders.map((folder) => ({
      label: folder.name,
      kind: `folder-${folder.id}`,
      icon: <Folder size={13} className="text-amber-500 flex-shrink-0" />,
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
      <div className="text-center text-xs text-gray-400 py-8">
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
        <div className="pt-1 border-t border-gray-100 mt-1">
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
              placeholder="文件夹名称"
              className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-400"
              autoFocus
            />
            <button
              onClick={handleCreateFolder}
              className="px-2 py-1 text-[10px] bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              创建
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowNewFolder(true)}
            className="flex items-center gap-1.5 px-2 py-1.5 text-xs text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded-md transition-colors w-full"
          >
            <FolderPlus size={12} />
            新建文件夹
          </button>
        )}
      </div>
    </div>
  )
}
