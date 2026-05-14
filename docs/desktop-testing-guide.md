# 桌面端测试指南

> 本指南面向：开发桌面壳（pywebview + WebView2）相关功能时，如何**不打包**完成绝大部分验证，只在最后做一次冒烟打包。
> 适用平台：开发可在 WSL / macOS / Linux 完成；**桌面壳本身只能在 Windows 主机运行**（依赖 WebView2）。

---

## 1. 分层测试策略

桌面端改动按依赖关系分三层，按下面顺序逐层验证可以最大化迭代速度：

| 层 | 改动范围 | 验证方式 | 是否需要打包 |
|----|---------|---------|------------|
| L1 | 纯前端（React 组件、store、事件监听） | 浏览器开发模式 + `npm test` | 否 |
| L2 | 原生菜单、托盘、窗口生命周期、私有 WebView2 API | Windows 上直接 `python -m` 启动 launcher | 否 |
| L3 | 启动流程、单实例锁、安装路径解析、自动更新 | 打包安装器后冒烟测试 | 是 |

**原则**：先 L1 → 再 L2 → 最后 L3。每升一层，迭代成本翻几倍。

---

## 2. L1：浏览器开发模式（覆盖 ~90% 前端改动）

### 2.1 启动

两个终端：

```bash
# 终端 1：后端 + 热重载
nini start --reload

# 终端 2：前端 Vite dev server（端口 3000，/api 和 /ws 代理到 8000）
cd web && npm run dev
```

浏览器访问 `http://localhost:3000`。修改任意 `.tsx` 文件 Vite 自动 HMR；改后端 `.py` 文件 uvicorn 自动重启。

### 2.2 单元测试

```bash
cd web && npm test -- --run       # vitest 全量（几秒）
cd web && npm test -- SessionTabs # 单个文件
```

```bash
pytest -q                                      # 后端全量
pytest tests/test_xxx.py::test_name -q         # 单测
pytest -k "session_tab" -q                     # 关键字匹配
```

### 2.3 桌面菜单事件的浏览器模拟

桌面壳的菜单回调最终通过 `evaluate_js` 派发浏览器 `CustomEvent`，前端用 `addEventListener` 接收。**所有事件都可以在浏览器 DevTools Console 里手动 dispatch 模拟**，从而在 L1 完成端到端验证。

| 菜单项 | 浏览器模拟命令 |
|--------|--------------|
| 文件 → 新建会话 | `window.dispatchEvent(new CustomEvent('nini:new-session'))` |
| 帮助 → 检查更新 | `window.dispatchEvent(new CustomEvent('nini:check-updates'))` |

只有"开发者工具 / 重新加载 / 全屏 / 退出 / 查看日志"这些**不经 evaluate_js** 的菜单项需要在 L2 验证。

### 2.4 Tab 栏 / Badge 自检清单

- [ ] 创建/切换会话 → Tab 栏出现对应 Tab，标题与会话一致
- [ ] 鼠标悬停 Tab 出现 `×` 关闭按钮；点击关闭但**不**删除会话
- [ ] 键盘 Tab 键聚焦 Tab → Enter/Space 切换；再 Tab 到 `×` → Enter 关闭
- [ ] 连续开 6 个会话 → 最早非活跃 Tab 自动淘汰，始终最多 5 个
- [ ] 刷新页面 → Tab 列表保留（localStorage 持久化）
- [ ] 侧栏删除会话 → 对应 Tab 自动关闭
- [ ] 非当前会话触发 AskUserQuestion 不回答 → 切走后导航栏「聊天」图标出现 accent 圆点 badge

---

## 3. L2：Windows 直跑 Launcher（覆盖原生菜单 / 控件交互）

### 3.1 关键原理：端口已占用时跳过自启后台

`windows_launcher.py:_resolve_runtime_port` + `_is_port_open` 的逻辑：

```python
existing_service = args.port > 0 and _is_port_open(host, port)
if not existing_service:
    # 才启动 nini-cli.exe start 子进程
```

也就是说：**如果指定端口已被占用，launcher 不会再启动后台**，直接把 WebView2 窗口指向 `http://host:port`。利用这一点，可以让 launcher 加载 Vite dev server，避免每次改前端都重打包。

### 3.2 三终端启动（Windows PowerShell）

```powershell
# 终端 1：后端（监听 8000）
nini start --reload

# 终端 2：Vite dev server（监听 3000，代理 /api、/ws → 8000）
cd web
npm run dev

# 终端 3：直接用 Python 启动桌面壳，指向 3000
python -m nini.windows_launcher --host 127.0.0.1 --port 3000
```

> 如果 `python -m nini.windows_launcher` 提示不能作为 main 运行：
> ```powershell
> python -c "from nini.windows_launcher import main; raise SystemExit(main(['--host','127.0.0.1','--port','3000']))"
> ```

效果：
- 桌面壳的原生菜单、托盘、单实例锁等都按真实代码路径走
- 前端 `.tsx` 改动通过 Vite HMR **实时推到 WebView2 窗口**
- 只有改 `windows_launcher.py` 时需要重启终端 3

### 3.3 菜单逐项自检清单

| 菜单 → 项 | 预期 |
|---------|------|
| 文件 → 新建会话 (Ctrl+N) | 创建新会话并切过去 |
| 文件 → 退出 | 窗口关闭 + 后台进程退出 |
| 视图 → **开发者工具** (Ctrl+Shift+I) | 弹出 WebView2 DevTools 面板 ⚠️ |
| 视图 → 重新加载 (Ctrl+R) | 页面刷新 |
| 视图 → 强制重新加载 (Ctrl+Shift+R) | 页面刷新（绕缓存） |
| 视图 → 全屏 (F11) | 进入/退出全屏 |
| 帮助 → 查看日志 | 系统默认应用打开日志文件 |
| 帮助 → 检查更新 | 触发 update flow |

⚠️ **开发者工具最重要**——它依赖 pywebview 私有路径（`Window.native.webview.CoreWebView2`），pywebview 升版本时必须重测此项。详见 §5 故障排查。

### 3.4 异常路径

- 关掉终端 1（后端） → 桌面壳窗口应显示连接断开 UI，菜单仍可用
- 关掉终端 2（Vite） → 窗口空白，按"重新加载"应失败但不崩溃
- 双击 launcher 命令两次 → 第二次应被单实例锁拦截，激活已有窗口

---

## 4. L3：打包冒烟测试

只有 L1 + L2 全部通过后，再做一次打包：

```bash
# 后端 wheel
python -m build

# Windows 安装器（参考 scripts/ 下打包脚本，通常用 PyInstaller + NSIS/Inno）
# 具体命令见 packaging README
```

**冒烟检查项**（不需要全量回归，L1/L2 已覆盖）：

- [ ] 安装器在干净 Windows 上能装上
- [ ] 启动后菜单栏显示「文件 / 视图 / 帮助」
- [ ] 视图 → 开发者工具 能打开 DevTools
- [ ] 文件 → 新建会话 能创建会话
- [ ] 关闭窗口后托盘图标存在；点击托盘重新打开窗口
- [ ] 退出菜单完整关闭进程，任务管理器无残留

打包安装器只用来验证"分发链路本身没坏"，**不是用来发现功能 bug**——功能 bug 应在 L1/L2 抓到。

---

## 5. 故障排查记录

### 5.1 开发者工具菜单点击无反应

**症状**：菜单 → 视图 → 开发者工具 (Ctrl+Shift+I) 点击后没有任何反应。

**根因**（三个叠加）：

1. **路径错**：早期实现用了 `window._js_bridge.webview.CoreWebView2`，但 pywebview 5.x 的 `Window` 没有 `_js_bridge` 属性。正确路径是公开 API `window.native.webview.CoreWebView2`（pywebview 在 `winforms.py:setup_app` 里 `self.pywebview_window.native = self`）。
2. **能力被禁**：pywebview 在 `debug=False` 启动时把 WebView2 的 `Settings.AreDevToolsEnabled` 设为 `False`，此时 `OpenDevToolsWindow()` 即使调用成功也是 no-op。
3. **线程错**：pywebview 的菜单回调**显式在子线程执行**（`winforms.py:set_window_menu` 中 `threading.Thread(target=function).start()`）。而 WebView2 / WinForms 控件方法**必须在 UI 线程调用**，需要 `webview2_ctl.Invoke(Action(_inner))` marshal。

**还要避免**：`with suppress(Exception)` 会把所有异常吞掉，开发模式下看不到根因。改成 `try/except` + `traceback.print_exc()` 至少 stderr 能看到。

**修复定位**：`src/nini/windows_launcher.py` 的 `_open_devtools` 函数。

### 5.2 pywebview 升级后需复查的私有路径

| 属性 | 当前用法 | 风险 |
|------|---------|------|
| `Window.native` | 拿 BrowserForm 实例 | pywebview 5.x 公开 API，稳定 |
| `BrowserForm.webview` | 拿 WebView2 WinForms 控件 | 取决于 winforms.py 内部结构 |
| `.CoreWebView2.Settings.AreDevToolsEnabled` | 运行时开启 DevTools | WebView2 SDK 公开属性，稳定 |
| `.CoreWebView2.OpenDevToolsWindow()` | 打开 DevTools | WebView2 SDK 公开方法，稳定 |

升 pywebview 主版本时按上表逐项重测。

### 5.3 WSL 里跑 launcher 报 import 错

预期。pywebview 的 `edgechromium` 后端只在 Windows 上有 `webview2` / `pythonnet` 依赖。L2 必须切到 Windows 主机。L1 在 WSL/macOS/Linux 都可。

---

## 6. 速查表

```
改了 .tsx / store.ts / hooks.ts        → 浏览器 + npm test
改了 .py（除 windows_launcher.py）      → 浏览器 + pytest
改了 windows_launcher.py                → Windows 上 python -m 直跑
改了打包脚本 / installer / 更新流程     → 必须打包冒烟
```

**默认不要打包**——除非动了打包链路本身。L1 + L2 是 95% 改动的归宿。
