/* Embedded form renderer is the reviewed shared __app module, bundled below. */
'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('session');
history.replaceState(null, '', location.pathname);
const root=document.getElementById('workspace'), title=document.createElement('h1'), status=document.createElement('p'), select=document.createElement('select'), open=document.createElement('button'), close=document.createElement('button'), formRoot=document.createElement('section');
const preflight=document.createElement('button'),moduleResult=document.createElement('section');preflight.textContent='Проверить компиляцию BSL';moduleResult.setAttribute('aria-label','Компиляция модуля формы');
const downloadCheck=document.createElement('button');downloadCheck.textContent='Скачать отчёт проверок';
const check=document.createElement('button');check.textContent='Проверить форму без запуска';
const preview=document.createElement('button'),previewResult=document.createElement('section');preview.textContent='Проверить XML формы';previewResult.setAttribute('aria-label','Проверка XML формы');
const search=document.createElement('input'), find=document.createElement('button');search.maxLength=128;search.setAttribute('aria-label','Поиск объявленных форм');find.textContent='Найти формы';
select.setAttribute('aria-label','Объявленная форма'); open.textContent='Открыть форму'; close.textContent='Закрыть сеанс'; status.setAttribute('role','status');
const limitations=document.createElement('ul');limitations.setAttribute('aria-label','Неподдерживаемые возможности формы');
const navigationDiagnostics=document.createElement('ul');navigationDiagnostics.setAttribute('aria-label','Ограничения навигации');
const tabs=document.createElement('nav');tabs.setAttribute('aria-label','Открытые формы');
const explorer=document.createElement('section'),explorerTitle=document.createElement('h2');explorerTitle.textContent='Объекты конфигурации';
const subsystems=document.createElement('select');subsystems.setAttribute('aria-label','Подсистема');
const objectSearch=document.createElement('input'),families=document.createElement('select'),objects=document.createElement('select'),objectFind=document.createElement('button'),inspect=document.createElement('button'),detail=document.createElement('section'),inventoryStatus=document.createElement('p');
objectSearch.maxLength=128;objectSearch.setAttribute('aria-label','Поиск объектов');families.setAttribute('aria-label','Тип объекта');objects.setAttribute('aria-label','Объект конфигурации');
objectFind.textContent='Найти объекты';inspect.textContent='Описание объекта';detail.setAttribute('aria-label','Метаданные выбранного объекта');inventoryStatus.setAttribute('role','status');
explorer.append(explorerTitle,objectSearch,families,subsystems,objectFind,objects,inspect,inventoryStatus,navigationDiagnostics,detail);
root.append(title,status,explorer,search,find,select,check,preview,preflight,downloadCheck,open,close,tabs,limitations,previewResult,moduleResult,formRoot);
const familyLabels={Catalog:'Справочники',Document:'Документы',AccumulationRegister:'Регистры накопления',InformationRegister:'Регистры сведений',Report:'Отчёты',DataProcessor:'Обработки',Subsystem:'Подсистемы',CommonForm:'Общие формы',Form:'Формы',Enum:'Перечисления',Constant:'Константы'};
function caption(name,labels){const label=labels?.[name];return typeof label==='string'&&label&&label!==name?label+' ('+name+')':name;}
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
  downloadCheck.disabled=Boolean(blocked)||!matchingChecks(state);
  open.disabled=check.disabled=preview.disabled=preflight.disabled=blocked||!select.value;
  search.disabled=find.disabled=select.disabled=Boolean(blocked);
  close.disabled=blocked||[...mounts.values()].some(entry=>entry.view.client?.snapshot?.kind!=='closed');
  for(const button of tabs.children)button.disabled=Boolean(blocked);
  for(const control of [objectSearch,families,subsystems,objects,objectFind,inspect,...detail.querySelectorAll('button')])control.disabled=Boolean(blocked);
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
  for(const name of state.forms){const option=document.createElement('option');option.value=name;option.textContent=caption(name,state.form_labels);select.append(option);}
  if(state.forms.includes(previous))select.value=previous;
  if(state.omitted_forms)status.textContent+=' Ещё '+state.omitted_forms+' форм: уточните поиск.';
  limitations.replaceChildren();for(const diagnostic of state.form_diagnostics||[]){const item=document.createElement('li');item.textContent=diagnostic.path+': '+diagnostic.reason;limitations.append(item);}
  const previousObject=objects.value;objects.replaceChildren();
  for(const name of state.objects||[]){const option=document.createElement('option');option.value=name;option.textContent=caption(name,state.object_labels);objects.append(option);}
  if((state.objects||[]).includes(previousObject))objects.value=previousObject;
  families.replaceChildren();for(const family of ['',...(state.object_families||[])]){const option=document.createElement('option');option.value=family;option.textContent=familyLabels[family]||family||'Все типы';families.append(option);}families.value=state.object_family||'';
  subsystems.replaceChildren();for(const name of ['',...(state.subsystems||[])]){const option=document.createElement('option');option.value=name;option.textContent=name?caption(name,state.subsystem_labels):'Все подсистемы и объекты';subsystems.append(option);}subsystems.value=state.object_subsystem||'';
  inventoryStatus.textContent='Показано объектов: '+(state.objects||[]).length+(state.omitted_objects?'; ещё '+state.omitted_objects+', уточните поиск.':'.');
  if(state.omitted_families)inventoryStatus.textContent+=' Других типов: '+state.omitted_families+'. Используйте поиск по полному имени.';
  navigationDiagnostics.replaceChildren();for(const diagnostic of state.navigation_diagnostics||[]){const item=document.createElement('li');item.textContent=diagnostic;navigationDiagnostics.append(item);}if(state.omitted_navigation_diagnostics){const item=document.createElement('li');item.textContent='Других ограничений: '+state.omitted_navigation_diagnostics;navigationDiagnostics.append(item);}
  if(state.omitted_subsystems)inventoryStatus.textContent+=' Других подсистем: '+state.omitted_subsystems+'. Общий список объектов остаётся доступен.';
  detail.replaceChildren();
  if(state.object_detail){
    const data=state.object_detail,heading=document.createElement('h3'),path=document.createElement('p'),notice=document.createElement('p');
    heading.textContent=caption(data.name,{[data.name]:data.title});path.textContent='XML: '+data.source_path;
    notice.textContent=data.execution==='metadata_only'?'Только метаданные: объявленной исполняемой формы нет. CRUD и хранилище не предоставляются.':'Объявленные формы открываются явно и могут выдавать ошибки неподдерживаемых возможностей. CRUD и хранилище не предоставляются.';
    detail.append(heading,path,notice);
    const checkedForms=new Set();
    function addFormChecks(name){
      if(checkedForms.has(name))return;checkedForms.add(name);
      for(const [label,method] of [['Проверить без запуска','workspace.check'],['Проверить XML','workspace.preview'],['Проверить BSL','workspace.preflight']]){
        const button=document.createElement('button');button.textContent=label+' '+caption(name,data.form_labels);button.setAttribute('aria-label',label+' '+name);
        button.addEventListener('click',()=>action(method,{name}));detail.append(button);
      }
    }
    const defaultTitles={DefaultObjectForm:'Форма объекта',DefaultFolderForm:'Форма группы',DefaultListForm:'Форма списка',DefaultChoiceForm:'Форма выбора',DefaultFolderChoiceForm:'Выбор группы',DefaultForm:'Основная форма',DefaultRecordForm:'Форма записи'};
    for(const item of data.default_forms||[]){const button=document.createElement('button');button.textContent=(defaultTitles[item.property]||item.property)+': '+caption(item.name,data.form_labels);button.addEventListener('click',()=>action('workspace.open',{name:item.name}));detail.append(button);addFormChecks(item.name);}
    for(const message of data.default_form_diagnostics||[]){const note=document.createElement('p');note.textContent=message;detail.append(note);}

    for(const name of data.forms){const button=document.createElement('button');button.textContent='Открыть '+caption(name,data.form_labels);button.addEventListener('click',()=>action('workspace.open',{name}));detail.append(button);addFormChecks(name);}
    if(data.omitted_forms){const note=document.createElement('p');note.textContent='Ещё форм: '+data.omitted_forms+'. Уточните общий поиск форм.';detail.append(note);}
  }
  moduleResult.replaceChildren();
  if(state.module_preflight){const data=state.module_preflight,heading=document.createElement('h3'),notice=document.createElement('p'),source=document.createElement('p'),outcome=document.createElement('p');heading.textContent='BSL: '+data.name;notice.textContent='Компиляция и статическая диагностика объявленных обработчиков memory-only формы. Полные связи XML и runtime не проверялись. Исполнения и прав хранения нет.';source.textContent=data.module_path+' · SHA256: '+(data.module_sha256||'нет файла')+' · профиль: '+data.compilation_profile;outcome.textContent=data.status==='compiled'?'Компиляция выполнена. Это не подтверждение запуска или совместимости.':'Компиляция не подтверждена: '+(data.error||'недоступно');moduleResult.append(heading,notice,source,outcome);if(data.handler_names){const audit=data.handler_names,summary=document.createElement('p');summary.textContent=audit.status==='names-checked'?'Имена обработчиков: ссылок '+audit.referenced+'; отсутствуют: '+(audit.missing.length?audit.missing.join(', '):'не найдены')+(audit.omitted_missing?' (ещё '+audit.omitted_missing+')':'')+'. Статические ошибки контекста/сигнатуры: '+((audit.signature_issues||[]).length?audit.signature_issues.join('; '):'не найдены')+(audit.omitted_signature_issues?' (ещё '+audit.omitted_signature_issues+')':'')+'. Конфликты реквизитов: '+((audit.attribute_issues||[]).length?audit.attribute_issues.join('; '):'не найдены')+(audit.omitted_attribute_issues?' (ещё '+audit.omitted_attribute_issues+')':'')+'. Это не проверка значений аргументов, прав или исполнения.':'Имена обработчиков не проверены: '+(audit.error||'недоступно');moduleResult.append(summary);}}
  previewResult.replaceChildren();
  if(state.form_preview){const data=state.form_preview,heading=document.createElement('h3'),notice=document.createElement('p'),source=document.createElement('p');heading.textContent='XML: '+data.name;notice.textContent='Только XML-проекция: модуль и runtime не проверялись, форма не запускалась. Это не подтверждение совместимости.';source.textContent=data.source_path+' · SHA256: '+(data.source_sha256||'нет файла');previewResult.append(heading,notice,source);if(data.counts){const counts=document.createElement('p');counts.textContent='После проекции: реквизиты '+data.counts.attributes+', команды '+data.counts.commands+', элементы '+data.counts.controls;previewResult.append(counts);}for(const diagnostic of data.diagnostics||[]){const note=document.createElement('p');note.textContent=diagnostic.path+': '+diagnostic.reason;previewResult.append(note);}if(data.omitted_diagnostics){const note=document.createElement('p');note.textContent='Других ограничений: '+data.omitted_diagnostics;previewResult.append(note);}}
  const entries=state.open_forms||[];
  for(const [generation,entry] of mounts){
    if(!entries.some(item=>item.generation===generation)){entry.panel.remove();mounts.delete(generation);}
  }
  tabs.replaceChildren();
  for(const item of entries){
    const button=document.createElement('button');button.textContent=caption(item.name,state.form_labels)+(item.active?'':' (закрыта)');
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
function matchingChecks(value){
  const xml=value?.form_preview,module=value?.module_preflight;
  const hash=value=>value===null||(typeof value==='string'&&/^[0-9a-f]{64}$/.test(value));
  return Boolean(xml&&module&&typeof xml.name==='string'&&xml.name===module.name&&hash(xml.source_sha256)&&hash(module.module_sha256)&&xml.source_sha256===module.xml_sha256);
}
function checkReport(value){
  if(!matchingChecks(value))return null;
  const xml=value.form_preview,module=value.module_preflight;
  // Deliberately exclude workspace state, form values, browser session and BSL.
  return {schema:'yadinassi-source-form-check/1',name:xml.name,
    scope:'Static XML projection and BSL preflight only; not runtime or native parity',
    xml:{source_path:xml.source_path,source_sha256:xml.source_sha256,status:xml.status,
      counts:xml.counts,diagnostics:xml.diagnostics,omitted_diagnostics:xml.omitted_diagnostics},
    module:{source_path:module.module_path,source_sha256:module.module_sha256,xml_sha256:module.xml_sha256,
      compilation_profile:module.compilation_profile,status:module.status,error:module.error,handler_names:module.handler_names},
    runtime_checked:false,storage_granted:false,native_parity:false};
}
downloadCheck.addEventListener('click',()=>{
  if(busy||failed||inFlight||state?.kind==='closed')return;
  const report=checkReport(state);if(!report)return;
  let url;
  try{
    url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download='yadinassi-form-check.json';link.click();
  }catch(error){status.textContent='Не удалось скачать отчёт. Проверки сохранены на экране; команды не повторяются.';}
  finally{if(url)setTimeout(()=>URL.revokeObjectURL(url),1000);}
});
async function action(method,params){if(busy||failed||inFlight)return;busy=true;paint();try{await apply(await call(method,params));}catch(error){failed=true;status.textContent=error.message;}finally{busy=false;paint();queueMicrotask(syncForms);}}
objectFind.addEventListener('click',()=>action('workspace.objects',{query:objectSearch.value,family:families.value,subsystem:subsystems.value}));
inspect.addEventListener('click',()=>action('workspace.inspect',{name:objects.value}));
objectSearch.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.objects',{query:objectSearch.value,family:families.value,subsystem:subsystems.value});}});
find.addEventListener('click',()=>action('workspace.search',{query:search.value}));
search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.search',{query:search.value});}});
check.addEventListener('click',()=>action('workspace.check',{name:select.value}));
preflight.addEventListener('click',()=>action('workspace.preflight',{name:select.value}));
preview.addEventListener('click',()=>action('workspace.preview',{name:select.value}));
open.addEventListener('click',()=>action('workspace.open',{name:select.value}));close.addEventListener('click',()=>action('workspace.close',{}));
window.addEventListener('beforeunload',event=>{if([...mounts.values()].some(entry=>entry.view.hasPending())){event.preventDefault();event.returnValue='';}});
action('workspace.snapshot',{});
