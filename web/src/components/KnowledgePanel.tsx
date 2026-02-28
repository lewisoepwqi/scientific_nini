/**
 * KnowledgePanel - 知识库管理面板
 *
 * 提供知识库文档的上传、查看、删除功能。
 */
import { useEffect, useState, useCallback } from "react";
import {
  BookOpen,
  X,
  Upload,
  Trash2,
  FileText,
  Search,
  Loader2,
  AlertCircle,
} from "lucide-react";

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
  isOpen: boolean;
  onClose: () => void;
}

export default function KnowledgePanel({ isOpen, onClose }: KnowledgePanelProps) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showUploadDialog, setShowUploadDialog] = useState(false);

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

  useEffect(() => {
    if (isOpen) {
      void fetchDocuments();
    }
  }, [isOpen, fetchDocuments]);

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
    if (!confirm("确定要删除这个文档吗？")) return;

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
    <div className="fixed inset-y-0 right-0 w-96 bg-white dark:bg-gray-900 shadow-xl border-l border-gray-200 dark:border-gray-700 z-50 flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-blue-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            知识库
          </h2>
          <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full">
            {documents.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowUploadDialog(true)}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-blue-600 dark:text-blue-400"
            title="上传文档"
          >
            <Upload className="w-5 h-5" />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* 搜索框 */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="搜索文档..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mx-4 mt-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 flex items-center gap-2 text-sm text-red-700 dark:text-red-300">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* 文档列表 */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-32 text-gray-500">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            加载中...
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-500">
            <FileText className="w-12 h-12 mb-2 opacity-50" />
            <p className="text-sm">
              {searchQuery ? "未找到匹配的文档" : "暂无文档"}
            </p>
            {!searchQuery && (
              <button
                onClick={() => setShowUploadDialog(true)}
                className="mt-2 text-sm text-blue-600 hover:text-blue-700"
              >
                上传第一个文档
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredDocuments.map((doc) => (
              <div
                key={doc.id}
                className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      <span className="font-medium text-gray-900 dark:text-gray-100 truncate">
                        {doc.title}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 space-x-2">
                      <span>{doc.file_type.toUpperCase()}</span>
                      <span>•</span>
                      <span>{formatFileSize(doc.file_size)}</span>
                      <span>•</span>
                      <IndexStatusBadge status={doc.index_status} />
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
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
    </div>
  );
}

// 索引状态标签
function IndexStatusBadge({
  status,
}: {
  status: KnowledgeDocument["index_status"];
}) {
  const styles = {
    indexed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
    indexing:
      "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300",
    failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
    pending: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300",
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
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-80 p-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          上传文档
        </h3>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              选择文件
            </label>
            <input
              type="file"
              accept=".txt,.md,.pdf"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              标题（可选）
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="文档标题"
              className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            disabled={uploading}
            className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={!selectedFile || uploading}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {uploading && <Loader2 className="w-4 h-4 animate-spin" />}
            上传
          </button>
        </div>
      </div>
    </div>
  );
}
