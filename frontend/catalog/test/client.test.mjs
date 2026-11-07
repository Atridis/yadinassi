import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorClient, PROTOCOL, typedInput, readBoundedJSON, takeSessionCapability, rowDraftKey, editorDraft, reconcileDraft, hasDraftChanges, draftEvents, flushDraft} from '../src/client.mjs';
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

test('reference input uses only the field target and an offered selection',()=>{
  const field={kind:'catalog_ref',value:{catalog:'target'},choices:[{value:'empty'},{value:'selected'}]};
  assert.deepEqual(typedInput(field,'selected'),{type:'CatalogRef',catalog:'target',record:'selected'});
  for(const value of ['unknown',{},null,4])assert.throws(()=>typedInput(field,value),/available reference/);
});

// Reference-row draft and flush contract; included by the existing CI job.
{

const first='11111111-1111-4111-8111-111111111111';
const second='22222222-2222-4222-8222-222222222222';
const third='33333333-3333-4333-8333-333333333333';
const empty='00000000-0000-0000-0000-000000000000';
const selected='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const target='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const key=id=>rowDraftKey('Items',id);
function row(id,number,record=empty){
  return {id,number,field:{name:'Product',kind:'catalog_ref',readOnly:false,inputText:record,
    value:{type:'CatalogRef',catalog:target,record},choices:[{value:empty,label:'Empty reference'},{value:selected,label:'Product'}]}};
}
function editor(){
  return {editorId:'editor-1',editingLocked:false,sourceStale:false,
    fields:[{control:'InputDescription',kind:'string',inputText:'Record',enabled:true,readOnly:false}],
    sections:[{name:'Items',title:'Items',readOnly:false,canAdd:true,rows:[row(first,1),row(second,2)]}]};
}
const snapshot=(editor,revision=0)=>({protocol:PROTOCOL,formId:'catalog-editor',revision,state:{kind:'editor',editor},capabilities:{}});
function changedDraft(current){
  const draft=editorDraft(current);
  draft.fields.InputDescription='Changed';draft.rows[key(first)]=selected;draft.rows[key(second)]=selected;
  return draft;
}
function accept(current,params){
  const next=structuredClone(current);
  if(params.event==='change')next.fields.find(field=>field.control===params.control).inputText=params.value.value;
  if(params.event==='changeRow'){
    const field=next.sections.find(section=>section.name===params.section).rows.find(row=>row.id===params.row).field;
    field.inputText=params.value.record;field.value=params.value;
  }
  return next;
}

test('drafts cover scalar and reference rows without including read-only summary data',()=>{
  const current=editor();current.sections.push({name:'Unsupported',readOnly:true,reason:'multiple-columns',rowCount:50,rows:[]});
  assert.deepEqual(editorDraft(current),{fields:{InputDescription:'Record'},rows:{[key(first)]:empty,[key(second)]:empty}});
  assert.deepEqual(editorDraft(),{fields:{},rows:{}});
  assert.deepEqual(editorDraft({fields:current.fields}),{fields:{InputDescription:'Record'},rows:{}});
});

test('row keys are section plus opaque identity, independent of names and indexes',()=>{
  assert.notEqual(rowDraftKey('Items',first),rowDraftKey('Others',first));
  assert.notEqual(rowDraftKey('a,b','c'),rowDraftKey('a','b,c'));
  const current=editor();current.sections[0].name='__proto__';
  assert.equal(editorDraft(current).rows[rowDraftKey('__proto__',first)],empty);
  assert.equal(Object.getPrototypeOf(editorDraft(current).rows),Object.prototype);
});

test('row-only input is dirty and emits a typed reference addressed by UUID',()=>{
  const current=editor(),draft=editorDraft(current);draft.rows[key(second)]=selected;
  assert.equal(hasDraftChanges(current,draft),true);
  assert.deepEqual(draftEvents(current,draft),[{event:'changeRow',values:{section:'Items',row:second,
    value:{type:'CatalogRef',catalog:target,record:selected}}}]);
  assert.equal(current.sections[0].rows[1].field.inputText,empty);
});

test('unchanged rows and display renumbering do not become mutations',()=>{
  const current=editor(),draft=editorDraft(current);
  current.sections[0].rows.reverse();current.sections[0].rows.forEach((row,index)=>{row.number=index+1;});
  assert.equal(hasDraftChanges(current,draft),false);assert.deepEqual(draftEvents(current,draft),[]);
});

test('flush plan includes scalar then row edits with exact reference targets',()=>{
  const current=editor(),draft=changedDraft(current);
  assert.deepEqual(draftEvents(current,draft),[
    {event:'change',values:{control:'InputDescription',value:{type:'String',value:'Changed'}}},
    ...[first,second].map(id=>({event:'changeRow',values:{section:'Items',row:id,value:{type:'CatalogRef',catalog:target,record:selected}}}))
  ]);
});

test('resync fills added rows, retains input by identity and never retargets a deleted row',()=>{
  const current=editor(),draft=changedDraft(current),fresh=editor();
  fresh.sections[0].rows=[row(second,1),row(third,2)];
  const merged=reconcileDraft(fresh,draft);
  assert.deepEqual(merged,{fields:{InputDescription:'Changed'},rows:{[key(second)]:selected,[key(third)]:empty}});
  assert.equal(draft.rows[key(first)],selected);
  assert.deepEqual(editorDraft(fresh).rows,{[key(second)]:empty,[key(third)]:empty});
});

test('all inputs are validated before a flush sends its first request',async()=>{
  const current=editor(),draft=changedDraft(current),seen=[];draft.rows[key(second)]='unoffered';
  const client={snapshot:snapshot(current),event(...args){seen.push(args);}};
  await assert.rejects(flushDraft(client,current,draft),/available reference/);
  assert.deepEqual(seen,[]);assert.equal(draft.rows[key(second)],'unoffered');
});

test('read-only sections, row fields and disabled scalar inputs cannot flush',()=>{
  for(const mark of [current=>{current.sections[0].readOnly=true;},
    current=>{current.sections[0].rows[0].field.readOnly=true;},
    current=>{current.fields[0].enabled=false;}]){
    const current=editor(),draft=changedDraft(current);mark(current);
    assert.throws(()=>draftEvents(current,draft),/read-only/);
  }
});

test('editing locks and stale source reject changed drafts without mutating them',()=>{
  for(const flag of ['editingLocked','sourceStale']){
    const current=editor(),draft=changedDraft(current),saved=structuredClone(draft);current[flag]=true;
    assert.throws(()=>draftEvents(current,draft),/locked/);assert.deepEqual(draft,saved);
  }
});

test('successful flush advances revisions before the following add or delete action',async()=>{
  for(const action of [{event:'addRow',section:'Items'},{event:'deleteRow',section:'Items',row:second}]){
    let current=editor(),revision=0;const original=current,draft=changedDraft(current),seen=[];
    const client=new EditorClient(async request=>{
      if(request.method==='editor.event'){seen.push(request.params);current=accept(current,request.params);revision++;}
      return {jsonrpc:'2.0',id:request.id,result:snapshot(current,revision)};
    });
    await client.hello();await flushDraft(client,original,draft);
    const {event,...values}=action;await client.event(event,values);
    assert.deepEqual(seen.map(params=>params.event),['change','changeRow','changeRow',event]);
    assert.deepEqual(seen.map(params=>params.baseRevision),[0,1,2,3]);
    assert.equal(hasDraftChanges(client.snapshot.state.editor,draft),false);
  }
});

test('failed row flush stops before add, delete, save or back and preserves all input',async()=>{
  for(const action of ['addRow','deleteRow','command','closeCard','close']){
    let current=editor(),revision=0;const original=current,draft=changedDraft(current),saved=structuredClone(draft),seen=[];
    const client=new EditorClient(async request=>{
      if(request.method==='editor.event'){
        seen.push(request.params.event);revision++;
        if(request.params.event==='changeRow')return {jsonrpc:'2.0',id:request.id,
          error:{data:{reason:'row_rejected',snapshot:snapshot(current,revision)}}};
        current=accept(current,request.params);
      }
      return {jsonrpc:'2.0',id:request.id,result:snapshot(current,revision)};
    });
    await client.hello();
    await assert.rejects((async()=>{await flushDraft(client,original,draft);await client.event(action);})(),/row_rejected/);
    assert.deepEqual(seen,['change','changeRow']);assert.deepEqual(draft,saved);
    assert.deepEqual(reconcileDraft(client.snapshot.state.editor,draft),saved);
  }
});

test('failed row mutation preserves drafts after their successful flush',async()=>{
  for(const event of ['addRow','deleteRow']){
    let current=editor(),revision=0;const original=current,draft=changedDraft(current);
    const client=new EditorClient(async request=>{
      if(request.method==='editor.event'){
        revision++;
        if(request.params.event===event)return {jsonrpc:'2.0',id:request.id,
          error:{data:{reason:'mutation_rejected',snapshot:snapshot(current,revision)}}};
        current=accept(current,request.params);
      }
      return {jsonrpc:'2.0',id:request.id,result:snapshot(current,revision)};
    });
    await client.hello();await flushDraft(client,original,draft);
    await assert.rejects(client.event(event,{section:'Items',...(event==='deleteRow'?{row:second}:{})}),/mutation_rejected/);
    assert.deepEqual(reconcileDraft(client.snapshot.state.editor,draft),draft);
  }
});

test('lost row response locks further edits until resync without replaying accepted rows',async()=>{
  let current=editor(),revision=0,lost=false;const original=current,draft=changedDraft(current),seen=[];
  const client=new EditorClient(async request=>{
    if(request.method==='editor.event'){
      seen.push(request.params);current=accept(current,request.params);revision++;
      if(request.params.event==='changeRow'&&!lost){lost=true;throw Error('interrupted');}
    }
    return {jsonrpc:'2.0',id:request.id,result:snapshot(current,revision)};
  });
  await client.hello();await assert.rejects(flushDraft(client,original,draft),/Do not repeat Save/);
  assert.equal(client.uncertain,true);
  await assert.rejects(flushDraft(client,client.snapshot.state.editor,draft),/Resynchronize/);
  assert.equal(seen.length,2);
  await client.resync();const authoritative=client.snapshot.state.editor;
  await flushDraft(client,authoritative,reconcileDraft(authoritative,draft));
  assert.deepEqual(seen.map(params=>[params.event,params.row]),[['change',undefined],['changeRow',first],['changeRow',second]]);
});

test('changed editor identity or new lock aborts a flush before the next row',async()=>{
  for(const alter of [current=>{current.editorId='another';},current=>{current.editingLocked=true;},current=>{current.sourceStale=true;}]){
    const current=editor(),draft=changedDraft(current),seen=[];
    const client={snapshot:snapshot(current),async event(event,values){seen.push(event);const next=accept(current,{event,...values});alter(next);this.snapshot=snapshot(next,1);}};
    await assert.rejects(flushDraft(client,current,draft),/Editor changed/);
    assert.deepEqual(seen,['change']);assert.equal(draft.rows[key(first)],selected);
  }
});

test('single imported field acceptance normalizes only that input and failure retains the whole draft',async()=>{
  for(const rejected of [false,true]){
    const current=editor();current.originalForm=true;
    current.fields.push({control:'InputDeletionMark',kind:'boolean',inputText:false,enabled:true,readOnly:false});
    const draft=changedDraft(current);draft.fields.InputDescription='  Trimmed  ';draft.fields.InputDeletionMark=true;
    const original=structuredClone(draft);
    const client=new EditorClient(async request=>{
      if(request.method==='editor.hello')return {jsonrpc:'2.0',id:request.id,result:snapshot(current)};
      const normalized=accept(current,{...request.params,value:{type:'String',value:'Trimmed'}});
      const result=snapshot(normalized,1);
      return rejected?{jsonrpc:'2.0',id:request.id,error:{data:{reason:'field_rejected',snapshot:result}}}:
        {jsonrpc:'2.0',id:request.id,result};
    });
    await client.hello();let acceptedControl;
    try{
      await client.event('change',{control:'InputDescription',value:{type:'String',value:draft.fields.InputDescription}});
      acceptedControl='InputDescription';
    }catch(error){assert.equal(error.message,'field_rejected');}
    const reconciled=reconcileDraft(client.snapshot.state.editor,draft,acceptedControl);
    assert.equal(reconciled.fields.InputDescription,rejected?'  Trimmed  ':'Trimmed');
    assert.equal(reconciled.fields.InputDeletionMark,true);
    assert.deepEqual(reconciled.rows,draft.rows);
    assert.deepEqual(draft,original);
    if(rejected)assert.deepEqual(reconciled,original);
  }
});

}
