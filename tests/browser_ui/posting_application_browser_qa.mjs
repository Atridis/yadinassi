/** Opt-in source-bound posting browser acquisition. No native StandardCommand parity claim. */
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
const workDeadline=startedAt+220000;
const totalDeadline=startedAt+240000;
const rpcFetchMs=35000,rpcReplyMs=50000; // Existing transport and observer budgets; global deadline unchanged.
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
const screenshots=['posting-cycle.png','posting-isolation.png','posting-cancelled.png','posting-reopened.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['typed_write_post_undo_sql_readback','repeat_late_navigation_dirty_sibling_close_fence',
 'source_cancellation_atomicity','persisted_reopen_natural_shutdown'];
// Business RPC plan excludes only form/application hello and snapshot reads.
const businessPlan=[
 ['catalog','open','change:NumberInput','change:NoteInput','change:DateLabel','command:NewLineButton','cell:LinesTable','cell:LinesTable','cell:LinesTable','command:WriteButton','command:PostButton','command:UndoButton'],
 ['open','change:NumberInput','change:MovementKeyInput','change:NoteInput','change:NoteInput','command:WriteButton','close:','openRecord','close:','command:WriteButton','close:'],
 ['change:NoteInput','command:PostButton','change:NoteInput','command:WriteButton','close:'],
 ['close','catalog','openRecord','close:','close']
];
const businessEvents=[];
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
  const args=['-m','yadinassi.ui.configuration_app',path.join(repo,'examples/configuration-posting-application'),
    '--posting-application','--f',path.join(owned,'documents.sqlite')];
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
// Independent read-only SQL, never the UI projection or replay of posting handlers.
const fixtureCode=String.raw`
import json,sqlite3,sys
from pathlib import Path
from contextlib import closing
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.configuration_posting_application import import_posting_application, PROFILE
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
root=Path(sys.argv[2]); source=Path(sys.argv[3]); database=root/'documents.sqlite'
try:
 if sys.argv[1]=='create':
  config=import_posting_application(read_configuration_directory(source),posting_runtime=PROFILE)
  SQLiteCatalogBackend.create_posting(database,config).close()
  result={'created':True}
 else:
  with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
   db.execute('PRAGMA query_only=ON')
   result={'documents':db.execute('SELECT number,revision,date,values_json,sections_json FROM document_record ORDER BY number').fetchall(),
    'posted':db.execute('SELECT r.number,COALESCE(p.posted,0) FROM document_record r LEFT JOIN document_posting_state p USING(document_id,record_id) ORDER BY number').fetchall(),
    'movements':db.execute('SELECT r.number,m.line_number,m.active,m.values_json FROM recorder_movement m JOIN document_record r USING(document_id,record_id) ORDER BY r.number,m.line_number').fetchall()}
 print(json.dumps(result))
except Exception:
 print('{"error":"owned_posting_fixture_failed"}',file=sys.stderr);sys.exit(1)
`;
function documentFixture(operation){
  const raw=execFileSync(python,['-c',fixtureCode,operation,owned,path.join(repo,'examples/configuration-posting-application')],
    {cwd:repo,env,encoding:'utf8',timeout:remaining(10000),maxBuffer:16384,stdio:['ignore','pipe','ignore']});
  return JSON.parse(raw);
}
const replyFor=predicate=>page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.status()===200&&predicate(response.request().postDataJSON()),{timeout:remaining(rpcReplyMs)});
const formReply=(event,control)=>replyFor(packet=>packet.method==='application.form'&&packet.params.request.method==='form.event'&&packet.params.request.params.event===event&&(!control||packet.params.request.params.control===control));
let lastApplicationState=null;
async function command(title,control,state='saved'){
 // DOM panel insertion order follows the source-bound application sessions.
 // Pin the active opaque session before dispatch, never accept a saved sibling.
 const index=await panels().evaluateAll(nodes=>nodes.findIndex(node=>!node.hidden));
 assert.equal(lastApplicationState?.sessions.length,await panels().count(),'session_panel_binding');
 const session=lastApplicationState?.sessions[index]?.id;
 assert.match(session||'',/^form-[1-9][0-9]*$/,'active_session_missing');
 const reply=replyFor(packet=>packet.method==='application.form'&&packet.params.session===session&&
   packet.params.request.method==='form.event'&&packet.params.request.params.event==='command'&&
   packet.params.request.params.control===control);
 await action(title).click();const data=await (await reply).json();
 assert.equal(data.result.session,session,'command_session_changed');
 const outcomes=data.result.state.posting.filter(item=>item.session===session);
 assert.equal(outcomes.length,1,'command_outcome_count');
 assert.equal(outcomes[0].state,state,'posting_outcome');await idle();
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
// Price draft uncommitted where the scenario deliberately tests checkbox/tab.
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
  const packet=JSON.parse(raw);exactKeys(packet,'jsonrpc id method params');
  assert.equal(packet.jsonrpc,'2.0');assert.ok(Number.isSafeInteger(packet.id)&&packet.id>0);
  if(packet.method==='application.hello'){
    exactKeys(packet.params,'protocol dialogCapability inputCapability');assert.equal(packet.params.inputCapability,'yadinassi-owned-input/1');assert.equal(packet.params.protocol,'yadinassi-configuration-app/3');
    assert.equal(packet.params.dialogCapability,'yadinassi-owned-dialog/1');
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
        exactKeys(event.value,event.value.type==='Date'?'type ticks':'type value');assert.ok(['String','Number','Boolean','Date'].includes(event.value.type),'scalar_only');
        if(event.value.type==='Date')assert.match(event.value.ticks,/^[0-9]{1,18}$/,'typed_date');
        else assert.ok(['string','boolean'].includes(typeof event.value.value),'scalar_value_only');
      }
      wireEvents.push({session:packet.params.session,event:event.event,control:event.control});
    }
  }
  if(['application.catalog','application.open','application.openRecord','application.close'].includes(packet.method))
    businessEvents.push(packet.method.slice('application.'.length));
  else if(packet.method==='application.form'&&packet.params.request.method==='form.event'){
    const event=packet.params.request.params;businessEvents.push(event.event+':'+(event.control||''));
  }
  return packet;
}
async function auditResponse(response){
  assert.equal(response.status(),200,'rpc_status');
  const body=await response.body();assert.ok(body.length<=262144,'reply_budget');
  const text=body.toString('utf8');const decoded=JSON.parse(text);
  lastApplicationState=decoded.result?.state;
  assert.ok(!/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(text),'persistent_uuid_leak');
  for(const key of ['operation_id','database_id','record_id','expected_revision','expanded_requests','source_files'])
    assert.ok(!text.includes('"'+key+'"'),'private_host_envelope_leak');
}
async function repeatClick(locator){await locator.evaluate(control=>{control.click();control.click();});}
async function scenario(name,fn){
 check();phase=name;const start=businessEvents.length,index=scenarioNames.indexOf(name);
 await fn();check();assert.deepEqual(businessEvents.slice(start),businessPlan[index],'business_rpc_plan_changed');
 results.push({name,status:'PASS',businessRpc:businessEvents.length-start});
}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:Object.keys(sessionStorage)})),{local:0,session:['yadinassi.browser.resume/1']},'only_resume_storage');
  assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/configuration','examples/configuration-posting-application','tests/browser_ui',
    'tests/test_configuration_posting_app.py','tests/test_configuration_posting_application.py','tests/test_document_posting_host.py','docs/posting-application-browser-qa.md',
    'tests/test_posting_application_browser_qa_contract.py','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-posting-browser-artifacts');
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
      if(rpc>=180){abort();return route.abort().catch(()=>{});}
      rpc++;
      try{
        checkRequest(route.request());
        const packet=route.request().postDataJSON();
        if(delayed&&packet.method==='application.openRecord'){
          const gate=delayed;delayed=null;
          const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
          await auditResponse(response);gate.arrived();await bounded(gate.wait,remaining(10000),'late_reply_gate_timeout');
          return await route.fulfill({response});
        }
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        await auditResponse(response);return await route.fulfill({response});
      }catch{wireFailure=true;abort();return route.abort().catch(()=>{});}
    }
    return route.continue();
  });
  page=await context.newPage();
  const writer=()=>page.waitForFunction(()=>document.querySelector('.browser-ownership')?.dataset.role==='writer',null,{timeout:remaining(10000)});
  const grid=()=>active().locator('table');
  const rowCount=n=>page.waitForFunction(expected=>document.querySelectorAll('.configuration-form-panels > section:not([hidden]) table tbody tr').length===expected,n,{timeout:remaining(10000)});
  const newDocument=async()=>{
    const reply=replyFor(packet=>packet.method==='application.open');
    await catalog().getByRole('button',{name:'New document',exact:true}).click();await reply;await idle();
  };
  const selectNumber=async number=>{
    const row=catalog().locator('tbody tr').filter({has:page.getByRole('cell',{name:number,exact:true})});
    await row.getByRole('checkbox').check();
  };
  const openNumber=async number=>{
    await selectNumber(number);const reply=replyFor(packet=>packet.method==='application.openRecord');
    await catalog().getByRole('button',{name:'Open selected',exact:true}).click();await reply;
    await value('Number (blank for automatic)',number);await idle();
  };
  const addLine=async()=>{const reply=formReply('command','NewLineButton');await action('Add line').click();await reply;await idle();};
  await scenario(scenarioNames[0],async()=>{
    phase='typed_write_post_undo';assert.deepEqual(documentFixture('create'),{created:true});
    await startHost();await page.goto(url);await writer();
    await entries().getByRole('button',{name:'Posting order',exact:true}).click();
    await catalog().getByRole('columnheader',{name:'Posted',exact:true}).waitFor();
    await newDocument();await countPanels(1);
    await commitInput('Number (blank for automatic)','D1');await commitInput('Note','Typed order');
    await commitInput('Date and time','2024-02-29T23:45:17');
    await addLine();await rowCount(1);await commitInput('Label, row 1','First');await commitInput('Quantity, row 1','2.50');
    const checked=formReply('cell');await field('Checked, row 1').check();await checked;await idle();
    await command('Write document','WriteButton');
    let db=documentFixture('audit');assert.deepEqual(db.posted,[['D1',0]]);assert.deepEqual(db.movements,[]);
    assert.equal(db.documents[0][2],'20240229234517');
    assert.deepEqual(JSON.parse(db.documents[0][3]),[['s','Typed order'],['n','1']]);
    const sections=JSON.parse(db.documents[0][4]);assert.equal(sections.length,1);assert.equal(sections[0][1].length,1);
    assert.deepEqual(sections[0][1][0][1],[['s','First'],['n','2.50'],['b',true]]);
    await command('Post document','PostButton');db=documentFixture('audit');
    assert.deepEqual(db.posted,[['D1',1]]);assert.equal(db.movements.length,1);
    assert.deepEqual(db.movements[0].slice(0,3),['D1',1,1]);
    assert.deepEqual(JSON.parse(db.movements[0][3]),[['n','1001'],['n','2.50']]);
    await catalog().getByRole('cell',{name:'Posted',exact:true}).waitFor();
    await command('Undo posting','UndoButton');db=documentFixture('audit');
    assert.deepEqual(db.posted,[['D1',0]]);assert.deepEqual(db.movements,[]);
    await catalog().getByRole('cell',{name:'Not posted',exact:true}).waitFor();await screenshot(screenshots[0]);
  });
  await scenario(scenarioNames[1],async()=>{
    phase='dirty_sibling_repeat_late_navigation';await newDocument();await countPanels(2);
    await commitInput('Number (blank for automatic)','D2');await commitInput('Movement key','2');await commitInput('Note','Sibling draft');
    await tabs().getByRole('button',{name:'Posting order',exact:true}).nth(0).click();
    await commitInput('Note','Updated first');
    const before=documentFixture('audit').documents[0][1],reply=formReply('command','WriteButton');
    const writesBefore=businessEvents.filter(event=>event==='command:WriteButton').length;
    await repeatClick(action('Write document'));await reply;await idle();
    assert.equal(businessEvents.filter(event=>event==='command:WriteButton').length,writesBefore+1,'duplicate_write_rpc');
    assert.equal(documentFixture('audit').documents[0][1],before+1,'duplicate_write');
    await closeForm();await countPanels(1);await value('Note','Sibling draft');
    await selectNumber('D1');let arrived,release;
    const arrival=new Promise(resolve=>arrived=resolve),wait=new Promise(resolve=>release=resolve);
    const ownerIndex=await panels().evaluateAll(nodes=>nodes.findIndex(node=>!node.hidden));
    const retainedOwner=lastApplicationState.sessions[ownerIndex].id;
    const opensBefore=businessEvents.filter(event=>event==='openRecord').length;
    delayed={arrived,wait};
    await repeatClick(catalog().getByRole('button',{name:'Open selected',exact:true}));
    await bounded(arrival,remaining(10000),'late_open_not_observed');
    await tabs().getByRole('button',{name:'Posting order',exact:true}).click();release();
    await countPanels(2);await idle();await value('Note','Sibling draft');
    const ownerAfter=await panels().evaluateAll(nodes=>nodes.findIndex(node=>!node.hidden));
    assert.equal(lastApplicationState.sessions[ownerAfter].id,retainedOwner,'late_reply_changed_owner');
    assert.equal(businessEvents.filter(event=>event==='openRecord').length,opensBefore+1,'duplicate_open_rpc');
    const closeReply=formReply('close');await action('Close form').click();await closeReply;await idle();
    assert.equal(await panels().count(),2,'dirty_sibling_was_closed');
    assert.equal(documentFixture('audit').documents.length,1,'close_implicitly_saved');
    const retainedPanels=await panels().count(),beforeFence=businessEvents.length;
    await button('Close application').click();
    await page.getByText('Close each form, including hidden tabs, before closing the application.',{exact:true}).waitFor();
    await idle();assert.equal(await panels().count(),retainedPanels,'application_close_removed_panels');
    assert.equal(businessEvents.length,beforeFence,'local_close_fence_dispatched');
    await value('Note','Sibling draft');
    assert.equal(host.exitCode,null,'dirty_application_closed');
    await screenshot(screenshots[1]);await command('Write document','WriteButton');await closeForm();await countPanels(1);
  });
  await scenario(scenarioNames[2],async()=>{
    phase='source_cancel_atomicity';await value('Number (blank for automatic)','D1');
    const before=documentFixture('audit');await commitInput('Note','cancel');
    await command('Post document','PostButton','rejected');
    assert.deepEqual(documentFixture('audit'),before,'cancel_changed_persisted_state');
    await screenshot(screenshots[2]);await commitInput('Note','Updated first');
    await command('Write document','WriteButton');await closeForm();await countPanels(0);
  });
  await scenario(scenarioNames[3],async()=>{
    phase='natural_shutdown_and_persisted_reopen';const before=documentFixture('audit');
    await naturalStop();await page.close();page=await context.newPage();
    await startHost();await page.goto(url);await writer();
    await entries().getByRole('button',{name:'Posting order',exact:true}).click();await openNumber('D1');
    await value('Note','Updated first');await value('Quantity, row 1','2.50');
    assert.equal(await field('Checked, row 1').isChecked(),true);
    assert.deepEqual(documentFixture('audit'),before,'reopen_mutated_database');
    await screenshot(screenshots[3]);await closeForm();await countPanels(0);await naturalStop();
    assert.deepEqual(documentFixture('audit'),before,'shutdown_mutated_database');
    report.acceptance={explicitHostManifest:true,writePostUndo:true,independentSqlReadback:true,
      dirtySibling:true,lateNavigation:true,repeatedClick:true,cancellationAtomic:true,naturalShutdown:true,
      nativeStandardFormWrite:false,injectedUnknownCommit:false,restartReceiptRecovery:false};
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
