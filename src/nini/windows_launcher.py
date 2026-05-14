"""Windows GUI 启动器：静默拉起后台服务，并提供内嵌窗口与托盘宿主。"""

from __future__ import annotations

import argparse
from contextlib import suppress
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
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

    HCURSOR = wintypes.HANDLE
    HBRUSH = wintypes.HANDLE
    HMENU = wintypes.HANDLE
    UINT_PTR = wintypes.WPARAM
    LRESULT = wintypes.LPARAM
    ATOM = wintypes.WORD
    HMODULE = wintypes.HANDLE
    LPCRECT = ctypes.POINTER(wintypes.RECT)
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
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
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

    HCURSOR = object
    HBRUSH = object
    HMENU = object
    UINT_PTR = object
    LRESULT = object
    ATOM = object
    HMODULE = object
    LPCRECT = object
    WNDPROC = Callable[..., int]

    class WNDCLASSW(ctypes.Structure):
        pass

    class POINT(ctypes.Structure):
        pass

    class MSG(ctypes.Structure):
        pass

    class NOTIFYICONDATAW(ctypes.Structure):
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


class _EmbeddedWindowApp:
    """使用 pywebview 承载 WebView2 的桌面宿主。"""

    def __init__(
        self,
        *,
        install_root: Path,
        host: str,
        port: int,
        server_process: subprocess.Popen[bytes] | None,
    ) -> None:
        self.install_root = install_root
        self.host = host
        self.port = port
        self.server_process = server_process
        self._window = None
        self._exit_requested = threading.Event()
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

            from webview.menu import Menu, MenuAction, MenuSeparator  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

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
                import traceback  # noqa: PLC0415

                try:
                    native = getattr(self._window, "native", None)
                    webview2_ctl = getattr(native, "webview", None)
                    if webview2_ctl is None or webview2_ctl.CoreWebView2 is None:
                        print(
                            "[nini] 打开 DevTools 失败：WebView2 控件尚未就绪",
                            file=sys.stderr,
                        )
                        return

                    # 延迟到运行时再 import：pywebview 启动时已加载 .NET CLR，
                    # 此时 System 模块才在 sys.path 上可用。
                    from System import Action  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]  # noqa: PLC0415

                    def _do_open() -> None:
                        core = webview2_ctl.CoreWebView2
                        core.Settings.AreDevToolsEnabled = True
                        core.OpenDevToolsWindow()

                    webview2_ctl.Invoke(Action(_do_open))
                except Exception:
                    traceback.print_exc()

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

            app_menu = [
                Menu(
                    "文件",
                    [
                        MenuAction("新建会话\tCtrl+N", _new_session),
                        MenuSeparator(),
                        MenuAction("退出", self.request_exit),
                    ],
                ),
                Menu(
                    "视图",
                    [
                        MenuAction("开发者工具\tCtrl+Shift+I", _open_devtools),
                        MenuSeparator(),
                        MenuAction("重新加载\tCtrl+R", _reload),
                        MenuAction("强制重新加载\tCtrl+Shift+R", _hard_reload),
                        MenuSeparator(),
                        MenuAction("全屏\tF11", _toggle_fullscreen),
                    ],
                ),
                Menu(
                    "帮助",
                    [
                        MenuAction("查看日志", _open_log_file),
                        MenuSeparator(),
                        MenuAction("检查更新", _check_updates),
                    ],
                ),
            ]

            url = _build_app_url(self.host, self.port)
            state = _load_window_state()
            win_width = state.get("width", 1360)
            win_height = state.get("height", 920)
            try:
                self._window = webview.create_window(
                    "Nini",
                    url=url,
                    width=win_width,
                    height=win_height,
                    min_size=(1100, 720),
                    confirm_close=False,
                )
            except TypeError:
                self._window = webview.create_window(
                    "Nini",
                    url=url,
                    width=win_width,
                    height=win_height,
                )

            self._bind_events()
            self._tray.start_background()
            webview.start(gui="edgechromium", debug=False, menu=app_menu)
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

    def _bind_events(self) -> None:
        if self._window is None:
            return
        with suppress(Exception):
            self._window.events.closing += self._on_window_closing
        with suppress(Exception):
            self._window.events.closed += self._on_window_closed
        with suppress(Exception):
            self._window.events.resized += self._on_window_resized

    def _on_window_closing(self):
        """关闭主窗口时改为隐藏到托盘。"""
        if self._exit_requested.is_set():
            return True
        self.hide_window()
        return False

    def _on_window_closed(self):
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
        )
        return app.run()
    finally:
        if mutex_handle and mutex_handle != -1:
            with suppress(Exception):
                kernel32.CloseHandle(mutex_handle)


if __name__ == "__main__":
    raise SystemExit(main())
