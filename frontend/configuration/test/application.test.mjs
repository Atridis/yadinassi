import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {APPLICATION_PROTOCOL,DIALOG_CAPABILITY,ApplicationClient,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from './application-fixtures.mjs';
import {mountApplication as mountProduction} from '../src/app.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
import {state,reply,field,deferred} from '../../form/test/fixtures.mjs';
const snapshot = (extra = {}) => ({kind:'application',lifecycle:'forms',messages:[],exitWarning:'',title:'Configuration',entries:[{id:1,title:'Welcome',kind:'form'},{id:2,title:'Details',kind:'form'}],sessions:[],active:null,uncertain:false,catalog:null,...extra});
const response = (request, value = snapshot(), extra = {}) => ({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state:value,error:null,session:null,form:null,...extra}});
function host(formField = () => field('Amount',{type:'Number',value:'1.00'}), before = async () => {}, demoRecovery = false) {
  let value = snapshot(), next = 0;
  const requests = [], env = environment();
  function open(entry) { const id = `form-${++next}`; value = {...value,active:id,sessions:[...value.sessions,{id,entry,title:`Form ${entry}`} ]}; return id; }
  const exchange = async request => {
    requests.push(request);
    await before(request);
    if (request.method === 'application.open') return response(request,value = (()=>{open(request.params.entry);return value;})(),{session:value.active,form:reply({id:1})});
    if (request.method === 'application.form') {
      const nested = request.params.request, id = request.params.session, closed = nested.params.event === 'close';
      if (nested.params.event === 'command') open(2);
      if (closed) { const sessions = value.sessions.filter(session=>session.id!==id); value = {...value,sessions,active:sessions.at(-1)?.id??null}; }
      return response(request,value,{session:id,form:reply(nested,state(nested.id-1,{items:[formField(nested)],...(closed?{kind:'closed',lifecycle:'closed',items:[]}: {})}))});
    }
    return response(request,value);
  };
  const demoExchange = async request => {
    const result = await exchange(request);
    return {...result,result:{...result.result,dialogCapability:DIALOG_CAPABILITY,dialogs:[],inputCapability:'yadinassi-owned-input/1',inputs:[]}};
  };
  demoExchange.recover = () => {};
  const app = demoRecovery ? mountProduction(env,env.document.root,demoExchange) : mountApplication(env,env.document.root,exchange);
  const settle = async () => { await app.client.tail; await Promise.all([...app.mounts.values()].map(entry=>entry.mount.ready)); };
  return {app,env,requests,settle};
}

test('exact bounded application state, stable entries and declared identities', () => {
  const request = {id:1,method:'application.hello',params:{}};
  assert.equal(validateApplicationReply(response(request),request,null).state.kind,'application');
  for (const patch of [{sessions:Array(9).fill({})},{entries:[]},{entries:Array(65).fill({})},{active:'form-1'},{uncertain:1},{extra:true}]) assert.throws(()=>validateApplicationReply(response(request,snapshot(patch)),request,null));
  assert.throws(()=>validateApplicationReply(response(request),request,snapshot({entries:[{id:3,title:'changed',kind:'form'}]})));
});

test('no crossed nested form, no server names or unknown errors accepted', () => {
  const request = {id:1,method:'application.form',params:{session:'form-1',request:{id:1}}};
  assert.throws(()=>validateApplicationReply(response(request,snapshot(),{session:'form-2',form:reply({id:1})}),request,null));
  assert.throws(()=>validateApplicationReply(response(request,snapshot(),{error:'raw server path'}),request,null));
});

test('lost response locks once and never sends queued work', async () => {
  const gate = deferred(), seen = []; let failed = 0;
  const client = new ApplicationClient(async request=>{seen.push(request);await gate.promise;throw Error('lost');},()=>{},()=>failed++);
  const first = client.request('application.hello',{}), next = client.request('application.open',{entry:1,request:'x'});
  await Promise.resolve();gate.resolve();await assert.rejects(first);await assert.rejects(next);
  assert.equal(seen.length,1);assert.equal(failed,1);assert.equal(client.pending,0);
});

test('retired opaque ID cannot reappear under another open', async () => {
  let value=snapshot({sessions:[{id:'form-1',entry:1,title:'A'}],active:'form-1'});
  const client=new ApplicationClient(async request=>response(request,value));
  await client.request('application.hello',{});value=snapshot();await client.request('application.snapshot',{});
  value=snapshot({sessions:[{id:'form-1',entry:1,title:'A'}],active:'form-1'});
  await assert.rejects(client.request('application.snapshot',{}));assert.equal(client.terminal,true);
});

test('retained tabs keep invalid draft, selection and focus without RPC', async () => {
  const {app,env,requests,settle}=host();await app.ready;await app.openForm(1);await settle();
  const one=app.mounts.get('form-1'), input=all(one.panel).find(node=>node.tagName==='INPUT');
  input.value='bad decimal';input.emit('input');input.focus();input.setSelectionRange(2,5);
  await app.openForm(2);await settle();const before=requests.length;app.show('form-1');
  assert.equal(app.mounts.get('form-1'),one);assert.equal(input.value,'bad decimal');assert.equal(env.document.activeElement,input);assert.equal(input.selectionStart,2);assert.equal(requests.length,before);assert.equal(app.pending(),true);
});

test('new form from BSL event is discovered and mounted without another open intent', async () => {
  const {app,requests,settle}=host();await app.ready;await app.openForm(1);await settle();
  const request={jsonrpc:'2.0',id:2,method:'form.event',params:{event:'command',revision:0,control:'DetailsButton'}};
  await app.client.form('form-1',request);await settle();
  assert.equal(app.mounts.size,2);assert.equal(app.mounts.get('form-2').panel.hidden,false);
  assert.equal(requests.filter(value=>value.method==='application.open').length,1);
});

test('closing one nested form retains other editor and live app', async () => {
  const {app,settle}=host();await app.ready;await app.openForm(1);await settle();await app.openForm(2);await settle();
  await app.mounts.get('form-1').mount.run('close');assert.equal(app.mounts.has('form-1'),false);assert.equal(app.mounts.has('form-2'),true);assert.equal(app.client.terminal,false);
});

test('duplicate UI openings share one in-flight request', async () => {
  const {app,requests,settle}=host();await app.ready;
  const first=app.openForm(1), second=app.openForm(1);assert.equal(first,second);await first;await settle();assert.equal(requests.filter(value=>value.method==='application.open').length,1);
});

test('hidden unsaved drafts block closing and browser unload', async () => {
  const {app,env,requests,settle}=host();await app.ready;await app.openForm(1);await settle();app.show(null);
  const input=all(app.mounts.get('form-1').panel).find(node=>node.tagName==='INPUT');input.value='bad';input.emit('input');
  buttons(env.document).find(node=>node.textContent==='Close application').emit('click');
  assert.equal(requests.some(value=>value.method==='application.close'),false);
  const event={prevented:false,preventDefault(){this.prevented=true;}};env.listeners.get('beforeunload')(event);assert.equal(event.prevented,true);
});

test('configuration bundle source and output hashes remain exact', async () => {
  const root=new URL('../',import.meta.url), target=new URL('../../../yadinassi/ui/assets/configuration/',import.meta.url);
  const manifest=JSON.parse(await readFile(new URL('build-manifest.json',target),'utf8'));
  assert.equal(manifest.schema,'yadinassi-configuration-assets/0');
  for(const [name,digest] of Object.entries(manifest.sources)) assert.equal(createHash('sha256').update(await readFile(new URL(name,root))).digest('hex'),digest,name);
  for(const [name,digest] of Object.entries(manifest.outputs)) assert.equal(createHash('sha256').update(await readFile(new URL(name,target))).digest('hex'),digest,name);
});


test('late open does not steal selection after newer tab navigation', async () => {
  const gate=deferred(), env=environment();
  const app=mountApplication(env,env.document.root,async request=>{
    if(request.method==='application.hello')return response(request);
    const value=snapshot({sessions:[{id:'form-1',entry:1,title:'Welcome'}],active:'form-1'});
    if(request.method==='application.open'){await gate.promise;return response(request,value,{session:'form-1',form:reply({id:1})});}
    return response(request,value,{session:'form-1',form:reply(request.params.request)});
  });
  await app.ready;const opening=app.openForm(1);app.show(null);gate.resolve();await opening;
  await app.client.tail;assert.equal(app.mounts.get('form-1').panel.hidden,true);
});

const dateField = nested => field('When', nested?.params.event === 'change' ? nested.params.value : {type:'Date',ticks:'0'},
  {controlId:1,editor:{kind:'date',parts:'dateTime'}});

test('retained configuration tabs preserve invalid metadata date text without RPC or losing focus', async () => {
  const {app,env,requests,settle}=host(dateField);await app.ready;await app.openForm(1);await settle();
  const owner=app.mounts.get('form-1'),input=all(owner.panel).find(node=>node.tagName==='INPUT');
  assert.equal(input.readOnly,false);input.value='2024-02-30T12:00:00';input.emit('input');input.focus();input.setSelectionRange(5,10);
  await app.openForm(2);await settle();const before=requests.length;app.show('form-1');
  assert.equal(app.mounts.get('form-1'),owner);assert.equal(input.value,'2024-02-30T12:00:00');
  assert.equal(env.document.activeElement,input);assert.equal(input.selectionStart,5);assert.equal(requests.length,before);
  await owner.mount.run('close');assert.equal(requests.length,before);assert.equal(app.pending(),true);
});

test('late typed Date reply stays in its retained owner without stealing the newer active tab', async () => {
  const gate=deferred();const {app,env,requests,settle}=host(dateField,async request=>{
    if(request.method==='application.form'&&request.params.request.params.event==='change')await gate.promise;
  });
  await app.ready;await app.openForm(1);await settle();await app.openForm(2);await settle();app.show('form-1');
  const owner=app.mounts.get('form-1'),other=app.mounts.get('form-2');
  const input=all(owner.panel).find(node=>node.tagName==='INPUT'),otherInput=all(other.panel).find(node=>node.tagName==='INPUT');
  input.value='1970-01-01T00:00:00';input.emit('input');const pending=owner.mount.run('change','When');
  app.show('form-2');otherInput.focus();gate.resolve();await pending;await settle();
  assert.equal(owner.panel.hidden,true);assert.equal(other.panel.hidden,false);assert.equal(env.document.activeElement,otherInput);
  assert.equal(input.value,'1970-01-01T00:00:00');assert.equal(owner.mount.view.hasDrafts(),false);
  const changes=requests.filter(request=>request.method==='application.form'&&request.params.request.params.event==='change');
  assert.equal(changes.length,1);assert.equal(changes[0].params.session,'form-1');
  assert.deepEqual(changes[0].params.request.params.value,{type:'Date',ticks:'621355968000000'});
});

test('transport-terminal application recovers by validated readonly hello, never replay',async()=>{
 const calls=[];let lost=true;
 const client=new ApplicationClient(async request=>{calls.push(request.method);if(request.method==='application.open'&&lost){lost=false;throw Error('lost');}return response(request);});
 await client.request('application.hello',{protocol:APPLICATION_PROTOCOL});
 await assert.rejects(client.request('application.open',{entry:1,request:'lost'}));assert.equal(client.terminal,true);
 await client.recoveryRead('application.hello',{protocol:APPLICATION_PROTOCOL});assert.equal(client.terminal,true);
 client.finishReadRecovery();assert.equal(client.terminal,false);
 assert.deepEqual(calls,['application.hello','application.open','application.hello']);
});
test('readonly recovery denies business intents and failed inspection keeps terminal',async()=>{
 let calls=0;const client=new ApplicationClient(async()=>{calls++;throw Error('lost');});client.lock();
 assert.throws(()=>client.recoveryRead('application.open',{entry:1,request:'x'}));
 assert.throws(()=>client.request('application.close',{},true));assert.equal(calls,0);
 await assert.rejects(client.recoveryRead('application.hello',{protocol:APPLICATION_PROTOCOL}));
 assert.throws(()=>client.finishReadRecovery());assert.equal(client.terminal,true);
});
test('semantic unknown is sticky and cannot be erased by readonly recovery',async()=>{
 const client=new ApplicationClient(async request=>response(request,snapshot({uncertain:true})));
 await assert.rejects(client.request('application.hello',{protocol:APPLICATION_PROTOCOL}));
 assert.equal(client.semanticUnknown,true);
 assert.throws(()=>client.recoveryRead('application.hello',{protocol:APPLICATION_PROTOCOL}));
 assert.throws(()=>client.finishReadRecovery());assert.equal(client.terminal,true);
});


test('mounted readonly recovery reconciles two locked forms without paint poisoning or draft loss',async()=>{
 let inspecting=false; const observed=[];
 const {app,env,requests,settle}=host(undefined,async request=>{
   if(inspecting && request.method==='application.form'){
     observed.push(request.params.session);
     assert.equal(all(env.document.root).find(node=>node.tagName==='MAIN').inert,true);
   }
 },true);
 await app.ready;await app.openForm(1);await settle();await app.openForm(2);await settle();
 const inputs=[...app.mounts.values()].map(entry=>all(entry.panel).find(node=>node.tagName==='INPUT'));
 inputs.forEach((input,index)=>{input.value=`draft-${index}`;input.emit('input');});
 app.client.lock();for(const entry of app.mounts.values())entry.mount.lock();
 const start=requests.length;inspecting=true;await app.resume();
 assert.deepEqual(observed,['form-1','form-2']);assert.equal(app.client.terminal,false);
 assert.equal(app.recoveryReady(),true);assert.equal(app.canLeave(),false);
 assert.deepEqual(inputs.map(input=>input.value),['draft-0','draft-1']);
 assert.equal(all(env.document.root).find(node=>node.tagName==='MAIN').inert,false);
 assert.deepEqual(requests.slice(start).map(request=>request.method==='application.form'?request.params.request.method:request.method),['application.hello','form.snapshot','form.snapshot']);
 for(const entry of app.mounts.values())assert.equal(entry.mount.client.transportFailed,false);
});

test('failed second form readonly recovery relocks all forms and preserves terminal fence',async()=>{
 let fail=false;
 const {app,requests,settle}=host(undefined,async request=>{
   if(fail&&request.method==='application.form'&&request.params.session==='form-2')throw Error('lost inspection');
 },true);
 await app.ready;await app.openForm(1);await settle();await app.openForm(2);await settle();
 app.client.lock();for(const entry of app.mounts.values())entry.mount.lock();
 const start=requests.length;fail=true;await assert.rejects(app.resume());
 assert.equal(app.client.terminal,true);assert.equal(app.recoveryReady(),false);
 for(const entry of app.mounts.values())assert.equal(entry.mount.client.transportFailed,true);
 assert.deepEqual(requests.slice(start).map(request=>request.method==='application.form'?request.params.request.method:request.method),['application.hello','form.snapshot','form.snapshot']);
});
