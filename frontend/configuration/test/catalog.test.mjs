import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL, ApplicationClient, validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from '../src/app.mjs';
import {environment, all, buttons} from '../../form/test/fake-dom.mjs';
import {state as formState, reply as formReply, field, deferred} from '../../form/test/fixtures.mjs';

const rows = () => [
  {key:'record-1',code:'001',description:'First',deletionMark:false},
  {key:'record-2',code:'002',description:'Second',deletionMark:false},
];
const snapshot = (extra = {}) => ({kind:'application',title:'Catalog app',
  entries:[{id:1,title:'Products',kind:'catalog-object'},{id:2,title:'Welcome',kind:'form'}],
  sessions:[],active:null,uncertain:false,catalog:{entry:1,version:1,rows:rows()},...extra});
const response = (request, state = snapshot(), extra = {}) => ({jsonrpc:'2.0',id:request.id,
  result:{protocol:APPLICATION_PROTOCOL,state,error:null,session:null,form:null,...extra}});
const byKey = (env,key) => all(env.document.root).find(node=>node.dataset.recordKey===key);
const command = (env,label) => buttons(env.document).find(node=>node.textContent===label);

function host() {
  let value=snapshot(), serial=0, error=null;
  const env=environment(), requests=[];
  const exchange=async request=>{
    requests.push(request);
    if (['application.open','application.openRecord'].includes(request.method)) {
      const id=`form-${++serial}`;
      value={...value,active:id,sessions:[...value.sessions,{id,entry:request.params.entry,title:'Product'}]};
      return response(request,value,{session:id,form:formReply({id:1})});
    }
    if(request.method==='application.form') {
      const nested=request.params.request;
      return response(request,value,{session:request.params.session,
        form:formReply(nested,formState(nested.id-1,{items:[field('Amount',{type:'Number',value:'1.00'})]}))});
    }
    return response(request,value,{error});
  };
  const app=mountApplication(env,env.document.root,exchange);
  const settle=async()=>{await app.client.tail;await Promise.all([...app.mounts.values()].map(entry=>entry.mount.ready));await app.client.tail;await Promise.resolve();};
  return {env,app,requests,settle,setCatalog(catalog,failure=null){value={...value,catalog};error=failure;}};
}

test('catalog projection is closed, bounded and never accepts raw reference payloads',()=>{
  const request={id:1,method:'application.hello',params:{}};
  assert.equal(validateApplicationReply(response(request),request,null).state.catalog.rows.length,2);
  for(const catalog of [
    {entry:2,version:1,rows:rows()}, {entry:1,version:-1,rows:rows()},
    {entry:1,version:1,rows:[rows()[0],rows()[0]]},
    {entry:1,version:1,rows:Array(257).fill(rows()[0])},
    {entry:1,version:1,rows:[{...rows()[0],key:'550e8400-e29b-41d4-a716-446655440000'}]},
    {entry:1,version:1,rows:[{...rows()[0],source:'/private/database'}]},
  ]) assert.throws(()=>validateApplicationReply(response(request,snapshot({catalog})),request,null));
});

test('catalog versions cannot roll backwards even after another projection was shown',async()=>{
  let value=snapshot();const client=new ApplicationClient(async request=>response(request,value));
  await client.request('application.hello',{});
  value=snapshot({catalog:null});await client.request('application.snapshot',{});
  value=snapshot({catalog:{entry:1,version:0,rows:rows()}});
  await assert.rejects(client.request('application.catalog',{entry:1}));assert.equal(client.terminal,true);
});

test('commands are above compact rows and newest synchronous selection owns Open',async()=>{
  const {env,app,requests,settle}=host();await app.ready;
  byKey(env,'record-1').emit('click');byKey(env,'record-2').emit('click');
  command(env,'Open selected').emit('click');await settle();
  const sent=requests.find(request=>request.method==='application.openRecord');
  assert.equal(sent.params.record,'record-2');assert.equal(sent.params.entry,1);
  assert.equal(all(byKey(env,'record-1')).some(node=>node.tagName==='BUTTON'),false);
});

test('multiple selected records never silently become a batch or an arbitrary target',async()=>{
  const {env,app,requests,settle}=host();await app.ready;
  byKey(env,'record-1').emit('click');byKey(env,'record-2').emit('click',{ctrlKey:true});
  assert.equal(command(env,'Open selected').disabled,true);
  command(env,'Open selected').emit('click');await settle();
  assert.equal(requests.some(request=>request.method==='application.openRecord'),false);
  byKey(env,'record-1').emit('click',{metaKey:true});
  assert.equal(command(env,'Open selected').disabled,false);
  command(env,'Open selected').emit('click');await settle();
  assert.equal(requests.find(request=>request.method==='application.openRecord').params.record,'record-2');
});

test('refresh reconciles selection by opaque key rather than row position',async()=>{
  const {env,app,requests,settle,setCatalog}=host();await app.ready;
  byKey(env,'record-1').emit('click');
  setCatalog({entry:1,version:2,rows:[rows()[1]]});
  await app.client.request('application.catalog',{entry:1});
  command(env,'Open selected').emit('click');await settle();
  assert.equal(requests.some(request=>request.method==='application.openRecord'),false);
});

test('authoritative list refresh does not remount or replace a dirty sibling form',async()=>{
  const {env,app,settle,setCatalog}=host();await app.ready;await app.openForm(1);await settle();
  const mount=app.mounts.get('form-1');const input=all(mount.panel).find(node=>node.tagName==='INPUT');
  input.value='invalid draft';input.emit('input');
  setCatalog({entry:1,version:2,rows:[...rows(),{key:'record-3',code:'003',description:'Saved elsewhere',deletionMark:false}]});
  await app.client.request('application.catalog',{entry:1});
  assert.equal(app.mounts.get('form-1'),mount);assert.equal(input.value,'invalid draft');
  assert.ok(byKey(env,'record-3'));assert.equal(app.pending(),true);
});

test('failed list projection retires stale visible targets without closing the card',async()=>{
  const {env,app,requests,settle,setCatalog}=host();await app.ready;await app.openForm(1);await settle();
  byKey(env,'record-1').emit('click');const oldOpen=command(env,'Open selected');
  setCatalog(null,'catalog_unavailable');await app.client.request('application.catalog',{entry:1});
  oldOpen.emit('click');await settle();
  assert.equal(app.mounts.size,1);assert.equal(app.client.terminal,false);
  assert.equal(requests.filter(request=>request.method==='application.openRecord').length,0);
  assert.equal(byKey(env,'record-1'),undefined);
});

test('catalog navigation lists records, New explicitly allocates a separate form',async()=>{
  const {env,app,requests,settle}=host();await app.ready;
  command(env,'Products').emit('click');await settle();
  assert.equal(requests.at(-1).method,'application.catalog');
  command(env,'New record').emit('click');await settle();
  assert.equal(requests.filter(request=>request.method==='application.open').length,1);
  assert.equal(app.mounts.size,1);
});

test('record open replies require a newly live declared form identity',()=>{
  const request={id:1,method:'application.openRecord',params:{entry:1,record:'record-1',request:'x'}};
  assert.throws(()=>validateApplicationReply(response(request),request,null));
  assert.throws(()=>validateApplicationReply(response(request,snapshot(),{session:'form-9'}),request,null));
});

test('lost catalog reply locks queued record operations without replay',async()=>{
  const gate=deferred(), sent=[];const client=new ApplicationClient(async request=>{sent.push(request);await gate.promise;throw Error('lost');});
  const first=client.request('application.catalog',{entry:1});
  const second=client.request('application.openRecord',{entry:1,record:'record-1',request:'x'});
  gate.resolve();await assert.rejects(first);await assert.rejects(second);
  assert.equal(client.terminal,true);assert.equal(sent.length,1);
});
