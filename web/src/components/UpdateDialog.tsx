import { AlertTriangle, CheckCircle2, Download, Loader2, X } from "lucide-react";
import Button from "./ui/Button";
import { useStore } from "../store";
import { useUpdateStore } from "../store/update";

export default function UpdateDialog() {
  const open = useUpdateStore((s) => s.dialogOpen);
  const check = useUpdateStore((s) => s.check);
  const download = useUpdateStore((s) => s.download);
  const busy = useUpdateStore((s) => s.busy);
  const error = useUpdateStore((s) => s.error);
  const closeDialog = useUpdateStore((s) => s.closeDialog);
  const downloadUpdate = useUpdateStore((s) => s.downloadUpdate);
  const applyUpdate = useUpdateStore((s) => s.applyUpdate);
  const runningSessions = useStore((s) => s.runningSessions);

  if (!open || !check?.update_available) return null;

  const ready = download.status === "ready";
  const hasRunningTask = runningSessions.size > 0;
  const applying = download.status === "applying" || download.status === "restarting";

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/35 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Nini 软件更新"
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
          <div>
            <div className="text-[12px] font-medium uppercase tracking-[0.18em] text-[var(--accent)]">
              Nini Update
            </div>
            <h2 className="m-0 mt-1 text-[18px] font-semibold text-[var(--text-primary)]">
              发现 Nini {check.latest_version}
            </h2>
            <p className="m-0 mt-1 text-[12px] text-[var(--text-muted)]">
              当前版本 {check.current_version}，升级前请保存正在进行的工作。
            </p>
          </div>
          <button
            type="button"
            onClick={closeDialog}
            className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"
            aria-label="关闭更新提示"
          >
            <X size={18} />
          </button>
        </header>

        <div className="space-y-4 px-5 py-4">
          {check.important && (
            <div className="flex gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-700">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              这是重要更新，但不会阻断你继续使用当前版本。
            </div>
          )}

          {check.notes.length > 0 && (
            <div>
              <div className="mb-2 text-[12px] font-medium text-[var(--text-secondary)]">
                更新内容
              </div>
              <ul className="m-0 space-y-1 pl-4 text-[12px] text-[var(--text-muted)]">
                {check.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          )}

          {download.status !== "idle" && (
            <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3">
              <div className="flex items-center justify-between text-[12px] text-[var(--text-secondary)]">
                <span>下载状态：{download.status}</span>
                <span>{download.progress}%</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--bg-overlay)]">
                <div
                  className="h-full rounded-full bg-[var(--accent)] transition-[width]"
                  style={{ width: `${download.progress}%` }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[12px] text-red-600">
              {error}
            </div>
          )}

          {hasRunningTask && ready && (
            <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-700">
              当前仍有任务运行，暂不能重启升级。
            </div>
          )}
        </div>

        <footer className="flex flex-wrap justify-end gap-2 border-t border-[var(--border-subtle)] px-5 py-4">
          <Button variant="secondary" onClick={closeDialog}>
            稍后处理
          </Button>
          {!ready ? (
            <Button onClick={() => void downloadUpdate()} disabled={busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              下载并校验
            </Button>
          ) : (
            <Button
              onClick={() => void applyUpdate()}
              disabled={busy || hasRunningTask || applying}
            >
              <CheckCircle2 size={14} />
              立即重启并升级
            </Button>
          )}
        </footer>
      </section>
    </div>
  );
}
