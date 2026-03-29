import { useState, type FormEvent } from "react";
import BaseModal from "./BaseModal";
import Button from "./ui/Button";

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
 <BaseModal open={true} onClose={() => {}} title="API Key 验证" backdropClass="bg-[var(--bg-elevated)]/55">
 <form
 onSubmit={handleSubmit}
 className="w-full max-w-md rounded-lg border border-[var(--border-default)] bg-[var(--bg-base)] p-6"
 >
 <div className="mb-4">
 <h2 className="text-lg font-semibold text-[var(--text-primary)]">输入 API Key</h2>
 <p className="mt-1 text-sm text-[var(--text-secondary)]">
 当前服务已开启鉴权。输入有效 API Key 后再初始化会话和连接。
 </p>
 </div>
 <label htmlFor="api-key-input" className="mb-3 block text-sm font-medium text-[var(--text-secondary)]">
 API Key
 </label>
 <input
 id="api-key-input"
 type="password"
 value={apiKey}
 onChange={(event) => setApiKey(event.target.value)}
 placeholder="请输入 API Key"
 className="mb-3 w-full rounded-lg border border-[var(--border-strong)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]"
 autoFocus
 aria-describedby={error ? "api-key-error" : undefined}
 />
 {error && (
 <div id="api-key-error" role="alert" className="mb-3 rounded-lg border border-[var(--error)] bg-[var(--accent-subtle)] px-3 py-2 text-sm text-[var(--error)]">
 {error}
 </div>
 )}
 <Button
 type="submit"
 variant="primary"
 loading={loading}
 className="w-full rounded-lg px-4 py-3 text-sm"
 >
 {loading ? "验证中..." : "继续"}
 </Button>
 </form>
 </BaseModal>
 );
}
