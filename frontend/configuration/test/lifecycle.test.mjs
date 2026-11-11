import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from '../src/app.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
import {reply as formReply} from '../../form/test/fixtures.mjs';
const snapshot = (extra = {}) => ({kind:'application',title:'Application',entries:[{id:1,title:'Main',kind:'form'}],
  sessions:[],active:null,uncertain:false,catalog:null,lifecycle:'running',messages:[],exitWarning:'',...extra});
const reply = (request,state=snapshot(),extra={}) => ({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state,error:null,session:null,form:null,...extra}});

test('application /3 admits each finite lifecycle and startup or exit diagnostics', () => {
  assert.equal(APPLICATION_PROTOCOL,'yadinassi-configuration-app/3');const request={id:1,method:'application.hello',params:{}};
  for(const lifecycle of ['forms','prepared','starting','running','before_exit','exiting','cancelled','failed','closed'])
    assert.equal(validateApplicationReply(reply(request,snapshot({lifecycle})),request,null).state.lifecycle,lifecycle);
  for(const error of ['startup_cancelled','startup_failed','exit_cancelled'])
    assert.equal(validateApplicationReply(reply(request,snapshot(),{error}),request,null).error,error);
});

test('application lifecycle metadata is mandatory, bounded and closed', () => {
  const request={id:1,method:'application.hello',params:{}};
  for(const patch of [{lifecycle:'raw_exception'},{messages:'message'},{messages:Array(65).fill('x')},
    {messages:['x'.repeat(4097)]},{messages:[false]},{exitWarning:'x'.repeat(4097)},{exitWarning:null}])
    assert.throws(()=>validateApplicationReply(reply(request,snapshot(patch)),request,null));
  for(const key of ['lifecycle','messages','exitWarning']) {const state=snapshot();delete state[key];assert.throws(()=>validateApplicationReply(reply(request,state),request,null));}
});

test('startup messages and exit warning render as literal text without HTML execution', async () => {
  const env=environment(), hostile='<img src=x onerror=alert(1)>';
  const app=mountApplication(env,env.document.root,async request=>reply(request,snapshot({messages:[hostile,'Started'],exitWarning:'Pending work remains'})));
  await app.ready;
  assert.ok(env.document.root.textContent.includes(hostile));assert.ok(env.document.root.textContent.includes('Pending work remains'));
  assert.equal(all(env.document.root).some(node=>['IMG','SCRIPT'].includes(node.tagName)),false);
});

test('cancelled application exit remains usable and displays authoritative cancellation message', async () => {
  const env=environment(),requests=[];
  const app=mountApplication(env,env.document.root,async request=>{
    requests.push(request);return reply(request,snapshot({messages:request.method==='application.close'?['Exit cancelled by application']:[]}),
      {error:request.method==='application.close'?'exit_cancelled':null});
  });
  await app.ready;buttons(env.document).find(node=>node.textContent==='Close application').emit('click');await app.client.tail;
  assert.equal(app.client.terminal,false);assert.ok(env.document.root.textContent.includes('Exit cancelled by application'));
  assert.equal(requests.filter(request=>request.method==='application.close').length,1);
});

test('open idempotency tokens are scoped to a document instance, not reset shared open-1', async () => {
  const tokens=[];
  for(let i=0;i<2;i++){
    const env=environment();let current=snapshot();
    const app=mountApplication(env,env.document.root,async request=>{
      if(request.method==='application.open') {tokens.push(request.params.request);current=snapshot({sessions:[{id:'form-1',entry:1,title:'Main'}],active:'form-1'});return reply(request,current,{session:'form-1',form:formReply({id:1})});}
      if(request.method==='application.form')return reply(request,current,{session:'form-1',form:formReply(request.params.request)});
      return reply(request,current);
    });
    await app.ready;await app.openForm(1);await app.client.tail;
  }
  assert.notEqual(tokens[0],tokens[1]);for(const token of tokens){assert.match(token,/^open-[0-9a-f]{32}-1$/);assert.ok(token.length<=64);}
});
