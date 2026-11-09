/** Opt-in owned form-app browser scenarios; never part of unit-test discovery. */
import {createRequire} from 'node:module';
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, mkdir, writeFile, readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {launchOutputReader, allowedRequest, sandboxStatus, ownBrowserPid, commandLineArgs, sandboxCommand} from './support.mjs';
const {chromium}=createRequire(import.meta.url)('playwright');
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const python=process.env.QA_PYTHON||'python';
const owned=await mkdtemp(path.join(tmpdir(),'yadinassi-form-browser-'));
const artifacts=path.join(owned,'artifacts'); await mkdir(artifacts);
const records=[];let browser,context,host,origin='',phase='browser_start';
const bounded=(promise,ms)=>{
  let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('deadline')),ms);})]).finally(()=>clearTimeout(timer));
};
async function stopHost(){
  if(!host)return;
  if(host.exitCode===null&&host.signalCode===null){
    const exited=new Promise(resolve=>host.once('exit',resolve));host.kill('SIGINT');
    try{await bounded(exited,12000);}catch{host.kill('SIGKILL');await bounded(exited,3000);}
  }
}
async function startHost(example,database){
  const args=['-m','yadinassi.ui.form_app',path.join(repo,'examples/forms',example)];
  if(database)args.push('--f',database);
  host=spawn(python,args,{cwd:repo,stdio:['ignore','pipe','pipe']});
  host.stderr.resume();const reader=launchOutputReader();
  return bounded(new Promise((resolve,reject)=>{
    let settled=false;
    host.once('error',()=>reject(Error('host_start')));
    host.once('exit',()=>{if(!settled)reject(Error('host_exit'));});
    host.stdout.on('data',chunk=>{
      if(settled)return;
      try{const url=reader(chunk);if(url){settled=true;origin=url.origin;resolve(url.href);}}
      catch{settled=true;reject(Error('host_url'));}
    });
  }),15000);
}
try{
  browser=await chromium.launch({headless:true,chromiumSandbox:true,...(process.env.QA_CHROMIUM?{executablePath:process.env.QA_CHROMIUM}:{})});
  phase='sandbox_inspection';
  const cdp=await browser.newBrowserCDPSession();
  const pid=ownBrowserPid((await cdp.send('SystemInfo.getProcessInfo')).processInfo);
  sandboxCommand(commandLineArgs(await readFile('/proc/'+pid+'/cmdline')));
  const inspection=await browser.newPage();await inspection.goto('chrome://sandbox');
  const sandbox=sandboxStatus(await inspection.locator('body').innerText());await inspection.close();
  phase='browser_scenarios';
  context=await browser.newContext({viewport:{width:1100,height:850}});
  await context.route('**/*',route=>allowedRequest(route.request().url(),origin)?route.continue():route.abort());
  let page=await context.newPage();page.setDefaultTimeout(15000);
  const url=await startHost('estimate');await page.goto(url);
  await page.getByRole('heading',{name:'Estimate calculator'}).waitFor();
  const field=name=>page.getByLabel(name,{exact:true});
  await field('Unit price').fill('7.25');
  await page.getByRole('button',{name:'Calculate',exact:true}).click();
  await page.waitForFunction(()=>[...document.querySelectorAll('label')].some(x=>x.textContent.includes('Total')&&x.querySelector('input')?.value==='21.75'));
  assert.equal(await field('Total').inputValue(),'21.75');
  assert.equal(await page.evaluate(()=>location.hash),'');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  await page.screenshot({path:path.join(artifacts,'estimate.png')});
  records.push({name:'edit_then_command_exact_decimal',status:'PASS'});
  // A duplicate click while an accepted event is in flight must not add an event.
  const events=[];page.on('request',r=>{if(r.url().endsWith('/rpc')){const data=JSON.parse(r.postData());if(data.method==='form.event')events.push(data.params.event);}});
  await page.evaluate(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent==='Calculate');b.click();b.click();});
  await page.waitForFunction(()=>document.querySelector('[aria-busy]')?.getAttribute('aria-busy')==='false');
  assert.deepEqual(events,['command']);
  await field('Unit price').fill('9');await page.getByRole('button',{name:'Close form',exact:true}).click();
  await page.getByText('Run the command before closing, or stop the launcher to discard edits.',{exact:true}).waitFor();
  await page.goto(url);await page.getByRole('heading',{name:'Estimate calculator'}).waitFor();
  assert.equal(await field('Unit price').inputValue(),'9');
  await page.getByRole('button',{name:'Calculate',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[aria-busy]')?.getAttribute('aria-busy')==='false');
  await page.getByRole('button',{name:'Close form',exact:true}).click();
  await page.getByText('This form is closed. You can close this tab.',{exact:true}).waitFor();
  await stopHost();records.push({name:'duplicate_click_close_cancel_and_reattach',status:'PASS'});
  const database=path.join(owned,'products.sqlite');
  execFileSync(python,['-m','yadinassi','--create-db',database,'--import-xml',path.join(repo,'examples/forms/product-intake/configuration')],{cwd:repo,stdio:'pipe',timeout:15000});
  await page.close();page=await context.newPage();page.setDefaultTimeout(15000);
  const productURL=await startHost('product-intake',database);await page.goto(productURL);
  await page.getByRole('heading',{name:'Create a product'}).waitFor();
  for (const [name,value] of [['Code','B001'],['Description','Browser-owned product'],['Amount','18.75']]) {
    await field(name).fill(value);await field(name).press('Enter');
    await page.waitForFunction(()=>document.querySelector('[aria-busy]')?.getAttribute('aria-busy')==='false');
  }
  await page.getByRole('button',{name:'Create product',exact:true}).click();
  await page.getByText('Product saved',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Create product',exact:true}).isDisabled(),true);
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(artifacts,'product-narrow.png')});
  await page.getByRole('button',{name:'Close form',exact:true}).click();
  await page.getByText('This form is closed. You can close this tab.',{exact:true}).waitFor();await stopHost();
  const readback=execFileSync(python,['-m','yadinassi','--f',database,'-c','Message(Catalogs.Products.FindByCode("B001").Amount);'],{cwd:repo,encoding:'utf8',stdio:'pipe',timeout:15000});
  assert.equal(readback.trim(),'18,75');records.push({name:'sqlite_save_close_and_durable_readback',status:'PASS'});
  await writeFile(path.join(artifacts,'result.json'),JSON.stringify({status:'PASS',sandbox,scenarios:records},null,2)+'\n');
  console.log(JSON.stringify({status:'PASS',scenarios:records,artifacts}));
}catch(error){
  // No capability URL, page contents, request payload or database path in errors.
  console.error(JSON.stringify({status:'FAIL',completed:records.map(x=>x.name),reason:error instanceof assert.AssertionError?'assertion':'browser_or_host_failure',phase,artifacts}));
  process.exitCode=1;
}finally{await context?.close();await browser?.close();await stopHost();}
