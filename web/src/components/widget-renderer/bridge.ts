export const WIDGET_BRIDGE_JS = `
(() => {
  const postToParent = (payload) => {
    window.parent.postMessage(
      {
        ...payload,
        widgetId: "__NINI_WIDGET_ID__",
      },
      "*",
    );
  };

  const reportHeight = () => {
    const body = document.body;
    const doc = document.documentElement;
    const height = Math.max(
      body?.scrollHeight || 0,
      body?.offsetHeight || 0,
      doc?.scrollHeight || 0,
      doc?.offsetHeight || 0,
    );
    postToParent({ type: "iframe-height", height });
  };

  window.sendPrompt = (text) => {
    if (typeof text !== "string" || !text.trim()) {
      return;
    }
    postToParent({ type: "send-prompt", text: text.trim() });
  };

  const observerTarget = document.body || document.documentElement;
  if (observerTarget && typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => reportHeight());
    observer.observe(observerTarget);
    window.addEventListener("beforeunload", () => observer.disconnect(), { once: true });
  }

  window.addEventListener("load", reportHeight);
  window.addEventListener("resize", reportHeight);
  document.addEventListener("DOMContentLoaded", reportHeight);

  if (document.fonts?.ready) {
    document.fonts.ready.then(reportHeight).catch(() => undefined);
  }

  requestAnimationFrame(() => reportHeight());
  setTimeout(reportHeight, 80);
})();
`.trim();
