import test from 'node:test';
import assert from 'node:assert/strict';
import {readOnlyScalarText, scalarText, editable} from '../../form/src/client.mjs';
import {reportCellText, reportColumnTitle, createReportPanel} from '../src/reports.mjs';
import {environment, all} from '../../form/test/fake-dom.mjs';
const date=ticks=>({type:'Date',ticks});
const report=()=>({report:'StockMovements',view:'Movements',at:null,start:null,end:null,
  columns:[{name:'Period',type:'Date'},{name:'QuantityOpeningBalance',type:'Number'},{name:'Product',type:'Catalog'}],
  rows:[[date('639299952000000'),{type:'Number',value:'1000000000000000000.125'},{type:'Catalog',text:'<script>Product</script>'}]]});
const state=result=>({kind:'application',reports:[{id:'StockMovements',title:'Stock Movements',view:'Movements'}],report:result,choice:null,uncertain:false,posting:[]});
function render(){const env=environment(),host=env.document.createElement('section');env.document.root.append(host);let requests=0;
  const panel=createReportPanel(env.document,host,async()=>{requests++;},()=>false);panel.update(state(report()));return {env,host,panel,requests:()=>requests};}

test('saved report dates render exact Gregorian whole seconds without changing the value',()=>{
  const value=Object.freeze(date('639299952000000'));assert.equal(reportCellText(value),'2026-11-11 12:00:00');assert.equal(value.ticks,'639299952000000');
  assert.equal(readOnlyScalarText(date('621355968000000')),'1970-01-01 00:00:00');
});
test('empty and full upper-bound dates remain explicit outside the editing envelope',()=>{
  assert.equal(readOnlyScalarText(date('0')),'Empty date');assert.equal(readOnlyScalarText(date('864000000')),'0001-01-02 00:00:00');
  const value=date('3155378975990000');assert.equal(readOnlyScalarText(value),'9999-12-31 23:59:59');
  assert.equal(scalarText(value,{kind:'date',parts:'dateTime'}),value.ticks);
  assert.equal(editable({kind:'field',visible:true,enabled:true,readOnly:false,value,editor:{kind:'date',parts:'dateTime'}}),false);
});
test('leap and nonleap century dates use the shared exact calendar',()=>{
  assert.equal(readOnlyScalarText(date('630874244960000')),'2000-02-29 12:34:56');
  assert.equal(readOnlyScalarText(date('599317056000000')),'1900-03-01 00:00:00');
});
test('fractional date ticks remain visibly exact and malformed scalars are still refused',()=>{
  assert.equal(readOnlyScalarText(date('1')),'1 ticks (exact date)');
  assert.equal(readOnlyScalarText(date('639299952000001')),'639299952000001 ticks (exact date)');
  for(const ticks of ['-1','01','1.5','3155378975990001'])assert.throws(()=>readOnlyScalarText(date(ticks)));
});
test('non-date scalar and reference text remains byte-exact and not a capability',()=>{
  assert.equal(reportCellText({type:'Number',value:'1000000000000000000.125'}),'1000000000000000000.125');
  assert.equal(reportCellText({type:'Catalog',text:'<script>Product</script>'}),'<script>Product</script>');
  assert.equal(readOnlyScalarText({type:'Boolean',value:false}),'No');
});
test('column spacing is presentation only and retains arbitrary Unicode source names',()=>{
  assert.equal(reportColumnTitle({name:'QuantityOpeningBalance'}),'Quantity Opening Balance');
  assert.equal(reportColumnTitle({name:'HTTPCode'}),'HTTP Code');
  assert.equal(reportColumnTitle({name:'КоличествоОстаток'}),'КоличествоОстаток');
  assert.equal(reportColumnTitle({name:'<b>Amount</b>'}),'<b>Amount</b>');
});
test('wide saved rows have an accessible keyboard-focusable native scroll region',()=>{
  const {host}=render(),region=all(host).find(n=>n.className==='configuration-report-table-scroll');
  assert.equal(region.getAttribute('role'),'region');assert.equal(region.getAttribute('aria-label'),'Stock Movements saved rows');assert.equal(region.getAttribute('tabindex'),'0');
  assert.ok(all(region).filter(n=>n.tagName==='TH').every(n=>n.getAttribute('scope')==='col'));
});
test('original column name and exact text cells remain visible without HTML interpretation',()=>{
  const {host}=render(),nodes=all(host);assert.ok(nodes.some(n=>n.tagName==='SMALL'&&n.textContent==='QuantityOpeningBalance'));
  assert.ok(nodes.some(n=>n.tagName==='TD'&&n.textContent==='2026-11-11 12:00:00'));
  assert.ok(nodes.some(n=>n.tagName==='TD'&&n.textContent==='<script>Product</script>'));assert.equal(nodes.some(n=>n.tagName==='SCRIPT'),false);
});
test('presentation and repeated paint never send a request or mutate a detached result',()=>{
  const {panel,requests}=render(),value=report(),before=JSON.stringify(value);panel.update(state(value));panel.update(state(value));
  assert.equal(requests(),0);assert.equal(JSON.stringify(value),before);
});
