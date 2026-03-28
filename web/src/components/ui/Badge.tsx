import React from 'react'

/**
 * Badge 组件 — 统一规范
 *
 * 高度 18px, 字号 11px, 内边距 0 6px, 圆角 4px
 * variant: default / success / warning / error
 * 颜色使用对应功能色 token
 */

export type BadgeVariant = 'default' | 'success' | 'warning' | 'error'

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
 variant?: BadgeVariant
}

const variantClasses: Record<BadgeVariant, string> = {
 default:
 'bg-[var(--bg-overlay)] text-[var(--text-secondary)]',
 success:
 'bg-[var(--success)]/15 text-[var(--success)]',
 warning:
 'bg-[var(--warning)]/15 text-[var(--warning)]',
 error:
 'bg-[var(--error)]/15 text-[var(--error)]',
}

export function Badge({
 variant = 'default',
 className = '',
 children,
 ...props
}: BadgeProps) {
 return (
 <span
 className={[
 'inline-flex items-center',
 'h-[18px] px-[6px] rounded-[4px]',
 'text-[11px] leading-none font-medium',
 'whitespace-nowrap select-none',
 variantClasses[variant],
 className,
 ]
 .join(' ')}
 {...props}
 >
 {children}
 </span>
 )
}

export default Badge
