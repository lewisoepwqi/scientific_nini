/**
 * 数据表预览组件。
 */
import React from 'react'
import type { DataPreviewPayload } from '../store/types'
import { isRecord } from '../store/utils'

interface Props {
 preview: DataPreviewPayload | unknown
}

function getColumns(preview: Record<string, unknown>, data: Record<string, unknown>[]): string[] {
 const cols = preview.columns
 if (Array.isArray(cols)) {
 const names = cols
 .map((item) => {
 if (isRecord(item) && typeof item.name === 'string') {
 return item.name
 }
 return null
 })
 .filter((name): name is string => Boolean(name))
 if (names.length > 0) {
 return names
 }
 }
 if (data.length > 0) {
 return Object.keys(data[0])
 }
 return []
}

function formatCell(value: unknown): string {
 if (value === null || value === undefined) return ''
 if (typeof value === 'number') return Number.isFinite(value) ? value.toString() : ''
 if (typeof value === 'string') return value
 if (typeof value === 'boolean') return value ? 'true' : 'false'
 return JSON.stringify(value)
}

const DataViewer = React.memo(function DataViewer({ preview }: Props) {
 if (!isRecord(preview)) {
 return <div className="text-xs text-[var(--error)] mt-2">数据预览格式无效</div>
 }

 const rowsRaw = preview.data
 const rows = Array.isArray(rowsRaw)
 ? rowsRaw.filter((item): item is Record<string, unknown> => isRecord(item))
 : []
 const previewRowsRaw = typeof preview.preview_rows === 'number' ? preview.preview_rows : rows.length
 const previewRows = Math.max(0, Math.floor(previewRowsRaw))
 const visibleRows = rows.slice(0, previewRows)
 const columns = getColumns(preview, visibleRows)

 if (visibleRows.length === 0 || columns.length === 0) {
 return <div className="text-xs text-[var(--text-secondary)] mt-2">没有可展示的数据行</div>
 }

 const totalRows = typeof preview.total_rows === 'number' ? preview.total_rows : rows.length

 return (
 <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] mt-2 overflow-hidden">
 <div className="px-3 py-2 text-xs text-[var(--text-secondary)] border-b border-[var(--border-default)] bg-[var(--bg-elevated)]">
 预览 {previewRows} / {totalRows} 行
 </div>
 <div className="overflow-x-auto">
 <table className="min-w-full text-xs">
 <thead className="bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
 <tr>
 {columns.map((column) => (
 <th key={column} className="px-3 py-2 text-left font-semibold border-b border-[var(--border-default)] whitespace-nowrap">
 {column}
 </th>
 ))}
 </tr>
 </thead>
 <tbody>
 {visibleRows.map((row, idx) => (
 <tr key={`row-${idx}`} className="odd:bg-[var(--bg-base)] dark:odd:bg-[var(--bg-elevated)] even:bg-[var(--bg-elevated)] dark:even:bg-[var(--bg-elevated)]/80">
 {columns.map((column) => (
 <td key={`${idx}-${column}`} className="px-3 py-2 border-b border-[var(--border-default)] align-top whitespace-nowrap">
 {formatCell(row[column])}
 </td>
 ))}
 </tr>
 ))}
 </tbody>
 </table>
 </div>
 </div>
 )
})

export default DataViewer
