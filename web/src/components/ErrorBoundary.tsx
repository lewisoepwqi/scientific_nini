import React, { Component, type ErrorInfo, type ReactNode } from "react"
import Button from "./ui/Button"

type ErrorBoundaryProps = {
 children: ReactNode
}

type ErrorBoundaryState = {
 error: Error | null
 retryKey: number
}

export default class ErrorBoundary extends Component<
 ErrorBoundaryProps,
 ErrorBoundaryState
> {
 state: ErrorBoundaryState = {
 error: null,
 retryKey: 0,
 }

 static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
 return { error }
 }

 override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
 console.error("ErrorBoundary 捕获到渲染异常", error, errorInfo)
 }

 private handleRetry = (): void => {
 this.setState((state) => ({
 error: null,
 retryKey: state.retryKey + 1,
 }))
 }

 private handleReload = (): void => {
 if (typeof window !== "undefined") {
 window.location.reload()
 }
 }

 override render(): ReactNode {
 const { error, retryKey } = this.state

 if (error) {
 return (
 <div className="flex min-h-screen items-center justify-center bg-[var(--bg-elevated)] px-6 py-10">
 <div className="w-full max-w-lg rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] p-8 shadow-md">
 <div className="mb-4 inline-flex rounded-full border border-[var(--warning)] bg-[var(--accent-subtle)] px-3 py-1 text-xs font-medium text-[var(--warning)]">
 应用保护已生效
 </div>
 <h1 className="text-2xl font-semibold text-[var(--text-primary)]">页面暂时无法显示</h1>
 <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
 渲染过程中捕获到未处理异常。你可以先重试当前界面，或直接重新加载应用。
 </p>
 <div className="mt-5 rounded-lg bg-[var(--bg-elevated)] px-4 py-3 text-sm text-[var(--text-disabled)]">
 <div className="mb-1 text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">
 error
 </div>
 <div>{error.message || "未知错误"}</div>
 </div>
 <div className="mt-6 flex flex-wrap gap-3">
 <Button
 type="button"
 variant="primary"
 onClick={this.handleRetry}
 className="rounded-full px-4 py-2 text-sm font-medium"
 >
 重试
 </Button>
 <Button
 type="button"
 variant="secondary"
 onClick={this.handleReload}
 className="rounded-full px-4 py-2 text-sm font-medium"
 >
 重新加载
 </Button>
 </div>
 </div>
 </div>
 )
 }

 return <React.Fragment key={retryKey}>{this.props.children}</React.Fragment>
 }
}
