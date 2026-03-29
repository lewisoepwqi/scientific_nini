import { startTransition } from "react";

/**
 * 对会触发懒加载挂起的 UI 切换，统一走预加载 + transition，
 * 避免在同步输入/点击事件中直接挂载 Suspense 边界。
 */
export function runDeferredUiUpdate(
  update: () => void,
  preload?: (() => Promise<unknown>) | null,
): void {
  if (preload) {
    void preload().catch(() => undefined);
  }
  startTransition(() => {
    update();
  });
}
