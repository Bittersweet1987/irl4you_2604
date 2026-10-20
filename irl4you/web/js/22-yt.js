// YouTube-Chat: Kanal eintragen (öffentlicher Chat ohne Anmeldung). Die Nachrichten selbst kommen über den normalen Chat (chat.js).
let ytData = null,
  ytTimer = null;
const YT_CHAT = {
  ok: "Livechat verbunden",
  "kein-stream": "Kein laufender YouTube-Stream gefunden. Die Box sucht jede Minute, solange der Chat geöffnet ist.",
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
  const chat = d.chat || {};
  $("yt_sum").textContent = d.handle ? "· " + d.handle : "· aus";
  if (document.activeElement.id !== "yt_chan") $("yt_chan").value = d.handle || "";
  const live = d.handle && chat.state && YT_CHAT[chat.state] ? (chat.state === "ok" && chat.title ? "Livechat verbunden: " + chat.title : YT_CHAT[chat.state]) : "";
  ytLines($("yt_status"), [d.handle ? "Kanal " + d.handle : "Noch kein Kanal eingetragen.", live, d.handle ? chat.error : ""]);
  clearTimeout(ytTimer);
  ytTimer = setTimeout(ytLoad, 15000);
}
async function ytLoad() {
  if (!$("yt_sec").open) {
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
$("yt_sec").addEventListener("toggle", () => {
  if ($("yt_sec").open) ytLoad();
});
ytLoad();
