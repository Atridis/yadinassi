import {FormError, createTransport, takeSessionCapability} from '../../form/src/client.mjs';
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
  const postingPanel = el('section'); postingPanel.setAttribute('aria-label','Posting operation');
  const notice = el('p'); notice.setAttribute('role','status');
  const applicationMessages = el('section'), exitWarning = el('p');
  applicationMessages.setAttribute('aria-label','Application messages'); applicationMessages.setAttribute('aria-live','polite');
  exitWarning.setAttribute('role','status');
  const mounts = new Map(), openings = new Map(); let active = null, openToken = 0, status = '', navigation = 0, client;
  const intents = new Map();
  let pickerBusy = false, pickerTicket = null, pickerReturn = null;
  const picker = el('section'), pickerTitle = el('h2'), pickerHelp = el('p'), pickerError = el('p');
  const pickerActions = el('div'), pickerRows = el('div'), codeLabel = el('label','Exact code'), pickerCode = el('input');
  picker.className = 'panel reference-picker'; picker.setAttribute('role','dialog'); picker.setAttribute('aria-modal','true'); picker.hidden = true;
  pickerTitle.id = `reference-title-${instance}`; picker.setAttribute('aria-labelledby',pickerTitle.id);
  pickerCode.type = 'text'; pickerCode.maxLength = 64; pickerCode.autocomplete = 'off'; pickerCode.spellcheck = false;
  pickerCode.setAttribute('aria-label','Exact code'); codeLabel.append(pickerCode);
  pickerHelp.textContent = 'Choose an existing record. Enter its exact code to filter. Cancel keeps the current value.';
  pickerError.setAttribute('role','status'); pickerRows.setAttribute('aria-label','Reference matches');
  picker.append(pickerTitle,pickerHelp,codeLabel,pickerActions,pickerError,pickerRows);
  let selectedEntry = null; const selectedRecords = new Set();
  const button = (text, parent, action) => {
    const node = el('button',text); node.type = 'button'; node.dataset.formAction = 'application-navigation';
    node.addEventListener('pointerdown',event => event.preventDefault()); node.addEventListener('click',action); parent.append(node); return node;
  };
  const pending = () => Boolean(pickerBusy || client.state?.choice || client.state?.posting?.some(item => ['uncertain','committed'].includes(item.state)) || client.pending || client.terminal || client.state?.uncertain || [...mounts.values()].some(entry => entry.mount?.hasPending()));
  function show(id, userNavigation = true) {
    if (userNavigation && client.state?.choice) return;
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
    if (client.state) paint();
  }
  async function choose(action, ticket = client.state?.choice?.ticket) {
    const choice = client.state?.choice;
    if (!choice || choice.ticket !== ticket || pickerBusy || client.pending || client.terminal || client.state.uncertain) return;
    const entry = mounts.get(choice.session); if (!entry?.mount) return;
    if (action.action === 'filter' && (typeof action.code !== 'string' || [...action.code].length > 64 ||
        /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(action.code))) {
      status = 'Enter an exact code of at most 64 characters.'; paint(); return;
    }
    // Do not route cancellation through native form validation or raw code parsing.
    pickerBusy = true; paint();
    try { await entry.mount.reference({...action,ticket}); }
    finally { pickerBusy = false; paint(); }
  }
  const filter = button('Find exact code',pickerActions,() => choose({action:'filter',code:pickerCode.value}));
  const cancel = button('Cancel selection',pickerActions,() => choose({action:'cancel'}));
  pickerCode.addEventListener('keydown',event => {
    if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); choose({action:'filter',code:pickerCode.value}); }
  });
  picker.addEventListener('keydown',event => {
    if (event.key === 'Escape') { event.preventDefault(); choose({action:'cancel'}); }
    if (event.key !== 'Tab') return;
    const descendants = node => [node,...Array.from(node.children || []).flatMap(descendants)];
    const nodes = descendants(picker).filter(node => ['BUTTON','INPUT'].includes(node.tagName) && !node.disabled && !node.closest('[hidden]'));
    const index = nodes.indexOf(document.activeElement);
    if (nodes.length && (event.shiftKey && index <= 0 || !event.shiftKey && (index < 0 || index === nodes.length - 1))) {
      event.preventDefault(); nodes[event.shiftKey ? nodes.length - 1 : 0].focus();
    }
  });
  function drawPicker() {
    const choice = client.state?.choice;
    picker.hidden = !choice;
    for (const node of [toolbar,entries,tabs,workarea]) node.inert = Boolean(choice);
    for (const entry of mounts.values()) entry.mount?.repaint();
    if (!choice) {
      pickerTicket = null;
      if (pickerReturn && !client.terminal) {
        const owner = mounts.get(pickerReturn.session);
        if (!owner || owner.panel.hidden || owner.mount?.view.focusReference(pickerReturn)) pickerReturn = null;
      }
      return;
    }
    const newTicket = pickerTicket !== choice.ticket;
    if (newTicket) { pickerTicket = choice.ticket; pickerCode.value = choice.code; pickerReturn = choice; }
    pickerTitle.textContent = 'Choose ' + choice.title;
    const disabled = pickerBusy || client.pending > 0 || client.terminal || client.state.uncertain;
    filter.disabled = cancel.disabled = pickerCode.disabled = disabled;
    pickerError.textContent = client.terminal ? 'The outcome may be unknown. Selection is locked; no request will be repeated.'
      : choice.error === 'too_many_matches' ? 'Too many matches. Enter an exact code to continue.'
      : status || (choice.rows.length ? `${choice.rows.length} matching records` : 'No matching records.');
    pickerRows.replaceChildren();
    for (const row of choice.rows) {
      const entry = el('div'), description = el('span',row.code + ' · ' + row.description);
      entry.append(description);
      const select = button('Choose record',entry,() => choose({action:'apply',choice:row.choice},choice.ticket));
      select.setAttribute('aria-label','Choose ' + row.code + ' ' + row.description); select.disabled = disabled;
      pickerRows.append(entry);
    }
    if (newTicket || !disabled && picker.contains(document.activeElement) && document.activeElement.disabled) pickerCode.focus({preventScroll:true});
    if (!disabled && document.activeElement === document.body) pickerCode.focus({preventScroll:true});
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
    const posting = entry.kind === 'posting-document', document = posting || entry.kind === 'document-object';
    const heading = el('h2',entry.title), actions = el('div'); actions.className = 'catalog-commands';
    const unavailable = () => Boolean(client.state?.choice) || client.terminal || client.state?.uncertain || client.state?.kind === 'closed' || client.pending > 0;
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
    for (const title of (document ? ['Select','Number','Date','Deletion mark',...(posting ? ['Posted'] : [])] : ['Select','Code','Description','Deletion mark'])) headings.append(el('th',title));
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
      if (posting) row.append(el('td',record.posted ? 'Posted' : 'Not posted'));
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
    const disabled = client.terminal || !client.state || client.state.kind === 'closed' || Boolean(client.state.choice);
    close.disabled = disabled; entries.replaceChildren();
    for (const entry of client.state?.entries || []) {
      const node = button(entry.title || `Form ${entry.id}`,entries,() => {
        if (['catalog-object','document-object','posting-document'].includes(entry.kind)) { show(null);perform('application.catalog',{entry:entry.id}); }
        else openForm(entry.id);
      });
      node.disabled = disabled || !['catalog-object','document-object','posting-document'].includes(entry.kind) && client.state.sessions.length >= 8;
    }
    for (const entry of mounts.values()) if (client.terminal) entry.mount?.lock();
    postingPanel.replaceChildren();
    const posting = client.state?.posting?.find(item => item.session === active);
    postingPanel.hidden = !posting;
    if (posting) {
      postingPanel.append(el('p',`Posting operation: ${posting.state}${posting.error ? ' ('+posting.error+')' : ''}. ${['uncertain','committed'].includes(posting.state) ? 'Posted state awaiting authoritative refresh' : posting.posted ? 'Posted' : 'Not posted'}.`));
      if (['uncertain','committed'].includes(posting.state)) {
        const recover = button('Resolve saved operation',postingPanel,async () => {
          if (client.pending || client.terminal || client.state.uncertain) return;
          const owner = posting.session, receipt = posting.receipt;
          const result = await perform('application.recoverPosting',{session:owner,receipt});
          if (result && mounts.has(owner)) await mounts.get(owner).mount.refresh();
        });
        recover.disabled = !posting.receipt || client.pending > 0 || client.terminal || client.state.uncertain;
        postingPanel.append(el('p','Recovery uses this host’s saved receipt. It never repeats posting handlers. Keep this application open.'));
      }
    }
    drawCatalog(); drawPicker();
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
        referenceActive: () => Boolean(client.state?.choice),
        onReference: Object.hasOwn(client.state,'choice') ? ({revision,action}) => client.reference(id,revision,action) : null,
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
    if (client.state?.choice) return Promise.resolve();
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
  workarea.append(catalogPanel,panels);shell.append(title,toolbar,applicationMessages,exitWarning,entries,tabs,notice,postingPanel,workarea,picker); root.replaceChildren(shell);
  if (!exchange) exchange = browserHost.transport;
  client = new ApplicationClient(exchange,reconcile,() => { for (const entry of mounts.values()) entry.mount?.lock(); paint(); });
  environment.addEventListener('beforeunload',event => { if (pending()) { event.preventDefault(); event.returnValue = ''; } });
  browserHost?.setPending(pending, () => Boolean(client.terminal || client.state?.uncertain));
  browserHost?.setInspectionAllowed(() => Boolean((client.terminal || client.state?.uncertain) && !client.pending &&
    !pickerBusy && !client.state?.choice && mounts.size &&
    [...mounts.values()].every(entry => entry.mount?.client?.locked && !entry.mount.client.busy) &&
    [...mounts.values()].some(entry => entry.mount?.client?.snapshot?.items.some(item => item.kind === 'group'))));
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
