(function () {
  const DES = [
    { id: "", name: "Standard", text: "Das bisherige Aussehen der Oberfläche.", sw: ["#0f172a", "#1e293b", "#06b6d4"] },
    {
      id: "klar",
      name: "Klar",
      text: "Hell, ruhig und großzügig: große Schrift, weiche Karten, viel Platz zum Antippen.",
      sw: ["#f4f6fb", "#ffffff", "#2457d6"],
    },
    {
      id: "kompakt",
      name: "Kompakt",
      text: "Dicht und nüchtern: viele Werte auf einen Blick, wenig Abstand, besonders am Rechner praktisch.",
      sw: ["#0b0f14", "#121821", "#37c8e0"],
    },
    {
      id: "kompakt-std",
      name: "Kompakt Standard",
      text: "Wie Kompakt (dicht, wenig Abstand), aber in den Farben des Standard-Designs.",
      sw: ["#0f172a", "#1e293b", "#06b6d4"],
    },
    {
      id: "kontrast",
      name: "Kontrast Plus",
      text: "Höchster Kontrast (Schwarz, Weiß, Gelb), große Schrift, dicke Rahmen und große Knöpfe. Für schlechtes Sehen und helles Sonnenlicht.",
      sw: ["#000000", "#ffffff", "#ffe600"],
    },
    {
      id: "cockpit",
      name: "Cockpit",
      text: "Dunkles Instrumentenbrett: Zahlen in Schreibmaschinenschrift, große Werte, Karten als Kacheln im Raster.",
      sw: ["#05080b", "#0b1218", "#00e5ff"],
    },
    {
      id: "mischpult",
      name: "Mischpult",
      text: "Hardware-Optik: Karten als Geräteblenden mit Schrauben, Tasten, leuchtende LED-Punkte für Zustände und Balken wie Pegelketten.",
      sw: ["#16181b", "#25282d", "#f2a900"],
    },
  ];
  const cur = () => (window.pbViews ? window.pbViews.design() : "");
  function pick(id) {
    window.pbViews.setDesign(id);
    let stored = "";
    try {
      stored = localStorage.getItem("pb_theme") || "";
    } catch (e) {}
    if (stored !== "light" && stored !== "dark") setTheme(id === "klar" ? "light" : "dark", false);
  }
  const box = $("design_list");
  DES.forEach((d) => {
    const l = document.createElement("label");
    l.className = "dchoice";
    const i = document.createElement("input");
    i.type = "radio";
    i.name = "design";
    i.value = d.id;
    i.checked = d.id === cur();
    l.appendChild(i);
    const sw = document.createElement("span");
    sw.className = "dsw";
    sw.setAttribute("aria-hidden", "true");
    d.sw.forEach((c) => {
      const e = document.createElement("i");
      e.style.background = c;
      sw.appendChild(e);
    });
    l.appendChild(sw);
    const t = document.createElement("span");
    t.className = "dtx";
    const b = document.createElement("b");
    b.textContent = d.name;
    const x = document.createElement("span");
    x.textContent = d.text;
    t.appendChild(b);
    t.appendChild(x);
    l.appendChild(t);
    box.appendChild(l);
  });
  document.addEventListener("pb-design-changed", () =>
    box.querySelectorAll("input[name=design]").forEach((i) => {
      i.checked = i.value === cur();
    }),
  );
  box.addEventListener("change", (e) => {
    const i = e.target.closest("input[name=design]");
    if (i && i.checked) pick(i.value);
  });
})();
const HLP_SEL = ".card .ph:not([id]):not([role])";
function hlpOwner(ph) {
  const isHead = (e) => !!e && (e.tagName === "SUMMARY" || (e.classList && e.classList.contains("sech")));
  if (ph.hasAttribute("data-hlp")) {
    for (let e = ph; e && !(e.classList && e.classList.contains("card")); e = e.parentElement)
      for (let p = e.previousElementSibling; p; p = p.previousElementSibling) if (isHead(p)) return p;
    return null;
  }
  let prev = ph.previousElementSibling;
  if (!prev && ph.parentElement && ph.parentElement.tagName === "DIV") prev = ph.parentElement.previousElementSibling;
  return isHead(prev) ? prev : null;
}
(function () {
  document.querySelectorAll(HLP_SEL).forEach((ph) => {
    const head = hlpOwner(ph);
    if (!head) return;
    let b = head.querySelector(":scope>.ibtn,:scope>.sumh>.ibtn");
    if (!b) {
      b = document.createElement("button");
      b.type = "button";
      b.className = "ibtn";
      b.textContent = "i";
      b.setAttribute("aria-expanded", "false");
      b.setAttribute("aria-label", "Hilfe anzeigen");
      b.title = "Hilfe";
      b._hlp = [];
      (head.querySelector(":scope>.sumh") || head).appendChild(b);
    }
    b._hlp.push(ph);
    ph.classList.add("hlp");
  });
  document.addEventListener(
    "click",
    (e) => {
      const b = e.target.closest && e.target.closest(".ibtn");
      if (!b) return;
      e.preventDefault();
      e.stopPropagation();
      const open = b.getAttribute("aria-expanded") !== "true";
      b.setAttribute("aria-expanded", String(open));
      b.setAttribute("aria-label", open ? "Hilfe ausblenden" : "Hilfe anzeigen");
      (b._hlp || []).forEach((p) => p.classList.toggle("open", open));
    },
    true,
  );
})();
let bkDoc = null,
  bkInfo = null,
  bkSending = false,
  bkPw = "";
const BK_MIN = 8;
function bkPwHint() {
  const on = $("bk_secrets").checked;
  $("bk_pwlab").textContent = on ? `Passwort zum Verschlüsseln (mind. ${BK_MIN} Zeichen)` : "Passwort (leer = unverschlüsselt)";
}
$("bk_secrets").addEventListener("change", bkPwHint);
async function bkExport() {
  const sec = $("bk_secrets").checked,
    pw = $("bk_pw").value,
    pw2 = $("bk_pw2").value,
    msg = $("bk_msg"),
    btn = $("bk_export");
  if (pw !== pw2) {
    msg.textContent = "Die beiden Passwörter sind nicht gleich.";
    return;
  }
  if ((sec || pw) && pw.length < BK_MIN) {
    msg.textContent = sec
      ? `Mit Passwörtern bitte ein Passwort eingeben (mind. ${BK_MIN} Zeichen).`
      : `Mindestens ${BK_MIN} Zeichen (oder leer lassen).`;
    return;
  }
  btn.disabled = true;
  msg.textContent = "Wird gesammelt und verschlüsselt …";
  try {
    const r = await srtlaCall("POST", "/api/settings/export", { secrets: sec, password: pw || undefined });
    const blob = new Blob([JSON.stringify(r.document, null, 1)], { type: "application/json" }),
      now = new Date();
    const name =
      "irl4you-einstellungen-" +
      now.getFullYear() +
      pad2(now.getMonth() + 1) +
      pad2(now.getDate()) +
      "-" +
      pad2(now.getHours()) +
      pad2(now.getMinutes()) +
      ".json";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 20000);
    $("bk_pw").value = "";
    $("bk_pw2").value = "";
    msg.textContent =
      "Heruntergeladen: " +
      name +
      " (" +
      Math.max(1, Math.round(blob.size / 1024)) +
      " KB). " +
      (r.encrypted ? "Verschlüsselt. Das Passwort wird nirgends gespeichert." : "Unverschlüsselt, ohne Passwörter.") +
      ((r.notes || []).length ? " Hinweis: " + r.notes.join("; ") : "");
  } catch (x) {
    msg.textContent = "Fehler: " + x.message;
  }
  btn.disabled = false;
}
$("bk_export").addEventListener("click", bkExport);
function bkReset() {
  bkDoc = null;
  bkInfo = null;
  bkPw = "";
  $("bk_plan").hidden = true;
  setHtml($("bk_plan"), "");
  $("bk_ipwrow").hidden = true;
  $("bk_ipw").value = "";
}
$("bk_file").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  bkReset();
  $("bk_imsg").textContent = "";
  $("bk_reload").hidden = true;
  if (!f) return;
  if (f.size > 300000) {
    $("bk_imsg").textContent = "Datei zu groß.";
    return;
  }
  try {
    bkDoc = JSON.parse(await f.text());
  } catch (x) {
    bkDoc = null;
    $("bk_imsg").textContent = "Keine Sicherung (kein JSON).";
    return;
  }
  if (bkDoc && bkDoc.encrypted === true) {
    $("bk_ipwrow").hidden = false;
    $("bk_imsg").textContent = "Verschlüsselt: bitte Passwort eingeben.";
    $("bk_ipw").focus();
    return;
  }
  bkPreview();
});
async function bkPreview() {
  const pw = $("bk_ipw").value;
  $("bk_imsg").textContent = "Wird geprüft …";
  try {
    bkInfo = await srtlaCall("POST", "/api/settings/preview", { document: bkDoc, password: pw || undefined });
  } catch (x) {
    $("bk_imsg").textContent = x.message;
    return;
  }
  bkPw = pw;
  $("bk_ipwrow").hidden = true;
  $("bk_ipw").value = "";
  $("bk_imsg").textContent = "";
  const r = bkInfo,
    when = r.created ? new Date(r.created) : null,
    ts = when && !isNaN(when) ? when.toLocaleString(LOC(), { dateStyle: "medium", timeStyle: "short" }) : "";
  const rows = r.sections
    .map((x) =>
      x.ok
        ? `<label class="logopt"><input type="checkbox" data-sec="${esc(x.id)}" checked> <b>${esc(x.label)}</b> <span class="muted">(${x.count})</span>${x.note ? `<span class="ph">${esc(x.note)}</span>` : ""}</label>`
        : `<div class="logopt bkbad"><b>${esc(x.label)}</b>: nicht lesbar, wird ausgelassen. <span class="ph">${esc(x.note)}</span></div>`,
    )
    .join("");
  setHtml(
    $("bk_plan"),
    `<div class="wstat ok"><span class="wdot"></span><span class="wgrow"><span>${ts ? `Sicherung vom ${esc(ts)}` : "Sicherung"}</span>${r.box_version ? `<span>${`(Version ${esc(r.box_version)})`}</span>` : ""}, <span>${r.encrypted ? "verschlüsselt" : "nicht verschlüsselt"}</span>, <span>${r.secrets ? "mit Passwörtern" : "ohne Passwörter"}</span></span></div>
    <div class="sech">Einspielen (ersetzt die jetzigen Einstellungen)</div>${rows}
    <div class="actions"><button id="bk_go" type="button" class="warnbtn"${bkSending ? " disabled" : ""}>Ausgewählte Teile einspielen</button></div>`,
  );
  $("bk_plan").hidden = false;
  if (bkSending) $("bk_imsg").textContent = "Es wird gesendet. Bitte erst beenden.";
}
$("bk_open").addEventListener("click", bkPreview);
$("bk_ipw").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    bkPreview();
  }
});
const BK_TODO = "pb_bk_todo";
function bkTodoState() {
  try {
    const v = JSON.parse(localStorage.getItem(BK_TODO) || "null");
    return v && typeof v === "object" ? v : null;
  } catch (e) {
    return null;
  }
}
function bkTodoSave(v) {
  try {
    if (v) localStorage.setItem(BK_TODO, JSON.stringify(v));
    else localStorage.removeItem(BK_TODO);
  } catch (e) {}
}
function bkTodoRender() {
  const box = $("bk_todo"),
    st = bkTodoState();
  if (!box) return;
  box.hidden = !st;
  if (st)
    box.querySelectorAll("input[data-todo]").forEach((i) => {
      i.checked = !!(st.done || {})[i.dataset.todo];
    });
}
function bkTodoShow() {
  if (!bkTodoState()) bkTodoSave({ done: {} });
  bkTodoRender();
}
$("bk_todo").addEventListener("change", (e) => {
  const i = e.target.closest("input[data-todo]");
  if (!i) return;
  const st = bkTodoState() || { done: {} };
  st.done = st.done || {};
  st.done[i.dataset.todo] = i.checked;
  const all = [...$("bk_todo").querySelectorAll("input[data-todo]")].every((x) => st.done[x.dataset.todo]);
  bkTodoSave(all ? null : st);
  if (all) setTimeout(bkTodoRender, 600);
  else bkTodoRender();
});
bkTodoRender();
function bkResults(r) {
  bkTodoShow();
  setHtml(
    $("bk_imsg"),
    (r.results || [])
      .map((x) => `<div class="${x.ok ? "bkok" : "bkbad"}">${x.ok ? "✓" : "✗"} <b>${esc(x.label)}</b>: ${esc(x.message)}</div>`)
      .join(""),
  );
  $("bk_reload").hidden = false;
  [
    typeof srtlaLoad === "function" && srtlaLoad,
    typeof pipeLoad === "function" && pipeLoad,
    typeof wifiLoad === "function" && wifiLoad,
    typeof djiLoad === "function" && djiLoad,
  ].forEach((f) => {
    try {
      f && f();
    } catch (e) {}
  });
}
async function bkWithProgress(fn) {
  const t0 = Date.now();
  progSet("bk_prog", true, 3, "Der Stand davor wird gesichert", t0);
  const poll = setInterval(async () => {
    try {
      const p = await srtlaCall("GET", "/api/settings/progress");
      if (p.state === "running" && p.total)
        progSet(
          "bk_prog",
          true,
          Math.max(5, Math.round((p.done * 100) / p.total)),
          p.label ? `Einspielen: ${p.label} (${p.done + 1} von ${p.total})` : "Der Stand davor wird gesichert",
        );
    } catch (e) {}
  }, 600);
  try {
    return await fn();
  } finally {
    clearInterval(poll);
    progSet("bk_prog", true, 100, "Fertig");
    setTimeout(() => progSet("bk_prog", false), 2500);
  }
}
document.addEventListener("click", async (e) => {
  if (e.target.id === "bk_go") {
    const secs = [...document.querySelectorAll("#bk_plan input[data-sec]:checked")].map((i) => i.dataset.sec);
    if (!secs.length) {
      $("bk_imsg").textContent = "Bitte mindestens einen Teil wählen.";
      return;
    }
    if (!confirm("Die gewählten Teile ersetzen die jetzigen Einstellungen. Der Stand davor wird gesichert.\n\nEinspielen?")) return;
    e.target.disabled = true;
    $("bk_imsg").textContent = "Wird eingespielt …";
    try {
      const r = await bkWithProgress(() =>
        srtlaCall("POST", "/api/settings/import", { document: bkDoc, password: bkPw || undefined, sections: secs }),
      );
      bkResults(r);
      bkReset();
      $("bk_file").value = "";
    } catch (x) {
      $("bk_imsg").textContent = "Fehler: " + x.message;
      e.target.disabled = false;
    }
    bkLoad();
  }
});
$("bk_restore").addEventListener("click", async () => {
  if (!confirm("Stand vor dem letzten Einspielen zurückholen? Die jetzigen Einstellungen werden ersetzt.")) return;
  $("bk_imsg").textContent = "Wird zurückgeholt …";
  try {
    bkResults(await bkWithProgress(() => srtlaCall("POST", "/api/settings/restore", {})));
  } catch (x) {
    $("bk_imsg").textContent = "Fehler: " + x.message;
  }
  bkLoad();
});
$("bk_reload").addEventListener("click", () => location.reload());
async function bkLoad() {
  try {
    const d = await srtlaCall("GET", "/api/settings");
    bkSending = !!d.sending;
    $("bk_restore").hidden = !d.has_backup;
    const go = $("bk_go");
    if (go) go.disabled = bkSending;
  } catch (e) {}
}
