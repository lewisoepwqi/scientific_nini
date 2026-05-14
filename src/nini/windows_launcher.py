"""Windows GUI 启动器：静默拉起后台服务，并提供内嵌窗口与托盘宿主。"""

from __future__ import annotations

import argparse
from contextlib import suppress
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable, cast
import webbrowser
from urllib.parse import urlparse

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
    WM_QUIT = 0x0012
    WM_COMMAND = 0x0111
    WM_NCCALCSIZE = 0x0083
    WM_USER = 0x0400
    WM_APP = 0x8000
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    TPM_LEFTALIGN = 0x0000
    TPM_RETURNCMD = 0x0100
    MF_STRING = 0x0000
    MF_SEPARATOR = 0x0800
    NIM_ADD = 0x00000000
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    CS_HREDRAW = 0x0002
    CS_VREDRAW = 0x0001
    PM_REMOVE = 0x0001
    ID_TRAY_SHOW = 1001
    ID_TRAY_OPEN_BROWSER = 1002
    ID_TRAY_EXIT = 1003
    ID_TRAY_LOG = 1004
    ERROR_ALREADY_EXISTS = 183
    WM_APP_SHOW_WINDOW = WM_APP + 2
    IDI_APPLICATION = 32512
    IDC_ARROW = 32512
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    LR_DEFAULTSIZE = 0x0040
    WM_TRAYICON = WM_APP + 1
    GWL_WNDPROC = -4
    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    SWP_NOOWNERZORDER = 0x0200

    HCURSOR = wintypes.HANDLE
    HBRUSH = wintypes.HANDLE
    HMENU = wintypes.HANDLE
    UINT_PTR = wintypes.WPARAM
    LRESULT = wintypes.LPARAM
    ATOM = wintypes.WORD
    HMODULE = wintypes.HANDLE
    LPCRECT = ctypes.POINTER(wintypes.RECT)
    LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", HCURSOR),
            ("hbrBackground", HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", POINT),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", ctypes.c_byte * 16),
            ("hBalloonIcon", wintypes.HICON),
        ]

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [
            ("rgrc", wintypes.RECT * 3),
            ("lppos", ctypes.c_void_p),
        ]

    def _make_int_resource(resource_id: int):
        """将整数资源 ID 转成 Win32 可接受的 MAKEINTRESOURCEW 指针。"""
        return ctypes.cast(ctypes.c_void_p(resource_id & 0xFFFF), wintypes.LPCWSTR)

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = HMODULE

    user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadCursorW.restype = HCURSOR
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.CreatePopupMenu.restype = HMENU
    user32.AppendMenuW.argtypes = [HMENU, wintypes.UINT, UINT_PTR, wintypes.LPCWSTR]
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [HMENU]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [
        HMENU,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        LPCRECT,
    ]
    user32.TrackPopupMenu.restype = wintypes.UINT
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = LRESULT
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.CallWindowProcW.argtypes = [
        LONG_PTR,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.CallWindowProcW.restype = LRESULT
    if hasattr(user32, "SetWindowLongPtrW"):
        _set_window_long_ptr = user32.SetWindowLongPtrW
    else:
        _set_window_long_ptr = user32.SetWindowLongW
    _set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
    _set_window_long_ptr.restype = LONG_PTR
    if hasattr(user32, "GetWindowLongPtrW"):
        _get_window_long_ptr = user32.GetWindowLongPtrW
    else:
        _get_window_long_ptr = user32.GetWindowLongW
    _get_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_window_long_ptr.restype = LONG_PTR
    # 不设置 SetWindowPos.argtypes：pywebview 内部会在 SWP_NOSIZE 时传 None
    # 给 cx/cy。若这里全局绑定 int 类型，会把 pywebview 的拖拽实现打崩。
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
else:
    user32 = cast(Any, None)
    shell32 = cast(Any, None)
    kernel32 = cast(Any, None)

    WM_DESTROY = 0
    WM_CLOSE = 0
    WM_QUIT = 0
    WM_COMMAND = 0
    WM_NCCALCSIZE = 0
    WM_USER = 0
    WM_APP = 0
    WM_LBUTTONUP = 0
    WM_LBUTTONDBLCLK = 0
    WM_RBUTTONUP = 0
    TPM_LEFTALIGN = 0
    TPM_RETURNCMD = 0
    MF_STRING = 0
    MF_SEPARATOR = 0
    NIM_ADD = 0
    NIM_DELETE = 0
    NIF_MESSAGE = 0
    NIF_ICON = 0
    NIF_TIP = 0
    CS_HREDRAW = 0
    CS_VREDRAW = 0
    PM_REMOVE = 0
    ID_TRAY_SHOW = 0
    ID_TRAY_OPEN_BROWSER = 0
    ID_TRAY_EXIT = 0
    ID_TRAY_LOG = 0
    ERROR_ALREADY_EXISTS = 183
    WM_APP_SHOW_WINDOW = 0
    IDI_APPLICATION = 0
    IDC_ARROW = 0
    IMAGE_ICON = 0
    LR_LOADFROMFILE = 0
    LR_DEFAULTSIZE = 0
    WM_TRAYICON = 0
    GWL_WNDPROC = 0
    GWL_STYLE = 0
    WS_CAPTION = 0
    SWP_NOSIZE = 0
    SWP_NOMOVE = 0
    SWP_NOZORDER = 0
    SWP_NOACTIVATE = 0
    SWP_FRAMECHANGED = 0
    SWP_NOOWNERZORDER = 0

    HCURSOR = object
    HBRUSH = object
    HMENU = object
    UINT_PTR = object
    LRESULT = object
    ATOM = object
    HMODULE = object
    LPCRECT = object
    LONG_PTR = object
    WNDPROC = Callable[..., int]
    _set_window_long_ptr = cast(Any, None)
    _get_window_long_ptr = cast(Any, None)

    class WNDCLASSW(ctypes.Structure):
        pass

    class POINT(ctypes.Structure):
        pass

    class MSG(ctypes.Structure):
        pass

    class NOTIFYICONDATAW(ctypes.Structure):
        pass

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        pass

    def _make_int_resource(resource_id: int):
        return None


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """检测目标端口是否已监听。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pick_free_port(host: str) -> int:
    """在目标主机上申请一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    """等待目标端口就绪。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def _is_local_base_url(base_url: str) -> bool:
    """仅对本机 Ollama 地址启用自动拉起。"""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost"}


def _find_webview2_runtime() -> Path | None:
    """定位系统已安装的 WebView2 Runtime。"""
    suffix = Path("Microsoft") / "EdgeWebView" / "Application"
    roots = [
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramFiles", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in roots:
        if not root:
            continue
        app_root = Path(root) / suffix
        if not app_root.exists():
            continue
        for candidate in sorted(app_root.glob("*/msedgewebview2.exe"), reverse=True):
            if candidate.exists():
                return candidate
    return None


def _build_app_url(host: str, port: int) -> str:
    """构建桌面壳加载的本地地址。"""
    return f"http://{host}:{port}"


def _get_install_root() -> Path:
    """获取当前启动器的安装根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _build_server_command(
    cli_path: Path,
    *,
    host: str,
    port: int,
    log_level: str,
) -> list[str]:
    """构建后台服务启动命令。"""
    return [
        str(cli_path),
        "start",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        log_level,
        "--no-open",
    ]


def _get_windows_creationflags() -> int:
    """返回 Windows 无感后台启动所需 flags。"""
    new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return new_group | no_window


def _spawn_background_process(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[Any]:
    """以无控制台方式启动后台子进程，并保留句柄供退出时清理。"""
    kwargs: dict[str, Any] = {
        "args": command,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _get_windows_creationflags()
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(**kwargs)  # noqa: S603


def _show_error(message: str, title: str = "Nini") -> None:
    """在 GUI 模式下展示错误信息。"""
    if sys.platform == "win32":
        with suppress(Exception):
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
    print(message, file=sys.stderr)


def _show_missing_webview2_error() -> None:
    """提示 WebView2 Runtime 缺失。"""
    _show_error(
        "未检测到 Microsoft Edge WebView2 Runtime。\n"
        "请重新运行安装器，或手动安装 WebView2 Runtime 后再启动 Nini。",
        title="Nini 启动失败",
    )


def _start_bundled_ollama(install_root: Path, ollama_base_url: str) -> None:
    """若安装包包含便携版 Ollama，则静默拉起。"""
    if not _is_local_base_url(ollama_base_url):
        return

    parsed = urlparse(ollama_base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    if _is_port_open(host, port):
        return

    ollama_exe = install_root / "runtime" / "ollama" / "bin" / "ollama.exe"
    if not ollama_exe.exists():
        return

    env = dict(os.environ)
    env["OLLAMA_HOST"] = f"{host}:{port}"

    bundled_models = install_root / "runtime" / "ollama" / "models"
    if bundled_models.exists():
        env["OLLAMA_MODELS"] = str(bundled_models)

    _spawn_background_process([str(ollama_exe), "serve"], env=env)


def _open_browser(host: str, port: int) -> None:
    """打开前端页面。"""
    webbrowser.open(_build_app_url(host, port))


def _terminate_process(process: subprocess.Popen[bytes] | None, timeout: float = 8.0) -> None:
    """尽量平滑结束后台服务，失败时强制终止。"""
    if process is None:
        return
    if process.poll() is not None:
        return
    with suppress(Exception):
        process.terminate()
        process.wait(timeout=timeout)
        return
    with suppress(Exception):
        process.kill()
        process.wait(timeout=3)


_SINGLE_INSTANCE_MUTEX_NAME = "Global\\NiniSingleInstanceMutex"
_WINDOW_STATE_PATH = Path.home() / ".nini" / "window_state.json"


def _load_window_state() -> dict[str, int]:
    """读取上次保存的窗口尺寸；读取失败时返回空字典（使用默认值）。"""
    try:
        return json.loads(_WINDOW_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_window_state(width: int, height: int) -> None:
    """将当前窗口尺寸写入持久化文件。"""
    try:
        _WINDOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _WINDOW_STATE_PATH.write_text(
            json.dumps({"width": width, "height": height}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _acquire_single_instance_mutex() -> int | None:
    """尝试创建命名 Mutex。返回句柄表示本实例为第一个；返回 None 表示已有实例运行。"""
    if sys.platform != "win32":
        return -1  # 非 Windows 始终视为第一实例
    handle = kernel32.CreateMutexW(None, True, _SINGLE_INSTANCE_MUTEX_NAME)
    if not handle:
        return None
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _signal_existing_instance() -> None:
    """向已有 Nini 实例的托盘窗口发送显示消息。"""
    if sys.platform != "win32":
        return
    hwnd = user32.FindWindowW("NiniTrayWindow", None)
    if hwnd:
        user32.PostMessageW(hwnd, WM_APP_SHOW_WINDOW, 0, 0)


def _confirm_exit() -> bool:
    """弹出原生退出确认框，返回用户是否确认退出。非 Windows 环境始终返回 True。"""
    if sys.platform != "win32":
        return True
    IDYES = 6
    MB_YESNO = 0x00000004
    MB_ICONQUESTION = 0x00000020
    MB_SETFOREGROUND = 0x00010000
    result = user32.MessageBoxW(
        None,
        "确定要退出 Nini 吗？\n后台服务将会停止，所有进行中的任务将中断。",
        "退出 Nini",
        MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND,
    )
    return result == IDYES


def _get_log_path() -> Path | None:
    """返回当前 nini 日志文件路径；若不存在则返回 None。"""
    candidates = [
        Path.home() / ".nini" / "logs" / "nini.log",
        Path.home() / ".nini" / "nini.log",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _open_log_file() -> None:
    """用系统默认程序打开日志文件；若日志不存在则弹出提示。"""
    path = _get_log_path()
    if path is None:
        _show_error("未找到日志文件。\n请确认 Nini 已成功启动过至少一次。", title="查看日志")
        return
    if sys.platform == "win32":
        with suppress(Exception):
            os.startfile(str(path))


class _TrayApp:
    """最小可用的 Windows 托盘宿主。"""

    def __init__(
        self,
        *,
        install_root: Path,
        host: str,
        port: int,
        primary_label: str,
        primary_action: Callable[[], None] | None,
        watched_process: subprocess.Popen[bytes] | None = None,
        on_exit: Callable[[], None] | None = None,
        show_log_action: Callable[[], None] | None = None,
    ) -> None:
        self.install_root = install_root
        self.host = host
        self.port = port
        self.primary_label = primary_label
        self.primary_action = primary_action
        self.watched_process = watched_process
        self.on_exit = on_exit
        self.show_log_action = show_log_action
        self._hwnd: int | None = None
        self._class_name = "NiniTrayWindow"
        self._wnd_proc: Any = None
        self._notify_data: NOTIFYICONDATAW | None = None
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None

    def run(self) -> int:
        if sys.platform != "win32":
            return 0
        try:
            self._create_window()
            self._add_tray_icon()
            return self._message_loop()
        finally:
            self._remove_tray_icon()

    def start_background(self) -> None:
        """在后台线程启动托盘消息循环。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.run, name="nini-tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止托盘线程。"""
        self._stop_requested.set()
        if self._hwnd is not None:
            with suppress(Exception):
                user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _create_window(self) -> None:
        hinstance = kernel32.GetModuleHandleW(None)

        if sys.platform == "win32":

            @WNDPROC
            def _window_proc(hwnd, msg, wparam, lparam):
                if msg == WM_APP_SHOW_WINDOW:
                    if self.primary_action is not None:
                        threading.Thread(target=self.primary_action, daemon=True).start()
                    return 0
                if msg == WM_TRAYICON:
                    return self._handle_tray_event(hwnd, lparam)
                if msg == WM_COMMAND:
                    return self._handle_command(hwnd, wparam)
                if msg == WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        else:

            def _window_proc(hwnd, msg, wparam, lparam):
                return 0

        self._wnd_proc = _window_proc
        wnd_class = WNDCLASSW()
        wnd_class.style = CS_HREDRAW | CS_VREDRAW
        wnd_class.lpfnWndProc = self._wnd_proc
        wnd_class.cbClsExtra = 0
        wnd_class.cbWndExtra = 0
        wnd_class.hInstance = hinstance
        wnd_class.hIcon = self._load_icon()
        wnd_class.hCursor = user32.LoadCursorW(None, _make_int_resource(IDC_ARROW))
        wnd_class.hbrBackground = 0
        wnd_class.lpszMenuName = None
        wnd_class.lpszClassName = self._class_name
        user32.RegisterClassW(ctypes.byref(wnd_class))
        hwnd = user32.CreateWindowExW(
            0,
            self._class_name,
            "Nini Tray",
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            hinstance,
            None,
        )
        if not hwnd:
            raise OSError("创建托盘窗口失败")
        self._hwnd = hwnd

    def _load_icon(self):
        icon_path = self.install_root / "nini.ico"
        if icon_path.exists():
            icon = user32.LoadImageW(
                None,
                str(icon_path),
                IMAGE_ICON,
                0,
                0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            if icon:
                return icon
        return user32.LoadIconW(None, _make_int_resource(IDI_APPLICATION))

    def _add_tray_icon(self) -> None:
        if self._hwnd is None:
            return
        notify_data = NOTIFYICONDATAW()
        notify_data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        notify_data.hWnd = self._hwnd
        notify_data.uID = 1
        notify_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        notify_data.uCallbackMessage = WM_TRAYICON
        notify_data.hIcon = self._load_icon()
        notify_data.szTip = "Nini 正在后台运行"
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(notify_data))
        self._notify_data = notify_data

    def _remove_tray_icon(self) -> None:
        if self._notify_data is not None:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._notify_data))
            self._notify_data = None

    def _message_loop(self) -> int:
        msg = MSG()
        while not self._stop_requested.is_set():
            while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE) != 0:
                if msg.message == WM_QUIT:
                    return 0
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if self.watched_process is not None and self.watched_process.poll() is not None:
                self._stop_requested.set()
                if self.on_exit is not None:
                    with suppress(Exception):
                        self.on_exit()
                break
            time.sleep(0.1)
        return 0

    def _handle_tray_event(self, hwnd: int, event_code: int) -> int:
        if event_code in {WM_LBUTTONUP, WM_LBUTTONDBLCLK}:
            if self.primary_action is not None:
                self.primary_action()
            else:
                _open_browser(self.host, self.port)
            return 0
        if event_code == WM_RBUTTONUP:
            self._show_menu(hwnd)
            return 0
        return 0

    def _handle_command(self, hwnd: int, wparam: int) -> int:
        command_id = wparam & 0xFFFF
        if command_id == ID_TRAY_SHOW:
            if self.primary_action is not None:
                self.primary_action()
            else:
                _open_browser(self.host, self.port)
            return 0
        if command_id == ID_TRAY_OPEN_BROWSER:
            _open_browser(self.host, self.port)
            return 0
        if command_id == ID_TRAY_LOG:
            if self.show_log_action is not None:
                self.show_log_action()
            return 0
        if command_id == ID_TRAY_EXIT:
            if not _confirm_exit():
                return 0
            self._stop_requested.set()
            if self.on_exit is not None:
                with suppress(Exception):
                    self.on_exit()
            user32.DestroyWindow(hwnd)
            return 0
        return 0

    def _show_menu(self, hwnd: int) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_SHOW, self.primary_label)
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_OPEN_BROWSER, "在浏览器中打开")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_LOG, "查看日志")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_EXIT, "退出 Nini")
            point = POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(hwnd)
            selected = user32.TrackPopupMenu(
                menu,
                TPM_LEFTALIGN | TPM_RETURNCMD,
                point.x,
                point.y,
                0,
                hwnd,
                None,
            )
            if selected:
                user32.PostMessageW(hwnd, WM_COMMAND, selected, 0)
        finally:
            user32.DestroyMenu(menu)


class _DesktopShellApi:
    """暴露给前端自绘标题栏的 JS 桥接对象。

    pywebview 把实例上的可调用属性映射到 ``window.pywebview.api.<name>(...)``，
    回调统一返回 None 或简单字典（pywebview 会自动 JSON 序列化）。最大化/最小化
    通过 pywebview 5.x 的 ``window.maximize/minimize`` 实现；不可用时退化到 WinForms
    的 ``WindowState`` 属性。
    """

    def __init__(
        self,
        *,
        host_app: "_EmbeddedWindowApp",
        open_devtools: Callable[[], None],
        reload_: Callable[[], None],
        hard_reload: Callable[[], None],
        toggle_fullscreen: Callable[[], None],
        new_session: Callable[[], None],
        check_updates: Callable[[], None],
        open_log_file: Callable[[], None],
    ) -> None:
        self._host = host_app
        self._open_devtools = open_devtools
        self._reload = reload_
        self._hard_reload = hard_reload
        self._toggle_fullscreen = toggle_fullscreen
        self._new_session = new_session
        self._check_updates = check_updates
        self._open_log_file = open_log_file

    # --- 窗口控制 -----------------------------------------------------------
    def is_desktop_shell(self) -> bool:
        return True

    def minimize(self) -> None:
        window = self._host._window
        if window is None:
            return
        # pywebview 5.x: 优先直接调用 minimize；旧版本退化到 WinForms。
        if hasattr(window, "minimize"):
            with suppress(Exception):
                window.minimize()
                return
        self._set_winforms_state("Minimized")

    def toggle_maximize(self) -> dict[str, bool]:
        window = self._host._window
        maximized = False
        if window is not None:
            if self._is_winforms_maximized():
                # 还原
                if hasattr(window, "restore"):
                    with suppress(Exception):
                        window.restore()
                else:
                    self._set_winforms_state("Normal")
                maximized = False
            else:
                # 最大化（pywebview 5.3+ 提供 maximize；老版本走 WinForms）
                if hasattr(window, "maximize"):
                    with suppress(Exception):
                        window.maximize()
                        maximized = True
                if not maximized:
                    self._set_winforms_state("Maximized")
                    maximized = self._is_winforms_maximized()
        return {"maximized": maximized}

    def close_to_tray(self) -> None:
        """模拟点击系统关闭按钮：触发 closing 事件，隐藏到托盘。"""
        self._host.hide_window()

    def request_exit(self) -> None:
        """从应用菜单退出整个桌面壳。"""
        self._host.request_exit()

    # --- 菜单项 -------------------------------------------------------------
    def open_devtools(self) -> None:
        self._open_devtools()

    def reload(self) -> None:
        self._reload()

    def hard_reload(self) -> None:
        self._hard_reload()

    def toggle_fullscreen(self) -> None:
        self._toggle_fullscreen()

    def new_session(self) -> None:
        self._new_session()

    def check_updates(self) -> None:
        self._check_updates()

    def open_log_file(self) -> None:
        self._open_log_file()

    # --- WinForms 兜底 ------------------------------------------------------
    def _winforms_form(self) -> Any:
        window = self._host._window
        if window is None:
            return None
        return getattr(window, "native", None)

    def _set_winforms_state(self, state: str) -> None:
        form = self._winforms_form()
        if form is None:
            return
        try:
            from System.Windows.Forms import FormWindowState  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

            mapping = {
                "Minimized": FormWindowState.Minimized,
                "Maximized": FormWindowState.Maximized,
                "Normal": FormWindowState.Normal,
            }
            target = mapping.get(state)
            if target is None:
                return
            form.BeginInvoke(lambda: setattr(form, "WindowState", target))
        except Exception:
            pass

    def _is_winforms_maximized(self) -> bool:
        form = self._winforms_form()
        if form is None:
            return False
        try:
            from System.Windows.Forms import FormWindowState  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

            return bool(form.WindowState == FormWindowState.Maximized)
        except Exception:
            return False


class _EmbeddedWindowApp:
    """使用 pywebview 承载 WebView2 的桌面宿主。"""

    def __init__(
        self,
        *,
        install_root: Path,
        host: str,
        port: int,
        server_process: subprocess.Popen[bytes] | None,
        debug: bool = False,
    ) -> None:
        self.install_root = install_root
        self.host = host
        self.port = port
        self.server_process = server_process
        self.debug = debug
        self._window: Any = None
        self._exit_requested = threading.Event()
        self._resize_old_wnd_proc: int | None = None
        self._resize_wnd_proc: Any = None
        self._resize_hwnd: int | None = None
        self._tray = _TrayApp(
            install_root=install_root,
            host=host,
            port=port,
            primary_label="显示主窗口",
            primary_action=self.show_window,
            watched_process=server_process,
            on_exit=self.request_exit,
            show_log_action=_open_log_file,
        )

    def run(self) -> int:
        try:
            if _find_webview2_runtime() is None:
                _show_missing_webview2_error()
                return 1

            try:
                import webview  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]
            except ImportError:
                _show_error(
                    "当前安装包缺少 pywebview 依赖。\n"
                    "请重新执行打包流程，或暂时使用 `nini.exe --external-browser` 排查问题。",
                    title="Nini 启动失败",
                )
                return 1

            webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True

            def _open_devtools() -> None:
                """启用并打开 WebView2 DevTools 面板。

                关键约束：
                1. pywebview 的菜单回调显式在子线程执行（见 winforms.py:set_window_menu），
                   而 WebView2 / WinForms 控件方法必须在 UI 线程调用，因此需要通过
                   `webview2_ctl.Invoke(...)` marshal 回 UI 线程。
                2. pywebview 在 debug=False 启动时把 `AreDevToolsEnabled` 设为 False，
                   `OpenDevToolsWindow()` 即使调用成功也会被静默丢弃；这里在 UI 线程上
                   先开启 settings 再打开 DevTools。
                3. 通过公开属性 `Window.native`（pywebview 设定的 BrowserForm 实例）拿
                   WebView2 控件，避免依赖私有 `_js_bridge` 路径。
                失败时把异常打印到 stderr，方便开发模式下定位问题。
                """
                threading.Thread(
                    target=self._schedule_open_devtools,
                    name="nini-open-devtools",
                    daemon=True,
                ).start()

            def _reload() -> None:
                with suppress(Exception):
                    self._window.evaluate_js("location.reload()")  # type: ignore[attr-defined]

            def _hard_reload() -> None:
                with suppress(Exception):
                    self._window.evaluate_js("window.location.href = window.location.href")  # type: ignore[attr-defined]

            def _toggle_fullscreen() -> None:
                with suppress(Exception):
                    self._window.toggle_fullscreen()  # type: ignore[attr-defined]

            def _new_session() -> None:
                with suppress(Exception):
                    self._window.evaluate_js(  # type: ignore[attr-defined]
                        "window.dispatchEvent(new CustomEvent('nini:new-session'))"
                    )

            def _check_updates() -> None:
                with suppress(Exception):
                    self._window.evaluate_js(  # type: ignore[attr-defined]
                        "window.dispatchEvent(new CustomEvent('nini:check-updates'))"
                    )

            # 将原 pywebview 原生菜单回调封装成 JS API，前端自绘标题栏调用。
            # 详见 web/src/components/TitleBar.tsx 与 web/src/lib/desktopBridge.ts。
            app_api = _DesktopShellApi(
                host_app=self,
                open_devtools=_open_devtools,
                reload_=_reload,
                hard_reload=_hard_reload,
                toggle_fullscreen=_toggle_fullscreen,
                new_session=_new_session,
                check_updates=_check_updates,
                open_log_file=_open_log_file,
            )

            url = _build_app_url(self.host, self.port)
            state = _load_window_state()
            win_width = state.get("width", 1360)
            win_height = state.get("height", 920)
            create_kwargs: dict[str, Any] = {
                "url": url,
                "width": win_width,
                "height": win_height,
                "min_size": (1100, 720),
                "confirm_close": False,
                # 使用 pywebview 原生窗口框架（FormBorderStyle.Sizable）：
                # 原生标题栏 / 缩放边框 / 最小化最大化关闭 / 拖动全部由系统负责。
                "frameless": False,
                "easy_drag": False,
                "js_api": app_api,
            }
            try:
                self._window = webview.create_window("Nini", **create_kwargs)
            except TypeError:
                # 老版本 pywebview 不支持部分参数（min_size / frameless / js_api），
                # 退化到最小可用集合：标题 + URL + 尺寸。
                self._window = webview.create_window(
                    "Nini",
                    url=url,
                    width=win_width,
                    height=win_height,
                )

            self._bind_events()
            self._tray.start_background()

            # 打包模式：持久化用户数据（localStorage / Cookie 跨会话保留）。
            # 开发模式：每次强制删除并重建 WebView2 数据目录，彻底防止旧版
            # index.html 被 HTTP 缓存，避免资产哈希不匹配导致 MIME 报错黑屏。
            if getattr(sys, "frozen", False):
                webview2_data_dir = Path.home() / ".nini" / "webview2"
                webview2_data_dir.mkdir(parents=True, exist_ok=True)
                webview.start(
                    gui="edgechromium",
                    debug=self.debug,
                    private_mode=False,
                    storage_path=str(webview2_data_dir),
                )
            else:
                dev_data_dir = Path.home() / ".nini" / "webview2_dev"
                shutil.rmtree(dev_data_dir, ignore_errors=True)
                dev_data_dir.mkdir(parents=True, exist_ok=True)
                webview.start(
                    gui="edgechromium",
                    debug=self.debug,
                    private_mode=False,
                    storage_path=str(dev_data_dir),
                )
            return 0
        except Exception as exc:
            _show_error(
                "启动内嵌窗口失败："
                f"{exc}\n"
                "请确认 WebView2 Runtime 安装完整，或使用 `nini.exe --external-browser` 排查。",
                title="Nini 启动失败",
            )
            return 1
        finally:
            self._exit_requested.set()
            self._tray.stop()
            _terminate_process(self.server_process)

    def _schedule_open_devtools(self) -> None:
        """后台投递 DevTools 打开动作，避免阻塞 JS bridge。"""
        import traceback  # noqa: PLC0415

        try:
            native = getattr(self._window, "native", None)
            webview2_ctl = getattr(native, "webview", None)
            if webview2_ctl is None:
                print("[nini] 打开 DevTools 失败：WebView2 控件尚未就绪", file=sys.stderr)
                return

            from System import Action  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

            def _do_open() -> None:
                try:
                    core = webview2_ctl.CoreWebView2
                    if core is None:
                        print(
                            "[nini] 打开 DevTools 失败：WebView2 Core 尚未就绪",
                            file=sys.stderr,
                        )
                        return
                    core.Settings.AreDevToolsEnabled = True
                    core.OpenDevToolsWindow()
                except Exception:
                    traceback.print_exc()

            webview2_ctl.BeginInvoke(Action(_do_open))
        except Exception:
            traceback.print_exc()

    def _install_caption_strip(self) -> None:
        """隐藏原生标题栏，但保留原生缩放边框。

        ``frameless=False`` 给了完整的原生窗口框架（标题栏 + 四周缩放边框）。这里
        子类化 WndProc 处理 ``WM_NCCALCSIZE``：DefWindowProc 默认会从顶部多扣掉一个
        标题栏高度，导致客户区顶部留出一条非客户区残留（表现为黑边）。这里把顶部
        的内缩量重新对齐到与左右边框一致——标题栏区域归还给客户区，顶部仅保留与
        左右下相同的细缩放边框。该做法直接由几何关系推导，与 DPI 无关。窗口拖动由
        前端自绘标题栏的 ``-webkit-app-region: drag``（WebView2
        IsNonClientRegionSupportEnabled）负责。最大化时不剥离，避免破坏 WinForms 的
        最大化布局。
        """
        if sys.platform != "win32" or self._resize_wnd_proc is not None:
            return
        native = getattr(self._window, "native", None)
        hwnd = self._native_hwnd(native)
        if hwnd is None:
            return

        @WNDPROC
        def _caption_proc(hwnd_value, msg, wparam, lparam):
            old = self._resize_old_wnd_proc
            if msg == WM_NCCALCSIZE and wparam and old is not None:
                params = ctypes.cast(
                    ctypes.c_void_p(lparam),
                    ctypes.POINTER(NCCALCSIZE_PARAMS),
                )
                # rgrc[0] 进入时是新窗口矩形，DefWindowProc 处理后变为客户区矩形。
                win_top = int(params.contents.rgrc[0].top)
                result = user32.CallWindowProcW(old, hwnd_value, msg, wparam, lparam)
                if not self._window_is_maximized():
                    with suppress(Exception):
                        # 顶部内缩归零：客户区直达窗口顶边，顶部不再有非客户区，
                        # 从根上消除被 DWM 渲染成深色标题栏框的黑边残留。左右下仍
                        # 保留细缩放边框，配合 WS_THICKFRAME 提供四角与左右下三边的
                        # 原生缩放（顶部两角经左右边框区命中）；仅失去纯顶边缩放。
                        params.contents.rgrc[0].top = win_top
                return result
            if old is None:
                return user32.DefWindowProcW(hwnd_value, msg, wparam, lparam)
            return user32.CallWindowProcW(old, hwnd_value, msg, wparam, lparam)

        proc_ptr = ctypes.cast(_caption_proc, ctypes.c_void_p).value
        if proc_ptr is None:
            return
        old_proc = _set_window_long_ptr(hwnd, GWL_WNDPROC, proc_ptr)
        if old_proc:
            self._resize_hwnd = hwnd
            self._resize_old_wnd_proc = int(old_proc)
            self._resize_wnd_proc = _caption_proc
            # 去掉 WS_CAPTION：保留 WS_CAPTION 时 DefWindowProc 仍会把顶部非客户区
            # 当作标题栏框绘制（表现为黑边）；移除后系统只画四周统一的细缩放边框，
            # 缩放能力来自仍保留的 WS_THICKFRAME。
            with suppress(Exception):
                style = int(_get_window_long_ptr(hwnd, GWL_STYLE))
                new_style = style & ~WS_CAPTION
                if new_style != style:
                    _set_window_long_ptr(hwnd, GWL_STYLE, new_style)
            # 立即触发一次 NCCALCSIZE 重算，让标题栏马上消失。
            with suppress(Exception):
                user32.SetWindowPos(
                    wintypes.HWND(hwnd),
                    None,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE
                    | SWP_NOSIZE
                    | SWP_NOZORDER
                    | SWP_NOACTIVATE
                    | SWP_NOOWNERZORDER
                    | SWP_FRAMECHANGED,
                )

    def _window_is_maximized(self) -> bool:
        """判断宿主 WinForms 窗口是否最大化。"""
        native = getattr(self._window, "native", None)
        if native is None:
            return False
        try:
            from System.Windows.Forms import FormWindowState  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

            return bool(native.WindowState == FormWindowState.Maximized)
        except Exception:
            return False

    def _restore_native_wnd_proc(self) -> None:
        """窗口关闭前恢复原始 WndProc。"""
        if (
            sys.platform != "win32"
            or self._resize_hwnd is None
            or self._resize_old_wnd_proc is None
        ):
            return
        with suppress(Exception):
            _set_window_long_ptr(self._resize_hwnd, GWL_WNDPROC, self._resize_old_wnd_proc)
        self._resize_hwnd = None
        self._resize_old_wnd_proc = None
        self._resize_wnd_proc = None

    @staticmethod
    def _native_hwnd(native: Any) -> int | None:
        """从 WinForms Form 中取出 HWND。"""
        handle = getattr(native, "Handle", None)
        if handle is None:
            return None
        with suppress(Exception):
            return int(handle.ToInt64())
        with suppress(Exception):
            return int(handle.ToInt32())
        with suppress(Exception):
            return int(handle)
        return None

    def _bind_events(self) -> None:
        if self._window is None:
            return
        with suppress(Exception):
            self._window.events.closing += self._on_window_closing
        with suppress(Exception):
            self._window.events.closed += self._on_window_closed
        with suppress(Exception):
            self._window.events.resized += self._on_window_resized
        with suppress(Exception):
            self._window.events.loaded += self._on_window_loaded

    def _on_window_loaded(self) -> None:
        """每次页面加载完成后，隐藏原生标题栏并启用 WebView2 CSS 拖拽区域支持。

        ``_install_caption_strip`` 通过 WndProc 子类隐藏原生标题栏（保留缩放边框）；
        WebView2 的 IsNonClientRegionSupportEnabled 让前端自绘标题栏的 CSS
        ``-webkit-app-region: drag`` 被识别为可拖动区域，从而能拖动整个窗口。
        """
        import traceback  # noqa: PLC0415

        try:
            native = getattr(self._window, "native", None)
            webview2_ctl = getattr(native, "webview", None)
            if webview2_ctl is None:
                return
            self._install_caption_strip()
            from System import Action  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

            def _enable() -> None:
                try:
                    core = webview2_ctl.CoreWebView2
                    if core is not None:
                        core.Settings.IsNonClientRegionSupportEnabled = True
                        core.CallDevToolsProtocolMethodAsync(
                            "Overlay.setShowViewportSizeOnResize",
                            '{"show":false}',
                        )
                except Exception:
                    pass  # 旧版 WebView2 SDK 不支持此属性，忽略

            webview2_ctl.BeginInvoke(Action(_enable))
        except Exception:
            traceback.print_exc()

    def _on_window_closing(self):
        """关闭主窗口时改为隐藏到托盘。"""
        if self._exit_requested.is_set():
            return True
        self.hide_window()
        return False

    def _on_window_closed(self):
        self._restore_native_wnd_proc()
        self._exit_requested.set()

    def show_window(self) -> None:
        if self._window is None:
            return
        with suppress(Exception):
            self._window.show()
        with suppress(Exception):
            self._window.restore()
        with suppress(Exception):
            self._window.bring_to_front()

    def _on_window_resized(self) -> None:
        if self._window is None:
            return
        with suppress(Exception):
            _save_window_state(self._window.width, self._window.height)

    def hide_window(self) -> None:
        if self._window is None:
            return
        with suppress(Exception):
            self._window.hide()

    def request_exit(self) -> None:
        self._exit_requested.set()
        if self._window is None:
            return
        with suppress(Exception):
            self._window.destroy()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nini Windows 启动器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="监听端口；默认自动选择空闲端口",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        help="等待后端启动成功的秒数",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="后台服务日志级别",
    )
    parser.add_argument(
        "--external-browser",
        action="store_true",
        help="使用外部浏览器打开，不启动内嵌桌面窗口",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="http://127.0.0.1:11434",
        help="便携版 Ollama 自动拉起地址",
    )
    parser.add_argument(
        "--cli-name",
        default="nini-cli.exe" if sys.platform == "win32" else "nini-cli",
        help="后台 CLI 可执行文件名",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用 WebView2 调试模式（DevTools 可用，控制台输出错误）",
    )
    return parser


def _resolve_runtime_port(host: str, requested_port: int) -> int:
    """解析本次桌面壳使用的监听端口。"""
    if requested_port > 0:
        return requested_port
    return _pick_free_port(host)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    mutex_handle = _acquire_single_instance_mutex()
    if mutex_handle is None:
        _signal_existing_instance()
        return 0
    try:
        install_root = _get_install_root()
        cli_path = install_root / args.cli_name
        host = args.host
        port = _resolve_runtime_port(host, args.port)

        if port <= 0:
            _show_error("无法为 Nini 分配本地监听端口。")
            return 1

        if not cli_path.exists() and not getattr(sys, "frozen", False):
            # 开发模式：回退到 PATH 中的 nini 脚本
            fallback = shutil.which("nini")
            if fallback:
                cli_path = Path(fallback)
        if not cli_path.exists():
            _show_error(f"未找到后台启动文件：{cli_path}")
            return 1

        existing_service = args.port > 0 and _is_port_open(host, port)
        server_process: subprocess.Popen[bytes] | None = None

        if not existing_service:
            _start_bundled_ollama(install_root, args.ollama_base_url)
            try:
                server_process = _spawn_background_process(
                    _build_server_command(
                        cli_path,
                        host=host,
                        port=port,
                        log_level=args.log_level,
                    )
                )
            except OSError as exc:
                _show_error(f"启动后台服务失败：{exc}")
                return 1

            if not _wait_for_port(host, port, args.startup_timeout):
                _terminate_process(server_process)
                _show_error(
                    "Nini 后台服务未在预期时间内就绪。\n"
                    "可手动运行 nini-cli.exe start 查看日志并排查问题。"
                )
                return 1

        if args.external_browser:
            _open_browser(host, port)
            tray = _TrayApp(
                install_root=install_root,
                host=host,
                port=port,
                primary_label="打开 Nini",
                primary_action=lambda: _open_browser(host, port),
                watched_process=server_process,
                show_log_action=_open_log_file,
            )
            try:
                return tray.run()
            finally:
                _terminate_process(server_process)

        app = _EmbeddedWindowApp(
            install_root=install_root,
            host=host,
            port=port,
            server_process=server_process,
            debug=args.debug,
        )
        return app.run()
    finally:
        if mutex_handle and mutex_handle != -1:
            with suppress(Exception):
                kernel32.CloseHandle(mutex_handle)


if __name__ == "__main__":
    raise SystemExit(main())
