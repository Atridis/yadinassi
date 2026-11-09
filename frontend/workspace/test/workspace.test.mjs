import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {WORKSPACE_PROTOCOL,WorkspaceClient,validateWorkspaceReply} from '../src/client.mjs';
import {mountWorkspace} from '../src/app.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
import {state,reply,field,deferred} from '../../form/test/fixtures.mjs';
const workspace = (extra = {}) => ({kind:'workspace',revision:0,orders:[],truncated:false,sessions:[],uncertain:false,...extra});
const response = (request, snapshot = workspace(), extra = {}) => ({jsonrpc:'2.0',id:request.id,result:{protocol:WORKSPACE_PROTOCOL,state:snapshot,error:null,session:null,form:null,...extra}});
function host() {
  let snapshot = workspace(), next = 0;
  const requests = []; const env = environment();
  const exchange = async request => {
    requests.push(request);
    if (request.method === 'workspace.open') {
      const id = `s${++next}`; snapshot = {...snapshot,revision:snapshot.revision+1,sessions:[...snapshot.sessions,{id,kind:'intake'}]};
      return response(request,snapshot,{session:id,form:reply({id:1})});
    }
    if (request.method === 'workspace.form') {
      const nested = request.params.request;
      const closed = nested.params.event === 'close';
      if (closed) snapshot = {...snapshot,revision:snapshot.revision+1,sessions:snapshot.sessions.filter(value => value.id !== request.params.session)};
      const form = state(nested.id-1,{items:[field('Amount',{type:'Number',value:'1.00'})],...(closed ? {kind:'closed',lifecycle:'closed',items:[]} : {})});
      return response(request,snapshot,{session:request.params.session,form:reply(nested,form)});
    }
    return response(request,snapshot);
  };
  const app = mountWorkspace(env,env.document.root,exchange);
  return {app,env,requests,exchange};
}

test('workspace validates exact bounded state and rejects malformed envelopes', () => {
  const request = {id:1,method:'workspace.hello',params:{}};
  assert.equal(validateWorkspaceReply(response(request),request,null).state.kind,'workspace');
  for (const changes of [{revision:-1},{orders:Array(33).fill({})},{sessions:Array(5).fill({})},{uncertain:'false'},{kind:'form'},{extra:1}]) {
    assert.throws(() => validateWorkspaceReply(response(request,workspace(changes)),request,null));
  }
  const bad = response(request); bad.result.extra = true; assert.throws(() => validateWorkspaceReply(bad,request,null));
});

test('workspace rejects crossed form sessions and invalid nested snapshots', () => {
  const nested = {id:1,method:'form.hello',params:{}};
  const request = {id:2,method:'workspace.form',params:{session:'s1',request:nested}};
  assert.throws(() => validateWorkspaceReply(response(request,workspace(),{session:'s2',form:reply(nested)}),request,null));
  assert.throws(() => validateWorkspaceReply(response(request,workspace(),{session:'s1',form:reply(nested,{})}),request,null));
});

test('workspace serializes transport and terminal failure never replays queued requests', async () => {
  const gate = deferred(), seen = []; let failures = 0;
  const client = new WorkspaceClient(async request => { seen.push(request); await gate.promise; throw Error('lost'); },()=>{},()=>failures++);
  const first = client.request('workspace.hello',{}), second = client.request('workspace.list',{code:''});
  await Promise.resolve(); assert.equal(seen.length,1); gate.resolve();
  await assert.rejects(first); await assert.rejects(second); assert.equal(seen.length,1); assert.equal(failures,1); assert.equal(client.pending,0);
  const uncertain = new WorkspaceClient(async request => response(request,workspace({uncertain:true})));
  await assert.rejects(uncertain.request('workspace.hello',{})); assert.equal(uncertain.terminal,true);
});

test('tabs retain raw invalid drafts, focus and mounts without navigation RPCs', async () => {
  const {app,env,requests} = host(); await app.ready; await app.openForm(null);
  const first = app.mounts.get('s1'), node = all(first.panel).find(value=>value.tagName==='INPUT');
  node.value = 'bad decimal'; node.emit('input'); node.focus(); node.setSelectionRange(2,5);
  app.show(null); await app.openForm(null); const before = requests.length;
  app.show('s1'); assert.equal(app.mounts.get('s1'),first); assert.equal(node.value,'bad decimal');
  assert.equal(env.document.activeElement,node); assert.equal(node.selectionStart,2); assert.equal(requests.length,before);
  app.show('s2'); assert.equal(first.panel.hidden,true); assert.equal(app.pending(),true);
  const event = {prevented:false,preventDefault(){this.prevented=true;}}; env.listeners.get('beforeunload')(event); assert.equal(event.prevented,true);
});

test('closing a nested form removes only that tab and leaves workspace live', async () => {
  const {app} = host(); await app.ready; await app.openForm(null); await app.openForm(null);
  await app.mounts.get('s1').mount.run('close');
  assert.equal(app.mounts.has('s1'),false); assert.equal(app.mounts.has('s2'),true); assert.equal(app.client.terminal,false);
});

test('late open cannot activate after newer navigation', async () => {
  const gate = deferred(), env = environment();
  const app = mountWorkspace(env,env.document.root,async request => {
    if (request.method === 'workspace.hello') return response(request);
    if (request.method === 'workspace.open') { await gate.promise; return response(request,workspace({sessions:[{id:'s1',kind:'intake'}]}),{session:'s1',form:reply({id:1})}); }
    return response(request,workspace({sessions:[{id:'s1',kind:'intake'}]}),{session:'s1',form:reply(request.params.request)});
  });
  await app.ready; const opening = app.openForm(null); app.show(null); gate.resolve(); await opening;
  assert.equal(app.mounts.get('s1').panel.hidden,true);
});

test('malformed nested response locks every retained form and prevents refresh replay', async () => {
  const {app,requests} = host(); await app.ready; await app.openForm(null); await app.openForm(null);
  app.client.exchange = async request => response(request,workspace(),{session:'wrong',form:null});
  await app.mounts.get('s1').mount.refresh();
  assert.equal(app.client.terminal,true);
  for (const entry of app.mounts.values()) assert.equal(entry.mount.client.transportFailed,true);
  const before = requests.length; await app.mounts.get('s2').mount.refresh(); assert.equal(requests.length,before);
});

test('close workspace blocks hidden local drafts and clean open forms', async () => {
  const {app,env,requests} = host(); await app.ready; await app.openForm(null); app.show(null);
  const close = buttons(env.document).find(value=>value.textContent==='Close workspace'); close.emit('click');
  assert.equal(requests.some(value=>value.method==='workspace.close'),false);
  assert.ok(env.document.root.textContent.includes('Close each form tab'));
  const node = all(app.mounts.get('s1').panel).find(value=>value.tagName==='INPUT'); node.value='bad'; node.emit('input'); close.emit('click');
  assert.ok(env.document.root.textContent.includes('including hidden tabs'));
});

test('workspace bundle is closed and every source/output hash is current', async () => {
  const root = new URL('../',import.meta.url), target = new URL('../../yadinassi/ui/assets/workspace/',root);
  const manifest = JSON.parse(await readFile(new URL('build-manifest.json',target),'utf8'));
  assert.equal(manifest.schema,'yadinassi-workspace-assets/0');
  for (const [name,hash] of Object.entries(manifest.sources)) assert.equal(createHash('sha256').update(await readFile(new URL(name,root))).digest('hex'),hash,name);
  for (const [name,hash] of Object.entries(manifest.outputs)) assert.equal(createHash('sha256').update(await readFile(new URL(name,target))).digest('hex'),hash,name);
  assert.equal((await readdir(target)).length,5);
  const bundle = await readFile(new URL('app.js',target),'utf8');
  assert.equal(/^\s*(?:import|export)\s/m.test(bundle),false); assert.equal(/(?:localStorage|sessionStorage|innerHTML|eval\(|new Function)/.test(bundle),false);
});

test('blur generated by hiding a tab does not submit its draft', async () => {
  const {app,requests} = host(); await app.ready; await app.openForm(null);
  const entry = app.mounts.get('s1'), node = all(entry.panel).find(value=>value.tagName==='INPUT');
  node.value='2.00'; node.emit('input'); app.show(null); const before=requests.length;
  node.emit('blur',{relatedTarget:null}); await Promise.resolve();
  assert.equal(requests.length,before); assert.equal(entry.mount.view.hasDrafts(),true);
});

test('explicit intake discard abandons invalid drafts only after authoritative success', async () => {
  const {app,env} = host(); await app.ready; await app.openForm(null);
  const entry=app.mounts.get('s1'),node=all(entry.panel).find(value=>value.tagName==='INPUT'); node.value='bad'; node.emit('input');
  const discard=buttons(env.document).find(value=>value.textContent==='Discard new order');
  const gate=deferred(); let request;
  app.client.exchange=async incoming=>{request=incoming;await gate.promise;return response(incoming,workspace({revision:2}),{session:'s1'});};
  discard.emit('click'); await Promise.resolve(); assert.equal(request.method,'workspace.discard');
  assert.equal(app.mounts.has('s1'),true); assert.equal(node.value,'bad'); gate.resolve();
  await app.client.tail; await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  assert.equal(app.mounts.has('s1'),false); assert.equal(app.client.terminal,false);
});
