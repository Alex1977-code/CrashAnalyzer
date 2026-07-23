/* Prüftools-Seite: Karten mit Start/Abbrechen, Live-Konsole, Ergebnis-Verdikt. */
import { api } from "../api.js";
import { esc, fmtDateTime, verdictBadge } from "../format.js";

const pollers = new Map();   // run_id -> interval id

function stopPoller(runId) {
  if (pollers.has(runId)) {
    clearInterval(pollers.get(runId));
    pollers.delete(runId);
  }
}

export function stopAllPollers() {
  for (const id of pollers.values()) clearInterval(id);
  pollers.clear();
}

function toolCard(t) {
  const badges = [
    t.needs_admin ? `<span class="badge">Administrator</span>` : "",
    t.repairs ? `<span class="badge status-warning">verändert System</span>` : `<span class="badge">nur lesend</span>`,
    `<span class="badge">${esc(t.duration_hint)}</span>`,
  ].join("");
  const last = t.last_result && t.last_result.result ? `
    <div class="lastresult">
      <div class="row" style="gap:8px">${verdictBadge(t.last_result.result.verdict)}
        <span style="color:var(--muted);font-size:12px">zuletzt ${fmtDateTime(t.last_result.finished)}</span></div>
      <p class="sum" style="margin-top:4px">${esc(t.last_result.result.summary)}</p>
      ${t.last_result.result.details ? `<div class="result-details">${esc(t.last_result.result.details)}</div>` : ""}
    </div>` : "";
  const volumeInput = t.id === "chkdsk" ? `
    <label class="field" style="width:90px">Laufwerk
      <input type="text" value="C:" pattern="[A-Za-z]:" maxlength="2" data-volume aria-label="Laufwerksbuchstabe">
    </label>` : "";
  return `
    <article class="card tool" data-tool="${esc(t.id)}">
      <header>
        <div class="grow">
          <h3>${esc(t.name)}</h3>
          <p class="desc">${esc(t.description)}</p>
        </div>
      </header>
      <div class="meta">${badges}</div>
      ${t.warning ? `<div class="banner warn">${esc(t.warning)}</div>` : ""}
      <div class="row">
        ${volumeInput}
        <button class="btn primary" data-start ${t.available ? "" : "disabled"}
          title="${t.available ? "" : "Benötigt Administratorrechte — App über CrashAnalyzer.bat (Als Administrator) starten"}">
          Starten</button>
        <button class="btn danger" data-cancel hidden>Abbrechen</button>
        <span class="error-inline" data-error></span>
      </div>
      <div class="console" data-console hidden aria-live="polite"></div>
      <div data-result>${last}</div>
    </article>`;
}

function attachRun(card, toolId, runId, onDone) {
  const consoleEl = card.querySelector("[data-console]");
  const startBtn = card.querySelector("[data-start]");
  const cancelBtn = card.querySelector("[data-cancel]");
  const errEl = card.querySelector("[data-error]");
  consoleEl.hidden = false;
  consoleEl.textContent = "";
  startBtn.disabled = true;
  cancelBtn.hidden = false;
  errEl.textContent = "";
  let offset = 0;

  const tick = async () => {
    try {
      const r = await api.get(`/api/tools/runs/${runId}?offset=${offset}`);
      if (r.output_delta) {
        consoleEl.textContent += r.output_delta;
        consoleEl.scrollTop = consoleEl.scrollHeight;
      }
      offset = r.next_offset;
      if (r.status !== "running") {
        stopPoller(runId);
        startBtn.disabled = false;
        cancelBtn.hidden = true;
        if (r.status === "failed" && r.error) errEl.textContent = r.error;
        const res = card.querySelector("[data-result]");
        if (r.result) {
          res.innerHTML = `
            <div class="lastresult">
              <div class="row" style="gap:8px">${verdictBadge(r.result.verdict)}
                <span style="color:var(--muted);font-size:12px">${r.status === "cancelled" ? "abgebrochen" : "gerade eben"}</span></div>
              <p class="sum" style="margin-top:4px">${esc(r.result.summary)}</p>
              ${r.result.details ? `<div class="result-details">${esc(r.result.details)}</div>` : ""}
            </div>`;
        } else if (r.status === "cancelled") {
          res.innerHTML = `<div class="lastresult"><p class="sum">Lauf abgebrochen.</p></div>`;
        }
        onDone && onDone(r);
      }
    } catch (e) {
      stopPoller(runId);
      startBtn.disabled = false;
      cancelBtn.hidden = true;
      errEl.textContent = e.message;
    }
  };
  pollers.set(runId, setInterval(tick, 700));
  tick();

  cancelBtn.onclick = async () => {
    try { await api.post(`/api/tools/runs/${runId}/cancel`); } catch { /* Status kommt per Poll */ }
  };
}

export async function renderTools(root, ctx) {
  root.innerHTML = `<div class="loading"><div class="spinner"></div>Lade Prüftools …</div>`;
  let tools;
  try {
    tools = await api.get("/api/tools");
  } catch (e) {
    root.innerHTML = `<div class="banner critical">${esc(e.message)}</div>`;
    return;
  }
  const adminNote = ctx.state.meta && !ctx.state.meta.is_admin
    ? `<div class="banner warn"><b>Ohne Administratorrechte gestartet.</b> Einige Prüftools (SFC, DISM,
       CHKDSK, Speicherdiagnose) sind deshalb deaktiviert. Zum Freischalten die App über
       <b>CrashAnalyzer.bat</b> starten und die Administrator-Abfrage bestätigen.</div>`
    : "";
  root.innerHTML = `
    <div class="stack">
      <section>
        <h1>Prüftools</h1>
        <p style="color:var(--ink-2);margin-top:4px">Diagnosen laufen direkt hier in der App.
        Werkzeuge, die etwas verändern, sind gekennzeichnet und starten nur auf Klick.</p>
      </section>
      ${adminNote}
      <div class="grid-tools">${tools.map(toolCard).join("")}</div>
    </div>`;

  for (const t of tools) {
    const card = root.querySelector(`[data-tool="${CSS.escape(t.id)}"]`);
    const startBtn = card.querySelector("[data-start]");
    startBtn.addEventListener("click", async () => {
      const errEl = card.querySelector("[data-error]");
      errEl.textContent = "";
      const params = {};
      const vol = card.querySelector("[data-volume]");
      if (vol) params.volume = vol.value.trim();
      try {
        const { run_id } = await api.post(`/api/tools/${t.id}/start`, { params });
        attachRun(card, t.id, run_id);
      } catch (e) {
        errEl.textContent = e.message;
      }
    });
    if (t.active_run) attachRun(card, t.id, t.active_run);   // laufenden Lauf wieder aufnehmen
  }

  if (ctx.highlightTool) {
    const card = root.querySelector(`[data-tool="${CSS.escape(ctx.highlightTool)}"]`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.style.outline = "2px solid var(--accent)";
      setTimeout(() => { card.style.outline = ""; }, 2500);
    }
    ctx.highlightTool = null;
  }
}
