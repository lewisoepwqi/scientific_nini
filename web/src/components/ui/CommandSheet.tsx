/**
 * CommandSheet —— 右侧滑入式表单/配置面板。
 *
 * 适用场景：新建/编辑 Agent、工具配置、知识库上传等需要填写表单的操作。
 * 半透明遮罩，点击遮罩或 ESC 关闭。
 *
 * 设计规范：.impeccable.md Interaction Patterns §CommandSheet
 */
import { useEffect, useId, useRef, useCallback, type ReactNode } from 'react'
import { X } from 'lucide-react'
import Button from './Button'

export interface CommandSheetProps {
 /** 是否打开 */
 isOpen: boolean
 /** 关闭回调 */
 onClose: () => void
 /** 确认回调 */
 onConfirm?: () => void
 /** 面板标题 */
 title: string
 /** 确认按钮文字，默认「确认」 */
 confirmLabel?: string
 /** 取消按钮文字，默认「取消」 */
 cancelLabel?: string
 /** 面板内容 */
 children: ReactNode
 /** 是否在加载中（禁用按钮） */
 loading?: boolean
}

export default function CommandSheet({
 isOpen,
 onClose,
 onConfirm,
 title,
 confirmLabel = '确认',
 cancelLabel = '取消',
 children,
 loading = false,
}: CommandSheetProps) {
 const sheetRef = useRef<HTMLDivElement>(null)
 const titleId = `command-sheet-title-${useId()}`
 const previousFocusRef = useRef<HTMLElement | null>(null)

 // 焦点管理
 useEffect(() => {
 if (isOpen) {
 previousFocusRef.current = document.activeElement as HTMLElement
 requestAnimationFrame(() => {
 sheetRef.current?.focus()
 })
 } else {
 previousFocusRef.current?.focus()
 previousFocusRef.current = null
 }
 }, [isOpen])

 // ESC 关闭 + Tab 焦点捕获
 const handleKeyDown = useCallback(
 (e: React.KeyboardEvent) => {
 if (e.key === 'Escape') {
 e.stopPropagation()
 onClose()
 return
 }

 // Tab 焦点捕获
 if (e.key === 'Tab' && sheetRef.current) {
 const focusable = sheetRef.current.querySelectorAll<HTMLElement>(
 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
 )
 const arr = Array.from(focusable).filter((el) => el.tabIndex >= 0)
 if (arr.length === 0) return

 const first = arr[0]
 const last = arr[arr.length - 1]

 if (e.shiftKey) {
 if (document.activeElement === first) {
 e.preventDefault()
 last.focus()
 }
 } else {
 if (document.activeElement === last) {
 e.preventDefault()
 first.focus()
 }
 }
 }
 },
 [onClose],
 )

 if (!isOpen) return null

 return (
 <>
 {/* 半透明遮罩 */}
 <div
 className="fixed inset-0 z-50"
 style={{ backgroundColor: 'rgba(0, 0, 0, 0.4)' }}
 onClick={onClose}
 aria-hidden="true"
 />

 {/* 面板 */}
 <div
 ref={sheetRef}
 role="dialog"
 aria-modal="true"
 aria-labelledby={titleId}
 tabIndex={-1}
 onKeyDown={handleKeyDown}
 className="fixed inset-y-0 right-0 z-50 flex flex-col outline-none"
 style={{
 width: '40vw',
 minWidth: '480px',
 backgroundColor: 'var(--bg-base)',
 borderLeft: '1px solid var(--border-subtle)',
 transform: 'translateX(0)',
 transition: 'transform 200ms ease',
 }}
 >
 {/* Header 44px */}
 <div
 className="flex h-[44px] flex-shrink-0 items-center justify-between px-4"
 style={{ borderBottom: '1px solid var(--border-subtle)' }}
 >
 <h2
 id={titleId}
 className="text-[14px] font-medium"
 style={{ color: 'var(--text-primary)', lineHeight: '20px' }}
 >
 {title}
 </h2>
 <Button
 variant="ghost"
 size="icon-md"
 type="button"
 onClick={onClose}
 aria-label="关闭面板"
 >
 <X size={18} />
 </Button>
 </div>

 {/* 可滚动内容区 */}
 <div className="flex-1 overflow-y-auto">
 {children}
 </div>

 {/* Footer 60px */}
 {onConfirm && (
 <div
 className="flex h-[60px] flex-shrink-0 items-center justify-end gap-2 px-4"
 style={{ borderTop: '1px solid var(--border-subtle)' }}
 >
 <Button
 variant="secondary"
 type="button"
 onClick={onClose}
 disabled={loading}
 >
 {cancelLabel}
 </Button>
 <Button
 variant="primary"
 type="button"
 onClick={onConfirm}
 loading={loading}
 >
 {confirmLabel}
 </Button>
 </div>
 )}
 </div>
 </>
 )
}
