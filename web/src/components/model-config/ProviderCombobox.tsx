/**
 * 提供商搜索下拉框 —— 与模型下拉保持一致的输入与面板样式。
 */
import { useEffect, useState, useRef } from 'react'
import { Search, ChevronDown } from 'lucide-react'
import type { ProviderOption } from './types'

interface ProviderComboboxProps {
  value: string
  onChange: (val: string) => void
  options: ProviderOption[]
  placeholder?: string
  disabled?: boolean
}

export default function ProviderCombobox({
  value,
  onChange,
  options,
  placeholder = '搜索提供商...',
  disabled = false,
}: ProviderComboboxProps) {
  const [query, setQuery] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  const selected = value ? options.find((item) => item.id === value) : undefined
  const selectedLabel = selected?.name || ''

  useEffect(() => {
    if (!dropdownOpen) {
      setQuery(selectedLabel)
    }
  }, [dropdownOpen, selectedLabel])

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

  const queryText = query.trim().toLowerCase()
  const filtered = queryText
    ? options.filter(
      (item) =>
        item.name.toLowerCase().includes(queryText) || item.id.toLowerCase().includes(queryText),
    )
    : options

  const pickProvider = (providerId: string) => {
    const picked = options.find((item) => item.id === providerId)
    setQuery(picked?.name || '')
    onChange(providerId)
    setDropdownOpen(false)
  }

  return (
    <div className="relative" ref={wrapperRef}>
      <div className="relative">
        <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            if (!dropdownOpen) setDropdownOpen(true)
          }}
          onFocus={() => !disabled && setDropdownOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              if (!queryText) {
                pickProvider('')
                return
              }
              if (filtered.length > 0) {
                pickProvider(filtered[0].id)
              }
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full h-8 pl-7 pr-7 text-xs border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300 disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => !disabled && setDropdownOpen(!dropdownOpen)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 disabled:opacity-50"
          disabled={disabled}
        >
          <ChevronDown size={12} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {dropdownOpen && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          <button
            type="button"
            onClick={() => pickProvider('')}
            className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 transition-colors ${
              !value ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
            }`}
          >
            自动（跟随全局）
          </button>
          {filtered.length === 0 ? (
            <div className="px-3 py-3 text-xs text-gray-400">无匹配提供商</div>
          ) : (
            filtered.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => pickProvider(item.id)}
                className={`w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 transition-colors ${
                  item.id === value ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
                }`}
              >
                {item.name}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
