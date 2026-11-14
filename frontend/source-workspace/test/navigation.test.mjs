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
 querySelectorAll(tag){return this.children.flatMap(x=>[...(x.tag===tag?[x]:[]),...x.querySelectorAll(tag)]);}
}
async function harness(state){
 const elements=[],root=new Element('main'),requests=[];
 const document={getElementById:()=>root,createElement:tag=>{const e=new Element(tag);elements.push(e);return e;}};
 const context=vm.createContext({document,location:{hash:'#session=secret',pathname:'/'},history:{replaceState(){}},URLSearchParams,queueMicrotask,window:{addEventListener(){}},fetch:async(_url,options)=>{requests.push(JSON.parse(options.body));return{ok:true,json:async()=>({result:{protocol:'yadinassi-source-workspace/1',state}})};}});
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
 const button=h.get('Метаданные выбранного объекта').children.find(x=>x.tag==='button');assert.equal(button.textContent,'Форма списка: Главная (CommonForm.Main)');
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
