/**
 * ConfirmDialog —— 居中确认对话框基础组件。
 *
 * 适用场景：删除确认、不可逆操作确认。
 * 半透明遮罩（点击遮罩不关闭），ESC 可关闭。
 *
 * 设计规范：.impeccable.md Interaction Patterns §ConfirmDialog
 */
import { useEffect, useId, useRef, useCallback } from 'react'
import Button from './Button'

export interface ConfirmDialogProps {
 /** 是否打开 */
 isOpen: boolean
 /** 取消回调 */
 onCancel: () => void
 /** 确认回调 */
 onConfirm: () => void
 /** 标题 */
 title: string
 /** 描述文字 */
 description?: string
 /** 确认按钮文字，默认「确认」 */
 confirmLabel?: string
 /** 取消按钮文字，默认「取消」 */
 cancelLabel?: string
 /** 是否为破坏性操作（红色确认按钮） */
 destructive?: boolean
}

export default function ConfirmDialog({
 isOpen,
 onCancel,
 onConfirm,
 title,
 description,
 confirmLabel = '确认',
 cancelLabel = '取消',
 destructive = false,
}: ConfirmDialogProps) {
 const dialogRef = useRef<HTMLDivElement>(null)
 const titleId = `confirm-dialog-title-${useId()}`
 const previousFocusRef = useRef<HTMLElement | null>(null)

 // 焦点管理
 useEffect(() => {
 if (isOpen) {
 previousFocusRef.current = document.activeElement as HTMLElement
 requestAnimationFrame(() => {
 // 自动聚焦取消按钮（安全操作）
 const cancelBtn = dialogRef.current?.querySelector<HTMLButtonElement>(
 '[data-confirm-cancel]',
 )
 cancelBtn?.focus()
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
 onCancel()
 return
 }

 if (e.key === 'Tab' && dialogRef.current) {
 const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
 'button:not([disabled])',
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
 [onCancel],
 )

 if (!isOpen) return null

 return (
 <>
 {/* 半透明遮罩 — 点击不关闭（防误操作） */}
 <div
 className="fixed inset-0 z-50"
 style={{ backgroundColor: 'rgba(0, 0, 0, 0.4)' }}
 aria-hidden="true"
 />

 {/* 对话框 */}
 <div
 ref={dialogRef}
 role="alertdialog"
 aria-modal="true"
 aria-labelledby={titleId}
 tabIndex={-1}
 onKeyDown={handleKeyDown}
 className="fixed inset-0 z-50 flex items-center justify-center p-4 outline-none"
 >
 <div
 className="flex w-full max-w-[380px] flex-col rounded-[12px] p-5"
 style={{
 backgroundColor: 'var(--bg-base)',
 border: '1px solid var(--border-default)',
 animation: 'confirmDialogIn 150ms ease forwards',
 }}
 >
 {/* 标题 */}
 <h2
 id={titleId}
 className="text-[16px] font-semibold"
 style={{ color: 'var(--text-primary)', lineHeight: '24px' }}
 >
 {title}
 </h2>

 {/* 描述 */}
 {description && (
 <p
 className="mt-2 text-[13px]"
 style={{ color: 'var(--text-secondary)', lineHeight: '20px' }}
 >
 {description}
 </p>
 )}

 {/* 按钮组 */}
 <div className="mt-5 flex items-center justify-end gap-2">
 <Button
 variant="secondary"
 type="button"
 onClick={onCancel}
 data-confirm-cancel
 >
 {cancelLabel}
 </Button>
 <Button
 variant={destructive ? 'danger' : 'primary'}
 type="button"
 onClick={onConfirm}
 >
 {confirmLabel}
 </Button>
 </div>
 </div>
 </div>
 </>
 )
}
