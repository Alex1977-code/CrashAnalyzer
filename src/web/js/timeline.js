/* Zeitleiste: Ereignis-Punktdiagramm (SVG) mit drei Bahnen und Hover-Tooltip.
   Farben: Systemabstürze = Serie 1 (blau), Programmabstürze = Serie 2 (orange),
   Indizien = neutral. Palette validiert (dataviz-Skill, hell+dunkel). */
import { esc, fmtDateTime, KIND_LABEL } from "./format.js";

const W = 1100, H = 170;
const PAD_L = 118, PAD_R = 16, AXIS_Y = H - 26;
const LANES = [
  { key: "crash", label: "Systemabstürze", y: 44 },
  { key: "evidence", label: "Indizien", y: 84 },
  { key: "app", label: "Programmabstürze", y: 124 },
];

function xScale(t, t0, t1) {
  const clamped = Math.min(Math.max(t, t0), t1);
  return PAD_L + ((clamped - t0) / (t1 - t0)) * (W - PAD_L - PAD_R);
}

function ticks(t0, t1, n = 6) {
  const out = [];
  const span = t1 - t0;
  for (let i = 0; i <= n; i++) {
    const t = t0 + (span * i) / n;
    const d = new Date(t);
    out.push({ x: xScale(t, t0, t1), label: d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) });
  }
  return out;
}

function collectPoints(analysis) {
  const pts = [];
  for (const epi of analysis.episodes) {
    pts.push({
      lane: "crash", time: +new Date(epi.time), r: 6,
      title: epi.title, sub: `${fmtDateTime(epi.time)} · Einschätzung: ${epi.confidence}`,
      fill: "var(--series-crash)", ring: true,
    });
    for (const ev of epi.evidence) {
      pts.push({
        lane: "evidence", time: +new Date(ev.time), r: 3.5,
        title: ev.text, sub: fmtDateTime(ev.time),
        fill: "var(--muted)", ring: false,
      });
    }
  }
  for (const g of analysis.app_crashes.groups) {
    pts.push({
      lane: "app", time: +new Date(g.last_time), r: 5,
      title: `${g.app} (${g.kind === "hang" ? "hängt" : "abgestürzt"}, ${g.count}×)`,
      sub: `zuletzt ${fmtDateTime(g.last_time)}`,
      fill: "var(--series-app)", ring: true,
    });
  }
  return pts.filter((p) => !isNaN(p.time));
}

export function renderTimeline(container, analysis) {
  const days = analysis.days || 30;
  const t1 = +new Date(analysis.generated_at || Date.now());
  const t0 = t1 - days * 86400_000;
  const pts = collectPoints(analysis);
  const laneY = Object.fromEntries(LANES.map((l) => [l.key, l.y]));

  const grid = ticks(t0, t1).map((t) =>
    `<line x1="${t.x}" y1="18" x2="${t.x}" y2="${AXIS_Y}" stroke="var(--grid)" stroke-width="1"/>
     <text x="${t.x}" y="${AXIS_Y + 16}" text-anchor="middle" font-size="11" fill="var(--muted)">${t.label}</text>`
  ).join("");

  const laneLabels = LANES.map((l) =>
    `<text x="${PAD_L - 12}" y="${l.y + 4}" text-anchor="end" font-size="11.5" fill="var(--muted)">${l.label}</text>
     <line x1="${PAD_L}" y1="${l.y}" x2="${W - PAD_R}" y2="${l.y}" stroke="var(--grid)" stroke-width="1" stroke-dasharray="1 5"/>`
  ).join("");

  let dots = "";
  const laneCount = { crash: 0, evidence: 0, app: 0 };
  for (const p of pts.sort((a, b) => a.time - b.time)) {
    const i = laneCount[p.lane]++;
    const jitter = p.lane === "evidence" ? ((i % 3) - 1) * 8 : 0;
    const cx = xScale(p.time, t0, t1).toFixed(1);
    const cy = laneY[p.lane] + jitter;
    dots += `
      <g class="pt" data-title="${esc(p.title)}" data-sub="${esc(p.sub)}">
        <circle cx="${cx}" cy="${cy}" r="12" fill="transparent"/>
        <circle cx="${cx}" cy="${cy}" r="${p.r}" fill="${p.fill}"
                ${p.ring ? 'stroke="var(--surface)" stroke-width="2"' : 'opacity="0.8"'}/>
      </g>`;
  }

  const empty = pts.length === 0
    ? `<text x="${(W + PAD_L - PAD_R) / 2}" y="${H / 2 - 6}" text-anchor="middle" font-size="13" fill="var(--muted)">Keine Ereignisse im gewählten Zeitraum</text>`
    : "";

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Zeitleiste der Ereignisse der letzten ${days} Tage">
      ${grid}
      ${laneLabels}
      <line x1="${PAD_L}" y1="${AXIS_Y}" x2="${W - PAD_R}" y2="${AXIS_Y}" stroke="var(--baseline)" stroke-width="1"/>
      ${empty}
      ${dots}
    </svg>
    <div class="legend" role="list">
      <span class="item" role="listitem"><span class="swatch" style="background:var(--series-crash)"></span>Systemabsturz</span>
      <span class="item" role="listitem"><span class="swatch" style="background:var(--series-app)"></span>Programmabsturz</span>
      <span class="item" role="listitem"><span class="swatch" style="background:var(--muted)"></span>Indiz (Fehler-Ereignis)</span>
    </div>`;

  const tooltip = document.getElementById("viz-tooltip");
  container.querySelectorAll("g.pt").forEach((g) => {
    g.addEventListener("mousemove", (e) => {
      tooltip.style.display = "block";
      tooltip.innerHTML = `<div class="t-title">${g.dataset.title}</div><div class="t-sub">${g.dataset.sub}</div>`;
      const pad = 14;
      const x = Math.min(e.clientX + pad, window.innerWidth - tooltip.offsetWidth - 8);
      const y = Math.min(e.clientY + pad, window.innerHeight - tooltip.offsetHeight - 8);
      tooltip.style.left = `${x}px`;
      tooltip.style.top = `${y}px`;
    });
    g.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
  });
}

export { KIND_LABEL };
