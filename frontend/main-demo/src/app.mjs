import {mountEditor} from '/catalog.js';
import {mountApplication} from '/configuration.js';
import {createBrowserHost} from '../../form/src/attachment.mjs';
import {MainDemoClient} from './client.mjs';

export function mountMainDemo(environment,root){
  if(typeof environment.CSSScopeRule!=='function'){
    root.textContent='Этот браузер не поддерживает изолированные стили приложения. Откройте демо в современном Chromium. Подключение к базе не выполнялось.';
    return {unsupported:true,ready:Promise.resolve(false)};
  }
  const host=createBrowserHost(environment,root),document=environment.document;
  const el=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  const shell=el('main'),title=el('h1','Единая демо'),nav=el('nav'),notice=el('p'),content=el('div');
  shell.className='main-demo-shell';nav.className='main-demo-navigation';content.className='main-demo-surface';
  title.className='main-demo-title';notice.className='main-demo-notice';
  const retry=el('button','Восстановить состояние');notice.setAttribute('role','status');
  retry.className='main-demo-recover';
  shell.append(title,nav,notice,retry,content);host.content.replaceChildren(shell);
  let mount=null,mountedEpoch=null,busy=false,disposed=false;const timers=new Set();
  const client=new MainDemoClient(host.transport);
  const localBlocked=()=>!mount||!mount.canLeave();
  const buttons=[];
  const paint=()=>{
    content.inert=Boolean(client.uncertain||host.attachment?.businessUnknown);
    for(const [button,surface] of buttons)button.disabled=disposed||busy||client.pending||client.uncertain||!client.state?.canSwitch||localBlocked()||client.state.surface===surface;
    retry.disabled=disposed||busy||client.pending;
    host.notify();
  };
  const dispatch=epoch=>{const exchange=async request=>{
    try{return await client.dispatch(request,epoch);}
    catch(error){notice.textContent='Ответ не получен или отклонён. Не повторяйте действие; восстановите состояние.';throw error;}
    finally{paint();const timer=environment.setTimeout(()=>{timers.delete(timer);if(!disposed)paint();},0);timers.add(timer);}
  };exchange.recover=recover;return exchange;};
  async function install(){
    if(client.state?.uncertain)throw Error('Состояние владельца не определено. Повтор активации запрещён.');
    if(client.state?.kind==='closed'){notice.textContent='Приложение закрыто.';return;}
    if(mount&&mountedEpoch===client.state.epoch){await mount.resume();return;}
    if(mount){if(!mount.canLeave())throw Error('Сохранён локальный черновик: автоматическое переключение запрещено.');mount.destroy();}
    content.replaceChildren();content.className='main-demo-surface '+(client.state.surface==='catalogs'?'main-demo-catalog':'main-demo-documents');mountedEpoch=client.state.epoch;
    mount=client.state.surface==='catalogs'?mountEditor(environment,content,dispatch(mountedEpoch)):mountApplication(environment,content,dispatch(mountedEpoch));
    await mount.ready;
  }
  async function recover(){
    if(disposed||busy)return;busy=true;paint();
    try{
      const inspect=async()=>{await client.snapshot();await install();return {protocol:'yadinassi-main-demo/1',epoch:client.state.epoch,ready:!client.uncertain&&!client.pending&&mount?.recoveryReady()};};
      if(host.enabled)await host.inspect(inspect);else await inspect();
      notice.textContent='Текущее состояние прочитано. Действия не повторялись.';
    }
    catch(error){notice.textContent=error.message;}
    finally{busy=false;paint();}
  }
  async function select(surface){
    if(disposed||busy||client.pending||client.uncertain||!client.state?.canSwitch||localBlocked())return;
    busy=true;paint();
    try{await client.select(surface);await install();notice.textContent='';}
    catch(error){notice.textContent=error.message;}
    finally{busy=false;paint();}
  }
  for(const [surface,label] of [['catalogs','Справочники'],['documents','Документы и отчёты']]){
    const button=el('button',label);button.addEventListener('click',()=>select(surface));nav.append(button);buttons.push([button,surface]);
  }
  retry.addEventListener('click',recover);
  const warn=event=>{if(busy||client.pending||client.uncertain||localBlocked()){event.preventDefault();event.returnValue='';}};
  environment.addEventListener('beforeunload',warn);
  host.setPending(()=>busy||client.pending||client.uncertain||localBlocked(),()=>client.uncertain);
  host.setInspectionAllowed?.(()=>Boolean((client.uncertain||host.attachment?.businessUnknown)&&!busy&&!client.pending&&!host.attachment?.rpcActive));
  // Renderer lifecycle changes can precede another RPC; reevaluate navigation locally.
  const inspect=()=>environment.queueMicrotask(paint);
  content.addEventListener('input',inspect);content.addEventListener('change',inspect);content.addEventListener('click',inspect);
  const ready=host.start(async()=>{await client.hello();await install();paint();});
  paint();return{ready,client,recover,destroy(){if(disposed)return;if(localBlocked()||busy||client.pending)throw Error('Finish current surface');disposed=true;for(const timer of timers)environment.clearTimeout(timer);timers.clear();mount?.destroy();environment.removeEventListener('beforeunload',warn);host.attachment?.dispose();host.content.replaceChildren();}};
}
if(typeof window!=='undefined'&&window.document?.getElementById('main-demo-app'))mountMainDemo(window,window.document.getElementById('main-demo-app'));
