/** Four detached stock statement flows; typed setup is not a browser effect. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile,rm,lstat,readdir} from 'node:fs/promises';
import {readFileSync,readlinkSync,lstatSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {allowedRequest,childEnvironment,ownBrowserPid,
  commandLineArgs,sandboxCommand,sandboxStatus,sha256,launchURL} from './support.mjs';

const startedAt=Date.now();
const workDeadline=startedAt+220000;
const totalDeadline=startedAt+240000;
const rpcFetchMs=35000,rpcReplyMs=50000; // Existing transport and observer budgets; global deadline unchanged.
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
const screenshots=['statement-pages.png','statement-filters.png','statement-fences.png','statement-reopened.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['periods_pages_exact_saved_totals','typed_filters_closed_choices',
 'raw_draft_retirement_delayed_page','natural_restart_new_setup_readonly_audit'];
// Only hello/snapshot reads are excluded. These fixed lists include every
// business request, including read-only setup/choice/page commands.
const businessPlan=[
 ['setup:open','report:Day','page','page','report:Month','page','report:None','page'],
 ['setup:begin','setup:filter','setup:apply','report:None',
  'setup:begin','setup:apply','report:None','setup:begin','setup:cancel','report:None',
  'setup:empty','report:None','setup:clear','report:None','setup:empty','report:None',
  'setup:clear','report:None','setup:begin','setup:filter','setup:cancel'],
 ['catalog','openRecord','setup:open','report:None','page','setup:begin','setup:filter','setup:cancel',
  'report:None','close:','setup:open','report:None'],
 ['close','setup:open','report:None','page','close']
];
const businessEvents=[];
// Closed diagnostic vocabulary only. Values from assertions, DOM, callbacks,
// storage, environment and subprocess stderr never become artifact strings.
const diagnosticPhases=['fixture_create','fixture_audit','setup_click','setup_reply','report_tab','report_fill',
 'report_click','report_wait','report_read','report_assert','page_click','page_wait','page_assert',
 'draft_focus','restore_draft','close_form','retired_choice','retired_page','delayed_page','restart','audit_compare',
 'screenshot_capability','screenshot_storage','screenshot_cookies','screenshot_capture','business_plan'];
const diagnosticReasons=['business_rpc_plan_changed','owned_fixture_failed','owned_fixture_timeout',
 'audited_reply_missing','audited_reply_request','audited_reply_origin','audited_reply_budget','audited_reply_duplicate','audited_reply_id',
 'report_refused','report_period_request','report_period_result','report_html_period','report_dom_rows','report_not_readonly',
 'report_typed_totals','report_page_identity','report_page_order','report_saved_labels','typed_seed_audit',
 'too_many_partial','exact_choice_mismatch','cancel_changed_selection','explicit_empty_mismatch','excluded_filter_rows',
 'draft_changed','unexpected_form_change','retired_dom_dispatched','duplicate_page_rpc','busy_not_fenced','late_owner_changed',
 'close_refused','unexpected_form_write','readonly_audit_changed','restarted_ticket_reused','restarted_page_reused','source_binding_changed',
 'capability_not_removed','only_resume_storage','browser_cookies_not_empty',
 'report_accessible_region','report_readable_headers','report_readable_cells'];
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
const panels=()=>page.locator('.configuration-form-panels > section');
const active=()=>page.locator('.configuration-form-panels > section:not([hidden])');
const field=name=>active().getByLabel(name,{exact:true});
const action=name=>active().getByRole('button',{name,exact:true});
const catalog=()=>page.locator('.configuration-catalog');
// Setup alone writes: one typed catalog transaction and one trusted root Post.
// The audit never calls report services, handlers, Query or write APIs. All
// catalog/document/movement audit rows share one existing read lease.
const fixtureCode=String.raw`
import json,sys
from pathlib import Path
from contextlib import closing
from datetime import datetime
from decimal import Decimal, localcontext
from hashlib import sha256
from uuid import uuid4
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.configuration_inventory_application import import_inventory_application, PROFILE, validated_core
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_backend import CatalogDraft, CatalogKey, CatalogSelection, BackendError, TabularSectionRows, TabularRow
from yadinassi.document_backend import DocumentDraft, DocumentKey, DocumentSelection
from yadinassi.inventory_host_operations import InventoryRootOperations
from yadinassi.sqlite_documents import DocumentView
from yadinassi.sqlite_transactions import _accumulation_port
from yadinassi.accumulation_movements import AccumulationDirection
from yadinassi.dates import _date_from_datetime
root=Path(sys.argv[2]); source=Path(sys.argv[3]); database=root/'stock.sqlite'
try:
 files=read_configuration_directory(source)
 config=import_inventory_application(files,inventory_runtime=PROFILE)
 if sys.argv[1]=='create':
  assert not database.exists()
  with closing(SQLiteDBContext.create_inventory_application(database,config)) as context:
   backend=context.backend; schemas={s.name:s for s in config.catalogs}; cards={}
   with closing(backend.begin_write(uuid4())) as owner:
    for name,rows in [('Products',[(f'P{i:03}',f'Product {i:03}') for i in range(1,53)]),
                      ('Warehouses',[('W1','Main warehouse'),('W2','Unused warehouse')])]:
     for code,label in rows:
      key=CatalogKey(backend.database_id,schemas[name].identity,uuid4()); cards[name,code]=key
      owner.create(CatalogDraft(key,code,label,False,(),()))
    assert len(owner.commit())==54
   schema=next(s for s in config.documents if s.name=='Receipt')
   draft=DocumentDraft(DocumentKey(backend.database_id,schema.identity,uuid4()),'R1',datetime(2026,11,11,12),False,
     (cards['Warehouses','W1'],),(TabularSectionRows(schema.tabular_sections[0].identity,
       tuple(TabularRow(uuid4(),(cards['Products',f'P{i:03}'],Decimal(i),Decimal(i*10))) for i in range(1,53))),),False)
   with closing(InventoryRootOperations(context,config)) as operations:
    receipt=operations.execute(uuid4(),draft,None,form='Document.Receipt.Form.Card',command='Post')
    assert receipt.state=='committed' and receipt.accepted
  with closing(SQLiteCatalogBackend.create_inventory(root/'core-only.sqlite',validated_core(config))) as core:
   try: core.launch_snapshot()
   except BackendError as failure: assert failure.code=='unsupported'
   else: raise AssertionError('core15_ui_grant')
  result={'created':True,'core15Denied':True,'setupCatalogs':54,'setupDocuments':1,'setupMovements':52}
 elif sys.argv[1]=='audit':
  before=sha256(database.read_bytes()).digest()
  with closing(SQLiteCatalogBackend(database,read_only=True)) as backend:
   snap=backend.launch_snapshot()
   assert snap.route=='inventory' and snap.profile==PROFILE
   assert {f.path:f.content for f in snap.files}==files
   with closing(backend.begin_read()) as owner:
    fingerprint=[str(owner.database_id),str(owner.configuration_generation),snap.profile,snap.source_digest]
    catalogs={s.name:s for s in owner.catalogs()}; cards={}; labels={}
    assert set(catalogs)=={'Products','Warehouses'}
    for name in sorted(catalogs):
     fingerprint.append(repr(catalogs[name]))
     rows=owner.select_catalog(catalogs[name].identity,CatalogSelection(limit=64))
     assert len(rows)==(52 if name=='Products' else 2)
     for card in sorted(rows,key=lambda c:c.code):
      assert type(card.key) is CatalogKey and not card.deletion_mark
      assert card.key.database_id==owner.database_id and card.key.catalog_id==catalogs[name].identity
      cards[name,card.code]=card;labels[card.key]=card.code;fingerprint.append(repr(card))
    reader=DocumentView(owner);documents=[];recorder=None
    for schema in reader.documents():
     fingerprint.append(repr(schema))
     for card in reader.select_documents(schema.identity,DocumentSelection(limit=2)):
      assert schema.name=='Receipt' and card.number=='R1' and card.posted and not card.deletion_mark
      assert type(card.key) is DocumentKey and type(card.date) is datetime and card.date==datetime(2026,11,11,12)
      assert card.values==(cards['Warehouses','W1'].key,) and len(card.tabular_sections)==1
      rows=card.tabular_sections[0].rows;assert len(rows)==52
      for i,row in enumerate(rows,1):
       assert row.values==(cards['Products',f'P{i:03}'].key,Decimal(i),Decimal(i*10))
       assert all(type(v) is Decimal for v in row.values[1:])
      recorder=card.key;documents.append(card);fingerprint.append(repr(card))
    assert len(documents)==1
    register,=config.registers;fingerprint.append(repr(register));movements=[];quantity=Decimal(0);amount=Decimal(0)
    for key,partition in _accumulation_port(owner).scan(register.identity):
     assert type(key) is DocumentKey and key==recorder and len(partition.rows)==52
     fingerprint.extend([repr(key),repr(partition)])
     for row in partition.rows:
      assert row.active is True and row.period==datetime(2026,11,11,12) and row.direction is AccumulationDirection.RECEIPT
      dims=dict(zip((f.name for f in register.dimensions),row.dimensions));resources=dict(zip((f.name for f in register.resources),row.resources))
      assert dims['Warehouse']==cards['Warehouses','W1'].key
      code=labels[dims['Product']];i=int(code[1:]);assert 1<=i<=52
      assert resources=={'Quantity':Decimal(i),'Amount':Decimal(i*10)}
      assert all(type(v) is Decimal for v in resources.values())
      quantity+=resources['Quantity'];amount+=resources['Amount'];movements.append(code)
    assert sorted(movements)==[f'P{i:03}' for i in range(1,53)]
    assert quantity==Decimal(1378) and amount==Decimal(13780)
    result={'catalogs':54,'documents':1,'movements':52,'quantity':str(quantity),'amount':str(amount),
     'fingerprint':sha256('\n'.join(fingerprint).encode()).hexdigest(),'sourceDigest':snap.source_digest,
     'databaseSha256':before.hex(),
     'dayTicks':str(_date_from_datetime(datetime(2026,11,11)).ticks),
     'monthTicks':str(_date_from_datetime(datetime(2026,11,1)).ticks)}
  assert sha256(database.read_bytes()).digest()==before
 else: raise AssertionError('fixture_mode')
 print(json.dumps(result))
except Exception:
 print('{"error":"owned_statement_fixture_failed"}',file=sys.stderr);sys.exit(1)
`;
function inventoryFixture(operation){
  assert.ok(['create','audit'].includes(operation),'fixture_mode');
  checkpoint(operation==='create'?'fixture_create':'fixture_audit');
  let raw;
  try{raw=execFileSync(python,['-c',fixtureCode,operation,owned,path.join(repo,'examples/configuration-inventory-application')],
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
async function closeForm(){const reply=formReply('close');await action('Close form').click();const result=deliveredReply(await reply).result;await idle();return result;}
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
const wireEvents=[];
let wireFailure=false;
// Retain only the first failed wire check. Concurrent attachment activity must
// not overwrite the original RPC failure, and no arbitrary packet is exported.
const wireStages=['request','fetch','status','body','json','projection','privacy','observer','delivery'];
const wireMethods=['attachment','application.hello','application.snapshot','application.catalog',
 'application.open','application.openRecord','application.form','application.close',
 'application.reportSetup','application.report','application.reportPage'];
const wireReasons=['wire_keys','writer_credential','writer_attachment','writer_generation','wire_budget',
 'persistent_uuid_in_request','unissued_setup','unissued_chooser','unissued_row','unissued_snapshot','unissued_page',
 'fixed_exact_code','fixed_period','wire_event','wire_revision','opaque_row','declared_column','scalar_only',
 'typed_date','scalar_value_only','rpc_status','reply_budget','audited_reply_id','too_many_partial',
 'page_budget','report_cell_budget','persistent_uuid_leak','private_host_envelope_leak',
 'audited_reply_budget','audited_reply_duplicate','attachment_budget','attachment_reply_budget',
 'unexpected_heartbeat_refusal','heartbeat_busy_budget','attachment_refused','late_reply_gate_timeout'];
function wireDiagnostic(trace,error){
  wireFailure=true;
  if(report.wire)return; // Preserve the first cause before fail-closed cleanup.
  const message=typeof error?.message==='string'?error.message:'';
  const reason=wireReasons.find(code=>message===code||message.startsWith(code+'\n'))||
    (error?.name==='SyntaxError'?'invalid_json':error?.name==='TimeoutError'?'wire_timeout':'wire_step_failed');
  const byteCount=(value,cap)=>Number.isSafeInteger(value)&&value>=0?Math.min(value,cap+1):null;
  report.wire={stage:wireStages.includes(trace.stage)?trace.stage:'other',
    method:wireMethods.includes(trace.method)?trace.method:'other',
    status:[200,400,403,409,500,503].includes(trace.status)?trace.status:trace.status===null?null:'other',
    requestBytes:byteCount(trace.requestBytes,65536),replyBytes:byteCount(trace.replyBytes,262144),reason};
}
const exactKeys=(value,names)=>assert.deepEqual(Object.keys(value).sort(),names.split(' ').filter(Boolean).sort(),'wire_keys');
function checkRequest(request,trace){
  const headers=request.headers();
  assert.match(headers['x-yadinassi-session']||'',/^[A-Za-z0-9_-]{43}$/,'writer_credential');
  assert.match(headers['x-yadinassi-attachment']||'',/^attachment-[1-9][0-9]*$/,'writer_attachment');
  assert.match(headers['x-yadinassi-generation']||'',/^[0-9]{1,16}$/,'writer_generation');
  const raw=request.postData();trace.requestBytes=typeof raw==='string'?Buffer.byteLength(raw):null;
  assert.ok(raw&&Buffer.byteLength(raw)<=65536,'wire_budget');
  assert.ok(!/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/i.test(raw),'persistent_uuid_in_request');
  const packet=JSON.parse(raw);trace.method=wireMethods.includes(packet?.method)?packet.method:'other';
  exactKeys(packet,'jsonrpc id method params');
  assert.equal(packet.jsonrpc,'2.0');assert.ok(Number.isSafeInteger(packet.id)&&packet.id>0);
  if(packet.method==='application.hello'){
    exactKeys(packet.params,'protocol dialogCapability inputCapability');assert.equal(packet.params.inputCapability,'yadinassi-owned-input/1');assert.equal(packet.params.protocol,'yadinassi-configuration-app/3');
    assert.equal(packet.params.dialogCapability,'yadinassi-owned-dialog/1');
  }else if(packet.method==='application.reportSetup'){
    const p=packet.params,a=p.action;
    const fields=a==='open'?'report action':'report ticket action'+(['begin','clear','empty'].includes(a)?' filter':a==='filter'?' choice code':a==='apply'?' choice value':' choice');
    exactKeys(p,fields);assert.equal(p.report,'StockStatement');
    assert.ok(['open','begin','filter','apply','cancel','clear','empty'].includes(a));
    if(a!=='open')assert.equal(p.ticket,lastApplicationState?.reportSetup?.ticket,'unissued_setup');
    if(p.filter)assert.ok(['Product','Warehouse'].includes(p.filter));
    if(p.choice)assert.equal(p.choice,lastApplicationState?.reportSetup?.choice?.ticket,'unissued_chooser');
    if(a==='apply')assert.ok(lastApplicationState.reportSetup.choice.rows.some(r=>r.choice===p.value),'unissued_row');
    if(a==='filter')assert.ok(['P001','P002','ABSENT'].includes(p.code),'fixed_exact_code');
  }else if(packet.method==='application.reportPage'){
    exactKeys(packet.params,'snapshot cursor');const p=lastApplicationState?.report?.page;
    assert.equal(packet.params.snapshot,p?.snapshot,'unissued_snapshot');
    assert.ok([p?.cursor,p?.next,p?.previous].includes(packet.params.cursor)&&packet.params.cursor!==null,'unissued_page');
  }else if(packet.method==='application.report'){
    exactKeys(packet.params,'report at start end periodicity setup');assert.equal(packet.params.report,'StockStatement');
    assert.equal(packet.params.at,null);assert.ok(['None','Day','Month'].includes(packet.params.periodicity));
    assert.equal(packet.params.setup,lastApplicationState?.reportSetup?.ticket,'unissued_setup');
    for(const key of ['start','end'])assert.ok(/^2026-11-(01|11|12)T[0-9:]{8}$/.test(packet.params[key]),'fixed_period');
  }else if(packet.method==='application.catalog'){
    exactKeys(packet.params,'entry');assert.ok(Number.isSafeInteger(packet.params.entry)&&packet.params.entry>0);
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
  if(packet.method==='application.reportSetup')businessEvents.push('setup:'+packet.params.action);
  else if(packet.method==='application.reportPage')businessEvents.push('page');
  else if(packet.method==='application.report')businessEvents.push('report:'+packet.params.periodicity);
  else if(['application.catalog','application.open','application.openRecord','application.close'].includes(packet.method))
    businessEvents.push(packet.method.slice('application.'.length));
  else if(packet.method==='application.form'&&packet.params.request.method==='form.event'){
    const event=packet.params.request.params;businessEvents.push(event.event+':'+(event.control||''));
  }
  return packet;
}
async function auditResponse(response,packet,trace){
  trace.stage='status';trace.status=response.status();assert.equal(response.status(),200,'rpc_status');
  trace.stage='body';const body=await response.body();trace.replyBytes=body.length;
  assert.ok(body.length<=262144,'reply_budget');
  trace.stage='json';const text=body.toString('utf8');const decoded=JSON.parse(text);
  trace.stage='projection';
  exactKeys(decoded,'jsonrpc id result');assert.equal(decoded.jsonrpc,'2.0');
  assert.equal(decoded.id,packet.id,'audited_reply_id');
  lastApplicationState=decoded.result?.state;
  if(lastApplicationState?.reportSetup){
    const setup=lastApplicationState.reportSetup;exactKeys(setup,'report ticket filters choice');
    assert.equal(setup.report,'StockStatement');assert.match(setup.ticket,/^setup-[0-9a-f]{32}-[1-9][0-9]*$/);
    for(const f of setup.filters)exactKeys(f,'id mode text');
    if(setup.choice){const choice=setup.choice;exactKeys(choice,'filter ticket code rows error');
      assert.ok(choice.rows.length<=32);assert.ok(choice.error===null||choice.error==='too_many_matches'&&choice.rows.length===0,'too_many_partial');
      for(const row of choice.rows)exactKeys(row,'choice code description');}
  }
  if(lastApplicationState?.report){
    const projection=lastApplicationState.report;
    exactKeys(projection,'report view at start end columns rows periodicity setup filters page');
    assert.ok(projection.rows.length<=50&&projection.page.total<=1000,'page_budget');
    assert.ok(projection.rows.length<=1000&&projection.rows.length*projection.columns.length<=25000,'report_cell_budget');
    for(const row of projection.rows)for(const cell of row){
      if(['Catalog','Document'].includes(cell.type))exactKeys(cell,'type text');
      else exactKeys(cell,cell.type==='Date'?'type ticks':'type value');
    }
  }
  trace.stage='privacy';
  assert.ok(!/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(text),'persistent_uuid_leak');
  for(const key of ['operation_id','database_id','record_id','expected_revision','expanded_requests','source_files'])
    assert.ok(!text.includes('"'+key+'"'),'private_host_envelope_leak');
  trace.stage='observer';assert.ok(observedReplies.size<180,'audited_reply_budget');
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
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/configuration','examples/configuration-inventory-application','tests/browser_ui',
    'tests/test_configuration_inventory_app.py','tests/test_inventory_application_reports.py','tests/test_configuration_inventory_reports_ui.py',
    'tests/test_inventory_application_statements.py','tests/test_inventory_report_controls.py','tests/test_inventory_statement_controller.py','tests/test_inventory_report_pages.py',
    'docs/inventory-statement-browser-qa.md','tests/test_inventory_statement_browser_qa_contract.py','.github/workflows/inventory-statement-browser-qa.yml').split('\0').filter(Boolean);
  for(const required of ['yadinassi/inventory_application_reports.py','yadinassi/inventory_host_operations.py',
    'yadinassi/sqlite_launch.py','yadinassi/ui/database_launch.py','frontend/configuration/src/reports.mjs',
    'examples/configuration-inventory-application/InventoryApplication.xml',
    'tests/browser_ui/inventory_statement_browser_qa.mjs','.github/workflows/inventory-statement-browser-qa.yml',
    'yadinassi/ui/inventory_report_controls.py','yadinassi/ui/report_pages.py','yadinassi/accumulation_periods.py'])
    assert.ok(names.includes(required),'source_manifest_missing');
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-inventory-statement-browser-artifacts');
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
  assert.deepEqual(inventoryFixture('create'),{created:true,core15Denied:true,setupCatalogs:54,setupDocuments:1,setupMovements:52},'typed_seed_audit');
  const initialAudit=inventoryFixture('audit');assert.equal(initialAudit.quantity,'1378.000','typed_seed_audit');assert.equal(initialAudit.amount,'13780.00','typed_seed_audit');
  report.fixture={catalogs:54,documents:1,movements:52,beforeBrowser:true,typedOnly:true};
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
      const trace={stage:'request',method:'attachment',status:null,requestBytes:null,replyBytes:null};
      try{
        assert.ok(++attachmentRequests<=96,'attachment_budget');
        const request=route.request();trace.requestBytes=Buffer.byteLength(request.postData()||'');
        const body=request.postDataJSON();
        if(body.action==='attach'){exactKeys(body,'action instance');assert.match(body.instance,/^[0-9a-f]{32}$/);}
        else{exactKeys(body,'action generation pending');assert.ok(['status','heartbeat','detach','takeover'].includes(body.action));assert.ok(Number.isSafeInteger(body.generation)&&body.generation>=0);assert.equal(typeof body.pending,'boolean');}
        trace.stage='fetch';const response=await route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0});
        trace.status=response.status();trace.stage='body';const bytes=await response.body();trace.replyBytes=bytes.length;
        assert.ok(bytes.length<=8192,'attachment_reply_budget');
        trace.stage='json';const value=JSON.parse(bytes.toString('utf8'));trace.stage='projection';
        if(body.action==='heartbeat'&&response.status()===409){
          exactKeys(value,'protocol error');assert.equal(value.protocol,'yadinassi-browser-attachment/1');
          assert.equal(value.error,'busy','unexpected_heartbeat_refusal');
          assert.ok(++report.heartbeatBusy<=attachmentRequests,'heartbeat_busy_budget');
          trace.stage='delivery';return await route.fulfill({response}); // Deliver exact refusal; never retry.
        }
        trace.stage='status';assert.equal(response.status(),200,'attachment_refused');trace.stage='projection';
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
        trace.stage='delivery';return await route.fulfill({response});
      }catch(error){if(host&&host.exitCode===null&&!aborted){wireDiagnostic(trace,error);abort();}return route.abort().catch(()=>{});}
    }
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=180){abort();return route.abort().catch(()=>{});}
      rpc++;
      const trace={stage:'request',method:'other',status:null,requestBytes:null,replyBytes:null};
      try{
        const packet=checkRequest(route.request(),trace);
        trace.stage='fetch';
        if(delayed&&packet.method==='application.reportPage'){
          const gate=delayed;delayed=null;
          const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
          await auditResponse(response,packet,trace);gate.arrived();await bounded(gate.wait,remaining(10000),'late_reply_gate_timeout');
          trace.stage='delivery';return await route.fulfill({response});
        }
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        await auditResponse(response,packet,trace);trace.stage='delivery';return await route.fulfill({response});
      }catch(error){wireDiagnostic(trace,error);abort();return route.abort().catch(()=>{});}
    }
    return route.continue();
  });
  page=await context.newPage();
  const writer=()=>page.waitForFunction(()=>{const b=document.querySelector('.browser-ownership');return b?.dataset.role==='writer'&&b.nextElementSibling?.inert===false;},null,{timeout:remaining(10000)});
  const reportPanel=()=>page.getByRole('region',{name:'Saved stock reports',exact:true});
  const reportButton=name=>reportPanel().getByRole('button',{name,exact:true});
  const choicePanel=()=>page.getByRole('region',{name:'Statement filter choice',exact:true});
  const flushPaint=async()=>{await idle();await bounded(page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))),remaining(5000),'paint_timeout');};
  const reportIdle=()=>page.waitForFunction(()=>{const n=document.querySelector('[aria-label="Declared stock reports"] button');return n&&!n.disabled;},null,{timeout:remaining(10000)});
  const setupAction=async(action,locator)=>{
    checkpoint('setup_click');const reply=replyFor(p=>p.method==='application.reportSetup'&&p.params.action===action);
    await locator.click();checkpoint('setup_reply');const actual=deliveredReply(await reply).result;
    assert.equal(actual.error,null,'report_refused');await reportIdle();return actual.state.reportSetup;
  };
  const prepareStatement=()=>setupAction('open',reportButton('Prepare statement'));
  const begin=dimension=>setupAction('begin',reportButton('Choose '+dimension));
  const search=async code=>{
    await choicePanel().getByLabel('Statement exact code',{exact:true}).fill(code);
    return setupAction('filter',reportButton('Find statement code'));
  };
  const apply=label=>setupAction('apply',choicePanel().getByRole('button',{name:label,exact:true}));
  const cancel=()=>setupAction('cancel',reportButton('Cancel statement choice'));
  const filterAction=(action,dimension)=>setupAction(action,reportButton((action==='empty'?'Empty ':'All ')+dimension));
  const fillPeriod=async(locator,value)=>{
    const html=value.endsWith(':00')?value.slice(0,-3):value;
    await locator.fill(html);assert.equal(await locator.inputValue(),html,'report_html_period');
  };
  const auditPresentation=async(projected)=>{
    const panel=reportPanel(),region=panel.locator('.configuration-report-table-scroll');
    const declared=lastApplicationState.reports.find(value=>value.id===projected.report);
    assert.equal(await region.getAttribute('role'),'region','report_accessible_region');
    assert.equal(await region.getAttribute('aria-label'),declared.title+' saved rows','report_accessible_region');
    assert.equal(await region.getAttribute('tabindex'),'0','report_accessible_region');
    const headers=await region.locator('th').evaluateAll(nodes=>nodes.map(node=>({
      scope:node.getAttribute('scope'),title:node.firstChild?.textContent,
      original:node.querySelector('small')?.textContent??null})));
    const titles={Period:'Period',Product:'Product',Warehouse:'Warehouse',
      QuantityOpeningBalance:'Quantity Opening Balance',QuantityReceipt:'Quantity Receipt',
      QuantityExpense:'Quantity Expense',QuantityClosingBalance:'Quantity Closing Balance',
      AmountOpeningBalance:'Amount Opening Balance',AmountReceipt:'Amount Receipt',
      AmountExpense:'Amount Expense',AmountClosingBalance:'Amount Closing Balance'};
    assert.deepEqual(headers,projected.columns.map(column=>{
      assert.ok(Object.hasOwn(titles,column.name),'report_readable_headers');
      return {scope:'col',title:titles[column.name],original:titles[column.name]===column.name?null:column.name};
    }),'report_readable_headers');
    const cells=await region.locator('tbody tr').evaluateAll(rows=>rows.map(row=>[...row.cells].map(cell=>cell.textContent)));
    const dateText=projected.periodicity==='Day'?'2026-11-11 00:00:00':'2026-11-01 00:00:00';
    assert.deepEqual(cells,projected.rows.map(row=>row.map(cell=>cell.type==='Date'?dateText:
      cell.type==='Number'?cell.value:cell.text)),'report_readable_cells');
  };
  const showStatement=async(periodicity='None',opening=false)=>{
    checkpoint('report_fill');const panel=reportPanel();
    const start=opening?'2026-11-12T00:00:00':'2026-11-01T00:00:00';
    const end=opening?'2026-11-12T00:00:00':'2026-11-11T12:00:00';
    await fillPeriod(panel.getByLabel('From moment (inclusive)',{exact:true}),start);
    await fillPeriod(panel.getByLabel('Through moment (inclusive)',{exact:true}),end);
    await panel.getByLabel('Statement periodicity',{exact:true}).selectOption(periodicity);
    const expected={report:'StockStatement',at:null,start,end,periodicity,setup:lastApplicationState.reportSetup.ticket};
    const reply=replyFor(p=>p.method==='application.report');checkpoint('report_click');await reportButton('Show saved stock').click();
    checkpoint('report_wait');const response=await reply;checkpoint('report_read');
    assert.deepEqual(response.request().postDataJSON().params,expected,'report_period_request');
    const result=deliveredReply(response).result;assert.equal(result.error,null,'report_refused');await reportIdle();
    const projected=result.state.report;checkpoint('report_assert');
    assert.deepEqual(Object.fromEntries(Object.keys(expected).map(k=>[k,projected[k]])),expected,'report_period_result');
    assert.equal(await panel.locator('table tbody tr').count(),projected.rows.length,'report_dom_rows');
    assert.equal(await panel.locator('table button,table input,table select').count(),0,'report_not_readonly');
    await auditPresentation(projected);
    return projected;
  };
  const header=result=>Object.fromEntries(Object.entries(result).filter(([key])=>!['page','rows'].includes(key)));
  const pageMove=async(direction,twice=false)=>{
    const before=lastApplicationState.report,expected=before.page[direction==='Next'?'next':'previous'];
    const count=businessEvents.length,reply=replyFor(p=>p.method==='application.reportPage');
    checkpoint('page_click');const control=reportButton(direction+' saved page');
    if(twice)await repeatClick(control);else await control.click();
    checkpoint('page_wait');const response=await reply,result=deliveredReply(response).result;await reportIdle();
    checkpoint('page_assert');assert.equal(result.error,null,'report_refused');const after=result.state.report;
    assert.equal(after.page.snapshot,before.page.snapshot,'report_page_identity');assert.equal(after.page.cursor,expected,'report_page_identity');
    assert.deepEqual(header(after),header(before),'report_page_identity');assert.equal(after.page.total,before.page.total,'report_page_identity');
    assert.equal(businessEvents.length,count+1,'duplicate_page_rpc');
    await auditPresentation(after);
    return after;
  };
  const exactInteger=cell=>{
    assert.equal(cell.type,'Number','report_typed_totals');assert.match(cell.value,/^-?[0-9]+(?:\.0+)?$/,'report_typed_totals');
    return BigInt(cell.value.split('.')[0]);
  };
  const verifyRows=(result,rows,{opening=false,all=true,product=null}={})=>{
    const named=rows.map(row=>Object.fromEntries(result.columns.map((c,i)=>[c.name,row[i]])));
    const labels=[];let quantity=0n,amount=0n;
    for(const row of named){
      exactKeys(row.Product,'type text');exactKeys(row.Warehouse,'type text');
      assert.equal(row.Product.type,'Catalog');assert.equal(row.Warehouse.type,'Catalog');
      assert.match(row.Product.text,/^Product (00[1-9]|0[1-4][0-9]|05[0-2])$/,'report_saved_labels');
      assert.equal(row.Warehouse.text,'Main warehouse','report_saved_labels');
      const n=BigInt(row.Product.text.slice(-3));labels.push(row.Product.text);
      if(product!==null)assert.equal(Number(n),product,'report_saved_labels');
      if(result.periodicity==='None')assert.equal(Object.hasOwn(row,'Period'),false);
      else{exactKeys(row.Period,'type ticks');assert.equal(row.Period.type,'Date');assert.equal(row.Period.ticks,result.periodicity==='Day'?initialAudit.dayTicks:initialAudit.monthTicks,'report_typed_totals');}
      for(const [resource,multiplier] of [['Quantity',1n],['Amount',10n]]){
        const expected={OpeningBalance:opening?n*multiplier:0n,Receipt:opening?0n:n*multiplier,Expense:0n,ClosingBalance:n*multiplier};
        for(const [suffix,value] of Object.entries(expected))assert.equal(exactInteger(row[resource+suffix]),value,'report_typed_totals');
      }
      quantity+=exactInteger(row.QuantityClosingBalance);amount+=exactInteger(row.AmountClosingBalance);
    }
    assert.equal(new Set(labels).size,labels.length,'report_page_order');
    if(all){assert.deepEqual(labels.sort(),Array.from({length:52},(_,i)=>'Product '+String(i+1).padStart(3,'0')),'report_page_order');
      assert.equal(quantity,1378n,'report_typed_totals');assert.equal(amount,13780n,'report_typed_totals');}
  };
  const unchanged=()=>{checkpoint('audit_compare');assert.deepEqual(inventoryFixture('audit'),initialAudit,'readonly_audit_changed');};
  const assertRaw=async()=>{await value('Description','RAW DRAFT');assert.equal(wireEvents.filter(e=>e.event==='change').length,0,'unexpected_form_change');};
  const clickRetired=async handle=>{
    const count=businessEvents.length;assert.equal(await handle.evaluate(node=>node.isConnected),false,'retired_dom_dispatched');
    await handle.evaluate(node=>node.click());await flushPaint();
    assert.equal(businessEvents.length,count,'retired_dom_dispatched');await handle.dispose();
  };
  await startHost();await page.goto(url);await writer();await idle();
  checkpoint('report_tab');await page.getByRole('navigation',{name:'Declared stock reports',exact:true}).getByRole('button',{name:'Stock BalanceAndTurnovers',exact:true}).click();
  await scenario(scenarioNames[0],async()=>{
    await prepareStatement();const first=await showStatement('Day');assert.equal(first.rows.length,50);assert.equal(first.page.total,52);
    const second=await pageMove('Next',true);assert.equal(second.rows.length,2);verifyRows(first,[...first.rows,...second.rows]);
    const back=await pageMove('Previous');assert.deepEqual(back,first,'report_page_order');
    for(const periodicity of ['Month','None']){
      const first=await showStatement(periodicity),second=await pageMove('Next');verifyRows(first,[...first.rows,...second.rows]);
    }
    unchanged();await reportPanel().scrollIntoViewIfNeeded();await screenshot(screenshots[0]);
  });
  await scenario(scenarioNames[1],async()=>{
    let setup=await begin('Product');assert.equal(setup.choice.error,'too_many_matches','too_many_partial');assert.deepEqual(setup.choice.rows,[],'too_many_partial');
    setup=await search('P001');assert.deepEqual(setup.choice.rows.map(r=>[r.code,r.description]),[['P001','Product 001']],'exact_choice_mismatch');
    await apply('Product 001');let result=await showStatement();assert.equal(result.page.total,1);verifyRows(result,result.rows,{all:false,product:1});
    setup=await begin('Warehouse');assert.equal(setup.choice.rows.length,2);await apply('Unused warehouse');result=await showStatement();assert.equal(result.page.total,0,'excluded_filter_rows');
    const committed=structuredClone(lastApplicationState.reportSetup.filters);await begin('Warehouse');setup=await cancel();assert.deepEqual(setup.filters,committed,'cancel_changed_selection');
    assert.equal((await showStatement()).page.total,0,'excluded_filter_rows');
    await filterAction('empty','Warehouse');result=await showStatement();assert.equal(result.page.total,0,'explicit_empty_mismatch');assert.equal(result.filters[1].mode,'empty');
    await filterAction('clear','Warehouse');result=await showStatement();assert.equal(result.page.total,1);verifyRows(result,result.rows,{all:false,product:1});
    await filterAction('empty','Product');result=await showStatement();assert.equal(result.page.total,0,'explicit_empty_mismatch');
    await filterAction('clear','Product');result=await showStatement();assert.equal(result.page.total,52);assert.ok(result.filters.every(f=>f.mode==='all'));
    await begin('Product');setup=await search('ABSENT');assert.deepEqual(setup.choice.rows,[],'exact_choice_mismatch');assert.equal(setup.choice.error,null);await cancel();
    unchanged();await reportPanel().scrollIntoViewIfNeeded();await screenshot(screenshots[1]);
  });
  await scenario(scenarioNames[2],async()=>{
    // MAX_TABLE_ROWS=32 bounds editable forms, not the detached 52-row report.
    // Exercise drafts on the existing small sibling card, never the seed Receipt.
    let reply=replyFor(p=>p.method==='application.catalog');await entries().getByRole('button',{name:'Warehouses card',exact:true}).click();await reply;await idle();
    await catalog().locator('tbody tr').filter({has:page.getByRole('cell',{name:'W1',exact:true})}).getByRole('checkbox').check();
    reply=replyFor(p=>p.method==='application.openRecord');await catalog().getByRole('button',{name:'Open selected',exact:true}).click();
    const opened=deliveredReply(await reply).result;const owner=opened.session;await idle();await value('Description','Main warehouse');
    assert.match(owner,/^form-[1-9][0-9]*$/);checkpoint('draft_focus');await field('Description').fill('RAW DRAFT');
    await reportPanel().getByLabel('From moment (inclusive)',{exact:true}).click();await assertRaw();
    await prepareStatement();const first=await showStatement();await assertRaw();
    let arrived,release;const arrival=new Promise(resolve=>arrived=resolve),wait=new Promise(resolve=>release=resolve);
    delayed={arrived,wait};const count=businessEvents.length;reply=replyFor(p=>p.method==='application.reportPage');
    checkpoint('delayed_page');await repeatClick(reportButton('Next saved page'));await bounded(arrival,remaining(10000),'late_page_not_observed');
    assert.equal(await reportButton('Show saved stock').isDisabled(),true,'busy_not_fenced');assert.equal(await reportButton('Choose Product').isDisabled(),true,'busy_not_fenced');
    assert.equal(businessEvents.length,count+1,'duplicate_page_rpc');await assertRaw();release();
    const late=deliveredReply(await reply).result;await reportIdle();assert.equal(late.state.active,owner,'late_owner_changed');
    assert.equal(late.state.report.page.snapshot,first.page.snapshot,'report_page_identity');await assertRaw();
    await begin('Product');await search('P002');const retiredChoice=await choicePanel().getByRole('button',{name:'Product 002',exact:true}).elementHandle();
    await cancel();checkpoint('retired_choice');await clickRetired(retiredChoice);await assertRaw();
    await showStatement();const retiredPage=await reportButton('Next saved page').elementHandle();
    // Restore only the local draft. The renderer removes a draft equal to its
    // authoritative value, so Close flushes no change and source Dirty stays false.
    checkpoint('restore_draft');await field('Description').fill('Main warehouse');
    await value('Description','Main warehouse');
    assert.equal(wireEvents.filter(e=>e.event==='change').length,0,'unexpected_form_change');
    const beforeClose=businessEvents.length;checkpoint('close_form');const closed=await closeForm();
    assert.equal(closed.session,owner,'late_owner_changed');assert.equal(closed.error,null,'close_refused');
    await countPanels(0);assert.ok(!closed.state.sessions.some(s=>s.id===owner),'close_refused');
    assert.equal(businessEvents.length,beforeClose+1,'unexpected_form_change');
    assert.equal(wireEvents.filter(e=>e.event==='change').length,0,'unexpected_form_change');
    assert.equal(wireEvents.filter(e=>e.event==='command').length,0,'unexpected_form_write');
    assert.equal(lastApplicationState.report,null);assert.equal(lastApplicationState.reportSetup,null);
    checkpoint('retired_page');await clickRetired(retiredPage);unchanged();
    await prepareStatement();await showStatement();unchanged();await reportPanel().scrollIntoViewIfNeeded();await screenshot(screenshots[2]);
  });
  await scenario(scenarioNames[3],async()=>{
    const previousSetup=lastApplicationState.reportSetup.ticket,previousPage=lastApplicationState.report.page;
    await countPanels(0);unchanged();await naturalStop();await page.close();
    checkpoint('restart');page=await context.newPage();await startHost();await page.goto(url);await writer();await idle();
    assert.equal(lastApplicationState.reportSetup,null);assert.equal(lastApplicationState.report,null);assert.equal(lastApplicationState.sessions.length,0);
    await page.getByRole('navigation',{name:'Declared stock reports',exact:true}).getByRole('button',{name:'Stock BalanceAndTurnovers',exact:true}).click();
    const fresh=await prepareStatement();assert.notEqual(fresh.ticket,previousSetup,'restarted_ticket_reused');
    const first=await showStatement('None',true),second=await pageMove('Next');
    assert.notEqual(first.page.snapshot,previousPage.snapshot,'restarted_page_reused');assert.notEqual(first.page.cursor,previousPage.cursor,'restarted_page_reused');
    verifyRows(first,[...first.rows,...second.rows],{opening:true});unchanged();await reportPanel().scrollIntoViewIfNeeded();await screenshot(screenshots[3]);
    await naturalStop();unchanged();
    report.acceptance={storedSourceLauncher:true,explicitFullForms15:true,core15Denied:true,
      typedSetupBeforeBrowser:true,oneCatalogTransaction:true,oneReceiptPost:true,real52Rows:true,dayMonthNone:true,
      sameSnapshotPages:true,exactTypedSums:true,sourceGrantedFilters:true,tooManyRequiresCode:true,emptyDistinctFromAll:true,
      labelsNotCapabilities:true,smallSiblingDraft:true,localDraftRestored:true,closeRetiresPages:true,noFormWrites:true,rawDraftPreserved:true,retiredDomDenied:true,realResponseDelay:true,noReplay:true,
      naturalRestart:true,independentTypedAudit:true,reportWrites:false,restartReceiptRecovery:false,nativeWindowParity:false};
    report.audit={unchanged:true,fingerprint:initialAudit.fingerprint,sourceDigest:initialAudit.sourceDigest};
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
console.log(JSON.stringify({status:report.status,completed:results.length,total:4,source:report.sourceCommit,failure:report.failure,cleanup:report.cleanup}));
if(failed||report.status!=='PASS')process.exitCode=1;
