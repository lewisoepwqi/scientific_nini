/**
 * KnowledgePanel - 知识库管理面板
 *
 * 提供知识库文档的上传、查看、删除功能。
 */
import { useState, useCallback } from "react";
import {
 Upload,
 Trash2,
 FileText,
 Search,
 Loader2,
 AlertCircle,
 RefreshCw,
} from "lucide-react";
import { useConfirm } from "../store/confirm-store";
import { CommandSheet } from "./ui";
import Button from "./ui/Button";

interface KnowledgeDocument {
 id: string;
 title: string;
 file_type: string;
 file_size: number;
 index_status: "indexed" | "indexing" | "failed" | "pending";
 created_at?: string;
 chunk_count?: number;
}

interface KnowledgePanelProps {
 isOpen?: boolean;
 onClose?: () => void;
}

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

export default function KnowledgePanel({ isOpen = true, onClose }: KnowledgePanelProps) {
 const confirm = useConfirm();
 const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
 const [loading, setLoading] = useState(false);
 const [uploading, setUploading] = useState(false);
 const [rebuilding, setRebuilding] = useState(false);
 const [searchQuery, setSearchQuery] = useState("");
 const [error, setError] = useState<string | null>(null);
 const [showUploadDialog, setShowUploadDialog] = useState(false);
 const [, setIndexStatus] = useState<IndexStatus | null>(null);

 // 获取文档列表
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

 // 获取索引状态
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

 // 重建索引
 const handleRebuildIndex = async () => {
 const ok = await confirm({
 title: "重建知识库索引",
 message: "重建索引可能需要一些时间，确定继续吗？",
 confirmText: "重建",
 });
 if (!ok) return;

 try {
 setRebuilding(true);
 setError(null);
 const resp = await fetch("/api/knowledge/index/rebuild", {
 method: "POST",
 });

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

 // 上传文档
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

 // 刷新列表
 await fetchDocuments();
 setShowUploadDialog(false);
 } catch (e) {
 console.error("上传文档失败:", e);
 setError("上传文档失败");
 } finally {
 setUploading(false);
 }
 };

 // 删除文档
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

 // 刷新列表
 await fetchDocuments();
 } catch (e) {
 console.error("删除文档失败:", e);
 setError("删除文档失败");
 }
 };

 // 格式化文件大小
 const formatFileSize = (bytes: number) => {
 if (bytes < 1024) return `${bytes} B`;
 if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
 return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
 };

 // 过滤文档
 const filteredDocuments = documents.filter((doc) =>
 doc.title.toLowerCase().includes(searchQuery.toLowerCase())
 );

 if (!isOpen) return null;

 return (
 <CommandSheet isOpen={isOpen} onClose={onClose ?? (() => {})} title="知识库">
 {/* 工具栏 */}
 <div
 className="flex items-center justify-between px-4 py-2"
 style={{ borderBottom: '1px solid var(--border-subtle)' }}
 >
 <span className="text-[11px] text-[var(--text-muted)]">
 {documents.length} 个文档
 </span>
 <div className="flex items-center gap-1">
 <Button
 variant="ghost"
 type="button"
 onClick={handleRebuildIndex}
 disabled={rebuilding}
 className="h-[28px] w-[28px] p-0"
 title="重建索引"
 aria-label="重建索引"
 >
 {rebuilding ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
 </Button>
 <Button
 variant="ghost"
 type="button"
 onClick={() => setShowUploadDialog(true)}
 className="h-[28px] w-[28px] p-0"
 title="上传文档"
 aria-label="上传文档"
 >
 <Upload size={13} />
 </Button>
 </div>
 </div>

 {/* 搜索框 */}
 <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
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

 {/* 错误提示 */}
 {error && (
 <div className="mx-4 mt-3 p-3 rounded-lg bg-[var(--accent-subtle)] border border-[var(--error)] flex items-center gap-2 text-sm text-[var(--error)]">
 <AlertCircle className="w-4 h-4" />
 {error}
 </div>
 )}

 {/* 文档列表 */}
 <div className="flex-1 overflow-y-auto p-4">
 {loading ? (
 <div className="flex items-center justify-center h-32 text-[var(--text-secondary)]">
 <Loader2 className="w-6 h-6 animate-spin mr-2" />
 加载中...
 </div>
 ) : filteredDocuments.length === 0 ? (
 <div className="flex flex-col items-center justify-center h-32 text-[var(--text-secondary)]">
 <FileText className="w-12 h-12 mb-2 opacity-50" />
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
 <div className="space-y-2">
 {filteredDocuments.map((doc) => (
 <div
 key={doc.id}
 className="p-3 rounded-lg border border-[var(--border-default)] hover:border-[var(--border-default)] transition-colors"
 >
 <div className="flex items-start justify-between">
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2">
 <FileText className="w-4 h-4 text-[var(--text-muted)] flex-shrink-0" />
 <span className="font-medium text-[var(--text-primary)] truncate">
 {doc.title}
 </span>
 </div>
 <div className="mt-1 text-xs text-[var(--text-secondary)] space-x-2">
 <span>{doc.file_type.toUpperCase()}</span>
 <span>•</span>
 <span>{formatFileSize(doc.file_size)}</span>
 <span>•</span>
 <IndexStatusBadge status={doc.index_status} />
 </div>
 </div>
 <Button
 variant="ghost"
 type="button"
 onClick={() => handleDelete(doc.id)}
 className="p-2 rounded text-[var(--text-muted)] hover:text-[var(--error)]"
 >
 <Trash2 className="w-4 h-4" />
 </Button>
 </div>
 </div>
 ))}
 </div>
 )}
 </div>

 {/* 上传对话框 */}
 {showUploadDialog && (
 <UploadDialog
 onClose={() => setShowUploadDialog(false)}
 onUpload={handleUpload}
 uploading={uploading}
 />
 )}
 </CommandSheet>
 );
}

// 索引状态标签
function IndexStatusBadge({
 status,
}: {
 status: KnowledgeDocument["index_status"];
}) {
 const styles = {
 indexed: "bg-[var(--accent-subtle)] text-[var(--success)]",
 indexing:
 "bg-[var(--accent-subtle)] text-[var(--warning)]",
 failed: "bg-[var(--accent-subtle)] text-[var(--error)]",
 pending: "bg-[var(--bg-elevated)] text-[var(--text-secondary)] dark:bg-[var(--bg-overlay)] dark:text-[var(--text-muted)]",
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

// 上传对话框
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
 <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
 <div className="bg-[var(--bg-base)] rounded-xl shadow-xl w-80 p-4">
 <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
 上传文档
 </h3>

 <div className="space-y-4">
 <div>
 <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
 选择文件
 </label>
 <input
 type="file"
 accept=".txt,.md,.pdf"
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
 className="w-full px-3 py-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] text-sm"
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
