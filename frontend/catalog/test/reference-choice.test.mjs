import test from 'node:test';
import assert from 'node:assert/strict';
import {validateReferenceAction} from '../src/client.mjs';
const state=()=>({state:{editor:{fields:[{control:'InputData1',lazyChoice:true,enabled:true,readOnly:false}],sections:[{name:'Rows',rows:[{id:'row1',field:{lazyChoice:true,readOnly:false}}]}]},referenceChoice:null}});
const picked=()=>{const s=state();s.state.referenceChoice={ticket:'ticket',rows:[{choice:'issued'}],navigation:{previous:null,next:'next'}};return s;};
test('begin requires exact supported scalar or stable section destination',()=>{
 const s=state();validateReferenceAction(s,{action:'begin',control:'InputData1',section:null,row:null});
 validateReferenceAction(s,{action:'begin',control:null,section:'Rows',row:'row1'});
 for(const a of [{action:'begin',control:'other',section:null,row:null},{action:'begin',control:null,section:'Rows',row:'row2'},{action:'begin',control:'InputData1',section:'Rows',row:null}])assert.throws(()=>validateReferenceAction(s,a));
});
test('pending and stale editor refuse all reference actions',()=>{
 for(const key of ['editingLocked','sourceStale']){const s=picked();s.state.editor[key]=true;assert.throws(()=>validateReferenceAction(s,{action:'apply',ticket:'ticket',choice:'issued'}));}
 assert.throws(()=>validateReferenceAction({state:{}},{action:'begin',control:'InputData1',section:null,row:null}));
});
test('apply and page require currently issued values, not arbitrary UUID or stale cursor',()=>{
 const s=picked();validateReferenceAction(s,{action:'apply',ticket:'ticket',choice:'issued'});validateReferenceAction(s,{action:'page',ticket:'ticket',cursor:'next'});
 for(const a of [{action:'apply',ticket:'old',choice:'issued'},{action:'apply',ticket:'ticket',choice:'uuid'},{action:'page',ticket:'ticket',cursor:null},{action:'page',ticket:'ticket',cursor:'old'}])assert.throws(()=>validateReferenceAction(s,a));
});
test('search bounds and closed action shapes are checked before transport',()=>{
 const s=picked();validateReferenceAction(s,{action:'search',ticket:'ticket',query:'abc'});
 for(const query of [null,'x'.repeat(129),'a\0b'])assert.throws(()=>validateReferenceAction(s,{action:'search',ticket:'ticket',query}));
 assert.throws(()=>validateReferenceAction(s,{action:'clear',ticket:'ticket',record:'uuid'}));
 assert.throws(()=>validateReferenceAction(s,{action:'sql',ticket:'ticket'}));
});
test('cancel clear refresh keep ticket binding and begin cannot replace active picker',()=>{
 const s=picked();for(const action of ['cancel','clear','refresh'])validateReferenceAction(s,{action,ticket:'ticket'});
 assert.throws(()=>validateReferenceAction(s,{action:'begin',control:'InputData1',section:null,row:null}));
 s.state.referenceChoice=null;assert.throws(()=>validateReferenceAction(s,{action:'apply',ticket:'ticket',choice:'issued'}));
});

test('lost Apply response is resolved by one snapshot read, never replay',async()=>{
 const {EditorClient,PROTOCOL,editorDraft,hasDraftChanges}=await import('../src/client.mjs');
 const before=picked();Object.assign(before,{protocol:PROTOCOL,formId:'catalog-editor',revision:1,capabilities:{}});before.state.kind='editor';
 const calls=[];const client=new EditorClient(async packet=>{calls.push(packet);if(packet.method==='editor.event')throw Error('lost');
   const next=structuredClone(before);next.revision=2;next.state.referenceChoice=null;return {jsonrpc:'2.0',id:packet.id,result:next};});
 client.snapshot=before;const draft=editorDraft(before.state.editor);assert.equal(hasDraftChanges(before.state.editor,draft),false);
 await assert.rejects(client.event('referenceChoice',{action:{action:'apply',ticket:'ticket',choice:'issued'}}));
 assert.equal(client.uncertain,true);await client.resync();assert.equal(client.uncertain,false);
 assert.equal(client.snapshot.state.referenceChoice,null);assert.deepEqual(calls.map(p=>p.method),['editor.event','editor.snapshot']);
});
test('native modal exposes recovery even while business actions are uncertain',async()=>{
 const {readFile}=await import('node:fs/promises');const source=await readFile(new URL('../src/app.jsx',import.meta.url),'utf8');
 assert.ok(source.includes('<button disabled={busy} onClick={resync}>Resynchronize choice</button>'));
 assert.ok(source.includes('orphanedDraft(previous,current,raw)'));
 assert.ok(source.includes('hasDraftChanges(previous,raw)'));
});
