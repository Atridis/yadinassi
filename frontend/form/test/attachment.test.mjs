import test from 'node:test';
import assert from 'node:assert/strict';
import {BROWSER_PROTOCOL, RESUME_KEY, AttachmentRefusal, documentInstance, readBrowserLaunch, BrowserAttachment, createBrowserHost} from '../src/attachment.mjs';
import {FormClient,validateSnapshot} from '../src/client.mjs';
import {EditorClient} from '../../catalog/src/client.mjs';
import {WorkspaceClient} from '../../workspace/src/client.mjs';
import {ApplicationClient} from '../../configuration/src/client.mjs';
import {ReferenceClient} from '../../reference-workspace/src/client.mjs';
import {mountForm} from '../src/app.mjs';
import {environment, all} from './fake-dom.mjs';
import {state, reply, response, field, button, deferred, pageLayout} from './fixtures.mjs';

const launcher = 'l'.repeat(43), credential = 'c'.repeat(43), resume = 'r'.repeat(43);
const status = (extra = {}) => ({protocol:BROWSER_PROTOCOL,attachment:'attachment-1',role:'writer',generation:1,
  leaseSeconds:90,graceSeconds:30,recovery:false,closed:false,...extra});
const issued = (extra = {}) => status({credential,resume,...extra});
const rejected = code => new Response(JSON.stringify({protocol:BROWSER_PROTOCOL,error:code})+'\n',
  {status:code==='unauthorized'?403:409,headers:{'content-type':'application/x-ndjson'}});
let seed = 0;
function browser(handle = () => response(issued()), store = new Map()) {
  const requests = [], intervals = new Map(); let interval = 0;
  const env = environment(async (path, options) => {
    const body = JSON.parse(options.body); requests.push({path,body,options}); return handle(path,body,options);
  });
  env.location.hash = '#session='+launcher+'&attachment=1';
  env.crypto = {getRandomValues(bytes) { bytes.fill(++seed); return bytes; }};
  env.sessionStorage = {getItem: key => store.get(key) ?? null, setItem: (key,value) => store.set(key,value), removeItem: key => store.delete(key)};
  env.setInterval = (callback, delay) => { intervals.set(++interval,{callback,delay}); return interval; };
  env.clearInterval = id => intervals.delete(id);
  return {env, requests, store, intervals};
}
const attached = async (handle, extra = {}) => {
  const setup = browser(handle); const client = new BrowserAttachment(setup.env,{launcher});
  Object.assign(client,extra); await client.attach(); return {...setup,client};
};
const tick = () => new Promise(resolve => setImmediate(resolve));
const hello = {jsonrpc:'2.0',id:1,method:'form.hello',params:{protocol:'yadinassi-form-ui/1'}};

test('attachment launch strips full capability and stores only the narrow returned resume', async () => {
  const {env,requests,store} = browser(); const launch = readBrowserLaunch(env);
  assert.deepEqual(launch,{enabled:true,launcher,resume:null}); assert.deepEqual(env.historyCalls,[[null,'','/']]);
  const client = new BrowserAttachment(env,launch); await client.attach();
  assert.deepEqual([...store],[[RESUME_KEY,resume]]); assert.equal(store.has(launcher),false);
  assert.equal(requests[0].options.headers['X-Yadinassi-Session'],launcher);
  assert.deepEqual(Object.keys(client.info).sort(),Object.keys(status()).sort()); assert.equal(client.writable,true);
});

test('reload and duplicated resume storage create distinct document identities without storing launcher', async () => {
  const store = new Map([[RESUME_KEY,resume]]), first = browser(undefined,store), second = browser(undefined,new Map(store));
  first.env.location.hash = second.env.location.hash = '';
  const a = readBrowserLaunch(first.env), b = readBrowserLaunch(second.env);
  assert.equal(a.resume,resume); assert.equal(b.enabled,true); assert.notEqual(documentInstance(first.env),documentInstance(second.env));
  const client = new BrowserAttachment(first.env,a); await client.attach();
  assert.equal(first.requests[0].options.headers['X-Yadinassi-Session'],resume);
});

test('legacy full launcher URL stays legacy and never reads or stores a resume', () => {
  const {env} = browser(); env.location.hash = '#session='+launcher;
  Object.defineProperty(env,'sessionStorage',{get() { throw Error('Legacy storage access'); }});
  assert.deepEqual(readBrowserLaunch(env),{enabled:false,launcher,resume:null});
});

test('blocked session storage does not prevent a valid attachment', async () => {
  const {env} = browser(); Object.defineProperty(env,'sessionStorage',{get() { throw Error('Blocked storage'); }});
  const client = new BrowserAttachment(env,readBrowserLaunch(env)); await client.attach(); assert.equal(client.writable,true);
});

test('observer starts with inert content and no business handshake until explicit takeover', async () => {
  const {env,requests} = browser((path,body) => response(body.action==='attach'?issued({role:'observer',generation:2}):status({generation:3})));
  const host = createBrowserHost(env,env.document.root); let reconciles = 0;
  await host.start(async () => { reconciles++; });
  assert.equal(host.content.inert,true); assert.equal(reconciles,0); assert.equal(requests.length,1);
  assert.ok(env.document.root.textContent.includes('Take control')); await host.attachment.takeover();
  assert.equal(reconciles,1); assert.equal(host.content.inert,false); assert.equal(requests[1].body.action,'takeover');
});

test('business RPC carries attachment credential and exact generation, never launcher key', async () => {
  const {client,requests} = await attached((path,body) => response(path==='/attachment'?issued():reply(body)));
  await client.exchange(hello); const sent = requests[1];
  assert.deepEqual(sent.options.headers,{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':credential,
    'X-Yadinassi-Attachment':'attachment-1','X-Yadinassi-Generation':'1'});
  assert.equal(sent.path,'/rpc'); assert.equal(sent.options.credentials,'omit'); assert.equal(sent.options.redirect,'error');
});

test('ownership reconciliation can read state but never sends a queued business action', async () => {
  const {env,requests} = browser((path,body) => response(path==='/attachment'?issued():reply(body)));
  const client = new BrowserAttachment(env,{launcher}); client.reconcile = async () => {
    await client.exchange(hello);
    await assert.rejects(client.exchange({...hello,method:'form.event',params:{event:'close',revision:0}}),{code:'not_writer'});
  };
  await client.attach(); assert.deepEqual(requests.map(request=>request.path),['/attachment','/rpc']);
});

test('known not_writer refusal pauses without retrying or creating an unknown outcome', async () => {
  const {client,requests} = await attached(path => path==='/attachment'?response(issued()):rejected('not_writer'));
  await assert.rejects(client.exchange(hello),{code:'not_writer',preDispatch:true});
  assert.equal(client.businessUnknown,false); assert.equal(client.writable,false); assert.equal(requests.length,2);
  await assert.rejects(client.exchange(hello),{code:'not_writer'}); assert.equal(requests.length,2);
});

test('all five business clients preserve known pre-dispatch refusals without terminal transport lock', async () => {
  for (const Client of [FormClient,EditorClient,WorkspaceClient,ApplicationClient,ReferenceClient]) {
    const client = new Client(async () => { throw new AttachmentRefusal('not_writer'); });
    await assert.rejects(client.hello ? client.hello() : client.request('workspace.hello',{}),{code:'not_writer'});
    assert.ok(!client.transportFailed && !client.uncertain && !client.terminal);
  }
});

test('generic HTTP failure or malformed refusal locks unknown business outcome permanently', async () => {
  for (const failure of [() => new Response('failed',{status:503}), () => new Response('{}\n',{status:409,headers:{'content-type':'application/x-ndjson'}}),
    () => { throw Error('Lost reply'); }]) {
    const {client,requests} = await attached(path => path==='/attachment'?response(issued()):failure());
    await assert.rejects(client.exchange(hello)); assert.equal(client.businessUnknown,true); assert.equal(client.writable,false);
    await client.takeover(); assert.equal(requests.length,2);
  }
});

test('status after unknown RPC never clears outcome lock or invokes business reconciliation', async () => {
  let reconciles = 0;
  const {client} = await attached((path,body) => path==='/attachment'?response(body.action==='attach'?issued():status()):Promise.reject(Error('lost')),
    {reconcile:async () => { reconciles++; }});
  await assert.rejects(client.exchange(hello)); await client.check();
  assert.equal(reconciles,1); assert.equal(client.businessUnknown,true); assert.equal(client.writable,false);
});

test('heartbeat uses fifteen-second cadence and carries raw-draft pending without business dispatch', async () => {
  const {client,intervals,requests} = await attached((_,body) => response(body.action==='attach'?issued():status()),{pending:()=>true});
  assert.equal(intervals.size,1); const timer=[...intervals.values()][0]; assert.equal(timer.delay,15000);
  timer.callback(); await tick(); assert.deepEqual(requests[1].body,{action:'heartbeat',generation:1,pending:true});
  assert.ok(requests.every(request=>request.path==='/attachment')); client.dispose(); assert.equal(intervals.size,0);
});

test('busy heartbeat is benign and a stalled heartbeat cannot accumulate queued timers', async () => {
  const gate = deferred(); const {client,intervals,requests} = await attached((_,body) => body.action==='attach'?response(issued()):gate.promise);
  const timer=[...intervals.values()][0]; timer.callback(); timer.callback(); timer.callback(); await tick(); assert.equal(requests.length,2);
  gate.resolve(rejected('busy')); await tick(); assert.equal(client.writable,true); assert.equal(client.businessUnknown,false);
});

test('heartbeat observes ownership loss and never silently takes ownership back', async () => {
  const {client,intervals,requests} = await attached((_,body) => response(body.action==='attach'?issued():status({role:'observer',generation:2})));
  [...intervals.values()][0].callback(); await tick(); assert.equal(client.writable,false); assert.equal(client.info.role,'observer');
  assert.deepEqual(requests.map(request=>request.body.action),['attach','heartbeat']);
});

test('pagehide detaches with keepalive and pending but never sends Save, Discard or Close', async () => {
  const {client,requests,intervals} = await attached((_,body) => response(body.action==='attach'?issued():status({role:'observer',generation:2})),{pending:()=>true});
  await client.detach(); assert.equal(client.suspended,true); assert.equal(client.writable,false); assert.equal(intervals.size,0);
  assert.deepEqual(requests[1].body,{action:'detach',generation:1,pending:true}); assert.equal(requests[1].options.keepalive,true);
  assert.equal(requests[1].options.headers['X-Yadinassi-Attachment'],'attachment-1'); assert.equal(requests.length,2);
});

test('detach during an in-flight RPC marks pending and does not repeat the business operation', async () => {
  const gate=deferred(); const {client,requests} = await attached((path,body) => path==='/rpc'?gate.promise:
    body.action==='attach'?response(issued()):rejected('busy'));
  const operation=client.exchange(hello); await client.detach(); assert.equal(requests[2].body.pending,true);
  gate.resolve(response(reply(hello))); await operation; assert.equal(client.writable,false);
  assert.equal(requests.filter(request=>request.path==='/rpc').length,1);
});

test('pageshow checks status before reads and detached observer requires explicit takeover', async () => {
  let reconciles=0; const {client,env,requests} = await attached((_,body) => response(body.action==='attach'?issued():status({role:'observer',generation:2})),
    {reconcile:async()=>{reconciles++;}});
  await client.detach(); env.listeners.get('pageshow')({persisted:true}); await tick();
  assert.deepEqual(requests.map(request=>request.body.action),['attach','detach','status']); assert.equal(reconciles,1); assert.equal(client.writable,false);
});

test('pageshow still-owned writer reconciles before enabling edits and preserves no replay contract', async () => {
  const gate=deferred(); let count=0; const {client,env} = await attached((_,body) => response(body.action==='attach'?issued():status()),
    {reconcile:async()=>{if(++count>1)await gate.promise;}});
  env.listeners.get('pageshow')({persisted:true}); await tick(); assert.equal(client.writable,false); assert.equal(count,2);
  gate.resolve(); await tick(); assert.equal(client.writable,true);
});

test('pagehide while reconciliation awaits cannot be undone by the late response', async () => {
  const gate=deferred(); const {env} = browser((_,body)=>response(body.action==='attach'?issued():status({role:'observer',generation:2})));
  const client=new BrowserAttachment(env,{launcher}); client.reconcile=()=>gate.promise;
  const opening=client.attach(); await tick(); await client.detach(); gate.resolve(); await opening;
  assert.equal(client.writable,false); assert.equal(client.suspended,true);
});

test('lost attach response retries only explicit bootstrap with the same document instance', async () => {
  let attempts=0; const {env,requests}=browser(()=>++attempts===1?Promise.reject(Error('lost attach')):response(issued()));
  const client=new BrowserAttachment(env,{launcher}); assert.equal(await client.attach(),false); assert.equal(requests.length,1);
  assert.equal(await client.attach(),true); assert.deepEqual(requests[0].body,requests[1].body); assert.equal(requests.length,2);
});

test('missing or expired reconnect key yields fixed instructions and clears expired narrow resume', async () => {
  const {env,requests,store}=browser(()=>rejected('unauthorized'),new Map([[RESUME_KEY,resume]]));
  const missing=new BrowserAttachment(env,{}); await missing.attach(); assert.equal(requests.length,0);
  const expired=new BrowserAttachment(env,{resume}); await expired.attach(); assert.equal(store.has(RESUME_KEY),false);
  assert.ok(expired.message.includes('complete URL')); assert.equal(expired.writable,false);
});

test('strict attachment schema rejects extra keys, wrong generation and mismatched attachment identity', async () => {
  for (const malformed of [issued({extra:true}),issued({generation:true}),issued({role:'owner'}),issued({credential:'short'}),issued({resume:42})]) {
    const {client}=await attached(()=>response(malformed)); assert.equal(client.info,null); assert.equal(client.writable,false);
  }
  const {client}=await attached((_,body)=>response(body.action==='attach'?issued():status({attachment:'attachment-2'})));
  await client.check(); assert.equal(client.writable,false); assert.equal(client.info.attachment,'attachment-1');
});

test('completed top-level Close stops heartbeat without any further closure request', async () => {
  const {client,intervals,requests}=await attached((path,body)=>response(path==='/attachment'?issued():reply(body,state(1,{kind:'closed',lifecycle:'closed'}))));
  await client.exchange({...hello,method:'form.event',params:{event:'close',revision:0}});
  assert.equal(client.info.closed,true); assert.equal(intervals.size,0); assert.equal(requests.length,2);
});

test('live raw invalid draft survives observer pause and takeover snapshot without event replay', async () => {
  let generation=1, role='writer'; const {env,requests}=browser((path,body)=> {
    if(path==='/attachment'){
      if(body.action==='attach')return response(issued());
      if(body.action==='takeover'){role='writer';generation++;}
      return response(status({role,generation}));
    }
    return response(reply(body,state(generation,{items:[field('Amount',{type:'Number',value:'1.00'}),button()]})));
  });
  const app=mountForm(env,env.document.root); await app.ready;
  const input=all(env.document.root).find(node=>node.tagName==='INPUT'); input.value='invalid decimal';input.emit('input');
  role='observer';generation++;await app.browserHost.attachment.check();
  assert.equal(app.browserHost.content.inert,true);assert.equal(input.value,'invalid decimal');
  await app.browserHost.attachment.takeover();assert.equal(input.value,'invalid decimal');assert.equal(app.browserHost.content.inert,false);
  assert.deepEqual(requests.filter(request=>request.path==='/rpc').map(request=>request.body.method),['form.hello','form.snapshot']);
});

test('ownership reconciliation keeps orphaned invalid cell input as copy-only data, never retargeted', async () => {
  const {createFormView}=await import('../src/view.mjs'),{table}=await import('./fixtures.mjs');
  const {env}=browser(),view=createFormView(env.document,env.document.root,{change(){},action(){},select(){},refresh(){}});
  const model=snapshot=>({snapshot,busy:false,locked:false,error:'',connected:true});
  view.render(model(state(0,{items:[table(),button()]})));
  const input=all(env.document.root).find(node=>node.getAttribute('aria-label')==='Quantity, row 1');
  input.value='raw invalid cell';input.emit('input');view.beginOwnershipReconcile();
  view.render(model(state(1,{items:[table({tableId:2}),button()]})));view.endOwnershipReconcile();
  assert.ok(env.document.root.textContent.includes('raw invalid cell'));assert.equal(view.hasDrafts(),true);
  assert.throws(()=>view.changes(),{code:'draft_changed'});
  view.clearDrafts();view.render(model(state(1,{items:[table({tableId:2}),button()]})));
  assert.equal(view.hasDrafts(),false);assert.equal(env.document.root.textContent.includes('raw invalid cell'),false);
});


test('inspection opt-in is fail-closed and never grants writer transport or takeover authority', async () => {
  const {env,requests}=browser(path=>path==='/attachment'?response(issued()):Promise.reject(Error('lost')));
  const host=createBrowserHost(env,env.document.root);await host.start(async()=>{});
  await assert.rejects(host.transport(hello));host.notify();
  assert.equal(host.content.inert,true);assert.equal(host.attachment.writable,false);
  host.setInspectionAllowed(()=>true);assert.equal(host.content.inert,false);assert.equal(host.content.dataset.inspection,'true');
  const count=requests.length;await assert.rejects(host.transport(hello),{code:'not_writer'});await host.attachment.takeover();
  assert.equal(requests.length,count);assert.equal(host.attachment.businessUnknown,true);
  host.setInspectionAllowed(()=>{throw Error('predicate failure');});assert.equal(host.content.inert,true);
  host.setInspectionAllowed(()=>1);assert.equal(host.content.inert,true);
  host.setInspectionAllowed(()=>true);
  for(const key of ['reconciling','busy','rpcActive']){
    host.attachment[key]=true;host.notify();assert.equal(host.content.inert,true,key);
    host.attachment[key]=false;host.notify();assert.equal(host.content.inert,false,key);
  }
  host.attachment.adopt(status({generation:2}));assert.equal(host.content.inert,true);
  host.attachment.adopt(status({generation:2}));assert.equal(host.content.inert,true,'status cannot revive old DOM inspection');
  host.attachment.dispose();
});

test('attached layout loss allows only local draft inspection after lock and revokes it for picker or ownership transitions', async () => {
  const snapshot=pageLayout();validateSnapshot(snapshot);let picker=false;
  const {env,requests}=browser((path,request)=>path==='/attachment'?response(issued()):
    request.params.event==='change'?Promise.reject(Error('lost response')):response(reply(request,snapshot)));
  const app=mountForm(env,env.document.root,{referenceActive:()=>picker});await app.ready;
  const input=name=>all(env.document.root).find(node=>node.tagName==='INPUT'&&node.getAttribute('aria-label')===name);
  const tab=name=>all(env.document.root).find(node=>node.getAttribute('role')==='tab'&&node.textContent===name);
  input('Name').value='uncertain first';input('Name').emit('input');tab('Second').emit('click');
  input('Notes').value='  raw second  ';input('Notes').emit('input');tab('First').emit('click');
  await app.run('change','Name');const count=requests.length;
  assert.equal(app.client.locked,true);assert.equal(app.browserHost.attachment.writable,false);assert.equal(app.browserHost.content.inert,false);
  tab('Second').emit('click');assert.equal(tab('Second').getAttribute('aria-selected'),'true');
  assert.equal(input('Notes').value,'  raw second  ');assert.equal(input('Notes').disabled,true);
  assert.ok(env.document.root.textContent.includes('Notes:   raw second  '));
  await app.run('change','Notes');await app.run('command','SaveSecond');await app.run('close');await app.refresh();
  assert.equal(requests.length,count);assert.equal(app.client.locked,true);
  picker=true;app.repaint();app.browserHost.notify();assert.equal(app.browserHost.content.inert,true);assert.equal(tab('First').disabled,true);
  picker=false;app.repaint();app.browserHost.notify();assert.equal(app.browserHost.content.inert,false);
  app.browserHost.attachment.adopt(status({role:'observer',generation:2}));
  assert.equal(app.browserHost.content.inert,true);assert.equal(input('Notes').value,'  raw second  ');assert.equal(requests.length,count);
  app.browserHost.attachment.dispose();
});


test('observer closed and pagehide transitions permanently revoke the retained inspection grant', async () => {
  for(const transition of ['observer','closed','pagehide']){
    const {env}=browser((path,body)=>path==='/attachment'?response(body.action==='attach'?issued():status({role:'observer',generation:2})):Promise.reject(Error('lost')));
    const host=createBrowserHost(env,env.document.root);await host.start(async()=>{});
    await assert.rejects(host.transport(hello));host.setInspectionAllowed(()=>true);assert.equal(host.content.inert,false);
    if(transition==='pagehide')await host.attachment.detach();
    else host.attachment.adopt(status(transition==='observer'?{role:'observer',generation:2}:{closed:true}));
    host.notify();assert.equal(host.content.inert,true,transition);
    if(transition!=='closed'){host.attachment.suspended=false;host.attachment.adopt(status({generation:3}));}
    host.setInspectionAllowed(()=>true);assert.equal(host.content.inert,true,'no stale grant revival');
    host.attachment.dispose();
  }
});

test('main demo reconciliation admits only exact read envelopes, never surface mutations',async()=>{
 const {client,requests}=await attached((path,body)=>response(path==='/attachment'?issued():{jsonrpc:'2.0',id:body.id,result:{}}));
 client.paused=true;client.reconciling=true;
 const wrap=request=>({jsonrpc:'2.0',id:90,method:'demo.dispatch',params:{epoch:'a'.repeat(32),request}});
 for(const method of ['demo.hello','demo.snapshot'])await client.exchange({jsonrpc:'2.0',id:90,method,params:{protocol:'yadinassi-main-demo/1'}});
 for(const method of ['editor.hello','editor.snapshot','application.hello','application.snapshot'])await client.exchange(wrap({jsonrpc:'2.0',id:2,method,params:{}}));
 for(const request of [
  {jsonrpc:'2.0',id:90,method:'demo.snapshot',params:{protocol:'wrong'}},
  {jsonrpc:'2.0',id:90,method:'demo.select',params:{epoch:'a'.repeat(32),surface:'documents'}},
  wrap({jsonrpc:'2.0',id:2,method:'editor.event',params:{event:'command',control:'SaveButton'}}),
  wrap({jsonrpc:'2.0',id:2,method:'application.form',params:{request:{method:'form.event'}}})]){
  const before=requests.length;await assert.rejects(client.exchange(request),AttachmentRefusal);assert.equal(requests.length,before);
 }
 client.dispose();
});

test('demo inspection never dispatches a write even for a writable owner',async()=>{
 const {client,requests}=await attached((path,body)=>response(path==='/attachment'?issued():{jsonrpc:'2.0',id:body.id,result:{}}));
 const before=requests.length;
 await assert.rejects(client.inspectDemo(()=>client.exchange({method:'demo.select',params:{surface:'documents'}})),AttachmentRefusal);
 assert.equal(requests.length,before);client.dispose();
});
test('demo inspection preserves unknown fence on callback failure',async()=>{
 const {client}=await attached(()=>response(issued()));client.businessUnknown=true;
 await assert.rejects(client.inspectDemo(async()=>{throw Error('inspection failed');}));
 assert.equal(client.businessUnknown,true);assert.equal(client.demoInspection,null);client.dispose();
});
test('demo inspection refuses generation changes and takeover during callback',async()=>{
 for(const change of [{generation:2},{role:'observer'}]){
  const {client}=await attached(()=>response(issued()));client.businessUnknown=true;
  await assert.rejects(client.inspectDemo(async()=>{client.info={...client.info,...change};return {protocol:'yadinassi-main-demo/1',epoch:'a'.repeat(32),ready:true};}),AttachmentRefusal);
  assert.equal(client.businessUnknown,true);client.dispose();
 }
});
test('demo inspection cannot clear unknown merely from caller assertion',async()=>{
 const {client}=await attached(()=>response(issued()));client.businessUnknown=true;
 await client.inspectDemo(async()=>({protocol:'yadinassi-main-demo/1',epoch:'a'.repeat(32),ready:true}));
 assert.equal(client.businessUnknown,true);client.dispose();
});
test('demo inspection clears fence only after observed snapshot and same epoch renderer read',async()=>{
 const epoch='a'.repeat(32);
 const {client}=await attached((path,body)=>response(path==='/attachment'?issued():{jsonrpc:'2.0',id:body.id,result:{protocol:'yadinassi-main-demo/1',state:{kind:'main-demo',surface:'catalogs',epoch,canSwitch:false,uncertain:false},error:null,payload:body.method==='demo.dispatch'?{jsonrpc:'2.0',id:body.params.request.id,result:{}}:null}}));
 client.businessUnknown=true;client.paused=true;
 for(const claim of [{epoch,ready:false},{epoch:'b'.repeat(32),ready:true}]){
  await client.inspectDemo(async()=>{
   await client.exchange({jsonrpc:'2.0',id:1,method:'demo.snapshot',params:{protocol:'yadinassi-main-demo/1'}});
   await client.exchange({jsonrpc:'2.0',id:2,method:'demo.dispatch',params:{epoch,request:{jsonrpc:'2.0',id:1,method:'editor.snapshot',params:{}}}});
   return {protocol:'yadinassi-main-demo/1',...claim};
  });
  assert.equal(client.businessUnknown,true);assert.equal(client.paused,true);
 }
 await client.inspectDemo(async()=>{
  await client.exchange({jsonrpc:'2.0',id:1,method:'demo.snapshot',params:{protocol:'yadinassi-main-demo/1'}});
  await client.exchange({jsonrpc:'2.0',id:2,method:'demo.dispatch',params:{epoch,request:{jsonrpc:'2.0',id:1,method:'editor.snapshot',params:{}}}});
  return {protocol:'yadinassi-main-demo/1',epoch,ready:true};
 });
 assert.equal(client.businessUnknown,false);assert.equal(client.paused,false);client.dispose();
});
