$("mf_info").addEventListener("click", () => {
  const m = $("mf_msg");
  if (!m.hidden && m.dataset.info === "1") {
    footMsg("");
    return;
  }
  const lines =
    $("mf_tools").dataset.cams === "1"
      ? [
          "Kurzer Klick = zum Hauptbild machen",
          "Doppelklick = aus-/einblenden, Ton bleibt",
          "Langer Klick = deaktivieren / aktivieren",
          "Ton: kurzer Klick = nächste Spur",
          "Ton: langer Klick = stumm / wieder laut",
        ]
      : ["Ton: langer Klick = stumm / wieder laut"];
  footMsg(lines.join("\n"), 15000);
  m.dataset.info = "1";
  fitMsg(m);
});
function fitMsg(m) {
  m.style.fontSize = "";
  let fs = parseFloat(getComputedStyle(m).fontSize) || 14;
  while (m.scrollWidth > m.clientWidth + 1 && fs > 9) {
    fs -= 0.5;
    m.style.fontSize = fs + "px";
  }
}
(function () {
  const root = document.documentElement,
    LK = "pb_foot_layout",
    IK = "pb_foot_info",
    LAY = ["one", "two", "left", "right"];
  let lay = "one",
    info = true;
  try {
    const v = localStorage.getItem(LK);
    if (LAY.includes(v)) lay = v;
    info = localStorage.getItem(IK) !== "0";
  } catch (e) {}
  function apply() {
    root.classList.toggle("mf2", lay === "two");
    root.classList.toggle("mfleft", lay === "left");
    root.classList.toggle("mfright", lay === "right");
    root.classList.toggle("nofootinfo", !info);
    if (typeof sizeFoot === "function") sizeFoot();
  }
  window.pbFootLayout = (v) => {
    lay = LAY.includes(v) ? v : "one";
    try {
      if (lay === "one") localStorage.removeItem(LK);
      else localStorage.setItem(LK, lay);
    } catch (e) {}
    apply();
  };
  window.pbFootLayoutGet = () => lay;
  window.pbFootInfo = (b) => {
    info = !!b;
    try {
      if (info) localStorage.removeItem(IK);
      else localStorage.setItem(IK, "0");
    } catch (e) {}
    apply();
  };
  window.pbFootInfoGet = () => info;
  apply();
})();
(function () {
  const f = $("mfoot"),
    root = document.documentElement,
    KEY = "pb_foot";
  let y = Math.max(0, window.scrollY),
    run = 0,
    scrollHid = false,
    mode = "auto";
  try {
    const v = localStorage.getItem(KEY);
    if (v === "always" || v === "hide" || v === "off") mode = v;
  } catch (e) {}
  const shown = () =>
    ["c_chat", "c_prev", "c_deck"].some((id) => {
      const e = $(id);
      return !!e && e.open && e.offsetParent !== null;
    });
  const apply = () => {
    const wide = shown(),
      h = mode === "off" || (mode !== "always" && wide && (mode === "hide" || scrollHid));
    root.classList.toggle("mfhide", h);
    root.classList.toggle("mfperm", mode === "off" || (mode === "hide" && wide));
  };
  window.pbFootMode = (m) => {
    mode = m === "always" || m === "hide" || m === "off" ? m : "auto";
    try {
      localStorage.setItem(KEY, mode);
    } catch (e) {}
    scrollHid = false;
    apply();
  };
  window.pbFootGet = () => mode;
  window.addEventListener(
    "scroll",
    () => {
      if (getComputedStyle(f).display === "none") {
        run = 0;
        scrollHid = false;
        apply();
        return;
      }
      const ny = Math.max(0, window.scrollY),
        d = ny - y;
      y = ny;
      run = d > 0 === run > 0 ? run + d : d;
      const bottom = window.innerHeight + ny >= document.documentElement.scrollHeight - 8;
      if (ny < 24 || bottom || run < -8) scrollHid = false;
      else if (run > 8) scrollHid = true;
      apply();
    },
    { passive: true },
  );
  f.addEventListener("focusin", () => {
    scrollHid = false;
    apply();
  });
  ["c_chat", "c_prev", "c_deck"].forEach((id) => {
    const e = $(id);
    if (e) e.addEventListener("toggle", apply);
  });
  window.addEventListener("resize", apply);
  document.addEventListener("pb-menus-changed", apply);
  new MutationObserver(apply).observe(document.querySelector("main"), {
    attributes: true,
    subtree: true,
    attributeFilter: ["data-pbhide"],
  });
  apply();
})();
function sizeFoot() {
  const h = $("mfoot").offsetHeight;
  if (h) document.documentElement.style.setProperty("--mfh", h + "px");
  else document.documentElement.style.removeProperty("--mfh");
}
window.addEventListener("resize", sizeFoot);
if (window.ResizeObserver) new ResizeObserver(sizeFoot).observe($("mfoot"));
function renderFoot(d) {
  if (footBusy) return;
  const f = d.footer,
    box = $("mf_tools");
  if (!f || !f.cams || !f.cams.length) {
    box.hidden = true;
    $("mf_info").hidden = true;
    setHtml(box, "");
    sizeFoot();
    return;
  }
  const L = camLabels(f.cams),
    multi = f.cams.length >= 2;
  const cams = !multi
    ? ""
    : f.cams
        .map((c) => {
          const full = c.name || c.key;
          const tip = (
            c.main
              ? [
                  `${full} ist das Hauptbild (lässt sich nicht ausblenden oder deaktivieren).`,
                  "Kurz auf eine andere Kamera drücken macht diese zum Hauptbild.",
                ]
              : [
                  c.inactive
                    ? `${full} ist deaktiviert.`
                    : c.hidden
                      ? `${full} ist ausgeblendet.`
                      : `${full} ist als kleines Bild zu sehen.`,
                  c.inactive
                    ? "Kurz drücken aktiviert die Kamera, das Bild bleibt ausgeblendet (Ton nutzbar)."
                    : "Kurz drücken macht es zum Hauptbild.",
                  c.inactive
                    ? "Doppelt tippen: aktivieren, das Bild bleibt ausgeblendet."
                    : c.hidden
                      ? "Doppelt tippen: das kleine Bild einblenden."
                      : "Doppelt tippen: das kleine Bild ausblenden (Ton noch da).",
                  c.inactive ? "Lang drücken: aktivieren." : "Lang drücken: deaktivieren (nicht im Stream, Ton nicht nutzbar).",
                ]
          ).join(" ");
          return `<button type="button" class="mf-t mf-cam${c.main ? " ismain" : ""}${c.hidden ? " hid" : ""}${c.inactive ? " off" : ""}${c.state === "live" ? " live" : ""}" data-kind="cam" data-key="${esc(c.key)}" data-label="${esc(L[c.key])}" data-slot="${c.slot}" data-main="${c.main ? 1 : 0}" data-hidden="${c.hidden ? 1 : 0}" data-inactive="${c.inactive ? 1 : 0}" data-gone="${c.state === "offline" ? 1 : 0}" title="${esc(tip)}" aria-label="${esc(tip)}">${c.main ? FIC.cam : c.hidden ? FIC.pipoff : FIC.pip}<span>${esc(L[c.key])}</span></button>`;
        })
        .join("");
  const a = f.audio || {},
    an = a.name || a.key || "",
    one = !multi || (a.next || "") === (a.src || "");
  const atip =
    (a.mute ? `Ton von ${an} (stumm).` : `Ton von ${an}.`) +
    " " +
    (one
      ? a.mute
        ? "Lang drücken schaltet wieder laut."
        : "Lang drücken schaltet stumm."
      : a.mute
        ? "Kurz drücken wechselt die Tonspur, lang drücken schaltet wieder laut."
        : "Kurz drücken wechselt die Tonspur, lang drücken schaltet stumm.");
  const aud = `<button type="button" class="mf-t mf-aud${a.mute ? " muted" : ""}" data-kind="aud" data-single="${one ? 1 : 0}" data-mute="${a.mute ? 1 : 0}" data-next="${esc(a.next || "main")}" title="${esc(atip)}" aria-label="${esc(atip)}">${a.mute ? FIC.micoff : FIC.spk}<span>Ton: ${esc(L[a.key] || an)}</span></button>`;
  box.hidden = false;
  box.dataset.cams = multi ? "1" : "0";
  $("mf_info").hidden = false;
  setHtml(box, cams + aud);
  sizeFoot();
}
async function footAct(b, long, dbl) {
  const d = sendData || {},
    f = d.footer || { cams: [] },
    mainKey = (f.cams.find((c) => c.main) || {}).key;
  try {
    let r;
    if (b.dataset.kind === "cam") {
      const isMain = b.dataset.main === "1",
        on = b.dataset.inactive === "1";
      if (long) {
        if (isMain) return footMsg("Das Hauptbild lässt sich nicht deaktivieren.");
        r = await srtlaCall("POST", "/api/pipeline/active", { key: b.dataset.key, active: on });
        return footMsg(on ? "Aktiviert." : "Deaktiviert: nicht mehr im Stream, Ton nicht nutzbar.");
      }
      if (isMain)
        return footMsg(
          dbl
            ? "Das Hauptbild lässt sich nicht ausblenden. Zum Tauschen kurz auf eine andere Kamera drücken."
            : "Das ist schon das Hauptbild.",
        );
      if (!dbl && !on && b.dataset.gone === "1")
        return footMsg("Diese Kamera ist nicht verbunden und lässt sich nicht zum Hauptbild machen.");
      if (on) {
        await srtlaCall("POST", "/api/pipeline/active", { key: b.dataset.key, active: true });
        r = await srtlaCall("POST", "/api/pipeline/view", { visible: { [b.dataset.slot]: false } });
        return footMsg("Aktiviert, Bild ausgeblendet: Ton nutzbar.");
      }
      if (dbl) r = await srtlaCall("POST", "/api/pipeline/view", { visible: { [b.dataset.slot]: b.dataset.hidden === "1" } });
      else r = await srtlaCall("POST", "/api/pipeline/swap", { with: b.dataset.key });
    } else if (long) {
      if (!d.active) return footMsg("Stumm schalten geht nur während der Sendung.");
      r = await srtlaCall("POST", "/api/pipeline/view", { mute: b.dataset.mute !== "1" });
    } else {
      if (b.dataset.single === "1") return footMsg("Es gibt nur eine Tonquelle. Lang drücken schaltet stumm oder wieder laut.");
      r = await srtlaCall("POST", "/api/pipeline/view", { audio: b.dataset.next });
    }
    footMsg((r && r.note) || "");
  } catch (x) {
    footMsg(x.message);
  } finally {
    footBusy = false;
    sendLoad();
  }
}
(function () {
  const box = $("mf_tools");
  let timer = null,
    fired = false,
    x0 = 0,
    y0 = 0;
  const stop = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };
  box.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".mf-t");
    if (!b || (e.pointerType === "mouse" && e.button !== 0)) return;
    footBusy = true;
    fired = false;
    x0 = e.clientX;
    y0 = e.clientY;
    stop();
    timer = setTimeout(() => {
      timer = null;
      fired = true;
      try {
        if (navigator.vibrate) navigator.vibrate(25);
      } catch (x) {}
      footAct(b, true);
    }, 550);
  });
  box.addEventListener("pointermove", (e) => {
    if (timer && Math.hypot(e.clientX - x0, e.clientY - y0) > 12) {
      stop();
      footBusy = false;
    }
  });
  ["pointerup", "pointercancel"].forEach((n) =>
    box.addEventListener(n, () => {
      stop();
      if (!fired)
        setTimeout(() => {
          footBusy = false;
        }, 400);
    }),
  );
  let tapT = null,
    tapKey = "";
  box.addEventListener("click", (e) => {
    const b = e.target.closest(".mf-t");
    if (!b) return;
    if (fired) {
      fired = false;
      e.preventDefault();
      return;
    }
    if (b.dataset.kind !== "cam") {
      footAct(b, false);
      return;
    }
    if (tapT && tapKey === b.dataset.key) {
      clearTimeout(tapT);
      tapT = null;
      footAct(b, false, true);
      return;
    }
    clearTimeout(tapT);
    tapKey = b.dataset.key;
    footBusy = true;
    tapT = setTimeout(() => {
      tapT = null;
      footAct(b, false);
    }, 300);
  });
  box.addEventListener("contextmenu", (e) => e.preventDefault());
})();
sendLoad();
setInterval(() => {
  if (!document.hidden) sendLoad();
}, 2000);
let rBusy = false,
  rDeclinedMem = false;
const R_STATE = { Running: "verbunden", NeedsLogin: "Anmeldung nötig", Stopped: "getrennt", NoState: "startet …", Starting: "startet …" };
