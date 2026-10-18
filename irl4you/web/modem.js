// IRL4YOU BOX: Mobilfunk-Modems (Verbindungen > Mobilfunk) und Passwort der Oberfläche ändern (Optionen).
(function(){
"use strict";
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function call(method,url,body){const r=await fetch(url,{method,headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||"Fehler");return j;}
const STATE={"kein-sim":["crit","Keine SIM-Karte"],"gesperrt":["warn","SIM gesperrt (PIN)"],"fehler":["crit","Fehler"],"aus":["warn","Aus"],
"suche":["warn","Sucht Netz …"],"eingebucht":["warn","Eingebucht, nicht verbunden"],"verbinde":["warn","Verbindet …"],"verbunden":["ok","Verbunden"]};
let data=null,timer=null,open={},draft={};
function modemHtml(m){const st=STATE[m.state]||["warn",m.state],c=m.config||{};
const sig=m.signal==null?"":` · Signal ${m.signal} %`;const op=m.operator?` · ${esc(m.operator)}${m.roaming?" (Roaming)":""}`:"";
const tech=(m.tech||[]).length?` · ${esc(m.tech.join("/"))}`:"";
let h=`<div class="wcard" data-id="${esc(m.id)}"><div class="wstat ${st[0]==="ok"?"ok":(st[0]==="crit"?"bad":"")}"><span class="wdot"></span><span class="wgrow"><b>${esc(m.name)}</b>${m.iface?" · "+esc(m.iface):""}<br>`+
`<span class="muted">${esc(st[1])}${sig}${op}${tech}</span></span><button type="button" class="sec md-edit">${open[m.id]?"Schließen":"Einstellen"}</button></div>`;
if(open[m.id]){const d=draft[m.id]||{autoconfig:c.autoconfig,apn:c.apn||"",username:c.username||"",password:"",roaming:!!c.roaming,network:c.network||"",network_type:c.network_type||""};draft[m.id]=d;
const types=[`<option value="">Automatisch (wie vom Modem gewählt)</option>`].concat((m.network_types||[]).map(t=>`<option value="${esc(t.key)}"${t.key===d.network_type?" selected":""}>${esc(t.label)}</option>`));
const nets=[`<option value="">Automatisch</option>`].concat((m.available_networks||[]).map(n=>`<option value="${esc(n.code)}"${n.code===d.network?" selected":""}${n.forbidden?" disabled":""}>${esc(n.name)} (${esc(n.code)}) ${esc((n.tech||[]).join("/"))}${n.current?" · aktuell":""}${n.forbidden?" · gesperrt":""}</option>`));
if(d.network&&!(m.available_networks||[]).some(n=>n.code===d.network))nets.push(`<option value="${esc(d.network)}" selected>${esc(d.network)}</option>`);
h+=`<label class="muted" style="display:block;margin:10px 0 0"><input type="checkbox" class="md-auto"${d.autoconfig?" checked":""}> APN automatisch (nach SIM-Karte)</label><div class="wform">`+
`<label class="muted">APN<input class="md-apn" maxlength="100" autocomplete="off" value="${esc(d.apn)}"${d.autoconfig?" disabled":""}></label>`+
`<label class="muted">Benutzername<input class="md-user" maxlength="64" autocomplete="off" value="${esc(d.username)}"${d.autoconfig?" disabled":""}></label>`+
`<label class="muted">Passwort<input class="md-pw" type="password" maxlength="64" autocomplete="new-password" placeholder="${c.password_set?"gespeichert – leer lassen, um es zu behalten":"meist leer"}"${d.autoconfig?" disabled":""}></label>`+
`<label class="muted">Netztyp<select class="md-type">${types.join("")}</select></label>`+
`<label class="muted">Netz<select class="md-net">${nets.join("")}</select></label></div>`+
`<label class="muted" style="display:block;margin:8px 0"><input type="checkbox" class="md-roam"${d.roaming?" checked":""}> Roaming erlauben (im Ausland, kann Kosten verursachen)</label>`+
`<div class="actions"><button type="button" class="md-save">Speichern und neu verbinden</button> <button type="button" class="sec md-scan"${m.no_sim?" disabled":""}>Netze suchen</button></div>`+
(m.scan_time?`<div class="ph">Letzte Suche: ${new Date(m.scan_time*1000).toLocaleTimeString()}</div>`:"");}
return h+"</div>";}
function render(){const box=$("modemlist");if(!box||!data)return;
if(box.contains(document.activeElement)&&document.activeElement.tagName!=="BUTTON")return;
box.innerHTML=data.modems.length?data.modems.map(modemHtml).join(""):`<div class="ph">Kein Modem gefunden. Mobilfunk-Sticks und M.2-Module erscheinen hier, sobald ModemManager sie erkennt.</div>`;
const msg=$("modemmsg");if(msg)msg.textContent=!data.helper_installed?"Der Mobilfunk-Helfer ist auf dieser Box noch nicht installiert.":(data.state==="working"?(data.message||"Läuft …"):(data.message||""));}
async function load(){try{data=await call("GET","/api/modems");render();}catch(e){const msg=$("modemmsg");if(msg)msg.textContent=e.message;}
clearTimeout(timer);const sec=$("net_modem");timer=setTimeout(load,data&&data.state==="working"?2000:(sec&&sec.open?5000:20000));}
function readDraft(card){const id=card.dataset.id,d=draft[id]||{};const q=s=>card.querySelector(s);
if(q(".md-auto"))d.autoconfig=q(".md-auto").checked;if(q(".md-apn"))d.apn=q(".md-apn").value.trim();if(q(".md-user"))d.username=q(".md-user").value.trim();
if(q(".md-pw"))d.password=q(".md-pw").value;if(q(".md-roam"))d.roaming=q(".md-roam").checked;if(q(".md-net"))d.network=q(".md-net").value;if(q(".md-type"))d.network_type=q(".md-type").value;
draft[id]=d;return d;}
document.addEventListener("change",e=>{const card=e.target.closest&&e.target.closest("#modemlist .wcard");if(!card)return;readDraft(card);if(e.target.classList.contains("md-auto")){document.activeElement.blur();render();}});
document.addEventListener("click",async e=>{const b=e.target.closest&&e.target.closest("#modemlist button");if(!b)return;const card=b.closest(".wcard"),id=card.dataset.id;const msg=$("modemmsg");
if(b.classList.contains("md-edit")){open[id]=!open[id];if(!open[id])delete draft[id];b.blur();render();return;}
try{if(b.classList.contains("md-save")){const d=readDraft(card);const body={action:"config",id,autoconfig:d.autoconfig,roaming:d.roaming,network:d.network,network_type:d.network_type};
if(!d.autoconfig){body.apn=d.apn;body.username=d.username;if(d.password)body.password=d.password;}
msg.textContent="Wird gespeichert …";await call("POST","/api/modems",body);open[id]=false;delete draft[id];}
else if(b.classList.contains("md-scan")){msg.textContent="Suche läuft, das kann einige Minuten dauern …";await call("POST","/api/modems",{action:"scan",id});}}
catch(x){msg.textContent=x.message;return;}b.blur();setTimeout(load,1200);});
function pwInit(){const f=$("uipw_form");if(!f)return;f.addEventListener("submit",async e=>{e.preventDefault();const m=$("uipw_msg");
const o=$("uipw_old").value,n=$("uipw_new").value,n2=$("uipw_new2").value;if(n!==n2){m.textContent="Die beiden neuen Passwörter sind verschieden";return;}
try{await call("POST","/api/password",{old:o,new:n,remember:true});m.textContent="Passwort geändert. Andere Geräte müssen sich neu anmelden.";f.reset();}catch(x){m.textContent=x.message;}});
call("GET","/api/auth").then(a=>{if(a.mode!=="own"){$("uipw_form").hidden=true;$("uipw_msg").textContent=a.mode==="demo"?"In der Vorschau nicht möglich.":"Das Passwort lässt sich hier nicht ändern.";}}).catch(()=>{});}
function init(){pwInit();const sec=$("net_modem");if(sec)sec.addEventListener("toggle",()=>{if(sec.open)load();});load();}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
