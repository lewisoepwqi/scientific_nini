/**
 * 模型搜索下拉框 —— 支持搜索过滤、远程模型列表、自定义输入。
 */
import { useEffect, useState, useRef } from 'react'
import { Search, ChevronDown, Loader2 } from 'lucide-react'
import type { RemoteModels } from './types'
import Button from '../ui/Button'

interface ModelComboboxProps {
 value: string
 onChange: (val: string) => void
 staticModels: string[]
 providerId: string
 size?: 'sm' | 'md'
}

export default function ModelCombobox({
 value,
 onChange,
 staticModels,
 providerId,
 size = 'md',
}: ModelComboboxProps) {
 const [query, setQuery] = useState(value)
 const [dropdownOpen, setDropdownOpen] = useState(false)
 const [remote, setRemote] = useState<RemoteModels>({
 loading: false,
 models: [],
 source: null,
 })
 const inputRef = useRef<HTMLInputElement>(null)
 const wrapperRef = useRef<HTMLDivElement>(null)
 const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
 const [activeIndex, setActiveIndex] = useState(0)

 // 展开时获取远程模型列表
 useEffect(() => {
 if (!dropdownOpen) return
 let cancelled = false
 setRemote((prev) => ({ ...prev, loading: true }))

 fetch(`/api/models/${providerId}/available`)
 .then((r) => r.json())
 .then((data) => {
 if (cancelled) return
 if (data.success && data.data) {
 setRemote({
 loading: false,
 models: data.data.models || [],
 source: data.data.source || 'static',
 })
 } else {
 setRemote({ loading: false, models: staticModels, source: 'static' })
 }
 })
 .catch(() => {
 if (!cancelled) {
 setRemote({ loading: false, models: staticModels, source: 'static' })
 }
 })

 return () => { cancelled = true }
 }, [dropdownOpen, providerId, staticModels])

 // 点击外部关闭
 useEffect(() => {
 function handleClick(e: MouseEvent) {
 if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
 setDropdownOpen(false)
 }
 }
 if (dropdownOpen) {
 document.addEventListener('mousedown', handleClick)
 return () => document.removeEventListener('mousedown', handleClick)
 }
 }, [dropdownOpen])

 // 同步外部 value 变化
 useEffect(() => {
 setQuery(value)
 }, [value])

 const allModels = remote.models.length > 0 ? remote.models : staticModels
 const filtered = query
 ? allModels.filter((m) => m.toLowerCase().includes(query.toLowerCase()))
 : allModels

 useEffect(() => {
 if (!dropdownOpen) return
 const selectedIndex = filtered.findIndex((model) => model === value)
 setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0)
 }, [dropdownOpen, filtered, value])

 useEffect(() => {
 if (!dropdownOpen) return
 const activeOption = optionRefs.current[activeIndex]
 activeOption?.scrollIntoView({ block: 'nearest' })
 }, [activeIndex, dropdownOpen])

 const handleSelect = (model: string) => {
 setQuery(model)
 onChange(model)
 setDropdownOpen(false)
 }

 const handleInputChange = (val: string) => {
 setQuery(val)
 onChange(val)
 if (!dropdownOpen) setDropdownOpen(true)
 }

 const compact = size === 'sm'
 const inputClassName = compact
 ? 'w-full h-8 pl-7 pr-7 text-xs border rounded-lg dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)] dark:text-[var(--text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]'
 : 'w-full pl-8 pr-8 py-2 text-sm border rounded-lg dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)] dark:text-[var(--text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]'
 const iconSize = compact ? 12 : 14

 return (
 <div className="relative" ref={wrapperRef}>
 <div className="relative">
 <Search size={iconSize} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
 <input
 ref={inputRef}
 type="text"
 name={`${providerId}-model-search`}
 autoComplete="off"
 value={query}
 onChange={(e) => handleInputChange(e.target.value)}
 onFocus={() => setDropdownOpen(true)}
 onKeyDown={(e) => {
 if (e.key === 'ArrowDown') {
 e.preventDefault()
 if (!dropdownOpen) {
 setDropdownOpen(true)
 setActiveIndex(0)
 return
 }
 if (filtered.length > 0) {
 setActiveIndex((prev) => Math.min(prev + 1, filtered.length - 1))
 }
 return
 }
 if (e.key === 'ArrowUp') {
 e.preventDefault()
 if (!dropdownOpen) {
 setDropdownOpen(true)
 setActiveIndex(Math.max(filtered.length - 1, 0))
 return
 }
 if (filtered.length > 0) {
 setActiveIndex((prev) => Math.max(prev - 1, 0))
 }
 return
 }
 if (e.key === 'Enter') {
 if (!dropdownOpen) return
 e.preventDefault()
 if (filtered.length > 0) {
 handleSelect(filtered[activeIndex] ?? filtered[0])
 return
 }
 if (query.trim()) {
 handleSelect(query.trim())
 }
 return
 }
 if (e.key === 'Escape') {
 setDropdownOpen(false)
 }
 }}
 placeholder="搜索或输入模型名称..."
 className={inputClassName}
 />
 <Button
 variant="ghost"
 size="icon-sm"
 type="button"
 onClick={() => setDropdownOpen(!dropdownOpen)}
 className="absolute right-1.5 top-1/2 -translate-y-1/2"
 >
 <ChevronDown size={iconSize} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
 </Button>
 </div>

 {dropdownOpen && (
 <div className="absolute z-10 w-full mt-1 bg-[var(--bg-base)] border border-[var(--border-default)] rounded-lg shadow-lg max-h-48 overflow-y-auto">
 {remote.loading ? (
 <div className="flex items-center gap-2 px-3 py-3 text-xs text-[var(--text-muted)]">
 <Loader2 size={12} className="animate-spin" />
 正在获取模型列表...
 </div>
 ) : filtered.length === 0 ? (
 <div className="px-3 py-3 text-xs text-[var(--text-muted)]">
 {query ? (
 <span>
 无匹配结果，按 Enter 使用自定义模型：
 <Button
 variant="ghost"
 className="ml-1 text-[var(--accent)] hover:underline"
 onClick={() => handleSelect(query)}
 >
 {query}
 </Button>
 </span>
 ) : '无可用模型'}
 </div>
 ) : (
 <>
 {remote.source === 'remote' && (
 <div className="px-3 py-1.5 text-[10px] text-[var(--success)] bg-[var(--accent-subtle)] border-b border-[var(--border-default)]">
 远程获取 · {allModels.length} 个模型
 </div>
 )}
 {filtered.map((m) => (
 <Button
 key={m}
 ref={(node) => {
 optionRefs.current[filtered.indexOf(m)] = node
 }}
 variant="ghost"
 type="button"
 onClick={() => handleSelect(m)}
 onMouseEnter={() => setActiveIndex(filtered.indexOf(m))}
 className={`w-full text-left px-3 py-1.5 text-sm ${
 activeIndex === filtered.indexOf(m)
 ? 'bg-[var(--accent-subtle)] text-[var(--accent)] font-medium'
 : m === value
 ? 'bg-[var(--accent-subtle)]/70 text-[var(--accent)] font-medium'
 : ''
 }`}
 >
 {m}
 </Button>
 ))}
 </>
 )}
 </div>
 )}
 </div>
 )
}
