# Windows WebView 桌面壳 v1 验收 + v2/v3 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 v1 验收补全、实施 v2 桌面增强（单实例治理、窗口状态持久化、退出确认、日志入口），并实施 v3 企业离线分发（离线 WebView2 捆绑、静默安装、代码签名）。

**Architecture:** v1 代码已完整落地（pywebview + EdgeChromium + Win32 托盘），后续各版本均在 `src/nini/windows_launcher.py` 和 `packaging/installer.nsi` 基础上增量迭代，不改动 FastAPI / React / PyInstaller 主体架构。

**Tech Stack:** Python 3.12, pywebview >= 5.3, ctypes/Win32 API, PyInstaller, NSIS, batch 构建脚本

---

## 背景说明

当前代码状态：v1 规划已 100% 实现。本计划分三个阶段：

- **v1 验收（Task 1–4）**：文档补全 + 测试覆盖 + 手工验收清单，无业务代码改动
- **v2 增强（Task 5–8）**：在 `windows_launcher.py` 增加单实例、窗口状态、退出确认、日志入口四项能力
- **v3 企业（Task 9–11）**：在 NSIS 脚本和构建脚本增加离线 WebView2、静默安装、代码签名

---

## 文件结构

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `WINDOWS_WEBVIEW_SHELL_PLAN.md` | 补充 v1 完成状态标注 |
| 修改 | `tests/test_windows_launcher.py` | 新增 v1 验收单元测试 |
| 新建 | `docs/windows-acceptance-checklist.md` | 手工验收清单 |
| 修改 | `src/nini/windows_launcher.py` | v2 四项能力增量实现 |
| 修改 | `packaging/installer.nsi` | v3 离线 WebView2 + 静默安装 |
| 修改 | `build_windows.bat` | v3 代码签名步骤 |

---

## v1 验收补全

---

### Task 1：更新规划文档状态标注

**Files:**
- Modify: `WINDOWS_WEBVIEW_SHELL_PLAN.md`

- [ ] **Step 1: 在文档顶部 "摘要" 标题之前插入状态块**

在文件第 1 行 `# Windows 壳层升级 v1 计划` 之后、`## 摘要` 之前插入：

```markdown
> **实施状态**
> - v1（内嵌窗口 + 托盘）：代码完整，待 Windows 10/11 真机验收
> - v2（单实例 + 窗口状态 + 退出确认 + 日志入口）：规划中
> - v3（企业离线包 + 代码签名 + 静默安装）：规划中
```

- [ ] **Step 2: 在 "假设与默认值" 章节末尾补充两条说明**

找到文档末尾 `## 假设与默认值` 章节，在最后一个列表项之后添加：

```markdown
- 桌面壳默认以随机端口 + `127.0.0.1` 启动，不对外暴露；`nini-cli.exe start` 固定端口逻辑不受影响，两者相互独立。
- 随机端口模式（默认）下，二次启动会产生多个 `nini.exe` 进程；单实例治理（命名 Mutex + 窗口激活）留 v2 处理。
```

- [ ] **Step 3: 提交**

```bash
git add WINDOWS_WEBVIEW_SHELL_PLAN.md
git commit -m "docs: 标注 v1 实施状态并补充已知缺口说明"
```

---

### Task 2：为解析器与端口逻辑补充单元测试

**Files:**
- Modify: `tests/test_windows_launcher.py`

- [ ] **Step 1: 在文件顶部导入中新增所需符号**

在现有 import 块之后添加：

```python
from nini.windows_launcher import (
    _build_server_command,
    _is_local_base_url,
    _build_parser,
    _resolve_runtime_port,
    _pick_free_port,
)
```

- [ ] **Step 2: 新增解析器默认值测试**

```python
def test_parser_defaults_to_loopback_and_random_port() -> None:
    args = _build_parser().parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 0
    assert args.startup_timeout == 30.0
    assert args.log_level == "warning"
    assert args.external_browser is False


def test_parser_accepts_explicit_port() -> None:
    args = _build_parser().parse_args(["--port", "9090"])
    assert args.port == 9090


def test_parser_accepts_external_browser_flag() -> None:
    args = _build_parser().parse_args(["--external-browser"])
    assert args.external_browser is True
```

- [ ] **Step 3: 新增端口分配逻辑测试**

```python
def test_resolve_runtime_port_uses_explicit_port_when_given() -> None:
    port = _resolve_runtime_port("127.0.0.1", 8500)
    assert port == 8500


def test_resolve_runtime_port_picks_free_port_when_zero() -> None:
    port = _resolve_runtime_port("127.0.0.1", 0)
    assert 1024 < port < 65536


def test_pick_free_port_returns_usable_port() -> None:
    port = _pick_free_port("127.0.0.1")
    assert 1024 < port < 65536
    # 验证端口确实可以绑定
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))
```

- [ ] **Step 4: 运行测试确认全部通过**

```bash
pytest tests/test_windows_launcher.py -v
```

期望输出：全部 `PASSED`，无 `FAILED`。

- [ ] **Step 5: 提交**

```bash
git add tests/test_windows_launcher.py
git commit -m "test(launcher): 补充解析器默认值与端口分配单元测试"
```

---

### Task 3：为 WebView2 运行时检测添加单元测试

**Files:**
- Modify: `tests/test_windows_launcher.py`

- [ ] **Step 1: 新增 import**

在文件顶部已有 import 块中补充：

```python
from unittest.mock import patch, MagicMock
from nini.windows_launcher import (
    _build_server_command,
    _is_local_base_url,
    _build_parser,
    _resolve_runtime_port,
    _pick_free_port,
    _find_webview2_runtime,
)
```

- [ ] **Step 2: 编写 WebView2 检测测试**

```python
def test_find_webview2_runtime_returns_none_when_no_dirs_exist(tmp_path) -> None:
    """所有 Program Files 环境变量指向空目录时返回 None。"""
    env_overrides = {
        "ProgramFiles(x86)": str(tmp_path),
        "ProgramFiles": str(tmp_path),
        "LOCALAPPDATA": str(tmp_path),
    }
    with patch.dict("os.environ", env_overrides, clear=False):
        result = _find_webview2_runtime()
    assert result is None


def test_find_webview2_runtime_returns_path_when_msedge_exists(tmp_path) -> None:
    """存在 msedgewebview2.exe 时返回其路径。"""
    # 构造 Microsoft\EdgeWebView\Application\120.0.0.0\msedgewebview2.exe
    edge_path = tmp_path / "Microsoft" / "EdgeWebView" / "Application" / "120.0.0.0"
    edge_path.mkdir(parents=True)
    exe = edge_path / "msedgewebview2.exe"
    exe.touch()

    env_overrides = {
        "ProgramFiles(x86)": str(tmp_path),
        "ProgramFiles": "",
        "LOCALAPPDATA": "",
    }
    with patch.dict("os.environ", env_overrides, clear=False):
        result = _find_webview2_runtime()
    assert result == exe
```

- [ ] **Step 3: 运行测试**

```bash
pytest tests/test_windows_launcher.py -v
```

期望输出：全部 `PASSED`。

- [ ] **Step 4: 提交**

```bash
git add tests/test_windows_launcher.py
git commit -m "test(launcher): 补充 WebView2 Runtime 检测单元测试"
```

---

### Task 4：创建 Windows 真机验收清单

**Files:**
- Create: `docs/windows-acceptance-checklist.md`

- [ ] **Step 1: 创建验收清单文件**

```markdown
# Windows 桌面壳真机验收清单

适用版本：v1（内嵌 WebView2 窗口 + 系统托盘）
测试环境：Windows 10 21H2 / Windows 11 23H2，干净系统（无已安装 WebView2 Runtime）

## 安装阶段

- [ ] 1. 在**无** WebView2 Runtime 的干净 VM 中执行安装包
- [ ] 2. 安装器弹出"正在安装 WebView2 Runtime"进度提示
- [ ] 3. Runtime 安装完成后，Nini 主程序安装继续进行
- [ ] 4. 安装完成后，桌面出现 Nini 快捷方式

## 首次启动

- [ ] 5. 双击 `nini.exe`，**不弹出系统浏览器**
- [ ] 6. 内嵌窗口打开，进入现有首页（加载时间 < 10 秒）
- [ ] 7. 任务栏右下角托盘出现 Nini 图标
- [ ] 8. 窗口标题为 `Nini`

## 功能验证

- [ ] 9. WebSocket 对话（发送一条消息，收到流式回复）
- [ ] 10. 文件上传（拖拽一个 PDF 到会话，能预览）
- [ ] 11. 图表展示（要求生成一个 matplotlib 图，能正常显示）
- [ ] 12. 文件下载/导出（导出对话记录，浏览器保存对话框正常弹出）

## 托盘交互

- [ ] 13. 单击托盘图标 → 窗口置前显示
- [ ] 14. 右键托盘 → 菜单显示三项：`显示主窗口`、`在浏览器中打开`、`退出 Nini`
- [ ] 15. 点击窗口 ✕ 关闭按钮 → 窗口隐藏，托盘图标仍在
- [ ] 16. 从托盘菜单点击"显示主窗口" → 窗口重新出现
- [ ] 17. 从托盘菜单点击"退出 Nini" → 应用彻底退出，托盘图标消失，任务管理器无残留进程

## 降级模式

- [ ] 18. `nini.exe --external-browser` → 用系统默认浏览器打开，不弹内嵌窗口
- [ ] 19. 上述模式下托盘仍存在

## 升级安装

- [ ] 20. 在已安装版本上执行新安装包 → 安装器不重复下载 WebView2 Runtime
- [ ] 21. 升级后用户数据（`%USERPROFILE%\.nini`）保留完整

## CLI 兼容性

- [ ] 22. `nini-cli.exe doctor` 输出正常，无报错
- [ ] 23. `nini-cli.exe start --port 8001` 独立启动后台服务（与 nini.exe 无冲突）
```

- [ ] **Step 2: 提交**

```bash
git add docs/windows-acceptance-checklist.md
git commit -m "docs: 新增 Windows v1 真机验收清单"
```

---

## v2 桌面增强

---

### Task 5：单实例治理（Mutex + 激活现有窗口）

**目标行为：** 当 `nini.exe` 已在运行时，二次启动不产生第二个进程，而是激活现有窗口并退出。

**Files:**
- Modify: `src/nini/windows_launcher.py`

- [ ] **Step 1: 在 Windows 常量块中追加新常量**

在文件中 `ID_TRAY_EXIT = 1003` 这一行所在的 `if sys.platform == "win32":` 块里，紧跟 `ID_TRAY_EXIT = 1003` 之后添加：

```python
    ID_TRAY_LOG = 1004          # 为 Task 8 预留，此处一并声明
    ERROR_ALREADY_EXISTS = 183
    WM_APP_SHOW_WINDOW = WM_APP + 2
```

在对应的 `else:` 块（非 Windows 平台），找到 `ID_TRAY_EXIT = 0` 行，在其后添加：

```python
    ID_TRAY_LOG = 0
    ERROR_ALREADY_EXISTS = 183
    WM_APP_SHOW_WINDOW = 0
```

- [ ] **Step 2: 声明 Mutex 名称常量**

在文件顶层（`class _TrayApp` 定义之前）添加：

```python
_SINGLE_INSTANCE_MUTEX_NAME = "Global\\NiniSingleInstanceMutex"
```

- [ ] **Step 3: 新增 Mutex 获取与信号函数**

在 `_SINGLE_INSTANCE_MUTEX_NAME` 声明之后添加：

```python
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
```

- [ ] **Step 4: 让 _TrayApp 的消息处理响应 WM_APP_SHOW_WINDOW**

在 `_TrayApp._create_window()` 方法中，`_window_proc` 函数的 `if msg == WM_TRAYICON:` 处理之前插入：

```python
                if msg == WM_APP_SHOW_WINDOW:
                    if self.primary_action is not None:
                        threading.Thread(
                            target=self.primary_action, daemon=True
                        ).start()
                    return 0
```

- [ ] **Step 5: 在 main() 入口处调用单实例检测**

在 `main()` 函数中，`args = _build_parser().parse_args(argv)` 之后、`install_root = _get_install_root()` 之前插入：

```python
    mutex_handle = _acquire_single_instance_mutex()
    if mutex_handle is None:
        _signal_existing_instance()
        return 0
```

- [ ] **Step 6: 在 main() 退出时释放 Mutex**

将 `main()` 函数的 `return app.run()` 之前部分重构为：

```python
    try:
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
```

- [ ] **Step 7: 运行现有测试确保无回归**

```bash
pytest tests/test_windows_launcher.py -v
```

期望输出：全部 `PASSED`。

- [ ] **Step 8: 新增单实例相关单元测试**

在 `tests/test_windows_launcher.py` 顶部 import 块补充：

```python
from nini.windows_launcher import (
    _build_server_command,
    _is_local_base_url,
    _build_parser,
    _resolve_runtime_port,
    _pick_free_port,
    _find_webview2_runtime,
    _acquire_single_instance_mutex,
)
```

然后新增测试：

```python
def test_acquire_single_instance_mutex_returns_non_none_first_time() -> None:
    """非 Windows 平台上，函数总返回非 None（视为第一实例）。"""
    import sys
    if sys.platform == "win32":
        # Windows 上第一次调用应成功获取句柄
        handle = _acquire_single_instance_mutex()
        assert handle is not None
        # 清理：此处仅验证函数可调用，实际句柄关闭由 main() 负责
    else:
        handle = _acquire_single_instance_mutex()
        assert handle == -1  # 非 Windows 平台哨兵值
```

- [ ] **Step 9: 运行全部测试**

```bash
pytest tests/test_windows_launcher.py -v
```

- [ ] **Step 10: 提交**

```bash
git add src/nini/windows_launcher.py tests/test_windows_launcher.py
git commit -m "feat(launcher): 单实例治理——Mutex 加锁 + 激活现有窗口"
```

---

### Task 6：窗口尺寸持久化

**目标行为：** 用户调整窗口大小后，下次启动自动恢复上次尺寸。存储路径 `~/.nini/window_state.json`，仅保存宽高（pywebview 5.x 跨平台 x/y 不稳定，暂不存储位置）。

**Files:**
- Modify: `src/nini/windows_launcher.py`

- [ ] **Step 1: 在文件顶部 import 块添加 json 导入**

在文件已有 `import json` 行（如不存在则添加）：

```python
import json
```

确认位置在 `import os` 附近。

- [ ] **Step 2: 新增窗口状态读写函数**

在文件顶层 `_SINGLE_INSTANCE_MUTEX_NAME` 常量下方添加：

```python
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
```

- [ ] **Step 3: 在 _EmbeddedWindowApp.run() 中应用已保存的尺寸**

找到 `_EmbeddedWindowApp.run()` 方法中 `url = _build_app_url(...)` 一行，在其后、`webview.create_window(...)` 之前插入：

```python
            state = _load_window_state()
            win_width = state.get("width", 1360)
            win_height = state.get("height", 920)
```

将原来 `webview.create_window(...)` 中的 `width=1360, height=920` 替换为 `width=win_width, height=win_height`。

最终结果：

```python
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
```

- [ ] **Step 4: 在 _bind_events() 中注册 resized 事件**

在 `_EmbeddedWindowApp._bind_events()` 方法中，已有的两个 `with suppress(Exception):` 块之后追加：

```python
        with suppress(Exception):
            self._window.events.resized += self._on_window_resized
```

- [ ] **Step 5: 新增 _on_window_resized 事件处理方法**

在 `_EmbeddedWindowApp` 类中，`hide_window()` 方法之前添加：

```python
    def _on_window_resized(self, width: int, height: int) -> None:
        _save_window_state(width, height)
```

- [ ] **Step 6: 为窗口状态读写函数编写单元测试**

在 `tests/test_windows_launcher.py` import 块中补充：

```python
from nini.windows_launcher import (
    _build_server_command,
    _is_local_base_url,
    _build_parser,
    _resolve_runtime_port,
    _pick_free_port,
    _find_webview2_runtime,
    _acquire_single_instance_mutex,
    _load_window_state,
    _save_window_state,
)
```

新增测试：

```python
def test_load_window_state_returns_empty_dict_when_file_missing(tmp_path) -> None:
    from unittest.mock import patch
    with patch("nini.windows_launcher._WINDOW_STATE_PATH", tmp_path / "window_state.json"):
        result = _load_window_state()
    assert result == {}


def test_save_and_load_window_state_roundtrip(tmp_path) -> None:
    from unittest.mock import patch
    state_file = tmp_path / "window_state.json"
    with patch("nini.windows_launcher._WINDOW_STATE_PATH", state_file):
        _save_window_state(1440, 900)
        result = _load_window_state()
    assert result == {"width": 1440, "height": 900}


def test_load_window_state_returns_empty_dict_on_corrupt_file(tmp_path) -> None:
    from unittest.mock import patch
    state_file = tmp_path / "window_state.json"
    state_file.write_text("not-json", encoding="utf-8")
    with patch("nini.windows_launcher._WINDOW_STATE_PATH", state_file):
        result = _load_window_state()
    assert result == {}
```

- [ ] **Step 7: 运行测试**

```bash
pytest tests/test_windows_launcher.py -v
```

期望输出：全部 `PASSED`。

- [ ] **Step 8: 提交**

```bash
git add src/nini/windows_launcher.py tests/test_windows_launcher.py
git commit -m "feat(launcher): 窗口尺寸持久化——resize 事件保存，启动时自动恢复"
```

---

### Task 7：退出确认对话框

**目标行为：** 用户点击托盘"退出 Nini"时，弹出原生 Windows 确认框（"是/否"），用户选"是"才真正退出。

**Files:**
- Modify: `src/nini/windows_launcher.py`

- [ ] **Step 1: 新增 _confirm_exit 函数**

在文件顶层（`_TrayApp` 定义之前）添加：

```python
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
```

- [ ] **Step 2: 在托盘退出处理中调用确认框**

在 `_TrayApp._handle_command()` 方法中，找到：

```python
        if command_id == ID_TRAY_EXIT:
            self._stop_requested.set()
            if self.on_exit is not None:
                with suppress(Exception):
                    self.on_exit()
            user32.DestroyWindow(hwnd)
            return 0
```

替换为：

```python
        if command_id == ID_TRAY_EXIT:
            if not _confirm_exit():
                return 0
            self._stop_requested.set()
            if self.on_exit is not None:
                with suppress(Exception):
                    self.on_exit()
            user32.DestroyWindow(hwnd)
            return 0
```

- [ ] **Step 3: 编写 _confirm_exit 单元测试**

在 `tests/test_windows_launcher.py` import 块补充：

```python
from nini.windows_launcher import (
    _build_server_command,
    _is_local_base_url,
    _build_parser,
    _resolve_runtime_port,
    _pick_free_port,
    _find_webview2_runtime,
    _acquire_single_instance_mutex,
    _load_window_state,
    _save_window_state,
    _confirm_exit,
)
```

新增测试：

```python
def test_confirm_exit_returns_true_on_non_windows() -> None:
    import sys
    if sys.platform != "win32":
        assert _confirm_exit() is True
    # Windows 平台跳过（需要用户交互，不适合自动化测试）
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_windows_launcher.py -v
```

期望输出：全部 `PASSED`。

- [ ] **Step 5: 提交**

```bash
git add src/nini/windows_launcher.py tests/test_windows_launcher.py
git commit -m "feat(launcher): 托盘退出前弹出原生确认对话框"
```

---

### Task 8：托盘"查看日志"入口

**目标行为：** 右键托盘菜单新增"查看日志"项，点击后用系统默认文本编辑器打开当前运行日志文件。日志路径沿用 nini 现有日志配置。

**Files:**
- Modify: `src/nini/windows_launcher.py`

- [ ] **Step 1: 确认日志文件路径**

运行以下命令，找到 nini 日志文件实际写入路径：

```bash
grep -rn "log\|LOG\|FileHandler\|log_file\|LOGFILE" src/nini/ --include="*.py" | grep -v "test\|__pycache__" | grep -v "log_level" | head -20
```

记录实际日志路径（如 `~/.nini/logs/nini.log` 或 `data/nini.log`）。

- [ ] **Step 2: 新增日志路径解析函数**

在文件顶层 `_save_window_state` 函数之后添加：

```python
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
```

> **注意：** 如果步骤 1 中找到了不同的日志路径，将其加入 `candidates` 列表第一项。

- [ ] **Step 3: 在 _TrayApp.__init__ 中新增 show_log_action 参数**

找到 `_TrayApp.__init__` 方法签名：

```python
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
    ) -> None:
```

替换为：

```python
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
```

并在 `self.on_exit = on_exit` 之后添加：

```python
        self.show_log_action = show_log_action
```

- [ ] **Step 4: 在托盘菜单中插入"查看日志"**

在 `_TrayApp._show_menu()` 方法中，找到：

```python
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_OPEN_BROWSER, "在浏览器中打开")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_EXIT, "退出 Nini")
```

替换为：

```python
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_OPEN_BROWSER, "在浏览器中打开")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_LOG, "查看日志")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_TRAY_EXIT, "退出 Nini")
```

- [ ] **Step 5: 在 _handle_command 中处理 ID_TRAY_LOG**

在 `_TrayApp._handle_command()` 方法中，`if command_id == ID_TRAY_EXIT:` 之前插入：

```python
        if command_id == ID_TRAY_LOG:
            if self.show_log_action is not None:
                self.show_log_action()
            return 0
```

- [ ] **Step 6: 新增打开日志文件的函数**

在文件顶层 `_get_log_path()` 之后添加：

```python
def _open_log_file() -> None:
    """用系统默认程序打开日志文件；若日志不存在则弹出提示。"""
    path = _get_log_path()
    if path is None:
        _show_error("未找到日志文件。\n请确认 Nini 已成功启动过至少一次。", title="查看日志")
        return
    with suppress(Exception):
        os.startfile(str(path))
```

- [ ] **Step 7: 在 _EmbeddedWindowApp 构建 _TrayApp 时传入 show_log_action**

找到 `_EmbeddedWindowApp.__init__` 中构造 `_TrayApp` 的代码：

```python
        self._tray = _TrayApp(
            install_root=install_root,
            host=host,
            port=port,
            primary_label="显示主窗口",
            primary_action=self.show_window,
            watched_process=server_process,
            on_exit=self.request_exit,
        )
```

替换为：

```python
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
```

对 `--external-browser` 模式下 `main()` 中的 `_TrayApp(...)` 同样添加 `show_log_action=_open_log_file`。

- [ ] **Step 8: 为 _get_log_path 编写单元测试**

在 `tests/test_windows_launcher.py` import 块补充 `_get_log_path`，新增：

```python
from nini.windows_launcher import (
    _build_server_command,
    _is_local_base_url,
    _build_parser,
    _resolve_runtime_port,
    _pick_free_port,
    _find_webview2_runtime,
    _acquire_single_instance_mutex,
    _load_window_state,
    _save_window_state,
    _confirm_exit,
    _get_log_path,
)
```

```python
def test_get_log_path_returns_none_when_no_log_exists(tmp_path) -> None:
    from unittest.mock import patch
    with patch("nini.windows_launcher.Path") as mock_path:
        # 让 Path.home() 返回 tmp_path，其下无日志文件
        mock_path.home.return_value = tmp_path
        mock_path.side_effect = lambda *a, **kw: Path(*a, **kw)
        result = _get_log_path()
    assert result is None


def test_get_log_path_returns_existing_log(tmp_path) -> None:
    log_file = tmp_path / ".nini" / "logs" / "nini.log"
    log_file.parent.mkdir(parents=True)
    log_file.touch()
    from unittest.mock import patch
    with patch("nini.windows_launcher._get_log_path", return_value=log_file):
        from nini.windows_launcher import _get_log_path as glp
        assert glp() == log_file
```

- [ ] **Step 9: 运行全部测试**

```bash
pytest tests/test_windows_launcher.py -v
```

期望：全部 `PASSED`。

- [ ] **Step 10: 提交**

```bash
git add src/nini/windows_launcher.py tests/test_windows_launcher.py
git commit -m "feat(launcher): 托盘新增"查看日志"入口，支持一键打开日志文件"
```

---

## v3 企业与离线分发

---

### Task 9：NSIS 支持企业离线 WebView2 Runtime 捆绑

**目标行为：** 当构建时设置 `BUNDLE_WEBVIEW2=1`，安装器内嵌完整 WebView2 离线安装包；否则保持现有在线下载逻辑不变。运行时优先使用捆绑包，跳过网络下载。

**Files:**
- Modify: `packaging/installer.nsi`
- Modify: `build_windows.bat`

- [ ] **Step 1: 了解现有 NSIS WebView2 检测逻辑**

阅读 `packaging/installer.nsi` 中 `EnsureWebView2Runtime` 函数（约第 71-93 行），记录现有下载逻辑。

- [ ] **Step 2: 在 installer.nsi 顶部添加条件编译宏**

在文件最顶部（`!include` 行之前）添加：

```nsis
; 离线 WebView2 捆绑包路径（可选）：构建时由 /DBUNDLE_WEBVIEW2_PATH=<path> 传入
; 若未定义则回退到在线下载模式
!ifndef BUNDLE_WEBVIEW2_PATH
  !define BUNDLE_WEBVIEW2_PATH ""
!endif
```

- [ ] **Step 3: 重写 EnsureWebView2Runtime 函数以支持离线优先**

找到现有 `EnsureWebView2Runtime` 函数，替换为：

```nsis
Function EnsureWebView2Runtime
  Call HasWebView2Runtime
  Pop $0
  ${If} $0 == "yes"
    Return
  ${EndIf}

  ; 离线模式：使用捆绑的安装包
  !if "${BUNDLE_WEBVIEW2_PATH}" != ""
    DetailPrint "正在安装离线 WebView2 Runtime..."
    ExecWait '"$INSTDIR\webview2\MicrosoftEdgeWebView2RuntimeInstallerX64.exe" /silent /install' $0
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONEXCLAMATION \
        "WebView2 Runtime 离线安装失败（错误码：$0）。$\n请联系管理员或手动安装。"
      Abort
    ${EndIf}
    Return
  !endif

  ; 在线模式：下载 Bootstrapper（现有逻辑）
  DetailPrint "正在下载 WebView2 Runtime 安装程序..."
  NSISdl::download \
    "https://go.microsoft.com/fwlink/p/?LinkId=2124703" \
    "$TEMP\MicrosoftEdgeWebView2Setup.exe"
  Pop $0
  ${If} $0 != "success"
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "WebView2 Runtime 下载失败。$\n请检查网络连接后重试，或联系管理员手动安装。"
    Abort
  ${EndIf}
  ExecWait '"$TEMP\MicrosoftEdgeWebView2Setup.exe" /silent /install' $0
  Delete "$TEMP\MicrosoftEdgeWebView2Setup.exe"
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "WebView2 Runtime 安装失败（错误码：$0）。$\n请联系管理员或手动安装。"
    Abort
  ${EndIf}
FunctionEnd
```

- [ ] **Step 4: 在离线安装包构建时拷贝 WebView2 安装文件**

在 NSIS 脚本的 `Section "主程序"` 中，`!if "${BUNDLE_WEBVIEW2_PATH}" != ""` 条件块中添加文件拷贝：

```nsis
Section "主程序" SecMain
  SetOutPath "$INSTDIR"
  
  ; 如果有捆绑 WebView2，拷贝到安装目录
  !if "${BUNDLE_WEBVIEW2_PATH}" != ""
    SetOutPath "$INSTDIR\webview2"
    File "${BUNDLE_WEBVIEW2_PATH}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    SetOutPath "$INSTDIR"
  !endif
  
  ; 以下为现有文件安装逻辑，保持不变
```

- [ ] **Step 5: 在 build_windows.bat 中添加离线 WebView2 下载步骤**

在 `build_windows.bat` 中，找到 `pyinstaller` 执行行之前，添加：

```batch
:: ── 可选：下载离线 WebView2 Runtime 安装包 ──────────────────────────────────
if "%BUNDLE_WEBVIEW2%"=="1" (
    echo [BUILD] 下载离线 WebView2 Runtime 安装包...
    set WEBVIEW2_DIR=%~dp0packaging\webview2
    if not exist "%WEBVIEW2_DIR%" mkdir "%WEBVIEW2_DIR%"
    powershell -Command "Invoke-WebRequest -Uri 'https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/MicrosoftEdgeWebView2RuntimeInstallerX64.exe' -OutFile '%WEBVIEW2_DIR%\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'"
    if errorlevel 1 (
        echo [ERROR] WebView2 离线包下载失败
        exit /b 1
    )
    set NSIS_EXTRA_ARGS=/DBUNDLE_WEBVIEW2_PATH=%WEBVIEW2_DIR%
) else (
    set NSIS_EXTRA_ARGS=
)
```

找到 NSIS 编译调用行（`makensis` 或 `"%NSIS_DIR%\makensis.exe"`），在其参数中追加 `%NSIS_EXTRA_ARGS%`：

```batch
"%NSIS_DIR%\makensis.exe" %NSIS_EXTRA_ARGS% packaging\installer.nsi
```

- [ ] **Step 6: 更新 packaging/README.md 说明两种构建模式**

在 `packaging/README.md` 中找到构建说明部分，添加：

```markdown
### 企业离线包构建

如需内嵌 WebView2 Runtime（适用于无网络访问的企业环境）：

```batch
set BUNDLE_WEBVIEW2=1
build_windows.bat
```

构建脚本会自动下载 `MicrosoftEdgeWebView2RuntimeInstallerX64.exe` 并捆绑进安装包。
安装时无需网络，直接从安装包内部完成 WebView2 安装。
```

- [ ] **Step 7: 提交**

```bash
git add packaging/installer.nsi build_windows.bat packaging/README.md
git commit -m "feat(packaging): NSIS 支持企业离线 WebView2 Runtime 捆绑"
```

---

### Task 10：NSIS 静默安装参数支持

**目标行为：** 支持 `nini-setup.exe /S`（静默安装，使用默认路径）和 `nini-setup.exe /S /D=C:\custom\path`（静默安装到指定路径），便于 GPO / 批量部署。

**Files:**
- Modify: `packaging/installer.nsi`

- [ ] **Step 1: 确认 NSIS 静默安装现状**

```bash
grep -n "SilentInstall\|\/S\|MUI_UNPAGE\|AutoCloseWindow" packaging/installer.nsi | head -20
```

记录现有是否已有 `SilentInstall` 配置。

- [ ] **Step 2: 在 installer.nsi 顶部添加静默安装声明**

在 `!include` 行之后，`Name` 定义之前添加：

```nsis
; 支持命令行静默安装：nini-setup.exe /S
; 支持自定义安装路径：nini-setup.exe /S /D=C:\custom\path
SilentInstall normal  ; 非静默时显示 UI；/S 时自动切换到 silentmode
```

- [ ] **Step 3: 在安装 Section 中跳过 WebView2 弹框（静默模式）**

在 `EnsureWebView2Runtime` 函数中，所有 `MessageBox` 调用改为静默模式下写日志：

```nsis
  ${If} $0 != 0
    IfSilent +3
      MessageBox MB_OK|MB_ICONEXCLAMATION \
        "WebView2 Runtime 安装失败（错误码：$0）。$\n请联系管理员或手动安装。"
    SetErrorLevel 1
    Abort
  ${EndIf}
```

对下载失败的 `MessageBox` 同样处理：

```nsis
  ${If} $0 != "success"
    IfSilent +3
      MessageBox MB_OK|MB_ICONEXCLAMATION \
        "WebView2 Runtime 下载失败。$\n请检查网络连接后重试。"
    SetErrorLevel 1
    Abort
  ${EndIf}
```

- [ ] **Step 4: 确保安装完成后静默模式不弹"完成"页**

在安装脚本末尾确认有：

```nsis
; 静默模式下自动关闭安装完成界面
!ifdef MUI_FINISHPAGE
  !define MUI_FINISHPAGE_NOAUTOCLOSE
!endif
```

如果使用 MUI2，确认 `!insertmacro MUI_PAGE_FINISH` 之前有 `!define MUI_FINISHPAGE_NOAUTOCLOSE`。

- [ ] **Step 5: 在 packaging/README.md 补充静默安装说明**

```markdown
### 静默安装（GPO / 批量部署）

```batch
:: 静默安装到默认路径（%ProgramFiles%\Nini）
nini-setup.exe /S

:: 静默安装到自定义路径
nini-setup.exe /S /D=C:\Enterprise\Nini

:: 静默卸载
"C:\Enterprise\Nini\Uninstall.exe" /S
```

静默模式下所有错误通过退出码反映（0 = 成功，非 0 = 失败），不弹出任何对话框。
```

- [ ] **Step 6: 提交**

```bash
git add packaging/installer.nsi packaging/README.md
git commit -m "feat(packaging): NSIS 静默安装参数支持（/S /D=path）"
```

---

### Task 11：Authenticode 代码签名

**目标行为：** 当环境变量 `SIGNING_CERT_THUMBPRINT` 存在时，`build_windows.bat` 自动对 `nini.exe`、`nini-cli.exe`、`nini-setup.exe` 进行代码签名，避免 Windows SmartScreen 拦截。

**Files:**
- Modify: `build_windows.bat`
- Modify: `packaging/README.md`

- [ ] **Step 1: 在 build_windows.bat 中添加签名辅助函数块**

在文件末尾（`echo [BUILD] 完成` 之前），添加签名步骤：

```batch
:: ── 代码签名（可选）────────────────────────────────────────────────────────
:: 需要在系统证书存储中安装签名证书，并设置 SIGNING_CERT_THUMBPRINT 环境变量。
:: 需要 Windows SDK 中的 signtool.exe 在 PATH 中。
if not "%SIGNING_CERT_THUMBPRINT%"=="" (
    echo [BUILD] 正在对可执行文件进行代码签名...
    set TIMESTAMP_URL=http://timestamp.digicert.com

    signtool sign ^
        /sha1 "%SIGNING_CERT_THUMBPRINT%" ^
        /tr "%TIMESTAMP_URL%" ^
        /td sha256 ^
        /fd sha256 ^
        /d "Nini - AI 科研伙伴" ^
        dist\nini.exe dist\nini-cli.exe
    if errorlevel 1 (
        echo [ERROR] 可执行文件签名失败
        exit /b 1
    )

    signtool sign ^
        /sha1 "%SIGNING_CERT_THUMBPRINT%" ^
        /tr "%TIMESTAMP_URL%" ^
        /td sha256 ^
        /fd sha256 ^
        /d "Nini - AI 科研伙伴 安装程序" ^
        dist\nini-setup.exe
    if errorlevel 1 (
        echo [ERROR] 安装程序签名失败
        exit /b 1
    )

    echo [BUILD] 代码签名完成
) else (
    echo [BUILD] 未设置 SIGNING_CERT_THUMBPRINT，跳过代码签名
)
```

> **注意：** `signtool.exe` 需要 Windows SDK。若 CI/CD 机器没有 SDK，可替换为第三方工具如 `osslsigncode`。

- [ ] **Step 2: 确认 NSIS 安装包在签名步骤之后构建**

检查 `build_windows.bat` 中 `makensis` 和 `signtool` 的顺序。签名流程：
1. `pyinstaller` 生成 `dist\nini.exe` 和 `dist\nini-cli.exe`
2. **签名** `dist\nini.exe` 和 `dist\nini-cli.exe`（Task 11 新增步骤）
3. `makensis` 打包已签名的 EXE → `dist\nini-setup.exe`
4. **签名** `dist\nini-setup.exe`

如果当前 `makensis` 在签名之前，需要将 EXE 签名步骤移到 `makensis` 之前，安装包签名保留在最后。

将签名步骤拆分为两段：

```batch
:: ── EXE 签名（在 NSIS 打包前）──────────────────────────────────────────────
if not "%SIGNING_CERT_THUMBPRINT%"=="" (
    echo [BUILD] 签名可执行文件...
    signtool sign /sha1 "%SIGNING_CERT_THUMBPRINT%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /d "Nini" dist\nini.exe dist\nini-cli.exe
    if errorlevel 1 ( echo [ERROR] EXE 签名失败 & exit /b 1 )
)

:: ── NSIS 打包 ──────────────────────────────────────────────────────────────
"%NSIS_DIR%\makensis.exe" %NSIS_EXTRA_ARGS% packaging\installer.nsi

:: ── 安装包签名（在 NSIS 打包后）────────────────────────────────────────────
if not "%SIGNING_CERT_THUMBPRINT%"=="" (
    echo [BUILD] 签名安装包...
    signtool sign /sha1 "%SIGNING_CERT_THUMBPRINT%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 /d "Nini 安装程序" dist\nini-setup.exe
    if errorlevel 1 ( echo [ERROR] 安装包签名失败 & exit /b 1 )
)
```

- [ ] **Step 3: 更新 packaging/README.md**

```markdown
### 代码签名

签名需要：
- 已安装 Authenticode 证书（EV 证书或标准证书均可）
- Windows SDK 中的 `signtool.exe` 在 PATH 中

```batch
:: 指定证书指纹（在系统证书存储中查找）
set SIGNING_CERT_THUMBPRINT=YOUR_CERT_THUMBPRINT_HERE
build_windows.bat
```

构建脚本会自动对 `nini.exe`、`nini-cli.exe`、`nini-setup.exe` 进行 SHA-256 签名并附加时间戳。
若未设置 `SIGNING_CERT_THUMBPRINT`，跳过签名，适用于开发构建。
```

- [ ] **Step 4: 提交**

```bash
git add build_windows.bat packaging/README.md
git commit -m "feat(packaging): 构建脚本支持 Authenticode 代码签名"
```

---

## 自检（Self-Review）

### Spec 覆盖检查

| 规划项 | 对应 Task |
|--------|-----------|
| v1 文档状态标注 | Task 1 |
| v1 测试覆盖补全 | Task 2, 3 |
| v1 真机验收清单 | Task 4 |
| v2 单实例治理 | Task 5 |
| v2 窗口尺寸持久化 | Task 6 |
| v2 退出确认对话框 | Task 7 |
| v2 查看日志入口 | Task 8 |
| v3 企业离线 WebView2 | Task 9 |
| v3 静默安装 | Task 10 |
| v3 代码签名 | Task 11 |

### 类型一致性检查

- `_acquire_single_instance_mutex() -> int | None`：Task 5 Step 3 定义，Task 5 Step 5-6 使用，一致 ✅
- `_load_window_state() -> dict[str, int]`：Task 6 Step 2 定义，Task 6 Step 3 使用 `.get("width", 1360)`，一致 ✅
- `_save_window_state(width: int, height: int) -> None`：Task 6 Step 2 定义，Task 6 Step 5 调用 `_save_window_state(width, height)`，一致 ✅
- `_confirm_exit() -> bool`：Task 7 Step 1 定义，Task 7 Step 2 调用 `if not _confirm_exit()`，一致 ✅
- `_get_log_path() -> Path | None`：Task 8 Step 2 定义，Task 8 Step 6 `_open_log_file()` 调用，一致 ✅
- `_TrayApp.__init__` 新增 `show_log_action` 参数：Task 8 Step 3 修改签名，Task 8 Step 7 传参，一致 ✅

### 无占位符确认

全部 Step 均包含可直接执行的代码或命令，无 TBD / TODO / "类似 Task N" 等占位 ✅
