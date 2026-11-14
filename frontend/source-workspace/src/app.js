/* Embedded form renderer is the reviewed shared __app module, bundled below. */
'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('session');
history.replaceState(null, '', location.pathname);
const root=document.getElementById('workspace'), title=document.createElement('h1'), status=document.createElement('p'), select=document.createElement('select'), open=document.createElement('button'), close=document.createElement('button'), formRoot=document.createElement('section');
const search=document.createElement('input'), find=document.createElement('button');search.maxLength=128;search.setAttribute('aria-label','Поиск объявленных форм');find.textContent='Найти формы';
select.setAttribute('aria-label','Объявленная форма'); open.textContent='Открыть форму'; close.textContent='Закрыть сеанс'; status.setAttribute('role','status');
root.append(title,status,search,find,select,open,close,formRoot);
let id=0,busy=false,view=null,state=null,failed=false;
async function call(method,params={}) {
  const response=await fetch('/rpc',{method:'POST',headers:{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':token||''},body:JSON.stringify({jsonrpc:'2.0',id:++id,method,params})+'\n'});
  if(!response.ok)throw Error('Связь потеряна. Команда не повторяется автоматически.');
  const reply=await response.json();if(reply.error)throw Error('Запрос отклонён');return reply.result;
}
function paint(){
  const active=Boolean(view && view.client?.snapshot?.kind!=='closed');
  open.disabled=busy||failed||!state||state.kind==='closed'||active||!select.value;
  search.disabled=find.disabled=busy||failed||active||state?.kind==='closed';
  select.disabled=busy||failed||active||state?.kind==='closed';close.disabled=busy||failed||!state||state.kind==='closed'||active;
}
async function apply(reply){
  if(reply.protocol!=='yadinassi-source-workspace/1')throw Error('Неизвестный протокол');state=reply.state;
  title.textContent=state.name+' · Source workspace';status.textContent=state.error|| (state.kind==='closed'?'Сеанс закрыт':'Формы в памяти: без сохранения объектов базы и без заявления о совместимости с 1С.');
  const previous=select.value;select.replaceChildren();
  for(const name of state.forms){const option=document.createElement('option');option.value=name;option.textContent=name;select.append(option);}
  if(state.forms.includes(previous))select.value=previous;
  if(state.omitted_forms)status.textContent+=' Ещё '+state.omitted_forms+' форм: уточните поиск.';
  if(state.active && (!view || view.generation!==state.generation)){
    formRoot.replaceChildren();const generation=state.generation;
    view=__app.mountForm(window,formRoot,{transport:request=>call('workspace.form',{generation,request}),onChange:()=>paint()});view.generation=generation;
    await view.ready;
  }
  paint();
}
async function action(method,params){if(busy||failed)return;busy=true;paint();try{await apply(await call(method,params));}catch(error){failed=true;status.textContent=error.message;}finally{busy=false;paint();}}
find.addEventListener('click',()=>action('workspace.search',{query:search.value}));
search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.search',{query:search.value});}});
open.addEventListener('click',()=>action('workspace.open',{name:select.value}));close.addEventListener('click',()=>action('workspace.close',{}));
window.addEventListener('beforeunload',event=>{if(view?.hasPending()){event.preventDefault();event.returnValue='';}});
action('workspace.snapshot',{});
