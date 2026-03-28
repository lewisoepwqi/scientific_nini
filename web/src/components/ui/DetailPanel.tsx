/**
 * DetailPanel —— 推入式右侧详情面板。
 *
 * 适用场景：查看信息（工具详情、Agent 信息、研究画像入口等）。
 * 无背景遮罩，不阻断主区域交互。
 *
 * 设计规范：.impeccable.md Interaction Patterns §DetailPanel
 */
import { useEffect, useId, useRef, useCallback, type ReactNode } from 'react'
import { X } from 'lucide-react'
import Button from './Button'

export interface DetailPanelProps {
 /** 是否打开 */
 isOpen: boolean
 /** 关闭回调 */
 onClose: () => void
 /** 面板标题 */
 title: string
 /** 面板内容 */
 children: ReactNode
 /** 面板宽度，默认 320px */
 width?: number
}

export default function DetailPanel({
 isOpen,
 onClose,
 title,
 children,
 width = 320,
}: DetailPanelProps) {
 const panelRef = useRef<HTMLDivElement>(null)
 const titleId = `detail-panel-title-${useId()}`
 const previousFocusRef = useRef<HTMLElement | null>(null)

 // 焦点管理：打开时聚焦面板，关闭时恢复焦点
 useEffect(() => {
 if (isOpen) {
 previousFocusRef.current = document.activeElement as HTMLElement
 requestAnimationFrame(() => {
 panelRef.current?.focus()
 })
 } else {
 previousFocusRef.current?.focus()
 previousFocusRef.current = null
 }
 }, [isOpen])

 // ESC 关闭
 const handleKeyDown = useCallback(
 (e: React.KeyboardEvent) => {
 if (e.key === 'Escape') {
 e.stopPropagation()
 onClose()
 }
 },
 [onClose],
 )

 if (!isOpen) return null

 return (
 <div
 ref={panelRef}
 role="dialog"
 aria-modal="false"
 aria-labelledby={titleId}
 tabIndex={-1}
 onKeyDown={handleKeyDown}
 className="fixed inset-y-0 right-0 z-50 flex flex-col border-l outline-none"
 style={{
 width: `${width}px`,
 backgroundColor: 'var(--bg-base)',
 borderLeftColor: 'var(--border-subtle)',
 transform: 'translateX(0)',
 transition: 'transform 150ms ease',
 }}
 >
 {/* Header 48px */}
 <div
 className="flex h-12 flex-shrink-0 items-center justify-between px-4 border-b border-[var(--border-subtle)]"
 >
 <h2
 id={titleId}
 className="text-[var(--text-md-size,14px)] font-medium"
 style={{ color: 'var(--text-primary)', fontSize: '14px', lineHeight: '20px' }}
 >
 {title}
 </h2>
 <Button
 variant="ghost"
 type="button"
 onClick={onClose}
 aria-label="关闭面板"
 className="h-[28px] w-[28px] p-0"
 >
 <X size={16} />
 </Button>
 </div>

 {/* 可滚动内容区 */}
 <div className="flex-1 overflow-y-auto">
 {children}
 </div>
 </div>
 )
}
