import test from 'node:test';
import assert from 'node:assert/strict';
import {APPLICATION_PROTOCOL,ApplicationClient,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from './application-fixtures.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
import {state,reply,field,button,table,column,deferred} from '../../form/test/fixtures.mjs';
const ref=(extra={})=>({type:'FormCatalogRef',scope:'a'.repeat(32),target:1,key:'b'.repeat(32),text:'Original',...extra});
const begin=(extra={})=>({action:'begin',control:'Product',row:null,column:null,...extra});
const choice=(extra={})=>({session:'form-1',ticket:'c'.repeat(32),control:'Product',row:null,column:null,title:'Products',code:'',
  rows:[{choice:'d'.repeat(32),code:'P1',description:'One'}],error:null,...extra});
const snapshot=(extra={})=>({kind:'application',lifecycle:'running',title:'Reference application',messages:[],exitWarning:'',
  entries:[{id:1,title:'Order',kind:'document-object'}],sessions:[{id:'form-1',entry:1,title:'Order'}],active:'form-1',uncertain:false,catalog:null,choice:null,...extra});
const response=(request,value=snapshot(),extra={})=>({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state:value,error:null,session:null,form:null,...extra}});
const locate=(root,label)=>all(root).find(node=>node.getAttribute('aria-label')===label);
const named=(env,text)=>buttons(env.document).find(node=>node.textContent===text);
const settle=()=>new Promise(resolve=>setTimeout(resolve,0));
function host(options={}){
  const env=environment(),requests=[];let appState=snapshot(options.restored?{choice:choice()}:{}),form=state(0,{items:[field('Name'),field('Product',ref()),
    table({columns:[column('Product','FormCatalogRef')],rows:[{id:9,values:[ref()]}]}),button()]});
  const exchange=async request=>{
    requests.push(request);if(options.before)await options.before(request);
    if(request.method==='application.form'){
      const inner=request.params.request,p=inner.params;
      if(inner.method==='form.event') form={...form,revision:form.revision+1,items:form.items.map(item=>item.name===p.control&&p.event==='change'?{...item,value:p.value}:item)};
      return response(request,appState,{session:'form-1',form:reply(inner,form)});
    }
    if(request.method==='application.reference'){
      const a=request.params.action;
      if(a.action==='begin')appState={...appState,choice:choice({control:a.control,row:a.row,column:a.column,...options.projection})};
      if(a.action==='page')appState={...appState,choice:{...appState.choice,rows:[{choice:'e'.repeat(32),code:'P33',description:'Last'}],navigation:{...appState.choice.navigation,page:2,previous:'reference-page-'+('f'.repeat(32)),next:null}}};
      if(a.action==='search')appState={...appState,choice:{...appState.choice,code:'',rows:[{choice:'e'.repeat(32),code:'P33',description:'Last'}],navigation:{page:1,pages:1,total:1,previous:null,next:null,query:a.query}}};
      if(a.action==='filter')appState={...appState,choice:{...appState.choice,code:a.code,error:null,rows:[{choice:'e'.repeat(32),code:a.code,description:'Filtered'}],...(Object.hasOwn(appState.choice,'navigation')?{navigation:{page:1,pages:1,total:1,previous:null,next:null,query:''}}:{})}};
      if(['apply','clear'].includes(a.action)){
        const locator=a.action==='apply'?appState.choice:a;
        const value=ref(a.action==='clear'?{key:null,text:''}:{key:'f'.repeat(32),text:'Selected'});
        form={...form,items:form.items.map(item=>item.name!==locator.control?item:locator.row===null?{...item,value}:
          {...item,rows:item.rows.map(row=>row.id!==locator.row?row:{...row,values:[value]})})};
      }
      if(['apply','clear','cancel'].includes(a.action))appState={...appState,choice:null};
      form={...form,revision:form.revision+1};
      if(options.lost&&a.action==='apply')throw Error('response lost');
      const error=options.refused?'reference_refused':null;
      return response(request,appState,{session:'form-1',form:reply({id:1},form,error),error});
    }
    return response(request,appState);
  };
  const app=mountApplication(env,env.document.root,exchange);
  const ready=async()=>{await app.ready;await Promise.all([...app.mounts.values()].map(entry=>entry.mount.ready));await settle();};
  const owner=()=>app.mounts.get('form-1').mount;
  return {env,app,requests,ready,owner,async begin(action=begin()){await owner().reference(action);await settle();}};
}

test('reference profile choice is optional while legacy application snapshots remain exact',()=>{
  const request={id:1,method:'application.hello',params:{}};
  const legacy=snapshot();delete legacy.choice;
  for(const value of [legacy,snapshot(),snapshot({choice:choice()}),snapshot({choice:choice({title:'😀'.repeat(1024),code:'Я'.repeat(64)})})])assert.equal(validateApplicationReply(response(request,value),request,null).state,value);
  assert.throws(()=>validateApplicationReply(response(request,{...legacy,other:null}),request,null));
});
test('picker projection rejects oversized, crossed, duplicate and malformed opaque identities',()=>{
  const request={id:1,method:'application.hello',params:{}};
  for(const patch of [{ticket:'bad'},{session:'form-2'},{row:1,column:null},{row:null,column:'Product'},{row:4097,column:'Product'},
    {control:''},{title:'x'.repeat(1025)},{code:'x'.repeat(65)},{rows:Array(33).fill(choice().rows[0])},
    {rows:[...choice().rows,...choice().rows]},{rows:[{...choice().rows[0],choice:'record-1'}]},
    {rows:[{...choice().rows[0],description:'\ud800'}]},{error:'raw exception'},{error:'too_many_matches'},{uuid:'forbidden'}]){
    assert.throws(()=>validateApplicationReply(response(request,snapshot({choice:choice(patch)})),request,null));
  }
});
test('reference nested replies have fixed host ID, matched session and finite authoritative errors',()=>{
  const request={id:4,method:'application.reference',params:{session:'form-1',revision:0,action:begin()}};
  const valid=response(request,snapshot(),{session:'form-1',form:reply({id:1},state(1),'reference_refused'),error:'reference_refused'});
  assert.equal(validateApplicationReply(valid,request,null).error,'reference_refused');
  for(const patch of [{session:'form-2'},{form:reply({id:2})},{form:reply({id:1},state(), 'raw error')}])assert.throws(()=>validateApplicationReply({...valid,result:{...valid.result,...patch}},request,null));
});
test('reference capability profile cannot silently appear or disappear on a retained connection',()=>{
  const request={id:1,method:'application.hello',params:{}},legacy=snapshot();delete legacy.choice;
  assert.throws(()=>validateApplicationReply(response(request,snapshot()),request,legacy));
  assert.throws(()=>validateApplicationReply(response(request,legacy),request,snapshot()));
});
test('reference client rejects unissued actions before RPC without terminal locking',async()=>{
  const requests=[],client=new ApplicationClient(async request=>{requests.push(request);return response(request,snapshot({choice:choice()}));});
  await client.request('application.hello',{});
  for(const action of [begin(),{action:'apply',ticket:'c'.repeat(32),choice:'f'.repeat(32)},
    {action:'cancel',ticket:'d'.repeat(32)},{action:'filter',ticket:'c'.repeat(32),code:'x'.repeat(65)},
    {action:'cancel',ticket:'c'.repeat(32),value:ref()}]){
    await assert.rejects(client.reference('form-1',0,action),error=>error.preDispatch===true);
  }
  assert.equal(client.terminal,false);assert.equal(requests.length,1);
});
test('scalar reference begin apply clear sends only scoped actions after scalar draft flush',async()=>{
  const h=host();await h.ready();const name=locate(h.env.document.root,'Name');name.value='Edited';name.emit('input');await h.begin();
  named(h.env,'Choose record').emit('click');await settle();await h.owner().reference(begin({action:'clear'}));
  const actions=h.requests.filter(request=>request.method==='application.reference');
  assert.deepEqual(actions.map(request=>request.params.revision),[1,2,3]);
  assert.deepEqual(actions[0].params,{session:'form-1',revision:1,action:begin()});
  assert.deepEqual(actions[1].params.action,{action:'apply',choice:'d'.repeat(32),ticket:'c'.repeat(32)});
  assert.equal(JSON.stringify(actions).includes('FormCatalogRef'),false);assert.equal(JSON.stringify(actions).includes('scope'),false);
  assert.equal(h.requests.filter(request=>request.method==='application.form'&&request.params.request.method==='form.event').length,1);
  assert.equal(locate(h.env.document.root,'Product').value,'');assert.equal(h.owner().client.snapshot.revision,4);
});
test('table reference choice uses stable row ID and column, not visual index or generic delta',async()=>{
  const h=host();await h.ready();await h.begin(begin({control:'Lines',row:9,column:'Product'}));named(h.env,'Choose record').emit('click');await settle();
  const actions=h.requests.filter(request=>request.method==='application.reference');assert.deepEqual(actions[0].params.action,begin({control:'Lines',row:9,column:'Product'}));
  assert.equal(locate(h.env.document.root,'Product, row 9').value,'Selected');assert.equal(h.owner().client.snapshot.items[2].rows[0].id,9);
});
test('overflow offers exact-code filter, never a misleading partial choice list',async()=>{
  const h=host({projection:{rows:[],error:'too_many_matches'}});await h.ready();await h.begin();
  assert.equal(named(h.env,'Choose record'),undefined);assert.ok(h.env.document.root.textContent.includes('Too many matches'));
  locate(h.env.document.root,'Exact code').value='P9';named(h.env,'Find exact code').emit('click');await settle();
  assert.deepEqual(h.requests.at(-1).params.action,{action:'filter',code:'P9',ticket:'c'.repeat(32)});
  assert.equal(h.app.client.state.choice.rows.length,1);assert.ok(h.env.document.root.textContent.includes('Filtered'));
});
test('Cancel bypasses invalid filter text and does not clear or mutate the reference',async()=>{
  const h=host();await h.ready();await h.begin();locate(h.env.document.root,'Exact code').value='x'.repeat(65);
  named(h.env,'Find exact code').emit('click');await settle();assert.equal(h.requests.filter(request=>request.method==='application.reference').length,1);
  assert.equal(named(h.env,'Cancel selection').disabled,false);named(h.env,'Cancel selection').emit('click');await settle();
  assert.equal(h.app.client.state.choice,null);assert.equal(locate(h.env.document.root,'Product').value,'Original');
  assert.equal(h.requests.at(-1).params.action.action,'cancel');assert.equal(h.app.client.terminal,false);
});
test('active picker pauses all normal owner intents, tab navigation and Close while Cancel stays usable',async()=>{
  const h=host();await h.ready();await h.begin();const count=h.requests.length;
  assert.equal(locate(h.env.document.root,'Name').disabled,true);assert.equal(named(h.env,'Close form').disabled,true);
  assert.equal(named(h.env,'Close application').disabled,true);assert.equal(named(h.env,'Cancel selection').disabled,false);
  await h.owner().run('command','Run');await h.owner().run('close');await h.owner().refresh();await h.app.openForm(1);h.app.show(null);
  assert.equal(h.requests.length,count);assert.equal(h.app.mounts.get('form-1').panel.hidden,false);
});
test('repeated Apply clicks serialize one request and never replay a completed choice',async()=>{
  const gate=deferred(),h=host({before:request=>request.method==='application.reference'&&request.params.action.action==='apply'?gate.promise:undefined});
  await h.ready();await h.begin();const apply=named(h.env,'Choose record');apply.emit('click');apply.emit('click');await settle();
  assert.equal(h.requests.filter(request=>request.params.action?.action==='apply').length,1);assert.equal(named(h.env,'Cancel selection').disabled,true);
  gate.resolve();await settle();apply.emit('click');await settle();assert.equal(h.requests.filter(request=>request.params.action?.action==='apply').length,1);
});
test('lost Apply response locks application and owner without retry or automatic cancellation',async()=>{
  const h=host({lost:true});await h.ready();await h.begin();named(h.env,'Choose record').emit('click');await settle();
  assert.equal(h.app.client.terminal,true);assert.equal(h.owner().client.transportFailed,true);
  const count=h.requests.length;named(h.env,'Cancel selection').emit('click');await h.owner().reference(begin());await settle();assert.equal(h.requests.length,count);
});
test('finite reference refusal still adopts completed snapshot and keeps application live',async()=>{
  const h=host({refused:true});await h.ready();await h.begin();assert.equal(h.app.client.terminal,false);assert.equal(h.owner().client.snapshot.revision,1);
  assert.ok(h.env.document.root.textContent.includes('reference_refused'));assert.equal(named(h.env,'Cancel selection').disabled,false);
  named(h.env,'Cancel selection').emit('click');await settle();assert.equal(h.app.client.state.choice,null);assert.equal(h.owner().client.snapshot.revision,2);
});
test('hostile picker labels and rows remain literal bounded text, never markup or URLs',async()=>{
  const hostile='<script>evil()</script> & "',h=host({projection:{title:hostile,rows:[{choice:'d'.repeat(32),code:'<img>',description:hostile}]}});
  await h.ready();await h.begin();assert.ok(h.env.document.root.textContent.includes(hostile));assert.equal(all(h.env.document.root).some(node=>['SCRIPT','IMG','A'].includes(node.tagName)),false);
  assert.equal(locate(h.env.document.root,'Choose <img> '+hostile).tagName,'BUTTON');
});
test('reload restores retained active picker and reads owner snapshot without another begin',async()=>{
  const h=host({restored:true});await h.ready();assert.equal(h.app.mounts.size,1);assert.equal(named(h.env,'Cancel selection').disabled,false);
  assert.equal(locate(h.env.document.root,'Name').disabled,true);assert.equal(h.requests.some(request=>request.method==='application.reference'),false);
  named(h.env,'Cancel selection').emit('click');await settle();assert.equal(h.app.client.state.choice,null);
});
test('picker retains filter DOM focus and returns focus to the original Choose control on cancellation',async()=>{
  const h=host();await h.ready();const choose=locate(h.env.document.root,'Choose Product');choose.focus();await h.begin();
  const code=locate(h.env.document.root,'Exact code');assert.equal(h.env.document.activeElement,code);code.value='P1';code.setSelectionRange(1,2);
  named(h.env,'Find exact code').emit('click');await settle();assert.equal(locate(h.env.document.root,'Exact code'),code);assert.equal(h.env.document.activeElement,code);
  named(h.env,'Cancel selection').emit('click');await settle();assert.equal(h.env.document.activeElement,choose);
});
test('retired row button cannot select an unissued choice after the filter projection changes',async()=>{
  const h=host();await h.ready();await h.begin();const stale=named(h.env,'Choose record');
  locate(h.env.document.root,'Exact code').value='P2';named(h.env,'Find exact code').emit('click');await settle();
  const count=h.requests.length;stale.emit('click');await settle();assert.equal(h.requests.length,count);assert.equal(h.app.client.terminal,false);
  assert.equal(h.app.client.state.choice.rows[0].choice,'e'.repeat(32));
});
test('Escape cancels without synthetic clear and modal Tab wraps to accessible controls',async()=>{
  const h=host();await h.ready();await h.begin();const dialog=all(h.env.document.root).find(node=>node.getAttribute('role')==='dialog');
  const code=locate(h.env.document.root,'Exact code');code.focus();let prevented=false;
  dialog.emit('keydown',{key:'Tab',shiftKey:true,preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(h.env.document.activeElement,named(h.env,'Choose record'));
  dialog.emit('keydown',{key:'Escape'});await settle();assert.equal(h.requests.at(-1).params.action.action,'cancel');assert.equal(locate(h.env.document.root,'Product').value,'Original');
});

const navigation=()=>({page:1,pages:2,total:33,previous:null,next:'reference-page-'+('a'.repeat(32)),query:''});
const pagedChoice=()=>choice({navigation:navigation(),rows:Array.from({length:32},(_,i)=>({choice:(i+1).toString(16).padStart(32,'0'),code:'P'+i,description:'Product '+i}))});
test('reference navigation rejects incomplete or forged totals and keeps overflow explicit',()=>{
 const request={id:1,method:'application.hello',params:{}};
 validateApplicationReply(response(request,snapshot({choice:pagedChoice()})),request,null);
 for(const patch of [{total:32},{page:0},{pages:3},{previous:'reference-page-'+('b'.repeat(32))},{next:'bad'},{query:'x'.repeat(129)}]){
  const c=pagedChoice();c.navigation={...c.navigation,...patch};assert.throws(()=>validateApplicationReply(response(request,snapshot({choice:c})),request,null));
 }
 const overflow=choice({rows:[],error:'snapshot_limit',navigation:null});validateApplicationReply(response(request,snapshot({choice:overflow})),request,null);
 for(const c of [choice({error:'snapshot_limit',navigation:null}),choice({rows:[],navigation:null}),choice({rows:[],error:'snapshot_limit'})])
  assert.throws(()=>validateApplicationReply(response(request,snapshot({choice:c})),request,null));
});
test('reference page request accepts only current picker cursor and bounded search',async()=>{
 const calls=[],c=pagedChoice(),client=new ApplicationClient(async r=>{calls.push(r);return response(r,snapshot({choice:c}));});
 await client.request('application.hello',{});
 for(const action of [{action:'page',ticket:c.ticket,cursor:'retired'},{action:'page',ticket:c.ticket,cursor:null},{action:'search',ticket:c.ticket,query:'x'.repeat(129)}])
  await assert.rejects(client.request('application.reference',{session:'form-1',revision:0,action}));
 assert.equal(calls.length,1);assert.equal(client.terminal,false);
});
test('catalog picker turns pages and searches without widening enum picker',async()=>{
 const c=pagedChoice(),h=host({projection:c});await h.ready();await h.begin();
 assert.equal(named(h.env,'Previous choices').disabled,true);assert.equal(named(h.env,'Next choices').disabled,false);
 named(h.env,'Next choices').emit('click');await h.app.client.tail;await settle();
 assert.deepEqual(h.requests.filter(r=>r.method==='application.reference').at(-1).params.action,{action:'page',cursor:c.navigation.next,ticket:c.ticket});
 assert.equal(named(h.env,'Next choices').disabled,true);assert.equal(named(h.env,'Previous choices').disabled,false);
 const exact=locate(h.env.document.root,'Exact code');exact.value='P33';named(h.env,'Find exact code').emit('click');await h.app.client.tail;await settle();
 const input=locate(h.env.document.root,'Reference search');input.value='Last';named(h.env,'Search references').emit('click');await h.app.client.tail;await settle();
 assert.deepEqual(h.requests.filter(r=>r.method==='application.reference').at(-1).params.action,{action:'search',query:'Last',ticket:c.ticket});
 assert.equal(named(h.env,'Previous choices').disabled,true);assert.equal(exact.value,'');
 const legacy=host();await legacy.ready();await legacy.begin();assert.equal(named(legacy.env,'Search references').hidden,true);
});
test('old visible choice is retired after a page projection',async()=>{
 const c=pagedChoice(),h=host({projection:c});await h.ready();await h.begin();
 await h.owner().reference({action:'page',ticket:c.ticket,cursor:c.navigation.next});await settle();const count=h.requests.length;
 await h.owner().reference({action:'apply',ticket:c.ticket,choice:c.rows[0].choice});
 assert.equal(h.requests.length,count);assert.equal(h.app.client.terminal,false);
});
