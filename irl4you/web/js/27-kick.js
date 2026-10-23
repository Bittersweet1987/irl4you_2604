// Kick-Chat: Kanal eintragen (öffentlicher Chat ohne Anmeldung). Die Nachrichten selbst kommen über den normalen Chat (chat.js).
let kickTimer = null;
const KICK_CHAT = {
  ok: "Livechat verbunden",
  "kein-kanal": "Diesen Kanal gibt es auf Kick nicht.",
  fehler: "Keine Verbindung zu Kick.",
  verbinde: "Verbinde mit Kick …",
};
function kickRender(d) {
  const chat = d.chat || {};
  $("kick_sum").textContent = d.handle ? "· " + d.handle : "· aus";
  if (document.activeElement.id !== "kick_chan") $("kick_chan").value = d.handle || "";
  const live = d.handle && chat.state && KICK_CHAT[chat.state] ? (chat.state === "ok" && chat.title ? "Livechat verbunden: " + chat.title : KICK_CHAT[chat.state]) : "";
  const other = Object.entries(chat.other || {}).map(([k, v]) => k + " " + v).join(", "),
    rx = chat.state === "ok" ? (chat.msgs ? chat.msgs + " Nachrichten empfangen (live " + ((chat.via || {}).ws || 0) + ", Verlauf " + ((chat.via || {}).hist || 0) + "), die letzte vor " + chat.age + " s" : "Noch keine Nachricht empfangen") + (other ? " (nicht angezeigt: " + other + ")" : "") : "";
  ytLines($("kick_status"), [d.handle ? "Kanal " + d.handle : "Noch kein Kanal eingetragen.", live, rx, d.handle ? chat.error : ""]);
  clearTimeout(kickTimer);
  kickTimer = setTimeout(kickLoad, 15000);
}
async function kickLoad() {
  if (!$("kick_sec").open) {
    clearTimeout(kickTimer);
    kickTimer = setTimeout(kickLoad, 15000);
    return;
  }
  try {
    kickRender(await srtlaCall("GET", "/api/kick"));
  } catch (e) {}
}
async function kickPost(body) {
  $("kick_err").textContent = "";
  try {
    kickRender(await srtlaCall("POST", "/api/kick", body));
  } catch (x) {
    $("kick_err").textContent = x.message;
  }
}
$("kick_chan_save").addEventListener("click", () => kickPost({ action: "channel", channel: $("kick_chan").value }));
$("kick_chan").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("kick_chan_save").click();
  }
});
$("kick_sec").addEventListener("toggle", () => {
  if ($("kick_sec").open) kickLoad();
});
kickLoad();
