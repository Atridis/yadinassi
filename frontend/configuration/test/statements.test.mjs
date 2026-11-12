import test from 'node:test';
import assert from 'node:assert/strict';
import {validReportRequest,validReportAction,validateReports,validateReportReply,createReportPanel} from '../src/reports.mjs';
import {ApplicationClient,APPLICATION_PROTOCOL} from '../src/client.mjs';
import {createFormView} from '../../form/src/view.mjs';
import {field,state as formState} from '../../form/test/fixtures.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
const setupTicket=n=>'setup-'+'a'.repeat(32)+'-'+n, choiceTicket=n=>'choice-'+'a'.repeat(32)+'-'+n;
const snapshot='report-'+'b'.repeat(32)+'-1', cursor=n=>'page-'+n.repeat(32), token='c'.repeat(32);
const reports=[{id:'StockStatement',title:'Stock statement',view:'BalanceAndTurnovers',periodicities:['None','Day','Month'],filters:[{id:'Product',title:'Product'}]}];
const setup=extra=>({report:'StockStatement',ticket:setupTicket(1),filters:[{id:'Product',mode:'all',text:''}],choice:null,...extra});
const choice=()=>({filter:'Product',ticket:choiceTicket(2),code:'',rows:[{choice:token,code:'P1',description:'<script>Product</script>'}],error:null});
const state=extra=>({kind:'application',title:'Stock',entries:[{id:1,title:'Products',kind:'catalog-object'}],sessions:[],active:null,uncertain:false,catalog:null,lifecycle:'forms',messages:[],exitWarning:'',choice:null,posting:[],reports,report:null,reportSetup:setup(),...extra});
const params=extra=>({report:'StockStatement',at:null,start:'2026-01-01T00:00:00',end:'2026-12-31T23:59:59',periodicity:'None',setup:setupTicket(1),...extra});
const result=extra=>({...params(),view:'BalanceAndTurnovers',filters:[{id:'Product',mode:'all',text:''}],columns:[{name:'Product',type:'Catalog'},{name:'QuantityClosingBalance',type:'Number'}],rows:[[{type:'Catalog',text:'Product'},{type:'Number',value:'10.125'}]],page:{snapshot,cursor:cursor('a'),previous:null,next:null,offset:0,total:1},...extra});
const reply=(req,s)=>({jsonrpc:'2.0',id:req.id,result:{protocol:APPLICATION_PROTOCOL,state:s,error:null,session:null,form:null}});
const flush=async()=>{for(let i=0;i<18;i++)await Promise.resolve();};
const mount=(s,request=async()=>{},command=async()=>{})=>{const env=environment(),host=env.document.createElement('section');env.document.root.append(host);const panel=createReportPanel(env.document,host,request,()=>false,command);panel.update(s);return {env,host,panel};};
const btn=(env,text)=>buttons(env.document).find(b=>b.textContent===text);

test('statement source declaration requires unique explicit periodicities and exact named filters',()=>{
  assert.doesNotThrow(()=>validateReports(state(),null));
  for(const edit of [r=>r.periodicities=['Year'],r=>r.periodicities=['Day','Day'],r=>r.filters[0].key='uuid',r=>r.filters.push(r.filters[0])]){
    const s=structuredClone(state());edit(s.reports[0]);assert.throws(()=>validateReports(s,null));
  }
});
test('statement setup field is required only by actual statement grant',()=>{
  const s=state();delete s.reportSetup;assert.throws(()=>validateReports(s,null));
  const no=state();delete no.reports;delete no.report;assert.throws(()=>validateReports(no,null));
});
test('statement request binds prepared setup and explicit 1900 to 2099 whole second period',()=>{
  assert.equal(validReportRequest(params(),state()),true);
  for(const p of [params({setup:setupTicket(2)}),params({periodicity:'day'}),params({start:'1899-12-31T23:59:59'}),params({end:'2100-01-01T00:00:00'}),params({filters:[]})])assert.equal(validReportRequest(p,state()),false);
});
test('open chooser blocks reading and apply is bound to current row and chooser',()=>{
  const s=state({reportSetup:setup({choice:choice()})});assert.equal(validReportRequest(params(),s),false);
  const p={report:'StockStatement',ticket:setupTicket(1),action:'apply',choice:choiceTicket(2),value:token};
  assert.equal(validReportAction('application.reportSetup',p,s),true);
  for(const edit of [{choice:choiceTicket(3)},{value:'d'.repeat(32)},{ticket:setupTicket(3)},{key:'uuid'}])assert.equal(validReportAction('application.reportSetup',{...p,...edit},s),false);
});
test('filter setup actions reject unknown fields raw references and cross report reuse',()=>{
  const p={report:'StockStatement',ticket:setupTicket(1),action:'empty',filter:'Product'};
  assert.equal(validReportAction('application.reportSetup',p,state()),true);
  for(const edit of [{filter:'Warehouse'},{report:'Other'},{record:'record-1'},{filter:{id:'Product'}}])assert.equal(validReportAction('application.reportSetup',{...p,...edit},state()),false);
});
test('chooser projection has bounded unique opaque row tokens and no persistent keys',()=>{
  const valid=state({reportSetup:setup({choice:choice()})});assert.doesNotThrow(()=>validateReports(valid,null));
  for(const edit of [c=>c.rows[0].uuid='secret',c=>c.rows.push(c.rows[0]),c=>c.error='too_many_matches',c=>c.ticket=setupTicket(1)]){
    const bad=structuredClone(valid);edit(bad.reportSetup.choice);assert.throws(()=>validateReports(bad,null));
  }
});
test('empty selected and omitted filters remain distinct closed values',()=>{
  for(const [mode,text] of [['all',''],['empty','(empty reference)'],['selected','Product']])assert.doesNotThrow(()=>validateReports(state({reportSetup:setup({filters:[{id:'Product',mode,text}]})}),null));
  for(const filter of [{id:'Product',mode:'all',text:'Product'},{id:'Product',mode:'empty',text:''},{id:'Product',mode:'selected',text:'Product',key:'uuid'}])assert.throws(()=>validateReports(state({reportSetup:setup({filters:[filter]})}),null));
});
test('page metadata is bounded and offsets cannot silently truncate a snapshot',()=>{
  assert.doesNotThrow(()=>validateReports(state({report:result()}),null));
  for(const edit of [p=>p.total=1001,p=>p.offset=1,p=>p.previous=cursor('b'),p=>p.next=cursor('a'),p=>p.cursor='uuid',p=>p.total=0]){
    const bad=result();edit(bad.page);assert.throws(()=>validateReports(state({report:bad}),null));
  }
});
test('page tokens cannot be routed to another snapshot or unissued neighbor',()=>{
  const s=state({report:result()});assert.equal(validReportAction('application.reportPage',{snapshot,cursor:cursor('a')},s),true);
  assert.equal(validReportAction('application.reportPage',{snapshot,cursor:cursor('z')},s),false);
  assert.equal(validReportAction('application.reportPage',{snapshot:snapshot+'x',cursor:cursor('a')},s),false);
});
test('page reply keeps exact original header filters total and requested cursor',()=>{
  const old=state({report:result({page:{snapshot,cursor:cursor('a'),previous:null,next:cursor('b'),offset:0,total:2}})});
  const next=result({page:{snapshot,cursor:cursor('b'),previous:cursor('a'),next:null,offset:1,total:2}});
  const request={method:'application.reportPage',params:{snapshot,cursor:cursor('b')}};
  assert.doesNotThrow(()=>validateReportReply({error:null,state:state({report:next})},request,old));
  for(const edit of [r=>r.start='2025-01-01T00:00:00',r=>r.filters[0].text='forged',r=>r.page.total=3,r=>r.page.cursor=cursor('c')]){
    const bad=structuredClone(next);edit(bad);assert.throws(()=>validateReportReply({error:null,state:state({report:bad})},request,old));
  }
});
test('fresh report response must bind setup and start at first page',()=>{
  const request={method:'application.report',params:params()};
  for(const edit of [r=>r.setup=setupTicket(5),r=>r.periodicity='Day',r=>r.page.offset=1]){
    const bad=result();edit(bad);assert.throws(()=>validateReportReply({error:null,state:state({report:bad})},request,state()));
  }
});
test('setup selection change rotates ticket while cancel keeps committed filters',()=>{
  const old=state({reportSetup:setup({choice:choice()})});
  const request={method:'application.reportSetup',params:{report:'StockStatement',ticket:setupTicket(1),action:'cancel',choice:choiceTicket(2)}};
  assert.doesNotThrow(()=>validateReportReply({error:null,state:state()},request,old));
  assert.throws(()=>validateReportReply({error:null,state:state({reportSetup:setup({ticket:setupTicket(3)})})},request,old));
});
test('queued page or chooser action is revalidated against latest authoritative state before transport',async()=>{
  let count=0;const client=new ApplicationClient(async req=>{count++;return reply(req,state({report:result()}));});
  await client.request('application.hello',{});const pending=client.request('application.reportPage',{snapshot,cursor:cursor('a')});client.state=state();
  await assert.rejects(pending);assert.equal(count,1);assert.equal(client.terminal,false);
});
test('tampered statement response locks client without replay',async()=>{
  let count=0;const client=new ApplicationClient(async req=>{count++;const r=result();if(req.method==='application.report')r.setup=setupTicket(2);return reply(req,state({report:req.method==='application.report'?r:null}));});
  await client.request('application.hello',{});await assert.rejects(client.request('application.report',params()));assert.equal(count,2);assert.equal(client.terminal,true);
});
test('statement panel prepares explicitly and never fabricates a selection',async()=>{
  const calls=[];const {env}=mount(state({reportSetup:null}),async()=>{},async(m,p)=>{calls.push([m,p]);});
  assert.equal(btn(env,'Show saved stock').disabled,true);btn(env,'Prepare statement').emit('click');await flush();
  assert.deepEqual(calls,[['application.reportSetup',{report:'StockStatement',action:'open'}]]);
});
test('chooser labels render as text and cancel is ticket bound',async()=>{
  const calls=[];const {env,host}=mount(state({reportSetup:setup({choice:choice()})}),async()=>{},async(m,p)=>calls.push([m,p]));
  assert.equal(all(host).some(n=>n.tagName==='SCRIPT'),false);assert.ok(btn(env,'<script>Product</script>'));
  btn(env,'Cancel statement choice').emit('click');await flush();assert.equal(calls[0][1].choice,choiceTicket(2));assert.equal(calls[0][1].action,'cancel');
});
test('retired chooser DOM cannot apply a row to a new setup',async()=>{
  let calls=0;const {env,panel}=mount(state({reportSetup:setup({choice:choice()})}),async()=>{},async()=>{calls++;});
  const retired=btn(env,'<script>Product</script>');panel.update(state({reportSetup:setup({ticket:setupTicket(5)})}));retired.emit('click');await flush();assert.equal(calls,0);
});
test('double next page is one request while pending with no automatic replay',async()=>{
  let calls=0,resolve;const r=result({page:{snapshot,cursor:cursor('a'),previous:null,next:cursor('b'),offset:0,total:2}});
  const {env,panel}=mount(state({report:r}),async()=>{},()=>{calls++;return new Promise(r=>resolve=r);});
  const next=btn(env,'Next saved page');next.emit('click');next.emit('click');assert.equal(calls,1);assert.equal(panel.pending(),true);
  resolve({error:'report_unavailable'});await flush();assert.equal(calls,1);assert.equal(panel.pending(),false);
});
test('retired page DOM cannot navigate into another report snapshot',async()=>{
  let calls=0;const r=result({page:{snapshot,cursor:cursor('a'),previous:null,next:cursor('b'),offset:0,total:2}});
  const {env,panel}=mount(state({report:r}),async()=>{},async()=>{calls++;});const next=btn(env,'Next saved page');panel.update(state());next.emit('click');await flush();assert.equal(calls,0);
});
test('empty and all buttons send different actions not raw UUID values',async()=>{
  const calls=[];const {env}=mount(state(),async()=>{},async(m,p)=>calls.push([m,p]));
  btn(env,'Empty Product').emit('click');await flush();btn(env,'All Product').emit('click');await flush();
  assert.deepEqual(calls.map(c=>c[1].action),['empty','clear']);assert.ok(calls.every(c=>Object.keys(c[1]).sort().join()==='action,filter,report,ticket'));
});
test('editing periodicity does not relabel an older detached statement',()=>{
  const {env,host}=mount(state({report:result()}));const select=all(host).find(n=>n.getAttribute?.('aria-label')==='Statement periodicity');select.value='Month';select.emit('change');
  assert.ok(all(host).some(n=>n.textContent.startsWith('Statement periodicity: None.')));assert.equal(all(host).some(n=>n.textContent.startsWith('Statement periodicity: Month.')),false);
});
test('empty statement page shows zero of zero without navigation or truncation',()=>{
  const r=result({rows:[],page:{snapshot,cursor:cursor('a'),previous:null,next:null,offset:0,total:0}});const {env,host}=mount(state({report:r}));
  assert.ok(all(host).some(n=>n.textContent.startsWith('0–0 of 0 saved rows.')));assert.equal(btn(env,'Next saved page').disabled,true);assert.equal(btn(env,'Previous saved page').disabled,true);
});

test('report pointer and focus boundaries preserve raw form draft without OnChange',()=>{
  const {env,host}=mount(state({reportSetup:setup({choice:choice()})}));let changes=0;
  const form=env.document.createElement('section');env.document.root.append(form);
  const view=createFormView(env.document,form,{change(){changes++;},action(){},refresh(){}});
  view.render({snapshot:formState(0,{items:[field('Name',{type:'String',value:'Saved'})]}),busy:false,locked:false,error:'',connected:true,outcomeUnknown:false,transportFailed:false,exhausted:false});
  const input=all(form).find(n=>n.tagName==='INPUT');input.value='Unsaved raw';input.emit('input');input.focus();
  for(const target of all(host).filter(n=>['BUTTON','INPUT','SELECT'].includes(n.tagName))){
    input.emit('blur',{relatedTarget:target});
    if(target.tagName==='BUTTON'){let prevented=false;target.emit('pointerdown',{preventDefault(){prevented=true;}});assert.equal(prevented,true);}
  }
  assert.equal(changes,0);assert.deepEqual(view.changes(),[{control:'Name',value:{type:'String',value:'Unsaved raw'}}]);
});
