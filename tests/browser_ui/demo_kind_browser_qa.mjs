/** One local disposable original-demo browser acquisition. No external traffic. */
import {chromium} from 'playwright';
import {spawn,execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile,rm,lstat,readdir} from 'node:fs/promises';
import path from 'node:path';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {launchOutputReader,allowedRequest,redact,childEnvironment,ownBrowserPid,commandLineArgs,sandboxCommand,sandboxStatus,sha256}
  from './support.mjs';
const startedAt=Date.now();
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const temporary=process.env.RUNNER_TEMP;
if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)throw Error('ordinary_nonroot_runner_required');
const output=path.join(temporary,'yadinassi-browser-artifacts');
await mkdir(output); // Never reuse old evidence.
const owned=await mkdtemp(path.join(temporary,'yadinassi-kind-browser-'));
const home=path.join(owned,'home');await mkdir(home);
const env=childEnvironment(process.env,home);env.PYTHONPATH=repo+':'+path.join(repo,'tests');
let host,browser,context,page,origin='',url='',rpc=0,phase='seed',failure,aborted=false,browserGroup=null;
const workDeadline=startedAt+160000;
const check=()=>{if(aborted||Date.now()>=workDeadline){aborted=true;throw Error('global_deadline_or_budget');}};
const remaining=max=>{check();return Math.max(1,Math.min(max,workDeadline-Date.now()));};
const killBrowser=()=>{if(browserGroup)try{process.kill(-browserGroup,'SIGKILL');}catch(e){if(e.code!=='ESRCH')throw e;}};
const abort=()=>{aborted=true;killHost('SIGKILL');killBrowser();};
const tokens=[],results=[];
const report={status:'FAIL',sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8',timeout:5000,maxBuffer:128}).trim(),scenarios:results,sandbox:null};
const bounded=(promise,ms,reason)=>{let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(reason)),ms);})]).finally(()=>clearTimeout(timer));};
const py=code=>JSON.parse(execFileSync(python,['-c',code,repo,path.join(owned,'demo.sqlite')],{cwd:repo,env,encoding:'utf8',timeout:remaining(15000),maxBuffer:16384,stdio:['ignore','pipe','pipe']}));
const audit=()=>py(`import sys,json\nfrom yadinassi.sqlite_catalog import SQLiteCatalogBackend\nfrom yadinassi.catalog_backend import CatalogSelection\nb=SQLiteCatalogBackend(sys.argv[2],read_only=True)\nv=b.begin_read()\ns=next(s for s in v.catalogs() if s.name=='ВидыНоменклатуры')\nrows=v.select_catalog(s.identity,CatalogSelection(limit=5))\nprint(json.dumps([{'code':r.code,'description':r.description,'id':str(r.key.record_id),'revision':r.revision.token} for r in rows]))\nv.close();b.close()`);
function killHost(signal){if(host?.pid)try{process.kill(-host.pid,signal);}catch(e){if(e.code!=='ESRCH')throw e;}}
async function stopHost(){if(!host)return;const done=host.exitCode!==null||host.signalCode!==null;if(!done){const ended=new Promise(r=>host.once('exit',r));killHost('SIGINT');try{await bounded(ended,5000,'host_close_timeout');}catch{killHost('SIGKILL');await bounded(ended,2000,'host_kill_timeout');}}killHost('SIGKILL');}
async function startHost(){
  check();
  host=spawn(python,['-m','yadinassi.ui.local_app','--f',path.join(owned,'demo.sqlite')],{cwd:repo,env,detached:true,stdio:['ignore','pipe','ignore']});
  const parse=launchOutputReader();let settled=false;
  url=await bounded(new Promise((resolve,reject)=>{
    host.once('error',()=>reject(Error('host_spawn_failed')));
    host.once('exit',()=>{if(!settled)reject(Error('host_exited_before_launch'));});
    host.stdout.on('data',data=>{if(settled)return;try{const found=parse(data);if(found){settled=true;origin=found.origin;tokens.push(found.hash.slice(9));resolve(found.href);}}catch{settled=true;reject(Error('invalid_launch_output'));}});
  }),15000,'host_start_timeout');
}
const button=name=>page.getByRole('button',{name,exact:true});
const input=()=>page.getByLabel('Description',{exact:true});
const idle=()=>page.waitForFunction(()=>![...document.querySelectorAll('button')].some(b=>b.textContent==='Working…'));
async function scenario(name,fn){check();phase=name;await fn();check();results.push({name,status:'PASS'});}
async function main(){
  assert.notEqual(process.getuid(),0,'nonroot_required');
  const git=(...args)=>execFileSync('git',args,{cwd:repo,encoding:'utf8',timeout:remaining(5000),maxBuffer:1024*1024}).trim();
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','tracked_checkout_dirty');
  const names=git('ls-files','-z','yadinassi','pyproject.toml','tests/browser_ui','examples/demo','.github/workflows/ui-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names)source[name]=sha256(await readFile(path.join(repo,name)));
  report.binding={commit:report.sourceCommit,tree:git('rev-parse','HEAD^{tree}'),source};
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1');
  py(`import sys,json\nfrom pathlib import Path\nfrom yadinassi.sqlite_catalog import SQLiteCatalogBackend\nr=Path(sys.argv[1])/'examples/demo'\nf={p.relative_to(r).as_posix():p.read_bytes() for p in r.rglob('*') if p.is_file()}\nassert len(f)==39\nb=SQLiteCatalogBackend.create_main_demo(sys.argv[2],__import__('yadinassi.configuration_main_demo',fromlist=['import_main_demo_configuration']).import_main_demo_configuration(f,profile='main-demo-v1'));b.close()\nprint(json.dumps({'files':len(f)}))`);
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
      const pid=Number(children[0]);assert.ok(Number.isSafeInteger(pid)&&pid>0);
      const stat=readFileSync('/proc/'+pid+'/stat','utf8');
      const fields=stat.slice(stat.lastIndexOf(')')+2).trim().split(/\s+/);
      assert.equal(Number(fields[1]),process.pid,'browser_not_direct_child');
      assert.equal(Number(fields[2]),pid,'browser_process_group_not_owned');browserGroup=pid;
      const args=readFileSync('/proc/'+pid+'/cmdline');assert.ok(args.length<=16384);sandboxCommand(commandLineArgs(args));
    }
  }
  check();assert.ok(browserGroup,'browser_process_missing');report.browser=browser.version();
  const cdp=await bounded(browser.newBrowserCDPSession(),remaining(5000),'cdp_setup_timeout');
  const info=await bounded(cdp.send('SystemInfo.getProcessInfo'),remaining(5000),'cdp_process_timeout');
  assert.equal(ownBrowserPid(info.processInfo),browserGroup,'browser_pid_mismatch');
  context=await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:false,serviceWorkers:'block'});
  const probe=await context.newPage();probe.setDefaultTimeout(remaining(10000));await probe.goto('chrome://sandbox');report.sandbox=sandboxStatus(await probe.locator('body').innerText());await probe.close();
  await startHost();
  await context.route('**/*',route=>{
    const target=route.request().url();
    if(aborted||!allowedRequest(target,origin))return route.abort();
    if(new URL(target).pathname==='/rpc'){
      if(rpc>=200){aborted=true;return route.abort().catch(()=>{}).finally(()=>{killHost('SIGKILL');killBrowser();});}
      rpc++;
    }
    return route.continue();
  });
  page=await context.newPage();page.setDefaultTimeout(10000);
  await page.goto(url);
  await scenario('catalog_and_readonly_code',async()=>{
    await page.getByRole('button',{name:/^ВидыНоменклатуры/}).click();
    await page.screenshot({path:path.join(output,'list.png')});
    await button('+ New record').click();
    assert.equal(await page.getByLabel('Code',{exact:true}).isDisabled(),true);
    await page.getByText('Imported name-validation handlers',{exact:false}).waitFor();
  });
  await scenario('blur_normalization_and_client_message',async()=>{
    await input().fill(' x ');await page.getByLabel('Color theme',{exact:true}).focus();
    await page.getByText('Название вида должно содержать не менее трех символов, например: Товары или Материалы.',{exact:true}).waitFor();
    assert.equal(await input().inputValue(),'x');
  });
  await scenario('short_save_refused_without_record',async()=>{
    await button('Save changes').click();
    await page.getByText('Укажите название вида номенклатуры длиной не менее трех символов.',{exact:true}).waitFor();
    assert.deepEqual(audit(),[]);await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(output,'narrow.png'),timeout:remaining(10000)});
    await page.setViewportSize({width:1280,height:900});
  });
  await scenario('pointer_blur_then_save_is_not_lost',async()=>{
    await input().fill('  Товары  ');await button('Save changes').click();
    await page.getByRole('status').filter({hasText:/^Saved$/}).waitFor();
    assert.equal(await input().inputValue(),'Товары');
    await page.locator('.records tbody tr').filter({hasText:'Товары'}).waitFor();
    assert.equal(await page.locator('.editor').count(),1,'save_closed_editor');
    assert.equal(await page.locator('.records tbody tr').count(),1,'created_row_missing_behind_card');
    assert.equal(await page.locator('.records tbody tr').first().getAttribute('aria-selected'),'true','saved_row_not_selected');
  });
  await scenario('valid_edit_number_and_durable_row',async()=>{
    const first=audit();assert.equal(first.length,1);assert.match(first[0].code,/^[0-9]{9}$/);
    await input().fill('  Материалы  ');await button('Save changes').click();await idle();
    await page.waitForFunction(()=>document.querySelector('input[aria-label="Description"]').value==='Материалы');
    await page.locator('.records tbody tr').filter({hasText:'Материалы'}).waitFor();
    assert.equal(await page.locator('.records tbody tr').count(),1,'rename_duplicated_row');
    const rows=audit();assert.equal(rows[0].description,'Материалы');assert.equal(rows[0].code,first[0].code);
    await page.screenshot({path:path.join(output,'editor.png')});
  });
  await scenario('repeated_save_keeps_row_code_revision',async()=>{
    const before=audit();await button('Save changes').click();
    await page.getByRole('status').filter({hasText:'No changes'}).waitFor();assert.deepEqual(audit(),before);
  });
  await scenario('dirty_back_discard_preserves_database',async()=>{
    await input().fill('Не сохранять');page.once('dialog',dialog=>dialog.accept());
    await button('← Back to records').click();
    await page.locator('.editor').waitFor({state:'detached'});
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='+ New record'&&!button.disabled));
    assert.equal(audit()[0].description,'Материалы');
  });
  await scenario('reload_reattach_and_host_restart_reopen',async()=>{
    phase='reload_missing_capability';
    await page.reload();await page.getByText('Session capability missing.',{exact:false}).waitFor();
    phase='reattach_existing_host';
    await page.goto(url);await button('+ New record').waitFor();
    await page.locator('.editor').waitFor({state:'detached'});
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='+ New record'&&!button.disabled));
    phase='close_existing_host';
    await button('Close database').click();await page.getByRole('heading',{name:'Database closed',exact:true}).waitFor();
    phase='restart_host';
    await stopHost();await startHost();await page.goto(url);
    phase='reopen_durable_record';
    await page.getByRole('button',{name:/^ВидыНоменклатуры/}).click();await page.locator('.records tbody tr').first().click();await button('Open selected').click();
    assert.equal(await input().inputValue(),'Материалы');assert.equal(audit().length,1);
  });
  assert.equal(git('status','--porcelain','--untracked-files=no'),'','source_changed');
  assert.equal(results.length,8);report.status='PASS';report.rpcRequests=rpc;
}
// Reserve 20 seconds for verified bounded cleanup within the 180s total.
const deadline=setTimeout(abort,Math.max(0,160000-(Date.now()-startedAt)));
try{await main();check();}catch(error){failure=error;report.status='FAIL';report.failure={phase,reason:aborted?'deadline_or_rpc_budget':phase==='sandbox_launch'&&/Operation not permitted|No usable sandbox|Failed to move to new namespace/i.test(String(error?.message))?'sandbox_start_denied':'step_failed'};}
finally{
  aborted=true;clearTimeout(deadline);
  try{if(browser)await bounded(browser.close(),10000,'browser_close_timeout');}catch{report.status='FAIL';report.cleanup='browser_close_failed';}
  killBrowser();
  try{await stopHost();}catch{report.status='FAIL';report.cleanup='host_close_failed';}
  if(browserGroup){
    let gone=false;
    for(let i=0;i<20;i++){try{process.kill(-browserGroup,0);}catch(e){if(e.code==='ESRCH'){gone=true;break;}else break;}await new Promise(r=>setTimeout(r,100));}
    if(!gone){report.status='FAIL';report.cleanup='browser_cleanup_unverified';}
  }
  report.elapsedMs=Date.now()-startedAt;
  await rm(owned,{recursive:true,force:true});
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
console.log(JSON.stringify({status:report.status,completed:results.length,total:8,source:report.sourceCommit,failure:report.failure}));if(failure||report.status!=='PASS')process.exitCode=1;
