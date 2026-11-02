import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorClient, PROTOCOL, typedInput, readBoundedJSON, takeSessionCapability} from '../src/client.mjs';
const snapshot=revision=>({protocol:PROTOCOL,formId:'catalog-editor',revision,state:{kind:'catalogs'},capabilities:{}});
const success=(request,revision=0)=>({jsonrpc:'2.0',id:request.id,result:snapshot(revision)});

test('handshake and event use authoritative revision',async()=>{
  const seen=[];const client=new EditorClient(async request=>{seen.push(request);return success(request,seen.length-1);});
  await client.hello();await client.event('create');assert.equal(client.snapshot.revision,1);
  assert.deepEqual(seen[1].params,{event:'create',baseRevision:0});
});
test('error commits authoritative post-handler snapshot',async()=>{
  const client=new EditorClient(async request=>request.method==='editor.hello'?success(request):
    {jsonrpc:'2.0',id:request.id,error:{code:-32000,message:'Rejected',data:{reason:'duplicate_code',snapshot:snapshot(1)}}});
  await client.hello();await assert.rejects(client.event('command',{control:'SaveButton'}),/duplicate_code/);
  assert.equal(client.snapshot.revision,1);assert.equal(client.uncertain,false);
});
test('network loss locks events without automatic retry',async()=>{
  let count=0;const client=new EditorClient(async request=>{if(++count===1)return success(request);throw Error('offline');});
  await client.hello();await assert.rejects(client.event('command',{control:'SaveButton'}),/Do not repeat Save/);
  assert.throws(()=>client.event('command',{control:'SaveButton'}),/Resynchronize/);assert.equal(count,2);
});
test('explicit snapshot resynchronizes after lost outcome without replay',async()=>{
  const methods=[];const client=new EditorClient(async request=>{methods.push(request.method);if(methods.length===2)throw Error();return success(request,methods.length===1?0:1);});
  await client.hello();await assert.rejects(client.event('create'));await client.resync();
  assert.equal(client.snapshot.revision,1);assert.equal(client.uncertain,false);
  assert.deepEqual(methods,['editor.hello','editor.event','editor.snapshot']);
});
test('malformed ids and cross-form snapshots never replace state',async()=>{
  for(const alter of [r=>({...r,id:true}),r=>({...r,result:{...r.result,formId:'another'}}),r=>({...r,result:{...r.result,revision:true}})]){
    const client=new EditorClient(async request=>alter(success(request)));
    await assert.rejects(client.hello());assert.equal(client.snapshot,null);assert.equal(client.uncertain,true);
  }
});
test('older snapshot cannot rewind state',async()=>{
  let count=0;const client=new EditorClient(async request=>success(request,++count===1?2:1));
  await client.hello();await assert.rejects(client.resync(),/Out-of-order/);assert.equal(client.snapshot.revision,2);
});
test('state-unavailable error locks edits and keeps prior snapshot',async()=>{
  const client=new EditorClient(async request=>request.method==='editor.hello'?success(request):
    {jsonrpc:'2.0',id:request.id,error:{data:{reason:'form_error',stateUnavailable:true,saveState:'committed'}}});
  await client.hello();await assert.rejects(client.event('create'));assert.equal(client.snapshot.revision,0);assert.equal(client.uncertain,true);
});
test('exact typed inputs never convert decimal or date through JS numbers',()=>{
  const decimal='999999999999999999.01';assert.deepEqual(typedInput({kind:'number'},decimal),{type:'String',value:decimal});
  assert.equal(typedInput({kind:'datetime'},'0001-01-01T00:00').value,'0001-01-01T00:00:00');
  assert.deepEqual(typedInput({kind:'boolean'},false),{type:'Boolean',value:false});
  assert.throws(()=>typedInput({kind:'boolean'},'false'));assert.throws(()=>typedInput({kind:'number'},12.5));
});
test('bounded JSON decoder rejects oversized and invalid UTF8 responses',async()=>{
  assert.deepEqual(await readBoundedJSON(new Response('{"a":1}\n')),{a:1});
  await assert.rejects(readBoundedJSON(new Response('x'.repeat(131073))),/Oversized/);
  await assert.rejects(readBoundedJSON(new Response(new Uint8Array([0xff]))));
});
test('HTTP rejection never becomes application success',async()=>{
  await assert.rejects(readBoundedJSON(new Response('rejected',{status:403})),/403/);
});

test('same-document launch hash is consumed and stripped without persistent storage',()=>{
  const seen=[];const history={replaceState(...args){seen.push(args);}};
  const location={hash:'#session='+'a'.repeat(43),pathname:'/'};
  assert.equal(takeSessionCapability(location,history),'a'.repeat(43));
  assert.deepEqual(seen,[[null,'','/']]);
});
test('missing or malformed launch capability is never sent as a header',()=>{
  for(const hash of ['', '#session=short', '#session=%D1%8F'.repeat(40)]){
    assert.equal(takeSessionCapability({hash,pathname:'/'},{replaceState(){}}),null);
  }
});
