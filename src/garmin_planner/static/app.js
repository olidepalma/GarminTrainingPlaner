'use strict';
const $ = id => document.getElementById(id);
const sports = {running:'Carrera', trail:'Trail', cycling:'Ciclismo', swimming:'Natación', strength:'Fuerza', triathlon:'Triatlón', other:'Otros'};
let csrf = '', dashboardData = null, visibleRows = 30, mfaJob = null, generation = 0, viewVersion = 0;
const fmt = (value, digits=1) => value == null ? '—' : Number(value).toLocaleString('es-ES', {maximumFractionDigits:digits});
const day = value => new Date(value + 'T12:00:00').toLocaleDateString('es-ES', {day:'2-digit', month:'short'});
const hours = seconds => seconds == null ? '—' : Math.floor(Math.round(seconds/60)/60)+' h '+Math.round(seconds/60)%60+' min';
function toast(message, error=false) { $('toast').textContent=message; $('toast').classList.toggle('error', error); $('toast').hidden=false; }
async function api(url, body) {
  const response = await fetch(url, {method:body===undefined?'GET':'POST', headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:body===undefined?undefined:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) {
    if (response.status===401 && url!=='/api/session/login') { generation++; await boot(); }
    throw new Error(data.detail || 'No se pudo completar la solicitud.');
  }
  return data;
}
function tab(name) {
  for (const id of ['overview','connections','coach','statistics','calendar','library']) $(id+'-view').hidden=id!==name;
  document.querySelectorAll('[data-tab]').forEach(button=>button.classList.toggle('active', button.dataset.tab===name));
  $('page-title').textContent=name==='overview'?'Vista general':name==='coach'?'Coach y objetivos':name==='statistics'?'Estadísticas Garmin':name==='calendar'?'Calendario':name==='library'?'Biblioteca':'Conexiones';
  $('page-eyebrow').textContent=name==='overview'?'TU ACTIVIDAD, EN CONTEXTO':'TUS DATOS, BAJO TU CONTROL';
  history.replaceState(null, '', '#'+name);
  window.scrollTo(0,0);
}
function cell(row, text) { const td=document.createElement('td'); td.textContent=text; row.append(td); }
function table(id, rows) {
  const target=$(id); target.replaceChildren();
  for (const values of rows) { const row=document.createElement('tr'); values.forEach(value=>cell(row,value)); target.append(row); }
}
function activityRows() {
  const rows=dashboardData.activities;
  table('activities', rows.slice(0,visibleRows).map(a=>[a.name,day(a.day),sports[a.sport]||'Otros',hours(a.duration_seconds),fmt(a.distance_m/1000)+' km',fmt(a.elevation_m,0)+' m',a.average_hr==null?'—':fmt(a.average_hr,0)+' ppm']));
  $('activity-count').textContent=`${Math.min(visibleRows,rows.length)} de ${rows.length} actividades`;
  $('more').hidden=visibleRows>=rows.length;
}
function drawWeeks(weeks) {
  const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 720 220'); svg.setAttribute('role','img'); svg.setAttribute('aria-label','Horas de entrenamiento por semana');
  const title=document.createElementNS(ns,'title'); title.textContent=weeks.map(w=>`${w.week}: ${fmt(w.hours)} horas`).join('. '); svg.append(title);
  const max=Math.max(1,...weeks.map(w=>w.hours)), step=640/Math.max(weeks.length,1);
  weeks.forEach((w,i)=>{
    const rect=document.createElementNS(ns,'rect'), height=w.hours/max*135;
    Object.entries({x:45+i*step+step*.18,y:170-height,width:step*.64,height:Math.max(height,1),rx:4,fill:'#89a565'}).forEach(([k,v])=>rect.setAttribute(k,String(v)));
    const label=document.createElementNS(ns,'text'); label.setAttribute('x',String(45+i*step+step/2)); label.setAttribute('y','197'); label.setAttribute('text-anchor','middle'); label.textContent=day(w.week);
    const total=document.createElementNS(ns,'text'); total.setAttribute('x',String(45+i*step+step/2)); total.setAttribute('y',String(160-height)); total.setAttribute('text-anchor','middle'); total.textContent=fmt(w.hours)+' h';
    svg.append(rect,label,total);
  }); $('week-chart').replaceChildren(svg);
}
async function loadDashboard() {
  const own=++viewVersion;
  const sport=$('sport').value;
  const data=await api(`/api/dashboard?days=${$('days').value}${sport?'&sport='+encodeURIComponent(sport):''}`);
  if (own!==viewVersion) return;
  dashboardData=data; visibleRows=30;
  $('date-range').textContent=`${day(data.from)} — ${day(data.through)} · ${new Date(data.through).getFullYear()}`;
  $('sessions').textContent=fmt(data.totals.sessions,0); $('hours').textContent=fmt(data.totals.hours)+' h';
  $('distance').textContent=fmt(data.totals.distance_km)+' km'; $('elevation').textContent=fmt(data.totals.elevation_m,0)+' m';
  $('empty').hidden=data.activities.length>0;
  drawWeeks(data.weeks); $('sport-chart').replaceChildren();
  for (const s of data.sports) {
    const row=document.createElement('div'); row.className='sport-row'; const name=document.createElement('span'), amount=document.createElement('span'), progress=document.createElement('progress');
    name.textContent=sports[s.sport]||'Otros'; amount.textContent=`${fmt(s.hours)} h · ${s.sessions} sesiones`; progress.max=Math.max(data.totals.hours,1); progress.value=s.hours; progress.setAttribute('aria-label',name.textContent+' '+amount.textContent); row.append(name,amount,progress); $('sport-chart').append(row);
  }
  activityRows();
  table('wellness',data.wellness.map(w=>[day(w.day),fmt(w.steps,0),w.resting_hr==null?'—':fmt(w.resting_hr,0)+' ppm',hours(w.sleep_seconds),fmt(w.sleep_score,0),w.hrv_ms==null?'—':fmt(w.hrv_ms,0)+' ms']));
  $('include-sleep').checked=data.wellness_options.sleep; $('include-hrv').checked=data.wellness_options.hrv;
}
async function loadConnections() {
  const c=await api('/api/connections');
  const connected=c.garmin.status==='connected';
  $('garmin-status').textContent=connected?'Conectada':'Sin conectar'; $('garmin-form').hidden=connected; $('garmin-disconnect').hidden=!connected;
  $('garmin-name').textContent=connected?c.garmin.name:'Actividades y recuperación, directamente desde tu cuenta.';
  $('sync').disabled=!connected;
  $('empty-message').textContent=connected?'No hay actividades en este periodo. Sincroniza o cambia los filtros.':'Conecta Garmin para importar tus entrenamientos. Las estadísticas se calculan en tu equipo.';
  $('sync-info').textContent=c.garmin.sync?`Última descarga de actividades: ${new Date(c.garmin.sync.at).toLocaleString('es-ES')}. ${c.garmin.sync.received} actividades revisadas.`:'Aún no se ha descargado el historial.';
  if (c.garmin.last_attempt?.status==='failed') $('sync-info').textContent+=' La última sincronización falló; se conservan los datos anteriores.';
  if (c.garmin.last_attempt?.warnings?.length) $('sync-info').textContent+=' '+c.garmin.last_attempt.warnings.join(' ');
  const pro=c.pro.status!=='not_connected';
  $('pro-status').textContent=c.pro.status==='connected'?'Plan autorizado':c.pro.status==='permission_required'?'Permiso pendiente':'Sin conectar';
  $('pro-name').textContent=pro?c.pro.email:'Usa tu plan de ChatGPT en esta aplicación, mediante autorización oficial.';
  $('pro-tools').hidden=!pro; $('pro-new').hidden=!pro; $('pro-connect').textContent=pro?'Volver a autorizar con ChatGPT':'Continue with ChatGPT';
  $('nightly-info').textContent=c.nightly.enabled?`Sincronización a las ${String(c.nightly.hour).padStart(2,'0')}:00 (${c.nightly.timezone}) mientras el servidor esté encendido. Si lo arrancas después de esa hora, se recupera la ejecución pendiente del día.`:'La sincronización automática está desactivada. Puedes sincronizar manualmente.';
  const notice=await api('/api/pro/notice'); $('pro-notice').textContent=notice.message||'';
}
async function boot() {
  const s=await api('/api/session'); csrf=s.csrf; $('panel').hidden=!s.authenticated; $('login-view').hidden=s.authenticated;
  $('password-label').textContent=s.setup_required?'Crea la contraseña de tu panel':'Contraseña del panel';
  $('local-password').autocomplete=s.setup_required?'new-password':'current-password';
  $('setup-hint').textContent=s.setup_required?'Primera visita: elige al menos 12 caracteres. Esta contraseña es independiente de Garmin y ChatGPT.':'Introduce la contraseña que elegiste para este panel.';
  $('login-button').textContent=s.setup_required?'Crear mi acceso':'Entrar';
  if (s.authenticated) { tab(['#connections','#coach','#statistics','#calendar','#library'].includes(location.hash)?location.hash.slice(1):'overview'); await Promise.all([loadDashboard(),loadConnections(),loadCoach(),loadStatistics(),loadCalendar(),loadLibrary(),loadReview()]); }
}
async function watch(identifier, target) {
  const own=generation;
  while (own===generation) {
    const job=await api('/api/jobs/'+identifier);
    $(target).textContent=job.message;
    if (job.status==='waiting_mfa') { mfaJob=identifier; $('mfa-form').hidden=false; }
    if (job.status==='failed') { $('mfa-form').hidden=true; throw new Error(job.message); }
    if (job.status==='completed') {
      if(job.kind==='library'){await loadLibrary();return;}
      $('mfa-form').hidden=true; mfaJob=null;
      if (job.result?.text) { $('pro-result').textContent=job.result.text+(job.result.usage?'\nUso de esta prueba: '+JSON.stringify(job.result.usage):''); }
      if (job.kind==='pro' && job.result?.revocation_confirmed===false) toast('Desconectada localmente. La revocación remota no se ha confirmado; revisa el acceso en los ajustes de ChatGPT.');
      await Promise.all([loadDashboard(),loadConnections(),loadCoach(),loadStatistics(),loadCalendar(),loadLibrary(),loadReview()]); return;
    }
    await new Promise(resolve=>setTimeout(resolve,1500));
  }
}
function action(id, handler) {
  $(id).addEventListener('click',async event=>{
    event.preventDefault(); const button=event.currentTarget; button.disabled=true;
    try { await handler(); } catch(error) { toast(error.message,true); }
    finally { button.disabled=false; }
  });
}
$('login-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('login-error').textContent=''; $('login-button').disabled=true;
  try { await api('/api/session/login',{password:$('local-password').value}); $('local-password').value=''; await boot(); }
  catch(error) { $('login-error').textContent=error.message; }
  finally { $('login-button').disabled=false; }
});
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
action('go-connections',()=>tab('connections'));
action('logout',async()=>{ await api('/api/session/logout',{}); generation++; await boot(); });
for (const id of ['days','sport']) $(id).addEventListener('change',()=>loadDashboard().catch(e=>toast(e.message,true)));
action('more',()=>{visibleRows+=30;activityRows();});
action('sync',async()=>{const job=await api('/api/garmin/sync',{}); toast('Sincronización en curso…'); await watch(job.job_id,'toast');});
$('garmin-form').addEventListener('submit',async event=>{
  event.preventDefault(); const button=event.currentTarget.querySelector('button'); button.disabled=true;
  try { const body={email:$('garmin-email').value,password:$('garmin-password').value}; $('garmin-password').value=''; const job=await api('/api/garmin/connect',body); body.password=''; await watch(job.job_id,'garmin-job'); toast('Garmin conectada. Pulsa Sincronizar Garmin para importar tu historial.'); }
  catch(error){toast(error.message,true);} finally {button.disabled=false;}
});
$('mfa-form').addEventListener('submit',async event=>{event.preventDefault(); try {await api('/api/jobs/'+mfaJob+'/mfa',{code:$('mfa-code').value});$('mfa-code').value='';$('mfa-form').hidden=true;}catch(error){toast(error.message,true);}});
action('garmin-disconnect',async()=>{const j=await api('/api/garmin/disconnect',{});await watch(j.job_id,'garmin-job');toast('Garmin desconectada. El historial descargado se conserva.');});
async function connectPro(new_account=false) {
  if(location.hostname!=='127.0.0.1') throw new Error('Para autorizar ChatGPT Pro en el LXC, abre un túnel SSH al puerto configurado del servidor y entra en http://127.0.0.1:8000 (o ese puerto). Inicia sesión allí y conecta Pro. Después puedes seguir usando el dominio HTTPS. Consulta docs/LXC.md.');
  const result=await api('/api/pro/start',{new_account}); window.location.assign(result.url);
}
action('pro-connect',()=>connectPro()); action('pro-new',()=>connectPro(true));
action('load-models',async()=>{
  const data=await api('/api/pro/models'); $('model').replaceChildren();
  for(const m of data.models){const o=document.createElement('option');o.value=m.id;o.textContent=m.name;$('model').append(o);}
  $('pro-test').disabled=!data.models.length; if(!data.models.length)toast('OpenAI no devolvió modelos disponibles para esta cuenta.',true);
});
action('pro-test',async()=>{const j=await api('/api/pro/test',{model:$('model').value});toast('Comprobando ChatGPT Pro…');await watch(j.job_id,'toast');});
action('pro-disconnect',async()=>{const j=await api('/api/pro/disconnect',{});await watch(j.job_id,'pro-notice');$('model').replaceChildren();$('pro-test').disabled=true;});
$('options-form').addEventListener('submit',async event=>{
  event.preventDefault();try {await api('/api/wellness-options',{sleep:$('include-sleep').checked,hrv:$('include-hrv').checked});await loadDashboard();toast('Preferencias guardadas. Se aplicarán en la próxima sincronización.');}catch(error){toast(error.message,true);}
});

let coachState = {}, coachDirty = false, raceCatalog = {};
const availabilityPanels = [];
const weekdays=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
function field(parent,label,type,value,values=null) {
  const wrap=document.createElement('label');wrap.textContent=label;
  const input=document.createElement(values?'select':type==='textarea'?'textarea':'input');
  if(values) for(const [v,text] of values){const o=document.createElement('option');o.value=v;o.textContent=text;input.append(o);}
  else if(type!=='textarea') input.type=type;
  if(type==='checkbox')input.checked=Boolean(value);else input.value=value??'';
  wrap.append(input);parent.append(wrap);return input;
}
const sportOptions=Object.entries(sports).filter(([v])=>v!=='other');
for(const [v,label] of sportOptions.filter(([v])=>!['strength','triathlon'].includes(v))) {
  const input=field($('coach-sports'),label,'checkbox',['running','cycling','swimming'].includes(v));input.dataset.sport=v;
}
function daySlots(i, slots) {
  const panel=availabilityPanels[i]||document.createElement('fieldset');
  if(!availabilityPanels[i]){$('coach-availability').append(panel);availabilityPanels[i]=panel;}
  panel.replaceChildren(); const legend=document.createElement('legend');legend.textContent=weekdays[i];panel.append(legend);
  const count=field(panel,'Franjas disponibles','text',String(slots.length),[0,1,2,3,4].map(n=>[String(n),n===0?'Descanso':String(n)]));
  panel.slotFields=[];
  slots.forEach((s,j)=>{const row=document.createElement('div');row.className='slot-row';const period=field(row,`Franja ${j+1}`,'text',s.period,[['morning','Mañana'],['midday','Mediodía'],['afternoon','Tarde'],['evening','Noche'],['any','Flexible']]);const minutes=field(row,'Minutos','number',s.minutes);minutes.min=5;minutes.max=480;minutes.required=true;panel.slotFields.push({period,minutes});panel.append(row);});
  count.addEventListener('change',()=>{const current=panel.slotFields.map(f=>({period:f.period.value,minutes:Number(f.minutes.value)}));daySlots(i,Array.from({length:Number(count.value)},(_,j)=>current[j]||{period:j===0?'morning':'afternoon',minutes:60}));coachDirty=true;});
}
weekdays.forEach((_,i)=>daySlots(i,i===6?[]:[{period:'any',minutes:60}]));
for(const id of ['coach-long-run','coach-long-bike']) {
  for(const [v,label] of [['','Sin preferencia'],...weekdays.map((d,i)=>[String(i),d])]) {const o=document.createElement('option');o.value=v;o.textContent=label;$(id).append(o);}
}
function eventRow(event={priority:'secondary',sport:'triathlon'}) {
  const row=document.createElement('fieldset');const legend=document.createElement('legend');legend.textContent='Prueba';row.append(legend);
  row.fields={};row.eventId=event.id||crypto.randomUUID();
  for(const [key,label,type,options] of [['name','Nombre','text'],['day','Fecha','date'],['sport','Modalidad','text',sportOptions],['priority','Prioridad','text',[['primary','Objetivo principal'],['secondary','Objetivo secundario']]],['distance_code','Distancia estándar','text',[['other','Otra / personalizada']]],['distances','Distancias por disciplina','text'],['goal','Objetivo de esta prueba','text']]) {
    row.fields[key]=field(row,label,type,event[key],options);if(['name','day'].includes(key))row.fields[key].required=true;
  }
  const refreshDistances=()=>{
    const select=row.fields.distance_code, saved=select.value;
    select.replaceChildren();for(const [code,item] of Object.entries(raceCatalog[row.fields.sport.value]||{})){const o=document.createElement('option');o.value=code;o.textContent=item[0];select.append(o);}
    const other=document.createElement('option');other.value='other';other.textContent='Otra / personalizada';select.append(other);
    select.value=[...select.options].some(o=>o.value===saved)?saved:'other';
    showDistance();
  };
  const showDistance=()=>{const code=row.fields.distance_code.value, standard=raceCatalog[row.fields.sport.value]?.[code];row.fields.distances.parentElement.hidden=Boolean(standard);row.fields.distances.disabled=Boolean(standard);if(standard)row.fields.distances.value=standard[1];};
  row.fields.distance_code.value=event.distance_code||'other';refreshDistances();
  if(event.distance_code && raceCatalog[event.sport]?.[event.distance_code])row.fields.distance_code.value=event.distance_code;
  showDistance();row.fields.sport.addEventListener('change',()=>{row.fields.distance_code.value='other';row.fields.distances.value='';refreshDistances();});row.fields.distance_code.addEventListener('change',()=>{if(row.fields.distance_code.value==='other')row.fields.distances.value='';showDistance();});
  const remove=document.createElement('button');remove.type='button';remove.className='ghost';remove.textContent='Eliminar prueba';remove.onclick=()=>{coachDirty=true;row.remove();};row.append(remove);$('coach-events').append(row);
}
function sessionRow(s={day:$('coach-start').value,sport:'running',intensity:'easy',minutes:30,title:'',instructions:''}) {
  const row=document.createElement('fieldset');row.fields={};
  for(const [key,label,type,options] of [['day','Fecha','date'],['sport','Deporte','text',sportOptions.filter(([v])=>v!=='triathlon')],['title','Sesión','text'],['minutes','Minutos','number'],['intensity','Intensidad','text',[['easy','Suave'],['moderate','Moderada'],['hard','Intensa']]],['slot','Franja disponible','text',[["",'Sin asignar (perfil anterior)'],["0",'Franja 1'],["1",'Franja 2'],["2",'Franja 3'],["3",'Franja 4']]],['long_session','Tirada / salida larga','checkbox'],['instructions','Indicaciones','textarea']]) row.fields[key]=field(row,label,type,s[key],options);
  const remove=document.createElement('button');remove.type='button';remove.className='ghost';remove.textContent='Eliminar sesión';remove.onclick=()=>row.remove();row.append(remove);row.strengthExercises=s.strength_exercises||[];if(row.strengthExercises.length)row.append(strengthPreview(row.strengthExercises));row.workoutStructure=s.workout||null;const blocks=document.createElement('button');blocks.type='button';blocks.className='ghost';blocks.textContent='Editar bloques de la sesión';blocks.onclick=()=>openWorkout({title:row.fields.title.value,day:row.fields.day.value,sport:row.fields.sport.value,minutes:Number(row.fields.minutes.value),instructions:row.fields.instructions.value,structure:row.workoutStructure||defaultStructure(Number(row.fields.minutes.value))},null,body=>{row.workoutStructure=body.structure;for(const key of ['title','day','sport','minutes','instructions'])row.fields[key].value=body[key];});row.append(blocks);$('coach-sessions').append(row);
}
function readRows(id) {return [...$(id).children].map(row=>Object.fromEntries(Object.entries(row.fields).map(([k,e])=>[k,e.type==='checkbox'?e.checked:e.type==='number'?Number(e.value):e.value])));}
function modelOption(id,value,label=value) {if(value && ![...$(id).options].some(o=>o.value===value)){const o=document.createElement('option');o.value=value;o.textContent=label;$(id).append(o);}$(id).value=value;}
async function loadCoach() {
  coachDirty=false;
  raceCatalog=(await api('/api/race-distances')).catalog;coachState=await api('/api/coach');const p=coachState.setup?.profile;
  if(p){for(const [id,key] of [['coach-sex','sex'],['coach-age','age'],['coach-weight','weight_kg'],['coach-height','height_cm'],['coach-strength-equipment','strength_equipment'],['coach-strength-loads','strength_loads']])$(id).value=p[key]??'';$('coach-strength-experience').value=p.strength_experience||'intermediate';$('coach-experience').value=p.experience;$('coach-max-days').value=p.max_days;$('coach-strength').checked=p.strength;$('coach-wellness').checked=p.use_wellness;$('coach-zones').value=p.zones;$('coach-notes').value=p.notes;
    weekdays.forEach((_,i)=>daySlots(i,p.slots?.[i]||(p.availability[i]>0?[{period:'any',minutes:p.availability[i]}]:[])));$('coach-garmin-zones').checked=p.use_garmin_zones!==false;document.querySelectorAll('[data-sport]').forEach(e=>e.checked=p.sports.includes(e.dataset.sport));
    $('coach-long-run').value=p.long_run_day??'';$('coach-long-bike').value=p.long_bike_day??'';modelOption('coach-initial-model',p.initial_model);modelOption('coach-weekly-model',p.weekly_model);
  }
  $('coach-events').replaceChildren();(coachState.setup?.events||[{priority:'primary',sport:'triathlon'}]).forEach(eventRow);
  const d=coachState.draft;$('coach-draft-card').hidden=!d;
  $('coach-sessions').replaceChildren();if(d){$('coach-strategy').value=d.plan.strategy;$('coach-rationale').value=d.plan.rationale;d.plan.sessions.forEach(sessionRow);$('coach-draft-info').textContent=`Modelo: ${d.model} · Contexto: ${d.context_characters} caracteres · Uso: ${JSON.stringify(d.usage||{})}`;$('coach-warnings').textContent=d.warnings.join(' ');renderSourceAudit(d);}
  $('coach-accepted-sources-card').hidden=!coachState.accepted;if(coachState.accepted)renderSourceAudit(coachState.accepted,'coach-accepted-sources');
  table('coach-calendar',(coachState.calendar||[]).sort((a,b)=>a.day.localeCompare(b.day)).map(s=>[day(s.day)+' '+s.day.slice(0,4),sports[s.sport],s.title+(s.slot!=null?' · Franja '+(s.slot+1):''),s.minutes,s.instructions]));
}
$('coach-start').value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);
action('coach-add-event',()=>{coachDirty=true;eventRow();});action('coach-add-session',()=>sessionRow());
action('coach-models',async()=>{coachDirty=true;const data=await api('/api/pro/models');for(const id of ['coach-initial-model','coach-weekly-model']){const saved=$(id).value;$(id).replaceChildren();for(const m of data.models)modelOption(id,m.id,m.name);if(data.models.some(m=>m.id===saved))$(id).value=saved;else {const wanted=id==='coach-initial-model'?'astra':'sol';$(id).value=data.models.find(m=>m.id.includes(wanted))?.id||data.models[0]?.id||'';}}});
$('coach-form').addEventListener('submit',async e=>{e.preventDefault();try{const preference=id=>$(id).value===''?null:Number($(id).value);const profile={sex:$('coach-sex').value||null,age:preference('coach-age'),weight_kg:preference('coach-weight'),height_cm:preference('coach-height'),strength_experience:$('coach-strength-experience').value,strength_equipment:$('coach-strength-equipment').value,strength_loads:$('coach-strength-loads').value,experience:$('coach-experience').value,sports:[...document.querySelectorAll('[data-sport]:checked')].map(e=>e.dataset.sport),slots:availabilityPanels.map(p=>p.slotFields.map(f=>({period:f.period.value,minutes:Number(f.minutes.value)}))),use_garmin_zones:$('coach-garmin-zones').checked,availability:availabilityPanels.map(p=>p.slotFields.reduce((sum,f)=>sum+Number(f.minutes.value),0)),max_days:Number($('coach-max-days').value),strength:$('coach-strength').checked,long_run_day:preference('coach-long-run'),long_bike_day:preference('coach-long-bike'),zones:$('coach-zones').value,notes:$('coach-notes').value,use_wellness:$('coach-wellness').checked,initial_model:$('coach-initial-model').value,weekly_model:$('coach-weekly-model').value};const events=readRows('coach-events').map((r,i)=>({...r,id:$('coach-events').children[i].eventId}));await api('/api/coach/setup',{profile,events});coachDirty=false;toast('Perfil y objetivos guardados.');}catch(error){toast(error.message,true);}});
action('coach-generate',async()=>{if(feedbackDirty)throw new Error('Guarda la revisión de la semana para incluir tus sensaciones en el borrador.');if(coachDirty)throw new Error('Guarda los cambios del perfil y objetivos antes de generar.');const j=await api('/api/coach/generate',{start:$('coach-start').value,mode:$('coach-mode').value});$('coach-job').textContent='Preparando borrador con tu contexto deportivo…';await watch(j.job_id,'coach-job');tab('coach');});
action('coach-accept',async()=>{if(coachDirty)throw new Error('Guarda primero los cambios del perfil.');await api('/api/coach/accept',{draft_id:coachState.draft.id,plan:{citations:coachState.draft.plan.citations||[],strategy:$('coach-strategy').value,rationale:$('coach-rationale').value,sessions:readRows('coach-sessions').map((s,i)=>({...s,slot:s.slot===''?null:Number(s.slot),workout:$('coach-sessions').children[i].workoutStructure,strength_exercises:s.sport==='strength'?$('coach-sessions').children[i].strengthExercises:[]}))}});await Promise.all([loadCoach(),loadCalendar()]);toast('Semana revisada guardada en el calendario.');});
$('coach-form').addEventListener('input',()=>{coachDirty=true;});
$('coach-form').addEventListener('change',()=>{coachDirty=true;});
async function loadStatistics() {
  const data=await api('/api/sports-statistics'), groups=data.groups||{};
  const names={hr_zones:'Zonas FC',power_zones:'Zonas de potencia',ftp:'FTP',threshold:'Umbral',predictions:'Pronósticos',vo2:'VO₂ máx.'};
  const rows=key=>groups[key]?.rows||[];
  const state={available:'Disponible',empty:'Sin datos',failed:'No actualizado; última descarga conservada',unrecognized:'Formato de Garmin no reconocido'};
  const formatted=r=>{if(r.unit!=='s')return fmt(r.value)+' '+r.unit;const seconds=Math.round(r.value);return [Math.floor(seconds/3600),Math.floor(seconds%3600/60),seconds%60].map(v=>String(v).padStart(2,'0')).join(':');};
  const values=r=>[r.label,formatted(r),r.sport||'General / sin perfil indicado',r.measured_on||'No informada'];
  const withEmpty=rows=>rows.length?rows:[['Sin datos disponibles','—','—','—']];
  renderVo2(rows('vo2'));
  table('statistics-hr',withEmpty(rows('hr_zones').map(values)));table('statistics-power',withEmpty(rows('power_zones').map(values)));
  table('statistics-predictions',rows('predictions').length?rows('predictions').map(r=>[r.label,formatted(r),r.measured_on||'No informada']):[['Sin datos disponibles','—','—']]);
  const predictionState=groups.predictions?.status; $('statistics-prediction-state').textContent=({unrecognized:'Garmin respondió, pero no se reconoció el formato. Vuelve a sincronizar después de actualizar la web.',failed:'La última descarga falló. Se muestran los últimos pronósticos si estaban disponibles.',empty:'Garmin no devolvió pronósticos para esta cuenta.',available:''})[predictionState]??'Pendiente de sincronización con Garmin.';
  $('statistics-update').textContent=data.attempt_at?'Último intento: '+new Date(data.attempt_at).toLocaleString('es-ES'):'Sin referencias importadas. Pulsa Sincronizar Garmin.';
  $('statistics-status').textContent=Object.entries(names).map(([k,n])=>`${n}: ${state[groups[k]?.status]||'Pendiente'}${groups[k]?.at?' (descarga '+new Date(groups[k].at).toLocaleString('es-ES')+')':''}`).join('. ');
  const n=['hr_zones','power_zones','ftp','threshold','vo2','predictions'].reduce((s,k)=>s+rows(k).length,0);$('coach-garmin-summary').textContent=n?`${n} referencias importadas disponibles. Revisa sus fechas y perfiles en Estadísticas Garmin.`:'Todavía no hay referencias importadas. Sincroniza Garmin; si faltan datos puedes añadirlos aquí.';
}

let vo2Rows=[];
function renderVo2(rows) {
  vo2Rows=rows;const selected=$('statistics-vo2-sport').value;
  const profiles=[...new Set(rows.map(r=>(r.sport||'general').toLowerCase()))];
  $('statistics-vo2-sport').replaceChildren();
  profiles.forEach(profile=>{const o=document.createElement('option');o.value=profile;o.textContent=sports[profile]||(profile==='generic'?'General (Garmin)':profile==='general'?'Sin perfil indicado':profile);$('statistics-vo2-sport').append(o);});
  $('statistics-vo2-sport').value=profiles.includes(selected)?selected:profiles.find(p=>p==='running')||profiles.find(p=>p==='generic')||profiles[0]||'';
  updateVo2();
}
function updateVo2() {
  const profile=$('statistics-vo2-sport').value, unique=new Map();
  vo2Rows.filter(r=>(r.sport||'general').toLowerCase()===profile).sort((a,b)=>(b.measured_on||'').localeCompare(a.measured_on||'')).forEach(r=>{const key=r.measured_on||r.field+':'+r.value;if(!unique.has(key))unique.set(key,r);});
  const latest=[...unique.values()].slice(0,2);
  table('statistics-metrics',latest.length?latest.map(r=>[r.label,fmt(r.value,2)+' '+r.unit,$('statistics-vo2-sport').selectedOptions[0]?.textContent||'—',r.measured_on||'No informada']):[['Sin registros disponibles','—','—','—']]);
  let text='Necesitamos dos registros fechados del mismo perfil para comparar la tendencia.';
  if(latest.length===2 && latest.every(r=>r.measured_on) && latest[0].measured_on!==latest[1].measured_on){const diff=latest[0].value-latest[1].value;text=(diff>0?'↑ Aumenta':diff<0?'↓ Disminuye':'→ Sin cambio')+': '+(diff>0?'+':'')+fmt(diff,2)+' ml/kg/min respecto al registro anterior.';}
  $('statistics-vo2-trend').textContent=text;
}
$('statistics-vo2-sport').addEventListener('change',updateVo2);

let calendarMonth=new Date(new Date().getFullYear(),new Date().getMonth(),1), calendarVersion=0;
const sportIcons={running:'🏃',trail:'⛰',cycling:'🚴',swimming:'🏊',strength:'🏋',triathlon:'🏊🚴🏃',other:'●'};
const statuses={completed:'Realizada',planned:'Planificada',race:'Prueba'};
const localISO=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
for(const [sport,label] of Object.entries(sports)){const item=document.createElement('span');item.className='calendar-key sport-'+sport;item.textContent=sportIcons[sport]+' '+label;$('calendar-legend').append(item);}
async function loadCalendar() {
  const own=++calendarVersion, year=calendarMonth.getFullYear(), month=calendarMonth.getMonth();
  const data=await api('/api/calendar?year='+year+'&month='+(month+1));if(own!==calendarVersion)return;
  data.entries=data.entries.filter(e=>!e.is_draft||$('calendar-show-draft').checked);
  $('calendar-month').textContent=calendarMonth.toLocaleDateString('es-ES',{month:'long',year:'numeric'});
  const grid=$('calendar-grid');grid.replaceChildren();
  weekdays.forEach(d=>{const header=document.createElement('div');header.className='calendar-weekday';header.textContent=d.slice(0,3);grid.append(header);});
  const first=new Date(year,month,1), offset=(first.getDay()+6)%7, today=localISO(new Date());
  for(let i=0;i<42;i++){
    const moment=new Date(year,month,1-offset+i), iso=localISO(moment), cell=document.createElement('article');
    cell.className='calendar-day'+(moment.getMonth()!==month?' outside':'')+(iso===today?' today':'');
    cell.setAttribute('aria-label',moment.toLocaleDateString('es-ES',{weekday:'long',day:'numeric',month:'long'}));
    const number=document.createElement('div');number.className='calendar-day-number';number.textContent=String(moment.getDate());cell.append(number);
    data.entries.filter(e=>e.day===iso).forEach(entry=>{
      const button=document.createElement('button');button.className='calendar-entry sport-'+(sports[entry.sport]?entry.sport:'other')+' kind-'+entry.kind+(entry.is_draft?' draft':'');
      button.setAttribute('aria-label',statuses[entry.kind]+': '+entry.title+', '+(sports[entry.sport]||'Otros')+', '+entry.day);
      const title=document.createElement('span');title.textContent=(sportIcons[entry.sport]||'●')+' '+entry.title;
      const status=document.createElement('small');status.textContent=(entry.kind==='completed'?'✓ ':entry.kind==='planned'?'◷ ':'🏁 ')+(entry.is_draft?'Borrador':statuses[entry.kind])+(entry.origin==='manual'?' · Propia':entry.origin==='coach'?' · Coach':'');
      button.append(title,status);button.addEventListener('click',()=>showCalendarDetail(entry));cell.append(button);
    });grid.append(cell);
  }
  $('calendar-info').textContent=data.entries.filter(e=>e.kind==='completed').length+' realizadas · '+data.entries.filter(e=>e.kind==='planned').length+' planificadas · '+data.entries.filter(e=>e.kind==='race').length+' pruebas. Las celdas grises corresponden a otro mes; navega a ese mes para ver sus entradas.';
}
function showCalendarDetail(entry) {
  $('calendar-detail-title').textContent=(sportIcons[entry.sport]||'●')+' '+entry.title;
  const body=$('calendar-detail-body');body.replaceChildren();const dl=document.createElement('dl');
  const add=(name,value)=>{if(value==null||value==='')return;const term=document.createElement('dt'),detail=document.createElement('dd');term.textContent=name;detail.textContent=String(value);dl.append(term,detail);};
  const d=entry.detail;add('Estado',entry.is_draft?'Borrador sin aceptar':statuses[entry.kind]);add('Fecha',new Date(entry.day+'T12:00:00').toLocaleDateString('es-ES',{weekday:'long',day:'numeric',month:'long',year:'numeric'}));add('Deporte',sports[entry.sport]||'Otros');
  if(entry.kind==='completed'){add('Origen','Garmin Connect');add('Tiempo',hours(d.duration_seconds));add('Distancia',fmt(d.distance_m/1000,2)+' km');add('Desnivel positivo',fmt(d.elevation_m,0)+' m');add('FC media',d.average_hr==null?'No disponible':fmt(d.average_hr,0)+' ppm');}
  if(entry.kind==='planned'){add('Origen',entry.origin==='manual'?'Sesión propia':'Coach');add('Duración',d.minutes+' min');add('Intensidad',({easy:'Suave',moderate:'Moderada',hard:'Intensa'})[d.intensity]);add('Franja',d.slot==null?'Sin asignar':String(d.slot+1));add('Horario',({morning:'Mañana',midday:'Mediodía',afternoon:'Tarde',evening:'Noche',any:'Flexible'})[d.period]);add('Sesión larga',d.long_session?'Sí':'No');add('Indicaciones',d.instructions);}
  if(entry.kind==='race'){add('Prioridad',d.priority==='primary'?'Objetivo principal':'Objetivo secundario');add('Distancias',d.distances);add('Objetivo',d.goal);}
  body.append(dl);
  if(entry.kind==='planned'){
    if(d.strength_exercises?.length)body.append(strengthPreview(d.strength_exercises));const structure=d.structure||d.workout;if(structure)body.append(blocksPreview(structure.blocks));
    if(entry.origin==='manual'){
      const edit=document.createElement('button');edit.className='ghost';edit.textContent=d.publication?.status?'Crear variante editable':'Editar sesión';edit.onclick=()=>{$('calendar-detail').close();openWorkout(d,d.publication?.status?null:d.id);};
      const send=document.createElement('button');send.textContent=d.publication?.status==='complete'?'Ver envío a Garmin':'Revisar envío a Garmin';send.onclick=async()=>{try{$('calendar-detail').close();await previewWorkout(d.id);}catch(e){toast(e.message,true);}};body.append(edit,send);
    }else if(!entry.is_draft){
      const copy=document.createElement('button');copy.className='ghost';copy.textContent='Crear copia propia y editar bloques';copy.onclick=()=>{$('calendar-detail').close();openWorkout({...d,title:'Copia: '+d.title,structure:d.workout||defaultStructure(d.minutes)},null).then(()=>{if(!d.workout)$('workout-editor-hint').textContent='Estos bloques son una plantilla: adáptalos a las indicaciones antes de guardar. Guardar crea otra propuesta propia en el calendario.';}).catch(error=>toast(error.message));};body.append(copy);
      if(d.workout){const send=document.createElement('button');send.textContent='Revisar envío a Garmin';send.onclick=async()=>{try{const imported=await api('/api/workouts/from-coach',{source:d.source_key});$('calendar-detail').close();await previewWorkout(imported.id);}catch(e){toast(e.message,true);}};body.append(send);}
    }
  }
  if(entry.kind==='planned'){
    const remove=document.createElement('button');remove.className='ghost';remove.textContent='Borrar sesión';remove.onclick=()=>{removingWorkout=entry;$('calendar-detail').close();$('workout-remove-summary').textContent=entry.title+' · '+entry.day+' · '+(entry.is_draft?'Borrador':entry.origin==='manual'?'Sesión propia':'Sesión del coach');$('workout-remove-error').textContent='';$('workout-remove-dialog').showModal();};body.append(remove);
  }
  $('calendar-detail').showModal();
}
let removingWorkout=null;
action('workout-remove-cancel',()=>$('workout-remove-dialog').close());
$('workout-remove-confirm').addEventListener('click',async()=>{const button=$('workout-remove-confirm');button.disabled=true;try{const entry=removingWorkout;const url=entry.origin==='manual'?'/api/workouts/'+entry.detail.id+'/remove':'/api/coach/sessions/'+entry.detail.source_key+'/remove?draft='+Boolean(entry.is_draft);await api(url,{});$('workout-remove-dialog').close();await Promise.all([loadCalendar(),loadReview(),loadCoach()]);toast('Sesión borrada del calendario de la web.');}catch(error){$('workout-remove-error').textContent=error.message;}finally{button.disabled=false;}});
action('calendar-prev',async()=>{if(calendarMonth.getFullYear()===2000&&calendarMonth.getMonth()===0)return;calendarMonth=new Date(calendarMonth.getFullYear(),calendarMonth.getMonth()-1,1);await loadCalendar();});
action('calendar-next',async()=>{if(calendarMonth.getFullYear()===2100&&calendarMonth.getMonth()===11)return;calendarMonth=new Date(calendarMonth.getFullYear(),calendarMonth.getMonth()+1,1);await loadCalendar();});
action('calendar-today',async()=>{calendarMonth=new Date(new Date().getFullYear(),new Date().getMonth(),1);await loadCalendar();});
action('calendar-close',()=>$('calendar-detail').close());
$('calendar-show-draft').addEventListener('change',()=>loadCalendar().catch(e=>toast(e.message,true)));
let editingWorkout=null, draftWorkoutSave=null, sendWorkout=null, workoutOptions={strength_categories:[]};
const blockNames={warmup:'Calentamiento',exercise:'Ejercicio',recovery:'Recuperación',rest:'Descanso',cooldown:'Vuelta a la calma',repeat:'Repetir bloque'};
const swimStrokes={'':'Sin especificar',free:'Crol',backstroke:'Espalda',breaststroke:'Braza',any_stroke:'Libre elección',butterfly:'Mariposa',drill:'Técnica'};
const swimEquipment={'':'Sin material',kickboard:'Tabla',pull_buoy:'Pull buoy',fins:'Aletas',paddles:'Palas',snorkel:'Snorkel'};
function defaultStructure(minutes=20){const total=Number(minutes)*60,warm=Math.min(300,total/5),cool=warm;return {pool_length:25,blocks:[{kind:'warmup',duration_type:'time',value:warm},{kind:'exercise',duration_type:'time',value:total-warm-cool},{kind:'cooldown',duration_type:'time',value:cool}]};}
function workoutTime(seconds){const n=Math.round(Number(seconds));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0');}
function workoutSeconds(text){if(!/^\d+:[0-5]\d$/.test(text))throw new Error('Indica el tiempo en minutos:segundos, por ejemplo 5:30.');const [m,s]=text.split(':').map(Number);const total=m*60+s;if(total<=0||total>86400)throw new Error('El tiempo de cada paso debe ser mayor que 0:00 y no superar 1440:00.');return total;}
function updateWorkoutDuration(){try{const walk=b=>b.kind==='repeat'?b.iterations*b.steps.reduce((sum,step)=>sum+walk(step),0):b.duration_type==='time'?b.value:0;const allTime=b=>b.kind==='repeat'?b.steps.every(allTime):b.duration_type==='time';const blocks=[...$('workout-blocks').children].map(c=>c.readBlock());const total=blocks.reduce((sum,b)=>sum+walk(b),0),estimate=Number($('workout-minutes').value)*60;const warn=blocks.length&&total!==estimate&&(blocks.every(allTime)||total>estimate);$('workout-duration-warning').textContent=warn?`Los bloques por tiempo suman ${workoutTime(total)} y la duración estimada es ${workoutTime(estimate)}. Puedes guardar sin que coincidan.`:'';}catch{$('workout-duration-warning').textContent='';}}
function strengthPreview(exercises){const section=document.createElement('section'),heading=document.createElement('h3');heading.textContent='Ejercicios de fuerza';section.append(heading);const list=document.createElement('ol');for(const exercise of exercises){const item=document.createElement('li'),name=document.createElement('strong'),detail=document.createElement('p');name.textContent=exercise.name;detail.textContent=`${exercise.sets} series · ${exercise.repetitions} · Carga: ${exercise.load} · Descanso: ${workoutTime(exercise.rest_seconds)} min:s`+(exercise.cues?' · '+exercise.cues:'');item.append(name,detail);list.append(item);}section.append(list);return section;}
function blocksPreview(blocks){const list=document.createElement('ol');for(const b of blocks){const item=document.createElement('li');item.textContent=blockNames[b.kind]+(b.kind==='repeat'?' × '+b.iterations:b.duration_type==='lap'?' · Hasta pulsar Lap':' · '+(b.duration_type==='time'?workoutTime(b.value)+' min:s':b.value+' '+({distance:'m',reps:'repeticiones'})[b.duration_type]))+(b.target&&b.target!=='none'?' · '+(b.target==='hr_zone'?'FC':'Potencia')+' Z'+b.zone:'')+(b.stroke?' · '+(swimStrokes[b.stroke]||b.stroke):'')+(b.equipment?' · '+(swimEquipment[b.equipment]||b.equipment):'')+(b.notes?' · '+b.notes:'');if(b.kind==='repeat')item.append(blocksPreview(b.steps));list.append(item);}return list;}
function editorField(parent,label,type,value,choices){const wrap=document.createElement('label');wrap.textContent=label;let input;if(choices){input=document.createElement('select');for(const [key,text] of Object.entries(choices))input.append(new Option(text,key));}else{input=document.createElement(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;}input.value=value??'';wrap.append(input);parent.append(wrap);return input;}
function blockEditor(container,b={kind:'exercise',duration_type:'time',value:60},depth=0){
  const root=document.createElement('section');root.className='workout-block';const heading=document.createElement('h4');heading.textContent=blockNames[b.kind]||'Paso';root.append(heading);const fields=document.createElement('div');fields.className='workout-step-fields';root.append(fields);let read;
  if(b.kind==='repeat'){
    const count=editorField(fields,'Repeticiones del bloque','number',b.iterations||2);count.min='2';count.max='50';const children=document.createElement('div');root.append(children);(b.steps||[{kind:'exercise',duration_type:'time',value:60},{kind:'rest',duration_type:'time',value:30}]).forEach(step=>blockEditor(children,step,depth+1));const add=document.createElement('button');add.type='button';add.className='ghost';add.textContent='Añadir paso dentro del bloque';add.onclick=()=>blockEditor(children,undefined,depth+1);root.append(add);
    if(depth<2){const nested=document.createElement('button');nested.type='button';nested.className='ghost';nested.textContent='Añadir repetición dentro del bloque';nested.onclick=()=>blockEditor(children,{kind:'repeat',iterations:2},depth+1);root.append(nested);}
    read=()=>({kind:'repeat',iterations:Number(count.value),steps:[...children.children].map(c=>c.readBlock())});
  }else{
    const kind=editorField(fields,'Tipo de paso','',b.kind||'exercise',Object.fromEntries(Object.entries(blockNames).filter(([k])=>k!=='repeat')));
    const unit=editorField(fields,'Fin del paso','',b.duration_type||'time',{time:'Tiempo (minutos:segundos)',distance:'Distancia (metros)',lap:'Hasta pulsar Lap',reps:'Repeticiones (fuerza)'});
    const value=editorField(fields,'Cantidad','number',b.value??60);let previousUnit=null;const label=document.createTextNode('');value.parentElement.firstChild.replaceWith(label);
    const target=editorField(fields,'Objetivo','',b.target||'none',{none:'Sin objetivo / esfuerzo en notas',hr_zone:'Zona de frecuencia cardiaca',power_zone:'Zona de potencia (bici)'});const zone=editorField(fields,'Zona','number',b.zone??2);zone.min='1';zone.max='7';
    const stroke=editorField(fields,'Estilo de natación','',b.stroke||'',swimStrokes),equipment=editorField(fields,'Material de natación','',b.equipment||'',swimEquipment);
    const category=editorField(fields,'Categoría Garmin de fuerza','',b.category||'',Object.fromEntries([['','Sin categoría'],...workoutOptions.strength_categories.map(c=>[c,c])]));
    const notes=editorField(root,'Notas del paso','textarea',b.notes||'');notes.maxLength=500;notes.rows=2;
    const update=()=>{if(previousUnit!==unit.value){value.type=unit.value==='time'?'text':'number';value.removeAttribute('pattern');if(unit.value==='time'){value.value=workoutTime(previousUnit===null?(b.value??60):60);value.pattern='[0-9]+:[0-5][0-9]';value.placeholder='5:30';value.inputMode='text';}else{value.value=previousUnit===null?(b.value??100):unit.value==='reps'?10:100;value.min='1';value.max='86400';}previousUnit=unit.value;}label.textContent=unit.value==='time'?'Duración (minutos:segundos)':unit.value==='distance'?'Distancia (metros)':unit.value==='reps'?'Cantidad de repeticiones':'Cantidad';value.required=unit.value!=='lap';value.disabled=unit.value==='lap';zone.disabled=target.value==='none';const swim=$('workout-sport').value==='swimming';stroke.parentElement.hidden=!swim;equipment.parentElement.hidden=!swim;category.parentElement.hidden=$('workout-sport').value!=='strength';};unit.onchange=update;target.onchange=update;root.updateSport=update;update();
    read=()=>({kind:kind.value,duration_type:unit.value,value:unit.value==='lap'?null:unit.value==='time'?workoutSeconds(value.value):Number(value.value),target:target.value,zone:target.value==='none'?null:Number(zone.value),stroke:$('workout-sport').value==='swimming'?stroke.value:'',equipment:$('workout-sport').value==='swimming'?equipment.value:'',category:$('workout-sport').value==='strength'?category.value:'',notes:notes.value});
  }
  const controls=document.createElement('div');const remove=document.createElement('button');remove.type='button';remove.className='ghost';remove.textContent='Eliminar bloque';remove.onclick=()=>{root.remove();updateWorkoutDuration();};const up=document.createElement('button');up.type='button';up.className='ghost';up.textContent='Subir bloque';up.onclick=()=>{if(root.previousElementSibling)container.insertBefore(root,root.previousElementSibling);};controls.append(up,remove);root.append(controls);root.readBlock=read;container.append(root);updateWorkoutDuration();
}
async function openWorkout(data={},identifier=null,onSave=null){
  workoutOptions=await api('/api/workout-options');editingWorkout=identifier;draftWorkoutSave=onSave;$('workout-save').textContent=onSave?'Guardar bloques en borrador':'Guardar sesión en calendario';$('workout-editor-hint').textContent=onSave?'Edita los bloques del borrador. El calendario cambiará cuando aceptes la semana.':'Guardar añade una propuesta al calendario local. El envío a Garmin es un paso posterior. Tiempo en minutos:segundos, distancia en metros.';
  $('workout-editor-title').textContent=identifier?'Editar sesión propia':'Crear sesión propia';$('workout-title').value=data.title||'';$('workout-day').value=data.day||new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);$('workout-sport').value=data.sport||'running';$('workout-minutes').value=data.minutes||20;$('workout-notes').value=data.instructions||'';$('workout-pool').value=data.structure?.pool_length||25;$('workout-blocks').replaceChildren();(data.structure||defaultStructure(data.minutes||20)).blocks.forEach(b=>blockEditor($('workout-blocks'),b));$('workout-pool').hidden=$('workout-sport').value!=='swimming';document.querySelector('label[for="workout-pool"]').hidden=$('workout-pool').hidden;$('workout-editor-error').textContent='';updateWorkoutDuration();$('workout-editor').showModal();
}
action('calendar-create',()=>openWorkout());
action('workout-add-step',()=>blockEditor($('workout-blocks')));action('workout-add-repeat',()=>blockEditor($('workout-blocks'),{kind:'repeat',iterations:2}));action('workout-editor-close',()=>$('workout-editor').close());
$('workout-sport').addEventListener('change',()=>{$('workout-pool').hidden=$('workout-sport').value!=='swimming';document.querySelector('label[for="workout-pool"]').hidden=$('workout-pool').hidden;$('workout-blocks').querySelectorAll('section').forEach(s=>s.updateSport?.());});
$('workout-form').addEventListener('input',updateWorkoutDuration);$('workout-form').addEventListener('change',updateWorkoutDuration);
$('workout-form').addEventListener('submit',async event=>{event.preventDefault();$('workout-save').disabled=true;$('workout-editor-error').textContent='';try{const body={title:$('workout-title').value,day:$('workout-day').value,sport:$('workout-sport').value,minutes:Number($('workout-minutes').value),instructions:$('workout-notes').value,structure:{pool_length:Number($('workout-pool').value),blocks:[...$('workout-blocks').children].map(c=>c.readBlock())}};if(draftWorkoutSave){await api('/api/workouts/validate',body);draftWorkoutSave(body);$('workout-editor').close();toast('Bloques actualizados en el borrador.');return;}await api('/api/workouts'+(editingWorkout?'/'+editingWorkout:''),body);$('workout-editor').close();calendarMonth=new Date(body.day+'T12:00:00');await Promise.all([loadCalendar(),loadReview()]);toast('Sesión guardada en el calendario local. Abre su detalle para revisar el envío a Garmin.');}catch(error){$('workout-editor-error').textContent=error.message;}finally{$('workout-save').disabled=false;}});
async function previewWorkout(identifier){const [preview,saved]=await Promise.all([api('/api/workouts/'+identifier+'/preview'),api('/api/workouts/'+identifier)]);sendWorkout={id:identifier,revision:preview.revision};$('workout-send-summary').textContent=saved.title+' · '+saved.day+' · '+sports[saved.sport]+' · '+saved.minutes+' min';$('workout-send-blocks').replaceChildren(blocksPreview(saved.structure.blocks));$('workout-send-warnings').textContent=preview.warnings.join(' ');$('workout-send-json').textContent=JSON.stringify(preview.payload,null,2);$('workout-send-status').textContent=saved.publication.status==='complete'?'Creada y programada en Garmin. ID: '+saved.publication.workout_id+'. Sincroniza tu reloj con Garmin Connect.':saved.publication.status?'Estado del envío anterior: '+saved.publication.status:'';$('workout-send-confirm').disabled=Boolean(saved.publication.status);$('workout-send-dialog').showModal();}
$('workout-send-confirm').addEventListener('click',async()=>{const button=$('workout-send-confirm');button.disabled=true;try{const job=await api('/api/workouts/'+sendWorkout.id+'/send',{revision:sendWorkout.revision});await watch(job.job_id,'workout-send-status');const saved=await api('/api/workouts/'+sendWorkout.id);$('workout-send-status').textContent='Creada y programada en Garmin. ID: '+saved.publication.workout_id+'. Sincroniza el reloj con Garmin Connect.';}catch(error){$('workout-send-status').textContent=error.message;const saved=await api('/api/workouts/'+sendWorkout.id).catch(()=>null);button.disabled=Boolean(saved?.publication.status);}});
action('workout-send-close',()=>$('workout-send-dialog').close());
let reviewState = null, feedbackDirty = false;
async function loadReview() {
  if(feedbackDirty)return;
  reviewState=await api('/api/coach/review');
  $('coach-review-dates').textContent=reviewState.from+' — '+reviewState.through;
  table('coach-review-table',Object.entries(reviewState.sports).map(([sport,r])=>[sports[sport]||sport,r.planned.sessions+' sesiones · '+fmt(r.planned.minutes,0)+' min',r.actual.sessions+' sesiones · '+fmt(r.actual.minutes,0)+' min',fmt(r.actual.km)+' km',r.volume_change_percent==null?'Sin base suficiente':fmt(r.volume_change_percent)+' % · '+r.prior_active_weeks+' semanas con registros']));
  $('coach-review-limitations').textContent=reviewState.limitations;
  $('coach-fatigue').value=reviewState.feedback?.fatigue??'';$('coach-effort').value=reviewState.feedback?.effort??'';$('coach-feedback').value=reviewState.feedback?.notes||'';
}
$('coach-feedback-form').addEventListener('input',()=>{feedbackDirty=true;});
$('coach-feedback-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.submitter;button.disabled=true;
  try {await api('/api/coach/feedback',{week_start:reviewState.from,fatigue:$('coach-fatigue').value?Number($('coach-fatigue').value):null,effort:$('coach-effort').value?Number($('coach-effort').value):null,notes:$('coach-feedback').value});feedbackDirty=false;toast('Revisión guardada para la próxima planificación.');}
  catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
function renderSourceAudit(draft,target='coach-source-audit') {
  const root=$(target);root.replaceChildren();const title=document.createElement('h3');title.textContent='Fragmentos enviados al coach';root.append(title);
  if(!draft.sources_snapshot?.length){const p=document.createElement('p');p.textContent='No se enviaron fragmentos de la Biblioteca.';root.append(p);return;}
  for(const source of draft.sources_snapshot){const details=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('p');summary.textContent=source.title+' · versión '+source.version+' · '+source.locator+((draft.plan.citations||[]).includes(source.id)?' · Citada por el coach':' · Enviada, sin cita');text.textContent=source.text;details.append(summary,text);root.append(details);}
}
async function loadLibrary() {
  const data=await api('/api/library'),selected=$('library-target').value;
  $('coach-library-summary').textContent=data.documents.filter(d=>d.enabled&&d.active!=null).length+' fuentes seleccionadas para nuevas planificaciones. Puedes revisarlas en Biblioteca.';
  $('library-target').replaceChildren(new Option('Nueva fuente',''));$('library-documents').replaceChildren();
  if(!data.documents.length){const p=document.createElement('p');p.className='muted';p.textContent='Todavía no hay fuentes. Puedes subir aquí tu EPUB cuando quieras.';$('library-documents').append(p);}
  for(const doc of data.documents){
    $('library-target').append(new Option(doc.title,doc.id));
    const item=document.createElement('section');item.className='library-document';const heading=document.createElement('h3');heading.textContent=doc.title;const by=document.createElement('p');by.className='muted';by.textContent=(doc.author||'Autor sin indicar')+' · Versión activa: '+(doc.active??'ninguna');
    const label=document.createElement('label');label.className='check';const check=document.createElement('input');check.type='checkbox';check.checked=doc.enabled;check.disabled=doc.active==null;label.append(check,document.createTextNode('Usar en el coach: '+doc.title));
    check.addEventListener('change',async()=>{check.disabled=true;try{await api('/api/library/'+doc.id+'/enabled',{enabled:check.checked});await loadLibrary();toast('Selección de fuentes guardada para futuras generaciones.');}catch(error){check.checked=!check.checked;toast(error.message,true);}finally{check.disabled=false;}});
    const newest=doc.versions[0],process=document.createElement('button');process.type='button';process.textContent=newest.status==='ready'?'Versión procesada':doc.active==null?'Procesar documento':'Procesar actualización';process.disabled=newest.status==='ready';
    process.addEventListener('click',async()=>{process.disabled=true;try{const job=await api('/api/library/'+doc.id+'/process',{});$('library-job').textContent='Extrayendo e indexando texto en tu equipo…';await watch(job.job_id,'library-job');toast('Documento procesado. Revisa la muestra y selecciona si usarlo en el coach.');}catch(error){toast(error.message,true);await loadLibrary();}});
    const preview=document.createElement('button');preview.type='button';preview.className='ghost';preview.textContent='Ver muestra';preview.disabled=doc.active==null;preview.addEventListener('click',async()=>{try{const result=await api('/api/library/'+doc.id+'/preview');$('library-preview-body').replaceChildren();for(const f of result.fragments){const h=document.createElement('h3'),p=document.createElement('p');h.textContent=f.locator;p.textContent=f.text;$('library-preview-body').append(h,p);}$('library-preview').showModal();}catch(error){toast(error.message,true);}});
    const versions=document.createElement('details'),caption=document.createElement('summary');caption.textContent='Versiones y estado';versions.append(caption);
    for(const v of doc.versions){const p=document.createElement('p');p.textContent='v'+v.version+' · '+v.filename+' · '+({pending:'Pendiente de procesamiento',ready:'Procesada',failed:'No se pudo procesar'}[v.status]||v.status)+' · '+v.chunks+' fragmentos · '+new Date(v.created).toLocaleString('es-ES')+(v.detail?' · '+v.detail:'')+(v.warnings.length?' · '+v.warnings.join(' '):'');versions.append(p);}
    item.append(heading,by,label,process,preview,versions);$('library-documents').append(item);
  }
  if(data.documents.some(d=>d.id===selected))$('library-target').value=selected;
}
$('library-preview-close').addEventListener('click',()=>$('library-preview').close());
$('library-target').addEventListener('change',()=>{const replacing=Boolean($('library-target').value);$('library-title').disabled=replacing;$('library-author').disabled=replacing;$('library-upload').textContent=replacing?'Subir actualización':'Subir archivo';});
$('library-upload-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=$('library-upload');button.disabled=true;
  try{const file=$('library-file').files[0];if(!file||file.size>40*1024*1024)throw new Error('Selecciona un documento de hasta 40 MB.');const query=new URLSearchParams({filename:file.name,title:$('library-title').value,author:$('library-author').value});if($('library-target').value)query.set('document_id',$('library-target').value);
    const response=await fetch('/api/library/upload?'+query,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-CSRF-Token':csrf},body:file});const data=await response.json();if(!response.ok)throw new Error(data.detail||'No se pudo subir el documento.');$('library-file').value='';await loadLibrary();toast('Archivo guardado. Pulsa Procesar documento para incorporarlo; todavía no se usa en el coach.');
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
boot().catch(error=>{$('login-error').textContent=error.message;});
