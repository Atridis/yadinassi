/** Closed owned-dialog browser acquisition; no native timing/parity claim. */
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
const screenshots=['dialogs-completion.png','dialogs-refusal.png','dialogs-retained.png','dialogs-locked-copy.png'];
const artifacts=['result.json','manifest.json',...screenshots];
const scenarioNames=['question_yes_once_shared_identity','no_cancel_warning_and_escape_no_answer',
 'independent_draft_retained_and_natural_close','lost_confirmed_answer_copy_only_no_replay'];
// Startup opens the first owner without a browser business RPC.
const businessPlan=[
 ['command:QuestionButton','answer:yes'],
 ['command:QuestionButton','answer:no','command:QuestionButton','answer:cancel','command:WarningButton','answer:dismiss'],
 ['open','command:QuestionButton','answer:yes','close:','close:','close'],
 ['open','command:QuestionButton','answer:yes']
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
  check();assert.ok(!host&&!hostGroup,'previous_host_live');lastApplicationState=null;lastApplicationResult=null;
  const args=['-m','yadinassi.ui.configuration_app',path.join(repo,'examples/configuration-dialogs'),'--application-host','--browser-session'];
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
const ownerTabs=()=>tabs().getByRole('button',{name:'Confirmation workflow',exact:true});
const replyFor=predicate=>page.waitForResponse(response=>new URL(response.url()).pathname==='/rpc'&&response.status()===200&&predicate(response.request().postDataJSON()),{timeout:remaining(rpcReplyMs)});
const formReply=(event,control)=>replyFor(packet=>packet.method==='application.form'&&packet.params.request.method==='form.event'&&packet.params.request.params.event===event&&(!control||packet.params.request.params.control===control));
let lastApplicationState=null,lastApplicationResult=null;
// Keep the already audited real bytes until this exact delivered command is
// observed. Chromium can evict a response body before a later CDP read; never
// issue another RPC or substitute current UI state for that response.
const observedCommands=new Map();
async function command(title,control){
  report.commandStage='bind_session';
  const index=await panels().evaluateAll(nodes=>nodes.findIndex(node=>!node.hidden));
  assert.equal(lastApplicationState?.sessions.length,await panels().count(),'session_panel_binding');
  const session=lastApplicationState?.sessions[index]?.id;
  assert.match(session||'',/^form-[1-9][0-9]*$/,'active_session_missing');
  const reply=replyFor(packet=>packet.method==='application.form'&&packet.params.session===session&&
    packet.params.request.method==='form.event'&&packet.params.request.params.event==='command'&&
    packet.params.request.params.control===control);
  report.commandStage='click';await action(title).click();
  report.commandStage='await_response';const response=await reply;
  report.commandStage='read_response';const packet=response.request().postDataJSON();
  const observed=observedCommands.get(packet.id);observedCommands.delete(packet.id);
  assert.ok(observed,'audited_command_missing');
  assert.deepEqual(observed.packet,packet,'audited_command_mismatch');const data=observed.actual;
  report.commandStage='verify_response';
  const errors=[null,'invalid_request','stale_revision','event_failed','closed','outcome_unknown','busy','request_limit','reference_refused','retired_session'];
  const safeError=code=>errors.includes(code)?code:'unexpected_protocol_code';
  report.lastCommand={sessionMatches:data.result.session===session,applicationError:safeError(data.result.error),formError:safeError(data.result.form?.result?.error)};
  assert.equal(data.result.session,session,'command_session_changed');
  assert.equal(data.result.error,null,'application_command_failed');
  assert.equal(data.result.form.result.error,null,'form_command_failed');report.commandStage='await_idle';await idle();report.commandStage='completed';
}
async function closeForm(){const reply=formReply('close');await action('Close form').click();await reply;await idle();}
async function naturalStop(){
 const ended=new Promise(resolve=>host.once('exit',(code,signal)=>resolve({code,signal})));
 const reply=replyFor(packet=>packet.method==='application.close');await button('Close application').click();await reply;
 const result=await bounded(ended,remaining(10000),'natural_shutdown_timeout');
 assert.deepEqual(result,{code:0,signal:null},'natural_shutdown_failed');
 await groupGone(hostGroup);host=null;hostGroup=null;origin='';
}
let delayed=null,dropNextAnswer=false;
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
  }else if(packet.method==='application.answerDialog'){
    exactKeys(packet.params,'session ticket answer');
    assert.match(packet.params.session,/^form-[1-9][0-9]*$/);
    const descriptor=lastApplicationResult?.dialogs.find(d=>d.owner===packet.params.session&&d.ticket===packet.params.ticket);
    assert.ok(descriptor&&descriptor.choices.includes(packet.params.answer),'answer_descriptor_binding');
    businessEvents.push('answer:'+packet.params.answer);
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
      if(event.event!=='close')assert.ok(['GreetingLabel','DetailsButton','QuestionButton','WarningButton'].includes(event.control),'declared_control');
      if(event.event==='change'){
        exactKeys(event.value,'type value');
        if(event.control==='KeepOpenCheck'){assert.equal(event.value.type,'Boolean');assert.equal(typeof event.value.value,'boolean');}
        else{assert.equal(event.value.type,'String');assert.equal(typeof event.value.value,'string');assert.ok(event.value.value.length<=256,'declared_string_budget');}
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
async function auditResponse(response,packet){
  assert.equal(response.status(),200,'rpc_status');
  const body=await response.body();assert.ok(body.length<=262144,'reply_budget');
  const text=body.toString('utf8');const decoded=JSON.parse(text);
  const result=decoded.result,state=result?.state;
  exactKeys(decoded,'jsonrpc id result');assert.equal(decoded.jsonrpc,'2.0');assert.equal(decoded.id,packet.id);
  exactKeys(result,'protocol state error session form updates dialogCapability dialogs inputCapability inputs');
  assert.equal(result.inputCapability,'yadinassi-owned-input/1');assert.deepEqual(result.inputs,[],'unexpected_input');
  assert.equal(result.dialogCapability,'yadinassi-owned-dialog/1');assert.ok(Array.isArray(result.dialogs)&&result.dialogs.length<=8,'dialog_bound');
  const tickets=new Set(),owners=new Set();
  for(const dialog of result.dialogs){
    exactKeys(dialog,'ticket owner kind title text choices');
    assert.match(dialog.ticket,/^[0-9a-f]{32}$/);assert.ok(!tickets.has(dialog.ticket),'dialog_ticket');tickets.add(dialog.ticket);
    assert.match(dialog.owner,/^form-[1-9][0-9]*$/);assert.ok(!owners.has(dialog.owner),'dialog_owner');owners.add(dialog.owner);
    assert.ok(['question','warning'].includes(dialog.kind));assert.equal(typeof dialog.title,'string');assert.ok(dialog.title.length<=256);
    assert.equal(typeof dialog.text,'string');assert.ok(dialog.text.length<=4096);
    assert.deepEqual(dialog.choices,dialog.kind==='warning'?['dismiss']:['yes','no','cancel']);
  }
  assert.equal(result.protocol,'yadinassi-configuration-app/3');
  exactKeys(state,'kind title entries sessions active uncertain catalog lifecycle messages exitWarning');
  assert.ok(Array.isArray(state.sessions)&&state.sessions.length<=8,'session_bound');
  const ids=new Set();for(const item of state.sessions){
    exactKeys(item,'id entry title owner blocked');assert.match(item.id,/^form-[1-9][0-9]*$/);assert.ok(!ids.has(item.id));ids.add(item.id);
    assert.ok(item.owner===null||/^form-[1-9][0-9]*$/.test(item.owner));assert.equal(typeof item.blocked,'boolean');
  }
  for(const owner of owners)assert.ok(ids.has(owner),'dialog_owner_missing');
  for(const item of state.sessions){
    assert.equal(item.blocked,(state.sessions.some(child=>child.owner===item.id)||owners.has(item.id)),'owner_pause_graph');
    if(item.owner!==null)assert.ok(ids.has(item.owner)&&item.owner!==item.id,'owner_identity_graph');
  }
  assert.ok(Array.isArray(result.updates)&&result.updates.length<=8,'update_bound');
  const updated=new Set();for(const update of result.updates){
    exactKeys(update,'session form');assert.ok(ids.has(update.session)&&!updated.has(update.session),'update_identity');updated.add(update.session);
    const previous=lastApplicationState?.sessions.find(item=>item.id===update.session);
    assert.ok(previous?.blocked&&lastApplicationState.sessions.some(item=>item.owner===update.session&&!ids.has(item.id)),'update_requires_retired_child');
    exactKeys(update.form,'jsonrpc id result');assert.equal(update.form.id,1);assert.equal(update.form.jsonrpc,'2.0');
    exactKeys(update.form.result,'protocol state error');assert.equal(update.form.result.protocol,'yadinassi-form-ui/1');
    assert.ok([null,'event_failed','outcome_unknown'].includes(update.form.result.error));
  }
  lastApplicationState=state;lastApplicationResult=result;
  assert.ok(!/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(text),'persistent_uuid_leak');
  for(const key of ['operation_id','database_id','record_id','expected_revision','expanded_requests','source_files','callback','additional_parameters','_form_target','enrollment'])
    assert.ok(!text.includes('"'+key+'"'),'private_host_envelope_leak');
  return decoded;
}
function completion(result,answer,total,greeting='Approved value'){
  assert.equal(result.error,null,'answer_application_error');assert.deepEqual(result.updates,[],'answer_updates');
  assert.deepEqual(result.dialogs,[],'answered_dialog_retained');
  const owner=result.state.sessions.find(item=>item.id===result.session);
  assert.ok(owner&&!owner.blocked,'owner_not_resumed');
  const snapshot=result.form.result.state;assert.equal(result.form.result.error,null,'answer_form_error');
  const item=name=>snapshot.items.find(i=>i.name===name)?.value;
  assert.deepEqual(item('GreetingLabel'),{type:'String',value:greeting},'answer_greeting');
  assert.deepEqual(item('AnswerLabel'),{type:'String',value:answer},'answer_label');
  assert.equal(item('CountLabel')?.type,'Number','completion_number_type');
  assert.equal(String(item('CountLabel')?.value),String(total),'completion_total');
  assert.deepEqual(snapshot.messages,['Completion count: 1','Additional parameters shared: Да'],'shared_identity_messages');
}
const dialog=()=>page.locator('.configuration-dialog:not([hidden])');
const answerButton=label=>dialog().getByRole('button',{name:label,exact:true});
async function answer(label,code){
  const reply=replyFor(p=>p.method==='application.answerDialog'&&p.params.answer===code);
  await answerButton(label).click();const response=await reply;
  const packet=response.request().postDataJSON(),observed=observedCommands.get(packet.id);observedCommands.delete(packet.id);
  assert.ok(observed,'audited_answer_missing');assert.deepEqual(observed.packet,packet);
  await idle();return observed.actual.result;
}
async function completionVisible(){
  const section=active().locator('[aria-label="Form messages"]');
  await section.getByText('Completion count: 1',{exact:true}).waitFor();
  await section.getByText('Additional parameters shared: Да',{exact:true}).waitFor();
  assert.equal(await section.locator('p').count(),2,'completion_message_duplicate');
  const items=lastApplicationResult.form.result.state.items;
  await value('Last answer',items.find(i=>i.name==='AnswerLabel').value.value);
  await value('Total completions',String(items.find(i=>i.name==='CountLabel').value.value));
}
async function repeatClick(locator){await locator.evaluate(control=>{control.click();control.click();});}
async function scenario(name,fn){
 check();phase=name;const start=businessEvents.length,index=scenarioNames.indexOf(name);
 await fn();check();assert.deepEqual(businessEvents.slice(start),businessPlan[index],'business_rpc_plan_changed');
 results.push({name,status:'PASS',businessRpc:businessEvents.length-start});
}
async function screenshot(name){
  assert.ok(screenshots.includes(name),'unexpected_screenshot');
  assert.equal(await page.evaluate(()=>location.hash),'','capability_not_removed');
  assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:Object.keys(sessionStorage)})),{local:0,session:['yadinassi.browser.resume/1']},'only_resume_storage');
  assert.equal((await context.cookies()).length,0,'browser_cookies_not_empty');
  await page.screenshot({path:path.join(output,name),animations:'disabled',timeout:remaining(10000)});
}
async function sourceBinding(){
  const names=git('ls-files','-z','yadinassi','pyproject.toml','frontend/form','frontend/configuration','examples/configuration-dialogs','tests/browser_ui',
    'tests/configuration_dialog_fixture.py','tests/test_configuration_dialogs.py','tests/test_configuration_dialogs_browser_qa_contract.py','docs/configuration-dialogs.md','docs/configuration-dialogs-browser-qa.md',
    '.github/workflows/configuration-dialogs-browser-qa.yml').split('\0').filter(Boolean);
  const source={};for(const name of names){check();source[name]=sha256(await readFile(path.join(repo,name)));}
  return {commit:git('rev-parse','HEAD'),tree:git('rev-parse','HEAD^{tree}'),source};
}
async function main(){
  if(!temporary||!path.isAbsolute(temporary)||process.platform!=='linux'||process.getuid()===0)
    throw Error('ordinary_nonroot_linux_runner_required');
  output=path.join(temporary,'yadinassi-dialogs-browser-artifacts');
  await mkdir(output);outputCreated=true; // Reject stale evidence, never overwrite it.
  assert.match(process.env.QA_SOURCE_SHA||'',/^[0-9a-f]{40}$/,'source_commit_required');
  report.sourceCommit=git('rev-parse','HEAD');
  assert.equal(report.sourceCommit,process.env.QA_SOURCE_SHA,'source_commit_mismatch');
  assert.equal(git('status','--porcelain','--untracked-files=all'),'','tracked_checkout_dirty');
  report.binding=await sourceBinding();
  report.versions={node:process.version,playwright:JSON.parse(await readFile(new URL('./node_modules/playwright/package.json',import.meta.url),'utf8')).version};
  assert.equal(report.versions.playwright,'1.64.1','playwright_version_mismatch');
  owned=await mkdtemp(path.join(temporary,'r-'));
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
        const actual=await auditResponse(response,packet);
        if(event?.event==='command'||packet.method==='application.answerDialog'){
          assert.ok(observedCommands.size<96,'audited_command_budget');
          observedCommands.set(packet.id,{packet,actual});
        }
        if(dropNextAnswer&&packet.method==='application.answerDialog'){
          dropNextAnswer=false;completion(actual.result,'Yes',1);
          report.confirmedAnswerBeforeLoss={ownerUpdated:true,completionCount:1};
          return await route.abort('failed');
        }
        if(delayed&&packet.method==='application.answerDialog'){
          const gate=delayed;delayed=null;completion(actual.result,'Yes',1);
          gate.arrived();await bounded(gate.wait,remaining(10000),'late_reply_gate_timeout');
        }
        return await route.fulfill({response});
      }catch{wireFailure=true;abort();return route.abort().catch(()=>{});}
    }
    return route.continue();
  });
  page=await context.newPage();
  const writer=()=>page.waitForFunction(()=>document.querySelector('.browser-ownership')?.dataset.role==='writer',null,{timeout:remaining(10000)});
  const openOwner=async()=>{
    const reply=replyFor(packet=>packet.method==='application.open');
    await entries().getByRole('button',{name:'Confirmation workflow',exact:true}).click();await reply;await idle();await field('Owner draft').waitFor();
  };
  const ask=async()=>{await command('Ask confirmation','QuestionButton');await dialog().waitFor();};
  await scenario(scenarioNames[0],async()=>{
    phase='dialogs_host_start';await startHost();await page.goto(url);await writer();await countPanels(1);
    await value('Owner draft','Editable owner draft');await ask();
    const before=businessEvents.length;
    assert.equal(await field('Owner draft').isDisabled(),true,'paused_owner_input_enabled');
    assert.equal(await action('Ask confirmation').isDisabled(),true,'paused_owner_command_enabled');
    await action('Ask confirmation').evaluate(n=>n.click());assert.equal(businessEvents.length,before,'paused_owner_dispatched');
    let arrived,release;const atGate=new Promise(r=>{arrived=r;}),wait=new Promise(r=>{release=r;});delayed={arrived,wait};
    const reply=replyFor(p=>p.method==='application.answerDialog');
    await repeatClick(answerButton('Yes'));
    try{
      await bounded(atGate,remaining(10000),'held_answer_not_received');
      assert.equal(await answerButton('Yes').isDisabled(),true,'busy_answer_enabled');
      assert.equal(await field('Owner draft').inputValue(),'Editable owner draft','answer_applied_before_delivery');
    }finally{release();}
    const response=await reply;const packet=response.request().postDataJSON();
    const observed=observedCommands.get(packet.id);observedCommands.delete(packet.id);assert.ok(observed,'audited_answer_missing');
    completion(observed.actual.result,'Yes',1);await idle();await value('Owner draft','Approved value');await completionVisible();
    await screenshot(screenshots[0]);
  });
  await scenario(scenarioNames[1],async()=>{
    phase='dialogs_answers';await ask();
    const before=businessEvents.length;await page.keyboard.press('Escape');
    assert.equal(await dialog().count(),1,'escape_closed_dialog');assert.equal(businessEvents.length,before,'escape_sent_answer');
    completion(await answer('No','no'),'No',2);await value('Owner draft','Approved value');
    await ask();completion(await answer('Cancel','cancel'),'Cancel',3);
    await command('Show warning','WarningButton');await dialog().waitFor();
    completion(await answer('Continue','dismiss'),'Warning dismissed',4);await completionVisible();
    await value('Owner draft','Approved value');await screenshot(screenshots[1]);
  });
  await scenario(scenarioNames[2],async()=>{
    phase='dialogs_retained_owner';await openOwner();await countPanels(2);
    const siblingId=await field('Owner draft').getAttribute('id');await field('Owner draft').fill('  independent raw draft  ');
    const before=businessEvents.length;await ownerTabs().first().click();assert.equal(businessEvents.length,before,'navigation_flushed_sibling');
    await ask();completion(await answer('Yes','yes'),'Yes',5);await completionVisible();
    await ownerTabs().nth(1).click();await value('Owner draft','  independent raw draft  ');
    assert.equal(await field('Owner draft').getAttribute('id'),siblingId,'retained_input_replaced');
    assert.equal(await active().locator('[aria-label="Form messages"] p').count(),0,'sibling_received_callback');
    await screenshot(screenshots[2]);
    const refreshed=replyFor(p=>p.method==='application.form'&&p.params.request.method==='form.snapshot');
    await action('Refresh state').click();await refreshed;await idle();await value('Owner draft','Editable owner draft');
    await closeForm();await countPanels(1);await closeForm();await countPanels(0);await naturalStop();report.naturalShutdown=true;
  });
  await scenario(scenarioNames[3],async()=>{
    phase='dialogs_fault_host_start';observedCommands.clear();await startHost();await page.goto(url);await writer();await countPanels(1);
    await openOwner();await countPanels(2);await field('Owner draft').fill('  raw copy after loss  ');await ownerTabs().first().click();await ask();
    dropNextAnswer=true;await answerButton('Yes').click();
    await page.getByText('Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.',{exact:true}).waitFor();await idle();
    assert.deepEqual(report.confirmedAnswerBeforeLoss,{ownerUpdated:true,completionCount:1},'real_answer_not_observed');
    const before=businessEvents.length;await ownerTabs().nth(1).click();
    const copy=active().locator('.draft-recovery-value');
    assert.ok((await copy.allTextContents()).includes('GreetingLabel:   raw copy after loss  '),'exact_raw_copy_missing');
    assert.equal(await copy.first().evaluate(n=>getComputedStyle(n).userSelect),'text','copy_not_selectable');
    for(const label of ['Refresh state','Ask confirmation','Show warning','Close form']){
      assert.equal(await action(label).isDisabled(),true,'locked_command_enabled');await action(label).evaluate(n=>n.click());
    }
    assert.equal(await field('Owner draft').isDisabled(),true,'locked_input_enabled');
    await button('Close application').evaluate(n=>n.click());
    await field('Owner draft').evaluate(n=>n.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})));
    assert.equal(businessEvents.length,before,'locked_intent_replayed');await screenshot(screenshots[3]);
    report.acceptance={questionCallbackOnce:true,warningCallbackOnce:true,sharedAdditionalObserved:true,
      retainedIndependentDraft:true,confirmedAnswerBeforeResponseLoss:true,noAutomaticReplay:true,
      copyOnlyAfterLoss:true,naturalShutdownBeforeFault:true,nativeDialogParity:false,
      nativeKeyboardParity:false,durableCallbackRecovery:false};
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
  const fixedAssertions=['session_panel_binding','active_session_missing','command_session_changed','application_command_failed','form_command_failed',
    'answer_descriptor_binding','dialog_owner_missing','answer_application_error','answer_updates','answered_dialog_retained','answer_form_error','answer_greeting','answer_label','completion_number_type','completion_total','shared_identity_messages','audited_answer_missing','held_answer_not_received','busy_answer_enabled','answer_applied_before_delivery','escape_closed_dialog','escape_sent_answer','real_answer_not_observed','owner_pause_graph','owner_identity_graph','update_requires_retired_child','busy_accept_enabled','retirement_before_response_delivery',
    'owner_not_resumed','paused_owner_input_enabled','paused_owner_command_enabled','paused_owner_close_enabled','paused_owner_dispatched',
    'refused_close_completed','refused_child_retired','navigation_flushed_sibling','retained_input_replaced','real_close_not_observed',
    'exact_raw_copy_missing','copy_not_selectable','locked_input_enabled','locked_refresh_enabled','locked_command_enabled','locked_close_enabled','locked_intent_replayed'];
  report.assertion=fixedAssertions.includes(assertion)?assertion:'unclassified_step';
  report.failureClass=['AssertionError','TimeoutError','TypeError','Error'].includes(error?.name)?error.name:'other';
  const reason=String(error?.message||'');
  report.observerFailure=/No resource with given identifier|No data found for resource/.test(reason)?'response_body_unavailable':
    /Target page, context or browser has been closed/.test(reason)?'browser_closed':
    /strict mode violation/.test(reason)?'ambiguous_locator':
    /Cannot read properties/.test(reason)?'missing_observer_value':'unclassified';
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
