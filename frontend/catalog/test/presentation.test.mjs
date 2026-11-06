import test from 'node:test';
import assert from 'node:assert/strict';
import {THEME_KEY,themePreference,resolvedTheme,readTheme,rememberTheme,workspacePreview,listCheckPresentation} from '../src/presentation.mjs';

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
const editing={state:{kind:'editor',catalogs:[],list:null,editor:{catalog:'one',catalogName:'Products',fields:[{inputText:'unsaved'}]}}};
test('browsing takes authoritative navigation and editor keeps only its matching preview',()=>{
  const preview=workspacePreview(null,browsing);
  assert.deepEqual(preview,{catalogs,list});
  assert.deepEqual(workspacePreview(preview,editing),preview);
  assert.equal(Object.hasOwn(workspacePreview(preview,editing),'editor'),false);
});
test('reattach in editor does not fabricate a record list or retain another catalog list',()=>{
  for(const previous of [null,{catalogs:[],list:{catalog:'two',rows:[{}]}}]){
    assert.deepEqual(workspacePreview(previous,editing),{catalogs:[catalogs[0]],list:null});
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
