import test from 'node:test';
import assert from 'node:assert/strict';
import {all,buttons} from '../../form/test/fake-dom.mjs';
import {deferred} from '../../form/test/fixtures.mjs';
import {host,findInput,edit,unload,tick,ownerEntry,childEntry} from './fixtures.mjs';
const command = (entry,name) => entry.mount.run('command',name);
async function opened() { const result=host(); await result.app.ready; await result.app.openForm(null); return result; }
async function choose(app,name='ChooseCustomerButton') {
  await command(ownerEntry(app),name); await app.settled(); return childEntry(app);
}
const events = requests => requests.filter(request=>request.method==='workspace.form').map(request=>request.params.request);

test('owner validates the complete raw draft before opening a choice', async () => {
  const {app,requests}=await opened(), owner=ownerEntry(app);
  edit(findInput(owner,'FieldCode'),'NEW00001'); edit(findInput(owner,'Quantity, row 1'),'not decimal');
  const before=requests.length; await command(owner,'ChooseCustomerButton'); await app.settled();
  assert.equal(requests.length,before); assert.equal(childEntry(app),undefined); assert.equal(owner.mount.view.hasDrafts(),true);
  assert.equal(findInput(owner,'Quantity, row 1').value,'not decimal'); assert.equal(app.client.terminal,false);
});

test('valid cell draft flushes before a single child command and separate child hello', async () => {
  const {app,requests}=await opened(), owner=ownerEntry(app);
  edit(findInput(owner,'Quantity, row 1'),'2.50'); const before=requests.length;
  const first=command(owner,'ChooseCustomerButton'); await command(owner,'ChooseCustomerButton'); await first; await app.settled();
  assert.deepEqual(events(requests.slice(before)).map(request=>[request.method,request.params.event,request.params.control]),[
    ['form.event','cell','LinesTable'],['form.event','command','ChooseCustomerButton'],['form.hello',undefined,undefined]]);
  assert.equal(events(requests.slice(before))[1].params.revision,1);
  assert.equal(owner.mount.view.hasDrafts(),false); assert.equal(app.mounts.size,2); assert.equal(childEntry(app).owner,owner.id);
  assert.equal(owner.fieldset.disabled,true); assert.equal(owner.panel.inert,true);
});

test('child completion removes only the child and freezes owner through successful refresh', async () => {
  const {app,env,requests,exchange}=await opened(), owner=ownerEntry(app), child=await choose(app);
  const gate=deferred(); let refreshing=false;
  app.client.exchange=async request=>{
    if (request.method==='workspace.form' && request.params.session===owner.id && request.params.request.method==='form.snapshot') {refreshing=true;await gate.promise;}
    return exchange(request);
  };
  const before=requests.length; const choosing=command(child,'ChooseButton'); await command(child,'ChooseButton'); await choosing; await tick();
  assert.equal(refreshing,true); assert.equal(app.mounts.has(child.id),false); assert.equal(app.mounts.get(owner.id),owner);
  assert.equal(owner.fieldset.disabled,true); assert.equal(owner.panel.inert,true); assert.equal(unload(env).prevented,true);
  const count=requests.length; await app.openForm(null); assert.equal(requests.length,count);
  gate.resolve(); await app.settled();
  assert.equal(owner.fieldset.disabled,false); assert.equal(owner.panel.inert,false);
  assert.equal(findInput(owner,'FieldCustomer').value,'Chosen customer');
  assert.deepEqual(events(requests.slice(before)).map(request=>[request.method,request.params.control]),[['form.event','ChooseButton'],['form.snapshot',undefined]]);
});

test('Cancel and ordinary close each preserve owner values and perform exactly one refresh', async () => {
  for (const completion of ['CancelButton','close']) {
    const {app,requests}=await opened(), owner=ownerEntry(app), child=await choose(app);
    const before=requests.length;
    await (completion==='close'?child.mount.run('close'):command(child,completion)); await app.settled();
    assert.equal(childEntry(app),undefined); assert.equal(findInput(owner,'FieldCustomer').value,'');
    assert.equal(owner.fieldset.disabled,false); assert.equal(app.client.terminal,false);
    assert.deepEqual(events(requests.slice(before)).map(request=>request.method),['form.event','form.snapshot']);
  }
});

test('product choice uses current row and browser payload carries only local IDs and scalars', async () => {
  const {app,requests}=await opened(), owner=ownerEntry(app);
  await owner.mount.run('select','LinesTable',1); const child=await choose(app,'ChooseProductButton');
  await child.mount.run('select','ChoicesTable',1); await command(child,'ChooseButton'); await app.settled();
  assert.equal(findInput(owner,'Product, row 1').value,'Chosen product');
  const select=events(requests).find(request=>request.params.control==='LinesTable' && request.params.event==='select');
  assert.equal(select.params.row,1);
  for (const request of requests) assert.equal(/CatalogKey|record_id|database_id|callback|target_catalog/i.test(JSON.stringify(request)),false);
});

test('owner blur and synthetic mutations cannot bypass a live child boundary', async () => {
  const {app,requests}=await opened(), owner=ownerEntry(app); await choose(app);
  const node=findInput(owner,'Quantity, row 1'), before=requests.length;
  node.emit('blur',{relatedTarget:null}); await tick(); assert.equal(requests.length,before);
  await command(owner,'SaveOrderButton'); await app.settled();
  assert.equal(requests.length,before); assert.equal(app.client.terminal,true); assert.equal(owner.fieldset.disabled,true);
});

test('lost child completion preserves mounted forms and never replays choice or owner refresh', async () => {
  const {app,env}=await opened(), owner=ownerEntry(app), child=await choose(app); let sent=0;
  app.client.exchange=async ()=>{sent++;throw Error('lost response');};
  await command(child,'ChooseButton'); await app.settled();
  await command(child,'ChooseButton'); await owner.mount.refresh(); await child.mount.refresh();
  assert.equal(sent,1); assert.equal(app.client.terminal,true); assert.equal(app.mounts.size,2);
  assert.equal(owner.fieldset.disabled,true); assert.equal(child.fieldset.disabled,true); assert.equal(unload(env).prevented,true);
});

test('lost, malformed or recoverably failed owner refresh never unfreezes after child dismissal', async () => {
  for (const failure of ['lost','malformed','recoverable','unknown']) {
    const {app,exchange}=await opened(), owner=ownerEntry(app), child=await choose(app); let reads=0;
    app.client.exchange=async request=>{
      if (request.params.session===owner.id && request.params.request?.method==='form.snapshot') {
        reads++; if (failure==='lost') throw Error('lost');
        const result=await exchange(request);
        if (failure==='malformed') result.result.session='wrong';
        if (failure==='recoverable') result.result.form.result.error='event_failed';
        if (failure==='unknown') result.result.form.result.error='outcome_unknown';
        return result;
      }
      return exchange(request);
    };
    await command(child,'ChooseButton'); await app.settled(); await owner.mount.refresh();
    assert.equal(childEntry(app),undefined,failure); assert.equal(app.client.terminal,true,failure);
    assert.equal(owner.fieldset.disabled,true,failure); assert.equal(reads,1,failure);
  }
});

test('workspace closure and unload guard include raw drafts, dirty state and open choices', async () => {
  const {app,env,requests}=await opened(), owner=ownerEntry(app);
  const close=buttons(env.document).find(node=>node.textContent==='Close workspace');
  assert.equal(unload(env).prevented,false); close.emit('click');
  assert.equal(requests.some(request=>request.method==='workspace.close'),false); assert.match(env.document.root.textContent,/Close the order form/);
  edit(findInput(owner,'Quantity, row 1'),'bad'); assert.equal(unload(env).prevented,true); close.emit('click');
  assert.match(env.document.root.textContent,/Save or discard pending edits/);
  await command(owner,'DiscardButton'); assert.equal(unload(env).prevented,false);
  edit(findInput(owner,'Quantity, row 1'),'2.00'); await owner.mount.run('change',{control:'LinesTable',row:1,column:'Quantity'});
  assert.equal(owner.mount.view.hasDrafts(),false); assert.equal(unload(env).prevented,true);
  await command(owner,'SaveOrderButton'); assert.equal(unload(env).prevented,false);
  const child=await choose(app); assert.equal(unload(env).prevented,true);
  await command(child,'CancelButton'); await app.settled(); await owner.mount.run('close'); await app.settled();
  assert.equal(app.mounts.size,0); close.emit('click'); await tick();
  assert.equal(app.client.state.kind,'closed'); assert.equal(unload(env).prevented,false);
});

test('modal has unique labels and traps Tab, Shift-Tab and Escape without duplicate completion', async () => {
  const {app,env,requests}=await opened(), owner=ownerEntry(app);
  const previous=findInput(owner,'Quantity, row 1'); previous.focus(); owner.panel.emit('focusin',{target:previous});
  const child=await choose(app);
  assert.equal(child.panel.getAttribute('role'),'dialog'); assert.equal(child.panel.getAttribute('aria-modal'),'true');
  assert.equal(env.document.getElementById(child.panel.getAttribute('aria-labelledby')).textContent,'Choose a reference');
  assert.equal(child.panel.contains(env.document.activeElement),true);
  const nodes=all(child.panel).filter(node=>!node.disabled&&!node.hidden&&!node.closest('[hidden]')&&(['BUTTON','INPUT','SELECT','TEXTAREA'].includes(node.tagName)||node.tabIndex===0));
  const first=nodes[0],last=nodes.at(-1); last.focus(); child.panel.emit('keydown',{key:'Tab'}); assert.equal(env.document.activeElement,first);
  first.focus(); child.panel.emit('keydown',{key:'Tab',shiftKey:true}); assert.equal(env.document.activeElement,last);
  const ids=all(env.document.root).map(node=>node.id).filter(Boolean); assert.equal(new Set(ids).size,ids.length);
  for (const entry of [owner,child]) for (const node of all(entry.panel)) {
    for (const id of (node.getAttribute('aria-describedby')||'').split(' ').filter(Boolean)) assert.equal(entry.panel.contains(env.document.getElementById(id)),true);
    if (node.htmlFor) assert.equal(entry.panel.contains(env.document.getElementById(node.htmlFor)),true);
  }
  const before=requests.length;
  child.panel.emit('keydown',{key:'Escape'}); child.panel.emit('keydown',{key:'Escape'}); await tick(); await app.settled();
  assert.equal(childEntry(app),undefined); assert.equal(env.document.activeElement,previous);
  assert.equal(events(requests.slice(before)).filter(request=>request.params.event==='close').length,1);
});

test('duplicate opens coalesce and reopening a closed order uses a fresh session and request token', async () => {
  const {app,requests,exchange}=host(); await app.ready; const gate=deferred();
  app.client.exchange=async request=>{if(request.method==='workspace.open')await gate.promise;return exchange(request);};
  const first=app.openForm(null), duplicate=app.openForm(null); assert.equal(first,duplicate); gate.resolve(); await first;
  const owner=ownerEntry(app); await app.openForm(null); assert.equal(app.mounts.size,1);
  await owner.mount.run('close'); await app.settled(); await app.openForm(null);
  const opens=requests.filter(request=>request.method==='workspace.open');
  assert.equal(opens.length,2); assert.notEqual(opens[0].params.request,opens[1].params.request); assert.notEqual(ownerEntry(app).id,owner.id);
});

test('repeated list clicks are disabled synchronously and list filters are literal strings', async () => {
  const {app,env,requests,exchange}=host(); await app.ready; const gate=deferred();
  app.client.exchange=async request=>{if(request.method==='workspace.list')await gate.promise;return exchange(request);};
  const search=all(env.document.root).find(node=>node.tagName==='INPUT'); search.value='X<>&';
  const refresh=buttons(env.document).find(node=>node.textContent==='Find / Refresh orders');
  refresh.emit('click'); refresh.emit('click'); assert.equal(refresh.disabled,true); assert.equal(search.disabled,true);
  gate.resolve(); await tick();
  assert.deepEqual(requests.filter(request=>request.method==='workspace.list').map(request=>request.params),[{code:'X<>&'}]);
  assert.equal(refresh.disabled,false);
});

test('failed child hello locks the owner and keeps the failed child visible without retry', async () => {
  const {app,exchange}=await opened(), owner=ownerEntry(app); let hellos=0;
  app.client.exchange=async request=>{
    if (request.params.request?.method==='form.hello') {hellos++;throw Error('child unavailable');}
    return exchange(request);
  };
  await choose(app); await app.settled();
  assert.equal(app.client.terminal,true); assert.equal(owner.fieldset.disabled,true); assert.equal(app.mounts.size,2);
  await childEntry(app).mount.refresh(); assert.equal(hellos,1);
});
