// YouTube-Chat: Zugangsdaten, Anmeldung mit dem YouTube-Konto (Geräte-Ablauf), Status des Livechats. Die Nachrichten selbst kommen über den normalen Chat (chat.js).
let ytData = null,
  ytTimer = null,
  ytOwnShown = false;
const YT_STATE = {
  "kein-client": "Für die Anmeldung fehlt noch die Client-ID. Sie wird unter „Eigene Zugangsdaten (erweitert)“ eingetragen.",
  bereit: "Nicht angemeldet.",
  wartet: "Warte auf die Bestätigung bei Google …",
  fehler: "Anmeldung fehlgeschlagen.",
};
const YT_CHAT = {
  ok: "Livechat verbunden",
  "kein-stream": "Kein laufender YouTube-Stream gefunden. Die Box sucht jede Minute, solange der Chat geöffnet ist.",
  kontingent: "Das Tageskontingent der YouTube-Schnittstelle ist aufgebraucht.",
  fehler: "Keine Verbindung zu YouTube.",
  verbinde: "Verbinde mit YouTube …",
};
function ytRender(d) {
  ytData = d;
  const on = d.state === "angemeldet",
    wait = d.state === "wartet";
  $("yt_sum").textContent = on ? "· " + (d.channel || "angemeldet") : "· aus";
  if (document.activeElement.id !== "yt_cid") $("yt_cid").value = d.client_id || "";
  if (document.activeElement.id !== "yt_secret") $("yt_secret").placeholder = d.secret_set ? "gespeichert" : "";
  $("yt_login").hidden = on || wait;
  $("yt_login").disabled = !d.has_client && !($("yt_cid").value && $("yt_secret").value);
  if (!d.builtin && !d.has_client && !ytOwnShown) {
    $("yt_own").open = true;
    ytOwnShown = true;
  }
  $("yt_logout").hidden = !on;
  $("yt_cancel").hidden = !wait;
  $("yt_code").hidden = !wait;
  if (wait) {
    $("yt_codetxt").textContent = d.code || "";
    const a = $("yt_link");
    a.href = d.uri || "https://www.google.com/device";
    a.textContent = (d.uri || "https://www.google.com/device").replace(/^https:\/\//, "");
  }
  const lines = [on ? (d.channel ? "Angemeldet als " + d.channel : "Angemeldet") : YT_STATE[d.state] || ""];
  if (on && d.chat && YT_CHAT[d.chat.state])
    lines.push(d.chat.state === "ok" && d.chat.title ? "Livechat verbunden: " + d.chat.title : YT_CHAT[d.chat.state]);
  if (d.error) lines.push(d.error);
  const el = $("yt_status");
  el.textContent = "";
  lines.filter(Boolean).forEach((l) => {
    const p = document.createElement("div");
    p.textContent = l;
    el.appendChild(p);
  });
  clearTimeout(ytTimer);
  ytTimer = setTimeout(ytLoad, wait ? 3000 : 15000);
}
async function ytLoad() {
  if (!$("yt_sec").open && !(ytData && ytData.state === "wartet")) {
    clearTimeout(ytTimer);
    ytTimer = setTimeout(ytLoad, 15000);
    return;
  }
  try {
    ytRender(await srtlaCall("GET", "/api/youtube"));
  } catch (e) {}
}
async function ytPost(body) {
  $("yt_err").textContent = "";
  try {
    ytRender(await srtlaCall("POST", "/api/youtube", body));
    return true;
  } catch (x) {
    $("yt_err").textContent = x.message;
    return false;
  }
}
async function ytSaveClient() {
  return ytPost({ action: "client", client_id: $("yt_cid").value, client_secret: $("yt_secret").value });
}
$("yt_save").addEventListener("click", async () => {
  if (await ytSaveClient()) $("yt_secret").value = "";
});
$("yt_login").addEventListener("click", async () => {
  if (($("yt_cid").value !== (ytData && ytData.client_id) || $("yt_secret").value) && !(await ytSaveClient())) return;
  $("yt_secret").value = "";
  await ytPost({ action: "login" });
});
$("yt_cancel").addEventListener("click", () => ytPost({ action: "cancel" }));
$("yt_logout").addEventListener("click", () => {
  if (confirm("Von YouTube abmelden?\n\nDer YouTube-Chat wird dann nicht mehr angezeigt. Die Zugangsdaten bleiben gespeichert.")) ytPost({ action: "logout" });
});
$("yt_sec").addEventListener("toggle", () => {
  if ($("yt_sec").open) ytLoad();
});
ytLoad();
