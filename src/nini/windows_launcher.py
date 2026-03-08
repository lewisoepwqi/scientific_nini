"""Windows GUI 启动器：静默拉起后台服务，并以系统托盘常驻。"""

from __future__ import annotations

import argparse
from contextlib import suppress
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import webbrowser
from urllib.parse import urlparse

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
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
    NIM_MODIFY = 0x00000001
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    CS_HREDRAW = 0x0002
    CS_VREDRAW = 0x0001
    ID_TRAY_OPEN = 1001
    ID_TRAY_EXIT = 1002
    IDI_APPLICATION = 32512
    IDC_ARROW = 32512
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    LR_DEFAULTSIZE = 0x0040
    WM_TRAYICON = WM_APP + 1
    CW_USEDEFAULT = 0x80000000

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

    # 明确声明 Win32 API 签名，避免不同 Python/Windows 组合下宽字符参数被错误传递。
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
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """检测目标端口是否已监听。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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
) -> subprocess.Popen[bytes]:
    """以无控制台方式启动后台子进程，并保留句柄供托盘退出时清理。"""
    kwargs: dict[str, object] = {
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
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
    print(message, file=sys.stderr)


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
    webbrowser.open(f"http://{host}:{port}")


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


class _TrayApp:
    """最小可用的 Windows 托盘宿主。"""

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
        self._hwnd: int | None = None
        self._class_name = "NiniTrayWindow"
        self._wnd_proc = None
        self._notify_data: NOTIFYICONDATAW | None = None

    def run(self) -> int:
        if sys.platform != "win32":
            return 0
        try:
            self._create_window()
            self._add_tray_icon()
            return self._message_loop()
        finally:
            self._remove_tray_icon()
            _terminate_process(self.server_process)

    def _create_window(self) -> None:
        hinstance = kernel32.GetModuleHandleW(None)

        @WNDPROC
        def _window_proc(hwnd, msg, wparam, lparam):
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
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
            if self.server_process is not None and self.server_process.poll() is not None:
                break
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        return 0

    def _handle_tray_event(self, hwnd: int, event_code: int) -> int:
        if event_code in {WM_LBUTTONUP, WM_LBUTTONDBLCLK}:
            _open_browser(self.host, self.port)
            return 0
        if event_code == WM_RBUTTONUP:
            self._show_menu(hwnd)
            return 0
        return 0

    def _handle_command(self, hwnd: int, wparam: int) -> int:
        command_id = wparam & 0xFFFF
        if command_id == ID_TRAY_OPEN:
            _open_browser(self.host, self.port)
            return 0
        if command_id == ID_TRAY_EXIT:
            user32.DestroyWindow(hwnd)
            return 0
        return 0

    def _show_menu(self, hwnd: int) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_OPEN, "打开 Nini")
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nini Windows 启动器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        help="等待后端启动成功的秒数",
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="后台服务日志级别",
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


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    install_root = Path(sys.executable).resolve().parent
    cli_path = install_root / args.cli_name

    if _is_port_open(args.host, args.port):
        _open_browser(args.host, args.port)
        return 0

    if not cli_path.exists():
        _show_error(f"未找到后台启动文件：{cli_path}")
        return 1

    _start_bundled_ollama(install_root, args.ollama_base_url)

    try:
        server_process = _spawn_background_process(
            _build_server_command(
                cli_path,
                host=args.host,
                port=args.port,
                log_level=args.log_level,
            )
        )
    except OSError as exc:
        _show_error(f"启动后台服务失败：{exc}")
        return 1

    if not _wait_for_port(args.host, args.port, args.startup_timeout):
        _terminate_process(server_process)
        _show_error(
            "Nini 后台服务未在预期时间内就绪。\n"
            "可手动运行 nini-cli.exe start 查看日志并排查问题。"
        )
        return 1

    _open_browser(args.host, args.port)
    return _TrayApp(
        install_root=install_root,
        host=args.host,
        port=args.port,
        server_process=server_process,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
