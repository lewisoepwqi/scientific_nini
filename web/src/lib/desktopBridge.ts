/**
 * 桌面壳（pywebview）JS 桥接。
 *
 * 当 Nini 通过 Windows 桌面壳启动时，windows_launcher.py 把 _DesktopShellApi 实例
 * 暴露为 `window.pywebview.api.*`。在浏览器（--external-browser）或 Vite dev 模式下
 * 该对象不存在，所有函数返回 `false` / `null` 以便调用方做降级。
 */

interface DesktopShellApi {
  is_desktop_shell: () => Promise<boolean>;
  minimize: () => Promise<void>;
  toggle_maximize: () => Promise<{ maximized: boolean }>;
  close_to_tray: () => Promise<void>;
  request_exit: () => Promise<void>;
  open_devtools: () => Promise<void>;
  reload: () => Promise<void>;
  hard_reload: () => Promise<void>;
  toggle_fullscreen: () => Promise<void>;
  new_session: () => Promise<void>;
  check_updates: () => Promise<void>;
  open_log_file: () => Promise<void>;
}

declare global {
  interface Window {
    pywebview?: {
      api?: Partial<DesktopShellApi>;
    };
  }
}

function getApi(): Partial<DesktopShellApi> | null {
  if (typeof window === "undefined") return null;
  return window.pywebview?.api ?? null;
}

export function isDesktopShell(): boolean {
  return getApi() !== null;
}

/**
 * 等待 pywebview JS 桥就绪。pywebview 在页面加载后异步注入 `window.pywebview.api`，
 * 初次渲染时可能尚未挂载。带超时降级，浏览器模式直接返回 false。
 */
export function waitForDesktopShell(timeoutMs = 1500): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  if (isDesktopShell()) return Promise.resolve(true);
  return new Promise((resolve) => {
    const start = Date.now();
    const timer = setInterval(() => {
      if (isDesktopShell()) {
        clearInterval(timer);
        resolve(true);
        return;
      }
      if (Date.now() - start > timeoutMs) {
        clearInterval(timer);
        resolve(false);
      }
    }, 80);
  });
}

async function call<T = void>(method: keyof DesktopShellApi): Promise<T | null> {
  const api = getApi();
  const fn = api?.[method] as (() => Promise<T>) | undefined;
  if (!fn) return null;
  try {
    return await fn();
  } catch (err) {
    console.warn(`[desktopBridge] ${method} 调用失败`, err);
    return null;
  }
}

export const desktopBridge = {
  isAvailable: isDesktopShell,
  waitForReady: waitForDesktopShell,
  minimize: () => call("minimize"),
  toggleMaximize: () => call<{ maximized: boolean }>("toggle_maximize"),
  closeToTray: () => call("close_to_tray"),
  requestExit: () => call("request_exit"),
  openDevtools: () => call("open_devtools"),
  reload: () => call("reload"),
  hardReload: () => call("hard_reload"),
  toggleFullscreen: () => call("toggle_fullscreen"),
  newSession: () => call("new_session"),
  checkUpdates: () => call("check_updates"),
  openLogFile: () => call("open_log_file"),
};
