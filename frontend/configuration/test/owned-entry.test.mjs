import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL,ApplicationClient,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from './application-fixtures.mjs';
import {environment,all} from '../../form/test/fake-dom.mjs';
const state=()=>({kind:'application',lifecycle:'running',messages:[],exitWarning:'',title:'Draft',entries:[{id:1,title:'Operation draft',kind:'form'},{id:2,title:'Private details',kind:'owned-form'}],sessions:[],active:null,uncertain:false,catalog:null});
const reply=(request,s=state())=>({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state:s,error:null,session:null,form:null,updates:[]}});
test('owned-only entry remains in inventory but has no navigation button',async()=>{
 const env=environment();const app=mountApplication(env,env.document.root,async r=>reply(r));await app.ready;
 const nav=all(env.document.root).find(n=>n.getAttribute?.('aria-label')==='Declared forms');
 assert.equal(nav.children.length,1);assert.equal(nav.children[0].textContent,'Operation draft');
 assert.equal(app.client.state.entries.length,2);
});
test('both direct opening methods fail before transport and do not poison client',async()=>{
 const calls=[];const client=new ApplicationClient(async r=>{calls.push(r);return reply(r);});await client.request('application.hello',{});
 for(const method of ['application.open','application.openRecord'])await assert.rejects(client.request(method,{entry:2,request:'private',record:'record-1'}),e=>e.code==='open_failed'&&e.preDispatch);
 assert.equal(calls.length,1);assert.equal(client.terminal,false);
 await client.request('application.snapshot',{});assert.equal(calls.length,2);
});
test('owned-only session requires a real owner and participates in closed graph validation',()=>{
 const s=state();s.sessions=[{id:'form-1',entry:1,title:'Owner',owner:null,blocked:true},{id:'form-2',entry:2,title:'Child',owner:'form-1',blocked:false}];s.active='form-2';
 validateApplicationReply(reply({id:1},s),{id:1,method:'application.snapshot'},null);
 for(const owner of [null,'form-9','form-2']){
  const bad=structuredClone(s);bad.sessions[1].owner=owner;
  assert.throws(()=>validateApplicationReply(reply({id:1},bad),{id:1,method:'application.snapshot'},null));
 }
 const bad=state();bad.entries[1].kind='private-form';assert.throws(()=>validateApplicationReply(reply({id:1},bad),{id:1},null));
});
