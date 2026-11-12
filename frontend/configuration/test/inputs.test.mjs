import test from 'node:test';
import assert from 'node:assert/strict';
import {INPUT_CAPABILITY,inputField,validInputAnswer} from '../src/inputs.mjs';
import {APPLICATION_PROTOCOL,ApplicationClient,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from '../src/app.mjs';
import {environment,all} from '../../form/test/fake-dom.mjs';
import {state,reply,field,button,deferred} from '../../form/test/fixtures.mjs';
const ticket='c'.repeat(32),choice='d'.repeat(32),hello={protocol:APPLICATION_PROTOCOL,inputCapability:INPUT_CAPABILITY};
const descriptor=extra=>({ticket,owner:'form-1',kind:'input',title:'',text:'Quantity',value:{type:'Number',value:'1.00'},editor:{kind:'number',digits:8,scale:2,nonnegative:true},...extra});
const selection=extra=>({ticket,owner:'form-1',kind:'choice',title:'Pick',choices:[{choice,value:{type:'String',value:'one'},presentation:'First'}],initial:null,...extra});
const snapshot=blocked=>({kind:'application',lifecycle:'running',messages:[],exitWarning:'',title:'Inputs',entries:[{id:1,title:'Owner',kind:'form'}],
  sessions:[{id:'form-1',entry:1,title:'Owner',owner:null,blocked}],active:'form-1',uncertain:false,catalog:null});
const envelope=(request,inputs=[descriptor()],extra={})=>({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,inputCapability:INPUT_CAPABILITY,inputs,
  state:snapshot(inputs.length>0),error:null,session:null,form:null,updates:[],...extra}});
const req=()=>({id:1,method:'application.hello',params:hello});
const answer={session:'form-1',ticket,action:'accept',value:{type:'Number',value:'2.00'}};
const form=(revision=0)=>state(revision,{items:[field('Name',{type:'String',value:'Original'}),button('Ask')]});
test('closed input descriptor reuses exact scalar qualifiers',()=>{assert.equal(validateApplicationReply(envelope(req()),req(),null).inputs.length,1);assert.equal(inputField(descriptor()).editor.scale,2);});
test('Boolean input admits only its exact Boolean editor',()=>{assert.equal(inputField(descriptor({value:{type:'Boolean',value:false},editor:{kind:'boolean'}})).view,'checkbox');assert.throws(()=>inputField(descriptor({value:{type:'Boolean',value:false},editor:{kind:'boolean',extra:true}})));});
test('mixed scalar input, refs, invented kinds and extra callbacks are rejected',()=>{for(const patch of [{kind:'html'},{callback:'private'},{value:{type:'Undefined'}},{editor:{kind:'number',digits:3,scale:2,nonnegative:false},value:{type:'Number',value:'99'}},{text:'\u0000'}])assert.throws(()=>validateApplicationReply(envelope(req(),[descriptor(patch)]),req(),null));});
test('choice rows are exact, bounded scalar-only token records',()=>{for(const patch of [{choices:[{choice,value:{type:'Undefined'},presentation:'x'}]},{choices:[{choice,value:{type:'String',value:'x'},presentation:'x',key:'raw'}]},{initial:'a'.repeat(32)},{choices:Array(129).fill(selection().choices[0])}])assert.throws(()=>validateApplicationReply(envelope(req(),[selection(patch)]),req(),null));});
test('choice duplicate tokens and malformed presentation fail closed',()=>{for(const choices of [[selection().choices[0],selection().choices[0]],[{...selection().choices[0],presentation:'\ud800'}]])assert.throws(()=>validateApplicationReply(envelope(req(),[selection({choices})]),req(),null));});
test('empty list selection allows cancellation but no invented choice',()=>{const value=selection({choices:[]});validateApplicationReply(envelope(req(),[value]),req(),null);assert.equal(validInputAnswer({...answer,action:'choose',choice},[value]),false);});
test('input owner cannot also own a question or child form',()=>{const value=envelope(req());value.result.dialogCapability='yadinassi-owned-dialog/1';value.result.dialogs=[{ticket:'b'.repeat(32),owner:'form-1',kind:'warning',title:'',text:'',choices:['dismiss']}];assert.throws(()=>validateApplicationReply(value,req(),null));delete value.result.dialogCapability;delete value.result.dialogs;value.result.state.sessions.push({id:'form-2',entry:1,title:'Child',owner:'form-1',blocked:false});assert.throws(()=>validateApplicationReply(value,req(),null));});
test('input graph requires exact blocked owner and unique lifetime token',()=>{const value=envelope(req());value.result.state.sessions[0].blocked=false;assert.throws(()=>validateApplicationReply(value,req(),null));assert.throws(()=>validateApplicationReply(envelope(req(),[descriptor(),descriptor()]),req(),null));});
test('forms-only negotiated hosts permit only empty inputs',()=>{const value=envelope(req(),[]);delete value.result.updates;delete value.result.state.sessions[0].owner;delete value.result.state.sessions[0].blocked;validateApplicationReply(value,req(),null);value.result.inputs=[descriptor()];assert.throws(()=>validateApplicationReply(value,req(),null));});
test('Number acceptance does not round clamp or change admitted type',()=>{for(const value of [{type:'Number',value:'1.001'},{type:'Number',value:'-1'},{type:'String',value:'2'}])assert.equal(validInputAnswer({...answer,value},[descriptor()]),false);assert.equal(validInputAnswer(answer,[descriptor()]),true);});
test('cancel bypasses invalid scalar parsing and carries no value',()=>{assert.equal(validInputAnswer({session:'form-1',ticket,action:'cancel'},[descriptor()]),true);assert.equal(validInputAnswer({...answer,action:'cancel'},[descriptor()]),false);});
test('choice accepts opaque token not value or row index',()=>{assert.equal(validInputAnswer({session:'form-1',ticket,action:'choose',choice},[selection()]),true);for(const token of [0,'one','a'.repeat(32)])assert.equal(validInputAnswer({session:'form-1',ticket,action:'choose',choice:token},[selection()]),false);});
test('Date accepts exact whole-second qualifier without timezone conversion',()=>{const value=descriptor({value:{type:'Date',ticks:'0'},editor:{kind:'date',parts:'date'}});assert.equal(validInputAnswer({...answer,value:{type:'Date',ticks:'864000000'}},[value]),true);assert.equal(validInputAnswer({...answer,value:{type:'Date',ticks:'1'}},[value]),false);assert.equal(validInputAnswer({...answer,value:{type:'Date',ticks:'3155378975990000'}},[descriptor({value:{type:'Date',ticks:'0'},editor:{kind:'date',parts:'dateTime'}})]),false);});
test('input negotiation must echo and remain immutable',async()=>{let omit=false;const client=new ApplicationClient(async request=>{const value=envelope(request,[]);if(omit){delete value.result.inputCapability;delete value.result.inputs;}return value;});await client.request('application.hello',hello);omit=true;await assert.rejects(client.request('application.snapshot',{}));assert.equal(client.terminal,true);});
test('unsolicited inputs are rejected by legacy client',async()=>{const client=new ApplicationClient(async request=>envelope(request,[]));await assert.rejects(client.request('application.hello',{protocol:APPLICATION_PROTOCOL}));assert.equal(client.terminal,true);});
test('invalid local answer does not consume prompt or send traffic',async()=>{let calls=0;const client=new ApplicationClient(async request=>{calls++;return envelope(request);});await client.request('application.hello',hello);await assert.rejects(client.request('application.answerInput',{...answer,value:{type:'Number',value:'1.001'}}),error=>error.preDispatch);assert.equal(calls,1);assert.equal(client.terminal,false);});
test('new input blocks a queued navigation and other form event',async()=>{const client=new ApplicationClient(async request=>envelope(request));await client.request('application.hello',hello);await assert.rejects(client.request('application.open',{entry:1,request:'x'}),error=>error.code==='input_pending');await assert.rejects(client.form('form-2',{id:1,method:'form.event',params:{event:'command'}}),error=>error.code==='input_pending');});
test('same ticket may not mutate its initial value or choices',async()=>{let change=false;const client=new ApplicationClient(async request=>envelope(request,[descriptor(change?{text:'Changed'}:{})]));await client.request('application.hello',hello);change=true;await assert.rejects(client.request('application.snapshot',{}));assert.equal(client.terminal,true);});
test('retired input may not resurrect on later snapshot',async()=>{let phase=0;const client=new ApplicationClient(async request=>envelope(request,phase===1?[]:[descriptor()]));await client.request('application.hello',hello);phase=1;await client.request('application.snapshot',{});phase=2;await assert.rejects(client.request('application.snapshot',{}));});
test('double confirmation queues at most one terminal answer',async()=>{const held=deferred();let calls=0;const client=new ApplicationClient(async request=>{calls++;if(request.method==='application.answerInput'){await held.promise;return envelope(request,[],{session:'form-1',form:reply({id:1},form(1))});}return envelope(request);});await client.request('application.hello',hello);const first=client.request('application.answerInput',answer),second=client.request('application.answerInput',answer);held.resolve();await first;await assert.rejects(second,error=>error.preDispatch);assert.equal(calls,2);});
test('lost answer locks queued work without replay',async()=>{let calls=0;const client=new ApplicationClient(async request=>{calls++;if(request.method==='application.answerInput')throw Error('lost');return envelope(request);});await client.request('application.hello',hello);const first=client.request('application.answerInput',answer),second=client.request('application.snapshot',{});await assert.rejects(first);await assert.rejects(second);assert.equal(client.terminal,true);assert.equal(calls,2);});
async function mounted(kind='input',lose=false,custom=null){
 const env=environment(),seen=[],held=deferred();let inputs=[],revision=0;
 const create=env.document.createElement.bind(env.document);env.document.createElement=tag=>{const node=create(tag);if(tag==='textarea'){let value='';Object.defineProperty(node,'value',{get:()=>value,set:text=>{value=String(text).replace(/\r\n?/g,'\n');}});}return node;};
 const app=mountApplication(env,env.document.root,async request=>{seen.push(request);const extra={dialogCapability:'yadinassi-owned-dialog/1',dialogs:[]};
  if(request.method==='application.form'){if(request.params.request.params?.event==='command'){inputs=[kind==='choice'?selection():custom||descriptor()];revision++;}Object.assign(extra,{session:'form-1',form:reply(request.params.request,form(revision))});}
  if(request.method==='application.answerInput'){await held.promise;if(lose)throw Error('lost');inputs=[];revision++;Object.assign(extra,{session:'form-1',form:reply({id:1},form(revision))});}
  return envelope(request,inputs,extra);
 });await app.ready;await app.mounts.get('form-1').mount.ready;
 await app.client.form('form-1',{id:9,method:'form.event',params:{event:'command',control:'Ask',revision:0}});app.show('form-1',false);
 return{env,app,seen,held,find:predicate=>all(env.document.root).find(predicate)};
}
test('renderer keeps invalid numeric draft local and cancel submits no value',async()=>{const x=await mounted();const control=x.find(n=>n.dataset.valueInput==='scalar');assert.equal(x.env.document.activeElement,control);control.value='1.001';x.find(n=>n.dataset.inputAction==='accept').emit('click');await x.app.client.tail;assert.equal(x.seen.filter(r=>r.method==='application.answerInput').length,0);x.find(n=>n.dataset.inputAction==='cancel').emit('click');x.held.resolve();await x.app.client.tail;assert.equal(x.seen.at(-1).params.action,'cancel');assert.equal(Object.hasOwn(x.seen.at(-1).params,'value'),false);});
test('renderer confirms exact decimal and fences repeated buttons',async()=>{const x=await mounted();x.find(n=>n.dataset.valueInput==='scalar').value='2.30';const ok=x.find(n=>n.dataset.inputAction==='accept');ok.emit('click');ok.emit('click');x.held.resolve();await x.app.client.tail;const answers=x.seen.filter(r=>r.method==='application.answerInput');assert.equal(answers.length,1);assert.deepEqual(answers[0].params.value,{type:'Number',value:'2.30'});});
test('renderer displays literal choices and confirms opaque selected token',async()=>{const x=await mounted('choice');const radio=x.find(n=>n.dataset.valueChoice===choice);radio.checked=true;radio.emit('change');x.find(n=>n.dataset.inputAction==='accept').emit('click');x.held.resolve();await x.app.client.tail;assert.equal(x.seen.at(-1).params.choice,choice);});
test('renderer retains raw input as read-only after lost confirmation',async()=>{const x=await mounted('input',true);const control=x.find(n=>n.dataset.valueInput==='scalar');control.value='2.30';x.find(n=>n.dataset.inputAction==='accept').emit('click');x.held.resolve();await x.app.client.tail;await new Promise(resolve=>setImmediate(resolve));assert.equal(x.app.client.terminal,true);assert.equal(control.value,'2.30');assert.equal(control.readOnly,true);assert.equal(x.seen.filter(r=>r.method==='application.answerInput').length,1);});

test('input receives deferred initial focus when preceding question retires',async()=>{
 const env=environment();let waiting=true;
 const app=mountApplication(env,env.document.root,async request=>{
  if(request.method==='application.answerDialog')waiting=false;
  const value=envelope(request);Object.assign(value.result,{dialogCapability:'yadinassi-owned-dialog/1',dialogs:waiting?[{ticket:'b'.repeat(32),owner:'form-2',kind:'warning',title:'Notice',text:'First',choices:['dismiss']}]:[]});
  value.result.state.sessions.push({id:'form-2',entry:1,title:'Other',owner:null,blocked:waiting});
  if(request.method==='application.form')Object.assign(value.result,{session:request.params.session,form:reply(request.params.request,form())});
  if(request.method==='application.answerDialog')Object.assign(value.result,{session:'form-2',form:reply({id:1},form(1))});
  return value;
 });await app.ready;await Promise.all([...app.mounts.values()].map(m=>m.mount.ready));
 const dismiss=all(env.document.root).find(n=>n.dataset.dialogAnswer==='dismiss');dismiss.emit('click');await app.client.tail;await new Promise(resolve=>setImmediate(resolve));
 const scalar=all(env.document.root).find(n=>n.dataset.valueInput==='scalar');assert.equal(env.document.activeElement,scalar);assert.equal(scalar.readOnly,false);
});

test('multiline String preserves untouched CRLF bytes instead of HTML input sanitization',async()=>{
 const original={type:'String',value:'a\r\nb'};
 const x=await mounted('input',false,descriptor({value:original,editor:{kind:'string',length:0,fixed:false}}));
 const control=x.find(n=>n.dataset.valueInput==='scalar');assert.equal(control.tagName,'TEXTAREA');assert.equal(control.value,'a\nb');
 x.find(n=>n.dataset.inputAction==='accept').emit('click');x.held.resolve();await x.app.client.tail;
 assert.deepEqual(x.seen.filter(r=>r.method==='application.answerInput')[0].params.value,original);
});
