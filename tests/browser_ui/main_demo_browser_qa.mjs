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
import {MainDemoFilterCapture} from './main_demo_filter_capture.mjs';
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
const report={status:'FAIL',sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8',timeout:5000,maxBuffer:128}).trim(),scenarios:results,sandbox:null,scope:'main-demo-original-catalogs-documents-owned-drafts-recovery',expectedScenarios:5};
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
  assert.ok(['list.png','editor.png','narrow.png','choice.png'].includes(name),'unexpected_screenshot');
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
    'tests/browser_ui/support.mjs','tests/browser_ui/main_demo_filter_capture.mjs','tests/browser_ui/main_demo_browser_support.mjs','tests/browser_ui/package-lock.json',
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
  let resultGate=null,dropOwnedResult=false,droppedOwnedResult=0;
  let dialogGate=null,dropDialog=false,droppedDialog=0;
  const requests=[];const filterCapture=new MainDemoFilterCapture();
  // Export only fixed protocol method names, never params, URLs or tokens.
  const diagnosticMethods=new Set(['demo.hello','demo.snapshot','demo.select','demo.dispatch','demo.close',
    'editor.hello','editor.snapshot','editor.select','editor.open','editor.event',
    'application.hello','application.catalog','application.catalogFilter','application.catalogPage','application.open','application.openRecord',
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
        action:inner?.params?.action?.action,nested:inner?.params?.request?.method,control:inner?.params?.request?.params?.control});
      report.rpcTail.push([safeMethod(request.method),safeMethod(inner?.method),safeMethod(inner?.params?.request?.method)]);
      if(report.rpcTail.length>12)report.rpcTail.shift();
      if(await filterCapture.route(route,origin,{fetchTimeout:remaining(rpcFetchMs),bodyTimeout:remaining(rpcFetchMs),bounded}))return;
      if(inner?.method==='application.answerDialog'&&(dialogGate||dropDialog)){
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        try{
          assert.equal(response.status(),200,'dialog_answer_http');
          const bytes=await bounded(response.body(),remaining(rpcFetchMs),'dialog_answer_body_timeout');
          assert.ok(bytes.length<=131072,'dialog_answer_body_budget');
          const body=JSON.parse(bytes.toString('utf8'));
          assert.equal(body.id,request.id,'dialog_answer_outer_id');
          assert.equal(body.result?.payload?.id,inner.id,'dialog_answer_inner_id');
          assert.equal(body.result?.error,null,'dialog_answer_outer_error');
          const result=body.result?.payload?.result;
          assert.equal(result?.error,null,'dialog_answer_inner_error');
          assert.equal(result.form?.result?.error,null,'dialog_answer_form_error');
          const values=result.form.result.state.items;
          const count=Number(values.find(item=>item.name==='AppliedCountField')?.value?.value);
          const amount=Number(values.find(item=>item.name==='AmountField')?.value?.value);
          assert.equal(count,dropDialog?2:1,'dialog_answer_count');
          assert.equal(amount,dropDialog?33:11,'dialog_answer_amount');
          if(dropDialog){dropDialog=false;droppedDialog++;return route.abort('failed');}
          const gate=dialogGate;dialogGate=null;gate.arrived();
          await bounded(gate.wait,remaining(10000),'dialog_answer_gate_timeout');
          return await route.fulfill({response,body:bytes});
        }finally{await response.dispose();}
      }
      const ownedAccept=inner?.method==='application.form'&&inner.params?.request?.method==='form.event'&&inner.params.request.params?.event==='command'&&inner.params.request.params.control==='AcceptButton';
      if(ownedAccept&&(resultGate||dropOwnedResult)){
        const response=await route.fetch({timeout:remaining(rpcFetchMs),maxRedirects:0,maxRetries:0});
        assert.equal(response.status(),200,'owned_result_http');
        const bytes=await bounded(response.body(),remaining(rpcFetchMs),'owned_result_body_timeout');
        assert.ok(bytes.length<=131072,'owned_result_body_budget');
        const body=JSON.parse(bytes.toString('utf8'));
        assert.equal(body.id,request.id,'owned_result_outer_id');
        assert.equal(body.result?.payload?.id,inner.id,'owned_result_inner_id');
        assert.equal(body.result?.error,null,'owned_result_outer_error');
        const result=body.result?.payload?.result;
        assert.equal(result?.error,null,'owned_result_inner_error');
        assert.equal(result.updates.length,1,'owned_result_update_count');
        assert.ok(!result.state.sessions.some(session=>session.id===inner.params.session),'owned_child_not_retired');
        const update=result.updates[0];
        assert.equal(update.form.result.error,null,'owned_result_update_error');
        const values=update.form.result.state.items;
        assert.equal(values.find(item=>item.name==='LastOutcomeField')?.value?.value,'Черновик ожидает подтверждения','owned_result_not_prepared');
        assert.equal(Number(values.find(item=>item.name==='AppliedCountField')?.value?.value),0,'owned_result_applied_early');
        if(dropOwnedResult){dropOwnedResult=false;droppedOwnedResult++;await response.dispose();return route.abort('failed');}
        const gate=resultGate;resultGate=null;gate.arrived();
        await bounded(gate.wait,remaining(10000),'owned_result_delivery_gate_timeout');
        return route.fulfill({response});
      }
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
    await legacyDialog().waitFor({state:'visible'});
    await page.setViewportSize({width:390,height:844});
    const choiceBounds=await legacyDialog().boundingBox();
    assert.ok(choiceBounds&&choiceBounds.x>=0&&choiceBounds.x+choiceBounds.width<=390,'narrow_choice_clipped');
    await screenshot('choice.png');await page.setViewportSize({width:1320,height:900});
    await click('Next choices');await click('Previous choices');
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
  // Observe only the existing browser response. Never dispatch a second request.
  const filterReply=async(method,action)=>{
    const capture=filterCapture.begin(method);
    try{
    report.filterStage='await-response';
    const waiting=replyFor(packet=>packet.method===method);
    const [response]=await Promise.all([waiting,action(),bounded(capture.ready,remaining(rpcReplyMs),'filter_capture_timeout')]);
    report.filterStage='read-response';
    const packet=response.request().postDataJSON();
    const captured=filterCapture.consume(capture,packet.id);
    assert.equal(captured.packet.params.request.id,packet.params.request.id,'filter_capture_consumer_inner_id');
    const bytes=captured.bytes;
    assert.ok(bytes.length<=131072,'filter_reply_body_budget');
    report.filterStage='validate-envelope';
    const body=JSON.parse(bytes.toString('utf8'));
    assert.equal(body.jsonrpc,'2.0');assert.equal(body.id,packet.id);
    assert.equal(body.result?.error,null);assert.equal(body.result?.state?.uncertain,false);
    const payload=body.result.payload;
    assert.equal(payload?.jsonrpc,'2.0');assert.equal(payload?.id,packet.params.request.id);
    assert.ok(payload.result&&!payload.error);assert.equal(payload.result.error,null);
    report.filterStage='await-render-ready';
    await page.waitForFunction(()=>[...document.querySelectorAll('.configuration-catalog button')].some(b=>b.textContent==='Apply filters'&&!b.disabled),null,{timeout:remaining(rpcReplyMs)});
    return payload.result;
    }finally{filterCapture.clear(capture);}
  };
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
    await click('Документы, формы и отчёты');
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
    await reports.getByRole('cell',{name:'Кабель USB-C',exact:true}).waitFor();
    const headingBounds=await page.getByRole('heading',{name:'Receipt card',level:1,exact:true}).boundingBox();
    assert.ok(headingBounds&&headingBounds.width>=200&&headingBounds.height<160,'embedded_title_collapsed');
    await screenshot('editor.png');
    const saved=audit();verifyMainDemoAudit(saved,assert);
    await act('close-document',()=>settled(formEvent('close'),()=>docButton('Close form').click()));await active().waitFor({state:'detached'});
    const recordList=page.locator('.configuration-catalog');
    const listField=label=>recordList.getByLabel(label,{exact:true});
    const listButton=label=>recordList.getByRole('button',{name:label,exact:true});
    const expectedFilters={deletion:'all',posting:'posted',dateFrom:'2026-11-11',dateTo:'2026-11-11',descending:false};
    const checkedList=async(result,total,filters)=>{
      report.filterStage='validate-catalog';
      const value=result.state.catalog;assert.equal(value.navigation.total,total,'filter_exact_total');
      assert.equal(value.navigation.page,1);assert.equal(value.navigation.pages,1);
      assert.equal(value.rows.length,total,'filter_exact_rows');
      if(filters)assert.deepEqual(value.navigation.filters,filters,'filter_exact_navigation');
      else assert.equal(Object.hasOwn(value.navigation,'filters'),false,'reset_omits_default_filters');
      report.filterStage='await-visible-rows';
      await page.waitForFunction(total=>document.querySelectorAll('.configuration-catalog tbody tr').length===total,total,{timeout:remaining(rpcReplyMs)});
      assert.equal(await recordList.locator('tbody tr').count(),total,'filter_visible_rows');
      if(total){assert.equal(value.rows[0].number,'RQA1');assert.equal(value.rows[0].posted,true);
        await recordList.getByRole('cell',{name:'RQA1',exact:true}).waitFor();}
    };
    await act('filter-posted',()=>listField('Posting filter').selectOption('posted'));
    await act('filter-date-from',()=>listField('Date from (inclusive)').fill('2026-11-11'));
    await act('filter-date-through',()=>listField('Date through (inclusive)').fill('2026-11-11'));
    await act('apply-posted-day',async()=>checkedList(await filterReply('application.catalogFilter',()=>listButton('Apply filters').click()),1,expectedFilters));
    await act('unapplied-date-draft',()=>listField('Date through (inclusive)').fill('2026-11-12'));
    await act('report-repaint-retains-filter-draft',async()=>{
      const value=await filterReply('application.report',()=>reports.getByRole('button',{name:'Show saved stock',exact:true}).click());
      await checkedList(value,1,expectedFilters);
      report.filterStage='validate-unapplied-draft';
      assert.equal(await listField('Date through (inclusive)').inputValue(),'2026-11-12','filter_draft_lost_on_repaint');
      report.filterStage='draft-preserved';
    });
    await act('refresh-restores-applied-filter',async()=>{
      const value=await filterReply('application.catalog',()=>listButton('Refresh records').click());
      await checkedList(value,1,expectedFilters);
      await page.waitForFunction(()=>document.querySelector('.configuration-catalog [aria-label="Date through (inclusive)"]')?.value==='2026-11-11',null,{timeout:remaining(rpcReplyMs)});
      assert.equal(await listField('Date through (inclusive)').inputValue(),'2026-11-11','refresh_did_not_restore_applied_date');
      assert.equal(await listField('Posting filter').inputValue(),'posted');
    });
    await act('excluded-date-from',()=>listField('Date from (inclusive)').fill('2026-11-12'));
    await act('excluded-date-through',()=>listField('Date through (inclusive)').fill('2026-11-12'));
    await act('apply-excluded-posted-day',async()=>checkedList(await filterReply('application.catalogFilter',()=>listButton('Apply filters').click()),0,{...expectedFilters,dateFrom:'2026-11-12',dateTo:'2026-11-12'}));
    await act('restore-date-from',()=>listField('Date from (inclusive)').fill('2026-11-11'));
    await act('restore-date-through',()=>listField('Date through (inclusive)').fill('2026-11-11'));
    await act('filter-unposted',()=>listField('Posting filter').selectOption('unposted'));
    await act('apply-unposted-day',async()=>checkedList(await filterReply('application.catalogFilter',()=>listButton('Apply filters').click()),0,{...expectedFilters,posting:'unposted'}));
    await act('reset-record-filters',async()=>{
      await checkedList(await filterReply('application.catalogFilter',()=>listButton('Reset filters').click()),1,null);
      await page.waitForFunction(()=>document.querySelector('.configuration-catalog [aria-label="Posting filter"]')?.value==='all',null,{timeout:remaining(rpcReplyMs)});
      assert.equal(await listField('Posting filter').inputValue(),'all');assert.equal(await listField('Deletion filter').inputValue(),'all');
      assert.equal(await listField('Date from (inclusive)').inputValue(),'');assert.equal(await listField('Date through (inclusive)').inputValue(),'');
      assert.equal(await listField('Descending order').isChecked(),false);
    });
    assert.deepEqual(audit(),saved,'readonly_record_filters_changed_database');
    report.recordFilters={postedOnDay:1,dateExcluded:0,unpostedOnDay:0,reset:1,unappliedDraftSurvivedPaint:true,refreshRestoredApplied:true,durableUnchanged:true};
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
  await scenario('owned_operation_draft_confirmation_without_database_write',async()=>{
    const saved=audit();const start=actionLog.length;
    await page.setViewportSize({width:1320,height:980});
    await click('Документы, формы и отчёты');
    const nav=page.getByRole('navigation',{name:'Declared forms',exact:true});
    assert.equal(await nav.getByRole('button',{name:'Подготовка изменений',exact:true}).count(),0,'owned_child_not_navigation');
    const observed=async(method,action)=>{
      report.draftStage='await-response';
      const waiting=replyFor(packet=>packet.method===method).catch(()=>{throw Error('draft_response_wait_failed');});
      const [response]=await Promise.all([waiting,action().catch(()=>{throw Error('draft_action_failed');})]);
      report.draftStage='read-response';
      const packet=response.request().postDataJSON();
      let bytes;
      try{bytes=await bounded(response.body(),remaining(rpcFetchMs),'draft_reply_timeout');}
      catch(error){throw Error(error?.message==='draft_reply_timeout'?'draft_reply_timeout':'draft_reply_read_failed');}
      assert.ok(bytes.length<=131072,'draft_reply_budget');
      report.draftStage='validate-envelope';
      let body;try{body=JSON.parse(bytes.toString('utf8'));}catch{throw Error('draft_reply_json');}
      assert.equal(body.id,packet.id,'draft_outer_id');
      assert.equal(body.result?.error,null,'draft_outer_error');
      assert.equal(body.result?.state?.uncertain,false,'draft_uncertain');
      const payload=body.result.payload;
      assert.equal(payload?.id,packet.params.request.id,'draft_inner_id');
      assert.ok(!payload.error&&payload.result,'draft_inner_error');
      assert.equal(payload.result.error,null,'draft_form_error');
      report.draftStage='await-idle';
      try{await idle();}catch{throw Error('draft_idle_timeout');}
      report.draftStage='complete';return payload.result;
    };
    const command=async(label)=>{let result;await act('draft:'+label,async()=>{result=await observed('application.form',()=>docButton(label).click());});return result;};
    const answer=async(label)=>{let result;await act('draft-answer:'+label,async()=>{result=await observed('application.answerDialog',()=>page.locator('.configuration-dialog').getByRole('button',{name:label,exact:true}).click());});return result;};
    const ownerValues=(result,amount,count)=>{
      const forms=[result.form,...(result.updates||[]).map(update=>update.form)].filter(Boolean);
      const owner=forms.find(form=>form.result.state.items.some(item=>item.name==='AppliedCountField'));
      assert.ok(owner,'draft_owner_projection_missing');
      const value=name=>owner.result.state.items.find(item=>item.name===name).value;
      assert.equal(value('AmountField').type,'Number');assert.equal(Number(value('AmountField').value),amount,'draft_amount');
      assert.equal(Number(value('AppliedCountField').value),count,'draft_applied_once');
    };
    await act('open-operation-draft',()=>settled(packet=>packet.method==='application.open',()=>nav.getByRole('button',{name:'Черновик операции',exact:true}).click()));
    await command('Подготовить изменения');
    await commit('DraftTitle','Поставка кабеля');await commit('Amount','123.45');await commit('Comment','Подготовлено без записи');
    await act('draft-keep-open',()=>settled(formEvent('change'),()=>docField('KeepOpen').check()));
    const veto=await command('Вернуть черновик');
    assert.equal(veto.state.sessions.length,2,'draft_keep_open_veto');assert.equal(veto.updates.length,0);
    await docField('Amount').waitFor();assert.equal(await docField('Amount').inputValue(),'123.45');
    await act('draft-allow-close',()=>settled(formEvent('change'),()=>docField('KeepOpen').uncheck()));
    ownerValues(await command('Вернуть черновик'),0,0);
    await command('Применить черновик');ownerValues(await answer('Cancel'),0,0);
    await command('Подготовить изменения');
    await docField('Amount').waitFor();assert.equal(await docField('Amount').inputValue(),'123.45','prepared_draft_reopened');
    await commit('Amount','99');ownerValues(await command('Отмена'),0,0);
    await command('Применить черновик');ownerValues(await answer('Yes'),123.45,1);
    const repeat=await command('Применить черновик');ownerValues(repeat,123.45,1);assert.deepEqual(repeat.dialogs,[],'no_repeated_confirmation');
    await command('О черновике');ownerValues(await answer('Continue'),123.45,1);
    await command('Close form');await active().waitFor({state:'detached'});
    await act('Справочники',async()=>{
      const switching=page.waitForResponse(response=>new URL(response.url()).origin===origin&&new URL(response.url()).pathname==='/rpc'&&response.status()===200&&response.request().postDataJSON().method==='demo.select'&&response.request().postDataJSON().params.surface==='catalogs',{timeout:remaining(rpcReplyMs)});
      const [response]=await Promise.all([switching,button('Справочники').click()]);
      const bytes=await bounded(response.body(),remaining(rpcFetchMs),'draft_switch_reply_timeout');
      assert.ok(bytes.length<=131072,'draft_switch_reply_budget');
      const value=JSON.parse(bytes.toString('utf8'));
      assert.equal(value.jsonrpc,'2.0');assert.equal(value.id,response.request().postDataJSON().id);
      assert.equal(value.result?.error,null);assert.equal(value.result?.state?.surface,'catalogs');
      assert.equal(value.result?.state?.uncertain,false);assert.equal(value.result?.state?.canSwitch,true);
      await page.getByRole('navigation',{name:'Catalogs',exact:true}).waitFor({state:'visible'});
    });
    assert.equal(actionLog.length-start,22,'draft_action_count');
    assert.deepEqual(audit(),saved,'memory_draft_changed_database');
    report.operationDraft={keepOpenVeto:true,preparedReopened:true,childCancelPreserved:true,appliedAmount:'123.45',appliedCount:1,repeatDidNotApply:true,messageReadOnly:true,durableUnchanged:true};
  });
  await scenario('owned_result_delayed_delivery_independent_draft_and_loss_without_replay',async()=>{
    const saved=audit(),start=actionLog.length;
    await click('Документы, формы и отчёты');
    const nav=page.getByRole('navigation',{name:'Declared forms',exact:true});
    const tabs=page.getByRole('navigation',{name:'Open forms',exact:true}).getByRole('button');
    const panels=page.locator('.configuration-form-panels > section');
    const openOwner=()=>settled(packet=>packet.method==='application.open',()=>nav.getByRole('button',{name:'Черновик операции',exact:true}).click());
    const command=label=>settled(formEvent('command'),()=>docButton(label).click());
    await act('recovery-open-owner-a',openOwner);
    await act('recovery-open-child-a',()=>command('Подготовить изменения'));
    await act('recovery-retain-raw-child-a',()=>docField('Comment').fill('  independent raw draft  '));
    const childInput=await docField('Comment').getAttribute('id');
    await act('recovery-inspect-paused-owner-a',()=>tabs.nth(0).click());
    assert.equal(await docButton('Подготовить изменения').isDisabled(),true,'owned_paused_command_enabled');
    assert.equal(await docButton('Close form').isDisabled(),true,'owned_paused_close_enabled');
    const beforePaused=requests.length;
    await act('recovery-paused-owner-cannot-dispatch',()=>docButton('Подготовить изменения').evaluate(node=>{node.click();node.click();}));
    assert.equal(requests.length,beforePaused,'owned_paused_dispatched');
    await act('recovery-return-child-a',()=>tabs.nth(1).click());
    assert.equal(await docField('Comment').inputValue(),'  independent raw draft  ','owned_independent_draft_lost');
    await act('recovery-open-owner-b',openOwner);
    await act('recovery-open-child-b',()=>command('Подготовить изменения'));
    await commit('Amount','42.50');
    let arrived,release;const atGate=new Promise(resolve=>{arrived=resolve;}),wait=new Promise(resolve=>{release=resolve;});resultGate={arrived,wait};
    const acceptBefore=requests.filter(request=>request.control==='AcceptButton').length;
    await act('recovery-delayed-child-result',async()=>{
      const reply=replyFor(formEvent('command'));
      await docButton('Вернуть черновик').evaluate(node=>{node.click();node.click();});
      try{
        await bounded(atGate,remaining(10000),'owned_result_gate_not_reached');
        assert.equal(await panels.count(),4,'owned_result_retired_before_delivery');
        assert.equal(await docButton('Вернуть черновик').isDisabled(),true,'owned_result_busy_enabled');
      }finally{release();}
      await reply;await idle();
    });
    assert.equal(requests.filter(request=>request.control==='AcceptButton').length,acceptBefore+1,'owned_result_duplicate_accept');
    assert.equal(await panels.count(),3,'owned_result_not_retired_after_delivery');
    await act('recovery-reopen-prepared-child-b',()=>command('Подготовить изменения'));
    assert.equal(await docField('Amount').inputValue(),'42.50','owned_result_reopen_value');
    const independent=page.locator('[id="'+childInput+'"]');
    assert.equal(await independent.inputValue(),'  independent raw draft  ','owned_independent_draft_lost');
    dropOwnedResult=true;
    await act('recovery-lose-confirmed-child-result',()=>docButton('Вернуть черновик').click());
    await page.getByText('Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.',{exact:true}).waitFor();
    assert.equal(droppedOwnedResult,1,'owned_result_loss_not_observed');
    const afterLoss=requests.length,acceptAfterLoss=requests.filter(request=>request.control==='AcceptButton').length;
    await act('recovery-inspect-without-replay',()=>button('Восстановить состояние').click());
    await idle();
    assert.ok(snapshotMethods(afterLoss).every(method=>['demo.snapshot','application.hello','application.form'].includes(method)),'owned_result_recovery_mutated');
    assert.ok(requests.slice(afterLoss).filter(request=>request.inner==='application.form').every(request=>request.nested==='form.snapshot'),'owned_result_recovery_form_mutated');
    assert.equal(requests.filter(request=>request.control==='AcceptButton').length,acceptAfterLoss,'owned_result_recovery_replayed');
    const copy=page.locator('.draft-recovery-value');
    assert.ok((await copy.allTextContents()).includes('CommentField:   independent raw draft  '),'owned_result_raw_copy_lost');
    assert.equal(await independent.isDisabled(),true,'owned_result_unknown_draft_unlocked');
    assert.deepEqual(audit(),saved,'owned_result_changed_database');
    assert.equal(actionLog.length-start,14,'owned_result_action_count');
    report.ownedResultRecovery={delayedCompletionOnce:true,pausedOwnerCannotDispatch:true,independentRawDraftRetained:true,confirmedCloseLost:true,noReplay:true,copyPreserved:true,durableUnchanged:true};
  });
  await scenario('dialog_confirmation_once_and_lost_answer_without_replay',async()=>{
    const saved=audit(),start=actionLog.length;
    await act('dialog-restart-owned-host',async()=>{await stopHost();await startHost();await page.goto(url);});
    await click('Документы, формы и отчёты');
    const nav=page.getByRole('navigation',{name:'Declared forms',exact:true});
    const dialog=()=>page.locator('.configuration-dialog:not([hidden])');
    const answerButton=name=>dialog().getByRole('button',{name,exact:true});
    const openOwner=()=>settled(packet=>packet.method==='application.open',()=>nav.getByRole('button',{name:'Черновик операции',exact:true}).click());
    const command=label=>settled(formEvent('command'),()=>docButton(label).click());
    const answer=label=>settled(packet=>packet.method==='application.answerDialog',()=>answerButton(label).click());
    await act('dialog-owner-a',openOwner);
    await act('dialog-child-a',()=>command('Подготовить изменения'));
    await act('dialog-retain-independent-draft',()=>docField('Comment').fill('  dialog independent raw draft  '));
    const childInput=await docField('Comment').getAttribute('id');
    await act('dialog-owner-b',openOwner);
    await act('dialog-child-b',()=>command('Подготовить изменения'));
    await commit('Amount','11');
    await act('dialog-return-first',()=>command('Вернуть черновик'));
    await act('dialog-confirm-first',()=>command('Применить черновик'));
    const answersBefore=requests.filter(request=>request.inner==='application.answerDialog').length;
    await act('dialog-escape-is-not-answer',async()=>{
      await page.keyboard.press('Escape');assert.equal(await dialog().count(),1,'dialog_escape_closed');
      assert.equal(await docButton('Подготовить изменения').isDisabled(),true,'dialog_owner_not_paused');
      assert.equal(requests.filter(request=>request.inner==='application.answerDialog').length,answersBefore,'dialog_escape_answered');
    });
    let arrived,release;const atGate=new Promise(resolve=>{arrived=resolve;}),wait=new Promise(resolve=>{release=resolve;});
    dialogGate={arrived,wait};
    await act('dialog-delayed-yes-once',async()=>{
      const reply=replyFor(packet=>packet.method==='application.answerDialog');
      await answerButton('Yes').evaluate(node=>{node.click();node.click();});
      try{await bounded(atGate,remaining(10000),'dialog_answer_not_received');
        assert.equal(await answerButton('Yes').isDisabled(),true,'dialog_answer_busy_enabled');
        assert.equal(Number(await docField('Amount').inputValue()),0,'dialog_answer_applied_before_delivery');
      }finally{release();}
      await reply;await idle();
    });
    assert.equal(requests.filter(request=>request.inner==='application.answerDialog').length,answersBefore+1,'dialog_answer_repeated');
    assert.equal(Number(await docField('Amount').inputValue()),11,'dialog_first_amount');
    const independent=page.locator('[id="'+childInput+'"]');
    assert.equal(await independent.inputValue(),'  dialog independent raw draft  ','dialog_independent_draft_lost');
    await act('dialog-no-repeat-without-pending',()=>command('Применить черновик'));
    assert.equal(await dialog().count(),0,'dialog_empty_reconfirmed');
    await act('dialog-prepare-no',()=>command('Подготовить изменения'));
    await commit('Amount','22');
    await act('dialog-return-no',()=>command('Вернуть черновик'));
    await act('dialog-confirm-no',()=>command('Применить черновик'));
    await act('dialog-answer-no',()=>answer('No'));
    assert.equal(Number(await docField('Amount').inputValue()),11,'dialog_no_applied');
    await act('dialog-prepare-cancel',()=>command('Подготовить изменения'));
    await commit('Amount','33');
    await act('dialog-return-cancel',()=>command('Вернуть черновик'));
    await act('dialog-confirm-cancel',()=>command('Применить черновик'));
    await act('dialog-answer-cancel',()=>answer('Cancel'));
    assert.equal(Number(await docField('Amount').inputValue()),11,'dialog_cancel_applied');
    await act('dialog-confirm-loss',()=>command('Применить черновик'));
    dropDialog=true;
    await act('dialog-lose-confirmed-answer',()=>answerButton('Yes').click());
    await page.getByText('Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.',{exact:true}).waitFor();
    assert.equal(droppedDialog,1,'dialog_loss_not_observed');
    const afterLoss=requests.length;
    await act('dialog-readonly-inspection',()=>button('Восстановить состояние').click());await idle();
    assert.ok(snapshotMethods(afterLoss).every(method=>['demo.snapshot','application.hello','application.form'].includes(method)),'dialog_recovery_mutated');
    assert.ok(requests.slice(afterLoss).filter(request=>request.inner==='application.form').every(request=>request.nested==='form.snapshot'),'dialog_recovery_form_mutated');
    assert.ok((await page.locator('.draft-recovery-value').allTextContents()).includes('CommentField:   dialog independent raw draft  '),'dialog_raw_copy_lost');
    assert.equal(await independent.isDisabled(),true,'dialog_unknown_draft_unlocked');
    assert.deepEqual(audit(),saved,'dialog_changed_database');
    assert.equal(actionLog.length-start,26,'dialog_action_count');
    report.dialogRecovery={delayedAnswerOnce:true,escapeNotAnswer:true,noDiscarded:true,cancelDeferred:true,
      confirmedAnswerLost:true,independentDraftRetained:true,copyPreserved:true,noReplay:true,durableUnchanged:true};
  });
  assert.equal(actionLog.length,121,'total_action_count');
  report.actions=actionLog;report.actionCount=actionLog.length;
  report.durable={authoredWarehouses:70,uiCreatedKinds:1,uiCreatedProducts:1,uiCreatedReceipts:1,
    lostApplyResponses:dropped,lostDocumentResponses:droppedDocument,recoveryReadOnly:true};
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','source_changed');
  assert.equal(git('rev-parse','HEAD'),report.sourceCommit,'source_commit_changed');
  for(const [name,digest] of Object.entries(source)){check();assert.equal(sha256(await readFile(path.join(repo,name))),digest,'source_bytes_changed');}
  assert.equal(results.length,5);report.status='PASS';report.rpcRequests=rpc;
}
// Reserve 20 seconds for verified bounded cleanup within the 180s total.
const deadline=setTimeout(abort,Math.max(0,workDeadline-Date.now()));
const totalTimer=setTimeout(()=>{abort();process.exit(1);},Math.max(0,totalDeadline-Date.now()));
// Export only fixed codes. Assertion messages can append paths/actual values;
// neither those details nor raw browser logs belong in the artifact.
const safeFailureCodes=new Set([
  'dialog_answer_http','dialog_answer_body_timeout','dialog_answer_body_budget','dialog_answer_outer_id','dialog_answer_inner_id','dialog_answer_outer_error','dialog_answer_inner_error','dialog_answer_form_error','dialog_answer_count','dialog_answer_amount','dialog_answer_gate_timeout','dialog_escape_closed','dialog_owner_not_paused','dialog_escape_answered','dialog_answer_not_received','dialog_answer_busy_enabled','dialog_answer_applied_before_delivery','dialog_answer_repeated','dialog_first_amount','dialog_independent_draft_lost','dialog_empty_reconfirmed','dialog_no_applied','dialog_cancel_applied','dialog_loss_not_observed','dialog_recovery_mutated','dialog_recovery_form_mutated','dialog_raw_copy_lost','dialog_unknown_draft_unlocked','dialog_changed_database','dialog_action_count',
  'draft_response_wait_failed','draft_action_failed','draft_reply_timeout','draft_reply_read_failed',
  'draft_reply_budget','draft_reply_json','draft_outer_id','draft_outer_error','draft_uncertain',
  'draft_inner_id','draft_inner_error','draft_form_error','draft_idle_timeout',
  'filter_capture_pending','filter_capture_method','filter_capture_duplicate','filter_capture_request_origin',
  'filter_capture_response_origin','filter_capture_request_id','filter_capture_http','filter_capture_json',
  'filter_capture_outer_id','filter_capture_inner_id','filter_capture_retired','filter_capture_failed',
  'filter_capture_cleanup','filter_capture_transport','filter_capture_timeout','filter_capture_consumed','filter_capture_consumer_id','filter_capture_consumer_inner_id',
  'owned_result_outer_id','owned_result_inner_id','owned_result_recovery_form_mutated',
  'owned_child_not_navigation','owned_child_not_retired','owned_independent_draft_lost','owned_paused_close_enabled','owned_paused_command_enabled','owned_paused_dispatched','owned_result_action_count','owned_result_applied_early','owned_result_body_budget','owned_result_body_timeout','owned_result_busy_enabled','owned_result_changed_database','owned_result_delayed_delivery_independent_draft_and_loss_without_replay','owned_result_delivery_gate_timeout','owned_result_duplicate_accept','owned_result_gate_not_reached','owned_result_http','owned_result_inner_error','owned_result_loss_not_observed','owned_result_not_prepared','owned_result_not_retired_after_delivery','owned_result_outer_error','owned_result_raw_copy_lost','owned_result_recovery_mutated','owned_result_recovery_replayed','owned_result_reopen_value','owned_result_retired_before_delivery','owned_result_unknown_draft_unlocked','owned_result_update_count','owned_result_update_error',
  'filter_exact_total','filter_exact_rows','filter_exact_navigation','filter_visible_rows',
  'filter_draft_lost_on_repaint','filter_reply_body_budget','filter_reply_body_timeout',
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
  for(const name of ['list.png','editor.png','narrow.png','choice.png']){
    try{const file=path.join(output,name),stat=await lstat(file);assert.ok(stat.isFile()&&!stat.isSymbolicLink()&&stat.size<=4*1024*1024);const bytes=await readFile(file);assert.equal(bytes.length,stat.size);images[name]={bytes:bytes.length,sha256:sha256(bytes)};}
    catch{await rm(path.join(output,name),{force:true});report.status='FAIL';report.artifacts='missing_or_invalid_screenshot';}
  }
  const raw=JSON.stringify(report,null,2)+'\n';
  assert.ok(Buffer.byteLength(raw)<=65536,'report_budget');
  assert.ok(!tokens.some(token=>raw.includes(token)),'capability_leak');
  await writeFile(path.join(output,'result.json'),raw);
  await writeFile(path.join(output,'manifest.json'),JSON.stringify({schema:1,source:report.sourceCommit,tree:report.binding?.tree,resultSha256:sha256(raw),images},null,2)+'\n');
  assert.ok((await readdir(output)).every(name=>['result.json','manifest.json','list.png','editor.png','narrow.png','choice.png'].includes(name)));
}
clearTimeout(totalTimer);
console.log(JSON.stringify({status:report.status,completed:results.length,total:5,source:report.sourceCommit,failure:report.failure}));if(failure||report.status!=='PASS')process.exitCode=1;
