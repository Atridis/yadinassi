import test from 'node:test';
import assert from 'node:assert/strict';
import {THEME_KEY,themePreference,resolvedTheme,readTheme,rememberTheme,workspacePreview,listCheckPresentation,isDeletionMarked,reconcileSelection,selectRecord,selectedReference,createSelectionModel} from '../src/presentation.mjs';

test('new or invalid preferences default to dark independent of OS',()=>{
  for(const value of [undefined,null,'','auto','DARK','session=secret',{},false]){
    assert.equal(themePreference(value),'dark');
    assert.equal(resolvedTheme(themePreference(value),false),'dark');
  }
});
test('only explicit system follows the OS, and explicit choices win',()=>{
  for(const dark of [false,true]){
    assert.equal(resolvedTheme('system',dark),dark?'dark':'light');
    assert.equal(resolvedTheme('dark',dark),'dark');
    assert.equal(resolvedTheme('light',dark),'light');
  }
});
test('theme storage uses one fixed presentation key and validated value',()=>{
  const seen=[];const environment={localStorage:{getItem(key){seen.push(['read',key]);return 'light';},setItem(...args){seen.push(['write',...args]);}}};
  assert.equal(readTheme(environment),'light');
  rememberTheme(environment,'system');rememberTheme(environment,'session=secret');
  assert.deepEqual(seen,[['read',THEME_KEY],['write',THEME_KEY,'system'],['write',THEME_KEY,'dark']]);
});
test('blocked storage getter, read and write do not interrupt the editor',()=>{
  const getter={get localStorage(){throw Error('blocked');}};
  const methods={localStorage:{getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}}};
  for(const environment of [getter,methods,{}]){
    assert.equal(readTheme(environment),'dark');
    assert.doesNotThrow(()=>rememberTheme(environment,'light'));
  }
});
const catalogs=[{id:'one',name:'Products'},{id:'two',name:'Categories'}];
const list={catalog:'one',rows:[{description:'Previously loaded'}]};
const browsing={state:{kind:'list',catalogs,list}};
const editing={state:{kind:'editor',catalogs:[],list,editor:{catalog:'one',catalogName:'Products',fields:[{inputText:'unsaved'}]}}};
test('browsing takes authoritative navigation and editor keeps only its matching preview',()=>{
  const preview=workspacePreview(null,browsing);
  assert.deepEqual(preview,{catalogs,list});
  assert.deepEqual(workspacePreview(preview,editing),preview);
  assert.equal(Object.hasOwn(workspacePreview(preview,editing),'editor'),false);
});
test('reattach uses authoritative editor list, never cached rows from another catalog',()=>{
  for(const previous of [null,{catalogs:[],list:{catalog:'two',rows:[{}]}}]){
    assert.deepEqual(workspacePreview(previous,editing),{catalogs:[catalogs[0]],list});
  }
});
test('return refreshes preview and closing clears all retained navigation',()=>{
  const previous=workspacePreview(null,browsing);
  const refreshed={...list,rows:[{description:'Saved value'}]};
  assert.equal(workspacePreview(previous,{state:{kind:'list',catalogs,list:refreshed}}).list,refreshed);
  for(const snapshot of [null,{state:{kind:'closed'}}])assert.deepEqual(workspacePreview(previous,snapshot),{catalogs:[],list:null});
});

test('list check is enabled only by the current supported list snapshot',()=>{
  const messages=[{text:'Карточка проверена',field:''}];
  assert.deepEqual(listCheckPresentation({state:{kind:'list',listCheck:{available:true,messages}}}),{available:true,messages});
  for(const snapshot of [null,browsing,{state:{kind:'list',listCheck:{available:false,messages}}}])
    assert.deepEqual(listCheckPresentation(snapshot),{available:false,messages:[]});
});
test('list check never reuses diagnostics while an editor or closed state is shown',()=>{
  const listCheck={available:true,messages:[{text:'Old result',field:'Name'}]};
  for(const state of [{kind:'editor'},{kind:'closed'},{kind:'catalogs'},{kind:'list',editor:{dirty:true}}])
    assert.deepEqual(listCheckPresentation({state:{...state,listCheck}}),{available:false,messages:[]});
});
test('fresh list snapshots clear prior results and preserve diagnostic text literally',()=>{
  const messages=[{text:'<script>untrusted</script>',field:'<Name>'}];
  const snapshot={state:{kind:'list',listCheck:{available:true,messages}}};
  assert.deepEqual(listCheckPresentation(snapshot).messages,messages);
  assert.deepEqual(listCheckPresentation({state:{kind:'list',listCheck:{available:true,messages:[]}}}).messages,[]);
  assert.deepEqual(listCheckPresentation({state:{kind:'list',listCheck:{available:true}}}).messages,[]);
});

test('deletion badge requires a true typed Boolean, never a truthy wire value',()=>{
  assert.equal(isDeletionMarked({deletionMark:{type:'Boolean',value:true}}),true);
  for(const deletionMark of [undefined,null,false,true,{type:'Boolean',value:false},
    {type:'Boolean',value:'true'},{type:'Boolean',value:1},{type:'String',value:'true'},{}])
    assert.equal(isDeletionMarked({deletionMark}),false);
  assert.equal(isDeletionMarked(null),false);
});

test('saved card accepts the new authoritative list without closing the editor',()=>{
  const refreshed={...list,total:2,rows:[{description:'Created record'}]};
  const snapshot={state:{...editing.state,list:refreshed}};
  assert.equal(workspacePreview({catalogs,list},snapshot).list,refreshed);
});
test('failed refresh clears stale list while preserving navigation',()=>{
  const snapshot={state:{...editing.state,list:null}};
  assert.deepEqual(workspacePreview({catalogs,list},snapshot),{catalogs,list:null});
});
test('editor preview never displays an authoritative list from another catalog',()=>{
  const snapshot={state:{...editing.state,list:{catalog:'two',rows:[]}}};
  assert.equal(workspacePreview({catalogs,list},snapshot).list,null);
});

const catalogId='00000000-0000-0000-0000-000000000001';
const ref=index=>({type:'CatalogRef',catalog:catalogId,record:`00000000-0000-0000-0000-${String(index).padStart(12,'0')}`});
const page=(...indexes)=>({catalog:catalogId,rows:indexes.map(index=>({reference:ref(index)}))});
const snap=(list,editor)=>({state:{kind:editor?'editor':'list',list,editor}});
test('selection resolves one exact reference, not a positional row',()=>{
  const list=page(2,3);const selected=selectRecord(null,list,ref(3));
  assert.deepEqual(selectedReference(selected,list),ref(3));
  assert.deepEqual(selectedReference(selected,page(3,2)),ref(3));
  // Simulate A already painted, then click B and click Open/check in the same
  // JavaScript turn: no framework render is required to change the command target.
  const model=createSelectionModel();model.select(list,ref(2));
  const painted=model.current;model.select(list,ref(3));
  assert.deepEqual(painted.records,[ref(2).record]);
  assert.deepEqual(model.target(list),ref(3));
  assert.equal(model.empty(list),false);
  model.select(list,ref(2),true);
  assert.equal(model.target(list),null); // old single-target button may still be painted
  model.select(list,ref(3),true);model.select(list,ref(2),true);
  assert.equal(model.empty(list),true);
  model.select(list,ref(3));assert.equal(model.target(page(4)),null); // latest page wins
});
test('checkbox style selection set disables single target for zero or multiple',()=>{
  const list=page(2,3);let selected=selectRecord(null,list,ref(2),true);
  selected=selectRecord(selected,list,ref(3),true);
  assert.equal(selectedReference(selected,list),null);
  assert.equal(selected.records.length,2);
  selected=selectRecord(selected,list,ref(2),true);
  assert.deepEqual(selectedReference(selected,list),ref(3));
  selected=selectRecord(selected,list,ref(3),true);
  assert.equal(selectedReference(selected,list),null);
});
test('plain selection replaces a set with one reference',()=>{
  const list=page(2,3);let selected=selectRecord(null,list,ref(2),true);
  selected=selectRecord(selected,list,ref(3),true);
  assert.deepEqual(selectRecord(selected,list,ref(2)).records,[ref(2).record]);
});
test('changing page intersects identity set and never retargets same row index',()=>{
  const selected=selectRecord(null,page(2,3),ref(3));
  assert.deepEqual(reconcileSelection(selected,snap(page(4,5))).records,[]);
  assert.deepEqual(reconcileSelection(selected,snap(page(3,5))).records,[ref(3).record]);
});
test('changing catalog clears selection even if record UUID coincides',()=>{
  const selected=selectRecord(null,page(2),ref(2));
  const other={catalog:'00000000-0000-0000-0000-000000000009',rows:[{reference:{...ref(2),catalog:'00000000-0000-0000-0000-000000000009'}}]};
  assert.deepEqual(reconcileSelection(selected,snap(other)).records,[]);
  assert.equal(selectedReference(selected,other),null);
});
test('saved authoritative reference becomes selected behind retained editor',()=>{
  const previous=selectRecord(null,page(2),ref(2));
  for(const saveState of ['saved','unchanged']){
    const current=reconcileSelection(previous,snap(page(2,3),{reference:ref(3),saveState,editingLocked:false}));
    assert.deepEqual(current.records,[ref(3).record]);
  }
});
test('rejected or uncertain draft cannot invent a selected record',()=>{
  const previous=selectRecord(null,page(2),ref(2));
  for(const saveState of ['editing','rejected','uncertain','committed']){
    const current=reconcileSelection(previous,snap(page(2),{reference:ref(3),saveState,editingLocked:true}));
    assert.deepEqual(current.records,[ref(2).record]);
  }
  assert.deepEqual(reconcileSelection(previous,snap(null)).records,[]);
});
test('removed records clear selection and empty references cannot be selected',()=>{
  const previous=selectRecord(null,page(2),ref(2));
  assert.equal(selectedReference(previous,page(3)),null);
  assert.deepEqual(selectRecord(null,page(2),ref(0)).records,[]);
  assert.deepEqual(selectRecord(null,page(2),ref(3)).records,[]);
  assert.deepEqual(reconcileSelection(previous,{state:{kind:'closed',list:page(2)}}).records,[]);
});
test('single target uses latest authoritative reference object and collapses duplicates',()=>{
  const previous={catalog:catalogId,records:[ref(2).record,ref(2).record]};const latest=page(2);
  assert.equal(selectedReference(previous,latest),latest.rows[0].reference);
  assert.deepEqual(reconcileSelection(previous,snap(latest)).records,[ref(2).record]);
});
