async function jget(url){const r=await fetch(url);if(!r.ok)throw new Error(await r.text());return r.json()}
async function jpost(url,body){const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):"{}"});if(!r.ok)throw new Error(await r.text());return r.json()}
function isoToLocal(iso){if(!iso)return"–";try{return new Date(iso).toLocaleString()}catch{return iso}}
function setText(id,val){document.getElementById(id).innerText=val}
function selectedValues(sel){return Array.from(sel.selectedOptions).map(o=>o.value)}

async function loadEntities(selected){
  const list=await jget("/api/entities");
  const sel=document.getElementById("entities");
  sel.innerHTML="";
  for(const it of list){
    const opt=document.createElement("option");
    opt.value=it.entity_id;
    opt.textContent=`${it.name} (${it.entity_id})`;
    if(selected&&selected.includes(it.entity_id)) opt.selected=true;
    sel.appendChild(opt);
  }
}

async function loadConfig(){
  const cfg=(await jget("/api/config")).config;
  await loadEntities(cfg.entities||[]);
  document.getElementById("start_time").value=cfg.start_time||"18:00";
  document.getElementById("end_time").value=cfg.end_time||"23:30";
  document.getElementById("interval_min").value=cfg.interval_min??5;
  document.getElementById("training_days").value=cfg.training_days??14;
  document.getElementById("slot_minutes").value=cfg.slot_minutes??15;
  document.getElementById("randomness").value=cfg.randomness??0.15;
  document.getElementById("darkness_mode").value=cfg.darkness_mode||"sun";
  document.getElementById("darkness_entity").value=cfg.darkness_entity||"sun.sun";
  document.getElementById("dark_state").value=cfg.dark_state||"below_horizon";
  document.getElementById("lux_threshold").value=cfg.lux_threshold??30;
}

async function saveConfig(){
  const msg=document.getElementById("save-msg");
  msg.textContent="speichere…";
  const cfg={
    entities:selectedValues(document.getElementById("entities")),
    start_time:document.getElementById("start_time").value.trim(),
    end_time:document.getElementById("end_time").value.trim(),
    interval_min:Number(document.getElementById("interval_min").value),
    training_days:Number(document.getElementById("training_days").value),
    slot_minutes:Number(document.getElementById("slot_minutes").value),
    randomness:Number(document.getElementById("randomness").value),
    darkness_mode:document.getElementById("darkness_mode").value,
    darkness_entity:document.getElementById("darkness_entity").value.trim(),
    dark_state:document.getElementById("dark_state").value.trim(),
    lux_threshold:Number(document.getElementById("lux_threshold").value),
  };
  await jpost("/api/config",cfg);
  msg.textContent="gespeichert ✔";
  setTimeout(()=>msg.textContent="",2500);
  await refreshStatus();
}

function renderLastStep(lastStep){
  const el=document.getElementById("st-laststep");
  el.textContent=lastStep?JSON.stringify(lastStep,null,2):"";
}
function renderPreview(preview){
  const el=document.getElementById("preview");
  el.innerHTML="";
  if(!preview||preview.length===0){el.innerHTML="<div class='muted'>Keine Vorschau (prüfe Zeitfenster/Intervall/Entities).</div>";return;}
  for(const item of preview){
    const div=document.createElement("div");
    div.className="preview-item";
    const expected=(item.expected_top_on||[]).map(x=>`${x.entity_id} (p≈${x.p})`).join(", ");
    div.innerHTML=`<div class="t">${isoToLocal(item.time)}</div><div class="e">${expected?("Expected ON: "+expected):"Expected ON: –"}</div>`;
    el.appendChild(div);
  }
}

async function refreshStatus(){
  const st=await jget("/api/status");
  setText("st-running",st.running?"Ja":"Nein");
  setText("st-next",isoToLocal(st.next_run));
  setText("st-last",isoToLocal(st.last_run));
  setText("st-train",isoToLocal(st.last_train));
  renderLastStep(st.last_step);
  renderPreview(st.preview);
}

async function wire(){
  document.getElementById("btn-save").onclick=saveConfig;
  document.getElementById("btn-train").onclick=async()=>{await jpost("/api/train");await refreshStatus();};
  document.getElementById("btn-start").onclick=async()=>{await jpost("/api/start");await refreshStatus();};
  document.getElementById("btn-stop").onclick=async()=>{await jpost("/api/stop");await refreshStatus();};
  document.getElementById("btn-step").onclick=async()=>{await jpost("/api/step");await refreshStatus();};
  await loadConfig();
  await refreshStatus();
  setInterval(refreshStatus,5000);
}
wire().catch(err=>{console.error(err);alert("Fehler: "+err.message);});
