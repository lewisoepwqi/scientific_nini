import { useState, type FormEvent } from "react";

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
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/55 px-4 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-slate-900">输入 API Key</h2>
          <p className="mt-1 text-sm text-slate-500">
            当前服务已开启鉴权。输入有效 API Key 后再初始化会话和连接。
          </p>
        </div>
        <label className="mb-3 block text-sm font-medium text-slate-700">
          API Key
        </label>
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="请输入 API Key"
          className="mb-3 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          autoFocus
        />
        {error && (
          <div className="mb-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={loading}
          className="inline-flex w-full items-center justify-center rounded-2xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "验证中..." : "继续"}
        </button>
      </form>
    </div>
  );
}
