import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL,ApplicationClient,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from './application-fixtures.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
const token='records-'+('a'.repeat(32))+'-1',next='records-page-'+('b'.repeat(32));
const catalog=()=>({entry:1,version:1,rows:Array.from({length:50},(_,i)=>({key:`record-${i+1}`,code:String(i),description:'Item',deletionMark:false})),navigation:{snapshot:token,page:1,pages:2,total:51,query:'',order:'code',previous:null,next}});
const state=c=>({kind:'application',lifecycle:'forms',messages:[],exitWarning:'',title:'Pages',entries:[{id:1,title:'Products',kind:'catalog-object'}],sessions:[],active:null,uncertain:false,catalog:c});
const reply=(r,c)=>({jsonrpc:'2.0',id:r.id,result:{protocol:APPLICATION_PROTOCOL,state:state(c),error:null,session:null,form:null}});
const command=(env,text)=>buttons(env.document).find(n=>n.textContent===text);
test('page projection validates totals topology and closed cursor schema',()=>{
 const r={id:1,method:'application.hello',params:{}};const c=catalog();validateApplicationReply(reply(r,c),r,null);
 for(const patch of [{total:50},{page:0},{previous:next},{query:false},{next:'arbitrary'}, {extra:true}])assert.throws(()=>validateApplicationReply(reply(r,{...c,navigation:{...c.navigation,...patch}}),r,null));
});
test('retired snapshot or cursor is refused before dispatch',async()=>{
 const calls=[],c=catalog(),client=new ApplicationClient(async r=>{calls.push(r);return reply(r,c);});
 await client.request('application.hello',{});
 for(const params of [{entry:1,snapshot:'old',cursor:next},{entry:1,snapshot:token,cursor:null},{entry:1,snapshot:token,cursor:'other'}])await assert.rejects(client.request('application.catalogPage',params));
 assert.equal(calls.length,1);assert.equal(client.terminal,false);
});
test('next and search send only current opaque navigation plus bounded query',async()=>{
 const env=environment(),calls=[],c=catalog();const app=mountApplication(env,env.document.root,async r=>{calls.push(r);return reply(r,c);});await app.ready;
 assert.equal(command(env,'Previous records').disabled,true);
 command(env,'Next records').emit('click');await app.client.tail;
 assert.deepEqual(calls.at(-1).params,{entry:1,snapshot:token,cursor:next});
 const input=all(env.document.root).find(n=>n.getAttribute?.('aria-label')==='Search records');input.value='needle';input.emit('input');input.emit('keydown',{key:'Enter',preventDefault(){}});await app.client.tail;
 assert.deepEqual(calls.at(-1).params,{entry:1,snapshot:token,query:'needle',order:'code'});
});
test('page change retires previous row selection',async()=>{
 const env=environment();let c=catalog();const app=mountApplication(env,env.document.root,async r=>{if(r.method==='application.catalogPage')c={...c,version:2,rows:[{key:'record-51',code:'51',description:'Last',deletionMark:false}],navigation:{...c.navigation,page:2,previous:'records-page-'+('c'.repeat(32)),next:null}};return reply(r,c);});await app.ready;
 all(env.document.root).find(n=>n.dataset.recordKey==='record-1').emit('click');assert.equal(command(env,'Open selected').disabled,false);
 command(env,'Next records').emit('click');await app.client.tail;await Promise.resolve();assert.equal(command(env,'Open selected').disabled,true);
});
