/* Embedded form renderer is the reviewed shared __app module, bundled below. */
'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('session');
history.replaceState(null, '', location.pathname);
const root=document.getElementById('workspace'), title=document.createElement('h1'), status=document.createElement('p'), select=document.createElement('select'), open=document.createElement('button'), close=document.createElement('button'), formRoot=document.createElement('section');
const search=document.createElement('input'), find=document.createElement('button');search.maxLength=128;search.setAttribute('aria-label','Поиск объявленных форм');find.textContent='Найти формы';
select.setAttribute('aria-label','Объявленная форма'); open.textContent='Открыть форму'; close.textContent='Закрыть сеанс'; status.setAttribute('role','status');
const limitations=document.createElement('ul');limitations.setAttribute('aria-label','Неподдерживаемые возможности формы');
const tabs=document.createElement('nav');tabs.setAttribute('aria-label','Открытые формы');
root.append(title,status,search,find,select,open,close,tabs,limitations,formRoot);
let id=0,busy=false,view=null,state=null,failed=false,inFlight=0;
const mounts=new Map();
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
      onChange:()=>paint()});
    mounts.set(generation,{panel,view:mount});await mount.ready;
  }
  view=mounts.get(state.generation)?.view||null;
  for(const [generation,entry] of mounts)entry.panel.hidden=generation!==state.generation;
  paint();
}
async function action(method,params){if(busy||failed||inFlight)return;busy=true;paint();try{await apply(await call(method,params));}catch(error){failed=true;status.textContent=error.message;}finally{busy=false;paint();}}
find.addEventListener('click',()=>action('workspace.search',{query:search.value}));
search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.search',{query:search.value});}});
open.addEventListener('click',()=>action('workspace.open',{name:select.value}));close.addEventListener('click',()=>action('workspace.close',{}));
window.addEventListener('beforeunload',event=>{if([...mounts.values()].some(entry=>entry.view.hasPending())){event.preventDefault();event.returnValue='';}});
action('workspace.snapshot',{});
