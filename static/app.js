function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
const S = io();
let aiTs = null;

S.on("state", d => {
  $("clock").textContent = d.time;
  conn(d.connected);
  chs(d.channels);
  sim(d.sim);
  room(d.room);
  if (d.suggestion) ai(d.suggestion, d.time);
  if (d.ai_stats) aiStats(d.ai_stats);
  if (d.sim) scene(d.sim);
  modeUpdate(d.live);
});

function modeUpdate(live) {
  const btn = $("mode-btn");
  if (live) {
    btn.textContent = "LIVE";
    btn.className = "badge b-live";
  } else {
    btn.textContent = "SIMULATION";
    btn.className = "badge b-sim";
  }
}

$("mode-btn").addEventListener("click", function() {
  fetch("/api/mode", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"})
    .then(r => r.json())
    .then(d => { if (d.error) alert(d.error); })
    .catch(e => alert("Failed: " + e));
});

function $(id) { return document.getElementById(id); }
function pct(db) { return Math.max(0, Math.min(100, (db + 60) / 66 * 100)); }
function bc(db)  { return db > -6 ? "red" : db > -18 ? "yellow" : "green"; }
function st(db)  { return db <= -55 ? "s" : db > -6 ? "clip" : db > -18 ? "hot" : "active"; }

function conn(ok) {
  const el = $("conn");
  el.textContent = ok ? "CONNECTED" : "OFFLINE";
  el.className = `badge b-conn ${ok ? "on" : "off"}`;
}

function chs(data) {
  const grid = $("chs");
  const keys = Object.keys(data).map(Number).sort((a,b)=>a-b);
  let act=0, loud={db:-999,n:""}, quiet={db:999,n:""};

  keys.forEach(ch => {
    const c = data[ch], db = c.db, s = st(db), p = pct(db);
    const dbStr = s==="s" ? "—" : db.toFixed(1);
    const faderStr = c.fader_db > -90 ? `${c.fader_db > 0 ? "+" : ""}${c.fader_db}` : "—";

    if (s !== "s") {
      act++;
      if (db > loud.db) loud = {db, n: c.name};
      if (db < quiet.db) quiet = {db, n: c.name};
    }

    let row = $(`r${ch}`);
    if (!row) {
      row = document.createElement("div");
      row.id = `r${ch}`;
      row.innerHTML = `
        <div class="cn">${ch}</div>
        <div class="cname" id="n${ch}">${esc(c.name)}</div>
        <div class="mw"><div class="mb green" id="b${ch}"></div></div>
        <div class="cdb s" id="d${ch}">—</div>
        <div class="cfader" id="f${ch}">—</div>
        <div class="ctag s" id="t${ch}">–</div>`;
      row.className = "cr";
      grid.appendChild(row);
    }

    row.className = `cr ${s==="s"?"":s}`;
    const nEl = $(`n${ch}`);
    nEl.textContent = c.name;
    nEl.className = `cname ${s==="s"?"s":""}`;
    const bar = $(`b${ch}`);
    bar.style.width = `${p}%`;
    bar.className = `mb ${bc(db)}`;
    const dEl = $(`d${ch}`);
    dEl.textContent = dbStr;
    dEl.className = `cdb ${s}`;
    $(`f${ch}`).textContent = faderStr;
    const tEl = $(`t${ch}`);
    tEl.textContent = {s:"–",active:"ON",hot:"HOT",clip:"CLIP"}[s];
    tEl.className = `ctag ${s==="active"?"on":s}`;
  });

  $("sa").textContent = act;
  $("sl").textContent = loud.db > -999 ? `${loud.n} (${loud.db.toFixed(1)})` : "—";
  $("sq").textContent = quiet.db < 999 && act > 1 ? `${quiet.n} (${quiet.db.toFixed(1)})` : "—";
  if (act >= 2) {
    const sp = loud.db - quiet.db;
    const el = $("ss");
    el.textContent = `${sp.toFixed(1)} dB`;
    el.style.color = sp > 15 ? "var(--yellow)" : "var(--text)";
  }

  const clip = keys.filter(ch => data[ch].db > -3);
  const ab = $("alert");
  if (clip.length) {
    ab.textContent = `⚠ HIGH SIGNAL: ${clip.map(ch=>data[ch].name).join(", ")} — check gain`;
    ab.className = "on";
  } else {
    ab.className = "";
  }
}

function sim(d) {
  if (!d) return;
  const props = d.proposals || {};
  const keys = Object.keys(props).map(Number).sort((a,b)=>a-b);
  const wrap = $("sim");

  if (keys.length === 0) {
    wrap.innerHTML = '<div class="sim-empty">No active channels</div>';
    return;
  }

  let html = "";
  keys.forEach(ch => {
    const p = props[ch];
    const sign = p.delta_db > 0 ? "+" : "";
    const deltaStr = Math.abs(p.delta_db) < 0.1 ? "·" : `${sign}${p.delta_db}`;
    const deltaCls = p.delta_db > 0.3 ? "pos" : p.delta_db < -0.3 ? "neg" : "zero";
    const act = p.action;

    // Bar widths: map -60..+10 dB to 0..100%
    const curPct = Math.max(0, Math.min(100, (p.current_fader_db + 60) / 70 * 100));
    const newPct = Math.max(0, Math.min(100, (p.proposed_fader_db + 60) / 70 * 100));
    const tgtPct = Math.max(0, Math.min(100, (p.target_db + 60) / 70 * 100));

    html += `
      <div class="sr">
        <div class="sr-name">${esc(p.name)}</div>
        <div class="sr-bar-wrap">
          <div class="sr-current" style="width:${curPct}%"></div>
          <div class="sr-proposed ${act}" style="width:${newPct}%"></div>
          <div class="sr-target" style="left:${tgtPct}%"></div>
        </div>
        <div class="sr-delta ${deltaCls}">${deltaStr}</div>
      </div>`;
  });

  wrap.innerHTML = html;
}

function scene(d) {
  $("scene").textContent = d.scene || "—";
  const h = d.mix_health ?? 100;
  const bar = $("h-bar");
  bar.style.width = `${h}%`;
  bar.className = `h-bar ${h>70?"green":h>40?"yellow":"red"}`;
  const lbl = $("h-lbl");
  lbl.textContent = `${h}%`;
  lbl.style.color = h>70?"var(--green)":h>40?"var(--yellow)":"var(--red)";
}

function room(r) {
  const avail = r.available !== false;
  const el = $("r-db");
  if (!avail) {
    el.textContent = "Unavailable";
    el.className = "room-db";
    el.style.color = "var(--muted)";
    $("r-bar").style.width = "0%";
    const sp = $("sp");
    sp.textContent = "NO MIC";
    sp.className = "sp off";
    $("freqs").innerHTML = r.error ? `<span class="ftag" title="${esc(r.error)}">mic error</span>` : "";
    return;
  }
  el.style.color = "";
  const db = r.db, p = pct(db);
  el.textContent = db > -90 ? `${db.toFixed(1)} dB` : "— dB";
  el.className = `room-db ${db>-6?"loud":db>-18?"hot":"ok"}`;
  const bar = $("r-bar");
  bar.style.width = `${p}%`;
  bar.className = `r-bar ${bc(db)}`;
  const sp = $("sp");
  sp.textContent = r.speech_detected ? "SPEECH ●" : "SPEECH";
  sp.className = `sp ${r.speech_detected?"on":"off"}`;
  $("freqs").innerHTML = (r.dominant_freqs||[]).map(f=>`<span class="ftag">${f} Hz</span>`).join("");
}

function ai(text, time) {
  const el = $("ai-text");
  if (el.textContent !== text) {
    el.textContent = text;
    $("ai-ts").textContent = `Updated ${time}`;
  }
}

function aiStats(s) {
  $("ai-req").textContent = s.requests;
  $("ai-tok").textContent = (s.input_tokens + s.output_tokens).toLocaleString();
  $("ai-cost").textContent = `$${s.total_cost.toFixed(4)}`;
}
