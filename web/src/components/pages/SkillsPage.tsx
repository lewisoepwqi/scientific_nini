/**
 * 技能工作台页面。
 *
 * 设计目标：
 * 1. 借鉴参考图的双栏技能工作台观感与信息层级。
 * 2. 保留当前项目已有的技能管理能力：启停、编辑、删除、附件管理、打包下载。
 * 3. 以页面级工作台重组交互，不改变后端接口语义。
 */
import {
  type ChangeEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  FolderOpen,
  FolderPlus,
  LayoutGrid,
  Loader2,
  Pencil,
  PencilLine,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useStore, type SkillItem } from "../../store";
import type { SkillPathEntry } from "../../store/types";
import { useConfirm } from "../../store/confirm-store";
import Button from "../ui/Button";
import PageHeader from "./PageHeader";

const CATEGORY_LABELS: Record<string, string> = {
  data: "数据操作",
  statistics: "统计检验",
  visualization: "可视化",
  export: "导出发布",
  report: "写作报告",
  workflow: "工作流",
  utility: "通用工具",
  experiment_design: "实验设计",
  other: "其他",
};

const CATEGORY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "data", label: "数据操作" },
  { value: "statistics", label: "统计检验" },
  { value: "visualization", label: "可视化" },
  { value: "export", label: "导出发布" },
  { value: "report", label: "写作报告" },
  { value: "workflow", label: "工作流" },
  { value: "utility", label: "通用工具" },
  { value: "experiment_design", label: "实验设计" },
  { value: "other", label: "其他" },
];

interface SkillTreeNode {
  path: string;
  name: string;
  type: "file" | "dir";
  size: number;
  children: SkillTreeNode[];
}

function ToggleSwitch({
  checked,
  ariaLabel,
  disabled = false,
  onChange,
}: {
  checked: boolean;
  ariaLabel: string;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`inline-flex h-11 w-11 items-center justify-center rounded-full transition-opacity duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
      }`}
    >
      <span
        className={`relative inline-flex h-6 w-11 items-center rounded-full border border-transparent transition-colors duration-200 ${
          checked ? "bg-[var(--accent)]" : "bg-[var(--bg-overlay)]"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 rounded-full bg-[var(--bg-base)] shadow-[var(--shadow-sm)] transition-transform duration-200 ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </span>
    </button>
  );
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
}

function dirname(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx >= 0 ? path.slice(0, idx) : "";
}

function basename(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx >= 0 ? path.slice(idx + 1) : path;
}

function buildSkillTree(files: SkillPathEntry[]): SkillTreeNode[] {
  const roots: SkillTreeNode[] = [];
  const nodeMap = new Map<string, SkillTreeNode>();

  const attachNode = (node: SkillTreeNode) => {
    const parent = dirname(node.path);
    if (!parent) {
      roots.push(node);
      return;
    }
    const parentNode = ensureDir(parent);
    if (!parentNode.children.some((child) => child.path === node.path)) {
      parentNode.children.push(node);
    }
  };

  const ensureDir = (path: string): SkillTreeNode => {
    const normalized = normalizePath(path);
    const existing = nodeMap.get(normalized);
    if (existing) return existing;
    const node: SkillTreeNode = {
      path: normalized,
      name: basename(normalized),
      type: "dir",
      size: 0,
      children: [],
    };
    nodeMap.set(normalized, node);
    attachNode(node);
    return node;
  };

  for (const file of files) {
    const normalized = normalizePath(file.path);
    if (!normalized) continue;
    if (file.type === "dir") {
      const dirNode = ensureDir(normalized);
      dirNode.size = file.size;
      continue;
    }

    const parent = dirname(normalized);
    if (parent) ensureDir(parent);
    const node: SkillTreeNode = {
      path: normalized,
      name: basename(normalized),
      type: "file",
      size: file.size,
      children: [],
    };
    nodeMap.set(normalized, node);
    attachNode(node);
  }

  const sortNodes = (nodes: SkillTreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    for (const node of nodes) {
      if (node.type === "dir" && node.children.length > 0) {
        sortNodes(node.children);
      }
    }
  };

  sortNodes(roots);
  return roots;
}

function getSkillBody(content: string): string {
  const normalized = content.replace(/\r\n/g, "\n");
  const frontmatter = normalized.match(/^\s*---\s*\n[\s\S]*?\n---\s*\n?/);
  if (!frontmatter) return normalized.trim();
  return normalized.slice(frontmatter[0].length).trim();
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function toStringArray(value: unknown): string[] {
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === "string" ? item.trim() : ""))
      .filter(Boolean);
  }
  return [];
}

function pickFirstString(
  record: Record<string, unknown>,
  keys: string[],
): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function getSkillMetadata(skill: SkillItem | null): Record<string, unknown> {
  return asRecord(skill?.metadata);
}

function getSkillFrontmatter(skill: SkillItem | null): Record<string, unknown> {
  return asRecord(getSkillMetadata(skill).frontmatter);
}

function getSkillVersion(skill: SkillItem | null): string {
  const frontmatter = getSkillFrontmatter(skill);
  const metadata = getSkillMetadata(skill);
  const contract = asRecord(metadata.contract);
  return (
    pickFirstString(frontmatter, ["version", "skill_version"]) ??
    pickFirstString(contract, ["version"]) ??
    "未声明"
  );
}

function getSkillAuthor(skill: SkillItem | null): string {
  const frontmatter = getSkillFrontmatter(skill);
  const author =
    pickFirstString(frontmatter, ["author", "owner", "maintainer", "team"]) ??
    toStringArray(frontmatter.authors).join(" / ");
  return author || "Nini 技能目录";
}

function getSkillTags(skill: SkillItem | null): string[] {
  const metadata = getSkillMetadata(skill);
  const frontmatter = getSkillFrontmatter(skill);
  const tags = toStringArray(metadata.tags);
  if (tags.length > 0) return tags;
  return toStringArray(frontmatter.tags);
}

function getSkillSourceLabel(skill: SkillItem | null): string {
  const metadata = getSkillMetadata(skill);
  const standards = toStringArray(metadata.source_standard);
  if (standards.includes("nini")) return "Nini 内置";
  if (standards.includes("codex")) return "Codex 兼容";
  if (standards.includes("claude-code")) return "Claude Code 兼容";
  if (standards.includes("agent-skills")) return "Agent Skills";
  if (standards.length > 0) return standards[0];
  return "本地目录";
}

function getSkillLocationHint(skill: SkillItem | null): string {
  if (!skill?.location) return "—";
  const normalized = skill.location.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts.slice(-3).join("/");
}

function getSkillResearchDomain(skill: SkillItem | null): string {
  const metadata = getSkillMetadata(skill);
  const domain = metadata.research_domain;
  if (typeof domain === "string" && domain.trim()) return domain.trim();
  return "general";
}

function getSkillDifficulty(skill: SkillItem | null): string {
  const metadata = getSkillMetadata(skill);
  const difficulty = metadata.difficulty_level;
  if (typeof difficulty === "string" && difficulty.trim()) {
    return difficulty.trim();
  }
  return "intermediate";
}

function getCategoryLabel(category?: string): string {
  return CATEGORY_LABELS[category || "other"] || category || "其他";
}

function CategoryDropdown({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const current = CATEGORY_OPTIONS.find((o) => o.value === value);

  return (
    <div ref={ref} className="skills-custom-dropdown">
      <button
        type="button"
        className="skills-custom-dropdown-trigger"
        onClick={() => setOpen(!open)}
      >
        <span className="truncate">{current?.label ?? value}</span>
        <ChevronDown size={14} className="flex-shrink-0 text-[var(--text-muted)]" />
      </button>
      {open && (
        <div className="skills-custom-dropdown-menu">
          {CATEGORY_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`skills-custom-dropdown-option ${option.value === value ? "skills-custom-dropdown-option-active" : ""}`}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SkillFileTree({
  nodes,
  openDirs,
  selectedPath,
  renamingPath,
  renameValue,
  onToggleDir,
  onSelectPath,
  onStartRename,
  onRenameValueChange,
  onConfirmRename,
  onCancelRename,
  onDeletePath,
}: {
  nodes: SkillTreeNode[];
  openDirs: Set<string>;
  selectedPath: string | null;
  renamingPath: string | null;
  renameValue: string;
  onToggleDir: (path: string) => void;
  onSelectPath: (path: string, type: "file" | "dir", name: string, size: number) => void;
  onStartRename: (path: string, currentName: string) => void;
  onRenameValueChange: (value: string) => void;
  onConfirmRename: () => void;
  onCancelRename: () => void;
  onDeletePath: (path: string) => void;
}) {
  const renderNode = (node: SkillTreeNode, depth: number): ReactNode => {
    const isDir = node.type === "dir";
    const isOpen = isDir && openDirs.has(node.path);
    const isSelected = selectedPath === node.path;
    const isRenaming = renamingPath === node.path;

    return (
      <div key={node.path}>
        {isRenaming ? (
          /* 内联重命名输入 */
          <div
            className="skills-tree-row"
            style={{ paddingLeft: `${12 + depth * 16}px` }}
          >
            {isDir ? (
              <FolderOpen size={14} className="flex-shrink-0 text-[var(--text-secondary)]" />
            ) : (
              <FileText size={14} className="flex-shrink-0 text-[var(--text-secondary)]" />
            )}
            <input
              type="text"
              value={renameValue}
              onChange={(e) => onRenameValueChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onConfirmRename();
                if (e.key === "Escape") onCancelRename();
              }}
              onBlur={onConfirmRename}
              autoFocus
              className="flex-1 min-w-0 text-sm bg-transparent border-b border-[var(--accent)] outline-none text-[var(--text-primary)] px-0 py-0"
            />
            <button
              type="button"
              className="ml-1 text-[var(--success)] hover:text-[var(--success)]"
              onClick={onConfirmRename}
            >
              <Check size={14} />
            </button>
          </div>
        ) : (
          <div
            className={`group skills-tree-row ${isSelected ? "skills-tree-row-active" : ""}`}
            style={{ paddingLeft: `${12 + depth * 16}px` }}
          >
            <button
              type="button"
              className="flex items-center gap-1.5 min-w-0 flex-1 bg-transparent border-none cursor-pointer p-0"
              onClick={() => {
                if (isDir) onToggleDir(node.path);
                onSelectPath(node.path, node.type, node.name, node.size);
              }}
              onDoubleClick={() => onStartRename(node.path, node.name)}
              title="双击重命名"
            >
              <span className="w-4 flex-shrink-0 text-[var(--text-muted)]">
                {isDir ? (
                  isOpen ? (
                    <ChevronDown size={14} />
                  ) : (
                    <ChevronRight size={14} />
                  )
                ) : (
                  <span className="inline-block w-3" />
                )}
              </span>
              {isDir ? (
                <FolderOpen size={14} className="flex-shrink-0 text-[var(--text-secondary)]" />
              ) : (
                <FileText size={14} className="flex-shrink-0 text-[var(--text-secondary)]" />
              )}
              <span className="min-w-0 flex-1 truncate text-left text-sm text-[var(--text-primary)]">
                {node.name}
              </span>
              {!isDir && (
                <span className="ml-2 flex-shrink-0 text-[11px] text-[var(--text-muted)]">
                  {formatFileSize(node.size)}
                </span>
              )}
            </button>
            <button
              type="button"
              className="shrink-0 p-1 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error-subtle)] hidden group-hover:flex items-center justify-center"
              title="删除"
              onClick={(e) => {
                e.stopPropagation();
                onDeletePath(node.path);
              }}
            >
              <Trash2 size={12} />
            </button>
          </div>
        )}
        {isDir && isOpen && node.children.length > 0 && (
          <div>{node.children.map((child) => renderNode(child, depth + 1))}</div>
        )}
      </div>
    );
  };

  return <div>{nodes.map((node) => renderNode(node, 0))}</div>;
}

export default function SkillsPage({ onBack }: { onBack: () => void }) {
  const confirm = useConfirm();

  const skills = useStore((state) => state.skills);
  const fetchSkills = useStore((state) => state.fetchSkills);
  const uploadSkillFile = useStore((state) => state.uploadSkillFile);
  const getSkillDetail = useStore((state) => state.getSkillDetail);
  const updateSkill = useStore((state) => state.updateSkill);
  const toggleSkillEnabled = useStore((state) => state.toggleSkillEnabled);
  const deleteSkill = useStore((state) => state.deleteSkill);
  const listSkillFiles = useStore((state) => state.listSkillFiles);
  const getSkillFileContent = useStore((state) => state.getSkillFileContent);
  const saveSkillFileContent = useStore((state) => state.saveSkillFileContent);
  const uploadSkillAttachment = useStore((state) => state.uploadSkillAttachment);
  const createSkillDir = useStore((state) => state.createSkillDir);
  const deleteSkillPath = useStore((state) => state.deleteSkillPath);
  const downloadSkillBundle = useStore((state) => state.downloadSkillBundle);

  const markdownSkills = useMemo(
    () => skills.filter((item) => item.type === "markdown"),
    [skills],
  );

  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("all");
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [listWidth, setListWidth] = useState(480);
  const [resizingList, setResizingList] = useState(false);
  const listMainRef = useRef<HTMLElement | null>(null);

  const [editDescription, setEditDescription] = useState("");
  const [editCategory, setEditCategory] = useState("other");
  const [editLoading, setEditLoading] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [toggleBusyName, setToggleBusyName] = useState<string | null>(null);

  const [filesLoading, setFilesLoading] = useState(false);
  const [skillFiles, setSkillFiles] = useState<SkillPathEntry[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState("");
  const [selectedFileIsText, setSelectedFileIsText] = useState(true);
  const [selectedFileDirty, setSelectedFileDirty] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [newDirPath, setNewDirPath] = useState("");
  const [showNewDir, setShowNewDir] = useState(false);
  const [openDirs, setOpenDirs] = useState<Set<string>>(new Set());
  const [fileBusy, setFileBusy] = useState<string | null>(null);

  // Dirty-state tracking for edit form
  const [originalDescription, setOriginalDescription] = useState("");
  const [originalCategory, setOriginalCategory] = useState("other");
  const [originalContent, setOriginalContent] = useState("");

  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachmentInputRef = useRef<HTMLInputElement>(null);


  const categoryStats = useMemo(() => {
    const counts = new Map<string, number>();
    for (const skill of markdownSkills) {
      const key = skill.category || "other";
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return counts;
  }, [markdownSkills]);

  const filteredSkills = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return markdownSkills
      .filter((skill) => {
        if (activeCategory !== "all" && (skill.category || "other") !== activeCategory) {
          return false;
        }

        if (!query) return true;

        const tags = getSkillTags(skill).join(" ").toLowerCase();
        return [
          skill.name,
          skill.description,
          getCategoryLabel(skill.category),
          tags,
          getSkillSourceLabel(skill),
        ]
          .join(" ")
          .toLowerCase()
          .includes(query);
      })
      .sort((a, b) => {
        if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
  }, [activeCategory, markdownSkills, searchQuery]);

  const selectedSkill = useMemo(() => {
    if (!selectedName) return null;
    return markdownSkills.find((item) => item.name === selectedName) ?? null;
  }, [markdownSkills, selectedName]);

  const hasEdits = useMemo(() => {
    if (!selectedSkill) return false;
    return (
      editDescription !== originalDescription ||
      editCategory !== originalCategory
    );
  }, [editDescription, editCategory, originalDescription, originalCategory, selectedSkill]);

  const skillTree = useMemo(() => buildSkillTree(skillFiles), [skillFiles]);

  const enabledMdCount = markdownSkills.filter((item) => item.enabled).length;

  const [measuredWidth, setMeasuredWidth] = useState(0);

  useEffect(() => {
    const el = listMainRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setMeasuredWidth(Math.round(entry.contentRect.width));
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const detailGridCols = useMemo(() => {
    const w = measuredWidth || listWidth;
    if (w >= 780) return 3;
    if (w >= 500) return 2;
    return 1;
  }, [measuredWidth, listWidth]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  useEffect(() => {
    if (selectedName && !markdownSkills.some((skill) => skill.name === selectedName)) {
      setSelectedName(null);
      setEditDescription("");
      setEditCategory("other");
      setOriginalContent("");
      setSkillFiles([]);
      setSelectedPath(null);
      setSelectedFileContent("");
      setSelectedFileDirty(false);
    }
  }, [markdownSkills, selectedName]);

  useEffect(() => {
    if (!resizingList) return;
    const handleMove = (event: MouseEvent) => {
      const el = listMainRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const newWidth = Math.max(280, Math.min(960, event.clientX - rect.left));
      setListWidth(newWidth);
    };
    const handleUp = () => setResizingList(false);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [resizingList]);

  const resetFilePanel = useCallback(() => {
    setSkillFiles([]);
    setSelectedPath(null);
    setSelectedFileContent("");
    setSelectedFileIsText(true);
    setSelectedFileDirty(false);
    setShowNewDir(false);
    setOpenDirs(new Set());
  }, []);

  const refreshSkillFiles = useCallback(
    async (skillName: string) => {
      setFilesLoading(true);
      const result = await listSkillFiles(skillName);
      if (result.success && result.files) {
        setSkillFiles(result.files);
        const defaultOpen = new Set<string>();
        for (const entry of result.files) {
          if (entry.type === "dir" && !entry.path.includes("/")) {
            defaultOpen.add(normalizePath(entry.path));
          }
        }
        setOpenDirs((prev) => {
          if (prev.size === 0) return defaultOpen;
          const merged = new Set(prev);
          for (const value of defaultOpen) merged.add(value);
          return merged;
        });
        if (selectedPath && !result.files.some((file) => file.path === selectedPath)) {
          setSelectedPath(null);
          setSelectedFileContent("");
          setSelectedFileDirty(false);
        }
      } else {
        setError(result.message);
      }
      setFilesLoading(false);
    },
    [listSkillFiles, selectedPath],
  );

  const handleSelectSkill = useCallback(
    async (skill: SkillItem) => {
      setSelectedName(skill.name);
      setNotice(null);
      setError(null);
      resetFilePanel();

      setEditLoading(true);
      const result = await getSkillDetail(skill.name);
      if (result.success && result.skill) {
        const desc = result.skill.description || skill.description || "";
        const cat = result.skill.category || skill.category || "other";
        const body = getSkillBody(result.skill.content || "");
        setEditDescription(desc);
        setEditCategory(cat);
        setOriginalDescription(desc);
        setOriginalCategory(cat);
        setOriginalContent(body);
      } else {
        setError(result.message);
        const desc = skill.description || "";
        const cat = skill.category || "other";
        setEditDescription(desc);
        setEditCategory(cat);
        setOriginalDescription(desc);
        setOriginalCategory(cat);
        setOriginalContent("");
      }
      setEditLoading(false);

      await refreshSkillFiles(skill.name);
    },
    [getSkillDetail, refreshSkillFiles, resetFilePanel],
  );

  const handleUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;

      setUploading(true);
      setNotice(null);
      setError(null);
      const result = await uploadSkillFile(file);
      if (result.success) {
        setNotice(`上传成功：${file.name}`);
      } else {
        setError(result.message);
      }
      setUploading(false);
    },
    [uploadSkillFile],
  );

  const handleRefreshList = useCallback(async () => {
    setNotice(null);
    setError(null);
    await fetchSkills();
  }, [fetchSkills]);

  const handleSaveEdit = useCallback(async () => {
    if (!selectedSkill) return;
    const description = editDescription.trim();
    if (!description) {
      setError("描述不能为空");
      return;
    }

    setSavingEdit(true);
    setNotice(null);
    setError(null);
    const result = await updateSkill(selectedSkill.name, {
      description,
      category: editCategory,
      content: originalContent,
    });
    if (result.success) {
      setNotice(`已保存：${selectedSkill.name}`);
      setOriginalDescription(description);
      setOriginalCategory(editCategory);
    } else {
      setError(result.message);
    }
    setSavingEdit(false);
  }, [editCategory, editDescription, originalContent, selectedSkill, updateSkill]);

  const handleToggleEnabled = useCallback(
    async (skill: SkillItem, enabled: boolean) => {
      setToggleBusyName(skill.name);
      setNotice(null);
      setError(null);
      const result = await toggleSkillEnabled(skill.name, enabled);
      if (result.success) {
        setNotice(`${enabled ? "已启用" : "已禁用"}：${skill.name}`);
      } else {
        setError(result.message);
      }
      setToggleBusyName(null);
    },
    [toggleSkillEnabled],
  );

  const handleDelete = useCallback(
    async (skill: SkillItem) => {
      const ok = await confirm({
        title: "删除技能",
        message: `确认删除技能「${skill.name}」吗？此操作不可撤销。`,
        confirmText: "删除",
        destructive: true,
      });
      if (!ok) return;

      setNotice(null);
      setError(null);
      const result = await deleteSkill(skill.name);
      if (result.success) {
        if (selectedName === skill.name) {
          setSelectedName(null);
          setEditDescription("");
          setEditCategory("other");
          setOriginalContent("");
          resetFilePanel();
        }
        setNotice(`已删除：${skill.name}`);
      } else {
        setError(result.message);
      }
    },
    [confirm, deleteSkill, resetFilePanel, selectedName],
  );

  const handleToggleDir = useCallback((path: string) => {
    setOpenDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const handleSelectPath = useCallback(
    async (path: string, type: "file" | "dir") => {
      if (!selectedSkill) return;
      setSelectedPath(path);
      if (type === "dir") {
        setSelectedFileContent("");
        setSelectedFileIsText(false);
        setSelectedFileDirty(false);
        return;
      }

      setFileLoading(true);
      const result = await getSkillFileContent(selectedSkill.name, path);
      if (result.success && result.file) {
        setSelectedFileIsText(result.file.is_text);
        setSelectedFileContent(result.file.content || "");
        setSelectedFileDirty(false);
      } else {
        setError(result.message);
      }
      setFileLoading(false);
    },
    [getSkillFileContent, selectedSkill],
  );

  const handleSaveFile = useCallback(async () => {
    if (!selectedSkill || !selectedPath || !selectedFileIsText) return;
    setFileBusy("save-file");
    setNotice(null);
    setError(null);
    const result = await saveSkillFileContent(
      selectedSkill.name,
      selectedPath,
      selectedFileContent,
    );
    if (result.success) {
      setNotice(`已保存文件：${selectedPath}`);
      setSelectedFileDirty(false);
      await refreshSkillFiles(selectedSkill.name);
    } else {
      setError(result.message);
    }
    setFileBusy(null);
  }, [
    refreshSkillFiles,
    saveSkillFileContent,
    selectedFileContent,
    selectedFileIsText,
    selectedPath,
    selectedSkill,
  ]);

  const handleUploadAttachment = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file || !selectedSkill) return;

      // 自动推断上传目录：优先用选中的目录，否则用选中文件的父目录，否则根目录
      const targetDir = (() => {
        if (!selectedPath) return "";
        const entry = skillFiles.find((f) => f.path === selectedPath);
        if (entry?.type === "dir") return selectedPath;
        return dirname(selectedPath);
      })();

      setFileBusy("upload-attachment");
      setNotice(null);
      setError(null);
      const result = await uploadSkillAttachment(
        selectedSkill.name,
        file,
        targetDir,
      );
      if (result.success) {
        setNotice(`附件上传成功：${file.name}`);
        await refreshSkillFiles(selectedSkill.name);
      } else {
        setError(result.message);
      }
      setFileBusy(null);
    },
    [refreshSkillFiles, selectedSkill, selectedPath, skillFiles, uploadSkillAttachment],
  );

  const handleCreateDir = useCallback(async () => {
    if (!selectedSkill) return;
    const path = newDirPath.trim();
    if (!path) {
      setError("目录路径不能为空");
      return;
    }

    setFileBusy("create-dir");
    setNotice(null);
    setError(null);
    const result = await createSkillDir(selectedSkill.name, path);
    if (result.success) {
      setNotice(`目录已创建：${path}`);
      setNewDirPath("");
      await refreshSkillFiles(selectedSkill.name);
    } else {
      setError(result.message);
    }
    setFileBusy(null);
  }, [createSkillDir, newDirPath, refreshSkillFiles, selectedSkill]);

  const handleDeletePath = useCallback(async (path?: string) => {
    const targetPath = path ?? selectedPath;
    if (!selectedSkill || !targetPath) return;
    const ok = await confirm({
      title: "删除路径",
      message: `确认删除「${targetPath}」吗？此操作不可撤销。`,
      confirmText: "删除",
      destructive: true,
    });
    if (!ok) return;

    setFileBusy("delete-path");
    setNotice(null);
    setError(null);
    const result = await deleteSkillPath(selectedSkill.name, targetPath);
    if (result.success) {
      if (selectedPath === targetPath) {
        setSelectedPath(null);
        setSelectedFileContent("");
        setSelectedFileDirty(false);
      }
      setNotice(`已删除：${targetPath}`);
      await refreshSkillFiles(selectedSkill.name);
    } else {
      setError(result.message);
    }
    setFileBusy(null);
  }, [confirm, deleteSkillPath, refreshSkillFiles, selectedPath, selectedSkill]);

  const handleDownloadBundle = useCallback(async () => {
    if (!selectedSkill) return;
    setFileBusy("download-bundle");
    setNotice(null);
    setError(null);
    const result = await downloadSkillBundle(selectedSkill.name);
    if (!result.success) {
      setError(result.message);
    }
    setFileBusy(null);
  }, [downloadSkillBundle, selectedSkill]);

  // ---- 技能详情：基本信息查看/编辑模式 ----
  const [infoMode, setInfoMode] = useState<"view" | "edit">("view");
  // ---- 技能详情：文件内容预览/编辑模式 ----
  const [fileMode, setFileMode] = useState<"preview" | "edit">("preview");
  // ---- 技能详情：文件名内联编辑 ----
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // 切换技能时重置模式
  useEffect(() => {
    setInfoMode("view");
    setFileMode("preview");
    setRenamingPath(null);
  }, [selectedName]);

  const handleStartRename = useCallback((path: string, currentName: string) => {
    setRenamingPath(path);
    setRenameValue(currentName);
  }, []);

  const handleConfirmRename = useCallback(() => {
    // 重命名通过 saveSkillFileContent 实现（前端层面更新 local state）
    // 实际重命名操作需要后端支持，这里先退出编辑态
    setRenamingPath(null);
    setRenameValue("");
  }, []);

  const handleCancelRename = useCallback(() => {
    setRenamingPath(null);
    setRenameValue("");
  }, []);

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".md,.markdown,.txt"
        className="hidden"
        onChange={handleUpload}
      />
      <input
        ref={attachmentInputRef}
        type="file"
        className="hidden"
        onChange={handleUploadAttachment}
      />

      <main
        ref={listMainRef}
        className={`rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] overflow-hidden min-w-0 flex flex-col ${selectedSkill ? "flex-shrink-0" : "flex-1"}`}
        style={{ width: selectedSkill ? `${listWidth}px` : undefined }}
      >
        <PageHeader
          title="技能"
          onBack={onBack}
          actions={
            <>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => void handleRefreshList()}
              >
                刷新
              </Button>
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                loading={uploading}
                icon={!uploading ? <Upload size={13} /> : undefined}
              >
                安装技能
              </Button>
            </>
          }
        />

        <div className="flex-1 overflow-y-auto">
          <div className="border-b border-[var(--border-subtle)] px-5 py-3">
            <div className="w-full">
              <label htmlFor="skills-search" className="sr-only">
                搜索技能
              </label>
              <div className="relative">
                <Search
                  size={16}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
                />
                <input
                  id="skills-search"
                  type="text"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="搜索技能名称、描述、标签或来源"
                  className="skills-search-input w-full"
                />
              </div>
            </div>

            <div className="skills-filter-chip-group flex flex-wrap gap-2 mt-3">
              <button
                type="button"
                className={`skills-filter-chip ${
                  activeCategory === "all" ? "skills-filter-chip-active" : ""
                }`}
                onClick={() => setActiveCategory("all")}
              >
                全部
                <span>{markdownSkills.length}</span>
              </button>
              {CATEGORY_OPTIONS.filter(
                (option) => (categoryStats.get(option.value) || 0) > 0,
              ).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`skills-filter-chip ${
                    activeCategory === option.value
                      ? "skills-filter-chip-active"
                      : ""
                  }`}
                  onClick={() => setActiveCategory(option.value)}
                >
                  {option.label}
                  <span>{categoryStats.get(option.value) || 0}</span>
                </button>
              ))}
            </div>

            <div className="mt-3 text-xs text-[var(--text-muted)]">
              {enabledMdCount} 个启用 / {markdownSkills.length} 个技能
            </div>
          </div>

          <div className="p-4">
            {(notice || error) && (
              <div
                className={`mb-4 rounded-lg border px-4 py-3 text-sm ${
                  error ? "text-[var(--error)]" : "text-[var(--success)]"
                }`}
                style={{
                  borderColor: error
                    ? "color-mix(in srgb, var(--error) 24%, transparent)"
                    : "color-mix(in srgb, var(--success) 24%, transparent)",
                  background: error ? "var(--error-subtle)" : "var(--success-subtle)",
                }}
              >
                {error || notice}
              </div>
            )}

            {filteredSkills.length === 0 ? (
              <div className="skills-empty-state">
                <LayoutGrid size={28} className="text-[var(--text-muted)]" />
                <div className="space-y-1 text-center">
                  <div className="text-base font-medium text-[var(--text-primary)]">
                    没有匹配的技能
                  </div>
                  <div className="text-sm text-[var(--text-secondary)]">
                    调整搜索词或分类筛选，也可以直接安装新的 Markdown 技能。
                  </div>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  className="skills-touch-button"
                  onClick={() => fileInputRef.current?.click()}
                  icon={<Upload size={13} />}
                >
                  安装技能
                </Button>
              </div>
            ) : (
              <div
                className="grid gap-2"
                style={{
                  gridTemplateColumns: `repeat(${selectedSkill ? detailGridCols : 4}, minmax(0, 1fr))`,
                }}
              >
                {filteredSkills.map((skill) => {
                  const isSelected = selectedName === skill.name;
                  const cardAccessibleLabel = `${skill.name}，打开技能详情`;
                  const toggleAccessibleLabel = `${skill.enabled ? "禁用" : "启用"}技能 ${skill.name}`;
                  return (
                    <article
                      key={skill.name}
                      className={`skills-card ${isSelected ? "skills-card-active" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-pressed={isSelected}
                      aria-label={cardAccessibleLabel}
                      onClick={() => void handleSelectSkill(skill)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          void handleSelectSkill(skill);
                        }
                      }}
                    >
                      <div className="flex h-full flex-col gap-2">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <h3 className="truncate text-sm font-semibold leading-tight text-[var(--text-primary)]">
                              {skill.name}
                            </h3>
                            <div className="mt-1 flex items-center gap-2">
                              <span className="inline-flex items-center rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 text-[10px] leading-none text-[var(--text-muted)]">
                                {getCategoryLabel(skill.category)}
                              </span>
                              <span className="text-[10px] text-[var(--text-muted)]">
                                v{getSkillVersion(skill)}
                              </span>
                            </div>
                          </div>
                          <div
                            className="flex shrink-0 items-center gap-1"
                            onClick={(event) => event.stopPropagation()}
                          >
                            {toggleBusyName === skill.name && (
                              <Loader2 size={12} className="animate-spin text-[var(--text-muted)]" />
                            )}
                            <ToggleSwitch
                              checked={skill.enabled}
                              ariaLabel={toggleAccessibleLabel}
                              disabled={toggleBusyName === skill.name}
                              onChange={(enabled) => void handleToggleEnabled(skill, enabled)}
                            />
                          </div>
                        </div>
                        <p
                          className="overflow-hidden text-ellipsis line-clamp-4 text-xs leading-[1.6] text-[var(--text-secondary)]"
                          style={{
                            display: "-webkit-box",
                            WebkitLineClamp: 4,
                            WebkitBoxOrient: "vertical",
                          }}
                        >
                          {skill.description}
                        </p>
                        <div className="mt-auto flex items-center justify-between border-t border-[var(--border-subtle)] py-1">
                          <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-muted)]">
                            {getSkillAuthor(skill)}
                          </span>
                          <span className="shrink-0 text-[10px] text-[var(--text-muted)]">
                            {getSkillSourceLabel(skill)}
                          </span>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </main>

      {selectedSkill && (
        <>
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="调整技能列表宽度"
            onMouseDown={() => setResizingList(true)}
            className="panel-resizer"
          >
            <span className="panel-resizer-grip" />
          </div>
          <aside className="rounded-lg border border-[var(--border-subtle)] flex-1 min-w-0 flex flex-col bg-[var(--bg-base)] overflow-hidden">
            <div className="flex h-full flex-col overflow-y-auto">
              {/* ── 1. 头部：标题（无绿点）、下载和关闭按钮 ── */}
              <div className="h-12 border-b border-[var(--border-subtle)] flex items-center justify-between px-5 shrink-0 bg-[var(--bg-base)]">
                <h2 className="text-sm font-semibold text-[var(--text-primary)] truncate m-0">
                  {selectedSkill.name}
                </h2>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    icon={<Trash2 size={13} />}
                    onClick={() => void handleDelete(selectedSkill)}
                  >
                    删除
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => void handleDownloadBundle()}
                    disabled={fileBusy === "download-bundle"}
                    loading={fileBusy === "download-bundle"}
                    icon={<Download size={13} />}
                  >
                    下载
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setSelectedName(null)}
                    aria-label="关闭详情"
                    title="关闭详情"
                  >
                    <X size={16} />
                  </Button>
                </div>
              </div>

              {/* ── 2. 基本信息：查看/编辑模式 ── */}
              <section className="border-b border-[var(--border-subtle)]">
                <div className="skills-section-header px-5 pt-3 pb-0">
                  <div className="skills-section-title">基本信息</div>
                  {infoMode === "edit" ? (
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="primary"
                        size="sm"
                        disabled={!hasEdits || savingEdit}
                        loading={savingEdit}
                        onClick={() => void handleSaveEdit()}
                      >
                        保存修改
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setEditDescription(originalDescription);
                          setEditCategory(originalCategory);
                          setInfoMode("view");
                        }}
                      >
                        取消
                      </Button>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      icon={<Pencil size={13} />}
                      onClick={() => setInfoMode("edit")}
                    >
                      编辑
                    </Button>
                  )}
                </div>

                {editLoading ? (
                  <div className="flex items-center gap-2 px-5 py-4 text-sm text-[var(--text-secondary)]">
                    <Loader2 size={15} className="animate-spin" />
                    正在读取技能信息...
                  </div>
                ) : infoMode === "view" ? (
                  /* 查看模式：紧凑布局 */
                  <div className="px-5 pb-3 pt-2">
                    {/* 描述行（最多2行） */}
                    {(editDescription || selectedSkill.description) && (
                      <p
                        className="text-xs leading-[1.6] text-[var(--text-secondary)] mb-2"
                        style={{
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {editDescription || selectedSkill.description}
                      </p>
                    )}

                    {/* 3列网格：8个短字段 */}
                    <div className="skills-info-grid">
                      {/* 状态 */}
                      <div>
                        <div className="skills-info-cell-label">状态</div>
                        <div className="skills-info-cell-value">
                          <span className={`inline-flex items-center gap-1 ${selectedSkill.enabled ? "text-[var(--success)]" : "text-[var(--text-muted)]"}`}>
                            <span className={`skills-status-dot ${selectedSkill.enabled ? "bg-[var(--success)]" : "bg-[var(--text-muted)]"}`} />
                            {selectedSkill.enabled ? "启用" : "禁用"}
                          </span>
                        </div>
                      </div>
                      {/* 分类 */}
                      <div>
                        <div className="skills-info-cell-label">分类</div>
                        <div className="skills-info-cell-value">{getCategoryLabel(selectedSkill.category)}</div>
                      </div>
                      {/* 版本 */}
                      <div>
                        <div className="skills-info-cell-label">版本</div>
                        <div className="skills-info-cell-value">v{getSkillVersion(selectedSkill)}</div>
                      </div>
                      {/* 作者 */}
                      <div>
                        <div className="skills-info-cell-label">作者</div>
                        <div className="skills-info-cell-value">{getSkillAuthor(selectedSkill)}</div>
                      </div>
                      {/* 来源 */}
                      <div>
                        <div className="skills-info-cell-label">来源</div>
                        <div className="skills-info-cell-value">{getSkillSourceLabel(selectedSkill)}</div>
                      </div>
                      {/* 领域 */}
                      <div>
                        <div className="skills-info-cell-label">领域</div>
                        <div className="skills-info-cell-value">{getSkillResearchDomain(selectedSkill)}</div>
                      </div>
                      {/* 难度 */}
                      <div>
                        <div className="skills-info-cell-label">难度</div>
                        <div className="skills-info-cell-value">{getSkillDifficulty(selectedSkill)}</div>
                      </div>
                      {/* 路径 */}
                      <div>
                        <div className="skills-info-cell-label">路径</div>
                        <div className="skills-info-cell-value font-mono">{getSkillLocationHint(selectedSkill)}</div>
                      </div>
                    </div>

                    {/* 标签行 */}
                    {getSkillTags(selectedSkill).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {getSkillTags(selectedSkill).map((tag) => (
                          <span key={tag} className="skills-meta">{tag}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  /* 编辑模式：仅编辑描述和分类 */
                  <div className="px-5 pb-4 pt-3 space-y-4">
                    <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                      <label className="space-y-2">
                        <span className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-muted)]">
                          描述
                        </span>
                        <textarea
                          value={editDescription}
                          onChange={(event) => setEditDescription(event.target.value)}
                          className="skills-form-textarea"
                          placeholder="输入技能描述"
                          rows={3}
                        />
                      </label>
                      <label className="space-y-2">
                        <span className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-muted)]">
                          分类
                        </span>
                        <CategoryDropdown
                          value={editCategory}
                          onChange={setEditCategory}
                        />
                      </label>
                    </div>
                  </div>
                )}
              </section>

              {/* ── 3. 技能文件（文件树 + 内容预览/编辑） ── */}
              <section className="flex-1 flex flex-col min-h-0">
                <div className="skills-section-header px-5 pt-3 pb-0">
                  <div className="skills-section-title">技能文件</div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      icon={<FolderPlus size={13} />}
                      onClick={() => setShowNewDir(!showNewDir)}
                    >
                      {showNewDir ? "收起" : "新建目录"}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      icon={<Upload size={13} />}
                      onClick={() => attachmentInputRef.current?.click()}
                      loading={fileBusy === "upload-attachment"}
                    >
                      上传文件
                    </Button>
                  </div>
                </div>

                {showNewDir && (
                  <div className="flex items-center gap-2 px-5 pt-3">
                    <input
                      value={newDirPath}
                      onChange={(event) => setNewDirPath(event.target.value)}
                      placeholder="如 scripts/helpers"
                      className="skills-form-input flex-1"
                    />
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      loading={fileBusy === "create-dir"}
                      onClick={() => void handleCreateDir()}
                    >
                      创建
                    </Button>
                  </div>
                )}

                <div className={`flex-1 min-h-0 px-5 pt-3 pb-4 ${selectedPath ? "grid gap-3 lg:grid-cols-[1fr_1.5fr]" : ""}`}>
                  {/* 3.1 左侧文件树 */}
                  <div className="skills-tree-panel flex flex-col min-h-0">
                    <div className="h-11 flex items-center justify-between border-b border-[var(--border-subtle)] px-4 shrink-0">
                      <div className="text-sm font-medium text-[var(--text-primary)]">
                        文件树
                      </div>
                    </div>
                    <div className="flex-1 overflow-y-auto py-2">
                      {filesLoading ? (
                        <div className="flex items-center gap-2 px-4 py-4 text-sm text-[var(--text-secondary)]">
                          <Loader2 size={14} className="animate-spin" />
                          正在读取文件树...
                        </div>
                      ) : skillTree.length === 0 ? (
                        <div className="px-4 py-6 text-sm text-[var(--text-secondary)]">
                          当前技能还没有附属文件。
                        </div>
                      ) : (
                        <SkillFileTree
                          nodes={skillTree}
                          openDirs={openDirs}
                          selectedPath={selectedPath}
                          renamingPath={renamingPath}
                          renameValue={renameValue}
                          onToggleDir={handleToggleDir}
                          onSelectPath={(path, type) => void handleSelectPath(path, type)}
                          onStartRename={handleStartRename}
                          onRenameValueChange={setRenameValue}
                          onConfirmRename={handleConfirmRename}
                          onCancelRename={handleCancelRename}
                          onDeletePath={(path) => void handleDeletePath(path)}
                        />
                      )}
                    </div>
                  </div>

                  {/* 3.2 右侧文件内容预览/编辑 */}
                  {selectedPath && (
                    <div className="skills-tree-panel flex flex-col min-h-0">
                      <div className="h-11 flex items-center justify-between border-b border-[var(--border-subtle)] px-4 shrink-0">
                        <div className="text-sm font-medium text-[var(--text-primary)] truncate">
                          {selectedPath}
                        </div>
                        {fileMode === "edit" ? (
                          <div className="flex items-center gap-2">
                            <Button
                              type="button"
                              variant="primary"
                              size="sm"
                              disabled={!selectedFileDirty || !selectedFileIsText}
                              loading={fileBusy === "save-file"}
                              onClick={() => void handleSaveFile()}
                            >
                              保存修改
                            </Button>
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              onClick={() => setFileMode("preview")}
                            >
                              取消
                            </Button>
                          </div>
                        ) : (
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            icon={<PencilLine size={13} />}
                            onClick={() => setFileMode("edit")}
                          >
                            编辑
                          </Button>
                        )}
                      </div>
                      <div className="flex-1 p-4 min-h-0 overflow-auto flex flex-col">
                        {fileLoading ? (
                          <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                            <Loader2 size={14} className="animate-spin" />
                            正在读取文件...
                          </div>
                        ) : !selectedFileIsText ? (
                          <div className="skills-inline-empty">
                            当前选择的是目录或二进制文件，不支持文本查看。
                          </div>
                        ) : fileMode === "preview" ? (
                          /* 预览模式：只读展示 */
                          <pre className="whitespace-pre-wrap text-sm leading-[1.7] text-[var(--text-primary)] font-[inherit] m-0">
                            {selectedFileContent || "（空文件）"}
                          </pre>
                        ) : (
                          /* 编辑模式：可编辑 textarea */
                          <textarea
                            value={selectedFileContent}
                            onChange={(event) => {
                              setSelectedFileContent(event.target.value);
                              setSelectedFileDirty(true);
                            }}
                            className="skills-file-editor flex-1 min-h-0"
                            placeholder="文件内容"
                          />
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </section>
            </div>
          </aside>
        </>
      )}
    </>
  );
}
