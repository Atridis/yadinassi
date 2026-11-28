import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL, ApplicationClient, validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from './application-fixtures.mjs';
import {environment, all, buttons} from '../../form/test/fake-dom.mjs';
import {reply as formReply} from '../../form/test/fixtures.mjs';
const legacyReceipt = 'a'.repeat(32);
const posting = () => ({session:'form-1',state:'uncertain',error:'outcome_unknown',posted:null});
const state = extra => ({kind:'application',lifecycle:'forms',messages:[],exitWarning:'',title:'Posting',
  entries:[{id:1,title:'Orders',kind:'posting-document'}],sessions:[{id:'form-1',entry:1,title:'Order'}],active:'form-1',uncertain:false,
  catalog:{entry:1,version:1,rows:[{key:'record-1',number:'001',date:'2026-11-11 12:00:00',deletionMark:false,posted:true}]},posting:[posting()],...extra});
const reply = (request,value=state(),extra={}) => ({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state:value,error:null,session:null,form:null,...extra}});

test('posting entry requires authoritative Boolean state and receipt-free envelope',()=>{
  const request={id:1,method:'application.hello',params:{}};
  assert.equal(validateApplicationReply(reply(request),request,null).state.catalog.rows[0].posted,true);
  for(const bad of [undefined,'true',1,null]) {
    const value=state();value.catalog.rows[0].posted=bad;
    assert.throws(()=>validateApplicationReply(reply(request,value),request,null));
  }
});
test('posting projection rejects cross-session and database journal payloads',()=>{
  const request={id:1,method:'application.hello',params:{}};
  for(const item of [{...posting(),session:'form-2'},{...posting(),receipt:'550e8400-e29b-41d4-a716-446655440000'},
      {...posting(),operationId:'private'},{...posting(),requests:[]},{...posting(),expectedRevision:2}])
    assert.throws(()=>validateApplicationReply(reply(request,state({posting:[item]})),request,null));
});
test('posting extension cannot disappear or appear after handshake',()=>{
  const request={id:1,method:'application.snapshot',params:{}};const missing=state();delete missing.posting;
  assert.throws(()=>validateApplicationReply(reply(request,missing),request,state()));
  assert.throws(()=>validateApplicationReply(reply(request),request,missing));
});
test('posting actions reject other owners, legacy receipts and the wrong outcome before transport',async()=>{
  const requests=[];const client=new ApplicationClient(async request=>{requests.push(request);return reply(request);});
  await client.request('application.hello',{});
  for(const [method,params] of [
    ['discardPosting',{session:'form-2'}],
    ['discardPosting',{session:'form-1',receipt:legacyReceipt}],
    ['refreshPosting',{session:'form-1'}],
  ]) await assert.rejects(client.request('application.'+method,params));
  assert.equal(requests.length,1);assert.equal(client.terminal,false);
});
test('posting refresh cannot be rebound to a sibling and discard must retire its owner',()=>{
  const refresh={id:1,method:'application.refreshPosting',params:{session:'form-1'}};
  assert.throws(()=>validateApplicationReply(reply(refresh,state(),{session:'form-2',form:formReply({id:1})}),refresh,null));
  const discard={id:1,method:'application.discardPosting',params:{session:'form-1'}};
  assert.throws(()=>validateApplicationReply(reply(discard,state(),{session:'form-1'}),discard,null));
  const retired=state({sessions:[],active:null,posting:[]});
  assert.doesNotThrow(()=>validateApplicationReply(reply(discard,retired,{session:'form-1'}),discard,state()));
});
test('posting list and explicit draft discard remain visible without leaking journal IDs',async()=>{
  const env=environment();
  const app=mountApplication(env,env.document.root,async request=>
    request.method==='application.form' ? reply(request,state(),{session:request.params.session,form:formReply(request.params.request)}) : reply(request));
  await app.ready;await Promise.all([...app.mounts.values()].map(entry=>entry.mount.ready));
  app.show('form-1');
  assert.ok(all(env.document.root).some(node=>node.textContent==='Posted'));
  assert.ok(buttons(env.document).some(node=>node.textContent==='Discard draft'));
  assert.equal(app.pending(),true);
  assert.ok(all(env.document.root).some(node=>node.textContent.includes('does not confirm the previous write')));
  assert.equal(all(env.document.root).some(node=>node.textContent.includes(legacyReceipt)),false);
});
test('pending Posted is unknown until authoritative refresh',()=>{
  const request={id:1,method:'application.hello',params:{}};
  for(const status of ['uncertain','committed']) {
    const item={...posting(),state:status};
    assert.doesNotThrow(()=>validateApplicationReply(reply(request,state({posting:[item]})),request,null));
    for(const posted of [true,false]) assert.throws(()=>validateApplicationReply(reply(request,state({posting:[{...item,posted}]})),request,null));
  }
  assert.throws(()=>validateApplicationReply(reply(request,state({posting:[{...posting(),state:'saved'}]})),request,null));
});
