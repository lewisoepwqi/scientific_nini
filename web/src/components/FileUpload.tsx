/**
 * 文件上传组件 —— 附件按钮（支持多文件顺序上传）。
 */
import { useCallback, useRef, useState } from 'react'
import { useStore } from '../store'
import { Paperclip, Loader2 } from 'lucide-react'
import Button from './ui/Button'

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
 <Button
        variant="secondary"
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={isUploading}
        icon={<Paperclip size={14} />}
        title="上传数据文件"
      >
        <span className="hidden sm:inline">附件</span>
      </Button>
 <input
 ref={inputRef}
 type="file"
 accept=".csv,.xlsx,.xls,.tsv,.txt"
 multiple
 onChange={handleChange}
 className="hidden"
 disabled={isUploading}
 />

 <span className="hidden md:inline text-[11px] text-[var(--text-muted)] whitespace-nowrap">
 支持 CSV / Excel / TSV / TXT
 </span>

 {(isUploading || pendingCount > 0) && (
 <div className="min-w-0 rounded-md bg-[var(--accent-subtle)] px-2 py-1 text-[11px] text-[var(--success)] dark:text-[var(--success)]">
 <div className="flex items-center gap-1.5">
 <Loader2 size={12} className="animate-spin flex-shrink-0" />
 <span className="truncate">
 {uploadingFileName || '上传中'}
 {pendingCount > 1 ? `（剩余 ${pendingCount - 1}）` : ''}
 </span>
 <span className="text-[var(--success)]">{uploadProgress}%</span>
 </div>
 <div className="h-1 bg-[var(--accent-subtle)] rounded-full mt-1 overflow-hidden">
 <div className="h-full bg-[var(--success)] transition-all" style={{ width: `${uploadProgress}%` }} />
 </div>
 </div>
 )}
 </div>
 )
}
