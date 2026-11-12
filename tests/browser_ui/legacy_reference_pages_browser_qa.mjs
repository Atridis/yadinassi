/** Реальный legacy chooser и потеря ответа Apply; authored seed70, не native parity. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile,rm,lstat,readdir,readlink,realpath,open as openFile} from 'node:fs/promises';
import path from 'node:path';
import {readFileSync,lstatSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {launchOutputReader,allowedRequest,childEnvironment,ownBrowserPid,commandLineArgs,sandboxCommand,sandboxStatus,sha256}
  from './support.mjs';
const args=process.argv.slice(2);
assert.equal(args.length,0,'invalid_arguments');
const startedAt=Date.now();
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)throw Error('ordinary_nonroot_runner_required');
const output=path.join(temporary,'yadinassi-browser-artifacts');
await mkdir(output); // Never reuse old evidence.
const owned=await mkdtemp(path.join(temporary,'ydr-'));
const home=path.join(owned,'home');await mkdir(home);
const env=childEnvironment(process.env,home);env.PYTHONPATH=repo;
const ownedStat=await lstat(owned);
const ownedReal=await realpath(owned);
assert.equal(path.dirname(ownedReal),await realpath(temporary),'owned_directory_parent');
assert.ok(ownedStat.isDirectory()&&!ownedStat.isSymbolicLink()&&ownedStat.uid===process.getuid(),'owned_directory_identity');
let hostGroup=null;
let host,browser,context,page,origin='',url='',rpc=0,phase='seed',failure,aborted=false,browserGroup=null;
const workDeadline=startedAt+160000,totalDeadline=startedAt+180000;
const cleanupRemaining=max=>Math.max(1,Math.min(max,totalDeadline-Date.now()));
const check=()=>{if(aborted||Date.now()>=workDeadline){aborted=true;throw Error('global_deadline_or_budget');}};
const remaining=max=>{check();return Math.max(1,Math.min(max,workDeadline-Date.now()));};
const killBrowser=()=>signalGroup(browserGroup,'SIGKILL');
const abort=()=>{aborted=true;for(const identity of [hostGroup,browserGroup])try{signalGroup(identity,'SIGKILL');}catch{report.status='FAIL';report.cleanup='owned_signal_failed';}};
const tokens=[],results=[];
const report={status:'FAIL',sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8',timeout:5000,maxBuffer:128}).trim(),scenarios:results,sandbox:null,scope:'authored-legacy-reference-pages-lost-apply',expectedScenarios:1};
const bounded=(promise,ms,reason)=>{let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(reason)),ms);})]).finally(()=>clearTimeout(timer));};
const fixture=mode=>JSON.parse(execFileSync(python,[path.join(repo,'tests/browser_ui/legacy_reference_pages_fixture.py'),mode,owned],
  {cwd:repo,env,encoding:'utf8',timeout:remaining(15000),maxBuffer:16384,stdio:['ignore','pipe','pipe']}));
const audit=()=>fixture('audit');
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
function killHost(signal){signalGroup(hostGroup,signal);}
async function startHost(){
  check();assert.ok(!host||host.exitCode!==null||host.signalCode!==null,'previous_host_live');
  host=spawn(python,['-m','yadinassi.ui.local_app','--f',path.join(owned,'owned.sqlite')],{cwd:repo,env,detached:true,stdio:['ignore','pipe','ignore']});
  const parse=launchOutputReader();let settled=false;
  url=await bounded(new Promise((resolve,reject)=>{
    host.once('error',()=>reject(Error('host_spawn_failed')));
    host.once('spawn',()=>{try{hostGroup=processIdentity(host.pid);}catch{reject(Error('host_identity_failed'));}});
    host.once('exit',()=>{if(!settled)reject(Error('host_exited_before_launch'));});
    host.stdout.on('data',data=>{if(settled)return;try{const found=parse(data);if(found){settled=true;origin=found.origin;tokens.push(found.hash.slice(9));resolve(found.href);}}catch{settled=true;reject(Error('invalid_launch_output'));}});
  }),15000,'host_start_timeout');
}
const button=name=>page.getByRole('button',{name,exact:true});
const openSelectedRecord=async()=>{await page.locator('.records tbody tr').first().click();await button('Open selected').click();};
const field=name=>page.getByLabel(name,{exact:true});
const ready=()=>page.waitForFunction(()=>[...document.querySelectorAll('button')].some(
  button=>button.textContent==='Save changes'&&!button.disabled));
async function recordsReady(){
  await page.locator('.editor').waitFor({state:'detached'});
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(
    button=>button.textContent.trim()==='+ New record'&&!button.disabled));
}
async function screenshot(name){
  assert.ok(['list.png','editor.png','narrow.png'].includes(name),'unexpected_screenshot');
  assert.equal(new URL(page.url()).hash,'','capability_not_removed');
  await page.screenshot({path:path.join(output,name),fullPage:true,animations:'disabled',timeout:remaining(10000)});
}
async function closeHostThroughUI(){
  await button('Close database').click();
  await page.getByRole('heading',{name:'Database closed',exact:true}).waitFor();
  if(host.exitCode===null&&host.signalCode===null)
    await bounded(new Promise(resolve=>host.once('exit',resolve)),remaining(8000),'host_close_timeout');
  assert.equal(host.exitCode,0,'host_cleanup_failed');
  await stopHost();
}
async function scenario(name,fn){check();phase=name;await fn();check();results.push({name,status:'PASS'});}
async function main(){
  assert.notEqual(process.getuid(),0,'nonroot_required');
  const git=(...args)=>execFileSync('git',args,{cwd:repo,encoding:'utf8',timeout:remaining(5000),maxBuffer:1024*1024}).trim();
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','tracked_checkout_dirty');
  const names=git('ls-files','-z','yadinassi','pyproject.toml','tests/browser_ui','frontend/catalog','.github/workflows/legacy-reference-pages-browser-qa.yml').split('\0').filter(Boolean);
  for(const required of ['tests/browser_ui/legacy_reference_pages_browser_qa.mjs','tests/browser_ui/legacy_reference_pages_fixture.py',
    'tests/browser_ui/support.mjs','tests/browser_ui/package-lock.json',
    'frontend/catalog/src/app.jsx','.github/workflows/legacy-reference-pages-browser-qa.yml'])assert.ok(names.includes(required),'fixture_or_harness_not_tracked');
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  report.binding={commit:report.sourceCommit,tree:git('rev-parse','HEAD^{tree}'),source};
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1');
  phase='authored_fixture';assert.equal(fixture('seed').seeded,true);
  phase='browser_socket_path_preflight';
  assert.ok(Buffer.byteLength(path.join(home,'org.chromium.Chromium.XXXXXX','SingletonSocket'))<108,
    'socket_path_too_long');
  phase='sandbox_launch';
  const childrenPath='/proc/'+process.pid+'/task/'+process.pid+'/children';
  const priorChildren=new Set(readFileSync(childrenPath,'utf8').trim().split(/\s+/).filter(Boolean));
  try{
    check();browser=await chromium.launch({channel:'chromium',headless:true,chromiumSandbox:true,env,timeout:remaining(20000)});
  }finally{
    // Own the newly launched direct process group before depending on CDP.
    const children=readFileSync(childrenPath,'utf8').trim().split(/\s+/).filter(x=>x&&!priorChildren.has(x));
    assert.ok(children.length<=1,'unexpected_launch_children');
    if(children.length){
      phase='browser_owner_verification';
      const pid=Number(children[0]);assert.ok(Number.isSafeInteger(pid)&&pid>0);
      const stat=readFileSync('/proc/'+pid+'/stat','utf8');
      const fields=stat.slice(stat.lastIndexOf(')')+2).trim().split(/\s+/);
      assert.equal(Number(fields[1]),process.pid,'browser_not_direct_child');
      assert.equal(Number(fields[2]),pid,'browser_process_group_not_owned');browserGroup=processIdentity(pid);
      const processRoot='/proc/'+pid;
      assert.equal((await lstat(processRoot)).uid,process.getuid(),'browser_uid_mismatch');
      phase='browser_executable_verification';
      // procfs reports the canonical target, while the pinned registry path can
      // contain a runner-temp symlink. Compare the same exact file identity.
      const expectedExecutable=await realpath(chromium.executablePath());
      assert.equal(await readlink(processRoot+'/exe'),expectedExecutable,'browser_executable_mismatch');
      phase='browser_command_verification';
      const command=await openFile(processRoot+'/cmdline','r');
      try{
        const buffer=Buffer.alloc(16385);let length=0;
        while(length<buffer.length){const result=await command.read(buffer,length,buffer.length-length,null);
          if(!result.bytesRead)break;length+=result.bytesRead;}
        assert.ok(length>0&&length<=16384,'browser_command_budget');
        sandboxCommand(commandLineArgs(buffer.subarray(0,length)));
      }finally{await command.close();}
    }
  }
  check();assert.ok(browserGroup,'browser_process_missing');report.browser=browser.version();
  phase='browser_cdp_verification';
  const cdp=await bounded(browser.newBrowserCDPSession(),remaining(5000),'cdp_setup_timeout');
  const info=await bounded(cdp.send('SystemInfo.getProcessInfo'),remaining(5000),'cdp_process_timeout');
  assert.equal(ownBrowserPid(info.processInfo),browserGroup.pid,'browser_pid_mismatch');
  await cdp.detach();
  context=await browser.newContext({viewport:{width:1320,height:1000},locale:'en-US',timezoneId:'UTC',
    acceptDownloads:false,serviceWorkers:'block'});
  context.setDefaultTimeout(10000);context.setDefaultNavigationTimeout(15000);
  phase='browser_sandbox_status';
  const probe=await context.newPage();probe.setDefaultTimeout(remaining(10000));await probe.goto('chrome://sandbox');report.sandbox=sandboxStatus(await probe.locator('body').innerText());await probe.close();
  await startHost();
  let dropApply=false, dropped=0;
  const requests=[];
  await context.route('**/*',async route=>{
    const target=route.request().url();
    if(aborted||!allowedRequest(target,origin))return route.abort();
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=50){aborted=true;abort();return route.abort();}
      rpc++;
      const request=route.request().postDataJSON();
      requests.push({method:request.method,event:request.params?.event,action:request.params?.action?.action});
      if(dropApply&&request.params?.event==='referenceChoice'&&request.params.action.action==='apply'){
        dropApply=false;
        const response=await route.fetch({timeout:remaining(10000),maxRedirects:0,maxRetries:0});
        assert.equal(response.status(),200,'apply_http_failure');
        const bytes=await bounded(response.body(),remaining(10000),'apply_body_timeout');
        assert.ok(bytes.length<=131072,'apply_body_budget');
        const body=JSON.parse(bytes.toString('utf8'));
        assert.ok(body.result&&!body.error,'apply_backend_failure');
        assert.equal(body.result.state.referenceChoice,null,'apply_not_completed');
        dropped++;
        await response.dispose();
        return route.abort('failed');
      }
    }
    return route.continue();
  });
  page=await context.newPage();page.setDefaultTimeout(10000);
  await page.goto(url);
  await scenario('scalar_section_pages_save_restart_and_lost_apply_snapshot_recovery',async()=>{
    await page.getByRole('button',{name:/^Products\s*›?$/}).click();
    await button('+ New record').click();
    await field('Code').fill('PICKQA');
    await field('Description').fill('Draft preserved after lost Apply');
    await button('Choose DefaultWarehouse').click();
    const dialog=page.getByRole('dialog',{name:'Choose reference',exact:true});
    await dialog.waitFor({state:'visible'});
    await button('Next choices').click();
    await button('Previous choices').click();
    await field('Search references').fill('W069');
    await button('Search references').click();
    dropApply=true;
    await button('W069 · Warehouse 069').click();
    await button('Resynchronize choice').waitFor({state:'visible'});
    assert.equal(dropped,1,'lost_apply_not_observed');
    const beforeRecovery=requests.length;
    await button('Resynchronize choice').click();
    await dialog.waitFor({state:'hidden'});await ready();
    assert.deepEqual(requests.slice(beforeRecovery).map(r=>r.method),['editor.snapshot'],'recovery_replayed_event');
    assert.equal(await field('Code').inputValue(),'PICKQA','code_draft_lost');
    assert.equal(await field('Description').inputValue(),'Draft preserved after lost Apply','description_draft_lost');
    assert.equal(await field('DefaultWarehouse').locator('option:checked').innerText(),'W069 · Warehouse 069');
    assert.equal(requests.filter(r=>r.action==='apply').length,1,'scalar_apply_replayed');
    await button('Add row to Warehouses').click();
    await button('Choose Warehouses row 1').click();
    await dialog.waitFor({state:'visible'});
    await button('Next choices').click();
    await field('Search references').fill('W068');
    await button('Search references').click();
    await button('W068 · Warehouse 068').click();
    await dialog.waitFor({state:'hidden'});
    await button('Save changes').click();
    await page.getByRole('status').filter({hasText:/^Saved$/}).waitFor();await ready();
    await screenshot('editor.png');
    await button('← Back to records').click();await recordsReady();
    await screenshot('list.png');
    await closeHostThroughUI();
    const saved=audit();
    await startHost();await page.goto(url);
    await page.getByRole('button',{name:/^Products\s*›?$/}).click();
    await openSelectedRecord();await ready();
    assert.equal(await field('Code').inputValue(),'PICKQA');
    assert.equal(await field('Description').inputValue(),'Draft preserved after lost Apply');
    assert.equal(await field('DefaultWarehouse').locator('option:checked').innerText(),'W069 · Warehouse 069');
    assert.equal(await field('Warehouses row 1: Warehouse').locator('option:checked').innerText(),'W068 · Warehouse 068');
    assert.equal(await page.locator('table.section-rows tbody tr').count(),1);
    await page.setViewportSize({width:390,height:844});await screenshot('narrow.png');
    await closeHostThroughUI();
    assert.deepEqual(audit(),saved,'restart_changed_saved_data');
    assert.equal(requests.filter(r=>r.method==='editor.event').length,20,'business_request_count');
    assert.equal(requests.filter(r=>r.action==='apply').length,2,'apply_count');
    assert.equal(requests.filter(r=>r.method==='editor.snapshot').length,1,'snapshot_count');
    assert.equal(requests.filter(r=>r.method==='editor.hello').length,2,'hello_count');
    report.durable={preparedReferences:70,uiCreatedProducts:1,lostApplyResponses:1,
      recoverySnapshotOnly:true,scalarAndSectionSelectionsVerified:true,processRestartVerified:true};
    report.businessRequests=20;
  });
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','source_changed');
  assert.equal(git('rev-parse','HEAD'),report.sourceCommit,'source_commit_changed');
  for(const [name,digest] of Object.entries(source)){check();assert.equal(sha256(await readFile(path.join(repo,name))),digest,'source_bytes_changed');}
  assert.equal(results.length,1);report.status='PASS';report.rpcRequests=rpc;
}
// Reserve 20 seconds for verified bounded cleanup within the 180s total.
const deadline=setTimeout(abort,Math.max(0,workDeadline-Date.now()));
const totalTimer=setTimeout(()=>{abort();process.exit(1);},Math.max(0,totalDeadline-Date.now()));
// Export only fixed codes. Assertion messages can append paths/actual values;
// neither those details nor raw browser logs belong in the artifact.
const safeFailureCodes=new Set([
  'socket_path_too_long','unexpected_launch_children','browser_not_direct_child','browser_process_group_not_owned',
  'browser_uid_mismatch','browser_executable_mismatch','browser_command_budget',
  'browser_command_invalid','sandbox_command_missing','sandbox_disabled','unexpected_browser_transport',
  'browser_process_missing','browser_pid_mismatch','browser_pid_invalid',
  'cdp_setup_timeout','cdp_process_timeout','sandbox_status_invalid','sandbox_not_confirmed',
]);
function failureReason(error){
  if(aborted)return 'deadline_or_rpc_budget';
  const message=typeof error?.message==='string'?error.message:'';
  for(const code of safeFailureCodes)if(message===code||message.startsWith(code+'\n'))return code;
  if(['EACCES','EPERM','ENOENT','ESRCH'].includes(error?.code))return 'verification_'+error.code.toLowerCase();
  if(/Socket path too long/i.test(message))return 'socket_path_too_long';
  if(phase==='sandbox_launch'&&/Operation not permitted|No usable sandbox|Failed to move to new namespace|Chromium sandboxing failed!/i.test(message))
    return 'sandbox_start_denied';
  return 'step_failed';
}
try{await main();check();}catch(error){failure=error;report.status='FAIL';report.failure={phase,reason:failureReason(error)};}
finally{
  aborted=true;clearTimeout(deadline);
  try{if(browser)await bounded(browser.close(),cleanupRemaining(8000),'browser_close_timeout');}catch{report.status='FAIL';report.cleanup='browser_close_failed';}
  try{signalGroup(browserGroup,'SIGKILL');await groupGone(browserGroup);}catch{cleanupFailure('browser_cleanup_unverified');}
  try{await stopHost();}catch{cleanupFailure('host_cleanup_unverified');}
  report.elapsedMs=Date.now()-startedAt;
  try{
    const now=await lstat(owned);
    assert.ok(now.isDirectory()&&!now.isSymbolicLink()&&now.uid===ownedStat.uid&&now.dev===ownedStat.dev&&now.ino===ownedStat.ino,'owned_directory_changed');
    assert.equal(await realpath(owned),ownedReal,'owned_directory_retargeted');
    assert.equal(path.dirname(ownedReal),await realpath(temporary),'owned_directory_parent_changed');
    await bounded(rm(owned,{recursive:true,force:true}),cleanupRemaining(2000),'owned_remove_timeout');
    try{await lstat(owned);throw Error('owned_directory_remains');}catch(error){if(error.code!=='ENOENT')throw error;}
  }catch{cleanupFailure('owned_directory_cleanup_unverified');}
  const images={};
  for(const name of ['list.png','editor.png','narrow.png']){
    try{const file=path.join(output,name),stat=await lstat(file);assert.ok(stat.isFile()&&!stat.isSymbolicLink()&&stat.size<=4*1024*1024);const bytes=await readFile(file);assert.equal(bytes.length,stat.size);images[name]={bytes:bytes.length,sha256:sha256(bytes)};}
    catch{await rm(path.join(output,name),{force:true});report.status='FAIL';report.artifacts='missing_or_invalid_screenshot';}
  }
  const raw=JSON.stringify(report,null,2)+'\n';
  assert.ok(Buffer.byteLength(raw)<=65536,'report_budget');
  assert.ok(!tokens.some(token=>raw.includes(token)),'capability_leak');
  await writeFile(path.join(output,'result.json'),raw);
  await writeFile(path.join(output,'manifest.json'),JSON.stringify({schema:1,source:report.sourceCommit,tree:report.binding?.tree,resultSha256:sha256(raw),images},null,2)+'\n');
  assert.ok((await readdir(output)).every(name=>['result.json','manifest.json','list.png','editor.png','narrow.png'].includes(name)));
}
clearTimeout(totalTimer);
console.log(JSON.stringify({status:report.status,completed:results.length,total:1,source:report.sourceCommit,failure:report.failure}));if(failure||report.status!=='PASS')process.exitCode=1;
