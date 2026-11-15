import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const code=readFileSync(new URL('../src/app.js',import.meta.url),'utf8');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.listeners={};this.value='';this.textContent='';}
 append(...nodes){this.children.push(...nodes);if(this.tag==='select'&&!this.value&&nodes[0])this.value=nodes[0].value;}
 replaceChildren(...nodes){this.children=[];this.value='';this.append(...nodes);}
 setAttribute(k,v){this.attributes[k]=v;}
 addEventListener(k,v){this.listeners[k]=v;}
 click(){this.clicked=true;}
 querySelectorAll(tag){return this.children.flatMap(x=>[...(x.tag===tag?[x]:[]),...x.querySelectorAll(tag)]);}
}
async function harness(state,extras={}){
 const elements=[],root=new Element('main'),requests=[];
 const document={getElementById:()=>root,createElement:tag=>{const e=new Element(tag);elements.push(e);return e;}};
 const context=vm.createContext({document,location:{hash:'#session=secret',pathname:'/'},history:{replaceState(){}},URLSearchParams,queueMicrotask,window:{addEventListener(){}},fetch:async(_url,options)=>{requests.push(JSON.parse(options.body));return{ok:true,json:async()=>({result:{protocol:'yadinassi-source-workspace/1',state}})};},...extras});
 vm.runInContext(code,context);await new Promise(resolve=>setImmediate(resolve));
 return{elements,requests,context,get:label=>elements.find(x=>x.attributes['aria-label']===label)};
}
const state={kind:'workspace',name:'Demo',forms:['CommonForm.Main'],objects:['Catalog.A','Catalog.B'],object_labels:{'Catalog.A':'Товары','Catalog.B':'Товары'},form_labels:{'CommonForm.Main':'Главная'},object_families:['Catalog','Document'],subsystems:['Subsystem.Reference'],subsystem_labels:{'Subsystem.Reference':'Нормативная информация'},form_diagnostics:[],open_forms:[]};
test('localized labels preserve canonical values and distinguish equal captions',async()=>{
 const h=await harness(state),objects=h.get('Объект конфигурации');
 assert.deepEqual(objects.children.map(x=>x.value),['Catalog.A','Catalog.B']);
 assert.deepEqual(objects.children.map(x=>x.textContent),['Товары (Catalog.A)','Товары (Catalog.B)']);
 assert.equal(h.get('Объявленная форма').children[0].textContent,'Главная (CommonForm.Main)');
 assert.equal(h.get('Тип объекта').children[1].textContent,'Справочники');
});
test('subsystem filter sends canonical declaration, not presentation',async()=>{
 const h=await harness(state);h.get('Подсистема').value='Subsystem.Reference';
 h.elements.find(x=>x.textContent==='Найти объекты').listeners.click();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(h.requests.at(-1).method,'workspace.objects');assert.equal(h.requests.at(-1).params.subsystem,'Subsystem.Reference');
});
test('untrusted labels remain text and missing labels use canonical fallback',async()=>{
 const h=await harness({...state,object_labels:{'Catalog.A':'<img src=x onerror=alert(1)>'}}),objects=h.get('Объект конфигурации');
 assert.equal(objects.children[0].textContent,'<img src=x onerror=alert(1)> (Catalog.A)');
 assert.equal(objects.children[0].children.length,0);assert.equal(objects.children[1].textContent,'Catalog.B');
});
test('closed workspace also disables new subsystem selector',async()=>{
 const h=await harness({...state,kind:'closed'});assert.equal(h.get('Подсистема').disabled,true);
});
test('membership diagnostics remain visible alongside empty filtered inventory',async()=>{
 const h=await harness({...state,objects:[],navigation_diagnostics:['Subsystem.Reference: Unknown source member']});
 assert.equal(h.get('Ограничения навигации').children[0].textContent,'Subsystem.Reference: Unknown source member');
});
test('retained tabs use supplied labels even when current search excludes form',async()=>{
 const h=await harness({...state,forms:[],open_forms:[{generation:3,name:'CommonForm.Main',active:false}]});
 assert.equal(h.get('Открытые формы').children[0].textContent,'Главная (CommonForm.Main) (закрыта)');
});
test('declared default action opens canonical target explicitly, with diagnostic text',async()=>{
 const h=await harness({...state,object_detail:{name:'Catalog.A',source_path:'Catalogs/A.xml',execution:'explicit_form_selection',forms:[],form_labels:{'CommonForm.Main':'Главная'},default_forms:[{property:'DefaultListForm',name:'CommonForm.Main'}],default_form_diagnostics:['DefaultObjectForm: unavailable']}});
 assert.equal(h.requests.length,1);
 const button=h.get('Метаданные выбранного объекта').children.find(x=>x.tag==='button'&&x.textContent==='Форма списка: Главная (CommonForm.Main)');assert.equal(button.textContent,'Форма списка: Главная (CommonForm.Main)');
 button.listeners.click();await new Promise(resolve=>setImmediate(resolve));assert.equal(h.requests.at(-1).method,'workspace.open');assert.equal(h.requests.at(-1).params.name,'CommonForm.Main');
 assert.ok(h.get('Метаданные выбранного объекта').children.some(x=>x.textContent==='DefaultObjectForm: unavailable'));
});
test('closed workspace cannot activate default form buttons',async()=>{
 const h=await harness({...state,kind:'closed',object_detail:{name:'Catalog.A',forms:[],default_forms:[{property:'DefaultObjectForm',name:'Catalog.A.Form.Card'}]}});
 assert.equal(h.get('Метаданные выбранного объекта').children.find(x=>x.tag==='button').disabled,true);
});
test('XML preview uses read-only RPC and visibly denies runtime validation',async()=>{
 const h=await harness({...state,form_preview:{name:'CommonForm.Main',source_path:'CommonForms/Main/Ext/Form.xml',source_sha256:'abc',counts:{attributes:1,commands:2,controls:3},diagnostics:[{path:'Items.Logo',reason:'Control unavailable'}]}});
 h.elements.find(x=>x.textContent==='Проверить XML формы').listeners.click();await new Promise(resolve=>setImmediate(resolve));assert.equal(h.requests.at(-1).method,'workspace.preview');assert.equal(h.requests.at(-1).params.name,'CommonForm.Main');
 const text=h.get('Проверка XML формы').children.map(x=>x.textContent).join('\n');assert.match(text,/модуль и runtime не проверялись/);assert.match(text,/SHA256: abc/);assert.match(text,/Items.Logo: Control unavailable/);
});
test('XML preview button is disabled after workspace closes',async()=>{const h=await harness({...state,kind:'closed'});assert.equal(h.elements.find(x=>x.textContent==='Проверить XML формы').disabled,true);});
test('module preflight sends exact selected form, is blocked when closed',async()=>{
 const h=await harness(state),button=h.elements.find(e=>e.textContent==='Проверить компиляцию BSL');
 await button.listeners.click();assert.equal(h.requests.at(-1).method,'workspace.preflight');assert.equal(h.requests.at(-1).params.name,'CommonForm.Main');
 const closed=await harness({...state,kind:'closed'});assert.equal(closed.elements.find(e=>e.textContent==='Проверить компиляцию BSL').disabled,true);
});
test('module compile diagnostic remains literal and does not claim execution',async()=>{
 const h=await harness({...state,module_preflight:{name:'CommonForm.Main',module_path:'Main/Module.bsl',module_sha256:'abc',compilation_profile:'standalone',status:'unavailable',error:'<script>bad()</script>'}});
 const panel=h.get('Компиляция модуля формы');assert.ok(panel.children[1].textContent.includes('runtime не проверялись'));assert.ok(panel.children[3].textContent.includes('<script>bad()</script>'));assert.ok(panel.children[3].textContent.startsWith('Компиляция не подтверждена'));
});
test('change-event reply reaches parent before workspace snapshot activates child',async()=>{
 const mounts=[],requests=[],root=new Element('main');let active=1,release;
 const source={...state,active:true,generation:1,open_forms:[{name:'CommonForm.Main',generation:1,active:true}]};
 const document={getElementById:()=>root,createElement:tag=>new Element(tag)};
 const context=vm.createContext({document,location:{hash:'#session=x',pathname:'/'},history:{replaceState(){}},URLSearchParams,queueMicrotask,window:{addEventListener(){}},
  __app:{mountForm(_window,_panel,options){mounts.push(options);return{ready:Promise.resolve(),client:{snapshot:{kind:'form'}},repaint(){},hasPending(){return false;}};}},
  fetch:async(_url,options)=>{const req=JSON.parse(options.body);requests.push(req);
   if(req.method==='workspace.form'){await new Promise(resolve=>{release=resolve;});active=2;return{ok:true,json:async()=>({result:{result:{error:null,parentReceipt:true}}})};}
   return{ok:true,json:async()=>({result:{protocol:'yadinassi-source-workspace/1',state:{...source,generation:active,open_forms:active===1?source.open_forms:[...source.open_forms,{name:'CommonForm.Child',generation:2,active:true}]}}})};}
 });
 vm.runInContext(code,context);await new Promise(resolve=>setImmediate(resolve));
 const parent=mounts[0];const pending=parent.transport({method:'form.event',params:{event:'change'}});
 parent.onChange();await new Promise(resolve=>setImmediate(resolve));assert.equal(requests.length,2);assert.equal(mounts.length,1);
 release();const reply=await pending;assert.equal(reply.result.parentReceipt,true);
 parent.onChange();await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
 assert.equal(mounts.length,2);assert.equal(requests.filter(r=>r.method==='workspace.form').length,1);
 assert.equal(requests.at(-1).method,'workspace.snapshot');
 await assert.rejects(parent.transport({method:'form.event',params:{event:'change'}}),/Неактивная форма/);
 assert.equal(requests.filter(r=>r.method==='workspace.form').length,1);
});
test('static handler audit is text and does not claim runtime binding',async()=>{
 const h=await harness({...state,module_preflight:{name:'CommonForm.Main',module_path:'Main/Module.bsl',module_sha256:'abc',compilation_profile:'standalone',status:'compiled',handler_names:{status:'names-checked',referenced:3,missing:['<img onerror=bad()>'],omitted_missing:2}}});
 const summary=h.elements.find(x=>x.textContent.includes('Имена обработчиков: ссылок'));
 assert.ok(summary);assert.ok(summary.textContent.includes('<img onerror=bad()>'));assert.ok(summary.textContent.includes('ещё 2'));assert.ok(summary.textContent.includes('не проверка значений аргументов'));assert.equal(summary.children.length,0);
 assert.deepEqual(h.requests.map(x=>x.method),['workspace.snapshot']);
});
test('unavailable XML name audit remains distinct from successful compilation',async()=>{
 const h=await harness({...state,module_preflight:{name:'CommonForm.Main',module_path:'Main/Module.bsl',module_sha256:'abc',compilation_profile:'standalone',status:'compiled',handler_names:{status:'unavailable',error:'XML missing'}}});
 assert.ok(h.elements.some(x=>x.textContent.startsWith('Компиляция выполнена')));
 assert.ok(h.elements.some(x=>x.textContent==='Имена обработчиков не проверены: XML missing'));
});
test('static signature diagnostics remain text without asserting execution',async()=>{
 const h=await harness({...state,module_preflight:{name:'CommonForm.Main',module_path:'Main/Module.bsl',module_sha256:'abc',compilation_profile:'standalone',status:'compiled',handler_names:{status:'names-checked',referenced:1,missing:[],signature_issues:['<script>bad()</script> requires client procedure(1)'],omitted_signature_issues:3}}});
 const summary=h.elements.find(x=>x.textContent.includes('Статические ошибки контекста/сигнатуры'));
 assert.ok(summary.textContent.includes('<script>bad()</script>'));assert.ok(summary.textContent.includes('ещё 3'));assert.equal(summary.children.length,0);assert.ok(summary.textContent.includes('не проверка значений аргументов, прав или исполнения'));
});
test('retained scalar attribute conflicts are shown as text, not runtime proof',async()=>{
 const h=await harness({...state,module_preflight:{name:'CommonForm.Main',module_path:'Main/Module.bsl',module_sha256:'abc',compilation_profile:'standalone',status:'compiled',handler_names:{status:'names-checked',referenced:0,missing:[],attribute_issues:['<img> shadows module declaration'],omitted_attribute_issues:4}}});
 const summary=h.elements.find(x=>x.textContent.includes('Конфликты реквизитов'));
 assert.ok(summary.textContent.includes('<img> shadows module declaration'));assert.ok(summary.textContent.includes('ещё 4'));assert.equal(summary.children.length,0);
});
const objectDetail={name:'Catalog.A',title:'Товары',source_path:'Catalogs/A.xml',execution:'declared_forms',forms:['Catalog.A.Form.Card'],form_labels:{'Catalog.A.Form.Card':'Карточка'},default_forms:[{property:'DefaultObjectForm',name:'Catalog.A.Form.Card'},{property:'DefaultListForm',name:'CommonForm.Main'}],default_form_diagnostics:[]};
test('object form XML probe sends canonical target without opening a form',async()=>{
 const h=await harness({...state,object_detail:objectDetail});
 await h.get('Проверить XML Catalog.A.Form.Card').listeners.click();
 assert.equal(h.requests.at(-1).method,'workspace.preview');assert.equal(h.requests.at(-1).params.name,'Catalog.A.Form.Card');assert.ok(!h.requests.some(r=>r.method==='workspace.open'));
});
test('explicit default form outside main selector can be preflighted',async()=>{
 const h=await harness({...state,forms:[],object_detail:objectDetail});
 await h.get('Проверить BSL CommonForm.Main').listeners.click();
 assert.equal(h.requests.at(-1).method,'workspace.preflight');assert.equal(h.requests.at(-1).params.name,'CommonForm.Main');assert.equal(h.requests.length,2);
});
test('duplicate default and child form share one diagnostic button per operation',async()=>{
 const h=await harness({...state,object_detail:objectDetail});
 for(const label of ['Проверить XML','Проверить BSL'])assert.equal(h.elements.filter(e=>e.attributes['aria-label']===label+' Catalog.A.Form.Card').length,1);
 assert.ok(h.get('Проверить XML Catalog.A.Form.Card').textContent.includes('Карточка'));
});
test('metadata-only and closed object cards do not expose live check actions',async()=>{
 const empty=await harness({...state,object_detail:{...objectDetail,forms:[],default_forms:[],execution:'metadata_only'}});
 assert.ok(!empty.elements.some(e=>e.attributes['aria-label']==='Проверить XML Catalog.A.Form.Card'));
 const closed=await harness({...state,kind:'closed',object_detail:objectDetail});
 assert.equal(closed.get('Проверить XML Catalog.A.Form.Card').disabled,true);assert.equal(closed.get('Проверить BSL CommonForm.Main').disabled,true);
});
test('untrusted object form caption is literal while target stays canonical',async()=>{
 const h=await harness({...state,object_detail:{...objectDetail,form_labels:{'Catalog.A.Form.Card':'<img onerror=bad()>'}}});
 const button=h.get('Проверить BSL Catalog.A.Form.Card');assert.ok(button.textContent.includes('<img onerror=bad()>'));assert.equal(button.children.length,0);
 await button.listeners.click();assert.equal(h.requests.at(-1).params.name,'Catalog.A.Form.Card');
});
test('combined form check sends one readonly request for selected canonical form',async()=>{
 const h=await harness(state);await h.elements.find(e=>e.textContent==='Проверить форму без запуска').listeners.click();
 assert.deepEqual(h.requests.map(r=>r.method),['workspace.snapshot','workspace.check']);assert.equal(h.requests.at(-1).params.name,'CommonForm.Main');
});
test('object combined check also uses one canonical request without automatic open',async()=>{
 const h=await harness({...state,object_detail:objectDetail});await h.get('Проверить без запуска Catalog.A.Form.Card').listeners.click();
 assert.equal(h.requests.at(-1).method,'workspace.check');assert.equal(h.requests.at(-1).params.name,'Catalog.A.Form.Card');assert.equal(h.requests.length,2);
});
test('closed and empty selection disable combined checks',async()=>{
 for(const extra of [{kind:'closed'}, {forms:[]}]){const h=await harness({...state,...extra});assert.equal(h.elements.find(e=>e.textContent==='Проверить форму без запуска').disabled,true);}
 const h=await harness({...state,kind:'closed',object_detail:objectDetail});assert.equal(h.get('Проверить без запуска Catalog.A.Form.Card').disabled,true);
});
const checkedState={...state,form_preview:{name:'CommonForm.Main',source_path:'Main/Form.xml',source_sha256:'a'.repeat(64),status:'projected',counts:{controls:2},diagnostics:[],omitted_diagnostics:0},module_preflight:{name:'CommonForm.Main',module_path:'Main/Module.bsl',module_sha256:'d'.repeat(64),xml_sha256:'a'.repeat(64),compilation_profile:'standalone',status:'compiled',error:null,handler_names:{status:'names-checked',missing:[]}}};
test('check report downloads local JSON without RPC, session or form data',async()=>{
 let captured,revoked;const extras={Blob:class{constructor(parts,options){captured={parts,options};}},URL:{createObjectURL(){return 'blob:local';},revokeObjectURL(url){revoked=url;}},setTimeout:fn=>fn()};
 const h=await harness({...checkedState,privateValue:'do-not-export'},extras);
 const button=h.elements.find(e=>e.textContent==='Скачать отчёт проверок');assert.equal(button.disabled,false);button.listeners.click();
 const report=JSON.parse(captured.parts.join(''));assert.equal(report.schema,'yadinassi-source-form-check/1');assert.equal(report.xml.source_sha256,'a'.repeat(64));assert.equal(report.module.source_sha256,'d'.repeat(64));assert.equal(report.runtime_checked,false);assert.equal(report.native_parity,false);
 assert.ok(!JSON.stringify(report).includes('secret'));assert.ok(!JSON.stringify(report).includes('do-not-export'));assert.deepEqual(h.requests.map(r=>r.method),['workspace.snapshot']);
 const link=h.elements.find(e=>e.tag==='a');assert.equal(link.download,'yadinassi-form-check.json');assert.equal(link.clicked,true);assert.equal(revoked,'blob:local');
});
test('report rejects mismatched names/hashes and absent checks',async()=>{
 for(const source of [state,{...checkedState,module_preflight:{...checkedState.module_preflight,name:'Other'}},{...checkedState,module_preflight:{...checkedState.module_preflight,xml_sha256:'different'}}]){
  let created=false;const h=await harness(source,{URL:{createObjectURL(){created=true;}}});const button=h.elements.find(e=>e.textContent==='Скачать отчёт проверок');assert.equal(button.disabled,true);button.listeners.click();assert.equal(created,false);
 }
});
test('failed probes remain exportable as failures, never converted into success',async()=>{
 let captured;const h=await harness({...checkedState,module_preflight:{...checkedState.module_preflight,status:'unavailable',error:'<script>syntax</script>',handler_names:null}},{Blob:class{constructor(parts){captured=parts.join('');}},URL:{createObjectURL(){return 'blob:x';},revokeObjectURL(){}},setTimeout:fn=>fn()});
 h.elements.find(e=>e.textContent==='Скачать отчёт проверок').listeners.click();const report=JSON.parse(captured);assert.equal(report.module.status,'unavailable');assert.equal(report.module.error,'<script>syntax</script>');assert.equal(report.xml.status,'projected');
});
test('closed workspace and download failure never trigger remote retry',async()=>{
 let created=false;const closed=await harness({...checkedState,kind:'closed'},{URL:{createObjectURL(){created=true;}}});const button=closed.elements.find(e=>e.textContent==='Скачать отчёт проверок');assert.equal(button.disabled,true);button.listeners.click();assert.equal(created,false);
 const h=await harness(checkedState,{Blob:class{constructor(){throw Error('blocked');}}});h.elements.find(e=>e.textContent==='Скачать отчёт проверок').listeners.click();assert.ok(h.elements.some(e=>e.textContent.startsWith('Не удалось скачать отчёт')));assert.equal(h.requests.length,1);
});
test('undefined and malformed source digests cannot create a bound report',async()=>{
 for(const digest of [undefined,'abc','A'.repeat(64)]){
  const h=await harness({...checkedState,form_preview:{...checkedState.form_preview,source_sha256:digest},module_preflight:{...checkedState.module_preflight,xml_sha256:digest}});
  assert.equal(h.elements.find(e=>e.textContent==='Скачать отчёт проверок').disabled,true);
 }
});
test('object batch check uses one canonical RPC and never opens forms',async()=>{
 const h=await harness({...state,object_detail:objectDetail});await h.elements.find(e=>e.textContent==='Проверить формы объекта без запуска (до 4)').listeners.click();
 assert.equal(h.requests.at(-1).method,'workspace.checkObject');assert.equal(h.requests.at(-1).params.name,'Catalog.A');assert.equal(h.requests.length,2);
});
test('batch summary retains failed checks and omissions as literal text',async()=>{
 const h=await harness({...state,object_detail:objectDetail,object_checks:{name:'Catalog.A',uninspected_targets:3,inventory_omitted_forms:2,forms:[{name:'Catalog.A.Form.Card',xml_status:'unavailable',module_status:'compiled',static_issues:1,xml_error:'<script>bad()</script>'}]}});
 const panel=h.get('Проверки форм объекта');assert.ok(panel.children[0].textContent.includes('Не проверено целей: 3'));assert.ok(panel.children[1].textContent.includes('<script>bad()</script>'));assert.equal(panel.children[1].children.length,0);
});
test('batch action is absent for metadata-only objects and disabled when closed',async()=>{
 const empty=await harness({...state,object_detail:{...objectDetail,forms:[],default_forms:[]}});assert.ok(!empty.elements.some(e=>e.textContent==='Проверить формы объекта без запуска (до 4)'));
 const closed=await harness({...state,kind:'closed',object_detail:objectDetail});assert.equal(closed.elements.find(e=>e.textContent==='Проверить формы объекта без запуска (до 4)').disabled,true);
 const other=await harness({...state,object_detail:objectDetail,object_checks:{name:'Catalog.B'}});assert.equal(other.get('Проверки форм объекта'),undefined);
});
test('batch unavailable handler audit remains visible alongside successful compilation',async()=>{
 const h=await harness({...state,object_detail:objectDetail,object_checks:{name:'Catalog.A',uninspected_targets:0,inventory_omitted_forms:0,forms:[{name:'Catalog.A.Form.Card',xml_status:'projected',module_status:'compiled',static_issues:0,audit_status:'unavailable',audit_error:'duplicate event'}]}});
 const text=h.get('Проверки форм объекта').children[1].textContent;assert.ok(text.includes('аудит обработчиков: unavailable (duplicate event)'));assert.ok(text.includes('BSL: compiled'));
});
