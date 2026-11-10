/** Opt-in owned typed-reference browser acquisition. No native-platform parity claim. */
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
const screenshots=['reference-created.png','reference-choice-narrow.png','reference-reopened.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['create_choose_save_exact_references',
  'edit_invalid_draft_cancel_and_selected_row_ownership','independent_readback_and_fresh_workspace_reopen'];
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

// Only fixed labels leave this process. Never export raw launch errors, paths,
// command arguments, environment values, process IDs or assertion actual/expected.
function launchFailureCode(error){
  const message=typeof error?.message==='string'?error.message:'';
  const fixed=['invalid_owned_pid','process_uid_mismatch','process_not_direct_child',
    'process_group_not_owned','unexpected_launch_children','browser_executable_mismatch',
    'browser_command_budget','browser_command_invalid','sandbox_command_missing','sandbox_disabled',
    'unexpected_browser_transport','browser_profile_missing','browser_profile_not_owned',
    'browser_process_missing','cdp_setup_timeout','cdp_process_timeout','browser_pid_invalid',
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
async function startHost(database){
  check();assert.ok(!host&&!hostGroup,'previous_host_live');
  const args=['-m','yadinassi.ui.reference_orders_workspace',path.join(repo,'examples/forms'),'--f',database];
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
const button=name=>page.getByRole('button',{name,exact:true,includeHidden:true});
const owner=()=>page.locator('.reference-workspace section[aria-disabled]:not([role="dialog"])');
const ownerField=name=>owner().getByLabel(name,{exact:true});
const ownerButton=name=>owner().getByRole('button',{name,exact:true,includeHidden:true});
const dialog=()=>page.getByRole('dialog',{name:'Choose a reference',exact:true});
const childButton=name=>dialog().getByRole('button',{name,exact:true});
const idle=()=>page.waitForFunction(()=>[...document.querySelectorAll('[aria-busy]')].every(node=>node.getAttribute('aria-busy')==='false'),null,{timeout:remaining(10000)});
const ownerReady=async()=>{
  await page.waitForFunction(()=>document.querySelector('.reference-workspace section[aria-disabled]:not([role="dialog"])')?.getAttribute('aria-disabled')==='false',null,{timeout:remaining(10000)});
  await idle();assert.equal(await ownerButton('Save changes').isEnabled(),true);
};
const wireEvents=[];
let snapshotGate=null,wireFailure=false;
const exactKeys=(value,names)=>assert.deepEqual(Object.keys(value).sort(),names.split(' ').filter(Boolean).sort(),'wire_keys');
function checkRequest(request){
  const raw=request.postData();assert.ok(raw&&Buffer.byteLength(raw)<=65536,'wire_budget');
  const packet=JSON.parse(raw);exactKeys(packet,'jsonrpc id method params');
  assert.equal(packet.jsonrpc,'2.0');assert.ok(Number.isSafeInteger(packet.id)&&packet.id>0);
  if(packet.method==='workspace.hello'){
    exactKeys(packet.params,'protocol');assert.equal(packet.params.protocol,'yadinassi-reference-orders/1');
  }else if(packet.method==='workspace.list')exactKeys(packet.params,'code');
  else if(packet.method==='workspace.open')exactKeys(packet.params,'revision row request');
  else if(packet.method==='workspace.close')exactKeys(packet.params,'');
  else{
    assert.equal(packet.method,'workspace.form');exactKeys(packet.params,'session request');
    const nested=packet.params.request;exactKeys(nested,'jsonrpc id method params');
    if(nested.method==='form.hello'){
      exactKeys(nested.params,'protocol');assert.equal(nested.params.protocol,'yadinassi-form-ui/1');
    }else if(nested.method==='form.snapshot')exactKeys(nested.params,'');
    else{
      assert.equal(nested.method,'form.event');const event=nested.params;
      const keys={command:'event revision control',close:'event revision',select:'event revision control row',
        change:'event revision control value',cell:'event revision control row column value'};
      assert.ok(Object.hasOwn(keys,event.event),'wire_event');exactKeys(event,keys[event.event]);
      if(event.event==='change'||event.event==='cell'){
        exactKeys(event.value,'type value');assert.ok(['String','Number','Boolean'].includes(event.value.type),'scalar_only');
        assert.ok(['string','boolean'].includes(typeof event.value.value),'scalar_value_only');
      }
      wireEvents.push({session:packet.params.session,event:event.event,control:event.control});
    }
  }
  return packet;
}
async function repeatClick(locator){await locator.evaluate(control=>{control.click();control.click();});}
async function openChoice(caption,{repeat=false}={}){
  const before=wireEvents.length;
  if(repeat)await repeatClick(ownerButton(caption));else await ownerButton(caption).click();
  await dialog().getByRole('heading',{name:'Choose a reference',exact:true}).waitFor();await idle();
  assert.equal(await dialog().count(),1);assert.equal(await owner().count(),1);
  assert.equal(await owner().getAttribute('aria-disabled'),'true');
  assert.equal(await owner().evaluate(node=>node.inert&&node.querySelector('fieldset').disabled),true);
  for(const name of ['Save changes','Close form','Choose customer','Choose product for selected line'])
    assert.equal(await ownerButton(name).isDisabled(),true);
  const blockedAt=rpc;
  await repeatClick(ownerButton('Save changes'));await repeatClick(ownerButton('Choose customer'));
  assert.equal(rpc,blockedAt,'frozen_owner_sent_request');
  if(repeat)assert.equal(wireEvents.slice(before).filter(event=>event.event==='command').length,1,'repeated_choice_sent_twice');
}
async function chooseCode(code,{search=false,holdRefresh=false}={}){
  if(search){
    await dialog().getByLabel('Find exact code (empty shows first 32)',{exact:true}).fill(code);
    await childButton('Find records').click();await idle();
  }
  const rows=dialog().locator('tbody tr');assert.ok(await rows.count()<=32);
  let chosen=null;
  for(let index=0;index<await rows.count();index++){
    const row=rows.nth(index);
    if(await row.locator('input[aria-label^="Code, row "]').inputValue()===code){chosen=row;break;}
  }
  assert.ok(chosen,'choice_code_missing');
  await chosen.getByRole('button',{name:/^Select row /}).click();await idle();
  let release,admitted;
  if(holdRefresh){
    const ready=new Promise(resolve=>{admitted=resolve;});
    const gate=new Promise(resolve=>{release=resolve;});snapshotGate={admitted,gate};
    try{
      await childButton('Choose selected record').click();
      await bounded(ready,remaining(5000),'owner_refresh_missing');
      await dialog().waitFor({state:'detached'});
      assert.equal(await owner().getAttribute('aria-disabled'),'true','owner_thawed_before_snapshot');
      assert.equal(await owner().evaluate(node=>node.inert&&node.querySelector('fieldset').disabled),true);
      assert.equal(await ownerButton('Save changes').isDisabled(),true);
      assert.equal(await button('Close workspace').isDisabled(),true);
      const before=rpc;await repeatClick(ownerButton('Save changes'));
      assert.equal(rpc,before,'owner_mutation_during_refresh');
    }finally{release();snapshotGate=null;}
  }else await childButton('Choose selected record').click();
  await dialog().waitFor({state:'detached'});await ownerReady();
}
async function closeOwner(){
  await ownerButton('Close form').click();await owner().waitFor({state:'detached'});
  await button('New order').waitFor();assert.equal(await button('New order').isEnabled(),true);
}
async function scenario(name,fn){check();phase=name;await fn();check();results.push({name,status:'PASS'});}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0,'browser_storage_not_empty');
  assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/reference-workspace','examples/forms','tests/browser_ui',
    'tests/test_ui_browser_qa_contract.py','tests/test_form_browser_qa_contract.py','tests/test_reference_browser_qa_contract.py','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-reference-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'yadinassi-reference-browser-'));
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
  await context.route('**/*',async route=>{
    const target=route.request().url();
    if(aborted||!allowedRequest(target,origin))return route.abort();
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=100){abort();return route.abort().catch(()=>{});}
      rpc++;
      try{
        const packet=checkRequest(route.request());
        if(snapshotGate&&packet.method==='workspace.form'&&packet.params.request.method==='form.snapshot'){
          const held=snapshotGate;held.admitted();await bounded(held.gate,remaining(5000),'snapshot_hold_timeout');
        }
      }catch{wireFailure=true;abort();return route.abort().catch(()=>{});}
    }
    return route.continue();
  });
  page=await context.newPage();
  const database=path.join(owned,'references.sqlite');
  phase='seed_owned_references';
  runPython(['-m','yadinassi','--create-db',database,'--import-xml',path.join(repo,'examples/forms/reference-order/configuration')]);
  runPython(['-m','yadinassi','--f',database,'-c',
    'C1=Catalogs.Customers.CreateItem(); C1.Code="C001"; C1.Description="Shared display"; C1.Write(); '+
    'C2=Catalogs.Customers.CreateItem(); C2.Code="C002"; C2.Description="Shared display"; C2.Write(); '+
    'P1=Catalogs.Products.CreateItem(); P1.Code="P001"; P1.Description="Shared product"; P1.UnitPrice=2.50; P1.Write(); '+
    'P2=Catalogs.Products.CreateItem(); P2.Code="P002"; P2.Description="Shared product"; P2.UnitPrice=4.25; P2.Write(); '+
    'O=Catalogs.Orders.CreateItem(); O.Code="O001"; O.Description="First order"; O.Customer=C1.Ref; O.Total=2.50; '+
    'R=O.Lines.Add(); R.Product=P1.Ref; R.ItemDescription="Original description"; R.Quantity=1; R.Price=2.50; R.Amount=2.50; O.Write();']);
  await startHost(database);await page.goto(url);
  await page.getByRole('heading',{name:'Reference Orders',exact:true}).waitFor();
  assert.equal(await page.locator('#reference-orders-app').count(),1);
  await button('Open order O001: First order').waitFor();
  await scenario(scenarioNames[0],async()=>{
    phase='create_repeated_new';
    const before=rpc;await repeatClick(button('New order'));
    await ownerField('Order code').waitFor();await ownerReady();
    assert.equal(rpc,before+2,'repeated_new_created_multiple_owners');
    assert.equal(await owner().count(),1);assert.equal(await button('New order').isDisabled(),true);
    for(const [name,value] of [['Order code','B001'],['Description','Browser reference order']]){
      await ownerField(name).fill(value);await ownerField(name).press('Enter');await idle();
    }
    phase='create_customer_choice';
    await openChoice('Choose customer',{repeat:true});
    await chooseCode('C002',{search:true,holdRefresh:true});
    assert.equal(await ownerField('Customer').inputValue(),'Shared display');
    phase='create_product_choice';
    await ownerButton('Add line').click();await idle();
    assert.equal(await ownerButton('Selected row 1 in Order lines').getAttribute('aria-pressed'),'true');
    await openChoice('Choose product for selected line');await chooseCode('P002');
    assert.equal(await ownerField('Product, row 1').inputValue(),'Shared product');
    assert.equal(await ownerField('Price, row 1').inputValue(),'4.25');
    phase='create_save_pending_quantity';
    await ownerField('Quantity, row 1').fill('2');await ownerButton('Save changes').click();await ownerReady();
    assert.equal(await ownerField('Status').inputValue(),'Order saved; you can continue editing');
    assert.equal(await ownerField('Total').inputValue(),'8.50');
    await screenshot('reference-created.png');await closeOwner();
  });
  await scenario(scenarioNames[1],async()=>{
    phase='edit_existing_order';
    await button('Open order O001: First order').click();await ownerField('Order code').waitFor();await ownerReady();
    assert.equal(await ownerField('Price, row 1').inputValue(),'2.50');
    await ownerButton('Add line').click();await idle();
    assert.equal(await ownerButton('Selected row 2 in Order lines').getAttribute('aria-pressed'),'true');
    phase='invalid_draft_blocks_choice';
    await ownerField('Price, row 2').fill('not-a-number');const invalidAt=rpc;
    await ownerButton('Choose product for selected line').click();await idle();
    assert.equal(await owner().getByRole('alert').isVisible(),true);
    assert.equal(rpc,invalidAt,'invalid_choice_draft_sent');assert.equal(await dialog().count(),0);
    phase='selected_row_product_choice';
    await ownerField('Price, row 2').fill('9');
    await openChoice('Choose product for selected line');await chooseCode('P002');
    assert.equal(await ownerField('Price, row 1').inputValue(),'2.50','choice_changed_unselected_row');
    assert.equal(await ownerField('Description, row 1').inputValue(),'Original description');
    assert.equal(await ownerField('Price, row 2').inputValue(),'4.25');
    phase='cancel_preserves_owner_draft';
    await ownerField('Quantity, row 2').fill('2');await openChoice('Choose customer');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'narrow_page_overflow');
    assert.equal(await dialog().evaluate(node=>node.getBoundingClientRect().left>=0&&node.getBoundingClientRect().right<=innerWidth),true);
    await screenshot('reference-choice-narrow.png');
    const cancelAt=wireEvents.length;await repeatClick(childButton('Cancel selection'));
    await dialog().waitFor({state:'detached'});await ownerReady();
    assert.equal(wireEvents.slice(cancelAt).filter(event=>event.control==='CancelButton').length,1,'cancel_repeated');
    assert.equal(await ownerField('Customer').inputValue(),'Shared display');
    assert.equal(await ownerField('Quantity, row 2').inputValue(),'2');
    phase='ordinary_child_close_preserves_reference';
    await openChoice('Choose customer');await dialog().press('Escape');
    await dialog().waitFor({state:'detached'});await ownerReady();
    assert.equal(await ownerField('Customer').inputValue(),'Shared display');
    phase='edit_save_exact_total';
    await ownerButton('Save changes').click();await ownerReady();
    assert.equal(await ownerField('Total').inputValue(),'11.00');
    assert.equal(await ownerField('Status').inputValue(),'Order saved; you can continue editing');
    await closeOwner();await button('Close workspace').click();
    await page.getByText('Workspace closed. You can close this page.',{exact:true}).waitFor();await stopHost();
  });
  await scenario(scenarioNames[2],async()=>{
    phase='independent_cli_readback';
    // Separate CLI opens the database after every owner and the host process are closed.
    const readback=runPython(['-m','yadinassi','--f',database,'-c',
      'A=Catalogs.Orders.FindByCode("B001").GetObject(); B=Catalogs.Orders.FindByCode("O001").GetObject(); '+
      'If A.Customer<>Catalogs.Customers.FindByCode("C002") Or A.Total<>8.50 Or A.Lines.Count()<>1 Then Raise "created reference readback"; EndIf; '+
      'If A.Lines.Get(0).Product<>Catalogs.Products.FindByCode("P002") Then Raise "created product readback"; EndIf; '+
      'If B.Customer<>Catalogs.Customers.FindByCode("C001") Or B.Total<>11 Or B.Lines.Count()<>2 Then Raise "cancel readback"; EndIf; '+
      'If B.Lines.Get(0).Product<>Catalogs.Products.FindByCode("P001") Or B.Lines.Get(1).Product<>Catalogs.Products.FindByCode("P002") Then Raise "selected row readback"; EndIf; '+
      'N=0; S=Catalogs.Orders.Select(); While S.Next() Do N=N+1; EndDo; If N<>2 Then Raise "duplicate order"; EndIf; Message("REFERENCE_CLI_READBACK_OK");']);
    assert.equal(readback.trim(),'REFERENCE_CLI_READBACK_OK');
    phase='independent_sqlite_typed_key_readback';
    const audit=runPython(['-c',`
from decimal import Decimal
from uuid import UUID
import sys
from yadinassi import Interpreter
from yadinassi.catalog_backend import CatalogKey
from yadinassi.database_context import SQLiteDBContext
with SQLiteDBContext(sys.argv[1]) as context:
    vm = Interpreter(database_context=context)
    try:
        refs = {code: vm.execute('Catalogs.' + catalog + '.FindByCode("' + code + '").GetObject()')._key
                for catalog, code in [('Customers','C001'),('Customers','C002'),('Products','P001'),('Products','P002')]}
        for code, customer, total, lines in [
                ('B001','C002','8.50',[('P002','Shared product','2','4.25','8.50')]),
                ('O001','C001','11.00',[('P001','Original description','1','2.50','2.50'),('P002','Shared product','2','4.25','8.50')])]:
            obj = vm.execute('Catalogs.Orders.FindByCode("' + code + '").GetObject()')
            manager = obj._manager
            stored = tuple(manager._stored(field, obj.get_member(field.name)) for field in manager._schema.fields)
            rows = obj._sections['lines']._stored_rows().rows
            if stored != (refs[customer], Decimal(total)) or len(rows) != len(lines):
                raise RuntimeError('header_readback')
            if type(stored[0]) is not CatalogKey or type(stored[0].record_id) is not UUID:
                raise RuntimeError('customer_type')
            for row, (product, description, quantity, price, amount) in zip(rows, lines):
                if type(row.values[0]) is not CatalogKey or row.values[0] != refs[product]:
                    raise RuntimeError('product_key')
                if row.values != (refs[product], description, Decimal(quantity), Decimal(price), Decimal(amount)):
                    raise RuntimeError('row_readback')
        print('REFERENCE_SQLITE_READBACK_OK')
    finally:
        vm.close()
`,database]);
    assert.equal(audit.trim(),'REFERENCE_SQLITE_READBACK_OK');
    phase='fresh_host_reopen';
    await page.close();page=await context.newPage();await startHost(database);await page.goto(url);
    await button('Open order B001: Browser reference order').waitFor();
    await page.getByLabel('Find exact code',{exact:true}).fill('B001');await button('Find / Refresh orders').click();
    await button('Open order O001: First order').waitFor({state:'detached'});
    await button('Open order B001: Browser reference order').click();await ownerField('Order code').waitFor();await ownerReady();
    assert.equal(await ownerField('Customer').inputValue(),'Shared display');
    assert.equal(await ownerField('Product, row 1').inputValue(),'Shared product');
    assert.equal(await ownerField('Price, row 1').inputValue(),'4.25');
    assert.equal(await ownerField('Quantity, row 1').inputValue(),'2');
    assert.equal(await ownerField('Total').inputValue(),'8.50');
    await screenshot('reference-reopened.png');await closeOwner();
    await page.getByLabel('Find exact code',{exact:true}).fill('O001');await button('Find / Refresh orders').click();
    await button('Open order O001: First order').click();await ownerField('Order code').waitFor();await ownerReady();
    assert.equal(await ownerField('Total').inputValue(),'11.00');
    assert.equal(await ownerField('Price, row 1').inputValue(),'2.50');
    assert.equal(await ownerField('Price, row 2').inputValue(),'4.25');
    await closeOwner();await button('Close workspace').click();
    await page.getByText('Workspace closed. You can close this page.',{exact:true}).waitFor();await stopHost();
    report.durable={independentCli:true,independentSQLite:true,freshHostReopen:true,typedKeys:true,
      cancelPreservedCustomer:true,selectedRowPreserved:true,orders:2,createdTotal:'8.50',editedTotal:'11.00'};
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
console.log(JSON.stringify({status:report.status,completed:results.length,total:3,source:report.sourceCommit,failure:report.failure,cleanup:report.cleanup}));
if(failed||report.status!=='PASS')process.exitCode=1;
