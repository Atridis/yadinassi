/** Four owned reference-application flows. Real Chromium/SQLite; no native parity claim. */
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
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
const screenshots=['reference-product.png','reference-document.png','reference-resumed.png','reference-independent.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['catalog_choose_filter_cancel_clear_save','document_typed_choices_durable_restart',
  'retained_picker_reload_dirty_sibling','repeated_apply_late_navigation_owned_shutdown'];
const plannedRPC=[20,23,14,10]; // 67 business RPCs; attachment heartbeats have a separate bound.
const tokens=[],results=[];
const report={status:'FAIL',sourceCommit:null,scenarios:results,sandbox:null};
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
  const args=['-m','yadinassi.ui.configuration_app',path.join(repo,'examples/configuration-reference-application'),
    '--reference-application','--f',path.join(owned,'references.sqlite')];
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
  assert.ok(['create','empty','first','final'].includes(mode),'fixture_mode');
  const script=`from contextlib import closing
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
  for code,title in [('C1','Category One'),('C2','Category Two')]:
   item=catalogs.get_index('Categories').create_item()
   item.set_member('Code',code); item.set_member('Description',title); item.write()
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
  assert set(categories)=={'C1','C2'} and set(products)=={'P1','P2'}
  product=products['P2']; category=product.values[-1]
  assert product.description=='Reference product' and product.values[0]==Decimal('7.25')
  assert type(category) is CatalogKey and category.catalog_id==schemas['Categories'].identity
  assert category.database_id==product.key.database_id
  if mode=='empty': assert category.record_id.int==0
  else:
   assert category==categories['C1'].key
   with closing(backend.begin_document_read()) as view:
    schema,=view.documents(); orders={c.number:c for c in view.select_documents(schema.identity,DocumentSelection(limit=3))}
   assert set(orders)==({'D1','D2'} if mode=='final' else {'D1'})
   first=orders['D1']; rows=first.tabular_sections[0].rows
   assert first.values==('Reference order',categories['C2' if mode=='final' else 'C1'].key)
   assert len(rows)==1 and rows[0].values==(products['P2'].key,'Reference line',Decimal('3.25'),True)
   assert type(rows[0].values[0]) is CatalogKey and rows[0].values[0].catalog_id==schemas['Products'].identity
   assert type(rows[0].values[2]) is Decimal and type(rows[0].values[3]) is bool
   if mode=='final':
    sibling=orders['D2']; empty=sibling.values[-1]
    assert sibling.values[0]=='Sibling draft' and not sibling.tabular_sections[0].rows
    assert type(empty) is CatalogKey and empty.catalog_id==schemas['Categories'].identity and empty.record_id.int==0
 assert sha256(target.read_bytes()).digest()==before
print('REFERENCE_FIXTURE_OK')
`;
  const raw=execFileSync(python,['-c',script,path.join(repo,'examples/configuration-reference-application'),path.join(owned,'references.sqlite'),mode],
    {cwd:repo,env,encoding:'utf8',timeout:remaining(15000),maxBuffer:128,stdio:['ignore','pipe','ignore']});
  assert.equal(raw.trim(),'REFERENCE_FIXTURE_OK','independent_typed_readback');
}
let delayedApply=null;
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
// Commit each draft through the real form lifecycle before the next intent.
// Reload assertions concern authoritative dirty data, not unsent local input.
async function commitInput(name,text){
  await field(name).fill(text);await field(name).press('Enter');await idle();
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
        if(event.event==='cell')assert.ok(['Label','Quantity','Checked'].includes(event.column),'declared_column');
      }
      if(event.event==='change'||event.event==='cell'){
        exactKeys(event.value,'type value');assert.ok(['String','Number','Boolean'].includes(event.value.type),'scalar_only');
        assert.ok(['string','boolean'].includes(typeof event.value.value),'scalar_value_only');
      }
      wireEvents.push({session:packet.params.session,event:event.event,control:event.control});
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
    'examples/configuration-reference-application','tests/browser_ui',
    'tests/test_configuration_reference_profile.py','tests/test_configuration_reference_app.py',
    'tests/test_configuration_reference_browser_qa_contract.py','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  for(const required of ['yadinassi/configuration_reference_profile.py','yadinassi/configuration_references.py',
    'yadinassi/configuration_reference_choice.py','yadinassi/form_references.py',
    'yadinassi/ui/configuration_app.py','frontend/form/src/attachment.mjs','frontend/configuration/src/app.mjs',
    'examples/configuration-reference-application/Configuration.xml',
    'tests/browser_ui/configuration_reference_browser_qa.mjs','tests/test_configuration_reference_browser_qa_contract.py'])
    assert.ok(names.includes(required),'required_source_not_tracked');
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
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
      exactKeys(value,'name title type readOnly');
      assert.ok(typeof value.name==='string'&&value.name.length>0&&value.name.length<=128,'column_name');
      assert.ok(typeof value.title==='string'&&value.title.length<=1024,'column_title');
      assert.ok(['String','Number','Boolean','Date','FormCatalogRef'].includes(value.type),'column_type');
      assert.equal(typeof value.readOnly,'boolean','column_readonly');
      return;
    }
    assert.equal(context,'value','reference_context');
    if(!value||typeof value!=='object')return;
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
  output=path.join(temporary,'yadinassi-configuration-reference-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'ya-cr-'));
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
      let wireStage='attachment_request';
      try{
        assert.ok(++attachmentRequests<=96,'attachment_budget');
        const request=route.request(),body=request.postDataJSON();
        if(body.action==='attach'){exactKeys(body,'action instance');assert.match(body.instance,/^[0-9a-f]{32}$/);}
        else{exactKeys(body,'action generation pending');assert.ok(['status','heartbeat','detach','takeover'].includes(body.action));assert.ok(Number.isSafeInteger(body.generation)&&body.generation>=0);assert.equal(typeof body.pending,'boolean');}
        wireStage='attachment_response';
        const response=await route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0});
        const bytes=await response.body();assert.ok(bytes.length<=8192,'attachment_reply_budget');
        const value=JSON.parse(bytes.toString('utf8'));
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
        wireStage='attachment_delivery';return await route.fulfill({response});
      }catch{if(host&&host.exitCode===null&&!aborted){report.wireStage??=wireStage;wireFailure=true;abort();}return route.abort().catch(()=>{});}
    }
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=100){abort();return route.abort().catch(()=>{});}
      rpc++;
      let wireStage='request_schema';
      try{
        const packet=checkRequest(route.request());
        wireStage='http_status';
        const response=await route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0});
        assert.equal(response.status(),200,'rpc_status');
        wireStage='reply_budget';
        const bytes=await response.body();assert.ok(bytes.length<=131072,'rpc_reply_budget');
        assert.ok(!/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/i.test(bytes.toString('utf8')),'persistent_uuid_in_reply');
        wireStage='reply_json';const result=JSON.parse(bytes.toString('utf8'));
        // Delay only delivery of an already completed real reply. Never invent
        // a reply or repeat a request to make the late-navigation scenario pass.
        if(delayedApply&&packet.method==='application.reference'&&packet.params.action.action==='apply'){
          wireStage='held_apply';const gate=delayedApply;delayedApply=null;gate.entered();
          await bounded(gate.released,remaining(5000),'held_apply_timeout');
        }
        checkReply(result,packet,stage=>{wireStage=stage;});
        wireStage='delivery';return await route.fulfill({response});
      }catch{report.wireStage??=wireStage;wireFailure=true;abort();return route.abort().catch(()=>{});}
    }
    return route.continue();
  });
  page=await context.newPage();
  const picker=()=>page.getByRole('dialog');
  const writer=()=>page.waitForFunction(()=>{
    const banner=document.querySelector('.browser-ownership');
    return banner?.dataset.role==='writer'&&banner.nextElementSibling?.inert===false;
  },null,{timeout:remaining(10000)});
  const replyFor=predicate=>page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.status()===200&&predicate(response.request().postDataJSON()),{timeout:remaining(10000)});
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
  const cancel=async()=>{const reply=refReply('cancel');await picker().getByRole('button',{name:'Cancel selection',exact:true}).click();await reply;await picker().waitFor({state:'hidden'});await idle();};
  const select=async(label,code,title)=>{await begin(label);await filter(code);await apply(code,title);};
  const save=async(name,control,status)=>{
    const reply=replyFor(packet=>packet.params?.request?.params?.control===control);
    await action(name).click();await reply;await value(status,'saved');await idle();
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
  const countRef=kind=>wireEvents.filter(event=>event.event==='reference'&&event.action===kind).length;
  let firstOrder,firstCategory,retainedChoice;
  await scenario(scenarioNames[0],async()=>{
    phase='fresh_reference_database';fixture('create');await startHost();await page.goto(url);await writer();await countPanels(1);await idle();
    assert.deepEqual(appState.messages,['Calculated in the owned server process','8'],'startup_servercall');
    await action('New product').click();await countPanels(2);await value('Save status','');await idle();
    await commitInput('Product code','P2');await commitInput('Product title','Reference product');await commitInput('Unit price','7.25');
    await select('Category','C1','Category One');await value('Category','Category One');
    assert.equal(await field('Category').isEditable(),false,'reference_text_editable');
    const owner=appState.active,before=structuredClone(referenceValue(owner,'CategoryInput'));
    await begin('Category');await filter('NONE');await picker().getByText('No matching records.',{exact:true}).waitFor();
    await cancel();assert.deepEqual(referenceValue(owner,'CategoryInput'),before,'cancel_changed_reference');
    const cleared=refReply('clear');await action('Clear Category').click();await cleared;await idle();await value('Category','');
    assert.equal(referenceValue(owner,'CategoryInput').key,null,'clear_not_typed_empty');
    await saveProduct();fixture('empty'); // Independent read-only CLI confirms the saved typed empty.
    await select('Category','C1','Category One');await saveProduct();await screenshot(screenshots[0]);
    await closeForm(1);
    assert.equal(rpc,plannedRPC[0],'catalog_rpc_plan');
  });
  await scenario(scenarioNames[1],async()=>{
    phase='document_header_and_line_choices';await action('New order').click();await countPanels(2);await value('Write status','Rows loaded: 0');await idle();
    await commitInput('Number (blank for automatic)','D1');await commitInput('Note','Reference order');
    await select('Category','C1','Category One');await action('Add line').click();await rowCount(1);await idle();
    await select('Product, row 1','P2','Reference product');await value('Product, row 1','Reference product');
    assert.equal(await field('Product, row 1').isEditable(),false);
    await commitInput('Label, row 1','Reference line');await commitInput('Quantity, row 1','3.25');
    await field('Checked, row 1').check();await idle();await writeDocument();
    await closeForm(1);await closeForm(0);await ordinaryShutdown();
    phase='independent_typed_sqlite_readback';fixture('first');
    await page.close();page=await context.newPage();await startHost();await page.goto(url);await writer();await countPanels(1);await idle();
    await entries().getByRole('button',{name:'Non-posting order',exact:true}).click();await openNumber('D1');
    await value('Category','Category One');await value('Product, row 1','Reference product');await value('Quantity, row 1','3.25');
    assert.equal(await field('Checked, row 1').isChecked(),true);firstOrder=appState.active;
    firstCategory=structuredClone(referenceValue(firstOrder,'CategoryInput'));
    await screenshot(screenshots[1]);
    assert.equal(rpc,plannedRPC[0]+plannedRPC[1],'restart_rpc_plan');
  });
  await scenario(scenarioNames[2],async()=>{
    phase='retained_authoritative_sibling';await catalog().getByRole('button',{name:'New document',exact:true}).click();await countPanels(3);await value('Write status','Rows loaded: 0');await idle();
    await commitInput('Number (blank for automatic)','D2');await commitInput('Note','Sibling draft');
    await switchOrder(0);await begin('Category');retainedChoice=structuredClone(appState.choice);
    phase='retained_picker_snapshot';await button('Check connection').click();await writer();await idle();
    assert.deepEqual(appState.choice,retainedChoice,'snapshot_lost_picker');
    phase='retained_picker_real_reload';page.once('dialog',dialog=>dialog.accept());await page.reload();await writer();await countPanels(3);await idle();
    await picker().waitFor();assert.deepEqual(appState.choice,retainedChoice,'reload_retargeted_picker');
    assert.deepEqual(referenceValue(firstOrder,'CategoryInput'),firstCategory,'reload_changed_owner');
    await page.setViewportSize({width:390,height:844});await screenshot(screenshots[2]);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'narrow_overflow');
    await cancel();await switchOrder(0);await value('Category','Category One');
    assert.deepEqual(referenceValue(firstOrder,'CategoryInput'),firstCategory,'reload_cancel_cleared_reference');
    await switchOrder(1);await value('Note','Sibling draft');
    const sibling=appState.sessions.filter(session=>session.title==='Non-posting order')[1].id;
    assert.equal(snapshots.get(sibling).dirty,true,'sibling_dirty_lost');
    assert.equal(rpc,plannedRPC[0]+plannedRPC[1]+plannedRPC[2],'retained_rpc_plan');
  });
  await scenario(scenarioNames[3],async()=>{
    await page.setViewportSize({width:1100,height:850});await switchOrder(0);await begin('Category');await filter('C2');
    const stale=await picker().getByRole('button',{name:'Choose C2 Category Two',exact:true}).elementHandle();
    let entered,release;const holding=new Promise(resolve=>entered=resolve),released=new Promise(resolve=>release=resolve);
    delayedApply={entered,released};const before=countRef('apply');
    phase='repeated_apply_and_late_navigation';
    try{
      await stale.evaluate(control=>{control.click();control.click();});await bounded(holding,remaining(10000),'apply_not_admitted');
      const admitted=rpc;
      // Attempt ordinary late clicks while the real completed reply is held.
      await page.getByRole('navigation',{name:'Open forms',exact:true,includeHidden:true})
        .getByRole('button',{name:'Non-posting order',exact:true,includeHidden:true}).nth(1).evaluate(control=>control.click());
      await page.getByRole('button',{name:'Close application',exact:true,includeHidden:true}).evaluate(control=>control.click());
      await active().getByRole('button',{name:'Close form',exact:true,includeHidden:true}).evaluate(control=>control.click());
      assert.equal(rpc,admitted,'late_navigation_sent_work');await value('Number (blank for automatic)','D1');
    }finally{release();}
    await picker().waitFor({state:'hidden'});await idle();await value('Category','Category Two');
    assert.equal(countRef('apply'),before+1,'repeated_apply_sent_twice');await writeDocument();
    await switchOrder(1);await value('Note','Sibling draft');await value('Category','');
    const retired=rpc;await stale.evaluate(control=>control.click());await stale.dispose();
    assert.equal(rpc,retired,'retired_choice_retargeted_sibling');
    const refusal=replyFor(packet=>packet.params?.request?.params?.event==='close');
    await action('Close form').click();await refusal;await idle();assert.equal(await panels().count(),3,'dirty_sibling_closed');
    await value('Note','Sibling draft');await screenshot(screenshots[3]);
    await writeDocument();await closeForm(2);await closeForm(1);await closeForm(0);await ordinaryShutdown();
    phase='final_independent_readback';fixture('final');
    assert.equal(rpc,plannedRPC.reduce((sum,value)=>sum+value,0),'total_rpc_plan');
    report.acceptance={typedCatalogReference:true,typedEmptySaved:true,typedDocumentHeader:true,typedLineReference:true,
      exactQuantity:'3.25',exactPrice:'7.25',independentReadOnlyAudit:true,restartReopen:true,retainedPicker:true,
      dirtySiblingRetained:true,cancelPreservesReference:true,repeatedApplyNotReplayed:true,lateNavigationFenced:true,
      ordinaryOwnedShutdown:true,posting:false,nativeChoiceEventParity:false};
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
  report.failure={phase,reason:wireFailure?'wire_contract':aborted?'deadline_or_rpc_budget':phase==='sandbox_launch'&&
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
