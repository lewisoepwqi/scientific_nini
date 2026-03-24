const CSP_POLICY = [
  "default-src 'none'",
  "script-src 'unsafe-inline' https://cdnjs.cloudflare.com https://esm.sh https://cdn.jsdelivr.net https://unpkg.com",
  "style-src 'unsafe-inline'",
  "img-src data: blob: https:",
  "font-src data: https:",
  "connect-src 'self'",
  "media-src data: blob: https:",
  "frame-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

export function assembleDocument(
  html: string,
  themeCSS: string,
  bridgeJS: string,
): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta http-equiv="Content-Security-Policy" content="${CSP_POLICY}" />
    <style>${themeCSS}</style>
  </head>
  <body>
    ${html}
    <script>${bridgeJS}</script>
  </body>
</html>`;
}
