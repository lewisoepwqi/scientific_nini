/**
 * 复用模态框组件 —— 统一处理 ARIA 属性、焦点捕获、Escape 关闭和焦点恢复。
 *
 * 所有模态框（设置面板、工具清单、技能管理等）都应使用此组件，
 * 以确保 WCAG 2.4.3 焦点顺序 和 4.1.2 名称、角色、值 合规。
 */
import { useCallback, useEffect, useId, useRef, type ReactNode } from 'react'

interface Props {
 /** 是否打开 */
 open: boolean
 /** 关闭回调 */
 onClose: () => void
 /** 标题文本，用于 aria-labelledby */
 title: string
 /** 模态框内容 */
 children: ReactNode
 /** 最大宽度 Tailwind class，默认 max-w-lg */
 maxWidthClass?: string
 /** 背景遮罩颜色 class，默认 bg-black/40 */
 backdropClass?: string
 /** 内容区额外 class */
 contentClass?: string
}

/**
 * 获取当前焦点元素及其祖先中最近的 focusable 边界。
 * 返回所有可通过 Tab 聚焦的元素列表。
 */
function getFocusableElements(container: HTMLElement): HTMLElement[] {
 const selector = [
 'a[href]',
 'button:not([disabled])',
 'input:not([disabled])',
 'select:not([disabled])',
 'textarea:not([disabled])',
 '[tabindex]:not([tabindex="-1"])',
 ].join(', ')
 return Array.from(container.querySelectorAll<HTMLElement>(selector)).filter(
 (el) => !el.hasAttribute('disabled') && el.tabIndex >= 0
 )
}

export default function BaseModal({
 open,
 onClose,
 title,
 children,
 maxWidthClass = 'max-w-lg',
 backdropClass = 'bg-black/40',
 contentClass = '',
}: Props) {
 const dialogRef = useRef<HTMLDivElement>(null)
 const titleId = `modal-title-${useId()}`
 // 记录打开前的焦点元素，关闭时恢复
 const previousFocusRef = useRef<HTMLElement | null>(null)

 // 打开时记录焦点、关闭时恢复
 useEffect(() => {
 if (open) {
 previousFocusRef.current = document.activeElement as HTMLElement
 // 延迟聚焦到模态框容器，确保 DOM 已渲染
 requestAnimationFrame(() => {
 dialogRef.current?.focus()
 })
 } else {
 // 恢复焦点到触发元素
 previousFocusRef.current?.focus()
 previousFocusRef.current = null
 }
 }, [open])

 // Escape 关闭
 const handleKeyDown = useCallback(
 (e: React.KeyboardEvent) => {
 if (e.key === 'Escape') {
 e.stopPropagation()
 onClose()
 return
 }

 // Tab 焦点捕获
 if (e.key === 'Tab' && dialogRef.current) {
 const focusable = getFocusableElements(dialogRef.current)
 if (focusable.length === 0) return

 const first = focusable[0]
 const last = focusable[focusable.length - 1]

 if (e.shiftKey) {
 // Shift+Tab：在第一个元素时跳到最后一个
 if (document.activeElement === first) {
 e.preventDefault()
 last.focus()
 }
 } else {
 // Tab：在最后一个元素时跳到第一个
 if (document.activeElement === last) {
 e.preventDefault()
 first.focus()
 }
 }
 }
 },
 [onClose]
 )

 if (!open) return null

 return (
 <div
 className={`fixed inset-0 z-50 flex items-center justify-center ${backdropClass} p-4 backdrop-blur-sm`}
 onClick={(e) => {
 // 点击遮罩关闭
 if (e.target === e.currentTarget) onClose()
 }}
 >
 <div
 ref={dialogRef}
 role="dialog"
 aria-modal="true"
 aria-labelledby={titleId}
 tabIndex={-1}
 onKeyDown={handleKeyDown}
 className={`bg-[var(--bg-base)] rounded-2xl shadow-2xl w-full ${maxWidthClass} flex flex-col max-h-[92vh] outline-none ${contentClass}`}
 >
 {/* 隐藏的标题，供 aria-labelledby 引用 */}
 <h2 id={titleId} className="sr-only">
 {title}
 </h2>
 {children}
 </div>
 </div>
 )
}
