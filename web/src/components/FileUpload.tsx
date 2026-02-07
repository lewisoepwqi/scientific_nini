/**
 * 文件上传组件 —— 拖拽/点击上传。
 */
import { useCallback, useState } from 'react'
import { useStore } from '../store'
import { Upload, FileSpreadsheet } from 'lucide-react'

export default function FileUpload() {
  const uploadFile = useStore((s) => s.uploadFile)
  const [isDragging, setIsDragging] = useState(false)

  const handleFile = useCallback(
    async (file: File) => {
      await uploadFile(file)
    },
    [uploadFile],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
      e.target.value = ''
    },
    [handleFile],
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={`relative rounded-lg border-2 border-dashed px-3 py-2 text-center text-sm transition-colors ${
        isDragging
          ? 'border-blue-400 bg-blue-50 text-blue-600'
          : 'border-gray-200 text-gray-400 hover:border-gray-300'
      }`}
    >
      <label className="cursor-pointer flex items-center justify-center gap-2">
        {isDragging ? (
          <Upload size={16} />
        ) : (
          <FileSpreadsheet size={16} />
        )}
        <span>{isDragging ? '释放以上传' : '拖拽或点击上传数据文件（CSV / Excel）'}</span>
        <input
          type="file"
          accept=".csv,.xlsx,.xls,.tsv,.txt"
          onChange={handleChange}
          className="hidden"
        />
      </label>
    </div>
  )
}
