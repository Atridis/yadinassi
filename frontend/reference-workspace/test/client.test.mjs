import test from 'node:test';
import assert from 'node:assert/strict';
import {ReferenceClient, validateReferenceReply, REFERENCE_PROTOCOL} from '../src/client.mjs';
import {reply, state, deferred} from '../../form/test/fixtures.mjs';
import {workspace, response, order, choice} from './fixtures.mjs';
const hello = {id:1,method:'workspace.hello',params:{protocol:REFERENCE_PROTOCOL}};
const nested = (session='o1', control='ChooseCustomerButton') => ({id:2,method:'workspace.form',params:{session,request:{id:2,method:'form.event',params:{event:'command',control,revision:0}}}});
const opened = (id='o1',revision=0) => workspace({revision,sessions:[order(id)]});

test('reference protocol accepts only exact bounded envelopes and display rows', () => {
  assert.equal(validateReferenceReply(response(hello),hello,null).state.kind,'workspace');
  for (const changes of [{revision:-1},{revision:Number.MAX_SAFE_INTEGER+1},{orders:Array(33).fill({})},{sessions:Array(3).fill(order())},
    {uncertain:'false'},{truncated:0},{kind:'form'},{extra:1}]) assert.throws(()=>validateReferenceReply(response(hello,workspace(changes)),hello,null));
  const row = {id:1,code:'O1',description:'<img onerror=evil()>',total:{type:'Number',value:'12.00'}};
  assert.equal(validateReferenceReply(response(hello,workspace({orders:[row]})),hello,null).state.orders[0].description,row.description);
  for (const change of [{id:0},{code:'x'.repeat(9)},{description:'x'.repeat(65)},{total:{type:'CatalogKey',value:'secret'}},{key:'secret'}])
    assert.throws(()=>validateReferenceReply(response(hello,workspace({orders:[{...row,...change}]})),hello,null));
  assert.throws(()=>validateReferenceReply(response(hello,workspace({orders:[row,row]})),hello,null));
  const withUpdates=response(hello); withUpdates.result.updates=[]; assert.throws(()=>validateReferenceReply(withUpdates,hello,null));
  const wrong=response(hello); wrong.id=9; assert.throws(()=>validateReferenceReply(wrong,hello,null));
});

test('session descriptors enforce a single immutable owner and owned child', () => {
  const request=nested(), previous=opened();
  assert.equal(validateReferenceReply(response(request,workspace({sessions:[order(),choice()]}),{session:'o1',form:reply(request.params.request)}),request,previous).state.sessions.length,2);
  for (const sessions of [[choice()],[order(),choice('c1','other')],[order(),order('o2')],[order(),choice(),choice('c2')],
    [{...order(),key:'secret'}],[{...order(),owner:'o1'}],[order(),{...choice(),kind:'editor'}]]) {
    assert.throws(()=>validateReferenceReply(response(request,workspace({sessions}),{session:'o1',form:reply(request.params.request)}),request,previous));
  }
  const prior=workspace({sessions:[order(),choice()]});
  assert.throws(()=>validateReferenceReply(response(nested('c1'),workspace({sessions:[order('o2'),choice('c1','o2')]}),{session:'c1',form:reply({id:2})}),nested('c1'),prior));
});

test('child additions and session removals require the matching authoritative operation', () => {
  const request=nested(), previous=opened();
  for (const control of ['SaveOrderButton','ChooseButton']) {
    const other=nested('o1',control);
    assert.throws(()=>validateReferenceReply(response(other,workspace({sessions:[order(),choice()]}),{session:'o1',form:reply(other.params.request)}),other,previous));
  }
  assert.throws(()=>validateReferenceReply(response(hello,workspace({sessions:[order(),choice()]})),hello,previous));
  assert.throws(()=>validateReferenceReply(response(request,workspace(),{session:'o1',form:reply(request.params.request)}),request,previous));
  assert.throws(()=>validateReferenceReply(response(hello,workspace()),hello,previous));
});

test('nested replies reject crossed sessions, reply IDs, stale revisions and forged scalar references', () => {
  const request=nested(), previous=opened();
  for (const changes of [{session:'c1'},{form:reply({id:99})},{form:reply({id:2},{})},{form:null}]) {
    assert.throws(()=>validateReferenceReply(response(request,previous,{session:'o1',form:reply({id:2}),...changes}),request,previous));
  }
  assert.throws(()=>validateReferenceReply(response(request,workspace({revision:1,sessions:[order()]}),{session:'o1',form:reply({id:2})}),request,opened('o1',2)));
  const bad=state(); bad.items[0].value={type:'CatalogKey',value:'secret'};
  assert.throws(()=>validateReferenceReply(response(request,previous,{session:'o1',form:reply({id:2},bad)}),request,previous));
});

test('open requires one valid owner snapshot and closed workspaces contain no sessions', () => {
  const request={id:2,method:'workspace.open',params:{revision:0,row:null,request:'open-1'}};
  const valid=response(request,opened(),{session:'o1',form:reply({id:1})});
  assert.equal(validateReferenceReply(valid,request,workspace()).session,'o1');
  for (const changes of [{form:null},{session:null},{form:reply({id:2})},{form:reply({id:1},state(0,{kind:'closed',lifecycle:'closed',items:[]}))}])
    assert.throws(()=>validateReferenceReply({...valid,result:{...valid.result,...changes}},request,workspace()));
  assert.throws(()=>validateReferenceReply(response(hello,workspace({kind:'closed',sessions:[order()]})),hello,null));
});

test('transport serialization and terminal failure never replay queued requests', async () => {
  const gate=deferred(),seen=[]; let failures=0;
  const client=new ReferenceClient(async request=>{seen.push(request);await gate.promise;throw Error('lost');},()=>{},()=>failures++);
  const first=client.request('workspace.hello',{}), second=client.request('workspace.list',{code:''});
  await Promise.resolve(); assert.equal(seen.length,1); gate.resolve();
  await assert.rejects(first); await assert.rejects(second);
  assert.equal(seen.length,1); assert.equal(client.pending,0); assert.equal(failures,1);
  await assert.rejects(client.request('workspace.list',{code:''})); assert.equal(seen.length,1);
});

test('outer and nested uncertain outcomes lock even when the reply shape is valid', async () => {
  for (const variant of ['outer','inner','error']) {
    const client=new ReferenceClient(async request=>response(request,opened(),{session:'o1',form:reply(request.params.request,state(1,{uncertain:variant==='inner'}),variant==='error'?'outcome_unknown':null)}));
    client.state=opened();
    if (variant==='outer') client.exchange=async request=>response(request,opened(),{session:'o1',form:reply(request.params.request)});
    const original=client.exchange; if (variant==='outer') client.exchange=async request=>{const result=await original(request);result.result.state.uncertain=true;return result;};
    await assert.rejects(client.form('o1',nested().params.request)); assert.equal(client.terminal,true);
  }
});

test('nested form revisions cannot roll back and recoverable errors remain authoritative', async () => {
  let revision=3, error='event_failed';
  const client=new ReferenceClient(async request=>response(request,opened(),{session:'o1',form:reply(request.params.request,state(revision),error)}));
  client.state=opened();
  const first=await client.form('o1',nested().params.request); assert.equal(first.result.error,'event_failed'); assert.equal(client.terminal,false);
  revision=2; error=null; await assert.rejects(client.form('o1',nested().params.request)); assert.equal(client.terminal,true);
});

test('retired session identities cannot be resurrected and request counters cannot overflow', async () => {
  const client=new ReferenceClient(async request=>response(request,opened(),{session:'o1',form:reply({id:1})}));
  client.state=workspace(); client.issued.set('o1',order());
  await assert.rejects(client.request('workspace.open',{revision:0,row:null,request:'open-2'})); assert.equal(client.terminal,true);
  let sent=0; const exhausted=new ReferenceClient(async request=>{sent++;return response(request);});
  exhausted.id=2147483647; await assert.rejects(exhausted.request('workspace.hello',{})); assert.equal(sent,0);
});
