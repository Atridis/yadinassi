import test from 'node:test';
import assert from 'node:assert/strict';
import {FormClient, FormError, validateScalar, validateSnapshot, scalarEqual, scalarText, typedInput} from '../src/client.mjs';
import {createFormView} from '../src/view.mjs';
import {mountForm} from '../src/app.mjs';
import {state, reply, field, table, column, button, deferred} from './fixtures.mjs';
import {environment, all, FakeDocument} from './fake-dom.mjs';
const ref = (extra = {}) => ({type:'FormCatalogRef',scope:'a'.repeat(32),target:1,key:'b'.repeat(32),text:'Product One',...extra});
const refField = (extra = {}) => field('Product',ref(),extra);
const refTable = (extra = {}) => table({columns:[column('Product','FormCatalogRef'),column('Amount','Number')],
  rows:[{id:7,values:[ref(),{type:'Number',value:'1.00'}]},{id:2,values:[ref({key:null,text:''}),{type:'Number',value:'2'}]}],...extra});
const initial = () => state(0,{items:[field('Name'),refField(),refTable(),button()]});
const locate = (root,label) => all(root).find(node=>node.getAttribute('aria-label')===label);
const edit = (node,value) => {node.value=value;node.emit('input');};
const settle = () => new Promise(resolve=>setTimeout(resolve,0));
const model = snapshot => ({snapshot,busy:false,locked:false,connected:true,error:''});
const begin = (extra={}) => ({action:'begin',control:'Product',row:null,column:null,...extra});
function host(options={}) {
  const env=environment(), requests=[], references=[];let current=initial(), paused=false;
  const app=mountForm(env,env.document.root,{transport:async request=>{
    requests.push(request);
    if(request.method==='form.event'){
      const p=request.params;
      current={...current,revision:current.revision+1,items:current.items.map(item=>item.name!==p.control?item:
        p.event==='change'?{...item,value:p.value}:p.event==='cell'?{...item,rows:item.rows.map(row=>row.id!==p.row?row:
          {...row,values:row.values.map((value,index)=>item.columns[index].name===p.column?p.value:value)})}:item)};
      if(options.changed) current=options.changed(current,request);
    }
    return reply(request,current,request.method==='form.event'?options.changeError||null:null);
  },referenceActive:()=>paused,onReference:async request=>{
    references.push(request);if(options.reference)return options.reference(request,current);
    current={...current,revision:current.revision+1};return reply({id:1},current);
  }});
  return {env,app,requests,references,pause(value){paused=value;app.repaint();}};
}

test('reference scalar accepts exact typed empty and opaque nonempty packets',()=>{
  for(const value of [ref(),ref({key:null,text:''}),ref({target:128,text:'<b>literal</b>'}),ref({text:'Я'.repeat(1024)}),ref({text:'😀'.repeat(1024)})]){
    assert.equal(validateScalar(value),value);assert.equal(scalarText(value),value.text);
  }
});
test('reference scalar rejects UUIDs, foreign shapes, invalid ranges and unbounded presentation',()=>{
  for(const patch of [{scope:'A'.repeat(32)},{scope:'a'.repeat(31)},{target:0},{target:129},{target:1.5},
    {key:'c641d26c-d8a0-49cb-841d-75574d25f782'},{key:5},{text:'x'.repeat(1025)},{text:'\ud800'},
    {uuid:'secret'},{value:'generic'},{type:'CatalogRef'}]) assert.throws(()=>validateScalar(ref(patch)));
});
test('reference equality compares scope target key but ignores presentation',()=>{
  assert.equal(scalarEqual(ref(),ref({text:'Renamed'})),true);
  for(const patch of [{scope:'c'.repeat(32)},{target:2},{key:null},{key:'d'.repeat(32)}])assert.equal(scalarEqual(ref(),ref(patch)),false);
  assert.equal(scalarEqual(ref(),{type:'String',value:'Product One'}),false);
});
test('form snapshot admits reference fields and typed table columns only with bounded scalar shapes',()=>{
  assert.equal(validateSnapshot(initial()).items[2].columns[0].type,'FormCatalogRef');
  assert.throws(()=>validateSnapshot(state(0,{items:[refTable({columns:[column('Product','Number'),column('Amount','Number')]})]})));
  assert.throws(()=>validateSnapshot(state(0,{items:[refField({value:ref({scope:'bad'})})]})));
});
test('generic scalar and cell change paths never transmit a reference',async()=>{
  const requests=[],client=new FormClient(async request=>{requests.push(request);return reply(request,initial());});await client.hello();
  assert.throws(()=>typedInput(refField(),'text'));
  assert.throws(()=>client.event('change',{control:'Product',value:ref()}));
  assert.throws(()=>client.event('cell',{control:'Lines',row:7,column:'Product',value:ref()}));
  assert.equal(requests.length,1);
});
test('nested reference adoption retains completed effects and does not consume a form request ID',async()=>{
  const client=new FormClient(async request=>reply(request,initial()));await client.hello();const id=client.id;
  const changed=state(2,{items:[refField({value:ref({text:'Renamed'})})]});
  assert.throws(()=>client.adopt(reply({id:1},changed,'reference_refused')),error=>error.code==='reference_refused');
  assert.equal(client.snapshot,changed);assert.equal(client.id,id);assert.equal(client.locked,false);
});
test('stale or mismatched nested reference replies lock without guessing a replacement action',async()=>{
  for(const malformed of [reply({id:2},initial()),reply({id:1},state(0))]){
    const client=new FormClient(async request=>reply(request,state(2)));await client.hello();
    assert.throws(()=>client.adopt(malformed));assert.equal(client.transportFailed,true);assert.equal(client.snapshot.revision,2);
  }
});
test('reference presentation is text-only read-only and cannot create local generic drafts',()=>{
  const document=new FakeDocument(),view=createFormView(document,document.root,{change(){},action(){},refresh(){},reference(){}});
  const hostile='<img src=x onerror=evil()> & "';view.render(model(state(0,{items:[refField({value:ref({text:hostile})})]})));
  const input=locate(document.root,'Product');assert.equal(input.readOnly,true);assert.equal(input.value,hostile);
  edit(input,'injected text');assert.deepEqual(view.changes(),[]);assert.equal(view.hasDrafts(),false);
  assert.equal(all(document.root).some(node=>['IMG','SCRIPT'].includes(node.tagName)),false);
});
test('reference actions are optional and honor declared readonly, hidden and empty policies',()=>{
  const document=new FakeDocument();let view=createFormView(document,document.root,{change(){},action(){},refresh(){}});
  view.render(model(initial()));assert.equal(locate(document.root,'Choose Product'),undefined);
  view=createFormView(document,document.root,{change(){},action(){},refresh(){},reference(){}});
  for(const patch of [{readOnly:true},{enabled:false},{visible:false},{view:'label'}]){
    view.render(model(state(0,{items:[refField(patch)]})));assert.equal(locate(document.root,'Choose Product').disabled,true);
  }
  view.render(model(state(0,{items:[refField({value:ref({key:null,text:''})})]})));
  assert.equal(locate(document.root,'Choose Product').disabled,false);assert.equal(locate(document.root,'Clear Product').disabled,true);
});
test('reference table buttons keep stable row identity after reorder and reject declared readonly columns',()=>{
  const document=new FakeDocument(),calls=[],view=createFormView(document,document.root,{change(){},action(){},refresh(){},reference:value=>calls.push(value)});
  view.render(model(state(0,{items:[refTable()]})));const choose=locate(document.root,'Choose Product, row 7');
  view.render(model(state(1,{items:[refTable({rows:[...refTable().rows].reverse()})]})));
  assert.equal(locate(document.root,'Choose Product, row 7'),choose);choose.emit('click');
  assert.deepEqual(calls,[begin({control:'Lines',row:7,column:'Product'})]);
  view.render(model(state(2,{items:[refTable({columns:[column('Product','FormCatalogRef',{readOnly:true}),column('Amount','Number')]})]})));
  assert.equal(choose.disabled,true);choose.emit('click');assert.equal(calls.length,1);
});
test('invalid scalar draft blocks reference begin without dropping raw input',async()=>{
  const {app,env,requests,references}=host();await app.ready;edit(locate(env.document.root,'Amount, row 7'),'bad number');
  await app.reference(begin());assert.equal(references.length,0);assert.equal(requests.length,1);
  assert.equal(locate(env.document.root,'Amount, row 7').value,'bad number');assert.equal(app.view.hasDrafts(),true);
});
test('reference intent flushes scalar and cell drafts before sending latest revision once',async()=>{
  const {app,env,requests,references}=host();await app.ready;edit(locate(env.document.root,'Name'),'Changed');edit(locate(env.document.root,'Amount, row 7'),'8.50');
  await app.reference(begin());assert.deepEqual(requests.slice(1).map(request=>[request.params.event,request.params.revision]),[['change',0],['cell',1]]);
  assert.deepEqual(references,[{revision:2,action:begin()}]);assert.equal(app.client.snapshot.revision,3);assert.equal(app.view.hasDrafts(),false);
});
test('blur into Choose and repeated clicks are one serialized intent, never a lost first click',async()=>{
  const gate=deferred(),h=host({reference:async(_,current)=>{await gate.promise;return reply({id:1},{...current,revision:current.revision+1});}});await h.app.ready;
  const source=locate(h.env.document.root,'Name'),choose=locate(h.env.document.root,'Choose Product');edit(source,'Edited');
  choose.emit('pointerdown',{bubbles:true});source.emit('blur',{relatedTarget:choose});assert.equal(choose.disabled,false);
  choose.emit('click');choose.emit('click');await settle();assert.equal(h.references.length,1);assert.equal(h.requests.length,2);
  gate.resolve();await settle();assert.equal(choose.disabled,false);
});
test('failed preceding change stops before reference and retains authoritative effects',async()=>{
  const h=host({changeError:'event_failed'});await h.app.ready;edit(locate(h.env.document.root,'Name'),'Completed');await h.app.reference(begin());
  assert.equal(h.references.length,0);assert.equal(h.app.client.snapshot.items[0].value.value,'Completed');assert.equal(h.app.view.hasDrafts(),false);
});
test('changed reference identity or replaced table during flush cannot retarget a pending choice',async()=>{
  for(const tableTarget of [false,true]){
    const h=host({changed:current=>({...current,items:current.items.map(item=>tableTarget&&item.kind==='table'?{...item,tableId:2}:!tableTarget&&item.name==='Product'?{...item,value:ref({key:'c'.repeat(32)})}:item)})});
    await h.app.ready;edit(locate(h.env.document.root,'Name'),'Changed');await h.app.reference(tableTarget?begin({control:'Lines',row:7,column:'Product'}):begin());
    assert.equal(h.references.length,0);assert.ok(h.env.document.root.textContent.includes('changed or removed'));
  }
});
test('active picker blocks owner edits, commands, refresh and Close but cancellation bypasses raw drafts',async()=>{
  const h=host();await h.app.ready;edit(locate(h.env.document.root,'Amount, row 7'),'bad');h.pause(true);
  await h.app.run('command','Run');await h.app.run('close');await h.app.refresh();assert.equal(h.requests.length,1);
  assert.equal(locate(h.env.document.root,'Name').disabled,true);await h.app.reference({action:'cancel',ticket:'c'.repeat(32)});
  assert.equal(h.references.length,1);assert.equal(h.references[0].action.action,'cancel');assert.equal(h.app.view.hasDrafts(),true);
});
test('lost reference response locks once without event replay or false draft recovery',async()=>{
  const h=host({reference:async()=>{throw Error('lost');}});await h.app.ready;await h.app.reference(begin());await h.app.reference(begin());
  assert.equal(h.references.length,1);assert.equal(h.app.client.transportFailed,true);assert.equal(h.requests.length,1);
});
test('known predispatch ownership refusal preserves a live reference owner for reconciliation',async()=>{
  const h=host({reference:async()=>{const error=new FormError('reference_refused');error.preDispatch=true;throw error;}});await h.app.ready;await h.app.reference(begin());
  assert.equal(h.references.length,1);assert.equal(h.app.client.transportFailed,false);assert.equal(h.app.client.snapshot.revision,0);
});
