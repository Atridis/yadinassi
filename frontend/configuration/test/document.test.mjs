import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL, ApplicationClient, validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from './application-fixtures.mjs';
import {environment, all, buttons} from '../../form/test/fake-dom.mjs';
import {reply as formReply} from '../../form/test/fixtures.mjs';
const row = () => ({key:'record-1',number:'00001',date:'2026-11-10 12:30:00',deletionMark:false});
const state = extra => ({kind:'application',lifecycle:'forms',messages:[],exitWarning:'',title:'Orders',entries:[{id:1,title:'Orders',kind:'document-object'}],sessions:[],active:null,uncertain:false,catalog:{entry:1,version:1,rows:[row()]},...extra});
const reply = (request,value=state(),extra={}) => ({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state:value,error:null,session:null,form:null,...extra}});

test('document list admits only bounded typed number date and opaque key',()=>{
  const request={id:1,method:'application.hello',params:{}};
  assert.equal(validateApplicationReply(reply(request),request,null).state.catalog.rows.length,1);
  for(const bad of [
    {...row(),number:'1234567890'}, {...row(),date:'2026-11-10'}, {...row(),date:'2026-11-10 12:30:00.001'},
    {...row(),code:'1'}, {...row(),posted:true}, {...row(),deletionMark:'false'},
    {...row(),key:'550e8400-e29b-41d4-a716-446655440000'},
  ]) assert.throws(()=>validateApplicationReply(reply(request,state({catalog:{entry:1,version:1,rows:[bad]}})),request,null));
});
test('catalog and document record projections cannot cross declared kinds',()=>{
  const request={id:1,method:'application.hello',params:{}};
  assert.throws(()=>validateApplicationReply(reply(request,state({entries:[{id:1,title:'Catalog',kind:'catalog-object'}]})),request,null));
  assert.throws(()=>validateApplicationReply(reply(request,state({catalog:{entry:1,version:1,rows:[{key:'record-1',code:'1',description:'No',deletionMark:false}]}})),request,null));
});
test('document toolbar opens explicit new and selected records, no per-row buttons',async()=>{
  const env=environment(),requests=[];let value=state(),n=0;
  const app=mountApplication(env,env.document.root,async request=>{
    requests.push(request);
    if(['application.open','application.openRecord'].includes(request.method)){
      const id=`form-${++n}`;value={...value,active:id,sessions:[...value.sessions,{id,entry:1,title:'Order'}]};
      return reply(request,value,{session:id,form:formReply({id:1})});
    }
    if(request.method==='application.form') return reply(request,value,{session:request.params.session,form:formReply(request.params.request)});
    return reply(request,value);
  });
  const settle=async()=>{await app.client.tail;await Promise.all([...app.mounts.values()].map(x=>x.mount.ready));await app.client.tail;await Promise.resolve();};
  await app.ready;
  const command=label=>buttons(env.document).find(node=>node.textContent===label);
  assert.ok(all(env.document.root).some(node=>node.textContent==='Number'));
  assert.ok(all(env.document.root).some(node=>node.textContent==='Date'));
  const selected=all(env.document.root).find(node=>node.dataset.recordKey==='record-1');
  assert.equal(all(selected).some(node=>node.tagName==='BUTTON'),false);
  selected.emit('click');command('Open selected').emit('click');await settle();
  assert.equal(requests.find(request=>request.method==='application.openRecord').params.record,'record-1');
  command('New document').emit('click');await settle();
  assert.equal(requests.filter(request=>request.method==='application.open').length,1);
});
test('document record versions remain monotonic across null projection',async()=>{
  let value=state();const client=new ApplicationClient(async request=>reply(request,value));
  await client.request('application.hello',{});value=state({catalog:null});await client.request('application.snapshot',{});
  value=state({catalog:{entry:1,version:0,rows:[row()]}});
  await assert.rejects(client.request('application.catalog',{entry:1}));assert.equal(client.terminal,true);
});
test('document records do not expose document handle or section object payloads',()=>{
  const request={id:1,method:'application.hello',params:{}};
  for(const extra of [{ref:{}},{lines:[]},{database:'/private/file'},{revision:'private'}])
    assert.throws(()=>validateApplicationReply(reply(request,state({catalog:{entry:1,version:1,rows:[{...row(),...extra}]}})),request,null));
});

test('known form capacity refusal remains usable without allocating a form',async()=>{
  const requests=[];const client=new ApplicationClient(async request=>{
    requests.push(request);
    return reply(request,state(),{error:request.method==='application.openRecord'?'form_capacity':null});
  });
  await client.request('application.hello',{});
  const result=await client.request('application.openRecord',{entry:1,record:'record-1',request:'large'});
  assert.equal(result.error,'form_capacity');assert.equal(result.session,null);assert.equal(client.terminal,false);
  await client.request('application.catalog',{entry:1});
  assert.equal(client.state.catalog.rows.length,1);assert.equal(requests.length,3);
});

test('capacity message explains bounded refusal and keeps the catalog controls live',async()=>{
  const env=environment();
  const app=mountApplication(env,env.document.root,async request=>reply(request,state(),{
    error:request.method==='application.openRecord'?'form_capacity':null}));
  await app.ready;
  all(env.document.root).find(node=>node.dataset.recordKey==='record-1').emit('click');
  buttons(env.document).find(node=>node.textContent==='Open selected').emit('click');
  // Await the same deduplicated opening, including its real finally/repaint.
  await app.openForm(1,'record-1');
  assert.equal(app.client.pending,0);assert.equal(app.client.terminal,false);assert.equal(app.mounts.size,0);
  assert.ok(all(env.document.root).some(node=>node.textContent.includes('Nothing was opened or changed.')));
  assert.equal(buttons(env.document).find(node=>node.textContent==='New document').disabled,false);
});
