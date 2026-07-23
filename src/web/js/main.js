/* App-Einstieg: Theme, Tabs, Datenladen, View-Wechsel. */
import { api } from "./api.js";
import { esc } from "./format.js";
import { renderDiagnose } from "./views/diagnose.js";
import { renderTools, stopAllPollers } from "./views/tools.js";
import { renderSettings } from "./views/settings.js";

const view = document.getElementById("view");
const state = { meta: null, analysis: null, days: null };
let currentTab = "diagnose";

const ctx = {
  state,
  highlightTool: null,
  reload: (opts = {}) => loadAnalysis(opts),
  goTool: (toolId) => {
    ctx.highlightTool = toolId;
    switchTab("tools");
  },
};

/* ---------- Theme ---------- */
const THEME_KEY = "crash-analyzer-theme";
function applyTheme(theme) {
  if (theme === "light" || theme === "dark") {
    document.documentElement.dataset.theme = theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
}
applyTheme(localStorage.getItem(THEME_KEY));
document.getElementById("theme-toggle").addEventListener("click", () => {
  const systemDark = matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : systemDark;
  const next = isDark ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
});

/* ---------- Tabs ---------- */
const renderers = { diagnose: renderDiagnose, tools: renderTools, settings: renderSettings };

function switchTab(tab) {
  currentTab = tab;
  stopAllPollers();
  document.querySelectorAll("nav.tabs button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  renderers[tab](view, ctx);
}

document.querySelectorAll("nav.tabs button").forEach((b) =>
  b.addEventListener("click", () => switchTab(b.dataset.tab)));

/* ---------- Daten ---------- */
async function loadAnalysis({ days, refresh } = {}) {
  state.analysis = null;
  if (currentTab === "diagnose") renderDiagnose(view, ctx);
  const params = new URLSearchParams();
  if (days) params.set("days", String(days));
  if (refresh) params.set("refresh", "1");
  try {
    state.analysis = await api.get(`/api/analysis${params.toString() ? "?" + params : ""}`);
  } catch (e) {
    if (currentTab === "diagnose") {
      view.innerHTML = `<div class="banner critical"><b>Analyse fehlgeschlagen:</b> ${esc(e.message)}
        <div style="margin-top:8px"><button class="btn" id="retry">Erneut versuchen</button></div></div>`;
      view.querySelector("#retry").addEventListener("click", () => loadAnalysis({ refresh: true }));
    }
    return;
  }
  if (currentTab === "diagnose") renderDiagnose(view, ctx);
}

async function boot() {
  renderDiagnose(view, ctx);   // Ladezustand
  try {
    state.meta = await api.get("/api/meta");
    document.getElementById("app-version").textContent = "v" + state.meta.version;
    document.getElementById("admin-badge").innerHTML = state.meta.is_admin
      ? `<span class="badge status-ok" title="Volle Prüftool-Unterstützung"><span aria-hidden="true">✓</span>Administrator</span>`
      : `<span class="badge" title="Einige Prüftools benötigen Administratorrechte">Standardrechte</span>`;
  } catch { /* Meta ist nicht kritisch */ }
  await loadAnalysis({});
}

boot();
