/** Opt-in real-browser acquisition. Never imported by ordinary unit discovery. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdir,mkdtemp,readFile,writeFile,rm,lstat,open as openFile,readlink,readdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {SCENARIOS,ARTIFACTS,launchOutputReader,allowedRequest,redact,childEnvironment,
  ownBrowserPid,commandLineArgs,sandboxCommand,sandboxStatus,completedResult,sha256} from './support.mjs';

const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON || 'python';
const temporary=process.env.RUNNER_TEMP;
if (!temporary || !path.isAbsolute(temporary) || process.platform!=='linux' || process.getuid()===0)
  throw Error('ordinary_nonroot_linux_runner_required');
const owned=await mkdtemp(path.join(temporary,'yadinassi-browser-'));
const output=path.join(temporary,'yadinassi-browser-artifacts');
await mkdir(output); // Fail if stale artifacts exist; never reuse a previous run.
const home=path.join(owned,'home');await mkdir(home);
const env=childEnvironment(process.env,home);
env.PYTHONPATH=repo+path.delimiter+path.join(repo,'tests');
const tokens=[],scenarios=[],diagnostics=[];
let browser,context,page,host,origin='',phase='binding',sandbox=null,durable=null;
let globalExpired=false,rpcRequests=0;
const diagnostic=(value)=>{if(diagnostics.length<20)diagnostics.push(redact(value,tokens));};
const report={status:'FAIL',scenarios,diagnostics,sandbox:null,browser:null,durable:null};
const bounded=(promise,ms,code)=>{
  let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(code)),ms);})])
    .finally(()=>clearTimeout(timer));
};
const git=(...args)=>execFileSync('git',args,{cwd:repo,encoding:'utf8',timeout:5000,maxBuffer:1024*1024}).trim();
const fixture=mode=>JSON.parse(execFileSync(python,[path.join(repo,'tests/browser_ui/fixture.py'),mode,owned],
  {cwd:repo,env,encoding:'utf8',timeout:15000,maxBuffer:16384,stdio:['ignore','pipe','pipe']}));
function signalHost(signal){
  if(host?.pid){try{process.kill(-host.pid,signal);}catch(error){if(error.code!=='ESRCH')throw error;}}
}
async function stopHost(){
  if(!host)return;
  const exited=()=>host.exitCode!==null||host.signalCode!==null;
  try{
    if(!exited()){
      const finished=new Promise(resolve=>host.once('exit',resolve));
      signalHost('SIGINT');
      try{await bounded(finished,8000,'host_close_timeout');}
      catch{signalHost('SIGKILL');await bounded(finished,3000,'host_kill_timeout');}
    }
  }finally{signalHost('SIGKILL');} // Also terminate remaining members after an early parent exit.

}
async function startHost(){
  assert.ok(!host||host.exitCode!==null,'previous_host_live');
  host=spawn(python,['-m','yadinassi.ui.local_app','--f',path.join(owned,'owned.sqlite')],
    {cwd:repo,env,detached:true,stdio:['ignore','pipe','pipe']});
  const readLaunch=launchOutputReader();let settled=false;
  host.stderr.on('data',data=>diagnostic('host: '+data.toString()));
  const url=await bounded(new Promise((resolve,reject)=>{
    const finish=(callback,value)=>{if(!settled){settled=true;callback(value);}};
    host.once('error',()=>finish(reject,Error('host_spawn_failed')));
    host.once('exit',()=>finish(reject,Error('host_exited_before_url')));
    host.stdout.on('data',data=>{
      if(settled)return; // Drain without retaining output after URL/failure.
      try{const parsed=readLaunch(data);if(parsed){
        tokens.push(parsed.hash.slice(9));origin=parsed.origin;finish(resolve,parsed.href);
      }}catch{finish(reject,Error('host_url_or_output_invalid'));}
    });
  }),15000,'host_start_timeout');
  return url;
}
async function hostClosed(){
  await page.getByRole('heading',{name:'Database closed',exact:true}).waitFor();
  if(host.exitCode===null)await bounded(new Promise(resolve=>host.once('exit',resolve)),8000,'host_close_timeout');
  assert.equal(host.exitCode,0,'host_cleanup_failed');
}
const button=name=>page.getByRole('button',{name:name.endsWith(' ›')?new RegExp('^'+name.slice(0,-2)+'(?:\\s*›)?$'):name,exact:true});
const click=async name=>button(name).click();
const input=name=>page.getByLabel(name,{exact:true});
const themeKey='yadinassi.catalog.theme';
async function resolvedTheme(expected){
  await page.waitForFunction(value=>document.documentElement.dataset.theme===value,expected);
}
async function themePreference(preference,resolved){
  const before=rpcRequests;
  await input('Color theme').selectOption({label:preference});
  await resolvedTheme(resolved);
  // Let rendering/effects finish without issuing or replaying any host event.
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(rpcRequests,before,'theme_issued_rpc');
}
async function storageContainsOnlyTheme(expected){
  // Return only a verdict, never capability-bearing storage contents to diagnostics.
  assert.equal(await page.evaluate(({key,value})=>
    localStorage.length===1&&localStorage.getItem(key)===value&&sessionStorage.length===0,
  {key:themeKey,value:expected}),true,'unexpected_browser_storage');
  assert.equal((await context.cookies()).length,0,'unexpected_browser_cookie');
}
async function desktopWorkspace(){
  const panels=[page.locator('aside'),page.locator('.records'),page.locator('.editor')];
  const boxes=[];
  for(const panel of panels){assert.equal(await panel.isVisible(),true,'desktop_panel_hidden');boxes.push(await panel.boundingBox());}
  assert.ok(boxes.every(box=>box&&box.width>0&&box.height>0),'desktop_panel_empty');
  for(let i=1;i<boxes.length;i++){
    assert.ok(boxes[i-1].x+boxes[i-1].width<=boxes[i].x+1,'desktop_panels_not_side_by_side');
    assert.ok(Math.max(boxes[i-1].y,boxes[i].y)<Math.min(boxes[i-1].y+boxes[i-1].height,
      boxes[i].y+boxes[i].height),'desktop_panels_not_aligned');
  }
  const main=await page.locator('main').boundingBox();
  assert.ok(main.width>=1240,'desktop_workspace_not_full_width');
}
async function lockedNavigation(){
  const navigation=page.locator('aside nav button, .records button');
  assert.ok(await navigation.count()>0,'navigation_missing');
  for(const control of await navigation.all())assert.equal(await control.isDisabled(),true,'editor_navigation_enabled');
  await page.getByText('Close the editor to switch records or catalogs.',{exact:true}).waitFor();
}
const status=async value=>page.getByRole('status').filter({hasText:value}).waitFor();
async function save(){
  const response=page.waitForResponse(reply=>{
    if(reply.url()!==origin+'/rpc')return false;
    try{const request=JSON.parse(reply.request().postData());return request.method==='editor.event'&&
      request.params.event==='command'&&request.params.control==='SaveButton';}catch{return false;}
  });
  await click('Save changes');await response;
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(
    button=>button.textContent==='Save changes'&&!button.disabled));
}
const row=text=>page.getByRole('row').filter({hasText:text});
const open=async text=>row(text).getByRole('button',{name:'Open →',exact:true}).click();
async function step(index,callback){
  phase=SCENARIOS[index];const started=Date.now();
  await bounded(callback(),45000,'scenario_timeout');
  scenarios.push({name:phase,status:'PASS',milliseconds:Date.now()-started});
}
async function screenshot(name){
  assert.ok(ARTIFACTS.includes(name)&&name.endsWith('.png'));
  assert.equal(new URL(page.url()).hash,'','capability_not_removed');
  await page.screenshot({path:path.join(output,name),fullPage:true,animations:'disabled',timeout:10000});
}
const deadline=setTimeout(()=>{globalExpired=true;diagnostic('global_deadline');signalHost('SIGKILL');
  if(browser)browser.close().catch(()=>{});},240000);
try{
  const commit=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}');
  assert.equal(commit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','tracked_checkout_dirty');
  const names=git('ls-files','-z','yadinassi','pyproject.toml','tests/browser_ui',
    'tests/ui_catalog_fixture.py','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names)source[name]=sha256(await readFile(path.join(repo,name)));
  report.binding={commit,tree,source};
  report.versions={node:process.version,playwright:JSON.parse(await readFile(
    new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version,
    python:execFileSync(python,['--version'],{env,encoding:'utf8',timeout:5000}).trim()};
  assert.equal(report.versions.playwright,'1.64.1');
  phase='owned_fixture';assert.equal(fixture('seed').seeded,true);
  phase='sandbox_launch';
  browser=await chromium.launch({headless:true,channel:'chromium',chromiumSandbox:true,
    env:childEnvironment(process.env,home),timeout:20000});
  report.browser=browser.version();
  const cdp=await browser.newBrowserCDPSession();
  // New Playwright no longer sets --enable-automation. Read argv only from the
  // exact process identified by this browser's own CDP, without changing flags.
  const pid=ownBrowserPid((await cdp.send('SystemInfo.getProcessInfo')).processInfo);
  const processRoot='/proc/'+pid;
  assert.equal((await lstat(processRoot)).uid,process.getuid(),'browser_uid_mismatch');
  assert.equal(await readlink(processRoot+'/exe'),chromium.executablePath(),'browser_executable_mismatch');
  const command=await openFile(processRoot+'/cmdline','r');
  try{
    const buffer=Buffer.alloc(16385);let length=0;
    while(length<buffer.length){const read=await command.read(buffer,length,buffer.length-length,null);
      if(!read.bytesRead)break;length+=read.bytesRead;}
    assert.ok(length>0&&length<=16384,'browser_command_budget');
    sandboxCommand(commandLineArgs(buffer.subarray(0,length)));
  }finally{await command.close();}
  await cdp.detach();
  context=await browser.newContext({viewport:{width:1320,height:900},locale:'en-US',
    timezoneId:'UTC',colorScheme:'light',acceptDownloads:false,serviceWorkers:'block'});
  context.setDefaultTimeout(10000);context.setDefaultNavigationTimeout(15000);
  const probe=await context.newPage();await probe.goto('chrome://sandbox');
  sandbox=sandboxStatus(await probe.locator('body').innerText());await probe.close();
  report.sandbox={requested:true,commandVerified:true,...sandbox};
  await context.route('**/*',route=>allowedRequest(route.request().url(),origin)?route.continue():route.abort('blockedbyclient'));
  page=await context.newPage();
  page.on('request',request=>{if(request.url()===origin+'/rpc')rpcRequests++;});
  page.on('pageerror',error=>diagnostic('page: '+error.message));
  page.on('console',message=>{if(message.type()==='error')diagnostic('console: '+message.text());});
  let url;
  await step(0,async()=>{
    url=await startHost();await page.goto(url);
    await resolvedTheme('dark');assert.equal(await input('Color theme').inputValue(),'dark');
    assert.equal(await page.evaluate(()=>matchMedia('(prefers-color-scheme: dark)').matches),false);
    await click('Categories ›');
    await row('Owned category').waitFor();await screenshot('list.png');
    await open('Owned category');assert.equal(await input('Code').inputValue(),'10');
    await desktopWorkspace();await lockedNavigation();
    await click('← Back to records');
  });
  await step(1,async()=>{
    await click('+ New record');await input('Code').fill('10');await input('Description').fill('Browser owned record');
    await save();await status('Save rejected: duplicate_code');
    assert.equal(await input('Description').inputValue(),'Browser owned record');
    await input('Code').fill('40');await save();await status('Saved');
    assert.equal(await input('Code').inputValue(),'40');
  });
  await step(2,async()=>{
    await input('Description').fill('Browser persisted edit');await save();await status('Saved');
    await click('← Back to records');await click('Products ›');await open('Owned product 10');
    await input('Text').fill('Browser scalar');await input('Amount').fill('123.40');
    await input('Active').uncheck();await input('Moment').fill('2025-06-07T08:09:10');
    await save();await status('Saved');
    assert.equal(await input('Amount').inputValue(),'123.40');assert.equal(await input('Active').isChecked(),false);
  });
  await step(3,async()=>{
    // Two completed UI commands, not a transport replay or direct host API call.
    await save();await status('No changes');await save();await status('No changes');
  });
  await step(4,async()=>{
    const originalReference=await input('Category').inputValue();
    await input('Category').selectOption('00000000-0000-0000-0000-000000000000');
    await save();await status('Saved');
    await click('← Back to records');await open('Owned product 10');
    assert.equal(await input('Category').inputValue(),'00000000-0000-0000-0000-000000000000');
    await input('Category').selectOption(originalReference);await save();await status('Saved');
    await input('Text').fill('Discard me');
    assert.equal(await page.getByRole('status').count(),0,'stale_save_status_with_dirty_draft');
    await desktopWorkspace();await lockedNavigation();
    await page.getByText('List preview · refreshed when you return',{exact:true}).waitFor();
    await screenshot('editor.png'); // Populated dark split-view and a retained dirty draft.
    for(const [preference,resolved] of [['Light','light'],['Dark','dark'],['System','light']]){
      await themePreference(preference,resolved);
      assert.equal(await input('Text').inputValue(),'Discard me','theme_lost_dirty_draft');
    }
    const before=rpcRequests;
    await page.emulateMedia({colorScheme:'dark'});await resolvedTheme('dark');
    await page.emulateMedia({colorScheme:'light'});await resolvedTheme('light');
    assert.equal(rpcRequests,before,'system_theme_issued_rpc');
    assert.equal(await input('Text').inputValue(),'Discard me');
    await themePreference('Light','light');await storageContainsOnlyTheme('light');
    page.once('dialog',dialog=>dialog.dismiss());
    await click('← Back to records');await page.getByText('Unsaved changes',{exact:true}).waitFor();
    assert.equal(await input('Text').inputValue(),'Discard me');await click('Discard & return');
    await open('Owned product 10');assert.equal(await input('Text').inputValue(),'Browser scalar');
  });
  await step(5,async()=>{
    await page.emulateMedia({colorScheme:'dark'});
    await page.reload();await page.getByText('Session capability missing.',{exact:false}).waitFor();
    await resolvedTheme('light');assert.equal(await input('Color theme').inputValue(),'light');
    await storageContainsOnlyTheme('light');
    await page.goto(url);await input('Text').waitFor();
    assert.equal(await input('Text').inputValue(),'Browser scalar');
    assert.equal(new URL(page.url()).hash,'');
    await resolvedTheme('light');await storageContainsOnlyTheme('light');
  });
  await step(6,async()=>{
    assert.equal(await input('Category').locator('option:checked').textContent(),'10 · Owned category');
    assert.equal(await input('Category').evaluate(node=>node.tagName),'SELECT');
    await themePreference('Dark','dark');await desktopWorkspace();
    await page.getByText('Return to records to refresh the list.',{exact:true}).waitFor();
    await page.setViewportSize({width:960,height:900});
    const mediumNavigation=await page.locator('aside').boundingBox();
    const mediumEditor=await page.locator('.editor').boundingBox();
    const mediumRecords=await page.locator('.records').boundingBox();
    assert.ok(mediumNavigation.x+mediumNavigation.width<=mediumEditor.x+1,'medium_navigation_overlap');
    assert.ok(mediumRecords.y>=mediumEditor.y+mediumEditor.height-1,'medium_preview_not_below_editor');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.locator('.editor').isVisible(),true,'mobile_editor_hidden');
    const editorBox=await page.locator('.editor').boundingBox();
    for(const panel of [page.locator('aside'),page.locator('.records')]){
      if(await panel.isVisible())assert.ok((await panel.boundingBox()).y>=editorBox.y+editorBox.height-1,
        'mobile_editor_not_prioritized');
    }
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    const referencesBox=await input('Category').boundingBox();
    const actionsBox=await page.locator('.editor-actions').boundingBox();
    assert.ok(actionsBox.y>=referencesBox.y+referencesBox.height-1,'mobile_actions_overlap_references');
    await screenshot('narrow.png');
  });
  await step(7,async()=>{
    await click('Close database');await hostClosed();durable=fixture('audit');
    assert.equal(durable.durable,true);url=await startHost();await page.goto('about:blank');await page.goto(url);
    await click('Categories ›');await row('Browser persisted edit').waitFor();assert.equal(await row('Browser persisted edit').count(),1);
    await open('Browser persisted edit');assert.equal(await input('Code').inputValue(),'40');
    await click('← Back to records');await click('Products ›');await open('Owned product 10');
    assert.equal(await input('Text').inputValue(),'Browser scalar');assert.equal(await input('Amount').inputValue(),'123.40');
    assert.equal(await input('Active').isChecked(),false);assert.equal(await input('Moment').inputValue(),'2025-06-07T08:09:10');
    await click('Close database');await hostClosed();
  });
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','source_changed');
  assert.equal(diagnostics.length,0,'browser_or_host_diagnostics');
  assert.equal(globalExpired,false);assert.equal(completedResult(scenarios),true);
  report.status='PASS';report.durable=durable;
}catch(error){report.failedPhase=phase;diagnostic(error.message);process.exitCode=1;}
finally{
  clearTimeout(deadline);
  try{if(browser)await bounded(browser.close(),10000,'browser_cleanup_timeout');}
  catch(error){diagnostic(error.message);report.status='FAIL';process.exitCode=1;}
  try{await stopHost();}catch(error){diagnostic(error.message);report.status='FAIL';process.exitCode=1;}
  try{await rm(owned,{recursive:true,force:true});}
  catch{diagnostic('owned_cleanup_failed');report.status='FAIL';process.exitCode=1;}
  const images={};for(const name of ARTIFACTS.filter(x=>x.endsWith('.png'))){
    try{const file=path.join(output,name),info=await lstat(file);
      if(!info.isFile()||info.size>4*1024*1024)throw Error('image_budget');
      const content=await readFile(file);
      if(content.length!==info.size||content.length>4*1024*1024)throw Error('image_changed');
      images[name]={bytes:content.length,sha256:sha256(content)};
    }catch{
      await rm(path.join(output,name),{force:true});
      report.status='FAIL';process.exitCode=1;diagnostic('screenshot_missing_or_oversized');
    }
  }
  // Redaction's individual-message cap is not the report budget. Serialize the
  // already-redacted diagnostics without truncating its source hash manifest.
  const raw=JSON.stringify(report,null,2)+'\n';
  if(tokens.some(token=>raw.includes(token)))throw Error('artifact_capability_leak');
  await writeFile(path.join(output,'result.json'),raw);
  await writeFile(path.join(output,'manifest.json'),JSON.stringify({schema:1,
    source:report.binding?.commit,tree:report.binding?.tree,resultSha256:sha256(raw),images},null,2)+'\n');
  const actual=await readdir(output);assert.ok(actual.every(name=>ARTIFACTS.includes(name)));
  console.log(JSON.stringify({status:report.status,completed:scenarios.length,total:SCENARIOS.length,
    failedPhase:report.failedPhase,source:report.binding?.commit}));
}
