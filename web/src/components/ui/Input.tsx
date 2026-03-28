import React from 'react'

/**
 * Input 组件 — 统一规范
 *
 * 高度 28px, 字号 13px, 内边距 0 8px, 圆角 6px
 * 颜色全用 token
 * focus: border-color + box-shadow 0 0 0 1px var(--accent)
 * 支持 prefix/suffix icon slot
 */

export interface InputProps
 extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'prefix'> {
 /** 左侧图标 slot */
 prefix?: React.ReactNode
 /** 右侧图标 slot */
 suffix?: React.ReactNode
 inputRef?: React.Ref<HTMLInputElement>
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
 ({ prefix, suffix, inputRef, className = '', style, ...props }, _ref) => {
 const ref = inputRef ?? _ref

 /* 有图标时调整内边距 */
 const paddingLeft = prefix ? 'pl-8' : 'pl-[8px]'
 const paddingRight = suffix ? 'pr-8' : 'pr-[8px]'

 if (prefix || suffix) {
 return (
 <div className="relative inline-flex items-center w-full">
 {prefix && (
 <span className="absolute left-2 flex items-center pointer-events-none text-[var(--text-muted)]">
 {prefix}
 </span>
 )}
 <input
 ref={ref}
 className={[
 'w-full h-[28px] rounded-[6px] text-[13px]',
 'bg-[var(--bg-base)] text-[var(--text-primary)]',
 'border border-[var(--border-default)]',
 'outline-none',
 'transition-[border-color,box-shadow] duration-100 ease-linear',
 'placeholder:text-[var(--text-muted)]',
 'focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)]',
 paddingLeft,
 paddingRight,
 'disabled:opacity-50 disabled:cursor-not-allowed',
 className,
 ]
 .join(' ')}
 style={style}
 {...props}
 />
 {suffix && (
 <span className="absolute right-2 flex items-center pointer-events-none text-[var(--text-muted)]">
 {suffix}
 </span>
 )}
 </div>
 )
 }

 return (
 <input
 ref={ref}
 className={[
 'w-full h-[28px] rounded-[6px] text-[13px]',
 'px-[8px]',
 'bg-[var(--bg-base)] text-[var(--text-primary)]',
 'border border-[var(--border-default)]',
 'outline-none',
 'transition-[border-color,box-shadow] duration-100 ease-linear',
 'placeholder:text-[var(--text-muted)]',
 'focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)]',
 'disabled:opacity-50 disabled:cursor-not-allowed',
 className,
 ]
 .join(' ')}
 style={style}
 {...props}
 />
 )
 },
)

Input.displayName = 'Input'

export default Input
