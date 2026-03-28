import React from 'react'
import { useStore } from '../../store'
import { type WsConnectionStatus } from '../../store/websocket-status'

/**
 * ConnectionBadge — WebSocket 连接状态指示器
 *
 * 三种视觉状态：
 * - connected / reconnecting（success/progress）：绿色实心圆 + "已连接"
 * - connecting / reconnecting（progress/warning）：脉冲动画圆 + "连接中"
 * - disconnected / failed（muted/danger）：红色实心圆 + "未连接"
 *
 * 高度 20px，圆点 6px，字号 11px
 * connecting 状态圆点 animate-pulse，prefers-reduced-motion 下禁用
 */

type BadgeState = 'connected' | 'connecting' | 'disconnected'

/** 将 WsConnectionStatus 映射为三种 Badge 视觉状态 */
function resolveBadgeState(status: WsConnectionStatus): BadgeState {
  switch (status) {
    case 'connected':
      return 'connected'
    case 'connecting':
    case 'reconnecting':
      return 'connecting'
    case 'disconnected':
    case 'failed':
    default:
      return 'disconnected'
  }
}

const STATE_CONFIG: Record<
  BadgeState,
  { label: string; dotColor: string; bgColor: string; textColor: string; pulse: boolean }
> = {
  connected: {
    label: '已连接',
    dotColor: 'var(--success)',
    bgColor: 'color-mix(in srgb, var(--success) 15%, transparent)',
    textColor: 'var(--success)',
    pulse: false,
  },
  connecting: {
    label: '连接中',
    dotColor: 'var(--warning)',
    bgColor: 'color-mix(in srgb, var(--warning) 15%, transparent)',
    textColor: 'var(--warning)',
    pulse: true,
  },
  disconnected: {
    label: '未连接',
    dotColor: 'var(--error)',
    bgColor: 'color-mix(in srgb, var(--error) 15%, transparent)',
    textColor: 'var(--error)',
    pulse: false,
  },
}

export interface ConnectionBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {}

export function ConnectionBadge({ className, ...props }: ConnectionBadgeProps) {
  const wsStatus = useStore((s) => s.wsStatus)
  const state = resolveBadgeState(wsStatus)
  const config = STATE_CONFIG[state]

  return (
    <span
      className={[
        'inline-flex items-center gap-1',
        'h-[20px] px-[8px] rounded-[var(--radius-sm)]',
        'text-[11px] leading-none font-medium',
        'whitespace-nowrap select-none',
        'motion-safe:transition-colors motion-safe:duration-100',
        className,
      ].join(' ')}
      style={{
        backgroundColor: config.bgColor,
        color: config.textColor,
      }}
      aria-live="polite"
      aria-label={config.label}
      role="status"
      {...props}
    >
      <span
        className={[
          'inline-block w-[6px] h-[6px] rounded-full shrink-0',
          config.pulse ? 'animate-pulse' : '',
        ].join(' ')}
        style={{ backgroundColor: config.dotColor }}
      />
      <span className="hidden sm:inline">{config.label}</span>
    </span>
  )
}

export default ConnectionBadge
