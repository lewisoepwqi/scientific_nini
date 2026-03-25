import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import ErrorBoundary from "./ErrorBoundary"

describe("ErrorBoundary", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it("应捕获渲染异常并展示降级 UI，重试后可恢复渲染", () => {
    let shouldThrow = true

    const ProblemChild = () => {
      if (shouldThrow) {
        throw new Error("渲染失败")
      }
      return <div>恢复成功</div>
    }

    render(
      <ErrorBoundary>
        <ProblemChild />
      </ErrorBoundary>,
    )

    expect(screen.getByText("页面暂时无法显示")).toBeInTheDocument()
    expect(screen.getByText("渲染失败")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "重新加载" })).toBeInTheDocument()

    shouldThrow = false
    fireEvent.click(screen.getByRole("button", { name: "重试" }))

    expect(screen.getByText("恢复成功")).toBeInTheDocument()
    expect(consoleErrorSpy).toHaveBeenCalled()
  })
})
