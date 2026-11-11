import {createTransport, takeSessionCapability} from '../../form/src/client.mjs';
import {mountForm} from '../../form/src/app.mjs';
import {createBrowserHost, documentInstance} from '../../form/src/attachment.mjs';
import {APPLICATION_PROTOCOL, ApplicationClient} from './client.mjs';

export function mountApplication(environment, root, exchange = null) {
  const browserHost = exchange ? null : createBrowserHost(environment, root);
  root = browserHost?.content || root;
  const instance = browserHost?.instance || documentInstance(environment);
  const document = environment.document;
  const el = (tag, text = '') => { const node = document.createElement(tag); node.textContent = text; return node; };
  const shell = el('main'), title = el('h1','Configuration forms'), toolbar = el('nav'), entries = el('nav'), tabs = el('nav'), panels = el('div');
  const workarea = el('div'), catalogPanel = el('section'); workarea.className = 'configuration-workarea';
  panels.className = 'configuration-form-panels';
  catalogPanel.className = 'configuration-catalog'; catalogPanel.setAttribute('aria-label','Catalog records'); catalogPanel.hidden = true;
  shell.className = 'configuration-app'; entries.setAttribute('aria-label','Declared forms'); tabs.setAttribute('aria-label','Open forms');
  const notice = el('p'); notice.setAttribute('role','status');
  const applicationMessages = el('section'), exitWarning = el('p');
  applicationMessages.setAttribute('aria-label','Application messages'); applicationMessages.setAttribute('aria-live','polite');
  exitWarning.setAttribute('role','status');
  const mounts = new Map(), openings = new Map(); let active = null, openToken = 0, status = '', navigation = 0, client;
  const intents = new Map();
  let selectedEntry = null; const selectedRecords = new Set();
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
    workarea.className = active && client.state?.catalog ? 'configuration-workarea with-form' : 'configuration-workarea';
  }
  function reconcileSelection() {
    const catalog = client.state?.catalog;
    if (!catalog || selectedEntry !== catalog.entry) selectedRecords.clear();
    selectedEntry = catalog?.entry ?? null;
    const keys = new Set(catalog?.rows.map(row => row.key) || []);
    for (const key of selectedRecords) if (!keys.has(key)) selectedRecords.delete(key);
  }
  function drawCatalog() {
    reconcileSelection(); catalogPanel.replaceChildren();
    const catalog = client.state?.catalog;
    catalogPanel.hidden = !catalog;
    workarea.className = active && catalog ? 'configuration-workarea with-form' : 'configuration-workarea';
    if (!catalog) return;
    const entry = client.state.entries.find(entry => entry.id === catalog.entry);
    const document = entry.kind === 'document-object';
    const heading = el('h2',entry.title), actions = el('div'); actions.className = 'catalog-commands';
    const unavailable = () => client.terminal || client.state?.uncertain || client.state?.kind === 'closed' || client.pending > 0;
    const create = button(document ? 'New document' : 'New record',actions,() => { if (!unavailable()) openForm(catalog.entry); });
    const openSelected = () => {
      // Resolve from the live set and latest projection, never a captured row
      // index or a previous render's single selection.
      reconcileSelection();
      const current = client.state?.catalog, key = [...selectedRecords][0];
      if (!unavailable() && selectedRecords.size === 1 && current?.rows.some(row => row.key === key)) openForm(current.entry,key);
    };
    const open = button('Open selected',actions,openSelected);
    const refresh = button('Refresh records',actions,() => { if (!unavailable()) perform('application.catalog',{entry:catalog.entry}); });
    const count = el('span'); count.setAttribute('aria-label','Selected record count'); count.setAttribute('aria-live','polite'); actions.append(count);
    const table = el('table'), head = el('thead'), headings = el('tr');
    for (const title of (document ? ['Select','Number','Date','Deletion mark'] : ['Select','Code','Description','Deletion mark'])) headings.append(el('th',title));
    head.append(headings);table.append(head);const body = el('tbody'); table.append(body);
    const rows = [];
    function paintSelection() {
      for (const {row,check,key} of rows) { const checked = selectedRecords.has(key); check.checked = checked; check.disabled = unavailable(); row.setAttribute('aria-selected',String(checked)); }
      count.textContent = `${selectedRecords.size} selected`;
      open.disabled = unavailable() || selectedRecords.size !== 1; create.disabled = refresh.disabled = unavailable();
    }
    function select(key, multiple) {
      if (unavailable()) return;
      if (multiple) { if (selectedRecords.has(key)) selectedRecords.delete(key); else selectedRecords.add(key); }
      else { selectedRecords.clear(); selectedRecords.add(key); }
      paintSelection();
    }
    for (const record of catalog.rows) {
      const row = el('tr'), selectCell = el('td'), check = el('input'); check.type = 'checkbox'; row.tabIndex = 0;
      row.dataset.recordKey = record.key;check.setAttribute('aria-label',`Select ${document ? record.number : record.code} ${document ? record.date : record.description}`);
      check.addEventListener('click',event => { event.stopPropagation?.(); select(record.key,true); });
      row.addEventListener('click',event => select(record.key,Boolean(event.ctrlKey || event.metaKey)));
      row.addEventListener('keydown',event => {
        if (event.target && event.target !== row) return;
        if (event.key === ' ') { event.preventDefault();select(record.key,Boolean(event.ctrlKey || event.metaKey)); }
        if (event.key === 'Enter') { event.preventDefault();if (selectedRecords.size === 1 && selectedRecords.has(record.key)) openSelected(); }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); const index = rows.findIndex(item => item.row === row);
          rows[index+(event.key === 'ArrowDown'?1:-1)]?.row.focus();
        }
      });
      selectCell.append(check);row.append(selectCell,el('td',document ? record.number : record.code),el('td',document ? record.date : record.description),el('td',record.deletionMark?'Marked':''));
      rows.push({row,check,key:record.key});body.append(row);
    }
    catalogPanel.append(heading,actions,el('p','Confirmed records. Save refreshes this list without replacing other open drafts.'),table);
    if (!catalog.rows.length) catalogPanel.append(el('p','No records yet.'));
    paintSelection();
    workarea.className = active ? 'configuration-workarea with-form' : 'configuration-workarea';
  }
  function paint() {
    browserHost?.notify();
    applicationMessages.replaceChildren(...(client.state?.messages || []).map(message => el('p',message)));
    applicationMessages.hidden = !client.state?.messages?.length;
    exitWarning.textContent = client.state?.exitWarning || ''; exitWarning.hidden = !exitWarning.textContent;
    title.textContent = client.state?.title || 'Configuration forms';
    notice.textContent = client.terminal ? 'Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.' : status;
    const disabled = client.terminal || !client.state || client.state.kind === 'closed';
    close.disabled = disabled; entries.replaceChildren();
    for (const entry of client.state?.entries || []) {
      const node = button(entry.title || `Form ${entry.id}`,entries,() => {
        if (['catalog-object','document-object'].includes(entry.kind)) { show(null);perform('application.catalog',{entry:entry.id}); }
        else openForm(entry.id);
      });
      node.disabled = disabled || !['catalog-object','document-object'].includes(entry.kind) && client.state.sessions.length >= 8;
    }
    for (const entry of mounts.values()) if (client.terminal) entry.mount?.lock();
    drawCatalog();
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
    const generation = ['application.open','application.openRecord'].includes(request?.method) ? intents.get(request.params.request) : undefined;
    if (fresh.length && (generation === undefined || generation === navigation)) show(client.state.active || fresh.at(-1),false);
    else if (removedActive) show(client.state.active,false);
    paint();
  }
  async function perform(method,params) {
    try { return await client.request(method,params); }
    catch { status = 'Application connection failed.'; paint(); }
    finally { paint(); }
  }
  function openForm(entry, record = null) {
    const key = `${entry}:${record ?? ''}`;
    if (openings.has(key)) return openings.get(key);
    const token = `open-${instance}-${++openToken}`; intents.set(token,navigation);
    const params = {entry,request:token}; if (record !== null) params.record = record;
    const opening = perform(record === null?'application.open':'application.openRecord',params).finally(() => { openings.delete(key); intents.delete(token);paint(); });
    openings.set(key,opening); return opening;
  }
  const close = button('Close application',toolbar,async () => {
    if (pending() || mounts.size) { status = 'Close each form, including hidden tabs, before closing the application.'; paint(); return; }
    await perform('application.close',{});
  });
  workarea.append(catalogPanel,panels);shell.append(title,toolbar,applicationMessages,exitWarning,entries,tabs,notice,workarea); root.replaceChildren(shell);
  if (!exchange) exchange = browserHost.transport;
  client = new ApplicationClient(exchange,reconcile,() => { for (const entry of mounts.values()) entry.mount?.lock(); paint(); });
  environment.addEventListener('beforeunload',event => { if (pending()) { event.preventDefault(); event.returnValue = ''; } });
  browserHost?.setPending(pending, () => Boolean(client.terminal || client.state?.uncertain));
  const resume = async () => {
    if (client.terminal) throw Error('Unknown previous outcome');
    const retained = new Set(mounts.keys());
    const result = await client.request('application.hello',{protocol:APPLICATION_PROTOCOL});
    for (const [id,entry] of mounts) {
      if (retained.has(id)) await entry.mount.reconcileOwnership(); else await entry.mount.ready;
      if (entry.mount.client?.transportFailed || entry.mount.client?.outcomeUnknown) throw Error('Unknown form outcome');
    }
    return result;
  };
  paint(); const ready = browserHost ? browserHost.start(resume) : perform('application.hello',{protocol:APPLICATION_PROTOCOL});
  return {ready,client,mounts,show,pending,openForm,browserHost};
}
if (typeof window !== 'undefined' && window.document?.getElementById('configuration-app')) mountApplication(window,window.document.getElementById('configuration-app'));
