import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL,DIALOG_CAPABILITY,ApplicationClient,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from '../src/app.mjs';
import {environment,all} from '../../form/test/fake-dom.mjs';
import {state,reply,field,button,deferred} from '../../form/test/fixtures.mjs';
const ticket='a'.repeat(32), hello={protocol:APPLICATION_PROTOCOL,dialogCapability:DIALOG_CAPABILITY};
const descriptor=extra=>({ticket,owner:'form-1',kind:'question',title:'Confirm',text:'Continue?',choices:['yes','no','cancel'],...extra});
const snapshot=(blocked=true)=>({kind:'application',lifecycle:'running',messages:[],exitWarning:'',title:'Dialogs',
  entries:[{id:1,title:'Owner',kind:'form'}],sessions:[{id:'form-1',entry:1,title:'Owner',owner:null,blocked}],
  active:'form-1',uncertain:false,catalog:null});
const envelope=(request,dialogs=[descriptor()],extra={})=>({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,
  dialogCapability:DIALOG_CAPABILITY,dialogs,state:snapshot(dialogs.length>0),error:null,session:null,form:null,updates:[],...extra}});
const req=(method='application.hello',params=hello)=>({id:1,method,params});
const answer={session:'form-1',ticket,answer:'yes'};
const form=(revision=0,value='original')=>state(revision,{items:[field('Name',{type:'String',value}),button('Ask')]});

test('negotiated descriptors pause only their live owner with a closed wire shape',()=>{
  const value=validateApplicationReply(envelope(req()),req(),null);assert.equal(value.dialogs[0].ticket,ticket);
  assert.equal(value.state.sessions[0].blocked,true);
});
test('forms-only negotiated host admits only empty dialogs without owned graph',()=>{
  const value=envelope(req(),[]);delete value.result.updates;delete value.result.state.sessions[0].owner;delete value.result.state.sessions[0].blocked;
  assert.equal(validateApplicationReply(value,req(),null).dialogs.length,0);
  value.result.dialogs=[descriptor()];assert.throws(()=>validateApplicationReply(value,req(),null));
});
test('dialog descriptors reject extra identity, unsafe strings and invented outcomes',()=>{
  for(const patch of [{callback:'private'},{ticket:'x'},{title:'x'.repeat(257)},{text:'\u0000'},{text:'\ud800'},
    {choices:['yes','yes']},{choices:['yes','no','retry']},{kind:'warning',choices:['ok']},{kind:'html'}]){
    assert.throws(()=>validateApplicationReply(envelope(req(),[descriptor(patch)]),req(),null));
  }
});
test('dialog graph rejects duplicate tickets, duplicate owners and unbound owners',()=>{
  for(const dialogs of [[descriptor(),descriptor()],[descriptor(),descriptor({ticket:'b'.repeat(32)})],[descriptor({owner:'form-99'})]])
    assert.throws(()=>validateApplicationReply(envelope(req(),dialogs),req(),null));
  const value=envelope(req());value.result.state.sessions[0].blocked=false;assert.throws(()=>validateApplicationReply(value,req(),null));
});
test('owner cannot simultaneously own a form and a pending dialog',()=>{
  const value=envelope(req());value.result.state.sessions.push({id:'form-2',entry:1,title:'Child',owner:'form-1',blocked:false});
  assert.throws(()=>validateApplicationReply(value,req(),null));
});
test('production negotiation requires echo and rejects unsolicited extension on legacy client',async()=>{
  const missing=new ApplicationClient(async request=>{const value=envelope(request,[]);delete value.result.dialogs;delete value.result.dialogCapability;return value;});
  await assert.rejects(missing.request('application.hello',hello));assert.equal(missing.terminal,true);
  const legacy=new ApplicationClient(async request=>envelope(request,[]));await assert.rejects(legacy.request('application.hello',{protocol:APPLICATION_PROTOCOL}));
});
test('capability cannot disappear after an empty negotiated handshake',async()=>{
  let omit=false;const client=new ApplicationClient(async request=>{const value=envelope(request,[]);if(omit){delete value.result.dialogCapability;delete value.result.dialogs;}return value;});
  await client.request('application.hello',hello);omit=true;await assert.rejects(client.request('application.snapshot',{}));assert.equal(client.terminal,true);
});
test('same ticket cannot mutate its owner, content or choices',async()=>{
  for(const patch of [{text:'Changed'},{choices:['yes','no']},{kind:'warning',choices:['dismiss']}]){
    let changed=false;const client=new ApplicationClient(async request=>envelope(request,[descriptor(changed?patch:{})]));
    await client.request('application.hello',hello);changed=true;await assert.rejects(client.request('application.snapshot',{}));assert.equal(client.terminal,true);
  }
});
test('invalid answer or owner is refused locally without consuming a live prompt',async()=>{
  let calls=0;const client=new ApplicationClient(async request=>{calls++;return envelope(request);});await client.request('application.hello',hello);
  for(const patch of [{answer:'retry'},{ticket:'b'.repeat(32)},{session:'form-2'},{extra:true}])
    await assert.rejects(client.request('application.answerDialog',{...answer,...patch}),e=>e.preDispatch===true);
  assert.equal(calls,1);assert.equal(client.terminal,false);assert.equal(client.dialogs.length,1);
});
test('owner event is paused but snapshot is permitted',async()=>{
  let calls=0;const client=new ApplicationClient(async request=>{calls++;return envelope(request,undefined,request.method==='application.form'?{session:'form-1',form:reply(request.params.request,form())}:{});});
  await client.request('application.hello',hello);
  await assert.rejects(client.form('form-1',{id:1,method:'form.event',params:{event:'close'}}),e=>e.code==='dialog_pending');
  await assert.rejects(client.form('form-2',{id:1,method:'form.event',params:{event:'command'}}),e=>e.code==='dialog_pending');
  await assert.rejects(client.request('application.open',{entry:1,request:'later'}),e=>e.code==='dialog_pending');
  await client.form('form-1',{id:1,method:'form.snapshot',params:{}});assert.equal(calls,2);
});
test('double answer retires its ticket before a queued second answer can dispatch',async()=>{
  const held=deferred();let calls=0;const client=new ApplicationClient(async request=>{
    calls++;if(request.method==='application.answerDialog'){await held.promise;return envelope(request,[],{session:'form-1',form:reply({id:1},form(1,'yes'))});}return envelope(request);
  });await client.request('application.hello',hello);
  const first=client.request('application.answerDialog',answer),second=client.request('application.answerDialog',answer);held.resolve();
  await first;await assert.rejects(second,e=>e.preDispatch===true);assert.equal(calls,2);assert.equal(client.terminal,false);
});
test('retired dialog cannot resurrect even with unchanged public contents',async()=>{
  let phase=0;const client=new ApplicationClient(async request=>envelope(request,phase===1?[]:[descriptor()]));
  await client.request('application.hello',hello);phase=1;await client.request('application.snapshot',{});phase=2;
  await assert.rejects(client.request('application.snapshot',{}));assert.equal(client.terminal,true);
});
test('lost answer reply locks queued work without retrying callback delivery',async()=>{
  let calls=0;const client=new ApplicationClient(async request=>{calls++;if(request.method==='application.answerDialog')throw Error('lost');return envelope(request);});
  await client.request('application.hello',hello);const first=client.request('application.answerDialog',answer),second=client.request('application.snapshot',{});
  await assert.rejects(first);await assert.rejects(second);assert.equal(calls,2);assert.equal(client.terminal,true);
});
async function mounted({lose=false,error=null}={}){
  const env=environment(),seen=[],held=deferred();let dialogs=[],revision=0,value='original';
  const app=mountApplication(env,env.document.root,async request=>{
    seen.push(request);assert.notEqual(request.method,'application.retry');
    const extra={};
    if(request.method==='application.hello')assert.equal(request.params.dialogCapability,DIALOG_CAPABILITY);
    if(request.method==='application.form'){
      const nested=request.params.request;if(nested.params?.event==='command'){dialogs=[descriptor({text:'<img src=x> Continue?'})];revision++;}
      Object.assign(extra,{session:'form-1',form:reply(nested,form(revision,value))});
    }
    if(request.method==='application.answerDialog'){
      await held.promise;if(lose)throw Error('lost after execution');dialogs=[];revision++;value='confirmed';
      Object.assign(extra,{session:'form-1',error:error?'completion_failed':null,form:reply({id:1},form(revision,value),error)});
    }
    return {...envelope(request,dialogs,extra),result:{...envelope(request,dialogs,extra).result,inputCapability:'yadinassi-owned-input/1',inputs:[]}};
  });await app.ready;await app.mounts.get('form-1').mount.ready;
  const owner=app.mounts.get('form-1'),input=all(owner.panel).find(n=>n.tagName==='INPUT');
  // A sibling/retained raw draft is never implicitly sent by an answer.
  input.value='  unsent text  ';input.emit('input');
  await app.client.form('form-1',{id:9,method:'form.event',params:{event:'command',control:'Ask',revision:0}});
  // Direct client dispatch bypasses the mount's usual finish repaint.
  app.show('form-1',false);
  const modal=all(env.document.root).find(n=>n.className==='configuration-dialog');
  return {app,env,seen,held,owner,input,modal};
}
test('renderer uses literal prompt, disables owner and traps focus without Escape answering',async()=>{
  const {app,env,seen,owner,input,modal}=await mounted();const before=seen.length;
  assert.equal(modal.hidden,false);assert.equal(modal.getAttribute('aria-modal'),'true');assert.ok(modal.textContent.includes('<img src=x>'));
  assert.equal(all(modal).some(n=>n.tagName==='IMG'),false);assert.equal(input.disabled,true);assert.equal(input.value,'  unsent text  ');
  assert.ok(owner.panel.textContent.includes('paused for a dialog'));
  modal.emit('keydown',{key:'Escape'});await app.client.tail;assert.equal(seen.length,before);
  const buttons=all(modal).filter(n=>n.tagName==='BUTTON');buttons.at(-1).focus();let prevented=false;
  modal.emit('keydown',{key:'Tab',preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(env.document.activeElement,buttons[0]);
});
test('confirmed answer adopts authoritative state and preserves conflicting raw text without refresh',async()=>{
  const {app,seen,held,owner,input,modal}=await mounted();const count=seen.length;
  const yes=all(modal).find(n=>n.dataset.dialogAnswer==='yes');yes.emit('click');yes.emit('click');held.resolve();await app.client.tail;await Promise.resolve();
  assert.equal(seen.length,count+1);assert.equal(modal.hidden,true);assert.equal(owner.mount.client.snapshot.revision,2);
  assert.equal(input.value,'confirmed');assert.ok(owner.panel.textContent.includes('Name:   unsent text  '));assert.equal(app.client.terminal,false);
});
test('known completion failure keeps its partial effects and does not replay or lock family',async()=>{
  const {app,seen,held,owner,modal}=await mounted({error:'event_failed'});const count=seen.length;
  all(modal).find(n=>n.dataset.dialogAnswer==='no').emit('click');held.resolve();await app.client.tail;await Promise.resolve();
  assert.equal(seen.length,count+1);assert.equal(app.client.terminal,false);assert.equal(owner.mount.client.snapshot.items[0].value.value,'confirmed');
});
test('transport uncertainty locks all business yet leaves retained text and no retry affordance',async()=>{
  const {app,seen,held,owner,input,modal}=await mounted({lose:true});const count=seen.length;
  const yes=all(modal).find(n=>n.dataset.dialogAnswer==='yes');yes.emit('click');held.resolve();await app.client.tail;await Promise.resolve();
  yes.emit('click');await app.client.tail;assert.equal(seen.length,count+1);assert.equal(app.client.terminal,true);
  assert.equal(owner.mount.client.locked,true);assert.equal(input.value,'  unsent text  ');assert.equal(modal.getAttribute('aria-modal'),'false');
});
