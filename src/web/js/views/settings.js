/* Einstellungen: Zeitfenster, Update-Feed, Update-Prüfung/-Download, App-Info. */
import { api } from "../api.js";
import { esc } from "../format.js";

export async function renderSettings(root, ctx) {
  root.innerHTML = `<div class="loading"><div class="spinner"></div>Lade Einstellungen …</div>`;
  let cfg, status;
  try {
    [cfg, status] = await Promise.all([api.get("/api/config"), api.get("/api/update/status")]);
  } catch (e) {
    root.innerHTML = `<div class="banner critical">${esc(e.message)}</div>`;
    return;
  }
  const meta = ctx.state.meta || {};

  root.innerHTML = `
    <div class="stack" style="max-width:760px">
      <section><h1>Einstellungen</h1></section>

      <section class="card stack">
        <h2>Analyse</h2>
        <label class="field" style="max-width:220px">Standard-Zeitraum
          <select id="cfg-days">
            ${[7, 14, 30, 90].map((d) => `<option value="${d}" ${d === cfg.days ? "selected" : ""}>${d} Tage</option>`).join("")}
          </select>
        </label>
      </section>

      <section class="card stack">
        <h2>Updates</h2>
        <div class="row" style="gap:8px">
          <span class="badge">Installiert: Version ${esc(status.current_version)}</span>
          ${status.state === "staged" ? `<span class="badge status-warning">Version ${esc(status.staged_version)} wird beim nächsten Start installiert</span>` : ""}
        </div>
        <label class="field">Update-Feed-URL
          <input type="url" id="cfg-feed" value="${esc(cfg.feed_url)}"
                 placeholder="https://… /feed.json (leer = Updates deaktiviert)">
        </label>
        ${status.state === "unconfigured" ? `
          <div class="banner">Es ist kein Update-Feed konfiguriert. Trage die Feed-URL deiner
          Verteilquelle ein (JSON mit <code>version</code>, <code>zip_url</code>, <code>sha256</code>,
          <code>notes</code>), um Updates direkt aus der App zu laden.</div>` : ""}
        <div class="row">
          <button class="btn" id="update-check">Nach Updates suchen</button>
          <button class="btn primary" id="update-download" hidden>Update laden</button>
          <span id="update-result" style="font-size:13px;color:var(--ink-2)"></span>
        </div>
      </section>

      <section class="card stack">
        <h2>Über diese App</h2>
        <dl class="kv">
          <dt>Version</dt><dd>${esc(meta.version || "?")}</dd>
          <dt>Rechte</dt><dd>${meta.is_admin ? "Administrator" : "Standardbenutzer (eingeschränkte Prüftools)"}</dd>
          <dt>Analyse-Quellen</dt><dd>Windows-Ereignisprotokolle (System/Anwendung), Minidumps, Systeminfo (CIM)</dd>
          <dt>Datenschutz</dt><dd>Alle Daten bleiben auf diesem Rechner; es werden keine Daten hochgeladen.</dd>
        </dl>
      </section>

      <div class="row">
        <button class="btn primary" id="cfg-save">Speichern</button>
        <span id="cfg-result" style="font-size:13px;color:var(--ink-2)"></span>
      </div>
    </div>`;

  const feedInput = root.querySelector("#cfg-feed");
  const saveResult = root.querySelector("#cfg-result");
  const updResult = root.querySelector("#update-result");
  const downloadBtn = root.querySelector("#update-download");

  root.querySelector("#cfg-save").addEventListener("click", async () => {
    saveResult.textContent = "…";
    try {
      const saved = await api.put("/api/config", {
        days: Number(root.querySelector("#cfg-days").value),
        feed_url: feedInput.value.trim(),
      });
      saveResult.textContent = "Gespeichert.";
      ctx.state.configDays = saved.days;
    } catch (e) {
      saveResult.textContent = e.message;
    }
  });

  root.querySelector("#update-check").addEventListener("click", async () => {
    updResult.textContent = "Prüfe …";
    downloadBtn.hidden = true;
    try {
      const info = await api.post("/api/update/check");
      if (info.available) {
        updResult.textContent = `Version ${info.latest} verfügbar (installiert: ${info.current}).` +
          (info.notes ? ` Hinweise: ${info.notes}` : "");
        if (status.state === "exe") {
          // EXE ersetzt sich nicht selbst — Download-Link anbieten
          const url = info.exe_url || info.release_url || info.zip_url;
          updResult.innerHTML += ` <a href="${esc(url)}" target="_blank" rel="noopener">Neue Version herunterladen</a>`;
        } else {
          downloadBtn.hidden = false;
        }
      } else {
        updResult.textContent = `Du bist aktuell (Version ${info.current}).`;
      }
    } catch (e) {
      updResult.textContent = e.message;
    }
  });

  downloadBtn.addEventListener("click", async () => {
    updResult.textContent = "Lade Update …";
    try {
      const r = await api.post("/api/update/download");
      updResult.textContent = `Version ${r.staged_version} geladen und geprüft — ${r.hint}`;
      downloadBtn.hidden = true;
    } catch (e) {
      updResult.textContent = e.message;
    }
  });
}
