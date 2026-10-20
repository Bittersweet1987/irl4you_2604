// YouTube-Chat: Kanal eintragen (öffentlicher Chat ohne Anmeldung) und optional Anmeldung mit dem YouTube-Konto für die Moderation.
// Die Nachrichten selbst kommen über den normalen Chat (chat.js).
let ytData = null,
  ytTimer = null;
const YT_STATE = {
  "kein-client": "Die Anmeldung mit dem YouTube-Konto ist in dieser Version noch nicht freigeschaltet.",
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
function ytLines(el, lines) {
  el.textContent = "";
  lines.filter(Boolean).forEach((l) => {
    const p = document.createElement("div");
    p.textContent = l;
    el.appendChild(p);
  });
}
function ytRender(d) {
  ytData = d;
  const on = d.state === "angemeldet",
    wait = d.state === "wartet",
    chat = d.chat || {};
  $("yt_sum").textContent = on ? "· " + (d.channel || "angemeldet") : d.handle ? "· " + d.handle : "· aus";
  if (document.activeElement.id !== "yt_chan") $("yt_chan").value = d.handle || "";
  $("yt_login").hidden = on || wait;
  $("yt_login").disabled = !d.has_client;
  $("yt_logout").hidden = !on;
  $("yt_cancel").hidden = !wait;
  $("yt_code").hidden = !wait;
  if (wait) {
    $("yt_codetxt").textContent = d.code || "";
    const a = $("yt_link");
    a.href = d.uri || "https://www.google.com/device";
    a.textContent = (d.uri || "https://www.google.com/device").replace(/^https:\/\//, "");
  }
  const head = on ? (d.channel ? "Angemeldet als " + d.channel : "Angemeldet") : d.handle ? "Kanal " + d.handle : "Noch kein Kanal eingetragen.";
  const known = on || d.handle;
  const live = known && chat.state && YT_CHAT[chat.state] ? (chat.state === "ok" && chat.title ? "Livechat verbunden: " + chat.title : YT_CHAT[chat.state]) : "";
  ytLines($("yt_status"), [head, live, known ? chat.error : ""]);
  ytLines($("yt_loginmsg"), [on ? "" : YT_STATE[d.state] || "", d.error]);
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
$("yt_chan_save").addEventListener("click", () => ytPost({ action: "channel", channel: $("yt_chan").value }));
$("yt_chan").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("yt_chan_save").click();
  }
});
$("yt_login").addEventListener("click", () => ytPost({ action: "login" }));
$("yt_cancel").addEventListener("click", () => ytPost({ action: "cancel" }));
$("yt_logout").addEventListener("click", () => {
  if (confirm("Von YouTube abmelden?\n\nModerieren geht dann nicht mehr. Der eingetragene Kanal bleibt gespeichert.")) ytPost({ action: "logout" });
});
$("yt_sec").addEventListener("toggle", () => {
  if ($("yt_sec").open) ytLoad();
});
ytLoad();
