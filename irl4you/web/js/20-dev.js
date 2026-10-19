$("c_bk").addEventListener("toggle", () => {
  if ($("c_bk").open) bkLoad();
});
bkPwHint();
let devData = null,
  devTimer = null,
  devPwShown = false;
function devPwButton() {
  $("dev_pw").textContent = devPwShown ? "Passwort ausblenden" : "Passwort anzeigen";
}
async function devLoad() {
  let d;
  try {
    d = await srtlaCall("GET", "/api/developer");
  } catch (e) {
    return;
  }
  devData = d;
  const busy = d.state === "working",
    usable = d.helper_installed && !busy;
  $("dev_badge").textContent = !d.available ? "–" : d.active ? "SSH an" : "SSH aus";
  $("dev_badge").className = "badge " + (d.active ? "attn" : "");
  $("dev_state").className = "wstat" + (d.active ? " ok" : "");
  $("dev_text").textContent = !d.available
    ? "Auf dieser Box gibt es keinen SSH-Dienst."
    : (d.active ? "SSH aktiv" : "SSH ist ausgeschaltet") + (d.user ? " · " + `Benutzer: „${d.user}“` : "");
  const t = $("dev_toggle");
  t.textContent = d.active ? "SSH ausschalten" : "SSH einschalten";
  t.className = d.active ? "dangerbtn" : "warnbtn";
  t.disabled = !usable || !d.available;
  $("dev_reset").disabled = !usable || !d.can_reset;
  $("dev_reset").hidden = !d.can_reset;
  $("dev_pw").disabled = !d.helper_installed;
  devPwButton();
  if (!d.helper_installed)
    $("dev_msg").textContent =
      "Der Helfer ist noch nicht installiert. Er kommt mit dem nächsten Software-Update (oder install.sh erneut ausführen).";
  else if (busy) {
    $("dev_msg").textContent = "Läuft …";
    clearTimeout(devTimer);
    devTimer = setTimeout(devLoad, 1500);
  } else $("dev_msg").textContent = d.state === "error" ? d.message || "Fehler" : "";
}
async function encLoad() {
  let d;
  try {
    d = await srtlaCall("GET", "/api/encoder");
  } catch (e) {
    return;
  }
  $("enc_mode").value = d.mode;
  $("enc_mode").querySelector("option[value=software]").disabled = !d.software_available;
}
$("enc_mode").addEventListener("change", async () => {
  const msg = $("enc_msg"),
    sel = $("enc_mode");
  sel.disabled = true;
  try {
    const r = await srtlaCall("POST", "/api/encoder", { mode: sel.value });
    msg.textContent = r.note || "Gespeichert.";
  } catch (x) {
    msg.textContent = x.message;
  }
  sel.disabled = false;
  encLoad();
});
async function devPost(body, wait) {
  $("dev_msg").textContent = wait;
  try {
    await srtlaCall("POST", "/api/developer", body);
  } catch (x) {
    $("dev_msg").textContent = x.message;
    return false;
  }
  clearTimeout(devTimer);
  devTimer = setTimeout(devLoad, 1200);
  [3000, 8000].forEach((ms) => setTimeout(devLoad, ms));
  return true;
}
async function devPwShow() {
  const prev = devData ? devData.time : 0,
    out = $("dev_pw_out");
  out.textContent = "";
  $("dev_msg").textContent = "Prüfe das Passwort …";
  try {
    await srtlaCall("POST", "/api/developer", { action: "check" });
  } catch (x) {
    $("dev_msg").textContent = x.message;
    return;
  }
  for (let i = 0; i < 8; i++) {
    await new Promise((r) => setTimeout(r, 800));
    await devLoad();
    if (devData && devData.state !== "working" && devData.time !== prev) break;
  }
  $("dev_msg").textContent = "";
  try {
    const r = await srtlaCall("GET", "/api/developer/password");
    out.innerHTML =
      '<div class="pwshow" title="Klicken kopiert das Passwort">' +
      esc(r.password) +
      "</div>" +
      (r.state === "own"
        ? '<div class="muted">Achtung: Das Passwort wurde danach von Hand geändert, dieses gilt vermutlich nicht mehr.</div>'
        : "");
    devPwShown = true;
  } catch (x) {
    $("dev_msg").textContent = x.message;
    devPwShown = false;
  }
  devPwButton();
}
function devPwHide() {
  $("dev_pw_out").textContent = "";
  devPwShown = false;
  devPwButton();
}
$("dev_toggle").addEventListener("click", async () => {
  const start = !(devData && devData.active);
  if ((await devPost({ action: start ? "start" : "stop" }, start ? "Schalte SSH ein …" : "Schalte SSH aus …")) && start && devPwShown)
    devPwHide();
});
$("dev_pw").addEventListener("click", () => {
  if (devPwShown) devPwHide();
  else devPwShow();
});
$("dev_reset").addEventListener("click", async () => {
  if (!confirm("SSH-Passwort zurücksetzen?\n\nDas alte Passwort gilt danach nicht mehr.")) return;
  devPwHide();
  const prev = devData ? devData.time : 0;
  if (await devPost({ action: "reset", confirm: true }, "Erzeuge ein neues Passwort …")) {
    for (let i = 0; i < 15; i++) {
      await new Promise((r) => setTimeout(r, 800));
      await devLoad();
      if (devData && devData.state !== "working" && devData.time !== prev) break;
    }
    if (devData && devData.state !== "error") devPwShow();
  }
});
$("c_dev").addEventListener("toggle", () => {
  if ($("c_dev").open) {
    devLoad();
    encLoad();
  } else devPwHide();
});
devLoad();
async function powerDo(action) {
  let st = {};
  try {
    st = await srtlaCall("GET", "/api/power");
  } catch (e) {}
  if (!st.helper_installed) {
    $("pwmsg").textContent = "Der Helfer ist auf dieser Box noch nicht installiert (install.sh erneut ausführen).";
    return;
  }
  const live = st.sending ? "\n\nAchtung: Es wird gerade gesendet. Die Übertragung bricht dabei ab." : "";
  if (
    !confirm(
      (action === "poweroff"
        ? "Die Box jetzt herunterfahren?\n\nDanach ist die Box AUS und startet nicht von selbst wieder. Zum Einschalten den Strom kurz trennen oder die Ein-Taste drücken."
        : "Die Box jetzt neu starten?") + live,
    )
  )
    return;
  try {
    await srtlaCall("POST", "/api/power", { action, confirm: true });
  } catch (x) {
    $("pwmsg").textContent = x.message;
    return;
  }
  $("pwmsg").textContent =
    action === "poweroff"
      ? "Die Box fährt herunter. Sobald die Lüfter stehen, ist sie aus. Diese Seite ist dann nicht mehr erreichbar."
      : "Die Box startet neu. Diese Seite lädt sich nach etwa einer Minute wieder.";
}
$("pw_off").addEventListener("click", () => powerDo("poweroff"));
$("pw_reboot").addEventListener("click", () => powerDo("reboot"));
setSM(smStart);
(async function tickLoop() {
  try {
    if (!document.hidden) await tick();
  } catch (e) {}
  setTimeout(tickLoop, 2000);
})();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    tick();
    sendLoad();
  }
});
