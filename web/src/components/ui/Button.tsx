import React from 'react'
import { Loader2 } from 'lucide-react'

/**
 * Button 组件 — 统一规范
 *
 * 四种 variant: primary / secondary / ghost / danger
 * 高度 28px (sm: 24px), 字号 12px, 圆角 6px, 字重 500
 * 所有颜色使用 CSS token，禁止硬编码
 */

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'default' | 'sm' | 'icon-sm' | 'icon-md' | 'icon-lg'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
 variant?: ButtonVariant
 size?: ButtonSize
 loading?: boolean
 icon?: React.ReactNode
}

const variantClasses: Record<ButtonVariant, string> = {
 primary:
 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] border-none',
 secondary:
 'bg-transparent text-[var(--text-primary)] border border-[var(--border-default)] hover:bg-[var(--bg-hover)]',
 ghost:
 'bg-transparent text-[var(--text-secondary)] border-none hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
 danger:
 'bg-[var(--error)] text-white border-none hover:opacity-90',
}

const sizeClasses: Record<ButtonSize, string> = {
 default: 'h-[28px] px-3',
 sm: 'h-[24px] px-2',
 'icon-sm': 'h-8 w-8 p-0 rounded-lg',
 'icon-md': 'h-9 w-9 p-0 rounded-xl',
 'icon-lg': 'h-10 w-10 p-0 rounded-2xl',
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
 (
 {
 variant = 'primary',
 size = 'default',
 loading = false,
 icon,
 disabled,
 className = '',
 children,
 ...props
 },
 ref,
 ) => {
 const isDisabled = disabled || loading

 return (
 <button
 ref={ref}
 disabled={isDisabled}
 className={[
 /* 基础样式 */
 'inline-flex items-center justify-center gap-1',
 'rounded-[6px] text-[12px] font-medium',
 'appearance-none border border-transparent',
 'transition-[background-color,color,border-color,box-shadow] duration-100 ease-linear',
 'select-none whitespace-nowrap',
 /* 禁用态 */
 isDisabled ? 'opacity-50 cursor-not-allowed pointer-events-none' : 'cursor-pointer',
 /* variant + size */
 variantClasses[variant],
 sizeClasses[size],
 className,
 ]
 .filter(Boolean)
 .join(' ')}
 {...props}
 >
 {loading ? (
 <Loader2 className="h-3.5 w-3.5 animate-spin" />
 ) : icon ? (
 <span className="inline-flex shrink-0">{icon}</span>
 ) : null}
 {children}
 </button>
 )
 },
)

Button.displayName = 'Button'

export default Button
