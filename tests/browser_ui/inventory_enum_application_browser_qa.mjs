/** Пять связанных UI-сценария enum inventory; не свидетельство native parity. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile,rm,lstat,readdir} from 'node:fs/promises';
import {readFileSync,readlinkSync,lstatSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {launchOutputReader,allowedRequest,childEnvironment,ownBrowserPid,
  commandLineArgs,sandboxCommand,sandboxStatus,sha256,launchURL} from './support.mjs';

const startedAt=Date.now();
const workDeadline=startedAt+400000;
const totalDeadline=startedAt+420000;
const rpcFetchMs=35000,rpcReplyMs=50000; // Existing transport and observer budgets; global deadline unchanged.
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
const screenshots=['enum-catalogs.png','enum-written.png','enum-posted-report.png','enum-reopened-unposted.png','enum-record-pages.png','enum-reference-pages.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['catalog_enum_choice_save','receipt_header_line_enum_write',
 'post_visible_enum_movements','restart_reopen_unpost','record_pages_search_refresh','reference_pages_search_save_reopen'];
// Ровно 262 деловых RPC: 14 + 15 + 3 + 7 + 212 + 11. Hello/snapshot и lease heartbeat
// наблюдаются отдельно; бизнес-запросы не синтезируются и не повторяются.
const businessPlan=[
 ["catalog", "open", "change:CodeInput", "change:DescriptionInput", "reference:begin", "reference:apply", "command:SaveButton", "close:", "catalog", "open", "change:CodeInput", "change:DescriptionInput", "command:SaveButton", "close:"],
 ["catalog", "open", "change:NumberInput", "reference:begin", "reference:apply", "reference:begin", "reference:apply", "command:AddLineButton", "reference:begin", "reference:apply", "reference:begin", "reference:apply", "cell:LinesTable", "cell:LinesTable", "command:WriteButton"],
 ["command:PostButton", "report:StockMovements", "close:"],
 ["close", "catalog", "openRecord", "command:UndoPostingButton", "report:StockMovements", "close:", "close"],
 ["catalog",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "open","change:CodeInput","command:SaveButton","close:",
  "catalogPage","openRecord","change:DescriptionInput","command:SaveButton","close:","catalogPage","catalogFilter","catalogFilter","catalogPage","catalog","close"],
 ["catalog","openRecord","reference:begin","reference:page","reference:search","reference:apply","command:WriteButton","close:","openRecord","close:","close"]
];
const businessEvents=[];
// Closed diagnostic vocabulary only. Values from assertions, DOM, callbacks,
// storage, environment and subprocess stderr never become artifact strings.
const diagnosticPhases=['command_binding','command_click','command_wait','command_read','command_outcome','command_idle',
 'fixture_create','fixture_audit','audit_catalogs','audit_document_count',
 'audit_document_posted','audit_document_quantity','audit_no_movements',
 'screenshot_capability','screenshot_storage','screenshot_cookies','screenshot_capture','business_plan',
 'report_tab','report_fill','report_click','report_wait','report_read','report_assert','report_done',
 'late_owner_pin','late_owner_return','late_owner_delivery'];
const diagnosticReasons=['session_panel_binding','active_session_missing','command_session_changed',
 'command_outcome_count','posting_outcome','audit_catalogs','audit_document_count',
 'audit_document_posted','audit_document_quantity','write_created_movements',
 'capability_not_removed','only_resume_storage','browser_cookies_not_empty',
 'owned_fixture_failed','owned_fixture_timeout','business_rpc_plan_changed',
 'late_reply_changed_owner','duplicate_open_rpc','duplicate_write_rpc','duplicate_post_rpc',
 'duplicate_write_revision','shortage_changed_persisted_state','shortage_not_rejected',
 'resource_value','report_refused','balance_not_exclusive','unsaved_draft_changed_persistence',
 'audited_reply_missing','audited_reply_request','audited_reply_origin','audited_reply_budget','audited_reply_duplicate','audited_reply_id',
 'report_html_period','report_period_request','report_period_result'];
const diagnosticReason=error=>diagnosticReasons.find(code=>error?.message===code||typeof error?.message==='string'&&error.message.startsWith(code+'\n')) ||
 (error?.name==='TimeoutError'?'browser_operation_timeout':'step_failed');
const checkpoint=label=>{assert.ok(diagnosticPhases.includes(label),'invalid_diagnostic_phase');phase=label;};
let activeScenario=null;

const tokens=[],results=[];
const report={status:'FAIL',sourceCommit:null,scenarios:results,sandbox:null,heartbeatBusy:0};
let output,owned,home,env,host,browser,context,page,hostGroup,browserGroup;
let outputCreated=false,origin='',url='',phase='binding',aborted=false,rpc=0,failed=false;
const bounded=(promise,ms,code)=>{
  let timer;return Promise.race([promise,new Promise((_,reject)=>{
    timer=setTimeout(()=>reject(Error(code)),ms);
  })]).finally(()=>clearTimeout(timer));
};
const check=()=>{if(aborted||Date.now()>=workDeadline){aborted=true;throw Error('global_deadline_or_budget');}};
const remaining=max=>{check();return Math.max(1,Math.min(max,workDeadline-Date.now()));};
const cleanupRemaining=max=>Math.max(1,Math.min(max,totalDeadline-Date.now()));
const git=(...args)=>execFileSync('git',args,{cwd:repo,encoding:'utf8',timeout:remaining(5000),maxBuffer:1024*1024,stdio:['ignore','pipe','pipe']}).trim();

// Only fixed labels leave this process. Never export raw launch errors, paths,
// command arguments, environment values, process IDs or assertion actual/expected.
function launchFailureCode(error){
  const message=typeof error?.message==='string'?error.message:'';
  const fixed=['invalid_owned_pid','process_uid_mismatch','process_not_direct_child',
    'process_group_not_owned','unexpected_launch_children','browser_executable_mismatch',
    'browser_command_budget','browser_command_invalid','sandbox_command_missing','sandbox_disabled',
    'unexpected_browser_transport','browser_profile_missing','browser_profile_not_owned',
    'browser_socket_path_too_long','browser_process_missing','cdp_setup_timeout','cdp_process_timeout','browser_pid_invalid',
    'browser_pid_mismatch','cdp_detach_timeout','context_timeout','sandbox_status_invalid','sandbox_not_confirmed'];
  for(const code of fixed)if(message===code||message.startsWith(code+'\n'))return code;
  if(/Operation not permitted|No usable sandbox|Failed to move to new namespace/i.test(message))return 'sandbox_start_denied';
  if(/Executable doesn't exist/i.test(message))return 'browser_binary_missing';
  if(/error while loading shared libraries|Host system is missing dependencies/i.test(message))return 'browser_dependency_missing';
  if(error?.name==='TimeoutError')return 'browser_operation_timeout';
  if(error?.code==='ENOENT')return 'launch_file_missing';
  if(error?.code==='EACCES'||error?.code==='EPERM')return 'launch_access_denied';
  if(error?.code==='ESRCH')return 'launch_process_gone';
  return 'unclassified_launch_failure';
}

function processIdentity(pid){
  assert.ok(Number.isSafeInteger(pid)&&pid>0,'invalid_owned_pid');
  const root='/proc/'+pid,stat=readFileSync(root+'/stat','utf8');
  const fields=stat.slice(stat.lastIndexOf(')')+2).trim().split(/\s+/);
  assert.equal(lstatSync(root).uid,process.getuid(),'process_uid_mismatch');
  assert.equal(Number(fields[1]),process.pid,'process_not_direct_child');
  assert.equal(Number(fields[2]),pid,'process_group_not_owned');
  return {pid,start:fields[19]};
}
function signalGroup(identity,signal){
  if(!identity)return;
  try{
    // Reject a live, reused PID. A leaderless live group retains its reserved PGID.
    try{assert.deepEqual(processIdentity(identity.pid),identity,'owned_process_identity_changed');}
    catch(error){if(error.code!=='ENOENT'&&error.code!=='ESRCH')throw error;}
    process.kill(-identity.pid,signal);
  }catch(error){if(error.code!=='ESRCH')throw error;}
}
const cleanupFailure=code=>{report.status='FAIL';report.cleanup=code;};
function abort(){
  aborted=true;
  for(const identity of [hostGroup,browserGroup]){
    try{signalGroup(identity,'SIGKILL');}catch{cleanupFailure('owned_signal_failed');}
  }
}
async function groupGone(identity){
  if(!identity)return;
  for(let attempt=0;attempt<20&&Date.now()<totalDeadline;attempt++){
    try{process.kill(-identity.pid,0);}
    catch(error){if(error.code==='ESRCH')return;throw error;}
    await new Promise(resolve=>setTimeout(resolve,cleanupRemaining(100)));
  }
  throw Error('owned_group_cleanup_unverified');
}
async function stopHost(){
  if(!host)return;
  try{
    if(host.exitCode===null&&host.signalCode===null){
      const ended=new Promise(resolve=>host.once('exit',resolve));
      signalGroup(hostGroup,'SIGINT');
      try{await bounded(ended,cleanupRemaining(5000),'host_close_timeout');}
      catch{signalGroup(hostGroup,'SIGKILL');await bounded(ended,cleanupRemaining(2000),'host_kill_timeout');}
    }
  }finally{signalGroup(hostGroup,'SIGKILL');}
  await groupGone(hostGroup);host=null;hostGroup=null;origin='';
}
function applicationLaunchReader(){
  let buffered='',settled=false;
  return chunk=>{
    if(settled)return null;
    if(!Buffer.isBuffer(chunk)||Buffer.byteLength(buffered)+chunk.length>4096)throw Error('host_output_budget');
    buffered+=chunk.toString();
    const match=buffered.match(/^http:\/\/127\.0\.0\.1:[0-9]+\/#session=[A-Za-z0-9_-]{43}&attachment=1(?=\r?\n)/m);
    if(!match)return null;
    settled=true;buffered='';
    const checked=launchURL(match[0].slice(0,-13));checked.hash+='&attachment=1';return checked;
  };
}
function applicationAllowedRequest(target){
  if(allowedRequest(target,origin))return true;
  try{const parsed=new URL(target);return parsed.origin===origin&&!parsed.username&&!parsed.password&&!parsed.search&&parsed.pathname==='/attachment';}
  catch{return false;}
}
async function startHost(){
  check();assert.ok(!host&&!hostGroup,'previous_host_live');
  observedReplies.clear(); // A new real host has a new origin/request-ID space.
  const args=['-m','yadinassi','--ui','--f',path.join(owned,'stock.sqlite')];
  host=spawn(python,args,{cwd:repo,env,detached:true,stdio:['ignore','pipe','ignore']});
  const parse=applicationLaunchReader();let settled=false;
  url=await bounded(new Promise((resolve,reject)=>{
    const finish=(callback,value)=>{if(!settled){settled=true;callback(value);}};
    host.once('error',()=>finish(reject,Error('host_spawn_failed')));
    host.once('spawn',()=>{try{hostGroup=processIdentity(host.pid);}catch{finish(reject,Error('host_identity_failed'));}});
    host.once('exit',()=>finish(reject,Error('host_exited_before_launch')));
    host.stdout.on('data',data=>{
      if(settled)return; // Drain, never retain launcher output or capability URLs.
      try{const found=parse(data);if(found){origin=found.origin;tokens.push(new URLSearchParams(found.hash.slice(1)).get('session'));finish(resolve,found.href);}}
      catch{finish(reject,Error('invalid_launch_output'));}
    });
  }),remaining(15000),'host_start_timeout');
}
const button=name=>page.getByRole('button',{name,exact:true});
const entries=()=>page.getByRole('navigation',{name:'Declared forms',exact:true});
const tabs=()=>page.getByRole('navigation',{name:'Open forms',exact:true});
const panels=()=>page.locator('.configuration-form-panels > section');
const active=()=>page.locator('.configuration-form-panels > section:not([hidden])');
const field=name=>active().getByLabel(name,{exact:true});
const action=name=>active().getByRole('button',{name,exact:true});
const catalog=()=>page.locator('.configuration-catalog');
// Independent typed audit: no report service, Query, UI projection, posting
// handler or data seeding. Every business row is created through the browser.
const fixtureCode=String.raw`
import json,sys
from pathlib import Path
from contextlib import closing
from datetime import datetime
from decimal import Decimal, localcontext
from hashlib import sha256
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.configuration_inventory_enum_application import import_inventory_application, PROFILE, validated_core
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.catalog_backend import CatalogKey, CatalogSelection, BackendError
from yadinassi.document_backend import DocumentKey, DocumentSelection
from yadinassi.sqlite_documents import DocumentView
from yadinassi.sqlite_transactions import _accumulation_port
from yadinassi.accumulation_movements import AccumulationDirection
from yadinassi.enum_storage_values import EnumKey
root=Path(sys.argv[2]); database=root/'stock.sqlite'
sys.path.insert(0,str(Path.cwd()/'tests'))
from inventory_enum_application_fixture import source as historical_source
try:
 files=historical_source()
 config=import_inventory_application(files,inventory_runtime=PROFILE)
 if sys.argv[1]=='create':
  assert not database.exists()
  SQLiteCatalogBackend.create_inventory_enum_application(database,config).close()
  with closing(SQLiteCatalogBackend.create_inventory_enum(root/'core-only.sqlite',validated_core(config))) as core:
   try: core.launch_snapshot()
   except BackendError as failure: assert failure.code=='unsupported'
   else: raise AssertionError('core16_ui_grant')
  result={'created':True,'core16Denied':True}
 elif sys.argv[1] in ('audit','audit-picked'):
  before=sha256(database.read_bytes()).digest()
  def number(value):
   assert type(value) is Decimal
   with localcontext() as ctx:
    ctx.prec=50
    return format(value.normalize(),'f')
  with closing(SQLiteCatalogBackend(database,read_only=True)) as backend:
   snap=backend.launch_snapshot()
   assert snap.route=='inventory-enum' and snap.profile==PROFILE
   assert {f.path:f.content for f in snap.files}==files
   with closing(backend.begin_read()) as owner:
    catalogs={s.name:s for s in owner.catalogs()}; cards={}; labels={}; catalog_rows=[]
    definitions={e.name:e for e in config.enumerations}
    def enum_name(value, target):
     definition=definitions[target]
     assert type(value) is EnumKey and value.database_id==backend.database_id and value.enum_id==definition.identity
     backend._enum_domain.encode(value,definition.identity)
     if not value.value_id.int:return ''
     return next(v.name for v in definition.values if v.identity==value.value_id)
    catalog_enums=[]
    for name in sorted(catalogs):
     rows=owner.select_catalog(catalogs[name].identity,CatalogSelection(limit=64))
     assert len(rows)<64
     for card in rows:
      assert type(card.key) is CatalogKey and not card.deletion_mark
      labels[card.key]=card.code; cards[name,card.code]=card
      catalog_rows.append([name,card.code,card.description])
      if name=='Products':
       fields=dict(zip((f.name for f in catalogs[name].fields),card.values))
       catalog_enums.append(enum_name(fields['Unit'],'Units'))
    documents=[]; names={}; reader=DocumentView(owner)
    for schema in reader.documents():
     rows=reader.select_documents(schema.identity,DocumentSelection(limit=4))
     for card in rows:
      assert type(card.key) is DocumentKey and type(card.date) is datetime and not card.deletion_mark
      names[card.key]=(schema.name,card.number)
      values=dict(zip((f.name for f in schema.fields),card.values)); warehouse=values['Warehouse']
      state=enum_name(values['State'],'States')
      assert type(warehouse) is CatalogKey and warehouse.catalog_id==catalogs['Warehouses'].identity
      assert warehouse==cards['Warehouses','Z0049' if sys.argv[1]=='audit-picked' else 'W1'].key
      section=schema.tabular_sections[0]; rows=card.tabular_sections[0].rows; assert len(rows)==1
      values=dict(zip((f.name for f in section.fields),rows[0].values)); product=values['Product']
      unit=enum_name(values['Unit'],'Units')
      assert type(product) is CatalogKey and product.catalog_id==catalogs['Products'].identity
      assert product==cards['Products','P1'].key
      revision=owner._connection.execute('SELECT revision FROM document_record WHERE document_id=? AND record_id=?',
          (str(card.key.document_id),str(card.key.record_id))).fetchone()[0]
      documents.append({'kind':schema.name,'number':card.number,'revision':revision,'date':card.date.isoformat(),
       'posted':card.posted,'state':state,'unit':unit,'warehouse':labels[warehouse],'product':labels[product],
       'quantity':number(values['Quantity']),'amount':number(values['Amount'])})
    register,=config.registers; movements=[]; quantity=Decimal(0); amount=Decimal(0)
    for recorder,partition in _accumulation_port(owner).scan(register.identity):
     assert type(recorder) is DocumentKey and recorder in names and len(partition.rows)<=1
     for row in partition.rows:
      assert row.active is True and type(row.period) is datetime and type(row.direction) is AccumulationDirection
      dims=dict(zip((f.name for f in register.dimensions),row.dimensions))
      resources=dict(zip((f.name for f in register.resources),row.resources))
      all_values=dict(zip((f.name for f in (*register.dimensions,*register.attributes)),row.dimensions+row.attributes))
      unit=enum_name(all_values['Unit'],'Units');state=enum_name(all_values['State'],'States')
      assert dims['Product']==cards['Products','P1'].key and dims['Warehouse']==cards['Warehouses','W1'].key
      sign=1 if row.direction is AccumulationDirection.RECEIPT else -1
      quantity+=sign*resources['Quantity']; amount+=sign*resources['Amount']
      kind,num=names[recorder]
      movements.append({'kind':kind,'number':num,'line':row.line_number,'period':row.period.isoformat(),
       'direction':row.direction.value,'unit':unit,'state':state,'product':labels[dims['Product']],'warehouse':labels[dims['Warehouse']],
       'quantity':number(resources['Quantity']),'amount':number(resources['Amount'])})
    result={'catalogEnums':catalog_enums,'catalogs':sorted(catalog_rows),'documents':sorted(documents,key=lambda r:(r['kind'],r['number'])),
      'movements':sorted(movements,key=lambda r:(r['kind'],r['number'],r['line'])),
      'quantity':number(quantity),'amount':number(amount)}
  assert sha256(database.read_bytes()).digest()==before
 else: raise AssertionError('fixture_mode')
 print(json.dumps(result))
except Exception:
 print('{"error":"owned_inventory_fixture_failed"}',file=sys.stderr);sys.exit(1)
`;
function inventoryFixture(operation){
  assert.ok(['create','audit','audit-picked'].includes(operation),'fixture_mode');
  checkpoint(operation==='create'?'fixture_create':'fixture_audit');
  let raw;
  try{raw=execFileSync(python,['-c',fixtureCode,operation,owned],
    {cwd:repo,env,encoding:'utf8',timeout:remaining(15000),maxBuffer:16384,stdio:['ignore','pipe','ignore']});}
  catch(error){throw Error(error?.code==='ETIMEDOUT'?'owned_fixture_timeout':'owned_fixture_failed');}
  return JSON.parse(raw);
}
const replyFor=predicate=>page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.status()===200&&predicate(response.request().postDataJSON()),{timeout:remaining(rpcReplyMs)});
const formReply=(event,control)=>replyFor(packet=>packet.method==='application.form'&&packet.params.request.method==='form.event'&&packet.params.request.params.event===event&&(!control||packet.params.request.params.control===control));
let lastApplicationState=null;
// Keep already audited real responses until the matching delivered request is
// observed. Do not ask CDP to retrieve an evictable body a second time. This is
// not current UI state, a synthesized response, another fetch or an RPC retry.
const observedReplies=new Map();
function deliveredReply(response){
  const packet=response.request().postDataJSON();
  const observed=observedReplies.get(packet.id);observedReplies.delete(packet.id);
  assert.ok(observed,'audited_reply_missing');
  assert.deepEqual(observed.packet,packet,'audited_reply_request');
  assert.equal(new URL(response.url()).origin,observed.origin,'audited_reply_origin');
  assert.equal(observed.origin,origin,'audited_reply_origin');
  return observed.actual;
}
async function command(title,control,state='saved'){
 checkpoint('command_binding');
 // DOM panel insertion order follows the source-bound application sessions.
 // Pin the active opaque session before dispatch, never accept a saved sibling.
 const index=await panels().evaluateAll(nodes=>nodes.findIndex(node=>!node.hidden));
 assert.equal(lastApplicationState?.sessions.length,await panels().count(),'session_panel_binding');
 const session=lastApplicationState?.sessions[index]?.id;
 assert.match(session||'',/^form-[1-9][0-9]*$/,'active_session_missing');
 const reply=replyFor(packet=>packet.method==='application.form'&&packet.params.session===session&&
   packet.params.request.method==='form.event'&&packet.params.request.params.event==='command'&&
   packet.params.request.params.control===control);
 checkpoint('command_click');await action(title).click();
 checkpoint('command_wait');const response=await reply;
 checkpoint('command_read');const data=deliveredReply(response);checkpoint('command_outcome');
 assert.equal(data.result.session,session,'command_session_changed');
 const outcomes=data.result.state.posting.filter(item=>item.session===session);
 assert.equal(outcomes.length,1,'command_outcome_count');
 report.lastCommandOutcome=['saved','rejected','uncertain','committed'].includes(outcomes[0].state)?outcomes[0].state:'other';
 assert.equal(outcomes[0].state,state,'posting_outcome');checkpoint('command_idle');await idle();
}
async function closeForm(){const reply=formReply('close');await action('Close form').click();await reply;await idle();}
async function naturalStop(){
 const ended=new Promise(resolve=>host.once('exit',(code,signal)=>resolve({code,signal})));
 const reply=replyFor(packet=>packet.method==='application.close');await button('Close application').click();await reply;
 const result=await bounded(ended,remaining(10000),'natural_shutdown_timeout');
 assert.deepEqual(result,{code:0,signal:null},'natural_shutdown_failed');
 await groupGone(hostGroup);host=null;hostGroup=null;origin='';
}
let delayed=null;
const idle=()=>page.waitForFunction(()=>[...document.querySelectorAll('[aria-busy]')].every(node=>node.getAttribute('aria-busy')==='false'),null,{timeout:remaining(10000)});
const countPanels=count=>page.waitForFunction(expected=>document.querySelectorAll('.configuration-form-panels > section').length===expected,count,{timeout:remaining(10000)});
async function value(name,expected){
  await field(name).waitFor();
  await page.waitForFunction(({name,expected})=>[...document.querySelectorAll('.configuration-form-panels > section:not([hidden]) input')]
    .some(input=>input.getAttribute('aria-label')===name&&input.value===expected),{name,expected},{timeout:remaining(10000)});
  assert.equal(await field(name).inputValue(),expected);
}
// Text inputs commit on blur or Enter. Explicit Enter waits for the supported
// busy lifecycle instead of assuming Playwright's instantaneous focus/fill is a
// human pause between two asynchronously committing fields. Leave the final
// Stock draft deliberately remains unsaved across the report-only request.
async function commitInput(name,text){
  const reply=replyFor(packet=>packet.method==='application.form'&&['change','cell'].includes(packet.params.request.params?.event));
  await field(name).fill(text);await field(name).press('Enter');await reply;await idle();
}
const wireEvents=[];
let wireFailure=false;
const exactKeys=(value,names)=>assert.deepEqual(Object.keys(value).sort(),names.split(' ').filter(Boolean).sort(),'wire_keys');
function checkRequest(request){
  const headers=request.headers();
  assert.match(headers['x-yadinassi-session']||'',/^[A-Za-z0-9_-]{43}$/,'writer_credential');
  assert.match(headers['x-yadinassi-attachment']||'',/^attachment-[1-9][0-9]*$/,'writer_attachment');
  assert.match(headers['x-yadinassi-generation']||'',/^[0-9]{1,16}$/,'writer_generation');
  const raw=request.postData();assert.ok(raw&&Buffer.byteLength(raw)<=65536,'wire_budget');
  assert.ok(!/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/i.test(raw),'persistent_uuid_in_request');
  const packet=JSON.parse(raw);exactKeys(packet,'jsonrpc id method params');
  assert.equal(packet.jsonrpc,'2.0');assert.ok(Number.isSafeInteger(packet.id)&&packet.id>0);
  if(packet.method==='application.hello'){
    exactKeys(packet.params,'protocol dialogCapability inputCapability');assert.equal(packet.params.inputCapability,'yadinassi-owned-input/1');assert.equal(packet.params.protocol,'yadinassi-configuration-app/3');
    assert.equal(packet.params.dialogCapability,'yadinassi-owned-dialog/1');
  }else if(packet.method==='application.reference'){
    exactKeys(packet.params,'session revision action');
    assert.match(packet.params.session,/^form-[1-9][0-9]*$/);
    assert.ok(Number.isSafeInteger(packet.params.revision)&&packet.params.revision>=0);
    const a=packet.params.action;
    if(a.action==='begin'){
      exactKeys(a,'action control row column');
      assert.ok(['WarehouseInput','UnitInput','StateInput'].includes(a.control)&&a.row===null&&a.column===null ||
        a.control==='LinesTable'&&Number.isSafeInteger(a.row)&&a.row>0&&a.row<=4096&&['Product','Unit'].includes(a.column));
    }else{
      assert.ok(['apply','page','search'].includes(a.action),'declared_reference_action');
      exactKeys(a,a.action==='apply'?'action ticket choice':a.action==='page'?'action ticket cursor':'action ticket query');
      assert.equal(a.ticket,lastApplicationState?.choice?.ticket,'unissued_picker_ticket');
      assert.equal(packet.params.session,lastApplicationState.choice.session,'crossed_picker_owner');
      if(a.action==='apply')assert.ok(lastApplicationState.choice.rows.some(row=>row.choice===a.choice),'unissued_choice');
      else if(a.action==='page')assert.ok([lastApplicationState.choice.navigation?.previous,lastApplicationState.choice.navigation?.next].filter(Boolean).includes(a.cursor),'unissued_reference_page');
      else assert.equal(a.query,'ZZ updated','fixed_reference_search');
    }
  }else if(packet.method==='application.report'){
    exactKeys(packet.params,'report at start end');
    assert.ok(['StockMovements','StockBalance','StockTurnovers'].includes(packet.params.report),'declared_report_only');
    for(const key of ['at','start','end'])assert.ok(packet.params[key]===null||/^2026-11-11T[0-9:]{8}$/.test(packet.params[key]),'fixed_period');
  }else if(packet.method==='application.catalog'){
    exactKeys(packet.params,'entry');assert.ok(Number.isSafeInteger(packet.params.entry)&&packet.params.entry>0);
  }else if(['application.catalogPage','application.catalogFilter'].includes(packet.method)){
    const nav=lastApplicationState?.catalog?.navigation;
    exactKeys(packet.params,packet.method==='application.catalogPage'?'entry snapshot cursor':'entry snapshot query order');
    assert.equal(packet.params.entry,lastApplicationState?.catalog?.entry,'navigation_entry');
    assert.equal(packet.params.snapshot,nav?.snapshot,'navigation_snapshot');
    if(packet.method==='application.catalogPage')assert.ok([nav.previous,nav.next].filter(Boolean).includes(packet.params.cursor),'navigation_cursor');
    else{
      assert.ok(typeof packet.params.query==='string'&&packet.params.query.length<=128,'navigation_query');
      assert.ok(['code','description'].includes(packet.params.order),'navigation_order');
    }
  }else if(packet.method==='application.openRecord'){
    exactKeys(packet.params,'entry record request');assert.ok(Number.isSafeInteger(packet.params.entry)&&packet.params.entry>0);
    assert.match(packet.params.record,/^record-[1-9][0-9]{0,8}$/);assert.match(packet.params.request,/^open-[0-9a-f]{32}-[1-9][0-9]*$/);
  }else if(packet.method==='application.open'){
    exactKeys(packet.params,'entry request');assert.ok(Number.isSafeInteger(packet.params.entry)&&packet.params.entry>0);
    assert.match(packet.params.request,/^open-[0-9a-f]{32}-[1-9][0-9]*$/);
  }else if(packet.method==='application.snapshot'||packet.method==='application.close')exactKeys(packet.params,'');
  else{
    assert.equal(packet.method,'application.form');exactKeys(packet.params,'session request');
    assert.match(packet.params.session,/^form-[1-9][0-9]*$/);
    const nested=packet.params.request;exactKeys(nested,'jsonrpc id method params');
    assert.equal(nested.jsonrpc,'2.0');assert.ok(Number.isSafeInteger(nested.id)&&nested.id>0);
    if(nested.method==='form.hello'){
      exactKeys(nested.params,'protocol');assert.equal(nested.params.protocol,'yadinassi-form-ui/1');
    }else if(nested.method==='form.snapshot')exactKeys(nested.params,'');
    else{
      assert.equal(nested.method,'form.event');const event=nested.params;
      const keys={command:'event revision control',close:'event revision',change:'event revision control value',cell:'event revision control row column value',select:'event revision control row'};
      assert.ok(Object.hasOwn(keys,event.event),'wire_event');exactKeys(event,keys[event.event]);
      assert.ok(Number.isSafeInteger(event.revision)&&event.revision>=0,'wire_revision');
      if(event.event==='cell'||event.event==='select'){
        assert.ok(event.row===null&&event.event==='select'||Number.isSafeInteger(event.row)&&event.row>=1&&event.row<=4096,'opaque_row');
        if(event.event==='cell')assert.ok(['Quantity','Amount'].includes(event.column),'declared_column');
      }
      if(event.event==='change'||event.event==='cell'){
        exactKeys(event.value,event.value.type==='Date'?'type ticks':'type value');assert.ok(['String','Number','Boolean','Date'].includes(event.value.type),'scalar_only');
        if(event.value.type==='Date')assert.match(event.value.ticks,/^[0-9]{1,18}$/,'typed_date');
        else assert.ok(['string','boolean'].includes(typeof event.value.value),'scalar_value_only');
      }
      wireEvents.push({session:packet.params.session,event:event.event,control:event.control});
    }
  }
  if(packet.method==='application.reference')businessEvents.push('reference:'+packet.params.action.action);
  else if(packet.method==='application.report')businessEvents.push('report:'+packet.params.report);
  else if(['application.catalog','application.catalogPage','application.catalogFilter','application.open','application.openRecord','application.close'].includes(packet.method))
    businessEvents.push(packet.method.slice('application.'.length));
  else if(packet.method==='application.form'&&packet.params.request.method==='form.event'){
    const event=packet.params.request.params;businessEvents.push(event.event+':'+(event.control||''));
  }
  return packet;
}
async function auditResponse(response,packet){
  assert.equal(response.status(),200,'rpc_status');
  const body=await response.body();assert.ok(body.length<=262144,'reply_budget');
  const text=body.toString('utf8');const decoded=JSON.parse(text);
  exactKeys(decoded,'jsonrpc id result');assert.equal(decoded.jsonrpc,'2.0');
  assert.equal(decoded.id,packet.id,'audited_reply_id');
  lastApplicationState=decoded.result?.state;
  if(lastApplicationState?.report){
    const projection=lastApplicationState.report;
    exactKeys(projection,'report view at start end columns rows');
    assert.ok(projection.rows.length<=1000&&projection.rows.length*projection.columns.length<=25000,'report_cell_budget');
    for(const row of projection.rows)for(const cell of row){
      if(['Catalog','Document'].includes(cell.type))exactKeys(cell,'type text');
      else exactKeys(cell,cell.type==='Date'?'type ticks':'type value');
    }
  }
  if(lastApplicationState?.catalog){
    const {rows,navigation:n}=lastApplicationState.catalog;
    exactKeys(n,'snapshot page pages total query order previous next');
    assert.match(n.snapshot,/^records-[0-9a-f]{32}-[1-9][0-9]{0,9}$/);
    for(const k of ['page','pages','total'])assert.ok(Number.isSafeInteger(n[k]),'navigation_integer');
    assert.ok(n.total>=0&&n.total<=8192&&n.page>=1&&n.page<=n.pages,'navigation_bounds');
    assert.equal(n.pages,Math.max(1,Math.ceil(n.total/50)));
    assert.equal(rows.length,Math.min(50,Math.max(0,n.total-(n.page-1)*50)));
    for(const [key,absent] of [['previous',n.page===1],['next',n.page===n.pages]]){
      if(absent)assert.equal(n[key],null);else assert.match(n[key],/^records-page-[0-9a-f]{32}$/);
    }
  }
  assert.ok(!/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(text),'persistent_uuid_leak');
  for(const key of ['operation_id','database_id','record_id','expected_revision','expanded_requests','source_files'])
    assert.ok(!text.includes('"'+key+'"'),'private_host_envelope_leak');
  assert.ok(observedReplies.size<360,'audited_reply_budget');
  assert.ok(!observedReplies.has(packet.id),'audited_reply_duplicate');
  observedReplies.set(packet.id,{packet,actual:decoded,origin});
}
async function repeatClick(locator){await locator.evaluate(control=>{control.click();control.click();});}
async function scenario(name,fn){
 check();phase=name;const start=businessEvents.length,index=scenarioNames.indexOf(name);activeScenario=index;
 await fn();check();checkpoint('business_plan');assert.deepEqual(businessEvents.slice(start),businessPlan[index],'business_rpc_plan_changed');
 results.push({name,status:'PASS',businessRpc:businessEvents.length-start});
}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  checkpoint('screenshot_capability');assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  checkpoint('screenshot_storage');assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:Object.keys(sessionStorage)})),{local:0,session:['yadinassi.browser.resume/1']},'only_resume_storage');
  checkpoint('screenshot_cookies');assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  checkpoint('screenshot_capture');await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/configuration','examples/configuration-inventory-application','scripts/inventory_enum_behavior/runtime_source',
    'tests/inventory_application_fixture.py','tests/inventory_enum_application_fixture.py','tests/browser_ui',
    'tests/test_inventory_enum_application_profile.py','tests/test_inventory_enum_application_reports.py',
    'tests/test_inventory_enum_browser_qa_contract.py','docs/inventory-enum-browser-qa.md').split('\0').filter(Boolean);
  for(const required of ['yadinassi/inventory_application_reports.py','yadinassi/inventory_host_operations.py',
    'yadinassi/sqlite_launch.py','yadinassi/ui/database_launch.py','frontend/configuration/src/reports.mjs',
    'tests/inventory_enum_application_fixture.py',
    'examples/configuration-inventory-application/InventoryApplication.xml',
    'scripts/inventory_enum_behavior/runtime_source/Configuration.xml',
    'tests/browser_ui/inventory_enum_application_browser_qa.mjs'])
    assert.ok(names.includes(required),'source_manifest_missing');
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-inventory-enum-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'p-'));
  home=path.join(owned,'home');await mkdir(home);
  env=childEnvironment(process.env,home);env.PYTHONPATH=repo;
  phase='sandbox_launch';
  report.launch={stage:'children_before',returned:false,children:null,groupVerified:false,
    executableVerified:false,commandVerified:false,profileVerified:false};
  const childrenPath='/proc/'+process.pid+'/task/'+process.pid+'/children';
  const priorChildren=new Set(readFileSync(childrenPath,'utf8').trim().split(/\s+/).filter(Boolean));
  const previousTmp=process.env.TMPDIR;
  try{
    // Playwright creates its profile from the parent's temp directory, not launch env.
    process.env.TMPDIR=home;
    // Chromium 156 creates TMPDIR/org.chromium.Chromium.XXXXXX/SingletonSocket.
    // Linux sun_path includes the NUL byte: 108 or more path bytes abort launch.
    // Keep the same owned runner directory, with a short prefix and no fallback.
    report.launch.stage='socket_path_budget';
    assert.ok(Buffer.byteLength(path.join(home,'org.chromium.Chromium.XXXXXX','SingletonSocket'))<108,'browser_socket_path_too_long');
    report.launch.stage='chromium_launch';
    browser=await chromium.launch({channel:'chromium',headless:true,chromiumSandbox:true,env,timeout:remaining(20000)});
    report.launch.returned=true;
  }catch(error){
    // Preserve the launch failure even if subsequent ownership observation fails.
    report.launch.launchFailure=launchFailureCode(error);throw error;
  }finally{
    if(previousTmp===undefined)delete process.env.TMPDIR;else process.env.TMPDIR=previousTmp;
    // Capture the newly launched direct owned group even if CDP setup later fails.
    report.launch.stage='children_after';
    const children=readFileSync(childrenPath,'utf8').trim().split(/\s+/).filter(pid=>pid&&!priorChildren.has(pid));
    report.launch.children=Math.min(children.length,2);
    assert.ok(children.length<=1,'unexpected_launch_children');
    if(children.length){
      report.launch.stage='process_identity';
      browserGroup=processIdentity(Number(children[0]));report.launch.groupVerified=true;
      report.launch.stage='executable_identity';
      assert.equal(readlinkSync('/proc/'+browserGroup.pid+'/exe'),chromium.executablePath(),'browser_executable_mismatch');
      report.launch.executableVerified=true;report.launch.stage='browser_command';
      const bytes=readFileSync('/proc/'+browserGroup.pid+'/cmdline');assert.ok(bytes.length<=16384,'browser_command_budget');
      const args=commandLineArgs(bytes);sandboxCommand(args);
      report.launch.commandVerified=true;report.launch.stage='browser_profile';
      const profiles=args.filter(arg=>arg.startsWith('--user-data-dir='));
      assert.equal(profiles.length,1,'browser_profile_missing');
      const relative=path.relative(home,profiles[0].slice('--user-data-dir='.length));
      assert.ok(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative),'browser_profile_not_owned');
      report.launch.profileVerified=true;
    }
  }
  report.launch.stage='browser_ready';
  check();assert.ok(browserGroup,'browser_process_missing');report.browser=browser.version();
  report.launch.stage='cdp_session';
  const cdp=await bounded(browser.newBrowserCDPSession(),remaining(5000),'cdp_setup_timeout');
  report.launch.stage='cdp_process_identity';
  const info=await bounded(cdp.send('SystemInfo.getProcessInfo'),remaining(5000),'cdp_process_timeout');
  assert.equal(ownBrowserPid(info.processInfo),browserGroup.pid,'browser_pid_mismatch');
  report.launch.stage='cdp_detach';
  await bounded(cdp.detach(),remaining(5000),'cdp_detach_timeout');
  report.launch.stage='browser_context';
  context=await bounded(browser.newContext({viewport:{width:1100,height:850},locale:'en-US',timezoneId:'UTC',
    acceptDownloads:false,serviceWorkers:'block'}),remaining(10000),'context_timeout');
  context.setDefaultTimeout(10000);context.setDefaultNavigationTimeout(15000);
  report.launch.stage='sandbox_page';
  const probe=await context.newPage();await probe.goto('chrome://sandbox');
  report.launch.stage='sandbox_status';
  report.sandbox={requested:true,commandVerified:true,...sandboxStatus(await probe.locator('body').innerText())};
  report.launch.stage='sandbox_probe_close';
  await probe.close();report.launch.stage='verified';
  let attachmentRequests=0;
  await context.route('**/*',async route=>{
    const target=route.request().url();
    if(aborted||!applicationAllowedRequest(target))return route.abort();
    if(new URL(target).pathname==='/attachment'){
      try{
        assert.ok(++attachmentRequests<=96,'attachment_budget');
        const request=route.request(),body=request.postDataJSON();
        if(body.action==='attach'){exactKeys(body,'action instance');assert.match(body.instance,/^[0-9a-f]{32}$/);}
        else{exactKeys(body,'action generation pending');assert.ok(['status','heartbeat','detach','takeover'].includes(body.action));assert.ok(Number.isSafeInteger(body.generation)&&body.generation>=0);assert.equal(typeof body.pending,'boolean');}
        const response=await route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0});
        const bytes=await response.body();assert.ok(bytes.length<=8192,'attachment_reply_budget');
        const value=JSON.parse(bytes.toString('utf8'));
        if(body.action==='heartbeat'&&response.status()===409){
          exactKeys(value,'protocol error');assert.equal(value.protocol,'yadinassi-browser-attachment/1');
          assert.equal(value.error,'busy','unexpected_heartbeat_refusal');
          assert.ok(++report.heartbeatBusy<=attachmentRequests,'heartbeat_busy_budget');
          return await route.fulfill({response}); // Deliver exact refusal; never retry.
        }
        assert.equal(response.status(),200,'attachment_refused');
        exactKeys(value,'protocol attachment role generation leaseSeconds graceSeconds recovery closed'+(body.action==='attach'?' credential resume':''));
        assert.equal(value.protocol,'yadinassi-browser-attachment/1');
        assert.match(value.attachment,/^attachment-[1-9][0-9]*$/);
        assert.ok(['writer','observer'].includes(value.role));
        assert.ok(Number.isSafeInteger(value.generation)&&value.generation>=0);
        assert.equal(value.leaseSeconds,90);assert.equal(value.graceSeconds,30);
        assert.equal(typeof value.recovery,'boolean');assert.equal(typeof value.closed,'boolean');
        if(body.action==='attach'){
          for(const token of [value.credential,value.resume]){assert.match(token,/^[A-Za-z0-9_-]{43}$/);tokens.push(token);}
        }
        return await route.fulfill({response});
      }catch{if(host&&host.exitCode===null&&!aborted){wireFailure=true;abort();}return route.abort().catch(()=>{});}
    }
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=360){abort();return route.abort().catch(()=>{});}
      rpc++;
      try{
        checkRequest(route.request());
        const packet=route.request().postDataJSON();
        if(delayed&&packet.method==='application.openRecord'){
          const gate=delayed;delayed=null;
          const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
          await auditResponse(response,packet);gate.arrived();await bounded(gate.wait,remaining(10000),'late_reply_gate_timeout');
          return await route.fulfill({response});
        }
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        await auditResponse(response,packet);return await route.fulfill({response});
      }catch{wireFailure=true;abort();return route.abort().catch(()=>{});}
    }
    return route.continue();
  });
  page=await context.newPage();
  const writer=()=>page.waitForFunction(()=>{const b=document.querySelector('.browser-ownership');return b?.dataset.role==='writer'&&b.nextElementSibling?.inert===false;},null,{timeout:remaining(10000)});
  const picker=()=>page.getByRole('dialog');
  const reportPanel=()=>page.getByRole('region',{name:'Saved stock reports',exact:true});
  const choose=async(label,code,title)=>{
    assert.equal(await field(label).isEditable(),false,'reference_text_editable');
    let reply=replyFor(p=>p.method==='application.reference'&&p.params.action.action==='begin');
    await action('Choose '+label).click();await reply;await picker().waitFor();await idle();
    reply=replyFor(p=>p.method==='application.reference'&&p.params.action.action==='apply');
    await picker().getByRole('button',{name:'Choose '+code+' '+title,exact:true}).click();await reply;
    await picker().waitFor({state:'hidden'});await idle();await value(label,title);
  };
  const catalogEntry=async title=>{const reply=replyFor(p=>p.method==='application.catalog');await entries().getByRole('button',{name:title,exact:true}).click();await reply;await idle();};
  const newCard=async document=>{const reply=replyFor(p=>p.method==='application.open');await catalog().getByRole('button',{name:document?'New document':'New record',exact:true}).click();await reply;await idle();};
  const selectNumber=async number=>{await catalog().locator('tbody tr').filter({has:page.getByRole('cell',{name:number,exact:true})}).getByRole('checkbox').check();};
  const openNumber=async number=>{await selectNumber(number);const reply=replyFor(p=>p.method==='application.openRecord');await catalog().getByRole('button',{name:'Open selected',exact:true}).click();await reply;await idle();await value('Document number',number);};
  const prepare=async(kind,number,quantity,amount)=>{
    await catalogEntry(kind+' card');await newCard(true);await commitInput('Document number',number);
    await choose('Warehouse','W1','Main warehouse');
    const reply=formReply('command','AddLineButton');await action('Add line').click();await reply;await idle();
    await choose('Product, row 1','P1','Widget');await commitInput('Quantity, row 1',quantity);await commitInput('Amount, row 1',amount);
  };
  // Native datetime-local uses the shortest normalized HTML spelling: zero
  // seconds are omitted. The application restores exact whole seconds on wire.
  const fillPeriod=async(locator,value)=>{
    const html=value.endsWith(':00')?value.slice(0,-3):value;
    await locator.fill(html);assert.equal(await locator.inputValue(),html,'report_html_period');
  };
  const showReport=async(view,bounds={})=>{
    const expected={report:'Stock'+view,at:view==='Balance'?(bounds.at||'2026-11-11T12:00:01'):null,
      start:view==='Turnovers'?'2026-11-11T12:00:00':null,end:view==='Turnovers'?'2026-11-11T12:00:00':null};
    checkpoint('report_tab');await page.getByRole('navigation',{name:'Declared stock reports',exact:true}).getByRole('button',{name:'Stock '+view,exact:true}).click();
    const panel=reportPanel();checkpoint('report_fill');
    if(view==='Balance')await fillPeriod(panel.getByLabel('Balance before moment (exclusive)',{exact:true}),expected.at);
    if(view==='Turnovers'){
      await fillPeriod(panel.getByLabel('From moment (inclusive)',{exact:true}),expected.start);
      await fillPeriod(panel.getByLabel('Through moment (inclusive)',{exact:true}),expected.end);
    }
    const reply=replyFor(p=>p.method==='application.report');checkpoint('report_click');await panel.getByRole('button',{name:'Show saved stock',exact:true}).click();
    checkpoint('report_wait');const response=await reply;checkpoint('report_read');
    assert.deepEqual(response.request().postDataJSON().params,expected,'report_period_request');
    const result=deliveredReply(response).result;assert.equal(result.error,null,'report_refused');await idle();checkpoint('report_assert');
    assert.deepEqual(Object.fromEntries(['report','at','start','end'].map(k=>[k,result.state.report[k]])),expected,'report_period_result');
    assert.equal(result.state.report.report,'Stock'+view);assert.equal(result.state.report.view,view);
    assert.equal(await panel.locator('table tbody tr').count(),result.state.report.rows.length,'report_dom_rows');
    assert.equal(await panel.locator('table button,table input,table select').count(),0,'report_not_readonly');
    if(view==='Balance')await panel.getByText('Displayed balance before '+(bounds.at||'2026-11-11T12:00:01')+' (exclusive). Editing the controls does not change this result until Show saved stock.',{exact:true}).waitFor();
    if(view==='Turnovers')assert.equal(result.state.report.start,result.state.report.end,'inclusive_single_second');
    checkpoint('report_done');return result.state.report;
  };
  const reportNumber=(projection,name,expected)=>{
    assert.equal(projection.rows.length,1,'expected_one_stock_group');
    const index=projection.columns.findIndex(c=>c.name===name);assert.ok(index>=0,'resource_column_missing');
    assert.deepEqual(projection.rows[0][index],{type:'Number',value:expected},'resource_value');
  };
  await scenario(scenarioNames[0],async()=>{
    assert.deepEqual(inventoryFixture('create'),{created:true,core16Denied:true});
    await startHost();await page.goto(url);await writer();await idle();
    for(const [entry,code,title] of [['Products card','P1','Widget'],['Warehouses card','W1','Main warehouse']]){
      await catalogEntry(entry);await newCard(false);await commitInput('Code',code);await commitInput('Description',title);
      if(code==='P1')await choose('Unit','Piece','Piece');
      const reply=formReply('command','SaveButton');await action('Save record').click();await reply;await idle();
      await catalog().getByRole('cell',{name:title,exact:true}).waitFor();await closeForm();await countPanels(0);
    }
    const db=inventoryFixture('audit');
    assert.deepEqual(db.catalogs,[['Products','P1','Widget'],['Warehouses','W1','Main warehouse']],'audit_catalogs');
    assert.deepEqual(db.catalogEnums,['Piece']);assert.deepEqual(db.documents,[]);assert.deepEqual(db.movements,[]);
    await screenshot(screenshots[0]);
  });
  await scenario(scenarioNames[1],async()=>{
    await catalogEntry('Receipt card');await newCard(true);await commitInput('Document number','R1');
    await choose('Warehouse','W1','Main warehouse');await choose('State','Approved','Approved');
    const reply=formReply('command','AddLineButton');await action('Add line').click();await reply;await idle();
    await choose('Product, row 1','P1','Widget');await choose('Unit, row 1','Piece','Piece');
    await commitInput('Quantity, row 1','10.50');await commitInput('Amount, row 1','105');
    await command('Write document','WriteButton');
    const db=inventoryFixture('audit');assert.equal(db.documents.length,1);assert.equal(db.documents[0].posted,false);
    assert.equal(db.documents[0].state,'Approved');assert.equal(db.documents[0].unit,'Piece');
    assert.equal(db.documents[0].quantity,'10.5');assert.deepEqual(db.movements,[],'write_created_movements');
    await screenshot(screenshots[1]);
  });
  await scenario(scenarioNames[2],async()=>{
    await command('Post document','PostButton');const projection=await showReport('Movements');
    assert.equal(projection.rows.length,1);const column=name=>projection.columns.findIndex(c=>c.name===name);
    for(const [name,text] of [['Unit','Piece'],['State','Approved']]){
      assert.ok(column(name)>=0);assert.deepEqual(projection.rows[0][column(name)],{type:'String',value:text});
      await reportPanel().getByRole('cell',{name:text,exact:true}).waitFor();
    }
    const db=inventoryFixture('audit');assert.equal(db.documents[0].posted,true);assert.equal(db.movements.length,1);
    assert.equal(db.movements[0].unit,'Piece');assert.equal(db.movements[0].state,'Approved');
    await reportPanel().scrollIntoViewIfNeeded();await screenshot(screenshots[2]);await closeForm();await countPanels(0);
  });
  await scenario(scenarioNames[3],async()=>{
    const before=inventoryFixture('audit');await naturalStop();await page.close();page=await context.newPage();
    await startHost();await page.goto(url);await writer();await idle();await catalogEntry('Receipt card');await openNumber('R1');
    await value('State','Approved');await value('Unit, row 1','Piece');await value('Warehouse','Main warehouse');
    await value('Product, row 1','Widget');assert.deepEqual(inventoryFixture('audit'),before,'reopen_mutated_database');
    await command('Undo posting','UndoPostingButton');assert.deepEqual((await showReport('Movements')).rows,[]);
    const after=inventoryFixture('audit');assert.equal(after.documents[0].posted,false);assert.deepEqual(after.movements,[]);
    assert.equal(after.documents[0].state,'Approved');assert.equal(after.documents[0].unit,'Piece');
    await screenshot(screenshots[3]);await closeForm();await countPanels(0);await naturalStop();
    assert.deepEqual(inventoryFixture('audit'),after,'shutdown_mutated_database');
    report.acceptance={storedSourceLauncher:true,explicitFullForms16:true,core16Denied:true,
      catalogEnumChoice:true,headerEnumChoice:true,lineEnumChoice:true,writePostUndo:true,
      enumReportTextOnly:true,independentTypedAudit:true,naturalRestart:true,
      directBusinessSeeding:false,browserStateInjection:false,nativeParity:false};
  });
  await scenario(scenarioNames[4],async()=>{
    await page.close();page=await context.newPage();await startHost();await page.goto(url);await writer();await idle();
    await catalogEntry('Warehouses card');
    for(let index=0;index<50;index++){
      const suffix=String(index).padStart(4,'0');await newCard(false);
      await commitInput('Code','Z'+suffix);
      const reply=formReply('command','SaveButton');await action('Save record').click();await reply;await idle();
      await closeForm();await countPanels(0);
    }
    const nav=()=>lastApplicationState.catalog.navigation;
    const turn=async title=>{const reply=replyFor(p=>p.method==='application.catalogPage');await catalog().getByRole('button',{name:title,exact:true}).click();await reply;await idle();};
    const search=async(query,order)=>{
      await catalog().getByLabel('Search records',{exact:true}).fill(query);
      await catalog().getByLabel('Record order',{exact:true}).selectOption(order);
      const reply=replyFor(p=>p.method==='application.catalogFilter');await catalog().getByRole('button',{name:'Search records',exact:true}).click();await reply;await idle();
    };
    assert.equal(nav().total,51);assert.equal(nav().page,1);assert.equal(await catalog().locator('tbody tr').count(),50);
    await turn('Next records');assert.equal(nav().page,2);assert.equal(await catalog().locator('tbody tr').count(),1);
    await selectNumber('Z0049');const opened=replyFor(p=>p.method==='application.openRecord');
    await catalog().getByRole('button',{name:'Open selected',exact:true}).click();await opened;await idle();await value('Code','Z0049');
    await commitInput('Description','ZZ updated last warehouse');
    const saved=formReply('command','SaveButton');await action('Save record').click();await saved;await idle();
    assert.equal(nav().page,2);await catalog().getByRole('cell',{name:'ZZ updated last warehouse',exact:true}).waitFor();
    await closeForm();await countPanels(0);assert.equal(await catalog().getByRole('button',{name:'Open selected',exact:true}).isEnabled(),false);
    await turn('Previous records');assert.equal(nav().page,1);
    await search('Z0049','code');assert.equal(nav().total,1);assert.equal(nav().pages,1);
    await catalog().getByRole('cell',{name:'ZZ updated last warehouse',exact:true}).waitFor();
    await search('','description');assert.equal(nav().total,51);assert.equal(nav().order,'description');
    await turn('Next records');assert.equal(nav().page,2);
    const refreshed=replyFor(p=>p.method==='application.catalog');await catalog().getByRole('button',{name:'Refresh records',exact:true}).click();await refreshed;await idle();
    assert.equal(nav().page,2);assert.equal(nav().order,'description');assert.equal(nav().total,51);
    await catalog().getByRole('cell',{name:'ZZ updated last warehouse',exact:true}).waitFor();
    const audit=inventoryFixture('audit'),warehouses=audit.catalogs.filter(row=>row[0]==='Warehouses');
    assert.equal(warehouses.length,51);assert.ok(warehouses.some(row=>row[1]==='Z0049'&&row[2]==='ZZ updated last warehouse'));
    await screenshot(screenshots[4]);await naturalStop();
    assert.deepEqual(inventoryFixture('audit'),audit,'shutdown_mutated_database');
    report.acceptance.recordPaging=true;report.acceptance.recordSearchSort=true;report.acceptance.saveRefreshPage=true;
    report.acceptance.rowsCreatedThroughUI=51;
  });
  await scenario(scenarioNames[5],async()=>{
    // Reuse the 51 warehouses created through UI, never seed business rows.
    await page.close();page=await context.newPage();await startHost();await page.goto(url);await writer();await idle();
    await catalogEntry('Receipt card');await openNumber('R1');
    let reply=replyFor(p=>p.method==='application.reference'&&p.params.action.action==='begin');
    await action('Choose Warehouse').click();await reply;await picker().waitFor();await idle();
    const nav=()=>lastApplicationState.choice.navigation;
    assert.equal(nav().total,51);assert.equal(nav().page,1);assert.equal(lastApplicationState.choice.rows.length,32);
    reply=replyFor(p=>p.method==='application.reference'&&p.params.action.action==='page');
    await picker().getByRole('button',{name:'Next choices',exact:true}).click();await reply;await idle();
    assert.equal(nav().page,2);assert.equal(lastApplicationState.choice.rows.length,19);
    await picker().getByRole('button',{name:'Choose Z0049 ZZ updated last warehouse',exact:true}).waitFor();
    await picker().getByLabel('Reference search',{exact:true}).fill('ZZ updated');
    reply=replyFor(p=>p.method==='application.reference'&&p.params.action.action==='search');
    await picker().getByRole('button',{name:'Search references',exact:true}).click();await reply;await idle();
    assert.equal(nav().total,1);assert.equal(nav().page,1);assert.equal(nav().query,'ZZ updated');
    reply=replyFor(p=>p.method==='application.reference'&&p.params.action.action==='apply');
    await picker().getByRole('button',{name:'Choose Z0049 ZZ updated last warehouse',exact:true}).click();await reply;
    await picker().waitFor({state:'hidden'});await idle();await value('Warehouse','ZZ updated last warehouse');
    await command('Write document','WriteButton');
    const audit=inventoryFixture('audit-picked');assert.equal(audit.documents[0].warehouse,'Z0049');
    await closeForm();await countPanels(0);await openNumber('R1');await value('Warehouse','ZZ updated last warehouse');
    assert.deepEqual(inventoryFixture('audit-picked'),audit,'picker_reopen_mutated_database');
    await screenshot(screenshots[5]);await closeForm();await countPanels(0);await naturalStop();
    assert.deepEqual(inventoryFixture('audit-picked'),audit,'picker_shutdown_mutated_database');
    report.acceptance.referencePaging=true;report.acceptance.referenceSearch=true;report.acceptance.referenceSavedReopen=true;
  });
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','source_changed');
  assert.deepEqual(await sourceBinding(),report.binding,'source_binding_changed');
  assert.deepEqual(results.map(row=>row.name),scenarioNames,'incomplete_scenarios');
  assert.equal(wireFailure,false,'wire_contract_failed');
  report.status='PASS';report.rpcRequests=rpc;
}
// Hard work limit plus a separate 20-second cleanup reserve. No security changes.
const deadline=setTimeout(abort,Math.max(0,workDeadline-Date.now()));
const totalTimer=setTimeout(()=>{abort();process.exit(1);},Math.max(0,totalDeadline-Date.now()));
try{await main();check();}
catch(error){
  failed=true;report.status='FAIL';
  // Fixed, bounded flags/counts only. Never record DOM text, field contents,
  // response bodies, exception strings, database identifiers or capability URLs.
  report.rpcRequests=rpc;
  if(phase==='sandbox_launch'&&report.launch)report.launch.failure=launchFailureCode(error);
  report.failureClass=['AssertionError','TimeoutError','TypeError','SyntaxError','Error'].includes(error?.name)?error.name:'other';
  const observerMessage=typeof error?.message==='string'?error.message:'';
  report.observerFailure=/No resource with given identifier|No data found for resource/.test(observerMessage)?'response_body_unavailable':
    /Target page, context or browser has been closed/.test(observerMessage)?'browser_closed':
    /strict mode violation/.test(observerMessage)?'ambiguous_locator':
    /Malformed value/.test(observerMessage)?'malformed_input':
    /Input of type .* cannot be filled|Element is not an <input>/.test(observerMessage)?'unsupported_input':'unclassified';
  report.failure={phase,scenario:activeScenario,reason:wireFailure?'wire_contract':aborted?'deadline_or_rpc_budget':phase==='sandbox_launch'&&
    /Operation not permitted|No usable sandbox|Failed to move to new namespace/i.test(String(error?.message))?'sandbox_start_denied':diagnosticReason(error)};
}
finally{
  aborted=true;clearTimeout(deadline);
  try{if(browser)await bounded(browser.close(),cleanupRemaining(8000),'browser_close_timeout');}
  catch{cleanupFailure('browser_close_failed');}
  try{signalGroup(browserGroup,'SIGKILL');await groupGone(browserGroup);}
  catch{cleanupFailure('browser_cleanup_unverified');}
  try{await stopHost();}catch{cleanupFailure('host_cleanup_unverified');}
  try{
    if(owned){
      await bounded(rm(owned,{recursive:true,force:true}),cleanupRemaining(2000),'owned_remove_timeout');
      try{await lstat(owned);throw Error('owned_directory_remains');}catch(error){if(error.code!=='ENOENT')throw error;}
    }
  }catch{cleanupFailure('owned_directory_cleanup_unverified');}
  try{
    if(outputCreated){
      const images={};
      for(const name of screenshots){
        try{
          const file=path.join(output,name),stat=await lstat(file);
          assert.ok(stat.isFile()&&!stat.isSymbolicLink()&&stat.size>0&&stat.size<=4*1024*1024,'screenshot_budget');
          const bytes=await readFile(file);assert.equal(bytes.length,stat.size);
          assert.equal(bytes.subarray(0,8).toString('hex'),'89504e470d0a1a0a','screenshot_not_png');
          images[name]={bytes:bytes.length,sha256:sha256(bytes)};
        }catch{await rm(path.join(output,name),{force:true});report.status='FAIL';report.artifacts='missing_or_invalid_screenshot';}
      }
      report.elapsedMs=Date.now()-startedAt;
      const raw=JSON.stringify(report,null,2)+'\n';
      assert.ok(Buffer.byteLength(raw)<=65536,'report_budget');
      assert.ok(!tokens.some(token=>raw.includes(token)),'capability_leak');
      await writeFile(path.join(output,'result.json'),raw,{flag:'wx'});
      await writeFile(path.join(output,'manifest.json'),JSON.stringify({schema:1,source:report.sourceCommit,
        tree:report.binding?.tree,resultSha256:sha256(raw),images},null,2)+'\n',{flag:'wx'});
      assert.ok((await readdir(output)).every(name=>artifacts.includes(name)),'unexpected_artifact');
    }
  }catch{failed=true;report.status='FAIL';report.artifacts='artifact_validation_failed';}
  clearTimeout(totalTimer);
}
// Fixed verdicts only: no raw exception, URL, request, database or profile path.
console.log(JSON.stringify({status:report.status,completed:results.length,total:scenarioNames.length,source:report.sourceCommit,failure:report.failure,cleanup:report.cleanup}));
if(failed||report.status!=='PASS')process.exitCode=1;
