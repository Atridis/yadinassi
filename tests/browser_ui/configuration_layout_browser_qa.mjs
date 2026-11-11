/** Opt-in source-bound nested layout acquisition. Renderer pages are not native CurrentPage. */
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
const screenshots=['layout-drafts.png','layout-inheritance.png','layout-narrow.png','layout-locked-copy.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['nested_drafts_hidden_flush_and_focus','delayed_repeat_and_group_readonly',
 'independent_pages_visibility_keyboard_narrow_natural_close','lost_real_response_copy_only_navigation'];
// Exact business plan excludes only hello/snapshot reads and attachment traffic.
const businessPlan=[
 ['open','change:FirstNameInput','command:ApplyIdentity'],
 ['command:ApplyIdentity','command:ToggleNamesButton','command:ToggleNamesButton'],
 ['open','command:ToggleNotesButton','command:ToggleNotesButton','change:NotesInput','command:ApplyNotes','close:','close:','close'],
 ['open','change:FirstNameInput']
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
  const args=['-m','yadinassi.ui.configuration_app',path.join(repo,'examples/configuration-forms/layouts'),'--browser-session'];
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
// Page panels and editors may share a label; constrain exact labels to inputs.
const field=name=>active().locator('input').and(active().getByLabel(name,{exact:true}));
const action=name=>active().getByRole('button',{name,exact:true});
const layoutTab=name=>active().getByRole('tab',{name,exact:true});
const replyFor=predicate=>page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.status()===200&&predicate(response.request().postDataJSON()),{timeout:remaining(rpcReplyMs)});
const formReply=(event,control)=>replyFor(packet=>packet.method==='application.form'&&packet.params.request.method==='form.event'&&packet.params.request.params.event===event&&(!control||packet.params.request.params.control===control));
let lastApplicationState=null;
const observedCommands=new Map();
async function command(title,control){
  const index=await panels().evaluateAll(nodes=>nodes.findIndex(node=>!node.hidden));
  assert.equal(lastApplicationState?.sessions.length,await panels().count(),'session_panel_binding');
  const session=lastApplicationState?.sessions[index]?.id;
  assert.match(session||'',/^form-[1-9][0-9]*$/,'active_session_missing');
  const reply=replyFor(packet=>packet.method==='application.form'&&packet.params.session===session&&
    packet.params.request.method==='form.event'&&packet.params.request.params.event==='command'&&
    packet.params.request.params.control===control);
  await action(title).click();const response=await reply;
  const request=response.request().postDataJSON();
  const observed=observedCommands.get(request.id);observedCommands.delete(request.id);
  assert.ok(observed&&observed.packet.params.session===session&&
    observed.packet.params.request.params.control===control,'command_observer_binding');
  const data=observed.actual;
  const errors=[null,'invalid_request','stale_revision','event_failed','closed','outcome_unknown','busy','request_limit','reference_refused','retired_session'];
  const safeError=code=>errors.includes(code)?code:'unexpected_protocol_code';
  report.lastCommand={sessionMatches:data.result.session===session,applicationError:safeError(data.result.error),formError:safeError(data.result.form?.result?.error)};
  assert.equal(data.result.session,session,'command_session_changed');
  assert.equal(data.result.error,null,'application_command_failed');
  assert.equal(data.result.form.result.error,null,'form_command_failed');await idle();
}
async function closeForm(){const reply=formReply('close');await action('Close form').click();await reply;await idle();}
async function naturalStop(){
 const ended=new Promise(resolve=>host.once('exit',(code,signal)=>resolve({code,signal})));
 const reply=replyFor(packet=>packet.method==='application.close');await button('Close application').click();await reply;
 const result=await bounded(ended,remaining(10000),'natural_shutdown_timeout');
 assert.deepEqual(result,{code:0,signal:null},'natural_shutdown_failed');
 await groupGone(hostGroup);host=null;hostGroup=null;origin='';
}
let delayed=null,dropNextChange=false;
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
  const reply=replyFor(packet=>packet.method==='application.form'&&packet.params.request.params?.event==='change');
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
      if(event.event!=='close')assert.ok(['FirstNameInput','LastNameInput','NotesInput','ApplyIdentity','ApplyNotes','ToggleNamesButton','ToggleNotesButton'].includes(event.control),'declared_control');
      if(event.event==='change'){
        exactKeys(event.value,'type value');assert.equal(event.value.type,'String');
        assert.equal(typeof event.value.value,'string');assert.ok(event.value.value.length<=512,'declared_string_budget');
      }
      wireEvents.push({session:packet.params.session,event:event.event,control:event.control});
    }
  }
  if(['application.open','application.close'].includes(packet.method))
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
  return decoded;
}
async function repeatClick(locator){await locator.evaluate(control=>{control.click();control.click();});}
async function scenario(name,fn){
 check();phase=name;const start=businessEvents.length,index=scenarioNames.indexOf(name);
 await fn();check();assert.deepEqual(businessEvents.slice(start),businessPlan[index],'business_rpc_plan_changed');
 results.push({name,status:'PASS',businessRpc:businessEvents.length-start});
}
async function selectedHoverContrast(){
  const selected=layoutTab('Identity');await selected.hover();
  // Wait for the known transition endpoint, not an arbitrary sleep or a transient dark frame.
  await page.waitForFunction(id=>{
    const node=document.getElementById(id);if(!node)return false;
    const style=getComputedStyle(node);
    return style.color==='rgb(255, 255, 255)'&&style.backgroundColor==='rgb(14, 51, 46)';
  },await selected.getAttribute('id'),{timeout:remaining(10000)});
  const colors=await selected.evaluate(node=>{const style=getComputedStyle(node);return [style.color,style.backgroundColor];});
  const luminance=color=>{
    const match=/^rgb\((\d+), (\d+), (\d+)\)$/.exec(color);assert.ok(match,'tab_color_format');
    const channels=match.slice(1).map(Number);assert.ok(channels.every(value=>value>=0&&value<=255));
    const linear=channels.map(value=>{const c=value/255;return c<=0.04045?c/12.92:((c+0.055)/1.055)**2.4;});
    return linear[0]*0.2126+linear[1]*0.7152+linear[2]*0.0722;
  };
  const values=colors.map(luminance);const contrast=(Math.max(...values)+0.05)/(Math.min(...values)+0.05);
  assert.ok(contrast>=4.5,'selected_tab_hover_contrast');report.selectedTabHoverContrast=Math.round(contrast*100)/100;
}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:Object.keys(sessionStorage)})),{local:0,session:['yadinassi.browser.resume/1']},'only_resume_storage');
  assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/configuration','examples/configuration-forms/layouts','tests/browser_ui',
    'tests/test_configuration_form_layouts.py','tests/test_configuration_layout_browser_qa_contract.py','docs/configuration-forms.md','docs/configuration-layout-browser-qa.md',
    '.github/workflows/configuration-layout-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-layout-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'l-'));
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
      if(rpc>=96){abort();return route.abort().catch(()=>{});}
      rpc++;
      try{
        checkRequest(route.request());
        const packet=route.request().postDataJSON();
        const event=packet.method==='application.form'?packet.params.request.params:null;
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        const actual=await auditResponse(response);
        if(event?.event==='command'){
          assert.ok(observedCommands.size<96,'command_observer_budget');
          observedCommands.set(packet.id,{packet,actual});
        }
        if(dropNextChange&&event?.event==='change'){
          dropNextChange=false;
          assert.equal(actual.result.error,null,'dropped_application_failed');
          assert.equal(actual.result.form.result.error,null,'dropped_change_failed');
          const field=actual.result.form.result.state.items.find(item=>item.name===event.control);
          assert.deepEqual(field.value,event.value,'real_change_not_completed');
          report.realReplyDroppedAfterConfirmedChange=true;
          return await route.abort('failed'); // Real server outcome, intentionally no browser reply or retry.
        }
        if(delayed&&event?.event==='command'&&event.control==='ApplyIdentity'){
          const gate=delayed;delayed=null;
          gate.arrived();await bounded(gate.wait,remaining(10000),'late_reply_gate_timeout');
        }
        return await route.fulfill({response});
      }catch{wireFailure=true;abort();return route.abort().catch(()=>{});}
    }
    return route.continue();
  });
  page=await context.newPage();
  const writer=()=>page.waitForFunction(()=>document.querySelector('.browser-ownership')?.dataset.role==='writer',null,{timeout:remaining(10000)});
  const openForm=async()=>{
    const reply=replyFor(packet=>packet.method==='application.open');
    await entries().getByRole('button').click();await reply;await idle();await field('First name').waitFor();
  };
  const selected=async name=>assert.equal(await layoutTab(name).getAttribute('aria-selected'),'true','page_selection');
  await scenario(scenarioNames[0],async()=>{
    phase='layout_host_start';await startHost();
    phase='layout_writer_attach';await page.goto(url);await writer();
    phase='layout_open_first';await openForm();await countPanels(1);
    const first=field('First name'),firstId=await first.getAttribute('id');
    await first.fill('  Ada draft  ');await first.evaluate(node=>node.setSelectionRange(2,5));
    phase='layout_hidden_draft_fence';const before=businessEvents.length;await layoutTab('Notes').click();await selected('Notes');
    await action('Build summary').click();await idle();
    await active().getByRole('alert').filter({hasText:'Unsubmitted inputs are on another page.'}).waitFor();
    await action('Close form').click();await idle();
    assert.equal(businessEvents.length,before,'hidden_draft_dispatched');assert.equal(await panels().count(),1);
    phase='layout_focus_restore';await layoutTab('Identity').click();await selected('Identity');
    assert.equal(await first.getAttribute('id'),firstId,'input_replaced');await value('First name','  Ada draft  ');
    assert.deepEqual(await first.evaluate(node=>({focused:document.activeElement===node,start:node.selectionStart,end:node.selectionEnd})),
      {focused:true,start:2,end:5},'focus_selection_not_retained');
    const names=active().locator('.orientation-horizontal').filter({has:page.getByLabel('First name',{exact:true})});
    assert.equal(await names.count(),1,'horizontal_group_missing');
    phase='layout_hover_contrast';await selectedHoverContrast();
    phase='layout_initial_summary';await screenshot(screenshots[0]);await command('Build summary','ApplyIdentity');
    await value('Summary','  Ada draft   : ');
  });
  await scenario(scenarioNames[1],async()=>{
    let arrived,release;const arrival=new Promise(resolve=>arrived=resolve),wait=new Promise(resolve=>release=resolve);
    delayed={arrived,wait};const reply=formReply('command','ApplyIdentity');
    await repeatClick(action('Build summary'));await bounded(arrival,remaining(10000),'late_command_not_observed');
    assert.equal(await layoutTab('Notes').isDisabled(),true,'busy_page_enabled');
    await layoutTab('Notes').evaluate(node=>node.click());release();await reply;await idle();await selected('Identity');
    await command('Lock/unlock name group','ToggleNamesButton');
    assert.equal(await field('First name').evaluate(node=>node.readOnly),true,'group_readonly_missing');
    assert.equal(await field('Last name').evaluate(node=>node.readOnly),true,'sibling_readonly_missing');
    await screenshot(screenshots[1]);await command('Lock/unlock name group','ToggleNamesButton');
    assert.equal(await field('First name').evaluate(node=>node.readOnly),false,'child_flag_not_restored');
  });
  await scenario(scenarioNames[2],async()=>{
    phase='layout_second_open';await openForm();await countPanels(2);
    phase='layout_second_notes_draft';await layoutTab('Notes').click();await field('Notes').fill('Sibling draft');
    phase='layout_return_first_instance';const before=businessEvents.length;await tabs().getByRole('button').nth(0).click();await selected('Identity');
    assert.equal(businessEvents.length,before,'instance_navigation_dispatched');
    phase='layout_keyboard_end';await layoutTab('Identity').focus();await layoutTab('Identity').press('End');await selected('Notes');
    phase='layout_hide_page';await command('Show/hide notes page','ToggleNotesButton');await selected('Identity');
    assert.equal(await active().getByRole('tab',{name:'Notes',exact:true}).count(),0,'hidden_page_tab_exposed');
    phase='layout_show_page';await command('Show/hide notes page','ToggleNotesButton');await selected('Identity');
    phase='layout_keyboard_next';await layoutTab('Identity').focus();await layoutTab('Identity').press('ArrowRight');await selected('Notes');
    phase='layout_narrow';await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'narrow_horizontal_overflow');
    await screenshot(screenshots[2]);await page.setViewportSize({width:1100,height:850});
    phase='layout_return_second_instance';await tabs().getByRole('button').nth(1).click();await selected('Notes');await value('Notes','Sibling draft');
    phase='layout_apply_second_draft';await commitInput('Notes','Sibling draft');
    phase='layout_second_summary_command';await command('Build summary','ApplyNotes');
    phase='layout_second_summary_readback';await value('Summary',' : Sibling draft');
    phase='layout_natural_close';await closeForm();await countPanels(1);await selected('Notes');await closeForm();await countPanels(0);
    await naturalStop();report.naturalShutdown=true;
  });
  await scenario(scenarioNames[3],async()=>{
    await page.close();page=await context.newPage();phase='layout_fault_host_start';await startHost();
    phase='layout_fault_writer_attach';await page.goto(url);await writer();await openForm();
    phase='layout_fault_copy_recovery';
    await field('First name').fill('  uncertain first  ');await layoutTab('Notes').click();await field('Notes').fill('  retained note  ');
    await layoutTab('Identity').click();dropNextChange=true;await field('First name').press('Enter');
    phase='layout_fault_await_global_lock';await page.getByText('Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.',{exact:true}).waitFor();
    phase='layout_fault_idle';await idle();assert.equal(report.realReplyDroppedAfterConfirmedChange,true,'real_loss_not_observed');
    await screenshot(screenshots[3]); // Bounded failure evidence is not a passing flow.
    assert.deepEqual(await page.locator('.browser-ownership + div').evaluate(node=>({inert:node.inert,inspection:node.dataset.inspection,disabled:node.getAttribute('aria-disabled')})),
      {inert:false,inspection:'true',disabled:'false'},'locked_layout_inspection_unavailable');
    phase='layout_fault_select_local_notes';const before=businessEvents.length;await layoutTab('Notes').click();await selected('Notes');await value('Notes','  retained note  ');
    phase='layout_fault_copy_readonly';
    assert.equal(await field('Notes').isDisabled(),true,'locked_input_enabled');
    const copy=active().locator('.draft-recovery-value');
    assert.ok((await copy.allTextContents()).includes('NotesInput:   retained note  '),'exact_raw_copy_missing');
    assert.equal(await copy.first().evaluate(node=>getComputedStyle(node).userSelect),'text','copy_not_selectable');
    phase='layout_fault_suppressed_actions';
    assert.equal(await entries().getByRole('button').evaluateAll(nodes=>nodes.every(node=>node.disabled)),true,'locked_outer_open_enabled');
    assert.equal(await button('Close application').isDisabled(),true,'locked_outer_close_enabled');
    await button('Close application').evaluate(node=>node.click());
    await field('Notes').evaluate(node=>{node.dispatchEvent(new Event('blur'));node.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));});
    await action('Build summary').evaluate(node=>node.click());await action('Close form').evaluate(node=>node.click());
    await layoutTab('Identity').click();await selected('Identity');await layoutTab('Notes').click();await selected('Notes');
    phase='layout_fault_screenshot';await screenshot(screenshots[3]);assert.equal(businessEvents.length,before,'locked_intent_replayed');
    assert.equal(await action('Build summary').isDisabled(),true);assert.equal(await action('Close form').isDisabled(),true);
    report.acceptance={nestedGroups:true,retainedDrafts:true,hiddenPageFlushFence:true,focusSelection:true,
      inheritedReadOnly:true,busyPageFence:true,independentInstances:true,visibilityFallback:true,keyboardTabs:true,
      narrowViewport:true,naturalShutdownBeforeFault:true,copyOnlyLockedNavigation:true,realResponseLoss:true,
      nativeLayoutParity:false,nativeCurrentPage:false,serverInactivePageAuthorization:false};
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
  report.rpcRequests=rpc;report.businessRpc=businessEvents.length;
  const assertion=String(error?.message||'').split('\n',1)[0];
  const fixedAssertions=['command_observer_binding','command_observer_budget','session_panel_binding','active_session_missing','command_session_changed','application_command_failed','form_command_failed',
    'page_selection','hidden_draft_dispatched','focus_selection_not_retained','instance_navigation_dispatched','narrow_horizontal_overflow',
    'locked_layout_inspection_unavailable','locked_outer_open_enabled','locked_outer_close_enabled','locked_intent_replayed','exact_raw_copy_missing','copy_not_selectable'];
  report.assertion=fixedAssertions.includes(assertion)?assertion:'unclassified_step';
  report.failureClass=['AssertionError','TimeoutError','TypeError','Error'].includes(error?.name)?error.name:'other';
  const reason=String(error?.message||'');
  report.observerFailure=/No resource with given identifier|No data found for resource/.test(reason)?'response_body_unavailable':
    /Target page, context or browser has been closed/.test(reason)?'browser_closed':
    /strict mode violation/.test(reason)?'ambiguous_locator':'unclassified';
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
