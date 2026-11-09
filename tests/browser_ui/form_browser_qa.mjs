/** Opt-in owned form-browser acquisition. No native-platform parity claim. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile,rm,lstat,readdir} from 'node:fs/promises';
import {readFileSync,readlinkSync,lstatSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {launchOutputReader,allowedRequest,childEnvironment,ownBrowserPid,
  commandLineArgs,sandboxCommand,sandboxStatus,sha256} from './support.mjs';

const startedAt=Date.now();
const workDeadline=startedAt+160000;
const totalDeadline=startedAt+180000;
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
const screenshots=['estimate.png','product-narrow.png','order-table-narrow.png','order-editor-narrow.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['edit_then_command_exact_decimal','duplicate_click_close_cancel_and_reattach',
  'sqlite_save_close_and_durable_readback','table_intake_edit_delete_save_reopen',
  'existing_order_edit_discard_save_reopen'];
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
const runPython=args=>execFileSync(python,args,{cwd:repo,env,encoding:'utf8',timeout:remaining(15000),maxBuffer:16384,stdio:['ignore','pipe','pipe']});

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
async function startHost(example,database){
  check();assert.ok(!host&&!hostGroup,'previous_host_live');
  const args=['-m','yadinassi.ui.form_app',path.join(repo,'examples/forms',example)];
  if(database)args.push('--f',database);
  host=spawn(python,args,{cwd:repo,env,detached:true,stdio:['ignore','pipe','ignore']});
  const parse=launchOutputReader();let settled=false;
  url=await bounded(new Promise((resolve,reject)=>{
    const finish=(callback,value)=>{if(!settled){settled=true;callback(value);}};
    host.once('error',()=>finish(reject,Error('host_spawn_failed')));
    host.once('spawn',()=>{try{hostGroup=processIdentity(host.pid);}catch{finish(reject,Error('host_identity_failed'));}});
    host.once('exit',()=>finish(reject,Error('host_exited_before_launch')));
    host.stdout.on('data',data=>{
      if(settled)return; // Drain, never retain launcher output or capability URLs.
      try{const found=parse(data);if(found){origin=found.origin;tokens.push(found.hash.slice(9));finish(resolve,found.href);}}
      catch{finish(reject,Error('invalid_launch_output'));}
    });
  }),remaining(15000),'host_start_timeout');
}
const button=name=>page.getByRole('button',{name,exact:true});
const field=name=>page.getByLabel(name,{exact:true});
const idle=()=>page.waitForFunction(()=>document.querySelector('[aria-busy]')?.getAttribute('aria-busy')==='false',null,{timeout:remaining(10000)});
async function scenario(name,fn){check();phase=name;await fn();check();results.push({name,status:'PASS'});}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0,'browser_storage_not_empty');
  assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','examples/forms','tests/browser_ui',
    'tests/test_ui_browser_qa_contract.py','tests/test_form_browser_qa_contract.py','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-form-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'yadinassi-form-browser-'));
  home=path.join(owned,'home');await mkdir(home);
  env=childEnvironment(process.env,home);env.PYTHONPATH=repo;
  phase='sandbox_launch';
  const childrenPath='/proc/'+process.pid+'/task/'+process.pid+'/children';
  const priorChildren=new Set(readFileSync(childrenPath,'utf8').trim().split(/\s+/).filter(Boolean));
  const previousTmp=process.env.TMPDIR;
  try{
    // Playwright creates its profile from the parent's temp directory, not launch env.
    process.env.TMPDIR=home;
    browser=await chromium.launch({channel:'chromium',headless:true,chromiumSandbox:true,env,timeout:remaining(20000)});
  }finally{
    if(previousTmp===undefined)delete process.env.TMPDIR;else process.env.TMPDIR=previousTmp;
    // Capture the newly launched direct owned group even if CDP setup later fails.
    const children=readFileSync(childrenPath,'utf8').trim().split(/\s+/).filter(pid=>pid&&!priorChildren.has(pid));
    assert.ok(children.length<=1,'unexpected_launch_children');
    if(children.length){
      browserGroup=processIdentity(Number(children[0]));
      assert.equal(readlinkSync('/proc/'+browserGroup.pid+'/exe'),chromium.executablePath(),'browser_executable_mismatch');
      const bytes=readFileSync('/proc/'+browserGroup.pid+'/cmdline');assert.ok(bytes.length<=16384,'browser_command_budget');
      const args=commandLineArgs(bytes);sandboxCommand(args);
      const profiles=args.filter(arg=>arg.startsWith('--user-data-dir='));
      assert.equal(profiles.length,1,'browser_profile_missing');
      const relative=path.relative(home,profiles[0].slice('--user-data-dir='.length));
      assert.ok(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative),'browser_profile_not_owned');
    }
  }
  check();assert.ok(browserGroup,'browser_process_missing');report.browser=browser.version();
  const cdp=await bounded(browser.newBrowserCDPSession(),remaining(5000),'cdp_setup_timeout');
  const info=await bounded(cdp.send('SystemInfo.getProcessInfo'),remaining(5000),'cdp_process_timeout');
  assert.equal(ownBrowserPid(info.processInfo),browserGroup.pid,'browser_pid_mismatch');
  await bounded(cdp.detach(),remaining(5000),'cdp_detach_timeout');
  context=await bounded(browser.newContext({viewport:{width:1100,height:850},locale:'en-US',timezoneId:'UTC',
    acceptDownloads:false,serviceWorkers:'block'}),remaining(10000),'context_timeout');
  context.setDefaultTimeout(10000);context.setDefaultNavigationTimeout(15000);
  const probe=await context.newPage();await probe.goto('chrome://sandbox');
  report.sandbox={requested:true,commandVerified:true,...sandboxStatus(await probe.locator('body').innerText())};
  await probe.close();
  await context.route('**/*',route=>{
    const target=route.request().url();
    if(aborted||!allowedRequest(target,origin))return route.abort();
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=100){abort();return route.abort().catch(()=>{});}
      rpc++;
    }
    return route.continue();
  });
  page=await context.newPage();
  await startHost('estimate');await page.goto(url);
  await page.getByRole('heading',{name:'Estimate calculator',exact:true}).waitFor();
  await scenario(scenarioNames[0],async()=>{
    await field('Unit price').fill('7.25');
    await button('Calculate').click(); // Immediate pointer action must flush the exact draft.
    await page.waitForFunction(()=>document.querySelector('input[aria-label="Total"]')?.value==='21.75');
    await idle();assert.equal(await field('Total').inputValue(),'21.75');
    await screenshot('estimate.png');
  });
  await scenario(scenarioNames[1],async()=>{
    const events=[];
    const observe=request=>{
      if(request.url()!==origin+'/rpc')return;
      const data=JSON.parse(request.postData());
      if(data.method==='form.event')events.push(data.params.event);
    };
    page.on('request',observe);
    try{
      await page.evaluate(()=>{const control=[...document.querySelectorAll('button')].find(button=>button.textContent==='Calculate');control.click();control.click();});
      await idle();assert.deepEqual(events,['command']);
    }finally{page.off('request',observe);}
    await field('Unit price').fill('9');await button('Close form').click();
    await page.getByText('Run the command before closing, or stop the launcher to discard edits.',{exact:true}).waitFor();
    await idle();await page.goto(url);
    await page.getByRole('heading',{name:'Estimate calculator',exact:true}).waitFor();
    assert.equal(await field('Unit price').inputValue(),'9');
    await button('Calculate').click();await idle();
    assert.equal(await field('Total').inputValue(),'27');
    await button('Close form').click();
    await page.getByText('This form is closed. You can close this tab.',{exact:true}).waitFor();
    await stopHost();
  });
  await scenario(scenarioNames[2],async()=>{
    const database=path.join(owned,'products.sqlite');
    runPython(['-m','yadinassi','--create-db',database,'--import-xml',path.join(repo,'examples/forms/product-intake/configuration')]);
    await page.close();page=await context.newPage();
    await startHost('product-intake',database);await page.goto(url);
    await page.getByRole('heading',{name:'Create a product',exact:true}).waitFor();
    for(const [name,value] of [['Code','B001'],['Description','Browser-owned product'],['Amount','18.75']]){
      await field(name).fill(value);await field(name).press('Enter');await idle();
    }
    await button('Create product').click();
    await page.getByText('Product saved',{exact:true}).waitFor();await idle();
    assert.equal(await button('Create product').isDisabled(),true);
    await page.setViewportSize({width:390,height:844});await screenshot('product-narrow.png');
    await button('Close form').click();
    await page.getByText('This form is closed. You can close this tab.',{exact:true}).waitFor();
    await stopHost();
    // A fresh CLI process opens the SQLite file only after the form host is gone.
    const readback=runPython(['-m','yadinassi','--f',database,'-c','Message(Catalogs.Products.FindByCode("B001").Amount);']);
    assert.equal(readback.trim(),'18,75');report.durable={reopenedAfterHostClose:true,exactAmount:'18.75'};
  });
  await scenario(scenarioNames[3],async()=>{
    const database=path.join(owned,'orders.sqlite');
    runPython(['-m','yadinassi','--create-db',database,'--import-xml',path.join(repo,'examples/forms/order-intake/configuration')]);
    await page.close();page=await context.newPage();await page.setViewportSize({width:1100,height:850});
    await startHost('order-intake',database);await page.goto(url);
    await page.getByRole('heading',{name:'Create an order',exact:true}).waitFor();
    for(const [name,value] of [['Order code','B002'],['Description','Browser-owned order']]){
      await field(name).fill(value);await field(name).press('Enter');await idle();
    }
    for(const [id,description,quantity,price] of [[1,'Cable','1.25','2.30'],[2,'Remove me','9','9'],[3,'Service','2','3.10']]){
      // Every Add after the first must flush the preceding row's price draft.
      await button('Add line').click();await idle();
      assert.equal(await button('Selected row '+id+' in Order lines').getAttribute('aria-pressed'),'true');
      for(const [column,value] of [['Description',description],['Quantity',quantity]]){
        await field(column+', row '+id).fill(value);await field(column+', row '+id).press('Enter');await idle();
      }
      await field('Price, row '+id).fill(price);
    }
    // Selection flushes the last draft before setting the requested owned identity.
    await button('Select row 2 in Order lines').click();await idle();
    assert.equal(await field('Price, row 3').inputValue(),'3.10');
    assert.equal(await button('Selected row 2 in Order lines').getAttribute('aria-pressed'),'true');
    await button('Delete selected line').click();await idle();
    assert.equal(await field('Description, row 2').count(),0);
    assert.equal(await field('Description, row 1').inputValue(),'Cable');
    assert.equal(await field('Description, row 3').inputValue(),'Service');
    assert.equal(await page.getByRole('region',{name:'Order lines',exact:true}).locator('tbody tr').count(),2);
    await button('Recalculate').click();await idle();
    assert.equal(await field('Total').inputValue(),'9.08');
    assert.equal(await field('Amount, row 1').inputValue(),'2.88');
    assert.equal(await field('Amount, row 3').inputValue(),'6.20');
    // Invalid drafts stop commands and selection before either may emit an RPC.
    await field('Price, row 1').fill('not-a-number');
    const beforeInvalid=rpc;
    await button('Recalculate').click();await idle();
    assert.equal(await page.getByRole('alert').isVisible(),true);
    assert.equal(rpc,beforeInvalid,'invalid_command_draft_sent');
    await button('Select row 3 in Order lines').click();await idle();
    assert.equal(rpc,beforeInvalid,'invalid_selection_draft_sent');
    // The final price is intentionally not submitted with Enter or blur first.
    await field('Price, row 1').fill('2.35');
    await button('Save order').click();await idle();
    assert.equal(await field('Status').inputValue(),'Order saved');
    assert.equal(await field('Total').inputValue(),'9.14');
    assert.equal(await field('Amount, row 1').inputValue(),'2.94');
    assert.equal(await field('Amount, row 3').inputValue(),'6.20');
    for(const name of ['Add line','Delete selected line','Recalculate','Save order'])
      assert.equal(await button(name).isDisabled(),true);
    for(const name of ['Order code','Description','Description, row 1','Quantity, row 1','Price, row 3'])
      assert.equal(await field(name).isEditable(),false);
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('region',{name:'Order lines',exact:true}).evaluate(node=>node.scrollIntoView({block:'start'}));
    assert.equal(await field('Description, row 1').isVisible(),true);
    assert.equal(await field('Description, row 3').isVisible(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'narrow_page_overflow');
    await screenshot('order-table-narrow.png');
    await button('Close form').click();
    await page.getByText('This form is closed. You can close this tab.',{exact:true}).waitFor();
    await stopHost();
    // A new CLI process verifies the whole owner and both stored rows after close.
    const readback=runPython(['-m','yadinassi','--f',database,'-c',
      'O=Catalogs.Orders.FindByCode("B002").GetObject(); '+
      'If O.Code<>"B002" Or O.Description<>"Browser-owned order" Or O.Total<>9.14 Or O.Lines.Count()<>2 Then Raise "order readback"; EndIf; '+
      'A=O.Lines.Get(0); B=O.Lines.Get(1); '+
      'If A.ItemDescription<>"Cable" Or A.Quantity<>1.25 Or A.Price<>2.35 Or A.Amount<>2.94 Then Raise "first row readback"; EndIf; '+
      'If B.ItemDescription<>"Service" Or B.Quantity<>2 Or B.Price<>3.10 Or B.Amount<>6.20 Then Raise "second row readback"; EndIf; '+
      'N=0; S=Catalogs.Orders.Select(); While S.Next() Do N=N+1; EndDo; '+
      'If N<>1 Then Raise "record count"; EndIf; Message("ORDER_READBACK_OK");']);
    assert.equal(readback.trim(),'ORDER_READBACK_OK');
    report.tableDurable={reopenedAfterHostClose:true,records:1,rows:2,exactTotal:'9.14',rowOrder:['Cable','Service']};
  });
  await scenario(scenarioNames[4],async()=>{
    const database=path.join(owned,'orders.sqlite');
    await page.close();page=await context.newPage();await page.setViewportSize({width:1100,height:850});
    await startHost('order-editor',database);await page.goto(url);
    await page.getByRole('heading',{name:'Edit existing orders',exact:true}).waitFor();
    await button('Select row 1 in Existing orders').click();await idle();
    await button('Open selected order').click();await idle();
    assert.equal(await field('Description').inputValue(),'Browser-owned order');
    assert.equal(await field('Price, row 1').inputValue(),'2.35');
    // An explicitly bound discard abandons even an invalid unsubmitted decimal.
    await field('Price, row 1').fill('invalid decimal');
    const beforeDiscard=rpc;
    await button('Discard / Reload').click();await idle();
    assert.equal(rpc,beforeDiscard+1,'discard_flushed_invalid_draft');
    assert.equal(await field('Price, row 3').inputValue(),'2.35');
    assert.equal(await field('Price, row 1').count(),0,'discard_reused_row_identity');
    await field('Description').fill('Browser edited existing');
    await field('Description').press('Enter');await idle();
    await button('Close form').click();await idle();
    assert.equal(await page.getByText('This form is closed. You can close this tab.',{exact:true}).count(),0);
    await field('Price, row 3').fill('2.40');
    await button('Save changes').click();await idle();
    assert.equal(await field('Total').inputValue(),'9.20');
    assert.equal(await button('Save changes').isEnabled(),true);
    assert.equal(await field('Price, row 5').isEditable(),true);
    await button('Save changes').click();await idle();
    assert.equal(await field('Status').inputValue(),'No changes; nothing was written');
    await field('Description').fill('Browser edited again');
    await button('Save changes').click();await idle();
    assert.equal(await field('Description').inputValue(),'Browser edited again');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'narrow_editor_overflow');
    await screenshot('order-editor-narrow.png');
    await button('Close form').click();
    await page.getByText('This form is closed. You can close this tab.',{exact:true}).waitFor();
    await stopHost();
    const readback=runPython(['-m','yadinassi','--f',database,'-c',
      'O=Catalogs.Orders.FindByCode("B002").GetObject(); '+
      'If O.Description<>"Browser edited again" Or O.Total<>9.20 Or O.Lines.Count()<>2 Then Raise "edited order readback"; EndIf; '+
      'If O.Lines.Get(0).ItemDescription<>"Cable" Or O.Lines.Get(0).Price<>2.40 Or O.Lines.Get(0).Amount<>3 Then Raise "edited line readback"; EndIf; '+
      'N=0; S=Catalogs.Orders.Select(); While S.Next() Do N=N+1; EndDo; '+
      'If N<>1 Then Raise "edited record count"; EndIf; Message("ORDER_EDITOR_READBACK_OK");']);
    assert.equal(readback.trim(),'ORDER_EDITOR_READBACK_OK');
    // A second independent form process opens the durable record, not a client snapshot.
    await page.close();page=await context.newPage();await startHost('order-editor',database);await page.goto(url);
    await page.getByRole('heading',{name:'Edit existing orders',exact:true}).waitFor();
    await button('Select row 1 in Existing orders').click();await idle();
    await button('Open selected order').click();await idle();
    assert.equal(await field('Description').inputValue(),'Browser edited again');
    assert.equal(await field('Price, row 1').inputValue(),'2.40');
    await button('Close form').click();
    await page.getByText('This form is closed. You can close this tab.',{exact:true}).waitFor();
    await stopHost();
    report.editorDurable={reopenedAfterHostClose:true,independentFormReopen:true,records:1,rows:2,exactTotal:'9.20'};
  });
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','source_changed');
  assert.deepEqual(await sourceBinding(),report.binding,'source_binding_changed');
  assert.deepEqual(results.map(row=>row.name),scenarioNames,'incomplete_scenarios');
  report.status='PASS';report.rpcRequests=rpc;
}
// Hard work limit plus a separate 20-second cleanup reserve. No security changes.
const deadline=setTimeout(abort,Math.max(0,workDeadline-Date.now()));
const totalTimer=setTimeout(()=>{abort();process.exit(1);},Math.max(0,totalDeadline-Date.now()));
try{await main();check();}
catch(error){
  failed=true;report.status='FAIL';
  report.failure={phase,reason:aborted?'deadline_or_rpc_budget':phase==='sandbox_launch'&&
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
