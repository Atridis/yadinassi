/** Opt-in owned configuration-form browser acquisition. No native-platform parity claim. */
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
const workDeadline=startedAt+420000;
const totalDeadline=startedAt+440000;
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
const screenshots=['application-startup.png','application-takeover-draft.png','application-resumed.png',
  'application-exit-refused.png','application-clean.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['shipped_startup_and_commonmodule_servercall',
  'two_tab_takeover_preserves_raw_draft_and_open_host',
  'resume_without_startup_replay_and_dropped_reply_not_retried',
  'real_grace_preserves_beforeexit_refusal','real_grace_closes_only_empty_clean_application'];
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
async function startHost(application){
  check();assert.ok(!host&&!hostGroup,'previous_host_live');
  assert.ok(['shipped','editable','refusal'].includes(application),'unknown_owned_application');
  const directory=await hostFixture(application);
  const args=['-m','yadinassi.ui.configuration_app',directory,'--application-host'];
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
async function hostFixture(kind){
  if(kind==='shipped')return path.join(repo,'examples/configuration-application-host');
  const base='examples/configuration-application-host/';
  const directory=path.join(owned,kind),hashes={};
  for(const name of git('ls-files','-z',base).split('\0').filter(Boolean)){
    assert.ok(name.startsWith(base),'fixture_scope');
    const stat=await lstat(path.join(repo,name));assert.ok(stat.isFile()&&!stat.isSymbolicLink(),'fixture_regular');
    let data=await readFile(path.join(repo,name),'utf8');
    if(kind==='editable'&&name===base+'CommonForms/Welcome/Ext/Form.xml'){
      assert.equal((data.match(/LabelField/g)||[]).length,2,'fixture_patch_identity');
      data=data.replaceAll('LabelField','InputField').replace('GreetingLabel','GreetingInput');
    }
    if(kind==='refusal'&&name===base+'Ext/ManagedApplicationModule.bsl'){
      assert.ok(!data.includes('BeforeExit'),'fixture_lifecycle_identity');
      data+='\nProcedure BeforeExit(Cancel, WarningText)\n Cancel = True; WarningText = "Close refused by application";\nEndProcedure\n';
    }
    const relative=name.slice(base.length),target=path.join(directory,relative);
    await mkdir(path.dirname(target),{recursive:true});await writeFile(target,data,{flag:'wx'});hashes[relative]=sha256(data);
  }
  report.fixtureBindings={...report.fixtureBindings,[kind]:hashes};
  return directory;
}
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
  await field(name).fill(text);await field(name).press('Enter');await idle();
}
const wireEvents=[];
let wireFailure=false;
let routeFailure=null;
let lifetimeStage=null;
const detachDiagnostics={pagehide:0,fetch:0,request:0,route:0,receipt:0,matched:0};
const exactKeys=(value,names)=>assert.deepEqual(Object.keys(value).sort(),names.split(' ').filter(Boolean).sort(),'wire_keys');
function checkRequest(request){
  const raw=request.postData();assert.ok(raw&&Buffer.byteLength(raw)<=65536,'wire_budget');
  const packet=JSON.parse(raw);exactKeys(packet,'jsonrpc id method params');
  assert.equal(packet.jsonrpc,'2.0');assert.ok(Number.isSafeInteger(packet.id)&&packet.id>0);
  if(packet.method==='application.hello'){
    exactKeys(packet.params,'protocol');assert.equal(packet.params.protocol,'yadinassi-configuration-app/3');
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
      const keys={command:'event revision control',close:'event revision',change:'event revision control value'};
      assert.ok(Object.hasOwn(keys,event.event),'wire_event');exactKeys(event,keys[event.event]);
      assert.ok(Number.isSafeInteger(event.revision)&&event.revision>=0,'wire_revision');
      if(event.event==='change'){
        exactKeys(event.value,'type value');assert.ok(['String','Number','Boolean'].includes(event.value.type),'scalar_only');
        assert.ok(['string','boolean'].includes(typeof event.value.value),'scalar_value_only');
      }
      wireEvents.push({session:packet.params.session,event:event.event,control:event.control});
    }
  }
  return packet;
}
async function repeatClick(locator){await locator.evaluate(control=>{control.click();control.click();});}
async function scenario(name,fn){check();phase=name;await fn();check();results.push({name,status:'PASS'});}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:Object.keys(sessionStorage)})),{local:0,session:['yadinassi.browser.resume/1']},'only_resume_storage');
  assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/configuration','examples/configuration-forms','examples/configuration-catalog-forms','examples/configuration-application-host','tests/browser_ui',
    'tests/test_configuration_forms.py','tests/test_configuration_catalog_forms.py','tests/test_configuration_catalog.py','tests/test_configuration_catalog_profile.py','tests/test_form_empty_date_state.py','tests/test_configuration_app.py','tests/test_configuration_browser_qa_contract.py',
    'tests/test_form_browser_qa_contract.py','tests/test_ui_browser_qa_contract.py','tests/test_application_host_browser_qa_contract.py','tests/test_configuration_host.py','tests/test_browser_session.py','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-application-host-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'ya-app-'));
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
  // Diagnostic observation only: call the original fetch unchanged and never dispatch lifecycle events.
  await context.addInitScript(()=>{
    addEventListener('pagehide',()=>console.debug('ya-qa-pagehide'));
    const original=globalThis.fetch;
    globalThis.fetch=function(input,options){
      if(input==='/attachment'&&typeof options?.body==='string'){
        try{if(JSON.parse(options.body).action==='detach')console.debug('ya-qa-detach-fetch');}catch{}
      }
      return Reflect.apply(original,this,arguments);
    };
  });
  let renewals=0;
  context.on('request',request=>{
    if(new URL(request.url()).pathname!=='/attachment')return;
    try{const action=request.postDataJSON()?.action;if(action==='detach')detachDiagnostics.request++;else if(['attach','heartbeat','status','takeover'].includes(action))renewals++;}catch{}
  });
  const replies=new WeakMap(),headers=new WeakMap(),detachReceipts=new Map(),applicationPages=new Set();let dropReply=false,dropped=0,commandRequests=0,attachmentRequests=0;
  await context.route('**/*',async route=>{
    const request=route.request(),target=request.url();
    let routeStage='request_admission';
    try{
    if(aborted||!applicationAllowedRequest(target))return route.abort();
    const pathname=new URL(target).pathname;
    if(pathname==='/attachment'){
      routeStage='attachment_validation';
      assert.ok(++attachmentRequests<=96,'attachment_request_budget');
      const body=request.postDataJSON();
      if(body.action==='detach')detachDiagnostics.route++;
      if(body.action==='attach'){exactKeys(body,'action instance');assert.match(body.instance,/^[0-9a-f]{32}$/);}
      else{exactKeys(body,'action generation pending');assert.ok(['status','heartbeat','detach','takeover'].includes(body.action));assert.ok(Number.isSafeInteger(body.generation)&&body.generation>=0);assert.equal(typeof body.pending,'boolean');}
      // Credentials are retained only for in-memory stale-writer proof, never artifacts.
      routeStage='attachment_exchange';
      const response=await route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0}),bytes=await response.body();assert.ok(bytes.length<=8192,'attachment_reply_budget');const value=JSON.parse(bytes.toString('utf8'));
      if(value.credential)tokens.push(value.credential);if(value.resume)tokens.push(value.resume);
      if(body.action==='detach'){
        detachDiagnostics.receipt++;
        const sent=request.headers(),key=sent['x-yadinassi-session'],expected=detachReceipts.get(key);
        if(expected){
          assert.equal(response.status(),200,'detach_http_accepted');
          assert.equal(value.protocol,'yadinassi-browser-attachment/1','detach_protocol');
          assert.equal(value.attachment,expected.attachment,'detach_attachment');
          assert.equal(value.role,'observer','detach_released_writer');
          assert.ok(Number.isSafeInteger(value.generation)&&value.generation>=body.generation,'detach_generation');
          detachDiagnostics.matched++;detachReceipts.delete(key);
        }
      }
      return route.fulfill({response});
    }
    if(pathname==='/rpc'){
      if(rpc>=100){abort();return route.abort().catch(()=>{});}rpc++;
      let packet;routeStage='rpc_validation';
      try{packet=checkRequest(request);}catch{routeFailure??=routeStage;wireFailure=true;abort();return route.abort().catch(()=>{});}
      const owner=request.frame().page();headers.set(owner,request.headers());
      const command=packet.method==='application.form'&&packet.params.request.method==='form.event'&&packet.params.request.params.event==='command';
      if(command)commandRequests++;
      routeStage=packet.method==='application.close'?'application_close_exchange':'rpc_exchange';
      const response=await route.fetch({timeout:remaining(15000),maxRedirects:0,maxRetries:0}),bytes=await response.body();assert.ok(bytes.length<=131072,'rpc_reply_budget');const reply=JSON.parse(bytes.toString('utf8'));
      if(response.status()===200)replies.set(owner,reply);
      if(dropReply&&command){dropReply=false;dropped++;return route.abort('failed');}
      return route.fulfill({response});
    }
    return await route.continue();
    }catch{if(host&&host.exitCode===null&&!aborted){routeFailure??=routeStage;wireFailure=true;abort();}return route.abort().catch(()=>{});}
  });
  const newPage=async()=>{const p=await context.newPage();applicationPages.add(p);p.on('dialog',dialog=>dialog.accept());
    p.on('console',message=>{if(message.type()!=='debug')return;
      if(message.text()==='ya-qa-pagehide')detachDiagnostics.pagehide++;
      else if(message.text()==='ya-qa-detach-fetch')detachDiagnostics.fetch++;
    });return p;};
  const ownership=(p,role)=>p.waitForFunction(expected=>document.querySelector('.browser-ownership')?.dataset.role===expected,role,{timeout:remaining(10000)});
  const state=p=>replies.get(p)?.result?.state;
  const openShipped=async(kind='shipped')=>{await startHost(kind);page=await newPage();await page.goto(url);await ownership(page,'writer');await countPanels(1);await idle();};
  const detach=async p=>{
    const sent=headers.get(p),key=sent?.['x-yadinassi-session'],attachment=sent?.['x-yadinassi-attachment'];
    assert.ok(key&&attachment,'detach_known_attachment');
    detachReceipts.set(key,{attachment});
    lifetimeStage='detach_navigation';await p.goto('about:blank');
    lifetimeStage='detach_page_close';await p.close();
    assert.equal(p.isClosed(),true,'actual_page_closed');lifetimeStage=null;
  };
  const realGrace=async()=>{
    assert.ok([...applicationPages].every(p=>p.isClosed()),'all_application_pages_closed');
    assert.equal(context.pages().length,0,'no_live_browser_pages');
    const before=Date.now(),renewalsBefore=renewals;
    lifetimeStage='real_lease_and_grace';
    // Advisory unload may never leave Chromium. Observe the documented 90s lease
    // plus 30s grace without probes, synthetic detach, renewal or clock changes.
    await bounded(new Promise(resolve=>setTimeout(resolve,122000)),remaining(124000),'real_lease_grace_timeout');
    assert.ok(Date.now()-before>=120000,'real_lease_grace_not_elapsed');
    assert.equal(renewals,renewalsBefore,'no_attachment_renewal_during_absence');
    assert.ok([...applicationPages].every(p=>p.isClosed()),'pages_remain_closed');
    detachReceipts.clear();lifetimeStage=null;
  };
  await scenario(scenarioNames[0],async()=>{
    await openShipped();await value('GreetingLabel','Hello from the configuration application');
    assert.deepEqual(state(page).messages,['Calculated in the owned server process','8'],'startup_servercall');
    await action('Open details').click();await countPanels(2);await idle();
    await value('MessageLabel','Hello from the configuration application');
    await tabs().getByRole('button',{name:'Welcome',exact:true}).click();
    assert.ok((await active().innerText()).includes('5'),'command_servercall');
    assert.equal(state(page).sessions.length,2,'commonmodule_openform');
    await screenshot(screenshots[0]);
    await action('Close form').click();await countPanels(1);await action('Close form').click();await countPanels(0);
    const closedReply=page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.request().postDataJSON()?.method==='application.close'&&response.status()===200,{timeout:remaining(10000)});
    await button('Close application').click();await closedReply;await idle();
    assert.equal(state(page).lifecycle,'closed','explicit_application_close_completed');
    await stopHost();await page.close();
  });
  await scenario(scenarioNames[1],async()=>{
    await openShipped('editable');const original=page;
    await field('GreetingInput').evaluate(control=>{control.value='unsent original-page draft';control.dispatchEvent(new Event('input',{bubbles:true}));});
    const before=commandRequests,oldHeaders={...headers.get(original)},initial=state(original),initialRevision=replies.get(original).result.form.result.state.revision;
    const second=await newPage();await second.goto(url);await ownership(second,'observer');
    await second.getByRole('button',{name:'Take control',exact:true}).click();await ownership(second,'writer');
    page=second;await countPanels(1);await idle();
    await original.getByRole('button',{name:'Check connection',exact:true}).click();await ownership(original,'observer');
    assert.equal(await original.getByLabel('GreetingInput',{exact:true}).inputValue(),'unsent original-page draft','raw_draft_retained');
    const packet={jsonrpc:'2.0',id:90,method:'application.form',params:{session:initial.active,request:{jsonrpc:'2.0',id:90,method:'form.event',params:{event:'command',revision:initialRevision,control:'DetailsButton'}}}};
    const fenced=await original.evaluate(async({packet,oldHeaders})=>{
      const selected={};for(const key of ['content-type','x-yadinassi-session','x-yadinassi-attachment','x-yadinassi-generation'])selected[key]=oldHeaders[key];
      const response=await fetch('/rpc',{method:'POST',headers:selected,body:JSON.stringify(packet)+'\n'});return response.json();
    },{packet,oldHeaders});
    assert.equal(fenced.error,'not_writer','old_writer_fenced');assert.equal(state(second).sessions.length,1);
    assert.equal(commandRequests,before+1,'no_automatic_draft_commit');
    page=original;await screenshot(screenshots[1]);
    await detach(original);await detach(second);await realGrace();
    assert.equal(host.exitCode,null,'open_pending_host_retained');assert.equal(host.signalCode,null);
    await stopHost();
  });
  await scenario(scenarioNames[2],async()=>{
    await openShipped();const identities=state(page).sessions.map(x=>x.id);
    await page.reload();
    await page.waitForFunction(()=>['writer','observer'].includes(document.querySelector('.browser-ownership')?.dataset.role),null,{timeout:remaining(10000)});
    if(await page.locator('.browser-ownership').getAttribute('data-role')==='observer'){
      await page.getByRole('button',{name:'Take control',exact:true}).click();
    }
    await ownership(page,'writer');await countPanels(1);await idle();
    assert.deepEqual(state(page).sessions.map(x=>x.id),identities,'resume_retains_identity');
    assert.deepEqual(state(page).messages,['Calculated in the owned server process','8'],'startup_not_replayed');
    await screenshot(screenshots[2]);
    const before=commandRequests;dropReply=true;
    await action('Open details').click();
    await page.waitForFunction(()=>document.querySelector('.browser-ownership')?.textContent.includes('unknown')||document.body.textContent.includes('Requests will not be replayed'),null,{timeout:remaining(10000)});
    await new Promise(resolve=>setTimeout(resolve,1500));
    assert.equal(dropped,1);assert.equal(commandRequests,before+1,'lost_reply_not_retried');
    assert.equal(state(page).sessions.length,2,'dropped_command_really_executed');
    assert.equal(await page.getByRole('button',{name:'Take control',exact:true}).isEnabled(),false,'uncertain_takeover_disabled');
    await stopHost();await page.close();
  });
  await scenario(scenarioNames[3],async()=>{
    await openShipped('refusal');await action('Close form').click();await countPanels(0);await idle();
    lifetimeStage='refused_exit_request';
    const refusedReply=page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.request().postDataJSON()?.method==='application.close'&&response.status()===200,{timeout:remaining(10000)});
    await button('Close application').click();await refusedReply;await idle();
    lifetimeStage='refused_exit_state';
    assert.equal(state(page).lifecycle,'running');assert.equal(state(page).exitWarning,'Close refused by application');
    await detach(page);await realGrace();assert.equal(host.exitCode,null,'refused_exit_retained');
    lifetimeStage='refused_exit_reopen';
    page=await newPage();await page.goto(url);await ownership(page,'writer');await countPanels(0);await idle();
    lifetimeStage='refused_exit_reopen_state';
    assert.equal(state(page).exitWarning,'Close refused by application');await screenshot(screenshots[3]);
    lifetimeStage=null;
    await stopHost();await page.close();
  });
  await scenario(scenarioNames[4],async()=>{
    await openShipped();await action('Close form').click();await countPanels(0);await idle();
    assert.equal(state(page).lifecycle,'running');await screenshot(screenshots[4]);
    await detach(page);await realGrace();
    assert.equal(host.exitCode,0,'ordinary_clean_host_exit');assert.equal(host.signalCode,null,'no_forced_clean_shutdown');
    await stopHost();
  });
  assert.equal(wireFailure,false,'wire_contract');
  report.acceptance={shippedApplication:true,realServerCall:true,writerFencing:true,rawDraftRetained:true,
    resumeWithoutStartupReplay:true,genuineDroppedReply:true,noAutomaticRetry:true,
    realLeaseSeconds:90,realGraceSeconds:30,absenceWaitSeconds:122,refusedExitRetained:true,cleanOrdinaryExit:true,nativeParity:false};
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','source_changed');
  assert.deepEqual(await sourceBinding(),report.binding,'source_binding_changed');
  assert.deepEqual(results.map(row=>row.name),scenarioNames,'incomplete_scenarios');
  assert.equal(wireFailure,false,'wire_contract_failed');
  report.status='PASS';report.rpcRequests=rpc;
  report.detachDiagnostics={...detachDiagnostics};
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
  report.detachDiagnostics={...detachDiagnostics};
  if(phase==='sandbox_launch'&&report.launch)report.launch.failure=launchFailureCode(error);
  if(routeFailure)report.routeFailure=routeFailure;
  if(lifetimeStage)report.lifetimeStage=lifetimeStage;
  report.failure={phase,reason:routeFailure?'route_failed':aborted?'deadline_or_rpc_budget':phase==='sandbox_launch'&&
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
console.log(JSON.stringify({status:report.status,completed:results.length,total:5,source:report.sourceCommit,failure:report.failure,cleanup:report.cleanup}));
if(failed||report.status!=='PASS')process.exitCode=1;
