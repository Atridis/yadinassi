import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL,ApplicationClient,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from '../src/app.mjs';
import {environment,all} from '../../form/test/fake-dom.mjs';
import {state,reply,field,button,deferred} from '../../form/test/fixtures.mjs';
const node=(id,owner=null,blocked=false)=>({id,entry:1,title:id,owner,blocked});
const before=()=>({kind:'application',lifecycle:'running',messages:[],exitWarning:'',title:'Owned forms',entries:[{id:1,title:'Form',kind:'form'}],sessions:[node('form-1',null,true),node('form-2','form-1')],active:'form-2',uncertain:false,catalog:null});
const envelope=(request,value=before(),extra={})=>({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state:value,error:null,session:null,form:null,updates:[],...extra}});
const request=()=>({id:3,method:'application.form',params:{session:'form-2',request:{id:7,method:'form.event',params:{event:'close'}}}});
const completed=()=>envelope(request(),{...before(),sessions:[node('form-1')],active:'form-1'}, {session:'form-2',form:reply({id:7},state(1,{kind:'closed',lifecycle:'closed',items:[]})),updates:[{session:'form-1',form:reply({id:1},state(2))}]});

test('owned graph and one authoritative retained-owner update are admitted',()=>{
  const value=validateApplicationReply(completed(),request(),before());
  assert.equal(value.updates[0].session,'form-1');
});
test('ownership rejects cycles, dangling owners and more than one child',()=>{
  for(const mutate of [s=>s.sessions[0].owner='form-2',s=>s.sessions[1].owner='form-8',s=>s.sessions.push(node('form-3','form-1'))]){
    const value=before();mutate(value);assert.throws(()=>validateApplicationReply(envelope({id:1},value),{id:1,method:'application.hello'},null));
  }
});
test('blocked state is exactly derived from a live owned child',()=>{
  for(const mutate of [s=>s.sessions[0].blocked=false,s=>s.sessions[1].blocked=true,s=>s.sessions[1].blocked='yes']){
    const value=before();mutate(value);assert.throws(()=>validateApplicationReply(envelope({id:1},value),{id:1,method:'application.hello'},null));
  }
});
test('retained owner identity cannot be rebound and posting owners are excluded',()=>{
  const next=before();next.sessions[1].owner=null;next.sessions[0].blocked=false;
  assert.throws(()=>validateApplicationReply(envelope({id:1},next),{id:1,method:'application.snapshot'},before()));
  const posting=before();posting.entries[0].kind='posting-document';
  assert.throws(()=>validateApplicationReply(envelope({id:1},posting),{id:1,method:'application.hello'},null));
});
test('completion updates reject duplicates, retired or original targets and malformed envelopes',()=>{
  for(const mutate of [r=>r.updates.push(r.updates[0]),r=>r.updates[0].session='form-8',r=>r.updates[0].session='form-2',
    r=>r.updates[0].form.id=2,r=>r.updates[0].form.result.state=state(2,{kind:'closed',lifecycle:'closed',items:[]}),r=>r.updates[0].handler='Run']){
    const value=completed();mutate(value.result);assert.throws(()=>validateApplicationReply(value,request(),before()));
  }
});
test('completion requires a previously blocked owner whose child actually retired',()=>{
  const old=before();old.sessions[0].blocked=false;old.sessions[1].owner=null;
  assert.throws(()=>validateApplicationReply(completed(),request(),old));
  const value=completed();value.result.state=before();value.result.session=null;value.result.form=null;
  assert.throws(()=>validateApplicationReply(value,{id:3,method:'application.snapshot'},before()));
});
test('completion callback failure retains its snapshot instead of requiring replay',()=>{
  const value=completed();value.result.error='completion_failed';value.result.updates[0].form.result.error='event_failed';
  assert.equal(validateApplicationReply(value,request(),before()).updates[0].form.result.state.revision,2);
});
test('owned-results capability cannot disappear even when the family is empty',async()=>{
  let owned=true;const client=new ApplicationClient(async req=>{
    const value=envelope(req,{...before(),sessions:[],active:null});if(!owned)delete value.result.updates;return value;
  });
  await client.request('application.hello',{});owned=false;
  await assert.rejects(client.request('application.snapshot',{}));assert.equal(client.terminal,true);
});
test('blocked owner events are refused before transport without terminal locking',async()=>{
  let calls=0;const client=new ApplicationClient(async req=>{calls++;return envelope(req);});await client.request('application.hello',{});
  for(const event of ['change','command','close'])await assert.rejects(client.form('form-1',{id:1,method:'form.event',params:{event}}),e=>e.preDispatch===true&&e.code==='owned_child_open');
  await assert.rejects(client.reference('form-1',0,{action:'begin'}),e=>e.preDispatch===true);
  assert.equal(calls,1);assert.equal(client.terminal,false);
});
test('backward owner update revision locks without applying the reply',async()=>{
  let done=false;const client=new ApplicationClient(async req=>done?{...completed(),id:req.id}:envelope(req));
  await client.request('application.hello',{});client.formRevisions.set('form-1',3);done=true;
  await assert.rejects(client.form('form-2',request().params.request));assert.equal(client.terminal,true);assert.equal(client.state.sessions.length,2);
});
test('lost completed close response locks once and never replays queued work',async()=>{
  const wait=deferred();let calls=0,lose=false;const client=new ApplicationClient(async req=>{calls++;if(lose){await wait.promise;throw Error('lost');}return envelope(req);});
  await client.request('application.hello',{});lose=true;
  const close=client.form('form-2',request().params.request),later=client.request('application.snapshot',{});wait.resolve();
  await assert.rejects(close);await assert.rejects(later);assert.equal(calls,2);assert.equal(client.terminal,true);
});

async function mounted(error=null){
  const env=environment(),seen=[];let value={...before(),sessions:[node('form-1')],active:'form-1'};
  const snapshot=(revision=0,text='original')=>state(revision,{items:[field('Name',{type:'String',value:text}),button('Choose')]});
  const exchange=async req=>{
    seen.push(req);const result=envelope(req,value);
    if(req.method==='application.form'){
      const nested=req.params.request,sid=req.params.session;
      result.result.session=sid;result.result.form=reply(nested,snapshot());
      if(nested.params?.event==='command'){
        value=before();result.result.state=value;result.result.form=reply(nested,snapshot(1));
      }else if(nested.params?.event==='close'){
        value={...before(),sessions:[node('form-1')],active:'form-1'};
        Object.assign(result.result,{state:value,error:error?'completion_failed':null,form:reply(nested,state(1,{kind:'closed',lifecycle:'closed',items:[]})),
          updates:[{session:'form-1',form:reply({id:1},snapshot(2,'confirmed result'),error)}]});
      }
    }
    return result;
  };
  const app=mountApplication(env,env.document.root,exchange);await app.ready;await Promise.all([...app.mounts.values()].map(x=>x.mount.ready));
  const owner=app.mounts.get('form-1'),input=all(owner.panel).find(x=>x.tagName==='INPUT');input.value='  unsent text  ';input.emit('input');
  await app.client.form('form-1',{id:4,method:'form.event',params:{event:'command',control:'Choose',revision:0}});
  await Promise.all([...app.mounts.values()].map(x=>x.mount.ready));
  return {app,env,seen,owner,input};
}
test('mounted owner pauses all business controls and close while keeping raw text',async()=>{
  const {app,seen,owner,input}=await mounted();const count=seen.length;
  assert.equal(input.disabled,true);assert.equal(input.value,'  unsent text  ');assert.equal(owner.ownerNotice.hidden,false);assert.ok(owner.panel.contains(owner.ownerNotice));assert.ok(owner.panel.textContent.includes('This form is paused'));assert.ok(owner.panel.textContent.includes('Paused'));
  await owner.mount.run('change','Name');await owner.mount.run('command','Choose');await owner.mount.run('close');await owner.mount.refresh();
  assert.equal(seen.length,count);assert.equal(app.client.terminal,false);
});
test('mounted completion preserves conflicting raw text in recovery without issuing refresh',async()=>{
  const {app,seen,owner,input}=await mounted();const count=seen.length;
  await app.mounts.get('form-2').mount.run('close');
  assert.equal(app.mounts.size,1);assert.equal(app.client.terminal,false);assert.equal(owner.mount.client.snapshot.revision,2);
  assert.equal(owner.mount.client.snapshot.items[0].value.value,'confirmed result');assert.equal(input.value,'confirmed result');
  assert.ok(owner.panel.textContent.includes('Name:   unsent text  '));assert.equal(owner.mount.view.hasDrafts(),true);
  assert.equal(input.disabled,true);assert.equal(owner.ownerNotice.hidden,true);assert.equal(seen.length,count+1);
});
test('mounted callback error retains effects and drafts without terminal lock or replay',async()=>{
  const {app,seen,owner,input}=await mounted('event_failed');const count=seen.length;
  await app.mounts.get('form-2').mount.run('close');
  assert.equal(owner.mount.client.snapshot.items[0].value.value,'confirmed result');assert.equal(input.value,'confirmed result');
  assert.ok(owner.panel.textContent.includes('Name:   unsent text  '));assert.equal(owner.mount.view.hasDrafts(),true);
  assert.equal(app.client.terminal,false);assert.equal(seen.length,count+1);assert.match(owner.panel.textContent,/failed|error/i);
});
