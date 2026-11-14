/* Embedded form renderer is the reviewed shared __app module, bundled below. */
'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('session');
history.replaceState(null, '', location.pathname);
const root=document.getElementById('workspace'), title=document.createElement('h1'), status=document.createElement('p'), select=document.createElement('select'), open=document.createElement('button'), close=document.createElement('button'), formRoot=document.createElement('section');
const search=document.createElement('input'), find=document.createElement('button');search.maxLength=128;search.setAttribute('aria-label','Поиск объявленных форм');find.textContent='Найти формы';
select.setAttribute('aria-label','Объявленная форма'); open.textContent='Открыть форму'; close.textContent='Закрыть сеанс'; status.setAttribute('role','status');
const limitations=document.createElement('ul');limitations.setAttribute('aria-label','Неподдерживаемые возможности формы');
const tabs=document.createElement('nav');tabs.setAttribute('aria-label','Открытые формы');
const explorer=document.createElement('section'),explorerTitle=document.createElement('h2');explorerTitle.textContent='Объекты конфигурации';
const objectSearch=document.createElement('input'),families=document.createElement('select'),objects=document.createElement('select'),objectFind=document.createElement('button'),inspect=document.createElement('button'),detail=document.createElement('section'),inventoryStatus=document.createElement('p');
objectSearch.maxLength=128;objectSearch.setAttribute('aria-label','Поиск объектов');families.setAttribute('aria-label','Тип объекта');objects.setAttribute('aria-label','Объект конфигурации');
objectFind.textContent='Найти объекты';inspect.textContent='Описание объекта';detail.setAttribute('aria-label','Метаданные выбранного объекта');inventoryStatus.setAttribute('role','status');
explorer.append(explorerTitle,objectSearch,families,objectFind,objects,inspect,inventoryStatus,detail);
root.append(title,status,explorer,search,find,select,open,close,tabs,limitations,formRoot);
let id=0,busy=false,view=null,state=null,failed=false,inFlight=0;
const mounts=new Map();
let syncNeeded=false;
function syncForms(){if(syncNeeded&&!busy&&!inFlight&&!failed){syncNeeded=false;action('workspace.snapshot',{});}}
async function call(method,params={}) {
  const response=await fetch('/rpc',{method:'POST',headers:{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':token||''},body:JSON.stringify({jsonrpc:'2.0',id:++id,method,params})+'\n'});
  if(!response.ok)throw Error('Связь потеряна. Команда не повторяется автоматически.');
  const reply=await response.json();if(reply.error)throw Error('Запрос отклонён');return reply.result;
}
function paint(){
  if([...mounts.values()].some(entry=>entry.view.client?.transportFailed||entry.view.client?.outcomeUnknown||entry.view.client?.snapshot?.uncertain)){
    failed=true;status.textContent='Результат действия неизвестен. Формы и черновики сохранены в этой вкладке; переключение и повтор команд заблокированы.';
  }
  const blocked=busy||failed||inFlight>0||!state||state.kind==='closed';
  open.disabled=blocked||!select.value;
  search.disabled=find.disabled=select.disabled=Boolean(blocked);
  close.disabled=blocked||[...mounts.values()].some(entry=>entry.view.client?.snapshot?.kind!=='closed');
  for(const button of tabs.children)button.disabled=Boolean(blocked);
  for(const control of [objectSearch,families,objects,objectFind,inspect,...detail.querySelectorAll('button')])control.disabled=Boolean(blocked);
  inspect.disabled=Boolean(blocked)||!objects.value;
  for(const entry of mounts.values())entry.view.repaint();
}
async function formCall(generation,request){
  if(failed||generation!==state?.generation)throw Error('Неактивная форма');
  inFlight++;paint();
  try{return await call('workspace.form',{generation,request});}
  finally{inFlight--;paint();}
}
async function apply(reply){
  if(reply.protocol!=='yadinassi-source-workspace/1')throw Error('Неизвестный протокол');state=reply.state;
  title.textContent=state.name+' · Source workspace';status.textContent=state.error|| (state.kind==='closed'?'Сеанс закрыт':'Формы в памяти: без сохранения объектов базы и без заявления о совместимости с 1С.');
  const previous=select.value;select.replaceChildren();
  for(const name of state.forms){const option=document.createElement('option');option.value=name;option.textContent=name;select.append(option);}
  if(state.forms.includes(previous))select.value=previous;
  if(state.omitted_forms)status.textContent+=' Ещё '+state.omitted_forms+' форм: уточните поиск.';
  limitations.replaceChildren();for(const diagnostic of state.form_diagnostics||[]){const item=document.createElement('li');item.textContent=diagnostic.path+': '+diagnostic.reason;limitations.append(item);}
  const previousObject=objects.value;objects.replaceChildren();
  for(const name of state.objects||[]){const option=document.createElement('option');option.value=option.textContent=name;objects.append(option);}
  if((state.objects||[]).includes(previousObject))objects.value=previousObject;
  families.replaceChildren();for(const family of ['',...(state.object_families||[])]){const option=document.createElement('option');option.value=family;option.textContent=family||'Все типы';families.append(option);}families.value=state.object_family||'';
  inventoryStatus.textContent='Показано объектов: '+(state.objects||[]).length+(state.omitted_objects?'; ещё '+state.omitted_objects+', уточните поиск.':'.');
  if(state.omitted_families)inventoryStatus.textContent+=' Других типов: '+state.omitted_families+'. Используйте поиск по полному имени.';
  detail.replaceChildren();
  if(state.object_detail){
    const data=state.object_detail,heading=document.createElement('h3'),path=document.createElement('p'),notice=document.createElement('p');
    heading.textContent=data.name;path.textContent='XML: '+data.source_path;
    notice.textContent=data.execution==='metadata_only'?'Только метаданные: объявленной исполняемой формы нет. CRUD и хранилище не предоставляются.':'Объявленные формы открываются явно и могут выдавать ошибки неподдерживаемых возможностей. CRUD и хранилище не предоставляются.';
    detail.append(heading,path,notice);
    for(const name of data.forms){const button=document.createElement('button');button.textContent='Открыть '+name;button.addEventListener('click',()=>action('workspace.open',{name}));detail.append(button);}
    if(data.omitted_forms){const note=document.createElement('p');note.textContent='Ещё форм: '+data.omitted_forms+'. Уточните общий поиск форм.';detail.append(note);}
  }
  const entries=state.open_forms||[];
  for(const [generation,entry] of mounts){
    if(!entries.some(item=>item.generation===generation)){entry.panel.remove();mounts.delete(generation);}
  }
  tabs.replaceChildren();
  for(const item of entries){
    const button=document.createElement('button');button.textContent=item.name+(item.active?'':' (закрыта)');
    button.setAttribute('aria-current',item.generation===state.generation?'page':'false');
    button.addEventListener('click',()=>action('workspace.select',{generation:item.generation}));tabs.append(button);
  }
  if(state.active && !mounts.has(state.generation)){
    const generation=state.generation,panel=document.createElement('section');formRoot.append(panel);
    const mount=__app.mountForm(window,panel,{transport:request=>formCall(generation,request),
      isActive:()=>state?.generation===generation,
      businessBlocked:()=>busy||failed||state?.generation!==generation,
      onChange:()=>{paint();syncNeeded=true;queueMicrotask(syncForms);}});
    mounts.set(generation,{panel,view:mount});await mount.ready;
  }
  view=mounts.get(state.generation)?.view||null;
  for(const [generation,entry] of mounts)entry.panel.hidden=generation!==state.generation;
  paint();
}
async function action(method,params){if(busy||failed||inFlight)return;busy=true;paint();try{await apply(await call(method,params));}catch(error){failed=true;status.textContent=error.message;}finally{busy=false;paint();queueMicrotask(syncForms);}}
objectFind.addEventListener('click',()=>action('workspace.objects',{query:objectSearch.value,family:families.value}));
inspect.addEventListener('click',()=>action('workspace.inspect',{name:objects.value}));
objectSearch.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.objects',{query:objectSearch.value,family:families.value});}});
find.addEventListener('click',()=>action('workspace.search',{query:search.value}));
search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.search',{query:search.value});}});
open.addEventListener('click',()=>action('workspace.open',{name:select.value}));close.addEventListener('click',()=>action('workspace.close',{}));
window.addEventListener('beforeunload',event=>{if([...mounts.values()].some(entry=>entry.view.hasPending())){event.preventDefault();event.returnValue='';}});
action('workspace.snapshot',{});
