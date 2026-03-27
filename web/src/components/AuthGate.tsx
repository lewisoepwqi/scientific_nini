import { useState, type FormEvent } from "react";
import BaseModal from "./BaseModal";

interface Props {
  error: string | null;
  loading: boolean;
  onSubmit: (apiKey: string) => Promise<boolean | void>;
}

export default function AuthGate({ error, loading, onSubmit }: Props) {
  const [apiKey, setApiKey] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await onSubmit(apiKey);
  };

  return (
    <BaseModal open={true} onClose={() => {}} title="API Key 验证" backdropClass="bg-slate-950/55">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-3xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-6 shadow-2xl"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">输入 API Key</h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            当前服务已开启鉴权。输入有效 API Key 后再初始化会话和连接。
          </p>
        </div>
        <label htmlFor="api-key-input" className="mb-3 block text-sm font-medium text-slate-700 dark:text-slate-300">
          API Key
        </label>
        <input
          id="api-key-input"
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="请输入 API Key"
          className="mb-3 w-full rounded-2xl border border-slate-300 dark:border-slate-600 px-4 py-3 text-sm text-slate-900 dark:text-slate-100 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          autoFocus
          aria-describedby={error ? "api-key-error" : undefined}
        />
        {error && (
          <div id="api-key-error" role="alert" className="mb-3 rounded-2xl border border-rose-200 dark:border-red-800 bg-rose-50 dark:bg-red-900/20 px-3 py-2 text-sm text-rose-700 dark:text-red-400">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={loading}
          className="inline-flex w-full items-center justify-center rounded-2xl bg-slate-900 dark:bg-slate-700 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 dark:hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "验证中..." : "继续"}
        </button>
      </form>
    </BaseModal>
  );
}
