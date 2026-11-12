/** Единая демо: исходные формы, документы и readonly recovery. Seed только70складов; не native parity. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile,rm,lstat,readdir,readlink,realpath,open as openFile} from 'node:fs/promises';
import path from 'node:path';
import {readFileSync,lstatSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {childEnvironment,ownBrowserPid,commandLineArgs,sandboxCommand,sandboxStatus,sha256}
  from './support.mjs';
import {mainDemoLaunchOutputReader as launchOutputReader,mainDemoAllowedRequest as allowedRequest,verifyMainDemoAudit} from './main_demo_browser_support.mjs';
const args=process.argv.slice(2);
assert.equal(args.length,0,'invalid_arguments');
const startedAt=Date.now();
// Match existing transport/observer budgets; do not shorten a valid in-flight RPC.
const rpcFetchMs=35000,rpcReplyMs=50000;
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)throw Error('ordinary_nonroot_runner_required');
const output=path.join(temporary,'yadinassi-browser-artifacts');
await mkdir(output); // Never reuse old evidence.
const owned=await mkdtemp(path.join(temporary,'ydm-'));
const home=path.join(owned,'home');await mkdir(home);
const env=childEnvironment(process.env,home);env.PYTHONPATH=repo;
const ownedStat=await lstat(owned);
const ownedReal=await realpath(owned);
assert.equal(path.dirname(ownedReal),await realpath(temporary),'owned_directory_parent');
assert.ok(ownedStat.isDirectory()&&!ownedStat.isSymbolicLink()&&ownedStat.uid===process.getuid(),'owned_directory_identity');
let hostGroup=null;
let host,browser,context,page,origin='',url='',rpc=0,phase='seed',failure,aborted=false,browserGroup=null;
const workDeadline=startedAt+280000,totalDeadline=startedAt+300000;
const cleanupRemaining=max=>Math.max(1,Math.min(max,totalDeadline-Date.now()));
const check=()=>{if(aborted||Date.now()>=workDeadline){aborted=true;throw Error('global_deadline_or_budget');}};
const remaining=max=>{check();return Math.max(1,Math.min(max,workDeadline-Date.now()));};
const killBrowser=()=>signalGroup(browserGroup,'SIGKILL');
const abort=()=>{aborted=true;for(const identity of [hostGroup,browserGroup])try{signalGroup(identity,'SIGKILL');}catch{report.status='FAIL';report.cleanup='owned_signal_failed';}};
const tokens=[],results=[];
const report={status:'FAIL',sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8',timeout:5000,maxBuffer:128}).trim(),scenarios:results,sandbox:null,scope:'main-demo-original-catalogs-documents-recovery',expectedScenarios:2};
const bounded=(promise,ms,reason)=>{let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(reason)),ms);})]).finally(()=>clearTimeout(timer));};
const fixture=mode=>{
  const raw=execFileSync(python,[path.join(repo,'tests/browser_ui/main_demo_fixture.py'),mode,owned],
    {cwd:repo,env,encoding:'utf8',timeout:remaining(15000),maxBuffer:131072,stdio:['ignore','pipe','pipe']});
  assert.ok(Buffer.byteLength(raw,'utf8')<=131072,'fixture_stdout_budget');
  return JSON.parse(raw);
};
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
  host=spawn(python,['-m','yadinassi','--ui','--f',path.join(owned,'main-demo.sqlite')],{cwd:repo,env,detached:true,stdio:['ignore','pipe','ignore']});
  const parse=launchOutputReader();let settled=false;
  url=await bounded(new Promise((resolve,reject)=>{
    host.once('error',()=>reject(Error('host_spawn_failed')));
    host.once('spawn',()=>{try{hostGroup=processIdentity(host.pid);}catch{reject(Error('host_identity_failed'));}});
    host.once('exit',()=>{if(!settled)reject(Error('host_exited_before_launch'));});
    host.stdout.on('data',data=>{if(settled)return;try{const found=parse(data);if(found){settled=true;origin=found.origin;tokens.push(found.hash.slice(9).split('&')[0]);resolve(found.href);}}catch{settled=true;reject(Error('invalid_launch_output'));}});
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
  const names=git('ls-files','-z','yadinassi','pyproject.toml','tests/browser_ui','frontend/catalog','frontend/configuration','frontend/main-demo','frontend/form','examples/demo','.github/workflows/main-demo-browser-qa.yml').split('\0').filter(Boolean);
  for(const required of ['.github/workflows/main-demo-browser-qa.yml','tests/browser_ui/main_demo_browser_qa.mjs','tests/browser_ui/main_demo_fixture.py',
    'tests/browser_ui/support.mjs','tests/browser_ui/main_demo_browser_support.mjs','tests/browser_ui/package-lock.json',
    'frontend/catalog/src/app.jsx','frontend/main-demo/src/app.mjs','frontend/configuration/src/app.mjs'])assert.ok(names.includes(required),'fixture_or_harness_not_tracked');
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  report.binding={commit:report.sourceCommit,tree:git('rev-parse','HEAD^{tree}'),source};
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1');
  phase='authored_fixture';assert.deepEqual(fixture('seed'),{database:'main-demo.sqlite',authoredWarehouses:70,kindsInitially:0,productsInitially:0,documentsInitially:0});
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
  let dropApply=false, dropDocument=false, dropped=0, droppedDocument=0;
  const requests=[];
  // Export only fixed protocol method names, never params, URLs or tokens.
  const diagnosticMethods=new Set(['demo.hello','demo.snapshot','demo.select','demo.dispatch','demo.close',
    'editor.hello','editor.snapshot','editor.select','editor.open','editor.event',
    'application.hello','application.catalog','application.open','application.openRecord',
    'application.form','application.reference','application.report','application.reportSetup',
    'form.hello','form.snapshot','form.event']);
  const safeMethod=value=>diagnosticMethods.has(value)?value:'other';
  report.rpcTail=[];
  await context.route('**/*',async route=>{
    const target=route.request().url();
    if(aborted||!allowedRequest(target,origin))return route.abort();
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=180){aborted=true;abort();return route.abort();}
      rpc++;report.rpcRequests=rpc;
      const request=route.request().postDataJSON();
      const inner=request.method==='demo.dispatch'?request.params.request:null;
      requests.push({method:request.method,inner:inner?.method,event:inner?.params?.event,
        action:inner?.params?.action?.action,nested:inner?.params?.request?.method});
      report.rpcTail.push([safeMethod(request.method),safeMethod(inner?.method),safeMethod(inner?.params?.request?.method)]);
      if(report.rpcTail.length>12)report.rpcTail.shift();
      const loseApply=dropApply&&inner?.params?.event==='referenceChoice'&&inner.params.action.action==='apply';
      const loseDocument=dropDocument&&inner?.method==='application.hello';
      if(loseApply||loseDocument){
        if(loseApply)dropApply=false;else dropDocument=false;
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        assert.equal(response.status(),200,'lost_response_http_failure');
        const bytes=await bounded(response.body(),remaining(10000),'lost_response_body_timeout');
        assert.ok(bytes.length<=131072,'lost_response_body_budget');
        const body=JSON.parse(bytes.toString('utf8'));
        assert.ok(body.result&&!body.error&&!body.result.error,'outer_backend_failure');
        const payload=body.result.payload;
        assert.ok(payload?.result&&!payload.error&&!payload.result.error,'inner_backend_failure');
        if(loseApply){assert.equal(payload.result.state.referenceChoice,null,'apply_not_completed');dropped++;}
        else{assert.equal(payload.result.state?.kind,'application','document_read_not_completed');droppedDocument++;}
        await response.dispose();return route.abort('failed');
      }
    }
    return route.continue();
  });
  page=await context.newPage();page.setDefaultTimeout(10000);
  await page.goto(url);
  const actionLog=[];report.actions=actionLog;report.actionCount=0;
  const act=async(name,fn)=>{check();actionLog.push(name);report.actionCount=actionLog.length;report.progress={action:actionLog.length,name,state:'started'};await fn();check();report.progress.state='completed';};
  const click=async name=>act(name,()=>button(name).click());
  const catalog=async name=>act('catalog:'+name,()=>page.getByRole('navigation',{name:'Catalogs',exact:true}).getByRole('button',{name:new RegExp('^'+name+'\\s*›?$')}).click());
  const legacyDialog=()=>page.getByRole('dialog',{name:'Choose reference',exact:true});
  const snapshotMethods=start=>requests.slice(start).map(r=>r.method==='demo.dispatch'?r.inner:r.method);
  await scenario('original_catalogs_section_lost_apply_recovery_save',async()=>{
    await catalog('ВидыНоменклатуры');await click('+ New record');
    await act('kind-description',()=>field('Description').fill('Товары'));
    await click('Save changes');await page.getByRole('status').filter({hasText:/^Saved$/}).waitFor();
    await click('← Back to records');await recordsReady();
    await catalog('Номенклатура');await click('+ New record');
    assert.equal(await field('Code').isDisabled(),true);
    await act('product-description',()=>field('Description').fill('Кабель USB-C'));
    await act('kind-reference',()=>field('ВидНоменклатуры').selectOption({label:'000000001 · Товары'}));
    await click('Add row to Склады');await click('Choose Склады row 1');
    await legacyDialog().waitFor({state:'visible'});await click('Next choices');await click('Previous choices');
    await act('warehouse-search-text',()=>field('Search references').fill('W069'));await click('Search references');
    dropApply=true;await click('W069 · Warehouse 069');
    await button('Resynchronize choice').waitFor({state:'visible'});assert.equal(dropped,1);
    const recoveryStart=requests.length;await click('Resynchronize choice');
    await legacyDialog().waitFor({state:'hidden'});await ready();
    assert.deepEqual(snapshotMethods(recoveryStart),['demo.snapshot','editor.snapshot'],'catalog_recovery_not_snapshot_only');
    assert.equal(await field('Description').inputValue(),'Кабель USB-C');
    assert.equal(await field('Склады row 1: Склад').locator('option:checked').innerText(),'W069 · Warehouse 069');
    assert.equal(requests.filter(r=>r.action==='apply').length,1,'apply_replayed');
    await click('Save changes');await page.getByRole('status').filter({hasText:/^Saved$/}).waitFor();
    await click('← Back to records');await recordsReady();await click('Refresh records');
    await page.getByRole('cell',{name:'Кабель USB-C',exact:true}).waitFor();await screenshot('list.png');
    const saved=audit();assert.equal(saved.readOnlyAudit,true);
    assert.equal(saved.catalogs['ВидыНоменклатуры'].length,1);assert.equal(saved.catalogs['Номенклатура'].length,1);
    assert.equal(saved.catalogs['Номенклатура'][0].description,'Кабель USB-C');assert.equal(saved.movementRows.length,0);
    assert.equal(actionLog.length,20,'catalog_action_count');
  });
  const active=()=>page.locator('.configuration-form-panels > section:not([hidden])');
  const docField=name=>active().getByLabel(name,{exact:true});
  const docButton=name=>active().getByRole('button',{name,exact:true});
  const idle=()=>page.waitForFunction(()=>[...document.querySelectorAll('[aria-busy]')].every(node=>node.getAttribute('aria-busy')==='false'),null,{timeout:remaining(10000)});
  const replyFor=predicate=>page.waitForResponse(response=>{
    if(new URL(response.url()).pathname!=='/rpc'||response.status()!==200)return false;
    const packet=response.request().postDataJSON();
    return packet.method==='demo.dispatch'&&predicate(packet.params.request);
  },{timeout:remaining(rpcReplyMs)});
  const settled=async(predicate,action)=>{const reply=replyFor(predicate);await Promise.all([reply,action()]);await idle();};
  const formEvent=event=>packet=>packet.method==='application.form'&&packet.params.request.method==='form.event'&&packet.params.request.params.event===event;
  const commit=async(name,text)=>act('document-input:'+name,()=>settled(
    packet=>packet.method==='application.form'&&['change','cell'].includes(packet.params.request.params?.event),
    async()=>{await docField(name).fill(text);await docField(name).press('Enter');}));
  const choose=async(label,code,title)=>{
    await act('choose:'+label,()=>settled(packet=>packet.method==='application.reference'&&packet.params.action.action==='begin',()=>docButton('Choose '+label).click()));
    await act('apply:'+label,()=>settled(packet=>packet.method==='application.reference'&&packet.params.action.action==='apply',()=>page.getByRole('dialog').getByRole('button',{name:'Choose '+code+' '+title,exact:true}).click()));
    await page.getByRole('dialog').waitFor({state:'hidden'});
  };
  await scenario('same_database_document_report_recovery_return_to_original_catalog',async()=>{
    await click('Документы и отчёты');
    await act('receipt-list',()=>settled(packet=>packet.method==='application.catalog',()=>page.getByRole('navigation',{name:'Declared forms',exact:true}).getByRole('button',{name:'Receipt card',exact:true}).click()));
    await act('New document',()=>settled(packet=>packet.method==='application.open',()=>button('New document').click()));await commit('Document number','RQA1');
    await choose('Warehouse','W000','Warehouse 000');
    await act('add-line',()=>settled(formEvent('command'),()=>docButton('Add line').click()));
    await choose('Product, row 1','000000001','Кабель USB-C');
    // Invalid local draft cannot blur-commit; lose a real readonly hello, not a business write.
    await commit('Quantity, row 1','3');
    await act('amount-draft',()=>docField('Amount, row 1').fill('123x'));
    dropDocument=true;await click('Восстановить состояние');
    await page.getByText('Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.',{exact:true}).waitFor();
    assert.equal(droppedDocument,1);const recoveryStart=requests.length;
    await click('Восстановить состояние');
    await docButton('Write document').waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='Write document'&&!b.disabled));
    assert.deepEqual(snapshotMethods(recoveryStart),['demo.snapshot','application.hello','application.form']);
    assert.equal(requests.at(-1).nested,'form.snapshot');
    assert.equal(await docField('Amount, row 1').inputValue(),'123x','document_local_draft_lost');
    assert.equal(await docField('Quantity, row 1').inputValue(),'3');
    await commit('Amount, row 1','123');
    await act('write-document',()=>settled(formEvent('command'),()=>docButton('Write document').click()));
    await act('post-document',()=>settled(formEvent('command'),()=>docButton('Post document').click()));
    await act('movement-report-tab',()=>page.getByRole('navigation',{name:'Declared stock reports',exact:true}).getByRole('button',{name:'Stock Movements',exact:true}).click());
    const reports=page.getByRole('region',{name:'Saved stock reports',exact:true});
    // Movements has no period filter; only Turnovers/Statement expose bounds.
    await act('show-report',()=>reports.getByRole('button',{name:'Show saved stock',exact:true}).click());
    await reports.getByRole('cell',{name:'Кабель USB-C',exact:true}).waitFor();await screenshot('editor.png');
    const saved=audit();verifyMainDemoAudit(saved,assert);
    await act('close-document',()=>settled(formEvent('close'),()=>docButton('Close form').click()));await active().waitFor({state:'detached'});
    await click('Справочники');await catalog('Номенклатура');
    await act('select-product-row',()=>page.locator('.records tbody tr').first().click());await click('Open selected');await ready();
    assert.equal(await field('Description').inputValue(),'Кабель USB-C');
    assert.equal(await field('ВидНоменклатуры').locator('option:checked').innerText(),'000000001 · Товары');
    assert.equal(await field('Склады row 1: Склад').locator('option:checked').innerText(),'W069 · Warehouse 069');
    assert.deepEqual(audit(),saved,'surface_switch_changed_saved_data');
    await page.setViewportSize({width:390,height:844});await screenshot('narrow.png');
    await click('← Back to records');await recordsReady();
    // Process cleanup is owned and verified below; no hidden business close API.
  });
  assert.equal(actionLog.length,44,'total_action_count');
  report.actions=actionLog;report.actionCount=actionLog.length;
  report.durable={authoredWarehouses:70,uiCreatedKinds:1,uiCreatedProducts:1,uiCreatedReceipts:1,
    lostApplyResponses:dropped,lostDocumentResponses:droppedDocument,recoveryReadOnly:true};
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','source_changed');
  assert.equal(git('rev-parse','HEAD'),report.sourceCommit,'source_commit_changed');
  for(const [name,digest] of Object.entries(source)){check();assert.equal(sha256(await readFile(path.join(repo,name))),digest,'source_bytes_changed');}
  assert.equal(results.length,2);report.status='PASS';report.rpcRequests=rpc;
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
console.log(JSON.stringify({status:report.status,completed:results.length,total:2,source:report.sourceCommit,failure:report.failure}));if(failure||report.status!=='PASS')process.exitCode=1;
