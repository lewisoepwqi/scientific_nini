export const SCIENTIFIC_THEME_CSS = `
:root {
  color-scheme: light;
  --color-significant: #0f766e;
  --color-marginal: #b45309;
  --color-not-significant: #64748b;
  --color-positive-effect: #1d4ed8;
  --color-negative-effect: #be123c;
  --color-surface: #f8fafc;
  --color-surface-muted: #e2e8f0;
  --color-text: #0f172a;
  --color-border: rgba(15, 23, 42, 0.12);
  --color-accent: #0891b2;
  font-family: "IBM Plex Sans", "Noto Sans SC", sans-serif;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  padding: 0;
  background:
    radial-gradient(circle at top right, rgba(8, 145, 178, 0.12), transparent 38%),
    linear-gradient(180deg, #ffffff 0%, var(--color-surface) 100%);
  color: var(--color-text);
}

body {
  min-height: 100vh;
  padding: 16px;
  font-family: inherit;
  line-height: 1.6;
}

a {
  color: var(--color-accent);
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  border: 1px solid var(--color-border);
  background: white;
  color: var(--color-text);
  border-radius: 999px;
  padding: 8px 14px;
  cursor: pointer;
  transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
}

button:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
  border-color: rgba(8, 145, 178, 0.4);
}

table {
  width: 100%;
  border-collapse: collapse;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 16px;
  overflow: hidden;
}

th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
}

th {
  background: rgba(148, 163, 184, 0.12);
}

.widget-shell {
  border: 1px solid var(--color-border);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --color-significant: #5eead4;
    --color-marginal: #fbbf24;
    --color-not-significant: #94a3b8;
    --color-positive-effect: #60a5fa;
    --color-negative-effect: #fb7185;
    --color-surface: #020617;
    --color-surface-muted: #0f172a;
    --color-text: #e2e8f0;
    --color-border: rgba(148, 163, 184, 0.2);
    --color-accent: #67e8f9;
  }

  html,
  body {
    background:
      radial-gradient(circle at top right, rgba(34, 211, 238, 0.15), transparent 38%),
      linear-gradient(180deg, #020617 0%, var(--color-surface) 100%);
  }

  button {
    background: rgba(15, 23, 42, 0.88);
  }

  table,
  .widget-shell {
    background: rgba(15, 23, 42, 0.86);
  }
}
`.trim();
