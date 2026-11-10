import {createTransport, takeSessionCapability} from '../../form/src/client.mjs';
import {mountForm} from '../../form/src/app.mjs';
import {APPLICATION_PROTOCOL, ApplicationClient} from './client.mjs';

export function mountApplication(environment, root, exchange = null) {
  const document = environment.document;
  const el = (tag, text = '') => { const node = document.createElement(tag); node.textContent = text; return node; };
  const shell = el('main'), title = el('h1','Configuration forms'), toolbar = el('nav'), entries = el('nav'), tabs = el('nav'), panels = el('div');
  shell.className = 'configuration-app'; entries.setAttribute('aria-label','Declared forms'); tabs.setAttribute('aria-label','Open forms');
  const notice = el('p'); notice.setAttribute('role','status');
  const mounts = new Map(), openings = new Map(); let active = null, openToken = 0, status = '', navigation = 0, client;
  const intents = new Map();
  const button = (text, parent, action) => {
    const node = el('button',text); node.type = 'button'; node.dataset.formAction = 'application-navigation';
    node.addEventListener('pointerdown',event => event.preventDefault()); node.addEventListener('click',action); parent.append(node); return node;
  };
  const pending = () => Boolean(client.pending || client.terminal || client.state?.uncertain || [...mounts.values()].some(entry => entry.mount?.hasPending()));
  function show(id, userNavigation = true) {
    if (userNavigation) navigation++;
    active = id;
    for (const [key, entry] of mounts) {
      if (!entry.panel.hidden && entry.panel.contains(document.activeElement)) {
        const node = document.activeElement; entry.focus = {node,start:node.selectionStart,end:node.selectionEnd};
      }
      entry.panel.hidden = key !== id; entry.tab.setAttribute('aria-selected',String(key === id));
    }
    const saved = mounts.get(id)?.focus;
    if (saved?.node && !saved.node.disabled) { saved.node.focus({preventScroll:true}); if (typeof saved.start === 'number') saved.node.setSelectionRange(saved.start,saved.end); }
  }
  function paint() {
    title.textContent = client.state?.title || 'Configuration forms';
    notice.textContent = client.terminal ? 'Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.' : status;
    const disabled = client.terminal || !client.state || client.state.kind === 'closed';
    close.disabled = disabled; entries.replaceChildren();
    for (const entry of client.state?.entries || []) {
      const node = button(entry.title || `Form ${entry.id}`,entries,() => openForm(entry.id));
      node.disabled = disabled || client.state.sessions.length >= 8;
    }
    for (const entry of mounts.values()) if (client.terminal) entry.mount?.lock();
  }
  function reconcile(result, request) {
    status = result.error ? `Application: ${result.error}` : '';
    const fresh = []; let removedActive = false;
    for (const [id, entry] of mounts) if (!client.state.sessions.some(session => session.id === id)) {
      entry.panel.remove(); entry.tab.remove(); mounts.delete(id); if (active === id) { active = null; removedActive = true; }
    }
    for (const session of client.state.sessions) {
      if (mounts.has(session.id)) { mounts.get(session.id).tab.textContent = session.title; continue; }
      const id = session.id, panel = el('section'); panel.hidden = true; panels.append(panel);
      const tab = button(session.title || 'Form',tabs,() => show(id));
      const entry = {panel,tab,mount:null,focus:null}; mounts.set(id,entry); fresh.push(id);
      entry.mount = mountForm(environment,panel,{transport: request => client.form(id,request),isActive: () => active === id,
        onChange: () => { if (entry.mount?.client?.transportFailed) client.lock(); paint(); }});
    }
    const generation = request?.method === 'application.open' ? intents.get(request.params.request) : undefined;
    if (fresh.length && (generation === undefined || generation === navigation)) show(client.state.active || fresh.at(-1),false);
    else if (removedActive) show(client.state.active,false);
    paint();
  }
  async function perform(method,params) {
    try { return await client.request(method,params); }
    catch { status = 'Application connection failed.'; paint(); }
  }
  function openForm(entry) {
    if (openings.has(entry)) return openings.get(entry);
    const token = `open-${++openToken}`; intents.set(token,navigation);
    const opening = perform('application.open',{entry,request:token}).finally(() => { openings.delete(entry); intents.delete(token); });
    openings.set(entry,opening); return opening;
  }
  const close = button('Close application',toolbar,async () => {
    if (pending() || mounts.size) { status = 'Close each form, including hidden tabs, before closing the application.'; paint(); return; }
    await perform('application.close',{});
  });
  shell.append(title,toolbar,entries,tabs,notice,panels); root.replaceChildren(shell);
  if (!exchange) {
    try { exchange = createTransport(environment.fetch.bind(environment),takeSessionCapability(environment.location,environment.history)); }
    catch { exchange = async () => { throw Error('Missing session'); }; }
  }
  client = new ApplicationClient(exchange,reconcile,() => { for (const entry of mounts.values()) entry.mount?.lock(); paint(); });
  environment.addEventListener('beforeunload',event => { if (pending()) { event.preventDefault(); event.returnValue = ''; } });
  paint(); const ready = perform('application.hello',{protocol:APPLICATION_PROTOCOL});
  return {ready,client,mounts,show,pending,openForm};
}
if (typeof window !== 'undefined' && window.document?.getElementById('configuration-app')) mountApplication(window,window.document.getElementById('configuration-app'));
