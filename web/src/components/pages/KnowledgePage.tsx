/**
 * 知识库独立页面 —— 双栏布局（文档列表 + 预览区）
 *
 * 左侧：搜索框 + 上传按钮 + 可拖拽上传的文档列表
 * 右侧：选中文档的详情预览（信息 + 操作按钮）
 * 拖拽手柄分隔左右两栏（pill 样式，与 MemoryPanel 一致）
 */
import { useState, useCallback, useRef, useEffect } from "react";
import {
  Upload,
  Trash2,
  FileText,
  Search,
  Loader2,
  AlertCircle,
  RefreshCw,
  File,
  FileSpreadsheet,
  FileImage,
  Database,
} from "lucide-react";
import { useConfirm } from "../../store/confirm-store";
import Button from "../ui/Button";
import PageHeader from "./PageHeader";

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

/** 知识库文档 */
interface KnowledgeDocument {
  id: string;
  title: string;
  file_type: string;
  file_size: number;
  index_status: "indexed" | "indexing" | "failed" | "pending";
  created_at?: string;
  chunk_count?: number;
}

/** 索引状态概览 */
interface IndexStatus {
  vector_store_available: boolean;
  document_count: number;
  status_breakdown: {
    indexed: number;
    indexing: number;
    failed: number;
    pending: number;
  };
}

// ---------------------------------------------------------------------------
// 子组件：索引状态标签
// ---------------------------------------------------------------------------

function IndexStatusBadge({ status }: { status: KnowledgeDocument["index_status"] }) {
  const styles = {
    indexed: "bg-[var(--accent-subtle)] text-[var(--success)]",
    indexing: "bg-[var(--accent-subtle)] text-[var(--warning)]",
    failed: "bg-[var(--accent-subtle)] text-[var(--error)]",
    pending:
      "bg-[var(--bg-elevated)] text-[var(--text-secondary)] dark:bg-[var(--bg-overlay)] dark:text-[var(--text-muted)]",
  };

  const labels = {
    indexed: "已索引",
    indexing: "索引中",
    failed: "失败",
    pending: "待处理",
  };

  return (
    <span className={`px-1.5 py-0.5 rounded text-xs ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// 子组件：文件类型图标
// ---------------------------------------------------------------------------

/** 根据文件类型返回对应图标 */
function FileTypeIcon({ fileType }: { fileType: string }) {
  const ext = fileType.toLowerCase();
  if (ext === "pdf") return <FileText className="w-4 h-4 text-[var(--error)] flex-shrink-0" />;
  if (["doc", "docx"].includes(ext))
    return <FileText className="w-4 h-4 text-[var(--accent)] flex-shrink-0" />;
  if (["xls", "xlsx", "csv"].includes(ext))
    return <FileSpreadsheet className="w-4 h-4 text-[var(--success)] flex-shrink-0" />;
  if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext))
    return <FileImage className="w-4 h-4 text-[var(--warning)] flex-shrink-0" />;
  if (["json", "db", "sqlite"].includes(ext))
    return <Database className="w-4 h-4 text-[var(--text-secondary)] flex-shrink-0" />;
  return <File className="w-4 h-4 text-[var(--text-muted)] flex-shrink-0" />;
}

// ---------------------------------------------------------------------------
// 子组件：上传对话框
// ---------------------------------------------------------------------------

interface UploadDialogProps {
  onClose: () => void;
  onUpload: (file: File, title?: string) => void;
  uploading: boolean;
}

function UploadDialog({ onClose, onUpload, uploading }: UploadDialogProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      if (!title) {
        setTitle(file.name.replace(/\.[^/.]+$/, ""));
      }
    }
  };

  const handleSubmit = () => {
    if (selectedFile) {
      onUpload(selectedFile, title || undefined);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-[var(--bg-base)] rounded-xl shadow-xl w-80 p-4">
        <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-4">上传文档</h3>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
              选择文件
            </label>
            <input
              type="file"
              accept=".txt,.md,.pdf,.doc,.docx,.csv,.json"
              onChange={handleFileChange}
              className="block w-full text-sm text-[var(--text-muted)] file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-[var(--accent-subtle)] file:text-[var(--accent)] hover:file:bg-[var(--accent-subtle)]"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
              标题（可选）
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="文档标题"
              className="w-full px-3 py-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)]"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="secondary"
            type="button"
            onClick={onClose}
            disabled={uploading}
            className="px-4 py-2 text-sm"
          >
            取消
          </Button>
          <Button
            variant="primary"
            type="button"
            onClick={handleSubmit}
            disabled={!selectedFile || uploading}
            loading={uploading}
            className="px-4 py-2 text-sm rounded-lg flex items-center gap-2"
          >
            上传
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/** 格式化文件大小 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** 格式化日期 */
function formatDate(dateStr?: string): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

interface Props {
  onBack: () => void;
}

export default function KnowledgePage({ onBack }: Props) {
  const confirm = useConfirm();

  // ---- 数据状态 ----
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [, setIndexStatus] = useState<IndexStatus | null>(null);

  // ---- 拖拽分栏状态 ----
  const leftPanelRef = useRef<HTMLDivElement>(null);
  const [leftWidth, setLeftWidth] = useState(360);
  const isDragging = useRef(false);

  // ---- 拖拽上传状态 ----
  const [isDragOver, setIsDragOver] = useState(false);

  // ---- 初始化加载数据 ----
  useEffect(() => {
    fetchDocuments();
    fetchIndexStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- API：获取文档列表 ----
  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const resp = await fetch("/api/knowledge/documents");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setDocuments(data || []);
    } catch (e) {
      console.error("获取文档列表失败:", e);
      setError("获取文档列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // ---- API：获取索引状态 ----
  const fetchIndexStatus = useCallback(async () => {
    try {
      const resp = await fetch("/api/knowledge/index/status");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setIndexStatus(data);
    } catch (e) {
      console.error("获取索引状态失败:", e);
    }
  }, []);

  // ---- 操作：上传文档 ----
  const handleUpload = async (file: File, title?: string) => {
    try {
      setUploading(true);
      setError(null);

      const formData = new FormData();
      formData.append("file", file);
      if (title) formData.append("title", title);
      formData.append("domain", "general");

      const resp = await fetch("/api/knowledge/documents", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      await fetchDocuments();
      setShowUploadDialog(false);
    } catch (e) {
      console.error("上传文档失败:", e);
      setError("上传文档失败");
    } finally {
      setUploading(false);
    }
  };

  // ---- 操作：删除文档 ----
  const handleDelete = async (docId: string) => {
    const ok = await confirm({
      title: "删除文档",
      message: "确定要删除这个文档吗？删除后需要重新上传。",
      confirmText: "删除",
      destructive: true,
    });
    if (!ok) return;

    try {
      setError(null);
      const resp = await fetch(`/api/knowledge/documents/${docId}`, {
        method: "DELETE",
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      // 如果删除的是当前选中文档，清空选中状态
      if (selectedDocId === docId) {
        setSelectedDocId(null);
      }
      await fetchDocuments();
    } catch (e) {
      console.error("删除文档失败:", e);
      setError("删除文档失败");
    }
  };

  // ---- 操作：重建索引 ----
  const handleRebuildIndex = async (docId?: string) => {
    const ok = await confirm({
      title: "重建索引",
      message: docId
        ? "确定要为此文档重建索引吗？"
        : "重建所有索引可能需要一些时间，确定继续吗？",
      confirmText: "重建",
    });
    if (!ok) return;

    try {
      setRebuilding(true);
      setError(null);

      const url = docId
        ? `/api/knowledge/documents/${docId}/reindex`
        : "/api/knowledge/index/rebuild";
      const resp = await fetch(url, { method: "POST" });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const data = await resp.json();
      if (data.success) {
        await fetchDocuments();
        await fetchIndexStatus();
      } else {
        setError("索引重建失败");
      }
    } catch (e) {
      console.error("重建索引失败:", e);
      setError("重建索引失败");
    } finally {
      setRebuilding(false);
    }
  };

  // ---- 拖拽分栏：鼠标事件 ----
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const handleMove = (ev: MouseEvent) => {
      if (!isDragging.current) return;
      // 限制左侧宽度范围：240 ~ 600
      const newWidth = Math.max(240, Math.min(600, ev.clientX));
      setLeftWidth(newWidth);
    };

    const handleUp = () => {
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
    };

    document.addEventListener("mousemove", handleMove);
    document.addEventListener("mouseup", handleUp);
  }, []);

  // ---- 拖拽上传：文件拖入/拖出/放下 ----
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        handleUpload(files[0]);
      }
    },
    [handleUpload],
  );

  // ---- 过滤文档列表 ----
  const filteredDocuments = documents.filter((doc) =>
    doc.title.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  // ---- 当前选中的文档 ----
  const selectedDoc = selectedDocId
    ? documents.find((d) => d.id === selectedDocId) ?? null
    : null;

  // ---- 渲染 ----
  return (
    <div className="h-full flex flex-col">
      {/* 顶栏 */}
      <PageHeader
        title="知识库"
        onBack={onBack}
        actions={
          <Button
            variant="primary"
            type="button"
            size="sm"
            onClick={() => setShowUploadDialog(true)}
            icon={<Upload size={13} />}
          >
            上传文档
          </Button>
        }
      />

      {/* 错误提示 */}
      {error && (
        <div className="mx-4 mt-3 p-3 rounded-lg bg-[var(--accent-subtle)] border border-[var(--error)] flex items-center gap-2 text-sm text-[var(--error)]">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* 双栏主体 */}
      <div className="flex-1 flex overflow-hidden">
        {/* ========== 左侧：文档列表 ========== */}
        <div
          ref={leftPanelRef}
          style={{ width: leftWidth, minWidth: leftWidth }}
          className="flex flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-base)] overflow-hidden"
        >
          {/* 搜索框 */}
          <div className="p-3 flex-shrink-0">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
              <input
                type="text"
                placeholder="搜索文档..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="搜索文档"
                className="w-full pl-9 pr-4 py-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </div>
          </div>

          {/* 文档列表（支持拖拽上传） */}
          <div
            className="flex-1 overflow-y-auto px-3 pb-3"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {/* 拖拽上传高亮蒙层 */}
            {isDragOver && (
              <div className="absolute inset-0 z-10 bg-[var(--accent-subtle)] border-2 border-dashed border-[var(--accent)] rounded-lg flex items-center justify-center pointer-events-none">
                <div className="text-center">
                  <Upload className="w-8 h-8 mx-auto mb-2 text-[var(--accent)]" />
                  <p className="text-sm text-[var(--accent)]">拖放文件以上传</p>
                </div>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center h-32 text-[var(--text-secondary)]">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                加载中...
              </div>
            ) : filteredDocuments.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-[var(--text-secondary)]">
                <FileText className="w-10 h-10 mb-2 opacity-40" />
                <p className="text-sm">
                  {searchQuery ? "未找到匹配的文档" : "暂无文档"}
                </p>
                {!searchQuery && (
                  <Button
                    variant="ghost"
                    type="button"
                    onClick={() => setShowUploadDialog(true)}
                    className="mt-2 text-sm text-[var(--accent)]"
                  >
                    上传第一个文档
                  </Button>
                )}
              </div>
            ) : (
              <div className="space-y-1.5">
                {filteredDocuments.map((doc) => (
                  <div
                    key={doc.id}
                    onClick={() => setSelectedDocId(doc.id)}
                    className={`
                      p-3 rounded-lg border cursor-pointer transition-colors
                      ${
                        selectedDocId === doc.id
                          ? "border-[var(--accent)] bg-[var(--accent-subtle)]"
                          : "border-[var(--border-default)] hover:border-[var(--border-default)] hover:bg-[var(--bg-hover)]"
                      }
                    `}
                  >
                    {/* 第一行：图标 + 文件名 */}
                    <div className="flex items-center gap-2 min-w-0">
                      <FileTypeIcon fileType={doc.file_type} />
                      <span className="font-medium text-sm text-[var(--text-primary)] truncate">
                        {doc.title}
                      </span>
                    </div>
                    {/* 第二行：状态 + 大小 + 日期 */}
                    <div className="mt-1.5 flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
                      <IndexStatusBadge status={doc.index_status} />
                      <span>{formatFileSize(doc.file_size)}</span>
                      <span className="text-[var(--text-muted)]">·</span>
                      <span>{formatDate(doc.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 底部统计 */}
          <div className="px-4 py-2 text-[11px] text-[var(--text-muted)] flex items-center justify-between border-t border-[var(--border-subtle)] flex-shrink-0">
            <span>{documents.length} 个文档</span>
            <Button
              variant="ghost"
              type="button"
              onClick={() => handleRebuildIndex()}
              disabled={rebuilding}
              className="h-7 px-2 text-[11px] text-[var(--text-secondary)]"
              title="重建全部索引"
            >
              {rebuilding ? (
                <Loader2 size={12} className="animate-spin mr-1" />
              ) : (
                <RefreshCw size={12} className="mr-1" />
              )}
              重建索引
            </Button>
          </div>
        </div>

        {/* ========== 拖拽手柄（pill 样式） ========== */}
        <div
          onMouseDown={handleResizeStart}
          className="group flex w-1 cursor-col-resize items-center justify-center hover:bg-[var(--accent-subtle)] flex-shrink-0"
        >
          <div className="h-8 w-0.5 rounded-full bg-[var(--bg-overlay)] group-hover:bg-[var(--accent)]" />
        </div>

        {/* ========== 右侧：预览区 ========== */}
        <div className="flex-1 overflow-y-auto bg-[var(--bg-base)]">
          {selectedDoc ? (
            <div className="p-6">
              {/* 文档标题区域 */}
              <div className="flex items-center gap-3 mb-6">
                <FileTypeIcon fileType={selectedDoc.file_type} />
                <div className="min-w-0 flex-1">
                  <h2 className="text-base font-semibold text-[var(--text-primary)] truncate m-0">
                    {selectedDoc.title}
                  </h2>
                  <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                    {selectedDoc.file_type.toUpperCase()} · {formatFileSize(selectedDoc.file_size)}
                  </p>
                </div>
              </div>

              {/* 文档信息卡片 */}
              <div className="rounded-lg border border-[var(--border-default)] p-4 mb-6">
                <h3 className="text-sm font-medium text-[var(--text-primary)] mb-3">文档信息</h3>
                <div className="grid grid-cols-2 gap-y-3 gap-x-6 text-sm">
                  <div>
                    <span className="text-[var(--text-muted)]">文件名</span>
                    <p className="text-[var(--text-primary)] mt-0.5 truncate">
                      {selectedDoc.title}
                    </p>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">文件类型</span>
                    <p className="text-[var(--text-primary)] mt-0.5">
                      {selectedDoc.file_type.toUpperCase()}
                    </p>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">文件大小</span>
                    <p className="text-[var(--text-primary)] mt-0.5">
                      {formatFileSize(selectedDoc.file_size)}
                    </p>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">索引状态</span>
                    <p className="mt-0.5">
                      <IndexStatusBadge status={selectedDoc.index_status} />
                    </p>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">上传日期</span>
                    <p className="text-[var(--text-primary)] mt-0.5">
                      {formatDate(selectedDoc.created_at)}
                    </p>
                  </div>
                  {selectedDoc.chunk_count !== undefined && (
                    <div>
                      <span className="text-[var(--text-muted)]">分块数量</span>
                      <p className="text-[var(--text-primary)] mt-0.5">
                        {selectedDoc.chunk_count}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* 操作按钮 */}
              <div className="flex items-center gap-3">
                <Button
                  variant="secondary"
                  type="button"
                  size="sm"
                  onClick={() => handleRebuildIndex(selectedDoc.id)}
                  disabled={rebuilding}
                  icon={
                    rebuilding ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <RefreshCw size={13} />
                    )
                  }
                >
                  重建索引
                </Button>
                <Button
                  variant="danger"
                  type="button"
                  size="sm"
                  onClick={() => handleDelete(selectedDoc.id)}
                  icon={<Trash2 size={13} />}
                >
                  删除
                </Button>
              </div>
            </div>
          ) : (
            /* 空状态提示 */
            <div className="h-full flex flex-col items-center justify-center text-[var(--text-secondary)]">
              <FileText className="w-12 h-12 mb-3 opacity-30" />
              <p className="text-sm">选择左侧文档查看详情</p>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                或拖放文件到左侧区域上传
              </p>
            </div>
          )}
        </div>
      </div>

      {/* 上传对话框 */}
      {showUploadDialog && (
        <UploadDialog
          onClose={() => setShowUploadDialog(false)}
          onUpload={handleUpload}
          uploading={uploading}
        />
      )}
    </div>
  );
}
