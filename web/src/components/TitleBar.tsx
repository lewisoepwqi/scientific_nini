/**
 * TitleBar —— 桌面壳自绘的合一行标题栏（菜单按钮 + 会话标签页 + 窗口控制按钮）。
 *
 * 仅在桌面壳（pywebview 注入 `window.pywebview.api`）下接管窗口控制；在浏览器模式
 * 下退化为「菜单按钮 + 标签页」的薄条，不显示 min/max/close。
 *
 * 拖动区域：标题栏空白处通过 CSS `-webkit-app-region: drag` 允许拖动整个窗口；
 * 菜单按钮、标签页和窗口控制按钮通过 `no-drag` 类显式禁用拖动。pywebview 的
 * EdgeChromium 后端识别该属性。
 */
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Menu as MenuIcon, Minus, Square, Copy, X } from "lucide-react";
import { useStore } from "../store";
import { desktopBridge } from "../lib/desktopBridge";
import SessionTabs from "./SessionTabs";
import { NiniLogo } from "./GlobalNav";

const DRAG: CSSProperties = { WebkitAppRegion: "drag" } as CSSProperties;
const NO_DRAG: CSSProperties = { WebkitAppRegion: "no-drag" } as CSSProperties;

interface MenuItem {
  label: string;
  shortcut?: string;
  onSelect: () => void;
}

interface MenuGroup {
  label: string;
  items: MenuItem[];
}

/**
 * 单个下拉菜单。受控展开，点击外部关闭。点击菜单项后关闭并执行动作。
 * 通过 `data-titlebar-menu` 标记便于外部点击检测。
 */
function MenuDropdown({
  groups,
  onClose,
  anchorRect,
}: {
  groups: MenuGroup[];
  onClose: () => void;
  anchorRect: DOMRect | null;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      const node = ref.current;
      if (node && !node.contains(e.target as Node)) onClose();
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [onClose]);

  const top = anchorRect ? anchorRect.bottom + 4 : 36;
  const left = anchorRect ? anchorRect.left : 8;

  return (
    <div
      ref={ref}
      data-titlebar-menu
      role="menu"
      style={{ ...NO_DRAG, top, left }}
      className="fixed z-[100] min-w-[220px] rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] py-1 shadow-lg"
    >
      {groups.map((group, gi) => (
        <div key={group.label}>
          {gi > 0 && <div className="my-1 h-px bg-[var(--border-subtle)]" />}
          <div className="px-3 pt-1.5 pb-0.5 text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            {group.label}
          </div>
          {group.items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={() => {
                item.onSelect();
                onClose();
              }}
              className="flex w-full items-center justify-between gap-4 px-3 py-1.5 text-left text-xs text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            >
              <span>{item.label}</span>
              {item.shortcut && (
                <span className="text-[10px] text-[var(--text-muted)]">{item.shortcut}</span>
              )}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

export interface TitleBarProps {
  /** 是否处于聊天模式（决定是否渲染标签页）。 */
  showTabs: boolean;
}

export default function TitleBar({ showTabs }: TitleBarProps) {
  const [shellAvailable, setShellAvailable] = useState(desktopBridge.isAvailable());
  const [maximized, setMaximized] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const menuBtnRef = useRef<HTMLButtonElement | null>(null);
  const createNewSession = useStore((s) => s.createNewSession);

  useEffect(() => {
    let cancelled = false;
    void desktopBridge.waitForReady().then((ok) => {
      if (!cancelled) setShellAvailable(ok);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const openMenu = () => {
    setAnchorRect(menuBtnRef.current?.getBoundingClientRect() ?? null);
    setMenuOpen(true);
  };

  const handleNewSession = () => {
    void createNewSession();
  };

  const handleToggleMax = async () => {
    const result = await desktopBridge.toggleMaximize();
    if (result && typeof result === "object") setMaximized(result.maximized);
  };

  const handleDoubleClickDrag = () => {
    if (shellAvailable) void handleToggleMax();
  };

  const menuGroups: MenuGroup[] = [
    {
      label: "文件",
      items: [
        { label: "新建会话", shortcut: "Ctrl+N", onSelect: handleNewSession },
        { label: "退出", onSelect: () => void desktopBridge.requestExit() },
      ],
    },
    {
      label: "视图",
      items: [
        { label: "开发者工具", shortcut: "Ctrl+Shift+I", onSelect: () => void desktopBridge.openDevtools() },
        { label: "重新加载", shortcut: "Ctrl+R", onSelect: () => void desktopBridge.reload() },
        { label: "强制重新加载", shortcut: "Ctrl+Shift+R", onSelect: () => void desktopBridge.hardReload() },
        { label: "全屏", shortcut: "F11", onSelect: () => void desktopBridge.toggleFullscreen() },
      ],
    },
    {
      label: "帮助",
      items: [
        { label: "查看日志", onSelect: () => void desktopBridge.openLogFile() },
      ],
    },
  ];

  return (
    <>
      {/* 窗口缩放由 pywebview 原生框架负责，不再渲染自绘缩放手柄 */}
      <div
        style={DRAG}
        onDoubleClick={handleDoubleClickDrag}
        className="pywebview-drag-region flex h-9 select-none items-stretch bg-[var(--bg-app)] border-b border-[var(--border-subtle)]"
      >
        {/* 左：菜单按钮 + 应用图标 */}
        <div style={NO_DRAG} className="flex items-center gap-1 pl-2 pr-1">
          <button
            ref={menuBtnRef}
            type="button"
            aria-label="应用菜单"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => (menuOpen ? setMenuOpen(false) : openMenu())}
            className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <MenuIcon size={16} />
          </button>
          <div
            style={DRAG}
            className="pywebview-drag-region flex h-full items-center gap-1.5 px-1 text-xs font-medium text-[var(--text-secondary)]"
          >
            <span className="pointer-events-none flex items-center">
              <NiniLogo size={16} />
            </span>
            <span className="pointer-events-none">Nini</span>
          </div>
        </div>

        {/* 中：标签页（也是 drag 区域：标签之间的空白可以拖动窗口） */}
        <div
          style={DRAG}
          className="pywebview-drag-region flex flex-1 min-w-0 items-end"
        >
          {showTabs ? (
            <div
              style={DRAG}
              className="pywebview-drag-region flex min-w-0 flex-1 items-end"
            >
              <SessionTabs />
            </div>
          ) : (
            <div style={DRAG} className="pywebview-drag-region h-full flex-1" />
          )}
          {/* 标签页右侧留一段拖动空白 */}
          <div
            style={DRAG}
            className="pywebview-drag-region h-full flex-1 min-w-[24px]"
          />
        </div>

        {/* 右：窗口控制按钮 */}
        {shellAvailable && (
          <div style={NO_DRAG} className="flex items-stretch">
            <button
              type="button"
              aria-label="最小化"
              onClick={() => void desktopBridge.minimize()}
              className="flex h-full w-11 items-center justify-center text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
            >
              <Minus size={14} />
            </button>
            <button
              type="button"
              aria-label={maximized ? "向下还原" : "最大化"}
              onClick={() => void handleToggleMax()}
              className="flex h-full w-11 items-center justify-center text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
            >
              {maximized ? <Copy size={12} /> : <Square size={12} />}
            </button>
            <button
              type="button"
              aria-label="关闭"
              onClick={() => void desktopBridge.closeToTray()}
              className="flex h-full w-11 items-center justify-center text-[var(--text-muted)] hover:bg-[#e81123] hover:text-white"
            >
              <X size={14} />
            </button>
          </div>
        )}

        {menuOpen && (
          <MenuDropdown
            groups={menuGroups}
            onClose={() => setMenuOpen(false)}
            anchorRect={anchorRect}
          />
        )}
      </div>
    </>
  );
}
