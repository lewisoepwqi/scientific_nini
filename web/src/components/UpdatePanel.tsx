import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
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
  const checking = useUpdateStore((s) => s.checking);
  const downloading = useUpdateStore((s) => s.downloading);
  const error = useUpdateStore((s) => s.error);
  const checkCompleted = useUpdateStore((s) => s.checkCompleted);
  const checkForUpdates = useUpdateStore((s) => s.checkForUpdates);
  const downloadUpdate = useUpdateStore((s) => s.downloadUpdate);
  const openDialog = useUpdateStore((s) => s.openDialog);
  const resetCheckCompleted = useUpdateStore((s) => s.resetCheckCompleted);

  const [showUpToDate, setShowUpToDate] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasUpdate = check?.update_available === true;
  const ready = download.status === "ready";
  const notConfigured = check?.status === "not_configured";
  const isDownloading = download.status === "downloading" || download.status === "verifying";

  // 检查完成后显示反馈
  useEffect(() => {
    if (!checkCompleted) return;

    if (error) {
      // 有错误时，不自动消失
      return;
    }

    if (!hasUpdate && check?.status === "up_to_date") {
      // 已是最新版本，显示提示后 3 秒自动消失
      setShowUpToDate(true);
      timerRef.current = setTimeout(() => {
        setShowUpToDate(false);
        resetCheckCompleted();
      }, 3000);
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [checkCompleted, hasUpdate, error, check?.status, resetCheckCompleted]);

  const handleCheck = () => {
    setShowUpToDate(false);
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    void checkForUpdates({ manual: true });
  };

  const handleRetry = () => {
    handleCheck();
  };

  return (
    <section className="rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-[var(--text-primary)] flex items-center gap-2">
            软件更新
            {checking && (
              <RefreshCw size={12} className="animate-spin text-[var(--text-muted)]" />
            )}
            {isDownloading && (
              <Download size={12} className="animate-pulse text-[var(--accent)]" />
            )}
          </div>
          <div className="mt-1 text-[12px] text-[var(--text-muted)]">
            当前版本 {check?.current_version ?? "未知"}
            {hasUpdate && check.latest_version ? `，可更新到 ${check.latest_version}` : ""}
          </div>
        </div>
        <ShieldCheck size={18} className="mt-0.5 text-[var(--accent)]" />
      </div>

      {/* 未配置提示 */}
      {notConfigured && (
        <div className="rounded-[6px] border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-700">
          更新服务器未配置。如需使用更新功能，请在配置文件中设置 NINI_UPDATE_BASE_URL。
        </div>
      )}

      {/* 已是最新版本提示（自动消失） */}
      {showUpToDate && !checking && (
        <div className="rounded-[6px] border border-green-500/20 bg-green-500/10 px-3 py-2 text-[12px] text-green-700 flex items-center gap-2">
          <CheckCircle2 size={14} className="shrink-0" />
          <span>已是最新版本 ({check?.current_version})</span>
        </div>
      )}

      {/* 有新版本提示 */}
      {hasUpdate && (
        <div className="rounded-[6px] bg-[var(--accent-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
          {check?.important ? "重要更新：" : "发现新版本："}
          {check?.latest_version && <span className="font-medium"> {check.latest_version}</span>}
          <span className="text-[var(--text-muted)]"> · 安装包 {formatSize(check?.asset_size)}</span>
          {check?.notes && check.notes.length > 0 && (
            <div className="mt-1.5 text-[11px] text-[var(--text-muted)]">
              {check.notes[0]}
              {check.notes.length > 1 && "…"}
            </div>
          )}
        </div>
      )}

      {/* 下载进度提示 */}
      {isDownloading && (
        <div className="rounded-[6px] bg-[var(--bg-overlay)] px-3 py-2 text-[12px] text-[var(--text-muted)]">
          <div className="flex items-center justify-between mb-1">
            <span>{download.status === "verifying" ? "正在校验…" : "正在下载更新…"}</span>
            <span>{download.progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-[var(--border-default)]">
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-[width]"
              style={{ width: `${download.progress}%` }}
            />
          </div>
        </div>
      )}

      {/* 已准备好安装 */}
      {ready && (
        <div className="rounded-[6px] border border-green-500/20 bg-green-500/10 px-3 py-2 text-[12px] text-green-700 flex items-center gap-2">
          <CheckCircle2 size={14} className="shrink-0" />
          <span>更新已准备就绪，可以重启安装</span>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="rounded-[6px] border border-red-500/20 bg-red-500/10 px-3 py-2 text-[12px] text-red-600 flex items-start gap-2">
          <XCircle size={14} className="mt-0.5 shrink-0" />
          <div className="flex-1">
            <span>{error}</span>
            <button
              type="button"
              onClick={handleRetry}
              className="ml-2 text-red-600 underline hover:no-underline"
            >
              重试
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={handleCheck}
          disabled={checking}
        >
          <RefreshCw size={14} className={checking ? "animate-spin" : ""} />
          {checking ? "检查中…" : "检查更新"}
        </Button>
        {hasUpdate && !ready && !isDownloading && (
          <Button size="sm" onClick={() => void downloadUpdate()} disabled={downloading}>
            <Download size={14} />
            {downloading ? "启动下载…" : "下载更新"}
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
