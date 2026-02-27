/**
 * Markdown 技能管理弹窗 —— 上传、启用、编辑、删除与附属文件管理。
 */
import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useStore, type SkillItem, type SkillPathEntry } from '../store'
import {
  X,
  RefreshCw,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Upload,
  Pencil,
  Trash2,
  Loader2,
  Save,
  FolderPlus,
  Download,
  FileText,
  Folder,
} from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
}

const CATEGORY_LABELS: Record<string, string> = {
  data: '数据操作',
  statistics: '统计检验',
  visualization: '可视化',
  export: '导出',
  report: '报告',
  workflow: '工作流',
  utility: '通用工具',
  other: '其他',
}

const CATEGORY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'data', label: '数据操作' },
  { value: 'statistics', label: '统计检验' },
  { value: 'visualization', label: '可视化' },
  { value: 'export', label: '导出' },
  { value: 'report', label: '报告' },
  { value: 'workflow', label: '工作流' },
  { value: 'utility', label: '通用工具' },
  { value: 'other', label: '其他' },
]

function groupMarkdownSkills(skills: SkillItem[]): Array<[string, SkillItem[]]> {
  const map = new Map<string, SkillItem[]>()
  for (const s of skills) {
    const cat = s.category || 'other'
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat)!.push(s)
  }

  const order = ['workflow', 'report', 'data', 'statistics', 'visualization', 'export', 'utility', 'other']
  const grouped: Array<[string, SkillItem[]]> = []
  for (const key of order) {
    const items = map.get(key)
    if (items && items.length > 0) grouped.push([key, items])
  }
  for (const [key, items] of map) {
    if (!order.includes(key)) grouped.push([key, items])
  }
  return grouped
}

function getSkillBody(content: string): string {
  const normalized = content.replace(/\r\n/g, '\n')
  const frontmatter = normalized.match(/^\s*---\s*\n[\s\S]*?\n---\s*\n?/)
  if (!frontmatter) return normalized.trim()
  return normalized.slice(frontmatter[0].length).trim()
}

function hasFunctionConflict(skill: SkillItem): boolean {
  if (!skill.metadata || typeof skill.metadata !== 'object') return false
  return (skill.metadata as Record<string, unknown>).conflict_with === 'function'
}

interface SkillTreeNode {
  path: string
  name: string
  type: 'file' | 'dir'
  size: number
  children: SkillTreeNode[]
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '')
}

function dirname(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx >= 0 ? path.slice(0, idx) : ''
}

function basename(path: string): string {
  const idx = path.lastIndexOf('/')
  return idx >= 0 ? path.slice(idx + 1) : path
}

function buildSkillTree(files: SkillPathEntry[]): SkillTreeNode[] {
  const roots: SkillTreeNode[] = []
  const nodeMap = new Map<string, SkillTreeNode>()

  const attachNode = (node: SkillTreeNode) => {
    const parent = dirname(node.path)
    if (!parent) {
      roots.push(node)
      return
    }
    const parentNode = ensureDir(parent)
    if (!parentNode.children.some((c) => c.path === node.path)) {
      parentNode.children.push(node)
    }
  }

  const ensureDir = (path: string): SkillTreeNode => {
    const normalized = normalizePath(path)
    const existing = nodeMap.get(normalized)
    if (existing) return existing
    const node: SkillTreeNode = {
      path: normalized,
      name: basename(normalized),
      type: 'dir',
      size: 0,
      children: [],
    }
    nodeMap.set(normalized, node)
    attachNode(node)
    return node
  }

  for (const file of files) {
    const normalized = normalizePath(file.path)
    if (!normalized) continue
    if (file.type === 'dir') {
      const dirNode = ensureDir(normalized)
      dirNode.size = file.size
      continue
    }

    const parent = dirname(normalized)
    if (parent) ensureDir(parent)
    const node: SkillTreeNode = {
      path: normalized,
      name: basename(normalized),
      type: 'file',
      size: file.size,
      children: [],
    }
    nodeMap.set(normalized, node)
    attachNode(node)
  }

  const sortNodes = (nodes: SkillTreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const node of nodes) {
      if (node.type === 'dir' && node.children.length > 0) {
        sortNodes(node.children)
      }
    }
  }
  sortNodes(roots)
  return roots
}

export default function MarkdownSkillManagerPanel({ open, onClose }: Props) {
  const skills = useStore((s) => s.skills)
  const fetchSkills = useStore((s) => s.fetchSkills)
  const uploadSkillFile = useStore((s) => s.uploadSkillFile)
  const getSkillDetail = useStore((s) => s.getSkillDetail)
  const updateSkill = useStore((s) => s.updateSkill)
  const toggleSkillEnabled = useStore((s) => s.toggleSkillEnabled)
  const deleteSkill = useStore((s) => s.deleteSkill)
  const listSkillFiles = useStore((s) => s.listSkillFiles)
  const getSkillFileContent = useStore((s) => s.getSkillFileContent)
  const saveSkillFileContent = useStore((s) => s.saveSkillFileContent)
  const uploadSkillAttachment = useStore((s) => s.uploadSkillAttachment)
  const createSkillDir = useStore((s) => s.createSkillDir)
  const deleteSkillPath = useStore((s) => s.deleteSkillPath)
  const downloadSkillBundle = useStore((s) => s.downloadSkillBundle)

  const markdownSkills = useMemo(
    () => skills.filter((s) => s.type === 'markdown'),
    [skills],
  )
  const grouped = useMemo(() => groupMarkdownSkills(markdownSkills), [markdownSkills])

  const [openCats, setOpenCats] = useState<Set<string>>(new Set(['workflow']))
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [editingSkill, setEditingSkill] = useState<SkillItem | null>(null)
  const [editDescription, setEditDescription] = useState('')
  const [editCategory, setEditCategory] = useState('other')
  const [editContent, setEditContent] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

  const [filesLoading, setFilesLoading] = useState(false)
  const [skillFiles, setSkillFiles] = useState<SkillPathEntry[]>([])
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [selectedFileContent, setSelectedFileContent] = useState('')
  const [selectedFileIsText, setSelectedFileIsText] = useState(true)
  const [selectedFileDirty, setSelectedFileDirty] = useState(false)
  const [fileLoading, setFileLoading] = useState(false)
  const [uploadDirPath, setUploadDirPath] = useState('')
  const [newDirPath, setNewDirPath] = useState('')
  const [openDirs, setOpenDirs] = useState<Set<string>>(new Set())

  const fileInputRef = useRef<HTMLInputElement>(null)
  const attachmentInputRef = useRef<HTMLInputElement>(null)

  const resetFilePanel = useCallback(() => {
    setSkillFiles([])
    setSelectedPath(null)
    setSelectedFileContent('')
    setSelectedFileIsText(true)
    setSelectedFileDirty(false)
    setUploadDirPath('')
    setNewDirPath('')
    setOpenDirs(new Set())
  }, [])

  const refreshSkillFiles = useCallback(async (skillName: string) => {
    setFilesLoading(true)
    const result = await listSkillFiles(skillName)
    if (result.success && result.files) {
      setSkillFiles(result.files)
      const defaultOpen = new Set<string>()
      for (const entry of result.files) {
        if (entry.type === 'dir' && !entry.path.includes('/')) {
          defaultOpen.add(entry.path)
        }
      }
      setOpenDirs((prev) => {
        if (prev.size === 0) return defaultOpen
        const merged = new Set(prev)
        for (const value of defaultOpen) merged.add(value)
        return merged
      })
      if (selectedPath && !result.files.some((f) => f.path === selectedPath)) {
        setSelectedPath(null)
        setSelectedFileContent('')
        setSelectedFileDirty(false)
      }
    } else {
      setError(result.message)
    }
    setFilesLoading(false)
  }, [listSkillFiles, selectedPath])

  useEffect(() => {
    if (!open) return
    fetchSkills()
    setNotice(null)
    setError(null)
  }, [open, fetchSkills])

  useEffect(() => {
    if (!editingSkill) return
    const exists = markdownSkills.some((s) => s.name === editingSkill.name)
    if (!exists) {
      setEditingSkill(null)
      setEditDescription('')
      setEditCategory('other')
      setEditContent('')
      resetFilePanel()
    }
  }, [markdownSkills, editingSkill, resetFilePanel])

  const toggleCat = useCallback((cat: string) => {
    setOpenCats((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) {
        next.delete(cat)
      } else {
        next.add(cat)
      }
      return next
    })
  }, [])

  const handleUpload = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setBusyKey('upload')
    setNotice(null)
    setError(null)
    const result = await uploadSkillFile(file)
    if (result.success) {
      setNotice(`上传成功：${file.name}`)
      await fetchSkills()
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [uploadSkillFile, fetchSkills])

  const handleStartEdit = useCallback(async (skill: SkillItem) => {
    setBusyKey(`edit:${skill.name}`)
    setNotice(null)
    setError(null)
    const result = await getSkillDetail(skill.name)
    if (!result.success || !result.skill) {
      setError(result.message)
      setBusyKey(null)
      return
    }

    setEditingSkill(skill)
    setEditDescription(result.skill.description || skill.description || '')
    setEditCategory(result.skill.category || skill.category || 'other')
    setEditContent(getSkillBody(result.skill.content || ''))
    setSelectedPath(null)
    setSelectedFileContent('')
    setSelectedFileDirty(false)
    setOpenDirs(new Set())
    await refreshSkillFiles(skill.name)
    setBusyKey(null)
  }, [getSkillDetail, refreshSkillFiles])

  const handleSaveEdit = useCallback(async () => {
    if (!editingSkill) return

    const description = editDescription.trim()
    if (!description) {
      setError('描述不能为空')
      return
    }

    setSavingEdit(true)
    setNotice(null)
    setError(null)
    const result = await updateSkill(editingSkill.name, {
      description,
      category: editCategory,
      content: editContent,
    })
    if (result.success) {
      setNotice(`已保存：${editingSkill.name}`)
      await fetchSkills()
      await refreshSkillFiles(editingSkill.name)
    } else {
      setError(result.message)
    }
    setSavingEdit(false)
  }, [editingSkill, editDescription, editCategory, editContent, updateSkill, fetchSkills, refreshSkillFiles])

  const handleToggleEnabled = useCallback(async (skill: SkillItem, enabled: boolean) => {
    setBusyKey(`toggle:${skill.name}`)
    setNotice(null)
    setError(null)
    const result = await toggleSkillEnabled(skill.name, enabled)
    if (result.success) {
      setNotice(`${enabled ? '已启用' : '已禁用'}：${skill.name}`)
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [toggleSkillEnabled])

  const handleDelete = useCallback(async (skill: SkillItem) => {
    if (!window.confirm(`确认删除技能 ${skill.name} 吗？`)) return

    setBusyKey(`delete:${skill.name}`)
    setNotice(null)
    setError(null)
    const result = await deleteSkill(skill.name)
    if (result.success) {
      if (editingSkill?.name === skill.name) {
        setEditingSkill(null)
        setEditDescription('')
        setEditCategory('other')
        setEditContent('')
        resetFilePanel()
      }
      setNotice(`已删除：${skill.name}`)
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [deleteSkill, editingSkill, resetFilePanel])

  const handleSelectPath = useCallback(async (entry: SkillPathEntry) => {
    if (!editingSkill) return

    setSelectedPath(entry.path)
    if (entry.type === 'dir') {
      setSelectedFileContent('')
      setSelectedFileIsText(false)
      setSelectedFileDirty(false)
      return
    }

    setFileLoading(true)
    const result = await getSkillFileContent(editingSkill.name, entry.path)
    if (result.success && result.file) {
      setSelectedFileIsText(result.file.is_text)
      setSelectedFileContent(result.file.content || '')
      setSelectedFileDirty(false)
    } else {
      setError(result.message)
    }
    setFileLoading(false)
  }, [editingSkill, getSkillFileContent])

  const handleSaveSelectedFile = useCallback(async () => {
    if (!editingSkill || !selectedPath || !selectedFileIsText) return

    setBusyKey('save-file')
    setNotice(null)
    setError(null)
    const result = await saveSkillFileContent(editingSkill.name, selectedPath, selectedFileContent)
    if (result.success) {
      setNotice(`已保存文件：${selectedPath}`)
      setSelectedFileDirty(false)
      await refreshSkillFiles(editingSkill.name)
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [editingSkill, selectedPath, selectedFileIsText, selectedFileContent, saveSkillFileContent, refreshSkillFiles])

  const handleUploadAttachment = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !editingSkill) return

    setBusyKey('upload-attachment')
    setNotice(null)
    setError(null)
    const result = await uploadSkillAttachment(editingSkill.name, file, uploadDirPath)
    if (result.success) {
      setNotice(`附件上传成功：${file.name}`)
      await refreshSkillFiles(editingSkill.name)
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [editingSkill, uploadDirPath, uploadSkillAttachment, refreshSkillFiles])

  const handleCreateDir = useCallback(async () => {
    if (!editingSkill) return
    const path = newDirPath.trim()
    if (!path) {
      setError('目录路径不能为空')
      return
    }

    setBusyKey('create-dir')
    setNotice(null)
    setError(null)
    const result = await createSkillDir(editingSkill.name, path)
    if (result.success) {
      setNotice(`目录已创建：${path}`)
      setNewDirPath('')
      await refreshSkillFiles(editingSkill.name)
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [editingSkill, newDirPath, createSkillDir, refreshSkillFiles])

  const handleDeletePath = useCallback(async () => {
    if (!editingSkill || !selectedPath) return
    if (!window.confirm(`确认删除路径 ${selectedPath} 吗？`)) return

    setBusyKey('delete-path')
    setNotice(null)
    setError(null)
    const result = await deleteSkillPath(editingSkill.name, selectedPath)
    if (result.success) {
      setNotice(`已删除：${selectedPath}`)
      setSelectedPath(null)
      setSelectedFileContent('')
      setSelectedFileDirty(false)
      await refreshSkillFiles(editingSkill.name)
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [editingSkill, selectedPath, deleteSkillPath, refreshSkillFiles])

  const handleDownloadBundle = useCallback(async () => {
    if (!editingSkill) return
    setBusyKey('download-bundle')
    setNotice(null)
    setError(null)
    const result = await downloadSkillBundle(editingSkill.name)
    if (result.success) {
      setNotice(`已下载技能包：${editingSkill.name}`)
    } else {
      setError(result.message)
    }
    setBusyKey(null)
  }, [editingSkill, downloadSkillBundle])

  const handleToggleDir = useCallback((path: string) => {
    setOpenDirs((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }, [])

  useEffect(() => {
    if (!selectedPath) return
    const parts = selectedPath.split('/')
    if (parts.length <= 1) return
    setOpenDirs((prev) => {
      const next = new Set(prev)
      for (let i = 1; i < parts.length; i += 1) {
        next.add(parts.slice(0, i).join('/'))
      }
      return next
    })
  }, [selectedPath])

  const fileTree = useMemo(() => buildSkillTree(skillFiles), [skillFiles])
  const selectedEntry = selectedPath
    ? skillFiles.find((entry) => entry.path === selectedPath) ?? null
    : null

  if (!open) return null

  const enabledCount = markdownSkills.filter((s) => s.enabled).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-7xl mx-4 max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div className="flex items-center gap-2">
            <BookOpen size={18} className="text-emerald-600" />
            <h2 className="text-base font-semibold text-gray-800">技能管理（Markdown）</h2>
            <span className="text-xs text-gray-400">{enabledCount} 个启用 / {markdownSkills.length} 个技能</span>
          </div>
          <div className="flex items-center gap-1">
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,.markdown,.txt"
              className="hidden"
              onChange={handleUpload}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={busyKey === 'upload'}
              className="px-2.5 py-1.5 rounded-lg text-xs border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              title="上传 Markdown Skill"
            >
              <span className="inline-flex items-center gap-1">
                {busyKey === 'upload' ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                上传技能
              </span>
            </button>
            <button
              onClick={fetchSkills}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
              title="刷新"
            >
              <RefreshCw size={14} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
              title="关闭"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {(notice || error) && (
          <div className={`px-5 py-2 text-xs border-b ${error ? 'bg-red-50 text-red-600 border-red-100' : 'bg-emerald-50 text-emerald-700 border-emerald-100'}`}>
            {error || notice}
          </div>
        )}

        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[1.05fr_1.95fr]">
          <div className="min-h-0 overflow-y-auto px-5 py-3 border-r border-gray-100">
            <div className="space-y-1">
              {grouped.map(([cat, items]) => {
                const isOpen = openCats.has(cat)
                const label = CATEGORY_LABELS[cat] || cat
                return (
                  <div key={cat} className="border border-gray-200 rounded-lg">
                    <button
                      onClick={() => toggleCat(cat)}
                      className="w-full px-3 py-2 text-left flex items-center gap-2 hover:bg-gray-50 transition-colors"
                    >
                      {isOpen ? (
                        <ChevronDown size={14} className="text-gray-400" />
                      ) : (
                        <ChevronRight size={14} className="text-gray-400" />
                      )}
                      <span className="text-sm font-medium text-gray-700">{label}</span>
                      <span className="ml-auto text-xs text-gray-400">{items.length}</span>
                    </button>
                    {isOpen && (
                      <div className="border-t px-3 py-2 space-y-1.5">
                        {items.map((s) => {
                          const conflict = hasFunctionConflict(s)
                          const toggleBusy = busyKey === `toggle:${s.name}`
                          const editBusy = busyKey === `edit:${s.name}`
                          const deleteBusy = busyKey === `delete:${s.name}`
                          return (
                            <div key={s.name} className="text-xs border border-gray-100 rounded px-2 py-1.5">
                              <div className="flex items-start gap-2">
                                <span className={`font-mono flex-shrink-0 ${s.enabled ? 'text-gray-700' : 'text-gray-400 line-through'}`}>
                                  {s.name}
                                </span>
                                <span className="text-gray-400 flex-1">{s.description}</span>
                                {conflict && (
                                  <span className="text-[10px] text-amber-600 bg-amber-100 px-1 rounded">同名冲突</span>
                                )}
                              </div>

                              <div className="mt-1.5 flex items-center justify-between gap-2">
                                <label className="inline-flex items-center gap-1.5 text-[11px] text-gray-600">
                                  <input
                                    type="checkbox"
                                    checked={s.enabled}
                                    disabled={toggleBusy || conflict}
                                    onChange={(e) => handleToggleEnabled(s, e.target.checked)}
                                  />
                                  启用
                                </label>
                                <div className="flex items-center gap-1">
                                  <button
                                    onClick={() => handleStartEdit(s)}
                                    disabled={editBusy}
                                    className="px-1.5 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                                    title="编辑"
                                  >
                                    {editBusy ? <Loader2 size={11} className="animate-spin" /> : <Pencil size={11} />}
                                  </button>
                                  <button
                                    onClick={() => handleDelete(s)}
                                    disabled={deleteBusy}
                                    className="px-1.5 py-1 rounded border border-red-200 text-red-500 hover:bg-red-50 disabled:opacity-50"
                                    title="删除技能"
                                  >
                                    {deleteBusy ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                                  </button>
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
              {grouped.length === 0 && (
                <div className="text-xs text-gray-400 text-center py-6">暂无 Markdown 技能</div>
              )}
            </div>
          </div>

          <div className="min-h-0 overflow-y-auto px-5 py-4 space-y-4">
            {!editingSkill && (
              <div className="h-full flex items-center justify-center text-xs text-gray-400">
                从左侧选择一个技能进行管理
              </div>
            )}

            {editingSkill && (
              <>
                <div className="space-y-3 border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-800">技能内容编辑：{editingSkill.name}</h3>
                      <p className="text-xs text-gray-400 mt-0.5">编辑 SKILL.md 的描述/分类/正文</p>
                    </div>
                    <button
                      onClick={handleSaveEdit}
                      disabled={savingEdit}
                      className="px-2.5 py-1.5 rounded-lg text-xs border border-emerald-200 text-emerald-600 hover:bg-emerald-50 disabled:opacity-50"
                    >
                      <span className="inline-flex items-center gap-1">
                        {savingEdit ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                        保存技能
                      </span>
                    </button>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-600 mb-1">描述</label>
                    <input
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      className="w-full px-2.5 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-100"
                      placeholder="技能描述"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-gray-600 mb-1">分类</label>
                    <select
                      value={editCategory}
                      onChange={(e) => setEditCategory(e.target.value)}
                      className="w-full px-2.5 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-100"
                    >
                      {CATEGORY_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-gray-600 mb-1">正文（不含 frontmatter）</label>
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      className="w-full min-h-[220px] px-2.5 py-2 text-xs font-mono border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-100"
                      placeholder="请输入 Markdown 正文"
                    />
                  </div>
                </div>

                <div className="space-y-3 border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-800">附属文件管理（scripts/references/assets）</h3>
                      <p className="text-xs text-gray-400 mt-0.5">支持目录创建、附件上传、文本文件编辑与技能包下载</p>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => refreshSkillFiles(editingSkill.name)}
                        className="px-2 py-1 rounded text-xs border border-gray-200 text-gray-600 hover:bg-gray-50"
                      >
                        {filesLoading ? <Loader2 size={12} className="animate-spin" /> : '刷新文件'}
                      </button>
                      <button
                        onClick={handleDownloadBundle}
                        disabled={busyKey === 'download-bundle'}
                        className="px-2 py-1 rounded text-xs border border-blue-200 text-blue-600 hover:bg-blue-50 disabled:opacity-50"
                      >
                        <span className="inline-flex items-center gap-1">
                          {busyKey === 'download-bundle' ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                          下载技能包
                        </span>
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-3">
                    <div className="border rounded-lg p-2">
                      <div className="flex items-center gap-2 mb-2">
                        <input
                          value={newDirPath}
                          onChange={(e) => setNewDirPath(e.target.value)}
                          placeholder="新目录路径，如 scripts/helpers"
                          className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded"
                        />
                        <button
                          onClick={handleCreateDir}
                          disabled={busyKey === 'create-dir'}
                          className="px-2 py-1 text-xs border rounded border-gray-200 hover:bg-gray-50 disabled:opacity-50"
                        >
                          <span className="inline-flex items-center gap-1">
                            {busyKey === 'create-dir' ? <Loader2 size={11} className="animate-spin" /> : <FolderPlus size={11} />}
                            新建目录
                          </span>
                        </button>
                      </div>

                      <div className="flex items-center gap-2 mb-2">
                        <input
                          value={uploadDirPath}
                          onChange={(e) => setUploadDirPath(e.target.value)}
                          placeholder="上传目录（可空，根目录）"
                          className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded"
                        />
                        <input
                          ref={attachmentInputRef}
                          type="file"
                          className="hidden"
                          onChange={handleUploadAttachment}
                        />
                        <button
                          onClick={() => attachmentInputRef.current?.click()}
                          disabled={busyKey === 'upload-attachment'}
                          className="px-2 py-1 text-xs border rounded border-gray-200 hover:bg-gray-50 disabled:opacity-50"
                        >
                          <span className="inline-flex items-center gap-1">
                            {busyKey === 'upload-attachment' ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                            上传附件
                          </span>
                        </button>
                      </div>

                      <div className="max-h-[300px] overflow-y-auto border rounded">
                        {fileTree.length === 0 && (
                          <div className="text-xs text-gray-400 p-3">暂无文件</div>
                        )}
                        {fileTree.map((node) => {
                          const renderNode = (entryNode: SkillTreeNode, depth: number): JSX.Element => {
                            const isDir = entryNode.type === 'dir'
                            const isOpen = isDir && openDirs.has(entryNode.path)
                            const isSelected = selectedPath === entryNode.path
                            const entry: SkillPathEntry = {
                              path: entryNode.path,
                              name: entryNode.name,
                              type: entryNode.type,
                              size: entryNode.size,
                            }

                            return (
                              <div key={entryNode.path}>
                                <button
                                  onClick={() => {
                                    if (isDir) handleToggleDir(entryNode.path)
                                    void handleSelectPath(entry)
                                  }}
                                  className={`w-full text-left py-1.5 text-xs border-b last:border-b-0 hover:bg-gray-50 flex items-center gap-1.5 ${isSelected ? 'bg-emerald-50' : ''}`}
                                  style={{ paddingLeft: `${8 + depth * 14}px`, paddingRight: '8px' }}
                                >
                                  {isDir ? (
                                    isOpen ? <ChevronDown size={12} className="text-gray-400" /> : <ChevronRight size={12} className="text-gray-400" />
                                  ) : (
                                    <span className="inline-block w-3" />
                                  )}
                                  {isDir ? <Folder size={12} className="text-sky-500" /> : <FileText size={12} className="text-gray-500" />}
                                  <span className="font-mono truncate">{entryNode.name}</span>
                                  <span className="ml-auto text-[10px] text-gray-400">{entryNode.path}</span>
                                </button>
                                {isDir && isOpen && entryNode.children.length > 0 && (
                                  <div>
                                    {entryNode.children.map((child) => renderNode(child, depth + 1))}
                                  </div>
                                )}
                              </div>
                            )
                          }
                          return renderNode(node, 0)
                        })}
                      </div>

                      <div className="mt-2">
                        <button
                          onClick={handleDeletePath}
                          disabled={!selectedPath || busyKey === 'delete-path'}
                          className="px-2 py-1 text-xs border rounded border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
                        >
                          <span className="inline-flex items-center gap-1">
                            {busyKey === 'delete-path' ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                            删除选中路径
                          </span>
                        </button>
                      </div>
                    </div>

                    <div className="border rounded-lg p-2">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-xs text-gray-600 font-mono truncate">{selectedPath || '未选择文件'}</div>
                        <button
                          onClick={handleSaveSelectedFile}
                          disabled={!selectedPath || !selectedFileIsText || !selectedFileDirty || busyKey === 'save-file'}
                          className="px-2 py-1 text-xs border rounded border-emerald-200 text-emerald-600 hover:bg-emerald-50 disabled:opacity-50"
                        >
                          <span className="inline-flex items-center gap-1">
                            {busyKey === 'save-file' ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
                            保存文件
                          </span>
                        </button>
                      </div>

                      {fileLoading && (
                        <div className="text-xs text-gray-400">正在读取文件...</div>
                      )}

                      {!fileLoading && selectedPath && !selectedFileIsText && (
                        <div className="text-xs text-amber-600 bg-amber-50 border border-amber-100 rounded p-2">
                          {selectedEntry?.type === 'dir'
                            ? '当前选中目录，不支持文本编辑。'
                            : '当前文件为二进制文件，不支持文本编辑。'}
                        </div>
                      )}

                      {!fileLoading && selectedPath && selectedFileIsText && (
                        <textarea
                          value={selectedFileContent}
                          onChange={(e) => {
                            setSelectedFileContent(e.target.value)
                            setSelectedFileDirty(true)
                          }}
                          className="w-full min-h-[300px] px-2 py-2 text-xs font-mono border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          placeholder="文件内容"
                        />
                      )}

                      {!selectedPath && !fileLoading && (
                        <div className="text-xs text-gray-400">选择左侧文件后可在此查看或编辑。</div>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
