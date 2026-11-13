/** Two bounded source-UI smoke flows. No native parity claim. */
import {chromium} from 'playwright';
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, mkdir, writeFile, readFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {launchOutputReader, childEnvironment, sandboxStatus, sha256} from './support.mjs';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const root=process.env.RUNNER_TEMP;assert.ok(root&&path.isAbsolute(root));
assert.notEqual(process.getuid(),0);
const source=execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim();
assert.equal(source,process.env.QA_SOURCE_SHA);
const work=await mkdtemp(path.join(root,'s-'));const home=path.join(work,'h');await mkdir(home);
const output=path.join(root,'yadinassi-source-browser-artifacts');await mkdir(output);
const env=childEnvironment(process.env,home);env.PYTHONPATH=repo+path.delimiter+path.join(repo,'tests');
const fixture=path.join(work,'fixture');
execFileSync('python',['-c',`from test_source_forms import files\nfrom pathlib import Path\nroot=Path(${JSON.stringify(fixture)})\nmapping=files()\nfrom test_source_metadata import xml\nmapping['Configuration.xml']=mapping['Configuration.xml'].replace(b'</ChildObjects>',b'<CommonForm>Broken</CommonForm><CommonForm>Progressive</CommonForm></ChildObjects>')\nmapping['CommonForms/Broken.xml']=xml('CommonForm','Broken',properties='<FormType>Managed</FormType>')\nmapping['CommonForms/Broken/Ext/Form.xml']=b'<Unsupported/>'\nmapping['CommonForms/Progressive.xml']=xml('CommonForm','Progressive',properties='<FormType>Managed</FormType>')\nmapping['CommonForms/Progressive/Ext/Form.xml']=mapping['CommonForms/Main/Ext/Form.xml'].replace(b'<ChildItems>',b'<ChildItems><PictureField name="Logo" id="90"/>')\nmapping['CommonForms/Progressive/Ext/Form/Module.bsl']=mapping['CommonForms/Main/Ext/Form/Module.bsl']\nfor name,data in mapping.items():\n p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)`],{cwd:repo,env,timeout:15000});
const report={status:'FAIL',sourceCommit:source,scenarios:[],nativeParity:false};
let browser,host,context,page,phase='launch';
const deadline=setTimeout(()=>{host?.kill('SIGKILL');process.exitCode=1;browser?.close();},150000);
async function stopHost(){if(!host)return;if(host.exitCode===null&&host.signalCode===null){const p=new Promise(r=>host.once('exit',r));host.kill('SIGINT');await Promise.race([p,new Promise(r=>setTimeout(r,3000))]);if(host.exitCode===null&&host.signalCode===null)host.kill('SIGKILL');await Promise.race([p,new Promise((_,reject)=>setTimeout(()=>reject(Error('host_cleanup_timeout')),3000))]);}host=null;}
try {
 const old=process.env.TMPDIR;process.env.TMPDIR=home;
 try{browser=await chromium.launch({channel:'chromium',headless:true,chromiumSandbox:true,env,timeout:20000});}finally{if(old===undefined)delete process.env.TMPDIR;else process.env.TMPDIR=old;}
 context=await browser.newContext({acceptDownloads:false,serviceWorkers:'block'});context.setDefaultTimeout(10000);
 const probe=await context.newPage();await probe.goto('chrome://sandbox');report.sandbox=sandboxStatus(await probe.locator('body').innerText());await probe.close();
 for(const form of [false,true,'workspace','workspace_loss']) {
  phase=typeof form==='string'?form:form?'selected_form':'diagnostics';
  host=spawn('python',['-m','yadinassi','--ui','--configuration-source',fixture,'--run-startup',...(typeof form==='string'?['--source-workspace']:form?['--source-form','CommonForm.Main']:[])],{cwd:repo,env,stdio:['ignore','pipe','ignore']});
  const url=await new Promise((resolve,reject)=>{const parse=launchOutputReader();const timer=setTimeout(()=>reject(Error('host_timeout')),10000);host.once('exit',()=>{clearTimeout(timer);reject(Error('host_exit'));});host.stdout.on('data',b=>{try{const u=parse(b);if(u){clearTimeout(timer);resolve(u);}}catch(e){clearTimeout(timer);reject(e);}});});
  const origin=new URL(url).origin;
  await context.route('**/*',route=>{const u=new URL(route.request().url());return u.origin===origin&&['/','/app.js','/style.css','/rpc','/client.js'].includes(u.pathname)?route.continue():route.abort();});
  page=await context.newPage();const errors=[];page.on('pageerror',()=>errors.push('page_error'));
  await page.goto(url.href);
  if(!form){await page.getByText('Источник: Demo; попытка запуска: completed',{exact:true}).waitFor();assert.ok((await page.locator('#result').innerText()).includes('"runtime_active": false'));await page.getByRole('button',{name:'Закрыть диагностику'}).click();await page.getByText('Диагностика закрыта',{exact:true}).waitFor();}
  else if(form==='workspace_loss'){
   phase='workspace_loss:open';
   await page.getByRole('combobox',{name:'Объявленная форма'}).selectOption('CommonForm.Main');
   await page.getByRole('button',{name:'Открыть форму',exact:true}).click();
   await page.getByRole('textbox',{name:'GreetingLabel',exact:true}).waitFor();
   let dropped=false;
   await page.route(origin+'/rpc',async route=>{
    const request=route.request();
    if(!dropped&&request.postData()?.includes('"event":"close"')){
     dropped=true;const response=await route.fetch();assert.equal(response.status(),200);
     const body=await response.json();assert.equal(body.result.result.state.kind,'closed');
     return route.abort('failed');
    }
    return route.continue();
   });
   await page.getByRole('button',{name:'Close form',exact:true}).click();
   await page.getByText('Результат действия неизвестен. Формы и черновики сохранены в этой вкладке; переключение и повтор команд заблокированы.',{exact:true}).waitFor();
   assert.equal(dropped,true);
   for(const name of ['Открыть форму','Закрыть сеанс','Найти формы'])assert.equal(await page.getByRole('button',{name,exact:true}).isDisabled(),true);
   assert.equal(await page.getByRole('textbox',{name:'GreetingLabel',exact:true}).inputValue(),'Demo');
  }
  else if(form==='workspace'){
   await page.getByRole('heading',{name:'Demo · Source workspace'}).waitFor();
   await page.getByRole('combobox',{name:'Объявленная форма'}).selectOption('CommonForm.Main');
   for(let cycle=0;cycle<2;cycle++){
    await page.getByRole('button',{name:'Открыть форму',exact:true}).click();
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('input')).some(x=>x.value==='Demo'));
    assert.equal(await page.getByRole('button',{name:'Открыть форму',exact:true}).isEnabled(),true);
    assert.equal(await page.getByRole('button',{name:'Закрыть сеанс',exact:true}).isDisabled(),true);
    await page.getByRole('button',{name:'Run',exact:true}).click();
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('input')).some(x=>x.value==='updated'));
    await page.getByRole('button',{name:'Close form',exact:true}).click();
    await page.getByText('Closed',{exact:true}).waitFor();
   }
   await page.getByRole('textbox',{name:'Поиск объявленных форм'}).fill('Broken');
   await page.getByRole('button',{name:'Найти формы',exact:true}).click();
   await page.getByRole('combobox',{name:'Объявленная форма'}).selectOption('CommonForm.Broken');
   await page.getByRole('button',{name:'Открыть форму',exact:true}).click();
   await page.waitForFunction(()=>!document.querySelector('button')?.disabled);
   assert.equal(await page.getByRole('button',{name:'Закрыть сеанс',exact:true}).isEnabled(),true);
   assert.ok((await page.getByRole('status').first().innerText()).length>0);
   await page.screenshot({path:path.join(output,'workspace-open-close.png')});
   await page.getByRole('textbox',{name:'Поиск объявленных форм'}).fill('Progressive');
   await page.getByRole('button',{name:'Найти формы',exact:true}).click();
   await page.getByRole('combobox',{name:'Объявленная форма'}).selectOption('CommonForm.Progressive');
   await page.getByRole('button',{name:'Открыть форму',exact:true}).click();
   await page.getByRole('list',{name:'Неподдерживаемые возможности формы'}).getByText('Items.Logo: Control unavailable: PictureField',{exact:true}).waitFor();
   await page.getByRole('button',{name:'Run',exact:true}).click();
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('input')).some(x=>x.value==='updated'));
   await page.screenshot({path:path.join(output,'progressive.png')});
   phase='workspace:multiform';
   await page.getByRole('textbox',{name:'Поиск объявленных форм'}).fill('Main');
   await page.getByRole('button',{name:'Найти формы',exact:true}).click();
   await page.getByRole('combobox',{name:'Объявленная форма'}).selectOption('CommonForm.Main');
   await page.getByRole('button',{name:'Открыть форму',exact:true}).click();
   await page.getByRole('textbox',{name:'GreetingLabel',exact:true}).waitFor();
   assert.equal(await page.getByRole('textbox',{name:'GreetingLabel',exact:true}).inputValue(),'Demo');
   await page.getByRole('navigation',{name:'Открытые формы'}).getByRole('button',{name:'CommonForm.Progressive',exact:true}).click();
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('section:not([hidden]) input')).some(x=>x.value==='updated'&&x.getClientRects().length));
   assert.equal(await page.getByRole('textbox',{name:'GreetingLabel',exact:true}).inputValue(),'updated');
   const [response]=await Promise.all([page.waitForResponse(r=>r.url()===origin+'/rpc'&&r.request().postData()?.includes('form.event')),page.getByRole('button',{name:'Run',exact:true}).click()]);
   assert.equal(response.status(),200);await response.finished();assert.equal((await response.json()).result.result.error,null);
   await page.screenshot({path:path.join(output,'multiform.png')});
   await page.getByRole('button',{name:'Close form',exact:true}).click();
   await page.getByText('Closed',{exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Закрыть сеанс',exact:true}).isDisabled(),true);
   await page.getByRole('navigation',{name:'Открытые формы'}).getByRole('button',{name:'CommonForm.Main',exact:true}).click();
   assert.equal(await page.getByRole('textbox',{name:'GreetingLabel',exact:true}).inputValue(),'Demo');

   await page.getByRole('button',{name:'Close form',exact:true}).click();
   await page.getByText('Closed',{exact:true}).waitFor();
   await page.getByRole('button',{name:'Закрыть сеанс',exact:true}).click();
   await page.getByText('Сеанс закрыт',{exact:true}).waitFor();
  }
  else{phase='selected_form:initial';await page.waitForFunction(()=>Array.from(document.querySelectorAll('input')).some(x=>x.value==='Demo'));for(let i=0;i<2;i++){phase='selected_form:command'+i;const [response]=await Promise.all([page.waitForResponse(r=>r.url()===origin+'/rpc'&&r.request().postData()?.includes('form.event')),page.getByRole('button',{name:'Run',exact:true}).click()]);assert.equal(response.status(),200);phase='selected_form:response_body'+i;await response.finished();assert.equal((await response.json()).result.error,null);phase='selected_form:render'+i;await page.waitForFunction(()=>Array.from(document.querySelectorAll('input')).some(x=>x.value==='updated'));}phase='selected_form:close';await page.getByRole('button',{name:'Close form',exact:true}).click();await page.getByText('Closed',{exact:true}).waitFor();}
  phase=typeof form==='string'?form:form?'selected_form':'diagnostics';assert.deepEqual(errors,[]);await page.screenshot({path:path.join(output,phase+'.png')});
  report.scenarios.push({name:phase,status:'PASS'});await page.close();await context.unroute('**/*');await stopHost();
 }
 report.status='PASS';
}catch(error){report.failure={phase,reason:'smoke_failed',errorCode: /No (?:resource|data).*?(?:identifier|resource)/i.test(error?.message||'')?'response_body_unavailable':/getResponseBody/.test(error?.message||'')?'response_body_protocol':/closed/i.test(error?.message||'')?'target_closed':'unclassified',errorType:['TimeoutError','AssertionError','Error','TypeError'].includes(error?.name)?error.name:'other'};if(page){try{await page.screenshot({path:path.join(output,'failure.png')});}catch{}}process.exitCode=1;}
finally{clearTimeout(deadline);await stopHost();await browser?.close();await writeFile(path.join(output,'result.json'),JSON.stringify(report,null,2));const sums={};for(const name of ['result.json',...(report.scenarios.some(x=>x.name==='workspace')?['workspace-open-close.png','progressive.png','multiform.png']:[]),...report.scenarios.map(x=>x.name+'.png')])sums[name]=sha256(await readFile(path.join(output,name)));await writeFile(path.join(output,'manifest.json'),JSON.stringify({sourceCommit:source,sha256:sums},null,2));}
