import { useCallback, type CSSProperties } from "react";
import { X } from "lucide-react";
import { useStore } from "../store";

const DRAG: CSSProperties = { WebkitAppRegion: "drag" } as CSSProperties;
const NO_DRAG: CSSProperties = { WebkitAppRegion: "no-drag" } as CSSProperties;

export default function SessionTabs() {
  const sessionId = useStore((s) => s.sessionId);
  const openTabIds = useStore((s) => s.openTabIds);
  const tabTitles = useStore((s) => s.tabTitles);
  const runningSessions = useStore((s) => s.runningSessions);
  const switchSession = useStore((s) => s.switchSession);
  const closeTab = useStore((s) => s.closeTab);

  const handleTabClick = useCallback(
    (id: string) => {
      if (id !== sessionId) void switchSession(id);
    },
    [sessionId, switchSession],
  );

  const handleClose = useCallback(
    (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      closeTab(id);
    },
    [closeTab],
  );

  if (openTabIds.length === 0) return null;

  return (
    <div
      role="tablist"
      aria-label="会话标签页"
      style={DRAG}
      className="pywebview-drag-region flex h-full items-end gap-0.5 overflow-x-auto px-2 pt-1.5 scrollbar-none"
    >
      {openTabIds.map((id) => {
        const isActive = id === sessionId;
        const isRunning = runningSessions.has(id);
        const title = tabTitles[id] ?? "会话";
        return (
          <div
            key={id}
            role="tab"
            aria-selected={isActive}
            style={NO_DRAG}
            className={[
              "group relative flex items-center gap-1.5 max-w-[160px] min-w-[80px]",
              "h-8 px-2 rounded-t-md text-xs font-medium transition-colors shrink-0 cursor-pointer",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
              isActive
                ? "bg-[var(--bg-base)] text-[var(--text-primary)] border border-b-0 border-[var(--border-subtle)] z-10"
                : "bg-[var(--bg-app)] text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]",
            ].join(" ")}
            tabIndex={0}
            onClick={() => handleTabClick(id)}
            onDoubleClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleTabClick(id); }}
          >
            {isRunning && (
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] shrink-0" />
            )}
            <span className="truncate flex-1 text-left pl-1">{title}</span>
            <button
              type="button"
              aria-label={`关闭 ${title}`}
              tabIndex={0}
              style={NO_DRAG}
              onClick={(e) => handleClose(e, id)}
              className="opacity-0 group-hover:opacity-100 rounded p-0.5 hover:bg-[var(--bg-hover)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-opacity shrink-0"
            >
              <X size={10} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
