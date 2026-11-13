import test from 'node:test';import assert from 'node:assert/strict';
import {ApplicationClient,APPLICATION_PROTOCOL,validateApplicationReply} from '../src/client.mjs';
import {mountApplication} from './application-fixtures.mjs';
import {environment,all,buttons} from '../../form/test/fake-dom.mjs';
const defaults=()=>({deletion:'all',posting:'all',dateFrom:'',dateTo:'',descending:false});
const snapshot='records-'+('a'.repeat(32))+'-1';
const catalog=(document=false)=>({entry:1,version:1,rows:[],navigation:{snapshot,page:1,pages:1,total:0,query:'',order:document?'date':'code',previous:null,next:null}});
const state=(c,document=false)=>({kind:'application',lifecycle:'forms',messages:[],exitWarning:'',title:'Filters',entries:[{id:1,title:'Records',kind:document?'document-object':'catalog-object'}],sessions:[],active:null,uncertain:false,catalog:c});
const reply=(r,c,document=false,error=null)=>({jsonrpc:'2.0',id:r.id,result:{protocol:APPLICATION_PROTOCOL,state:state(c,document),error,session:null,form:null}});
const projection=(filters,document=false)=>{const c=catalog(document);c.navigation.filters=filters;return reply({id:1},c,document);};
const field=(env,label)=>all(env.document.root).find(n=>n.getAttribute?.('aria-label')===label);
const button=(env,label)=>buttons(env.document).find(n=>n.textContent===label);
async function mounted(document=false,before=()=>{}){
 const env=environment(),calls=[];let c=catalog(document);
 const app=mountApplication(env,env.document.root,async r=>{
  calls.push(r);const outcome=before(r);
  if(outcome)return reply(r,c,document,outcome);
  if(r.method==='application.catalogFilter'){
   const {filters,query,order}=r.params;const nav={...c.navigation,query,order};delete nav.filters;if(filters)nav.filters={...filters};c={...c,version:c.version+1,navigation:nav};
  }
  return reply(r,c,document);
 });await app.ready;return {env,app,calls};
}
test('navigation accepts exact nondefault filters without changing legacy eight keys',()=>{
 validateApplicationReply(reply({id:1},catalog()),{id:1},null);
 validateApplicationReply(projection({...defaults(),deletion:'marked'}),{id:1},null);
 for(const value of [defaults(),null,{...defaults(),descending:1},{...defaults(),extra:true},{...defaults(),deletion:'other'}])assert.throws(()=>validateApplicationReply(projection(value),{id:1},null));
});
test('dates validate calendar boundaries and catalogs reject document fields',()=>{
 for(const date of ['2024-02-29','0001-01-01','9999-12-31'])validateApplicationReply(projection({...defaults(),dateFrom:date},true),{id:1},null);
 for(const date of ['2023-02-29','0000-01-01','2024-13-01','2024-04-31',' ','2024-1-01'])assert.throws(()=>validateApplicationReply(projection({...defaults(),dateFrom:date},true),{id:1},null));
 assert.throws(()=>validateApplicationReply(projection({...defaults(),dateFrom:'2024-02-02',dateTo:'2024-02-01'},true),{id:1},null));
 for(const patch of [{posting:'posted'},{dateFrom:'2024-01-01'},{dateTo:'2024-01-01'}])assert.throws(()=>validateApplicationReply(projection({...defaults(),...patch}),{id:1},null));
});
test('filter requests keep current snapshot and exact shapes before transport',async()=>{
 const calls=[],client=new ApplicationClient(async r=>{calls.push(r);return reply(r,catalog());});await client.request('application.hello',{});
 const base={entry:1,snapshot,query:'',order:'code'};
 for(const params of [{...base,snapshot:'old',filters:{...defaults(),descending:true}},{...base,filters:defaults()},{...base,filters:{...defaults(),posting:'posted'}},{...base,filters:{...defaults(),descending:true},extra:1}])await assert.rejects(client.request('application.catalogFilter',params));
 assert.equal(calls.length,1);assert.equal(client.terminal,false);
 await client.request('application.catalogFilter',{...base,filters:{...defaults(),deletion:'unmarked',descending:true}});assert.equal(calls.length,2);
});
test('catalog UI exposes deletion and direction but not document-only controls',async()=>{
 const {env}=await mounted();assert.ok(field(env,'Deletion filter'));assert.ok(field(env,'Descending order'));
 assert.equal(field(env,'Posting filter'),undefined);assert.equal(field(env,'Date from (inclusive)'),undefined);assert.ok(button(env,'Apply filters'));assert.ok(button(env,'Reset filters'));
});
test('document filter drafts survive unrelated snapshot paints with selected sort',async()=>{
 const {env,app}=await mounted(true);
 field(env,'Posting filter').value='posted';field(env,'Posting filter').emit('change');
 field(env,'Date from (inclusive)').value='2024-02-29';field(env,'Date from (inclusive)').emit('input');
 field(env,'Record order').value='number';field(env,'Record order').emit('change');
 field(env,'Search records').value='draft';field(env,'Search records').emit('input');
 await app.client.request('application.snapshot',{});
 assert.equal(field(env,'Posting filter').value,'posted');assert.equal(field(env,'Date from (inclusive)').value,'2024-02-29');assert.equal(field(env,'Record order').value,'number');assert.equal(field(env,'Search records').value,'draft');
});
test('Apply sends typed filters and Reset omits defaults after acknowledgement',async()=>{
 const {env,app,calls}=await mounted(true);field(env,'Deletion filter').value='marked';field(env,'Deletion filter').emit('change');
 field(env,'Descending order').checked=true;field(env,'Descending order').emit('change');button(env,'Apply filters').emit('click');await app.client.tail;
 assert.deepEqual(calls.at(-1).params.filters,{...defaults(),deletion:'marked',descending:true});
 button(env,'Reset filters').emit('click');await app.client.tail;
 assert.deepEqual(calls.at(-1).params,{entry:1,snapshot,query:'',order:'date'});assert.equal(field(env,'Deletion filter').value,'all');assert.equal(field(env,'Descending order').checked,false);
});
test('invalid date range stays local and does not poison transport or erase drafts',async()=>{
 const {env,app,calls}=await mounted(true);
 for(const [label,value] of [['Date from (inclusive)','2024-02-02'],['Date through (inclusive)','2024-02-01']]){field(env,label).value=value;field(env,label).emit('input');}
 button(env,'Apply filters').emit('click');await app.client.tail;await Promise.resolve();
 assert.equal(calls.length,1);assert.equal(app.client.terminal,false);assert.equal(field(env,'Date from (inclusive)').value,'2024-02-02');
});
test('confirmed Refresh replaces unsent controls with authoritative accepted filters',async()=>{
 const {env,app,calls}=await mounted();field(env,'Deletion filter').value='marked';field(env,'Deletion filter').emit('change');
 button(env,'Refresh records').emit('click');await app.client.tail;
 assert.equal(calls.at(-1).method,'application.catalog');assert.equal(field(env,'Deletion filter').value,'all');
});

test('paging preserves unapplied filter drafts; Refresh restores last applied selection',async()=>{
 const env=environment(),next='records-page-'+('b'.repeat(32)),previous='records-page-'+('c'.repeat(32));
 const applied={...defaults(),deletion:'unmarked'};
 let c={...catalog(),rows:Array.from({length:50},(_,i)=>({key:`record-${i+1}`,code:String(i),description:'Item',deletionMark:false})),navigation:{...catalog().navigation,total:51,pages:2,next,filters:applied}};
 const app=mountApplication(env,env.document.root,async r=>{
  if(r.method==='application.catalogPage')c={...c,version:2,rows:[{key:'record-51',code:'51',description:'Last',deletionMark:false}],navigation:{...c.navigation,page:2,previous,next:null}};
  return reply(r,c);
 });await app.ready;
 field(env,'Deletion filter').value='marked';field(env,'Deletion filter').emit('change');
 field(env,'Descending order').checked=true;field(env,'Descending order').emit('change');
 field(env,'Search records').value='unsent';field(env,'Search records').emit('input');
 button(env,'Next records').emit('click');await app.client.tail;await Promise.resolve();
 assert.equal(app.client.state.catalog.navigation.page,2);
 assert.deepEqual(app.client.state.catalog.navigation.filters,applied);
 assert.equal(field(env,'Deletion filter').value,'marked');assert.equal(field(env,'Descending order').checked,true);assert.equal(field(env,'Search records').value,'unsent');
 button(env,'Refresh records').emit('click');await app.client.tail;await Promise.resolve();
 assert.equal(field(env,'Deletion filter').value,'unmarked');assert.equal(field(env,'Descending order').checked,false);assert.equal(field(env,'Search records').value,'');
});
