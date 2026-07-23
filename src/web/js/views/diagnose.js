/* Diagnose-Seite: Kernaussage, Kennzahlen, Zeitleiste, Episoden, Empfehlungen. */
import { esc, fmtDateTime, verdictBadge, STABILITY, KIND_LABEL } from "../format.js";
import { renderTimeline } from "../timeline.js";

const CONFIDENCE_HINT = {
  hoch: "Ursache eindeutig protokolliert",
  mittel: "starke Indizien, keine Gewissheit",
  niedrig: "Indizienlage dünn — Ursache eingegrenzt",
};

function sysChips(sys, meta) {
  const chips = [];
  if (sys.model) chips.push(`${esc(sys.manufacturer || "")} ${esc(sys.model)}`.trim());
  if (sys.os_name) chips.push(`${esc(sys.os_name)} (Build ${esc(sys.build || "?")})`);
  if (sys.ram_gb) chips.push(`${sys.ram_gb} GB RAM`);
  if (sys.boot_time) chips.push(`läuft seit ${fmtDateTime(sys.boot_time)}`);
  if (sys.is_laptop) chips.push("Laptop");
  return chips.map((c) => `<span class="badge">${c}</span>`).join("");
}

function stabilityTile(a) {
  const s = STABILITY[a.summary.stability] || STABILITY.instabil;
  return `
    <div class="card tile">
      <div class="label">Stabilität</div>
      <div class="value"><span class="badge ${s.cls}" style="font-size:15px"><span aria-hidden="true">${s.icon}</span>${s.label}</span></div>
      <div class="hint">${a.summary.main_suspect ? "Hauptverdacht: " + esc(a.summary.main_suspect) : "keine Auffälligkeiten"}</div>
    </div>`;
}

function episodeCard(epi, idx, total) {
  const evidence = epi.evidence.length
    ? `<ul class="evidence">${epi.evidence.map((e) =>
        `<li>${esc(e.text)} <span style="color:var(--muted)">(${fmtDateTime(e.time)})</span></li>`).join("")}</ul>`
    : "";
  const bug = epi.bugcheck;
  const tech = `
    <details class="tech">
      <summary>Technische Details</summary>
      <dl class="kv">
        ${bug ? `<dt>Stopcode</dt><dd class="mono">${esc(bug.hex)} — ${esc(bug.name)}</dd>
                 <dt>Parameter</dt><dd class="mono">${esc((bug.params || []).join(", ") || "–")}</dd>
                 <dt>Quelle</dt><dd>${esc(bug.source)}</dd>` : ""}
        ${epi.dump_path ? `<dt>Speicherabbild</dt><dd class="mono">${esc(epi.dump_path)}</dd>` : ""}
        <dt>Einschätzung</dt><dd>${esc(epi.confidence_reason)}</dd>
        <dt>Ereignis-ID</dt><dd class="mono">${esc(epi.id)}</dd>
      </dl>
    </details>`;
  return `
    <article class="card episode" aria-label="Absturz ${idx + 1} von ${total}">
      <header>
        <h3>${esc(epi.title)}</h3>
        <span class="badge">${esc(KIND_LABEL[epi.kind] || epi.kind)}</span>
        <span class="badge" title="${esc(CONFIDENCE_HINT[epi.confidence] || "")}">Sicherheit: ${esc(epi.confidence)}</span>
        <span class="when">${fmtDateTime(epi.time)}</span>
      </header>
      <p class="what">${esc(epi.what)}</p>
      <p class="why"><b>Warum:</b> ${esc(epi.why)}</p>
      ${evidence}
      ${tech}
    </article>`;
}

function recommendationList(recs, goTool) {
  if (!recs.length) return "";
  const CAT = { sofort: "Sofort", diagnose: "Diagnose", hardware: "Hardware", profi: "Profi" };
  const items = recs.map((r, i) => `
    <div class="rec">
      <div class="prio">${i + 1}</div>
      <div class="body">
        <span class="cat">${CAT[r.category] || r.category}</span>
        <b>${esc(r.title)}</b>
        <p>${esc(r.text)}</p>
      </div>
      ${r.tool_id ? `<button class="btn small" data-goto-tool="${esc(r.tool_id)}">Prüftool öffnen</button>` : ""}
    </div>`).join("");
  return `
    <section class="card">
      <div class="section-title"><h2>Empfohlene Schritte</h2><span class="count">in dieser Reihenfolge</span></div>
      <div class="reclist" style="margin-top:12px">${items}</div>
    </section>`;
}

function appCrashTable(ac) {
  if (!ac.total) return "";
  const rows = ac.groups.map((g) => `
    <tr>
      <td>${esc(g.app)}</td>
      <td>${g.kind === "hang" ? "reagierte nicht" : "abgestürzt"}</td>
      <td class="num">${g.count}</td>
      <td>${fmtDateTime(g.last_time)}</td>
      <td class="mono">${esc(g.top_module || "–")}</td>
    </tr>`).join("");
  return `
    <section class="card">
      <div class="section-title"><h2>Programmabstürze</h2>
        <span class="count">${ac.total} im Zeitraum — betreffen einzelne Programme, nicht den ganzen Rechner</span></div>
      <table class="plain" style="margin-top:10px">
        <thead><tr><th>Programm</th><th>Art</th><th>Anzahl</th><th>Zuletzt</th><th>Fehlermodul</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </section>`;
}

export function renderDiagnose(root, ctx) {
  const a = ctx.state.analysis;
  if (!a) {
    root.innerHTML = `<div class="loading"><div class="spinner"></div>Analysiere Ereignisprotokolle, Abstürze und Speicherabbilder …</div>`;
    return;
  }
  const s = a.summary;
  const patterns = a.patterns.map((p) =>
    `<div class="banner ${p.kind === "cluster" ? "critical" : "warn"}"><b>Muster erkannt:</b> ${esc(p.text)}</div>`).join("");

  const episodes = a.episodes.length
    ? a.episodes.map((e, i) => episodeCard(e, i, a.episodes.length)).join("")
    : `<section class="card empty-hero">
         <div class="big" aria-hidden="true">✓</div>
         <h2>Keine Systemabstürze gefunden</h2>
         <p>In den letzten ${a.days} Tagen wurde kein Bluescreen, kein unerwarteter Neustart und
         kein Stromverlust protokolliert.${s.app_crash_count ? " Die unten aufgeführten Programmabstürze betrafen nur einzelne Anwendungen." : ""}</p>
         <p style="margin-top:6px">Hinweis: Ein eingefrorener Rechner, der von selbst wieder reagiert,
         hinterlässt keine Spur im Protokoll.</p>
       </section>`;

  const memdiag = a.memdiag.last_run ? `
    <div class="banner"><b>Speicherdiagnose:</b> zuletzt ${fmtDateTime(a.memdiag.last_run)} —
    ${esc(a.memdiag.result || "Ergebnis unbekannt")}</div>` : "";

  const limits = a.limits.length ? `
    <section class="card">
      <details class="tech" style="border-top:0;margin-top:0;padding-top:0">
        <summary>Grenzen dieser Analyse (${a.limits.length})</summary>
        <ul class="limits">${a.limits.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
      </details>
    </section>` : "";

  root.innerHTML = `
    <div class="stack">
      <section class="card">
        <div class="row" style="justify-content:space-between">
          <div style="flex:1;min-width:300px">
            <p class="headline">${esc(s.headline)}</p>
            <div class="syschips">${sysChips(a.system || {}, ctx.state.meta)}</div>
          </div>
          <div class="row" style="flex:none">
            <label class="field">Zeitraum
              <select id="days-select">
                ${[7, 14, 30, 90].map((d) => `<option value="${d}" ${d === a.days ? "selected" : ""}>${d} Tage</option>`).join("")}
              </select>
            </label>
            <button class="btn primary" id="refresh-btn" style="align-self:end">Neu analysieren</button>
          </div>
        </div>
      </section>

      <div class="grid-tiles">
        <div class="card tile">
          <div class="label">Systemabstürze</div>
          <div class="value" style="color:${s.crash_count ? "var(--series-crash)" : "inherit"}">${s.crash_count}</div>
          <div class="hint">Bluescreens, Stromverlust, harte Neustarts</div>
        </div>
        <div class="card tile">
          <div class="label">Programmabstürze</div>
          <div class="value">${s.app_crash_count}</div>
          <div class="hint">einzelne Anwendungen (sekundär)</div>
        </div>
        ${stabilityTile(a)}
        <div class="card tile">
          <div class="label">Analysiert am</div>
          <div class="value" style="font-size:17px">${fmtDateTime(a.generated_at)}</div>
          <div class="hint">Zeitraum: letzte ${a.days} Tage</div>
        </div>
      </div>

      ${patterns}
      ${memdiag}

      <section class="card">
        <div class="section-title"><h2>Zeitleiste</h2><span class="count">alle protokollierten Ereignisse</span></div>
        <div class="timeline-wrap" id="timeline" style="margin-top:8px"></div>
      </section>

      ${a.episodes.length ? `<div class="section-title"><h2>Abstürze im Detail</h2><span class="count">neueste zuerst</span></div>` : ""}
      ${episodes}
      ${recommendationList(a.recommendations, ctx.goTool)}
      ${appCrashTable(a.app_crashes)}
      ${limits}
    </div>`;

  renderTimeline(root.querySelector("#timeline"), a);
  root.querySelector("#refresh-btn").addEventListener("click", () => ctx.reload({ refresh: true }));
  root.querySelector("#days-select").addEventListener("change", (e) =>
    ctx.reload({ days: Number(e.target.value) }));
  root.querySelectorAll("[data-goto-tool]").forEach((b) =>
    b.addEventListener("click", () => ctx.goTool(b.dataset.gotoTool)));
}
