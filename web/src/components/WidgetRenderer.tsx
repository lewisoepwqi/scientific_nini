import { useEffect, useRef, useState } from "react";

import { useStore } from "../store";
import { assembleDocument } from "./widget-renderer/assemble";
import { WIDGET_BRIDGE_JS } from "./widget-renderer/bridge";
import { SCIENTIFIC_THEME_CSS } from "./widget-renderer/theme";

const DEFAULT_IFRAME_HEIGHT = 200;

interface Props {
  title: string;
  html: string;
  description?: string | null;
}

interface WidgetBridgeMessage {
  type: "iframe-height" | "send-prompt";
  height?: number;
  text?: string;
  widgetId?: string;
}

function isWidgetBridgeMessage(value: unknown): value is WidgetBridgeMessage {
  if (!value || typeof value !== "object") {
    return false;
  }

  const record = value as Record<string, unknown>;
  return record.type === "iframe-height" || record.type === "send-prompt";
}

function injectWidgetId(script: string, widgetId: string): string {
  return script.split("__NINI_WIDGET_ID__").join(widgetId);
}

export default function WidgetRenderer({ title, html, description }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const submittedHtmlRef = useRef<string>("");
  const widgetIdRef = useRef(
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `widget-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  );
  const sendMessage = useStore((state) => state.sendMessage);
  const [height, setHeight] = useState(DEFAULT_IFRAME_HEIGHT);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || submittedHtmlRef.current === html) {
      return;
    }

    const bridgeScript = injectWidgetId(WIDGET_BRIDGE_JS, widgetIdRef.current);
    iframe.srcdoc = assembleDocument(html, SCIENTIFIC_THEME_CSS, bridgeScript);
    submittedHtmlRef.current = html;
    setHeight(DEFAULT_IFRAME_HEIGHT);
  }, [html]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent<unknown>) => {
      if (!isWidgetBridgeMessage(event.data)) {
        return;
      }

      const iframeWindow = iframeRef.current?.contentWindow;
      const matchesSource = Boolean(iframeWindow && event.source === iframeWindow);
      const matchesWidgetId = event.data.widgetId === widgetIdRef.current;
      if (!matchesSource && !matchesWidgetId) {
        return;
      }

      if (event.data.type === "iframe-height") {
        const nextHeight = typeof event.data.height === "number" ? event.data.height : 0;
        if (nextHeight > 0) {
          setHeight(Math.max(DEFAULT_IFRAME_HEIGHT, Math.ceil(nextHeight)));
        }
        return;
      }

      if (event.data.type === "send-prompt" && typeof event.data.text === "string") {
        const text = event.data.text.trim();
        if (text) {
          void sendMessage(text);
        }
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [sendMessage]);

  return (
    <div className="mt-3 overflow-hidden rounded-2xl border border-cyan-200/70 bg-white/90 shadow-sm">
      <div className="border-b border-cyan-100 bg-gradient-to-r from-cyan-50 via-white to-slate-50 px-4 py-3">
        <div className="text-sm font-semibold text-slate-900">{title}</div>
        {description && (
          <p className="mt-1 text-xs leading-5 text-slate-600">{description}</p>
        )}
      </div>
      <iframe
        ref={iframeRef}
        title={title}
        sandbox="allow-scripts"
        className="block w-full border-0 bg-transparent"
        style={{ height: `${height}px` }}
      />
    </div>
  );
}
