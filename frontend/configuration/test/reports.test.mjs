import test from 'node:test';
import assert from 'node:assert/strict';
import {validReportRequest,validateReports,createReportPanel} from '../src/reports.mjs';
import {ApplicationClient,APPLICATION_PROTOCOL} from '../src/client.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
const reports=[{id:'StockMovements',title:'Stock Movements',view:'Movements'},{id:'StockBalance',title:'Stock Balance',view:'Balance'},{id:'StockTurnovers',title:'Stock Turnovers',view:'Turnovers'}];
const state=extra=>({kind:'application',title:'Stock',entries:[{id:1,title:'Products',kind:'catalog-object'}],sessions:[],active:null,uncertain:false,catalog:null,lifecycle:'forms',messages:[],exitWarning:'',choice:null,posting:[],reports,report:null,...extra});
const params=extra=>({report:'StockBalance',at:'2026-11-11T23:59:59',start:null,end:null,...extra});
const report=()=>({...params(),view:'Balance',columns:[{name:'Product',type:'Catalog'},{name:'QuantityBalance',type:'Number'}],rows:[[{type:'Catalog',text:'<script>Product</script>'},{type:'Number',value:'1000000000000000000.125'}]]});
const reply=(request,value)=>({jsonrpc:'2.0',id:request.id,result:{protocol:APPLICATION_PROTOCOL,state:value,error:null,session:null,form:null}});
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};

test('closed report requests bind exact declared view and boundaries',()=>{
  assert.equal(validReportRequest(params(),state()),true);
  assert.equal(validReportRequest(params({report:'StockMovements',at:null}),state()),true);
  assert.equal(validReportRequest(params({report:'StockTurnovers',at:null,start:'2026-01-01T00:00:00',end:'2026-12-31T23:59:59'}),state()),true);
  for(const bad of [params({report:'SELECT *'}),params({query:'arbitrary'}),params({report:'StockMovements'}),params({at:null})])assert.equal(validReportRequest(bad,state()),false);
});
test('report boundaries reject invalid dates timezone fractions and reversed ranges',()=>{
  for(const at of ['2025-02-29T00:00:00','2026-04-31T00:00:00','0000-01-01T00:00:00','2026-11-11T24:00:00','2026-11-11T00:00:00Z','2026-11-11T00:00:00.1'])assert.equal(validReportRequest(params({at}),state()),false);
  assert.equal(validReportRequest(params({at:'2024-02-29T00:00:00'}),state()),true);
  assert.equal(validReportRequest(params({report:'StockTurnovers',at:null,start:'2026-12-01T00:00:00',end:'2026-01-01T00:00:00'}),state()),false);
});
test('typed report projection retains exact decimal text and noncapability labels',()=>{
  const s=state({report:report()});assert.doesNotThrow(()=>validateReports(s,null));
  assert.equal(s.report.rows[0][1].value,'1000000000000000000.125');
  for(const cell of [{type:'Catalog',text:'Product',key:'private-id'},{type:'FormCatalogRef',scope:1,target:1,key:'ref',text:'Product'},{type:'Catalog',text:123}]){
    const bad=structuredClone(s);bad.report.rows[0][0]=cell;assert.throws(()=>validateReports(bad,null));
  }
});
test('reports authority and names cannot change after handshake',()=>{
  const prior=state();for(const next of [state({reports:[]}),state({reports:[...reports,{id:'Extra',title:'Extra',view:'Balance'}]})])assert.throws(()=>validateReports(next,prior));
  const absent=state();delete absent.reports;delete absent.report;assert.throws(()=>validateReports(absent,prior));
  const incomplete=state();delete incomplete.report;assert.throws(()=>validateReports(incomplete,null));
});
test('report result rejects wrong view shape types and unbounded rows',()=>{
  for(const edit of [r=>r.view='Movements',r=>r.rows[0].pop(),r=>r.rows[0][1]={type:'Number',value:'1.0e2'},r=>r.columns[1].type='RuntimeObject',r=>r.rows=Array(1001).fill(r.rows[0])]){
    const s=state({report:report()});edit(s.report);assert.throws(()=>validateReports(s,null));
  }
});
test('report request refuses picker and retained uncertain receipts before transport',async()=>{
  let calls=0;const client=new ApplicationClient(async request=>{calls++;return reply(request,state());});await client.request('application.hello',{});
  client.state.choice={ticket:'pending'};await assert.rejects(client.request('application.report',params()));
  client.state.choice=null;client.state.posting=[{state:'uncertain'}];await assert.rejects(client.request('application.report',params()));
  client.state.posting=[];client.state.kind='closed';await assert.rejects(client.request('application.report',params()));
  assert.equal(calls,1);assert.equal(client.terminal,false);
});
test('report result is read only and clears when authoritative state clears it',async()=>{
  const client=new ApplicationClient(async request=>reply(request,state({report:request.method==='application.report'?report():null})));
  await client.request('application.hello',{});await client.request('application.report',params());assert.equal(client.state.report.rows.length,1);
  await client.request('application.snapshot',{});assert.equal(client.state.report,null);assert.equal(client.state.sessions.length,0);
});
test('report panel renders text not HTML and never exposes reference handles',()=>{
  const env=environment(),host=env.document.createElement('section');env.document.root.append(host);
  const panel=createReportPanel(env.document,host,async()=>{},()=>false);panel.update(state({report:report()}));
  buttons(env.document).find(b=>b.textContent==='Stock Balance').emit('click');
  assert.ok(all(host).some(n=>n.textContent==='<script>Product</script>'));assert.equal(all(host).some(n=>n.tagName==='SCRIPT'),false);
});
test('report panel repeated clicks send once while pending and do not auto replay',async()=>{
  const env=environment(),host=env.document.createElement('section');env.document.root.append(host);let calls=0,finish;
  const panel=createReportPanel(env.document,host,()=>{calls++;return new Promise(resolve=>finish=resolve);},()=>false);panel.update(state());
  const show=buttons(env.document).find(b=>b.textContent==='Show saved stock');show.emit('click');show.emit('click');assert.equal(calls,1);assert.equal(panel.pending(),true);
  finish({error:'report_unavailable'});await flush();assert.equal(calls,1);assert.equal(panel.pending(),false);
  assert.ok(all(host).some(n=>n.textContent.includes('exceeds the bounded result limit')));
});

test('edited boundaries do not relabel an older report as the new period',()=>{
  const env=environment(),host=env.document.createElement('section');env.document.root.append(host);let calls=0;
  const panel=createReportPanel(env.document,host,async()=>{calls++;},()=>false);panel.update(state({report:report()}));
  buttons(env.document).find(b=>b.textContent==='Stock Balance').emit('click');
  const input=all(host).find(n=>n.getAttribute?.('aria-label')==='Balance before moment (exclusive)');
  input.value='2028-01-01T00:00:00';input.emit('input');
  assert.equal(calls,0);assert.ok(all(host).some(n=>n.textContent.includes('Displayed balance before 2026-11-11T23:59:59')));
  assert.equal(all(host).some(n=>n.textContent.includes('Displayed balance before 2028')),false);
});
