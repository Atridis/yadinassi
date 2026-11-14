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
