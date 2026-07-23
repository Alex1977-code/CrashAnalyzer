/* Formatierung: deutsche Datums-/Zeitdarstellung, HTML-Escaping. */

const dtf = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
const dtfTime = new Intl.DateTimeFormat("de-DE", {
  weekday: "short", day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit",
});

export function fmtDate(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "–" : dtf.format(d);
}

export function fmtDateTime(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "–" : dtfTime.format(d) + " Uhr";
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const VERDICT = {
  ok:      { label: "In Ordnung", icon: "✓", cls: "status-ok" },
  warning: { label: "Hinweis", icon: "⚠", cls: "status-warning" },
  problem: { label: "Problem", icon: "✕", cls: "status-problem" },
  unknown: { label: "Unklar", icon: "?", cls: "status-unknown" },
};

export function verdictBadge(verdict) {
  const v = VERDICT[verdict] || VERDICT.unknown;
  return `<span class="badge ${v.cls}"><span aria-hidden="true">${v.icon}</span>${v.label}</span>`;
}

export const STABILITY = {
  stabil:   { label: "Stabil", icon: "✓", cls: "status-ok" },
  instabil: { label: "Instabil", icon: "⚠", cls: "status-warning" },
  kritisch: { label: "Kritisch", icon: "✕", cls: "status-problem" },
};

export const KIND_LABEL = {
  bsod: "Bluescreen",
  power_loss: "Stromverlust",
  power_button: "Power-Taste",
  hardware: "Hardwarefehler",
  storage: "Datenträger",
};
