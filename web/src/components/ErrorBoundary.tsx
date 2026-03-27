import React, { Component, type ErrorInfo, type ReactNode } from "react"

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
        <div className="flex min-h-screen items-center justify-center bg-slate-100 dark:bg-slate-800 px-6 py-10">
          <div className="w-full max-w-lg rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-8 shadow-xl shadow-slate-200/70">
            <div className="mb-4 inline-flex rounded-full border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-3 py-1 text-xs font-medium text-amber-700 dark:text-amber-400">
              应用保护已生效
            </div>
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">页面暂时无法显示</h1>
            <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
              渲染过程中捕获到未处理异常。你可以先重试当前界面，或直接重新加载应用。
            </p>
            <div className="mt-5 rounded-2xl bg-slate-950 dark:bg-slate-800 px-4 py-3 text-sm text-slate-100 dark:text-slate-200">
              <div className="mb-1 text-xs uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
                error
              </div>
              <div>{error.message || "未知错误"}</div>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={this.handleRetry}
                className="rounded-full bg-slate-900 dark:bg-slate-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 dark:hover:bg-slate-600"
              >
                重试
              </button>
              <button
                type="button"
                onClick={this.handleReload}
                className="rounded-full border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 transition hover:border-slate-400 dark:hover:border-slate-500 hover:text-slate-900 dark:hover:text-slate-100"
              >
                重新加载
              </button>
            </div>
          </div>
        </div>
      )
    }

    return <React.Fragment key={retryKey}>{this.props.children}</React.Fragment>
  }
}
