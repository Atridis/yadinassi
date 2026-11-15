import test from 'node:test';
import assert from 'node:assert/strict';
import {validateScalar, validateSnapshot, scalarEqual, scalarText, typedInput, FormClient} from '../src/client.mjs';
import {createFormView} from '../src/view.mjs';
import {state, reply, field, table, column} from './fixtures.mjs';
import {environment, all} from './fake-dom.mjs';
const value=(patch={})=>({type:'FormEnumRef',scope:'a'.repeat(32),target:1,key:'b'.repeat(32),text:'Piece',...patch});
const initial=()=>state(0,{items:[field('Unit',value()),table({columns:[column('Unit','FormEnumRef')],rows:[{id:1,values:[value()]}]})]});
test('enum packets retain an explicit family and opaque identity',()=>{
  assert.equal(validateScalar(value()).type,'FormEnumRef');
  assert.equal(scalarText(value()),'Piece');
  assert.equal(scalarEqual(value(),value({text:'renamed'})),true);
  assert.equal(scalarEqual(value(),value({type:'FormCatalogRef'})),false);
  assert.equal(scalarEqual(value(),value({scope:'c'.repeat(32)})),false);
  for(const patch of [{uuid:'leak'},{target:0},{key:'UUID'},{value:'Piece'}])assert.throws(()=>validateScalar(value(patch)));
});
test('enum headers and rows validate their exact packet family',()=>{
  assert.equal(validateSnapshot(initial()).items[1].columns[0].type,'FormEnumRef');
  const bad=initial();bad.items[1].rows[0].values[0].type='FormCatalogRef';
  assert.throws(()=>validateSnapshot(bad));
});
test('enum choice is not a generic scalar edit',async()=>{
  const requests=[],client=new FormClient(async request=>{requests.push(request);return reply(request,initial());});await client.hello();
  assert.throws(()=>typedInput(initial().items[0],'Piece'));
  assert.throws(()=>client.event('change',{control:'Unit',value:value()}));
  assert.throws(()=>client.event('cell',{control:'Lines',row:1,column:'Unit',value:value()}));
  assert.equal(requests.length,1);
});
test('enum presentation is literal and choice actions carry only locators',()=>{
  const env=environment(),actions=[];
  const view=createFormView(env.document,env.document.root,{change(){},action(){},refresh(){},reference:action=>actions.push(action)});
  const snapshot=initial();snapshot.items[0].value.text='<b>Piece</b>';
  view.render({snapshot,busy:false,locked:false,connected:true,error:''});
  const choose=all(env.document.root).find(node=>node.getAttribute('aria-label')==='Choose Unit');
  assert.ok(choose);choose.emit('click');
  assert.deepEqual(actions,[{action:'begin',control:'Unit',row:null,column:null}]);
  assert.equal(JSON.stringify(actions).includes('scope'),false);
});
