import { Download, RefreshCw, ShieldCheck } from "lucide-react";
import Button from "./ui/Button";
import { useUpdateStore } from "../store/update";

function formatSize(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "未知大小";
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.ceil(bytes / 1024)} KB`;
}

export default function UpdatePanel() {
  const check = useUpdateStore((s) => s.check);
  const download = useUpdateStore((s) => s.download);
  const busy = useUpdateStore((s) => s.busy);
  const error = useUpdateStore((s) => s.error);
  const checkForUpdates = useUpdateStore((s) => s.checkForUpdates);
  const downloadUpdate = useUpdateStore((s) => s.downloadUpdate);
  const openDialog = useUpdateStore((s) => s.openDialog);

  const hasUpdate = check?.update_available === true;
  const ready = download.status === "ready";

  return (
    <section className="rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-[var(--text-primary)]">软件更新</div>
          <div className="mt-1 text-[12px] text-[var(--text-muted)]">
            当前版本 {check?.current_version ?? "未知"}
            {hasUpdate && check.latest_version ? `，可更新到 ${check.latest_version}` : ""}
          </div>
        </div>
        <ShieldCheck size={18} className="mt-0.5 text-[var(--accent)]" />
      </div>

      {hasUpdate && (
        <div className="rounded-[6px] bg-[var(--accent-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
          {check?.important ? "重要更新：" : "发现新版本："}
          安装包 {formatSize(check?.asset_size)}，下载后会在安装前校验完整性和签名。
        </div>
      )}

      {error && (
        <div className="rounded-[6px] border border-red-500/20 bg-red-500/10 px-3 py-2 text-[12px] text-red-600">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void checkForUpdates({ manual: true })}
          disabled={busy}
        >
          <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
          检查更新
        </Button>
        {hasUpdate && !ready && (
          <Button size="sm" onClick={() => void downloadUpdate()} disabled={busy}>
            <Download size={14} />
            下载更新
          </Button>
        )}
        {(hasUpdate || ready) && (
          <Button variant="secondary" size="sm" onClick={openDialog}>
            查看详情
          </Button>
        )}
      </div>
    </section>
  );
}
