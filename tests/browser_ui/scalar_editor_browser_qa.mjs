/** Four owned typed-scalar flows. Exact naive dates, real Chromium/SQLite; no native UI parity claim. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile,rm,lstat,readdir} from 'node:fs/promises';
import {readFileSync,readlinkSync,lstatSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {allowedRequest,childEnvironment,ownBrowserPid,
  commandLineArgs,sandboxCommand,sandboxStatus,sha256,launchURL} from './support.mjs';

const startedAt=performance.now();
const workDeadline=startedAt+220000;
const totalDeadline=startedAt+240000;
const rpcFetchMs=35000,rpcReplyMs=rpcFetchMs+10000+5000; // Transport, preceding click, delivery reserve.
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
const screenshots=['scalar-product.png','scalar-document.png','scalar-invalid.png','scalar-independent.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['catalog_datetime_empty_qualifier_preflight','document_datetime_lines_durable_restart',
  'isolated_invalid_drafts_retained_tabs','held_write_reply_dirty_sibling_natural_shutdown'];
const plannedRPC=[13,29,7,7]; // 56 business RPCs; attachment heartbeats have a separate bound.
const tokens=[],results=[];
const report={status:'FAIL',sourceCommit:null,scenarios:results,sandbox:null,heartbeatBusy:0};
let output,owned,home,env,host,browser,context,page,hostGroup,browserGroup;
let outputCreated=false,origin='',url='',phase='binding',aborted=false,rpc=0,failed=false;
const bounded=(promise,ms,code)=>{
  let timer;return Promise.race([promise,new Promise((_,reject)=>{
    timer=setTimeout(()=>reject(Error(code)),ms);
  })]).finally(()=>clearTimeout(timer));
};
const check=()=>{if(aborted||performance.now()>=workDeadline){aborted=true;throw Error('global_deadline_or_budget');}};
const remaining=max=>{check();return Math.max(1,Math.min(max,workDeadline-performance.now()));};
const cleanupRemaining=max=>Math.max(1,Math.min(max,totalDeadline-performance.now()));
const git=(...args)=>execFileSync('git',args,{cwd:repo,encoding:'utf8',timeout:remaining(5000),maxBuffer:1024*1024,stdio:['ignore','pipe','pipe']}).trim();

// AssertionError may append an actual/expected diff. Match only a known first
// line and emit the allowlisted label, never any suffix from the exception.
function stepFailureCode(error){
  const message=typeof error?.message==='string'?error.message:'';
  const fixed=['ordinary_host_exit_timeout','ordinary_host_exit_failed','owned_group_cleanup_unverified',
    'independent_typed_readback','catalog_rpc_plan','restart_rpc_plan','invalid_draft_rpc_plan','total_rpc_plan',
    'evidence_input_offscreen','evidence_input_clipped','evidence_viewport_missing',
    'reopened_checkbox_changed','reference_not_typed','reopened_lines_missing',
    'reopened_product_column_missing','reopened_product_not_typed','save_reply_not_saved',
    'held_reply_not_ready','held_sibling_not_visible','held_owner_close_not_disabled','held_write_not_saved',
    'late_close_sent_work','late_close_removed_owner','double_write_replayed','late_reply_changed_sibling','dirty_sibling_closed'];
  return fixed.find(code=>message===code||message.startsWith(code+'\n'))??
    (error?.name==='TimeoutError'?'browser_step_timeout':'unclassified_step');
}

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
  for(let attempt=0;attempt<20&&performance.now()<totalDeadline;attempt++){
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
  const args=['-m','yadinassi.ui.configuration_app',path.join(repo,'examples/configuration-scalar-editors'),
    '--reference-application','--f',path.join(owned,'scalars.sqlite')];
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
// This fixed Python CLI never returns identities or source; it seeds/audits only
// this invocation's fresh owned SQLite file. No user database or native fixture.
function fixture(mode){
  assert.ok(['create','leap','empty','first','final'].includes(mode),'fixture_mode');
  const script=`from contextlib import closing
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import sys
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalogs import BSLCatalogs
from yadinassi.metadata import BSLCatalogMetadataCollection
from yadinassi.catalog_backend import CatalogKey
from yadinassi.document_backend import DocumentSelection
root=Path(sys.argv[1]); target=Path(sys.argv[2]); mode=sys.argv[3]
files={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
if mode=='create':
 assert not target.exists()
 with closing(SQLiteCatalogBackend.create_reference_application(target,files)) as backend:
  assert backend.storage_version==7
 with closing(SQLiteDBContext(target)) as context:
  catalogs=BSLCatalogs(BSLCatalogMetadataCollection(context),context)
  item=catalogs.get_index('Categories').create_item()
  item.set_member('Code','C1'); item.set_member('Description','Category One'); item.write()
  item=catalogs.get_index('Products').create_item()
  item.set_member('Code','P1'); item.set_member('Description','Seed product'); item.write()
else:
 before=sha256(target.read_bytes()).digest()
 with closing(SQLiteCatalogBackend(target,read_only=True)) as backend:
  assert backend.export_configuration()==files
  with closing(backend.begin_read()) as view:
   schemas={s.name:s for s in view.catalogs()}
   categories={c.code:c for c in view.select_catalog(schemas['Categories'].identity)}
   products={c.code:c for c in view.select_catalog(schemas['Products'].identity)}
  assert set(categories)=={'C1'} and set(products)=={'P1','P2'}
  product=products['P2']; values={f.name:v for f,v in zip(schemas['Products'].fields,product.values)}
  assert product.description=='Scalar product'
  assert type(values['Price']) is Decimal and values['Price']==Decimal('7.25' if mode=='leap' else '8.50')
  stamp=values['AvailableDate']
  assert type(stamp) is datetime and stamp.tzinfo is None and stamp.microsecond==0
  assert stamp==(datetime(2024,2,29,23,45,17) if mode=='leap' else datetime(1,1,1))
  category=values['Category']
  assert type(category) is CatalogKey and category.catalog_id==schemas['Categories'].identity and category.record_id.int==0
  if mode in ('first','final'):
   with closing(backend.begin_document_read()) as view:
    schema,=view.documents()
    orders={card.number:view.read_document(card.key) for card in view.select_documents(schema.identity,DocumentSelection(limit=3))}
   assert set(orders)==({'D1','D2'} if mode=='final' else {'D1'})
   first=orders['D1']; header={f.name:v for f,v in zip(schema.fields,first.values)}
   assert first.date==datetime(2024,3,10,2,30,1 if mode=='final' else 0)
   assert type(first.date) is datetime and first.date.tzinfo is None and first.date.microsecond==0
   assert header['Note']==('Corrected order' if mode=='final' else 'Scalar order')
   assert type(header['Category']) is CatalogKey and header['Category']==categories['C1'].key
   rows=first.tabular_sections[0].rows; fields=schema.tabular_sections[0].fields
   assert len(rows)==2
   first_line={f.name:v for f,v in zip(fields,rows[0].values)}
   second_line={f.name:v for f,v in zip(fields,rows[1].values)}
   assert first_line['DeliveryDate']==datetime(2024,11,3,1,30,0)
   assert second_line['DeliveryDate']==datetime(2024,3,31,2,30,0)
   for line in (first_line,second_line):
    assert type(line['DeliveryDate']) is datetime and line['DeliveryDate'].tzinfo is None and line['DeliveryDate'].microsecond==0
    assert type(line['Quantity']) is Decimal and type(line['Checked']) is bool and type(line['Product']) is CatalogKey
   assert first_line['Product']==products['P2'].key and first_line['Label']=='Scalar line'
   assert first_line['Quantity']==Decimal('4.50' if mode=='final' else '3.25') and first_line['Checked'] is True
   assert second_line['Label']=='Second line' and second_line['Quantity']==Decimal('2.50') and second_line['Checked'] is False
   assert second_line['Product'].catalog_id==schemas['Products'].identity and second_line['Product'].record_id.int==0
   if mode=='final':
    sibling=orders['D2']; values={f.name:v for f,v in zip(schema.fields,sibling.values)}
    assert values['Note']=='Sibling draft' and not sibling.tabular_sections[0].rows
    assert type(sibling.date) is datetime and sibling.date==datetime(1,1,1) and sibling.date.tzinfo is None
    assert type(values['Category']) is CatalogKey and values['Category'].record_id.int==0
 assert sha256(target.read_bytes()).digest()==before
print('SCALAR_FIXTURE_OK')
`;
  const raw=execFileSync(python,['-c',script,path.join(repo,'examples/configuration-scalar-editors'),path.join(owned,'scalars.sqlite'),mode],
    {cwd:repo,env,encoding:'utf8',timeout:remaining(15000),maxBuffer:128,stdio:['ignore','pipe','ignore']});
  assert.equal(raw.trim(),'SCALAR_FIXTURE_OK','independent_typed_readback');
}
let delayedWrite=null;
const snapshots=new Map();
let appState=null;
const idle=()=>page.waitForFunction(()=>[...document.querySelectorAll('[aria-busy]')].every(node=>node.getAttribute('aria-busy')==='false'),null,{timeout:remaining(10000)});
const countPanels=count=>page.waitForFunction(expected=>document.querySelectorAll('.configuration-form-panels > section').length===expected,count,{timeout:remaining(10000)});
async function value(name,expected){
  await field(name).waitFor();
  await page.waitForFunction(({name,expected})=>[...document.querySelectorAll('.configuration-form-panels > section:not([hidden]) input')]
    .some(input=>input.getAttribute('aria-label')===name&&input.value===expected),{name,expected},{timeout:remaining(10000)});
  assert.equal(await field(name).inputValue(),expected);
}
// Commit each valid draft through the real form lifecycle before the next
// intent. Invalid drafts stay in the actual browser until corrected explicitly.
async function commitInput(name,text){
  await field(name).fill(text);await field(name).press('Enter');await idle();
}
const wireEvents=[];
let wireFailure=false;
let businessWire=null;
let pendingSave=null;
const matchesSave=(packet,save)=>Boolean(save&&packet.method==='application.form'&&
  packet.params.session===save.session&&packet.params.request.method==='form.event'&&
  packet.params.request.params.event==='command'&&packet.params.request.params.control===save.control);
function diagnosticSaveStatus(result){
  const items=result.form?.result?.state?.items;
  const value=Array.isArray(items)?items.find(item=>item?.name==='StatusLabel')?.value:undefined;
  return value?.type==='String'?['saved','unchanged','rejected','uncertain','committed']
    .find(allowed=>allowed===value.value)??'other':'other';
}
const exactKeys=(value,names)=>assert.deepEqual(Object.keys(value).sort(),names.split(' ').filter(Boolean).sort(),'wire_keys');
function checkEditor(editor,type){
  assert.ok(editor&&typeof editor==='object'&&!Array.isArray(editor),'editor_object');
  const count=(value,max)=>Number.isSafeInteger(value)&&value>=0&&value<=max;
  if(type==='Date'){
    exactKeys(editor,'kind parts');assert.equal(editor.kind,'date');
    assert.ok(['dateTime','date','time'].includes(editor.parts),'editor_date_parts');
  }else if(type==='Number'){
    exactKeys(editor,'kind digits scale nonnegative');assert.equal(editor.kind,'number');
    assert.ok(count(editor.digits,128)&&count(editor.scale,editor.digits),'editor_number_counts');
    assert.equal(typeof editor.nonnegative,'boolean','editor_number_sign');
  }else{
    assert.equal(type,'String','editor_scalar_type');exactKeys(editor,'kind length fixed');assert.equal(editor.kind,'string');
    assert.ok(count(editor.length,65536),'editor_string_length');assert.equal(typeof editor.fixed,'boolean','editor_string_fixed');
    assert.ok(editor.length!==0||!editor.fixed,'editor_unqualified_string');
  }
}
// Closed diagnostic vocabularies only. A malformed/unknown envelope never
// supplies a string to the artifact, and diagnostics never authorize a reply.
const diagnosticStatus=status=>[200,400,403,404,405,409,411,413,503].find(allowed=>allowed===status)??'other';
function diagnosticRefusal(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join(',')!=='error,protocol'||
    value.protocol!=='yadinassi-browser-attachment/1')return 'unclassified';
  return ['not_writer','stale_generation','busy','outcome_unknown','unauthorized','closed','capacity','invalid_message']
    .find(allowed=>allowed===value.error)??'unclassified';
}
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
    exactKeys(packet.params,'protocol');assert.equal(packet.params.protocol,'yadinassi-configuration-app/3');
  }else if(packet.method==='application.reference'){
    exactKeys(packet.params,'session revision action');
    assert.match(packet.params.session,/^form-[1-9][0-9]*$/);
    assert.ok(Number.isSafeInteger(packet.params.revision)&&packet.params.revision>=0);
    const action=packet.params.action;
    if(['begin','clear'].includes(action.action)){
      exactKeys(action,'action control row column');
      assert.ok(action.control==='CategoryInput'&&action.row===null&&action.column===null||
        action.control==='LinesTable'&&Number.isSafeInteger(action.row)&&action.row>0&&action.row<=4096&&action.column==='Product');
    }else{
      const shapes={filter:'action ticket code',cancel:'action ticket',apply:'action ticket choice'};
      assert.ok(Object.hasOwn(shapes,action.action));exactKeys(action,shapes[action.action]);
      assert.equal(action.ticket,appState?.choice?.ticket,'unissued_picker_ticket');
      assert.equal(packet.params.session,appState.choice.session,'crossed_picker_owner');
      if(action.action==='filter')assert.ok(typeof action.code==='string'&&action.code.length<=64);
      if(action.action==='apply')assert.ok(appState.choice.rows.some(row=>row.choice===action.choice),'unissued_choice');
    }
    wireEvents.push({session:packet.params.session,event:'reference',control:action.control,action:action.action});
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
        if(event.event==='cell')assert.ok(['DeliveryDate','Label','Quantity','Checked'].includes(event.column),'declared_column');
      }
      if(event.event==='change'||event.event==='cell'){
        checkScalar(event.value);
        assert.ok(['String','Number','Boolean','Date'].includes(event.value.type),'scalar_only');
        if(event.value.type==='Date'){
          assert.ok(event.event==='change'&&['DateInput','AvailableDateInput'].includes(event.control)||
            event.event==='cell'&&event.control==='LinesTable'&&event.column==='DeliveryDate','declared_date_input');
          assert.ok(BigInt(event.value.ticks)<=3155378975980000n&&BigInt(event.value.ticks)%10000n===0n,'date_input_envelope');
        }
      }
      wireEvents.push({session:packet.params.session,event:event.event,control:event.control,row:event.row,column:event.column});
    }
  }
  return packet;
}
async function scenario(name,fn){check();phase=name;await fn();check();results.push({name,status:'PASS'});}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:Object.keys(sessionStorage)})),{local:0,session:['yadinassi.browser.resume/1']},'only_resume_storage');
  assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/configuration',
    'frontend/reference-workspace','frontend/workspace','docs/typed-scalar-browser-qa.md',
    'examples/configuration-scalar-editors','tests/browser_ui',
    'tests/test_form_editor_projection.py','tests/test_configuration_scalar_editors.py',
    'tests/test_scalar_editor_browser_qa_contract.py','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  for(const required of ['yadinassi/configuration_reference_profile.py','yadinassi/configuration_references.py',
    'yadinassi/configuration_reference_choice.py','yadinassi/form_references.py',
    'yadinassi/ui/configuration_app.py','yadinassi/ui/form_app.py','frontend/form/src/attachment.mjs',
    'frontend/form/src/client.mjs','frontend/form/src/view.mjs','frontend/form/src/app.mjs','frontend/configuration/src/app.mjs',
    'yadinassi/ui/assets/form/app.js','yadinassi/ui/assets/configuration/app.js',
    'yadinassi/ui/assets/reference-workspace/app.js','yadinassi/ui/assets/workspace/app.js',
    'examples/configuration-scalar-editors/Configuration.xml',
    'examples/configuration-scalar-editors/Catalogs/Products.xml',
    'examples/configuration-scalar-editors/Documents/Orders.xml',
    'tests/browser_ui/scalar_editor_browser_qa.mjs','tests/test_scalar_editor_browser_qa_contract.py',
    'docs/typed-scalar-browser-qa.md'])
    assert.ok(names.includes(required),'required_source_not_tracked');
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
function checkScalar(value){
  assert.ok(value&&typeof value==='object'&&!Array.isArray(value),'scalar_object');
  if(value.type==='Date'){
    exactKeys(value,'type ticks');assert.equal(typeof value.ticks,'string');
    assert.ok(/^(?:0|[1-9][0-9]{0,15})$/.test(value.ticks)&&String(BigInt(value.ticks))===value.ticks,'date_ticks_text');
    assert.ok(BigInt(value.ticks)<=3155378975990000n,'date_ticks_range');
  }else{
    exactKeys(value,'type value');assert.ok(['String','Number','Boolean'].includes(value.type),'scalar_type');
    if(value.type==='Boolean')assert.equal(typeof value.value,'boolean');
    else{
      assert.equal(typeof value.value,'string');assert.ok(Buffer.byteLength(value.value)<=8192,'scalar_text_budget');
      if(value.type==='Number'){
        assert.ok(value.value.length<=144,'decimal_budget');
        const match=/^-?[0-9]+(?:\.[0-9]+)?(?:E[+-][0-9]{1,4})?$/.exec(value.value);
        assert.ok(match&&match[0]===value.value,'decimal_text');
      }
    }
  }
}
// Responses stay in memory only. Validate reference provenance without exporting
// scoped identities, selection tickets, raw request/response bodies or DOM dumps.
function checkReply(body,packet,stage){
  stage('reply_envelope');
  exactKeys(body,'jsonrpc id result');assert.equal(body.id,packet.id);assert.equal(body.jsonrpc,'2.0');
  const result=body.result;exactKeys(result,'protocol state error session form');
  assert.equal(result.protocol,'yadinassi-configuration-app/3');assert.equal(result.error,null,'application_refused');
  assert.equal(result.state.uncertain,false);assert.ok(Object.hasOwn(result.state,'choice'));
  if(result.form){
    assert.equal(result.form.result.error,null,'form_refused');
    snapshots.set(result.session,result.form.result.state);
  }
  const inspect=(value,context='value')=>{
    // Only a table's columns array introduces descriptor context. A malformed
    // reference value must not escape validation merely by omitting its scope.
    if(context==='table-column'){
      stage('reference_descriptor');
      assert.ok(value&&typeof value==='object'&&!Array.isArray(value),'column_object');
      exactKeys(value,'name title type readOnly'+(Object.hasOwn(value,'editor')?' editor':''));
      assert.ok(typeof value.name==='string'&&value.name.length>0&&value.name.length<=128,'column_name');
      assert.ok(typeof value.title==='string'&&value.title.length<=1024,'column_title');
      assert.ok(['String','Number','Boolean','Date','FormCatalogRef'].includes(value.type),'column_type');
      assert.equal(typeof value.readOnly,'boolean','column_readonly');
      if(Object.hasOwn(value,'editor'))checkEditor(value.editor,value.type);
      return;
    }
    assert.equal(context,'value','reference_context');
    if(!value||typeof value!=='object')return;
    if(value.kind==='field'&&Object.hasOwn(value,'editor')){
      stage('scalar_descriptor');checkEditor(value.editor,value.value?.type);
    }
    if(['Date','String','Number','Boolean'].includes(value.type)){
      stage('scalar_value');checkScalar(value);
    }
    if(value.type==='FormCatalogRef'){
      stage('reference_value');
      exactKeys(value,'type scope target key text');assert.match(value.scope,/^[0-9a-f]{32}$/);
      assert.ok(Number.isSafeInteger(value.target)&&value.target>0&&value.target<=128);
      assert.ok(value.key===null||/^[0-9a-f]{32}$/.test(value.key));
      assert.ok(typeof value.text==='string'&&value.text.length<=1024);
      if(value.key===null)assert.equal(value.text,'');
    }
    for(const [key,nested] of Object.entries(value)){
      if(value.kind==='table'&&key==='columns'){
        stage('reference_descriptor');
        assert.ok(Array.isArray(nested)&&nested.length>0&&nested.length<=8,'column_budget');
        for(const column of nested)inspect(column,'table-column');
      }else inspect(nested,'value');
    }
  };
  inspect(result);appState=result.state;
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-scalar-editor-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'ya-se-'));
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
  context=await bounded(browser.newContext({viewport:{width:1440,height:1100},locale:'en-US',timezoneId:'UTC',
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
      let wireStage='attachment_request',httpStatus='unavailable',refusalCode='none';
      try{
        assert.ok(++attachmentRequests<=96,'attachment_budget');
        const request=route.request(),body=request.postDataJSON();
        if(body.action==='attach'){exactKeys(body,'action instance');assert.match(body.instance,/^[0-9a-f]{32}$/);}
        else{exactKeys(body,'action generation pending');assert.ok(['status','heartbeat','detach','takeover'].includes(body.action));assert.ok(Number.isSafeInteger(body.generation)&&body.generation>=0);assert.equal(typeof body.pending,'boolean');}
        wireStage='attachment_fetch';
        const response=await route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0});
        httpStatus=diagnosticStatus(response.status());wireStage='attachment_budget';
        const bytes=await response.body();assert.ok(bytes.length<=8192,'attachment_reply_budget');
        wireStage='attachment_json';
        const value=JSON.parse(bytes.toString('utf8'));
        if(response.status()!==200)refusalCode=diagnosticRefusal(value);
        wireStage='attachment_status';
        if(body.action==='heartbeat'&&response.status()===409){
          // The server's dispatch gate may be held by an admitted business RPC.
          // Only this exact pre-dispatch heartbeat refusal is benign. Deliver
          // the real response unchanged; never retry it or any business request.
          exactKeys(value,'protocol error');assert.equal(value.protocol,'yadinassi-browser-attachment/1');
          assert.equal(value.error,'busy','unexpected_heartbeat_refusal');
          assert.ok(++report.heartbeatBusy<=attachmentRequests,'heartbeat_busy_budget');
          wireStage='attachment_delivery';return await route.fulfill({response});
        }
        assert.equal(response.status(),200,'attachment_refused');
        wireStage='attachment_schema';
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
        wireStage='attachment_delivery';return await route.fulfill({response});
      }catch{
        if(host&&host.exitCode===null&&!aborted){
          report.wireStage??=wireStage;
          report.wireDiagnostic??={httpStatus,refusalCode,businessStage:businessWire?.stage??'idle'};
          wireFailure=true;abort();
        }
        return route.abort().catch(()=>{});
      }
    }
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=100){abort();return route.abort().catch(()=>{});}
      rpc++;
      let wireStage='request_schema',httpStatus='unavailable',refusalCode='none';
      const business={stage:wireStage};businessWire=business;
      const stage=value=>{wireStage=value;business.stage=value;};
      try{
        const packet=checkRequest(route.request());
        const saving=matchesSave(packet,pendingSave)?pendingSave:null;
        if(saving)saving.diagnostic.requestAdmitted=true;
        const held=matchesSave(packet,delayedWrite)?delayedWrite:null;
        if(held){delayedWrite=null;held.diagnostic.requestAdmitted=true;}
        stage('rpc_fetch');
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        httpStatus=diagnosticStatus(response.status());stage('reply_budget');
        const bytes=await response.body();assert.ok(bytes.length<=131072,'rpc_reply_budget');
        assert.ok(!/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/i.test(bytes.toString('utf8')),'persistent_uuid_in_reply');
        stage('reply_json');const result=JSON.parse(bytes.toString('utf8'));
        if(response.status()!==200)refusalCode=diagnosticRefusal(result);
        stage('http_status');assert.equal(response.status(),200,'rpc_status');
        checkReply(result,packet,stage);
        if(saving){saving.diagnostic.bodyAccepted=true;saving.diagnostic.status=diagnosticSaveStatus(result.result);}
        // Delay only delivery of an already completed real reply. Never invent
        // a reply or repeat a request to make the late-navigation scenario pass.
        if(held){
          const gate=held;gate.diagnostic.bodyAccepted=true;gate.diagnostic.status=diagnosticSaveStatus(result.result);
          assert.equal(gate.diagnostic.status,'saved','held_write_not_saved');
          stage('held_write');gate.diagnostic.replyHeld=true;gate.entered();
          await bounded(gate.released,remaining(5000),'held_write_timeout');
        }
        stage('delivery');await route.fulfill({response});
        if(saving)saving.diagnostic.deliveryCompleted=true;
        if(held)held.diagnostic.deliveryCompleted=true;
        return;
      }catch{
        // Preserve the first failure before aborting. An in-flight RPC failing
        // because another route or cleanup stopped the host is not its cause.
        if(!aborted){
          report.wireStage??=wireStage;
          report.wireDiagnostic??={httpStatus,refusalCode,businessStage:businessWire?.stage??'idle'};
          wireFailure=true;abort();
        }
        return route.abort().catch(()=>{});
      }finally{if(businessWire===business)businessWire=null;}
    }
    return route.continue();
  });
  page=await context.newPage();
  const picker=()=>page.getByRole('dialog');
  const writer=()=>page.waitForFunction(()=>{
    const banner=document.querySelector('.browser-ownership');
    return banner?.dataset.role==='writer'&&banner.nextElementSibling?.inert===false;
  },null,{timeout:remaining(10000)});
  const replyFor=predicate=>page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.status()===200&&predicate(response.request().postDataJSON()),{timeout:remaining(rpcReplyMs)});
  const refReply=kind=>replyFor(packet=>packet.method==='application.reference'&&packet.params.action.action===kind);
  const begin=async label=>{const reply=refReply('begin');await action('Choose '+label).click();await reply;await picker().waitFor();await idle();};
  const filter=async code=>{
    await picker().getByLabel('Exact code',{exact:true}).fill(code);
    const reply=refReply('filter');await picker().getByRole('button',{name:'Find exact code',exact:true}).click();await reply;await idle();
  };
  const apply=async(code,title)=>{
    const reply=refReply('apply');await picker().getByRole('button',{name:'Choose '+code+' '+title,exact:true}).click();
    await reply;await picker().waitFor({state:'hidden'});await idle();
  };
  const select=async(label,code,title)=>{await begin(label);await filter(code);await apply(code,title);};
  const save=async(name,control,status)=>{
    const diagnostic={command:control==='WriteButton'?'document_write':'product_save',stage:'click_command',
      requestAdmitted:false,bodyAccepted:false,deliveryCompleted:false,responseMatched:false,status:'not_received'};
    report.saveDiagnostic=diagnostic;
    const saving={session:appState.active,control,diagnostic};pendingSave=saving;
    const reply=replyFor(packet=>{
      if(!matchesSave(packet,saving))return false;
      diagnostic.responseMatched=true;return true;
    });
    // Observe rejection even if the click itself fails before awaiting reply.
    // This does not retry, resolve or replace the original waiting promise.
    reply.catch(()=>{});
    try{
      await action(name).click();diagnostic.stage='await_response';await reply;
      diagnostic.stage='await_saved_field';
      assert.equal(diagnostic.status,'saved','save_reply_not_saved');
      await value(status,'saved');diagnostic.stage='await_idle';await idle();diagnostic.stage='complete';
    }finally{if(pendingSave===saving)pendingSave=null;}
  };
  const saveProduct=()=>save('Save record','SaveButton','Save status');
  const writeDocument=()=>save('Write document','WriteButton','Write status');
  const closeForm=async count=>{const reply=replyFor(packet=>packet.params?.request?.params?.event==='close');await action('Close form').click();await reply;await countPanels(count);await idle();};
  const ordinaryShutdown=async()=>{
    const reply=replyFor(packet=>packet.method==='application.close');await button('Close application').click();await reply;
    assert.equal(appState.lifecycle,'closed');assert.equal(appState.kind,'closed');assert.equal(appState.sessions.length,0);
    if(host.exitCode===null&&host.signalCode===null)await bounded(new Promise(resolve=>host.once('exit',resolve)),remaining(10000),'ordinary_host_exit_timeout');
    assert.equal(host.exitCode,0,'ordinary_host_exit_failed');
    await groupGone(hostGroup);host=null;hostGroup=null;origin='';
  };
  const referenceValue=(session,control)=>{
    const value=snapshots.get(session)?.items.find(item=>item.name===control)?.value;
    assert.equal(value?.type,'FormCatalogRef','reference_not_typed');return value;
  };
  const openNumber=async number=>{
    const row=catalog().locator('tbody tr').filter({has:page.getByRole('cell',{name:number,exact:true})});
    await row.getByRole('checkbox').check();await catalog().getByRole('button',{name:'Open selected',exact:true}).click();
    await value('Number (blank for automatic)',number);await idle();
  };
  const switchOrder=async index=>{await tabs().getByRole('button',{name:'Non-posting order',exact:true}).nth(index).click();await idle();};
  const rowCount=n=>page.waitForFunction(expected=>document.querySelectorAll('.configuration-form-panels > section:not([hidden]) table tbody tr').length===expected,n,{timeout:remaining(10000)});
  const countEvent=(event,control,column)=>wireEvents.filter(item=>item.event===event&&item.control===control&&
    (column===undefined||item.column===column)).length;
  const typed=(session,control)=>snapshots.get(session)?.items.find(item=>item.name===control)?.value;
  const hasDateEditor=async label=>{
    assert.equal(await field(label).getAttribute('type'),'text','date_not_text_editor');
    assert.equal(await field(label).isEditable(),true,'date_not_editable');
  };
  const visibleInShot=async labels=>{
    const viewport=page.viewportSize();assert.ok(viewport,'evidence_viewport_missing');
    for(const label of labels){
      const box=await field(label).boundingBox();
      assert.ok(box&&box.width>0&&box.height>0&&box.x>=0&&box.y>=0&&
        box.x+box.width<=viewport.width&&box.y+box.height<=viewport.height,'evidence_input_offscreen');
      // An input can be inside the viewport but outside a narrower table's
      // scrollport. Require the whole control to survive ancestor clipping.
      const unclipped=await field(label).evaluate(input=>{
        const rect=input.getBoundingClientRect(),clips=value=>['auto','scroll','hidden','clip'].includes(value);
        for(let parent=input.parentElement;parent;parent=parent.parentElement){
          const style=getComputedStyle(parent),bounds=parent.getBoundingClientRect();
          const left=bounds.left+parent.clientLeft,top=bounds.top+parent.clientTop;
          if(clips(style.overflowX)&&(rect.left<left||rect.right>left+parent.clientWidth))return false;
          if(clips(style.overflowY)&&(rect.top<top||rect.bottom>top+parent.clientHeight))return false;
        }
        return true;
      });
      assert.equal(unclipped,true,'evidence_input_clipped');
    }
  };
  const captureEvidence=async(name,labels)=>{
    // Real scrolling only: expose the table column, then anchor the topmost
    // requested field. "If needed" alone leaves a visible header near the
    // bottom while the rows remain below it. Do not resize or rewrite the UI.
    for(const label of labels)await field(label).scrollIntoViewIfNeeded();
    await field(labels[0]).evaluate(input=>input.scrollIntoView({block:'start',inline:'nearest',behavior:'instant'}));
    // Keep the safe, allowlisted screenshot if its visibility check fails.
    // Such an image is diagnostic evidence only; the scenario still fails.
    await screenshot(name);await visibleInShot(labels);
  };
  const blockedIntents=async()=>{
    const before=rpc;
    await action('Write document').click();await idle();assert.equal(rpc,before,'invalid_save_sent_rpc');
    await active().getByRole('button',{name:/^Select row /}).first().click();await idle();assert.equal(rpc,before,'invalid_selection_sent_rpc');
    await action('Choose Product, row 1').click();await idle();assert.equal(rpc,before,'invalid_reference_sent_rpc');
    assert.equal(await picker().isVisible(),false,'invalid_opened_picker');
  };
  let firstOrder,sibling,firstCategory,firstProduct;
  await scenario(scenarioNames[0],async()=>{
    phase='fresh_scalar_database';fixture('create');await startHost();await page.goto(url);await writer();await countPanels(1);await idle();
    assert.deepEqual(appState.messages,['Calculated in the owned server process','8'],'startup_servercall');
    await action('New product').click();await countPanels(2);await value('Save status','');await idle();
    await commitInput('Product code','P2');await commitInput('Product title','Scalar product');await commitInput('Unit price','7.25');
    await hasDateEditor('Available since');await commitInput('Available since','2024-02-29T23:45:17');
    await saveProduct();fixture('leap');
    await value('Available since','2024-02-29T23:45:17');
    await captureEvidence(screenshots[0],['Unit price','Available since']);
    phase='catalog_lossless_number_and_string_preflight';const before=rpc;
    await field('Unit price').fill('7.251');await action('Save record').click();await idle();
    assert.equal(rpc,before,'price_precision_sent_rpc');assert.equal(await field('Unit price').inputValue(),'7.251');
    await field('Unit price').fill('7.25');await field('Unit price').press('Enter');await idle();assert.equal(rpc,before);
    await field('Product title').fill('x'.repeat(81));assert.equal((await field('Product title').inputValue()).length,81,'title_silently_truncated');
    await action('Save record').click();await idle();assert.equal(rpc,before,'long_title_sent_rpc');
    await field('Product title').fill('Scalar product');await field('Product title').press('Enter');await idle();assert.equal(rpc,before);
    const prices=countEvent('change','PriceInput');await commitInput('Unit price','8.5000');await value('Unit price','8.50');
    assert.equal(countEvent('change','PriceInput'),prices+1,'corrected_price_sent_twice');
    await commitInput('Available since','');assert.deepEqual(typed(appState.active,'AvailableDateInput'),{type:'Date',ticks:'0'},'clear_not_typed_date_zero');
    await saveProduct();fixture('empty');await closeForm(1);
    assert.equal(rpc,plannedRPC[0],'catalog_rpc_plan');
  });
  await scenario(scenarioNames[1],async()=>{
    phase='document_naive_datetime_header_and_rows';await action('New order').click();await countPanels(2);await value('Write status','Rows loaded: 0');await idle();
    await commitInput('Number (blank for automatic)','D1');await commitInput('Note','Scalar order');
    await hasDateEditor('Order date and time');await commitInput('Order date and time','2024-03-10T02:30:00');
    await select('Category','C1','Category One');await action('Add line').click();await rowCount(1);await idle();
    await select('Product, row 1','P2','Scalar product');assert.equal(await field('Product, row 1').isEditable(),false,'reference_text_editable');
    await hasDateEditor('DeliveryDate, row 1');await commitInput('DeliveryDate, row 1','2024-11-03T01:30:00');
    await commitInput('Label, row 1','Scalar line');await commitInput('Quantity, row 1','3.2500');await value('Quantity, row 1','3.25');
    await field('Checked, row 1').check();await idle();
    await action('Add line').click();await rowCount(2);await idle();
    await commitInput('DeliveryDate, row 2','2024-03-31T02:30:00');await commitInput('Label, row 2','Second line');
    phase='document_second_quantity';await commitInput('Quantity, row 2','2.50');
    phase='document_write';await writeDocument();
    phase='document_close_saved';await closeForm(1);
    phase='document_close_welcome';await closeForm(0);
    phase='document_ordinary_shutdown';await ordinaryShutdown();
    phase='independent_typed_datetime_audit';fixture('first');
    phase='document_restart';
    await page.close();page=await context.newPage();await startHost();await page.goto(url);await writer();await countPanels(1);await idle();
    phase='document_reopen_catalog';
    await entries().getByRole('button',{name:'Non-posting order',exact:true}).click();await openNumber('D1');
    phase='document_reopen_header';await value('Order date and time','2024-03-10T02:30:00');
    phase='document_reopen_line_dates';await value('DeliveryDate, row 1','2024-11-03T01:30:00');await value('DeliveryDate, row 2','2024-03-31T02:30:00');
    phase='document_reopen_quantities';await value('Quantity, row 1','3.25');await value('Quantity, row 2','2.50');
    phase='document_reopen_references';await value('Product, row 1','Scalar product');await value('Category','Category One');
    assert.equal(await field('Checked, row 1').isChecked(),true,'reopened_checkbox_changed');
    phase='document_reopen_reference_snapshots';
    firstOrder=appState.active;firstCategory=structuredClone(referenceValue(firstOrder,'CategoryInput'));
    const grid=snapshots.get(firstOrder)?.items.find(item=>item.name==='LinesTable');
    assert.ok(grid?.rows?.length===2,'reopened_lines_missing');
    const productColumn=grid.columns.findIndex(column=>column.name==='Product');
    assert.ok(productColumn>=0,'reopened_product_column_missing');
    firstProduct=structuredClone(grid.rows[0].values[productColumn]);
    assert.equal(firstProduct?.type,'FormCatalogRef','reopened_product_not_typed');
    phase='document_reopen_evidence';
    await captureEvidence(screenshots[1],['Order date and time','DeliveryDate, row 1','DeliveryDate, row 2']);
    phase='document_restart_rpc_count';assert.equal(rpc,plannedRPC[0]+plannedRPC[1],'restart_rpc_plan');
  });
  await scenario(scenarioNames[2],async()=>{
    phase='dirty_sibling_and_invalid_date_tab_retention';await catalog().getByRole('button',{name:'New document',exact:true}).click();
    await countPanels(3);await value('Write status','Rows loaded: 0');await idle();
    await commitInput('Number (blank for automatic)','D2');await commitInput('Note','Sibling draft');sibling=appState.active;
    await switchOrder(0);const before=rpc;
    await field('Order date and time').fill('2024-02-30T02:30:00');await blockedIntents();
    await action('Close form').click();await idle();assert.equal(rpc,before,'invalid_close_sent_rpc');
    await switchOrder(1);await value('Note','Sibling draft');await switchOrder(0);
    await value('Order date and time','2024-02-30T02:30:00');assert.equal(rpc,before,'tab_switch_submitted_draft');
    phase='invalid_date_evidence';await captureEvidence(screenshots[2],['Order date and time','DeliveryDate, row 1']);
    const dates=countEvent('change','DateInput');await commitInput('Order date and time','2024-03-10T02:30:01');
    assert.equal(countEvent('change','DateInput'),dates+1,'corrected_date_sent_twice');
    phase='isolated_negative_quantity_preflight';const negative=rpc;
    await field('Quantity, row 1').fill('-1');await blockedIntents();await value('Quantity, row 1','-1');assert.equal(rpc,negative);
    await field('Quantity, row 1').fill('3.25');await field('Quantity, row 1').press('Enter');await idle();assert.equal(rpc,negative);
    phase='isolated_quantity_scale_preflight';await field('Quantity, row 1').fill('3.251');await blockedIntents();await value('Quantity, row 1','3.251');
    const quantities=countEvent('cell','LinesTable','Quantity');await commitInput('Quantity, row 1','4.5000');await value('Quantity, row 1','4.50');
    assert.equal(countEvent('cell','LinesTable','Quantity'),quantities+1,'corrected_quantity_sent_twice');
    phase='isolated_note_length_preflight';await field('Note').fill('n'.repeat(81));assert.equal((await field('Note').inputValue()).length,81,'note_silently_truncated');
    await blockedIntents();await switchOrder(1);await value('Note','Sibling draft');await switchOrder(0);await value('Note','n'.repeat(81));
    const notes=countEvent('change','NoteInput');await commitInput('Note','Corrected order');assert.equal(countEvent('change','NoteInput'),notes+1,'corrected_note_sent_twice');
    assert.deepEqual(referenceValue(firstOrder,'CategoryInput'),firstCategory,'header_reference_changed_by_scalar_input');
    const grid=snapshots.get(firstOrder).items.find(item=>item.name==='LinesTable');
    assert.deepEqual(grid.rows[0].values[grid.columns.findIndex(column=>column.name==='Product')],firstProduct,'line_reference_changed_by_scalar_input');
    assert.equal(rpc,plannedRPC[0]+plannedRPC[1]+plannedRPC[2],'invalid_draft_rpc_plan');
  });
  await scenario(scenarioNames[3],async()=>{
    phase='held_write_prepare';
    let entered,release;const holding=new Promise(resolve=>entered=resolve),released=new Promise(resolve=>release=resolve);
    const diagnostic={requestAdmitted:false,bodyAccepted:false,replyHeld:false,releaseRequested:false,
      deliveryCompleted:false,responseMatched:false,status:'not_received'};report.heldDiagnostic=diagnostic;
    const gate={session:firstOrder,control:'WriteButton',entered,released,diagnostic};delayedWrite=gate;
    const before=countEvent('command','WriteButton');
    const write=await action('Write document').elementHandle(),ownerClose=await action('Close form').elementHandle();
    const reply=replyFor(packet=>{
      if(!matchesSave(packet,gate))return false;
      diagnostic.responseMatched=true;return true;
    });reply.catch(()=>{});
    phase='held_write_wait_for_reply';
    try{
      await write.evaluate(control=>{control.click();control.click();});await bounded(holding,remaining(rpcReplyMs),'held_reply_not_ready');
      const admitted=rpc;
      phase='held_write_navigate_sibling';
      // Navigation is synchronous. Native clicks preserve disabled/inert state
      // and do not spend the five-second hold awaiting Playwright actionability.
      await tabs().getByRole('button',{name:'Non-posting order',exact:true}).nth(1).evaluate(control=>control.click());
      assert.equal(await field('Number (blank for automatic)').inputValue(),'D2','held_sibling_not_visible');
      phase='held_write_attempt_late_close';
      await page.getByRole('button',{name:'Close application',exact:true,includeHidden:true}).evaluate(control=>control.click());
      assert.equal(await ownerClose.evaluate(control=>control.disabled),true,'held_owner_close_not_disabled');
      await ownerClose.evaluate(control=>control.click());
      assert.equal(rpc,admitted,'late_close_sent_work');assert.equal(await panels().count(),3,'late_close_removed_owner');
    }finally{diagnostic.releaseRequested=true;release();}
    phase='held_write_receive_reply';await reply;await idle();
    phase='held_write_verify_sibling';await value('Number (blank for automatic)','D2');await value('Note','Sibling draft');
    assert.equal(countEvent('command','WriteButton'),before+1,'double_write_replayed');
    assert.equal(snapshots.get(firstOrder)?.items.find(item=>item.name==='StatusLabel')?.value?.value,'saved','held_write_not_saved');
    assert.equal(typed(sibling,'NoteInput')?.value,'Sibling draft','late_reply_changed_sibling');
    await write.dispose();await ownerClose.dispose();
    phase='dirty_sibling_before_close';
    const refusal=replyFor(packet=>packet.method==='application.form'&&packet.params.session===sibling&&
      packet.params.request.params?.event==='close');await action('Close form').click();await refusal;await idle();
    assert.equal(await panels().count(),3,'dirty_sibling_closed');await value('Note','Sibling draft');
    phase='dirty_sibling_evidence';
    await captureEvidence(screenshots[3],['Note']);
    phase='sibling_write_saved';await writeDocument();
    phase='sibling_close_saved';await closeForm(2);
    phase='original_close_saved';await switchOrder(0);await closeForm(1);
    phase='welcome_close_saved';await closeForm(0);
    phase='final_ordinary_shutdown';await ordinaryShutdown();
    phase='final_independent_datetime_and_sibling_audit';fixture('final');
    assert.equal(rpc,plannedRPC.reduce((sum,value)=>sum+value,0),'total_rpc_plan');
    report.acceptance={typedCatalogDateTime:true,typedEmptySaved:true,typedDocumentDateTime:true,typedLineDateTime:true,
      exactQuantity:'4.50',exactPrice:'8.50',independentReadOnlyAudit:true,restartReopen:true,
      isolatedInvalidDrafts:true,tabRetainedRawInput:true,correctionsAppliedOnce:true,referencesPreserved:true,
      dirtySiblingRetained:true,realHeldReply:true,repeatedWriteNotReplayed:true,lateReplyDoesNotNavigate:true,
      ordinaryOwnedShutdown:true,posting:false,nativeScalarEditorParity:false};
  });
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','source_changed');
  assert.deepEqual(await sourceBinding(),report.binding,'source_binding_changed');
  assert.deepEqual(results.map(row=>row.name),scenarioNames,'incomplete_scenarios');
  assert.equal(wireFailure,false,'wire_contract_failed');
  report.status='PASS';report.rpcRequests=rpc;
}
// Hard work limit plus a separate 20-second cleanup reserve. No security changes.
const deadline=setTimeout(abort,Math.max(0,workDeadline-performance.now()));
const totalTimer=setTimeout(()=>{abort();process.exit(1);},Math.max(0,totalDeadline-performance.now()));
try{await main();check();}
catch(error){
  failed=true;report.status='FAIL';
  // Fixed, bounded flags/counts only. Never record DOM text, field contents,
  // response bodies, exception strings, database identifiers or capability URLs.
  report.rpcRequests=rpc;
  if(phase==='sandbox_launch'&&report.launch)report.launch.failure=launchFailureCode(error);
  report.failure={phase,code:stepFailureCode(error),reason:wireFailure?'wire_contract':aborted?'deadline_or_rpc_budget':phase==='sandbox_launch'&&
    /Operation not permitted|No usable sandbox|Failed to move to new namespace/i.test(String(error?.message))?'sandbox_start_denied':'step_failed'};
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
      report.elapsedMs=performance.now()-startedAt;
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
