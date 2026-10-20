function setDelays(vals) {
  DL.forEach(([r, n, v], i) => {
    const x = Math.max(0, Math.min(3000, +vals[i] || 0));
    const act = document.activeElement.id;
    if (act === r || act === n) return;
    $(r).max = 3000;
    $(r).value = x;
    $(n).value = x;
    $(v).textContent = x;
  });
}
function delayBody() {
  const o = {};
  DL.forEach(([r, n, v, k]) => {
    o[k] = +($(n).value || 0);
  });
  return o;
}
const isDelayCtl = (id) => DL.some(([r, n]) => id === r || id === n);
const DL_ENGINE_MAX = 750;
function dlWarn() {
  const el = $("dl_warn");
  if (!el) return;
  const vals = [+$("n_delay").value || 0];
  [
      ["p_pip", "n_delay1"],
      ["p_pip2", "n_delay2"],
      ["p_pip3", "n_delay3"],
    ].forEach(([s, n]) => {
      if ($(s).value) vals.push(+$(n).value || 0);
    });
  el.hidden = !(Math.max(...vals) > DL_ENGINE_MAX);
}
const pipOpt = (k, sel) =>
  `<option value="${esc(k.key)}"${k.key === sel ? " selected" : ""}>${esc(k.name)}${pipCams.filter((x) => x.name === k.name).length > 1 ? " (" + esc(k.key) + ")" : ""}${k.state === "live" ? " · sendet" : ""}</option>`;
function renderPreview() {
  const box = $("pvbox");
  if (!box) return;
  const W = box.clientWidth || 520,
    H = Math.round((W * 9) / 16);
  box.style.height = H + "px";
  const m = W / 60,
    canFree = pipCorners.length > 5;
  const nm = (k) => {
    const x = pipCams.find((y) => y.key === k);
    return x ? x.name : k;
  };
  let out = '<div class="pvmain">Hauptbild: ' + esc(nm($("p_main").value)) + "</div>";
  [
    ["p_pip", "p_corner", 1],
    ["p_pip2", "p_corner2", 2],
    ["p_pip3", "p_corner3", 3],
  ].forEach(([cs, co, k]) => {
    const cam = $(cs).value;
    if (!cam) return;
    const size = Math.max(1, Math.min(100, +$("p_size" + k).value || 25));
    let pw = (W * size) / 100;
    const ph = (pw * 9) / 16;
    const cinfo = pipCams.find((y) => y.key === cam) || {},
      portrait = cinfo.w > 0 && cinfo.h > cinfo.w;
    if (portrait) pw = (ph * cinfo.w) / cinfo.h;
    const st = styleOf(k),
      cr = portrait ? { l: 0, r: 0, t: 0, b: 0 } : st.crop,
      cw = (pw * (CROP_W - cr.l - cr.r)) / CROP_W,
      ch = (ph * (CROP_H - cr.t - cr.b)) / CROP_H,
      sc = W / 1920;
    const bw = st.border.enabled ? Math.max(1, Math.round(st.border.width * sc)) : 0,
      rad = st.radius ? Math.min(Math.round(st.radius * sc), Math.min(cw, ch) / 2) : 0;
    const c = +$(co).value,
      f = posFree[k];
    let x, y;
    if (c === 5) {
      x = (f.x / 1000) * (W - cw);
      y = (f.y / 1000) * (H - ch);
    } else if (c === 4) {
      x = (W - cw) / 2;
      y = H - ch - m;
    } else {
      x = c & 1 ? W - cw - m : m;
      y = c & 2 ? H - ch - m : m;
    }
    x = Math.max(0, Math.min(W - cw, x));
    y = Math.max(0, Math.min(H - ch, y));
    out +=
      `<div class="pvpip pv${k}${st.visible ? "" : " off"}" data-k="${k}" data-co="${co}" style="left:${x}px;top:${y}px;width:${cw}px;height:${ch}px;opacity:${st.visible ? 1 : 0.18};border-radius:${rad}px">` +
      `<div class="pvin" style="left:${(-pw * cr.l) / CROP_W}px;top:${(-ph * cr.t) / CROP_H}px;width:${pw}px;height:${ph}px"></div><b>${k}</b><span>${esc(nm(cam))}${st.visible ? "" : " (ausgeblendet)"}</span>` +
      (bw
        ? `<i class="pvrim" style="border:${bw}px solid ${hexRgba(st.border.color, st.border.opacity / 100)};border-radius:${rad}px"></i>`
        : "") +
      `</div>`;
  });
  box.innerHTML = out;
  $("pvnote").textContent = canFree
    ? "Bilder mit Maus oder Finger ziehen. Danach „Bildaufbau speichern“."
    : "Freies Verschieben braucht den neuen Überlagerungs-Baustein (kommt beim Software-Update).";
}
(function () {
  const box = $("pvbox");
  let drag = null;
  box.addEventListener("pointerdown", (e) => {
    const el = e.target.closest(".pvpip");
    if (!el || pipCorners.length <= 5) return;
    e.preventDefault();
    box.setPointerCapture(e.pointerId);
    const r = el.getBoundingClientRect();
    drag = { el, k: +el.dataset.k, co: el.dataset.co, dx: e.clientX - r.left, dy: e.clientY - r.top };
    el.classList.add("drag");
  });
  box.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const b = box.getBoundingClientRect(),
      W = b.width,
      H = b.height,
      w = drag.el.offsetWidth,
      h = drag.el.offsetHeight;
    const x = Math.max(0, Math.min(W - w, e.clientX - b.left - drag.dx)),
      y = Math.max(0, Math.min(H - h, e.clientY - b.top - drag.dy));
    drag.el.style.left = x + "px";
    drag.el.style.top = y + "px";
    posFree[drag.k] = { x: W > w ? Math.round((x / (W - w)) * 1000) : 0, y: H > h ? Math.round((y / (H - h)) * 1000) : 0 };
  });
  const end = () => {
    if (!drag) return;
    drag.el.classList.remove("drag");
    $(drag.co).value = FREE_ID;
    pipeDirty = true;
    $("pipeerr").textContent = "Nicht gespeichert: Mit „Bildaufbau speichern“ übernehmen.";
    drag = null;
  };
  box.addEventListener("pointerup", end);
  box.addEventListener("pointercancel", end);
  window.addEventListener("resize", () => renderPreview());
})();
function pipConstrain(v) {
  v = v || {
    main: $("p_main").value,
    pip: $("p_pip").value,
    pip2: $("p_pip2").value,
    pip3: $("p_pip3").value,
    c1: $("p_corner").value,
    c2: $("p_corner2").value,
    c3: $("p_corner3").value,
  };
  const has = (k) => pipCams.some((x) => x.key === k),
    free = (ex) => pipCams.filter((x) => !ex.includes(x.key));
  const main = has(v.main) ? v.main : (pipCams[0] || {}).key || "";
  pipPrevMain = main;
  const pip = has(v.pip) && v.pip !== main ? v.pip : (free([main])[0] || {}).key || "";
  const pip2 = has(v.pip2) && v.pip2 !== main && v.pip2 !== pip ? v.pip2 : "";
  const pip3 = pip2 && has(v.pip3) && v.pip3 !== main && v.pip3 !== pip && v.pip3 !== pip2 ? v.pip3 : "";
  const fill = (id, list, val, none) => {
    const el = $(id);
    el.innerHTML =
      (none ? '<option value="">keins</option>' : "") +
      (list.map((k) => pipOpt(k, val)).join("") || (none ? "" : '<option value="">keine Kamera</option>'));
    el.value = val;
  };
  fill("p_main", pipCams, main, false);
  fill("p_pip", free([main]), pip, false);
  fill("p_pip2", free([main, pip]), pip2, true);
  fill("p_pip3", pip2 ? free([main, pip, pip2]) : [], pip3, true);
  const ids = pipCorners.map((n, i) => String(i));
  const taken = (i, used) => i !== FREE_ID && used.includes(i);
  const c1 = ids.includes(String(v.c1)) ? String(v.c1) : "3";
  let c2 = String(v.c2);
  if (taken(c2, [c1]) || !ids.includes(c2)) c2 = ids.find((i) => !taken(i, [c1])) || "";
  $("p_corner").innerHTML = pipCorners.map((n, i) => `<option value="${i}">${esc(n)}</option>`).join("");
  $("p_corner").value = c1;
  $("p_corner2").innerHTML = pipCorners.map((n, i) => (taken(String(i), [c1]) ? "" : `<option value="${i}">${esc(n)}</option>`)).join("");
  $("p_corner2").value = c2;
  let c3 = String(v.c3);
  if (taken(c3, [c1, c2]) || !ids.includes(c3)) c3 = ids.find((i) => !taken(i, [c1, c2])) || "";
  $("p_corner3").innerHTML = pipCorners
    .map((n, i) => (taken(String(i), [c1, c2]) ? "" : `<option value="${i}">${esc(n)}</option>`))
    .join("");
  $("p_corner3").value = c3;
  const nm = (k) => {
    const x = pipCams.find((y) => y.key === k);
    return x ? x.name : k;
  };
  const au = $("p_audio"),
    prev = au.value;
  au.innerHTML = [
    ["main", "Hauptbild", main],
    ["pip", "Kleines Bild 1", pip],
    ["pip2", "Kleines Bild 2", pip2],
    ["pip3", "Kleines Bild 3", pip3],
  ]
    .filter((x) => x[2])
    .map((x) => `<option value="${x[0]}">${x[1]} (${esc(nm(x[2]))})</option>`)
    .join("");
  au.value = [...au.options].some((o) => o.value === prev) ? prev : "main";
  $("p_corner2").disabled = !pip2;
  $("p_pip3").disabled = !pip2;
  $("p_corner3").disabled = !pip3;
  $("dl2").style.display = pip2 ? "" : "none";
  $("dl3").style.display = pip3 ? "" : "none";
  const nSlots = Math.min(4, Math.max(1, pipCams.length));
  document
    .querySelectorAll("#pipecard .camcols>.camcol")
    .forEach((col, k) => col.classList.toggle("slotoff", !(k < nSlots || (k === 2 && pip2) || (k === 3 && pip3))));
  renderPreview();
}
function fcRender(d) {
  const box = $("fc_btns");
  if (!box) return;
  const c = d.config,
    byKey = Object.fromEntries((d.cameras || []).map((x) => [x.key, x])),
    nm = (k) => (byKey[k] || {}).name || k,
    fc = c.facecam || "";
  const btn = (slot, title, sub, on, off) =>
    `<button type="button" class="sec fcb${on ? " on" : ""}" data-slot="${slot}" aria-pressed="${on}"${off ? " disabled" : ""}><b>${esc(title)}</b><span class="muted">${esc(sub)}</span></button>`;
  setHtml(
    box,
    [
      ["pip", "Kleines Bild 1"],
      ["pip2", "Kleines Bild 2"],
      ["pip3", "Kleines Bild 3"],
    ]
      .map(([s, t]) => btn(s, t, c[s] ? nm(c[s]) : "nicht belegt", !!fc && c[s] === fc, !c[s]))
      .join("") + btn("", "Keine Facecam", "Der Ton folgt dem Hauptbild", !fc, false),
  );
}
async function fcRefresh() {
  try {
    fcRender(await srtlaCall("GET", "/api/pipeline"));
  } catch (e) {}
}
$("fc_btns").addEventListener("click", async (e) => {
  const b = e.target.closest("button.fcb");
  if (!b || b.disabled) return;
  const m = $("fc_msg");
  m.style.color = "";
  m.textContent = "Wird gesetzt …";
  try {
    const r = await srtlaCall("POST", "/api/pipeline/facecam", { slot: b.dataset.slot });
    m.textContent = r.note || "Gespeichert. Der Ton wechselt sofort.";
  } catch (x) {
    m.style.color = "var(--crit)";
    m.textContent = x.message;
  }
  fcRefresh();
  if (typeof sendLoad === "function") setTimeout(sendLoad, 600);
});
async function pipeLoad() {
  try {
    pipeData = await srtlaCall("GET", "/api/pipeline");
  } catch (e) {
    return;
  }
  const d = pipeData,
    c = d.config;
  fcRender(d);
  pipCams = d.cameras;
  pipCorners = d.corners;
  pipLive = d.live || {};
  if (pipeDirty || pipDelayDirty) {
    return;
  }
  if (document.activeElement.id !== "p_auto") $("p_auto").checked = c.auto_failover !== false;
  posFree = { 1: { x: c.x ?? 500, y: c.y ?? 500 }, 2: { x: c.x2 ?? 500, y: c.y2 ?? 500 }, 3: { x: c.x3 ?? 500, y: c.y3 ?? 500 } };
  [1, 2, 3].forEach((k) => {
    pipStyles[k] = Object.assign(STYLE_DEF(), (c.styles || {})[k] || {});
    pipStyles[k].crop = Object.assign({ l: 0, r: 0, t: 0, b: 0 }, pipStyles[k].crop);
    pipStyles[k].border = Object.assign(STYLE_DEF().border, pipStyles[k].border);
    pipStyles[k].opacity = 100;
    delete pipStyles[k].border.radius;
    styleFill(k);
  });
  pipConstrain({ main: c.main, pip: c.pip, pip2: c.pip2, pip3: c.pip3, c1: c.corner, c2: c.corner2 ?? 2, c3: c.corner3 ?? 0 });
  [
    ["p_size1", c.size_pct],
    ["p_size2", c.size_pct2 ?? c.size_pct],
    ["p_size3", c.size_pct3 ?? c.size_pct],
  ].forEach(([id, v]) => {
    if (document.activeElement.id !== id) $(id).value = v;
  });
  renderPreview();
  setDelays([c.main_delay_ms, c.pip_delay_ms, c.pip2_delay_ms, c.pip3_delay_ms]);
  dlWarn();
  pipLive = d.live || {};
  $("p_audio").value = c.audio;
  {
    const inPic = [c.main, c.pip, c.pip2, c.pip3].filter(Boolean),
      bar = $("swapbar");
    const order = (pipCams || []).map((x) => x.key).filter((k) => inPic.includes(k)),
      byKey = Object.fromEntries((pipCams || []).map((x) => [x.key, x]));
    bar.hidden = !(c.type === "pip" && c.main && inPic.length > 1);
    setHtml(
      $("swapbtns"),
      order
        .map((k) => {
          const cam = byKey[k] || {},
            on = k === c.main;
          const gone = !on && cam.state === "offline";
          return `<button type="button" class="${on ? "on" : "swapto"}" ${on ? 'aria-pressed="true" disabled' : gone ? `data-key="${esc(k)}"disabled` : `data-key="${esc(k)}"`} title="${on ? "Ist gerade das Hauptbild" : gone ? "Diese Kamera ist nicht verbunden und lässt sich nicht zum Hauptbild machen." : seamlessTo(c.main, k) ? "Als Hauptbild verwenden (tauscht mit dem aktuellen Hauptbild, ohne Unterbrechung der Sendung)" : "Als Hauptbild verwenden (tauscht mit dem aktuellen Hauptbild; läuft die Sendung, startet der Encoder dafür neu, etwa 5 Sekunden ohne Bild)"}"><span class="dot${cam.state === "live" ? "" : " off"}"></span>${esc(cam.name || k)}</button>`;
        })
        .join(""),
    );
  }
  let info = !c.main
    ? "Noch keine Pipeline gespeichert."
    : c.type === "pip"
      ? `Gespeichert: Bild-in-Bild, Hauptbild ${c.main}, kleines Bild ${[c.pip, c.pip2, c.pip3].filter(Boolean).join(", ")}.`
      : `Gespeichert: eine Kamera, Hauptbild ${c.main}.`;
  document.querySelectorAll(".pvs").forEach((e) => (e.hidden = d.plugin_present && d.plugin_style === false));
  if (d.needs_plugin && !d.plugin_present)
    info += " Bild-in-Bild braucht den Überlagerungs-Baustein, der noch nicht auf der Box installiert ist.";
  $("pipeinfo").textContent = info;
}
$("pipecard").addEventListener("input", (e) => {
  const id = e.target.id || "";
  if (/^p_size\d$/.test(id)) renderPreview();
  if (isDelayCtl(id)) {
    const row = DL.find(([r, n]) => id === r || id === n),
      val = Math.max(0, Math.min(3000, +e.target.value || 0));
    $(row[0]).value = val;
    if (id !== row[1]) $(row[1]).value = val;
    $(row[2]).textContent = val;
    pipDelayDirty = true;
    dlWarn();
    return;
  }
  pipeDirty = true;
  $("pipeerr").textContent = "Nicht gespeichert: Mit „Bildaufbau speichern“ übernehmen.";
});
$("pipecard").addEventListener("change", async (e) => {
  dlWarn();
  if (isDelayCtl(e.target.id || "")) {
    const row = DL.find(([r, n]) => e.target.id === r || e.target.id === n);
    const liveOk = row[3] === "main_delay_ms" ? pipLive.main : pipLive.pips;
    if (!pipeDirty && liveOk) {
      await pipSave();
    } else {
      pipeDirty = true;
      $("pipeerr").textContent = pipLive.main
        ? "Nicht gespeichert: Mit „Bildaufbau speichern“ übernehmen (Sendekette startet kurz neu)."
        : "Nicht gespeichert: Mit „Bildaufbau speichern“ übernehmen.";
    }
    return;
  }
  pipeDirty = true;
  if (e.target.id === "p_main") {
    const v = {
      main: $("p_main").value,
      pip: $("p_pip").value,
      pip2: $("p_pip2").value,
      pip3: $("p_pip3").value,
      c1: $("p_corner").value,
      c2: $("p_corner2").value,
      c3: $("p_corner3").value,
    };
    ["pip", "pip2", "pip3"].forEach((k) => {
      if (v[k] === v.main && pipPrevMain && pipPrevMain !== v.main) v[k] = pipPrevMain;
    });
    pipConstrain(v);
    return;
  }
  pipConstrain();
});
async function pipSave() {
  $("pipeerr").textContent = "";
  const body = {
    type: $("p_type").value,
    main: $("p_main").value,
    pip: $("p_pip").value,
    corner: +$("p_corner").value,
    pip2: $("p_pip2").value,
    corner2: +$("p_corner2").value,
    pip3: $("p_pip3").value,
    corner3: +$("p_corner3").value,
    x: posFree[1].x,
    y: posFree[1].y,
    x2: posFree[2].x,
    y2: posFree[2].y,
    x3: posFree[3].x,
    y3: posFree[3].y,
    size_pct: +$("p_size1").value,
    size_pct2: +$("p_size2").value,
    size_pct3: +$("p_size3").value,
    audio: $("p_audio").value,
    auto_failover: $("p_auto").checked,
    swap_cams: 4,
    always_ready: true,
    styles: pipStyles,
    ...delayBody(),
  };
  try {
    const r = await srtlaCall("POST", "/api/pipeline", body);
    pipeDirty = false;
    pipDelayDirty = false;
    $("pipeerr").textContent = (r && r.note) || "Gespeichert.";
    if (r && r.restarted) pipWatchRestart(r.note || "Gespeichert.");
  } catch (x) {
    $("pipeerr").textContent = x.message;
  }
  pipeLoad();
}
let pipWatchTok = 0;
