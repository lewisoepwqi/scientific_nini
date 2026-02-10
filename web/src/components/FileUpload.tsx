/**
 * 文件上传组件 —— 附件按钮（支持多文件顺序上传）。
 */
import { useCallback, useRef, useState } from 'react'
import { useStore } from '../store'
import { Paperclip, Loader2 } from 'lucide-react'

export default function FileUpload() {
  const uploadFile = useStore((s) => s.uploadFile)
  const isUploading = useStore((s) => s.isUploading)
  const uploadProgress = useStore((s) => s.uploadProgress)
  const uploadingFileName = useStore((s) => s.uploadingFileName)
  const inputRef = useRef<HTMLInputElement>(null)
  const [pendingCount, setPendingCount] = useState(0)

  const handleFiles = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return
      setPendingCount(files.length)
      for (const file of files) {
        await uploadFile(file)
        setPendingCount((count) => Math.max(count - 1, 0))
      }
      setPendingCount(0)
    },
    [uploadFile],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || [])
      void handleFiles(files)
      e.target.value = ''
    },
    [handleFiles],
  )

  return (
    <div className="flex items-center gap-2 min-w-0">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={isUploading}
        className="h-8 rounded-2xl border border-gray-200 px-2.5 text-xs text-gray-600
                   inline-flex items-center gap-1.5 hover:bg-gray-50 transition-colors
                   disabled:cursor-not-allowed disabled:opacity-60"
        title="上传数据文件"
      >
        <Paperclip size={14} />
        <span className="hidden sm:inline">附件</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls,.tsv,.txt"
        multiple
        onChange={handleChange}
        className="hidden"
        disabled={isUploading}
      />

      <span className="hidden md:inline text-[11px] text-gray-400 whitespace-nowrap">
        支持 CSV / Excel / TSV / TXT
      </span>

      {(isUploading || pendingCount > 0) && (
        <div className="min-w-0 rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">
          <div className="flex items-center gap-1.5">
            <Loader2 size={12} className="animate-spin flex-shrink-0" />
            <span className="truncate">
              {uploadingFileName || '上传中'}
              {pendingCount > 1 ? `（剩余 ${pendingCount - 1}）` : ''}
            </span>
            <span className="text-emerald-600">{uploadProgress}%</span>
          </div>
          <div className="h-1 bg-emerald-100 rounded-full mt-1 overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${uploadProgress}%` }} />
          </div>
        </div>
      )}
    </div>
  )
}
