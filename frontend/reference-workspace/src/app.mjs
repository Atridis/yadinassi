import {createTransport, takeSessionCapability, scalarText, FormError} from '../../form/src/client.mjs';
import {mountForm} from '../../form/src/app.mjs';
import {REFERENCE_PROTOCOL, ReferenceClient} from './client.mjs';

let workspaceSerial = 0n;
export function mountReferenceWorkspace(environment, root, exchange = null) {
  const document = environment.document, prefix = 'reference-workspace-' + ++workspaceSerial + '-';
  const el = (tag, text = '') => { const node = document.createElement(tag); node.textContent = text; return node; };
  const shell = el('div'), background = el('div'), title = el('h1','Reference Orders');
  shell.className = 'reference-workspace';
  const introduction = el('p','Create or open an order. Choose customers and products in a separate form, then save the order.');
  const toolbar = el('nav'); toolbar.setAttribute('aria-label','Order navigation');
  const notice = el('p'); notice.setAttribute('role','status'); notice.setAttribute('aria-live','polite');
  const list = el('section'), listTitle = el('h2','Orders'), label = el('label','Find exact code '), code = el('input');
  code.id = prefix + 'code'; code.maxLength = 8; code.autocomplete = 'off'; label.htmlFor = code.id; label.append(code);
  const rows = el('div'), truncation = el('p'), panels = el('div'), dialogs = el('div');
  const button = (caption, parent, action) => {
    const node = el('button',caption); node.type = 'button'; node.dataset.formAction = 'workspace-navigation';
    node.addEventListener('pointerdown',event => event.preventDefault());
    node.addEventListener('click',() => { if (!node.disabled) return action(); }); parent.append(node); return node;
  };
  const mounts = new Map(), recovering = new Set();
  let client, opening = null, openToken = 0, status = '', synchronization = Promise.resolve();
  const child = () => client?.state?.sessions.find(session => session.kind === 'choice');
  const owner = () => client?.state?.sessions.find(session => session.kind === 'order');
  const blocked = entry => client.terminal || entry.kind === 'order' && Boolean(child() || recovering.has(entry.id));
  const pending = () => Boolean(client.pending || client.terminal || client.state?.uncertain || opening || child() || recovering.size ||
    [...mounts.values()].some(entry => entry.mount?.hasPending()));
  const descendants = node => Array.from(node.children).flatMap(value => [value,...descendants(value)]);
  const focusable = entry => descendants(entry.panel).filter(node =>
    !node.disabled && !node.hidden && !node.closest('[hidden]') &&
    (['BUTTON','INPUT','SELECT','TEXTAREA'].includes(node.tagName) || node.tabIndex === 0));
  const focusEntry = entry => {
    if (!entry || blocked(entry)) return;
    const target = entry.lastFocus && entry.panel.contains(entry.lastFocus) && !entry.lastFocus.disabled ? entry.lastFocus : focusable(entry)[0];
    (target || entry.panel).focus({preventScroll:true});
  };
  function paint() {
    const currentChild = child(), currentOwner = owner();
    const disabled = client.terminal || !client.state || client.state.kind === 'closed';
    const managing = disabled || Boolean(client.pending || opening || currentOwner || recovering.size);
    create.disabled = managing; refresh.disabled = managing; code.disabled = managing;
    close.disabled = disabled || Boolean(client.pending || opening || currentChild || recovering.size);
    list.hidden = Boolean(currentOwner);
    background.inert = Boolean(currentChild || recovering.size);
    background.setAttribute('aria-hidden',String(Boolean(currentChild || recovering.size)));
    notice.textContent = client.terminal
      ? 'Connection lost or invalid response. All forms are locked. Copy pending edits before leaving. Reopen the launcher to start a new workspace; requests will not be replayed.'
      : recovering.size ? 'Applying the choice to the order…' : status;
    rows.replaceChildren();
    for (const order of client.state?.orders || []) {
      const row = el('p'); row.append(el('span',`${order.code} · ${order.description} · ${scalarText(order.total)} `));
      const open = button('Open order',row,() => openForm(order.id)); open.disabled = managing;
      open.setAttribute('aria-label',`Open order ${order.code}: ${order.description}`); rows.append(row);
    }
    if (client.state && !client.state.orders.length) rows.append(el('p','No matching orders.'));
    truncation.textContent = client.state?.truncated ? 'More than 32 orders match. Enter an exact code to narrow the results.' : '';
    for (const entry of mounts.values()) {
      const frozen = blocked(entry);
      entry.fieldset.disabled = frozen; entry.panel.inert = frozen;
      entry.panel.setAttribute('aria-disabled',String(frozen));
      if (entry.kind === 'order') entry.panel.setAttribute('aria-hidden',String(Boolean(currentChild || recovering.size)));
    }
    if (disabled && client.state?.kind === 'closed') notice.textContent = 'Workspace closed. You can close this page.';
  }
  function observe(result) {
    for (const entry of mounts.values()) if (entry.kind === 'choice' && !result.state.sessions.some(session => session.id === entry.id)) recovering.add(entry.owner);
    paint();
  }
  function schedule() {
    synchronization = synchronization.then(reconcile).catch(() => client.lock());
    return synchronization;
  }
  async function settled() {
    for (;;) { const current = synchronization; await current; if (current === synchronization) return; }
  }
  function mountSession(session) {
    const panel = el('section'), fieldset = el('fieldset'), content = el('div');
    const entry = {...session,panel,fieldset,mount:null,lastFocus:null};
    fieldset.className = 'form-boundary'; fieldset.append(content); panel.tabIndex = -1;
    if (session.kind === 'choice') {
      panel.className = 'choice-dialog'; panel.setAttribute('role','dialog'); panel.setAttribute('aria-modal','true');
      const heading = el('h2','Choose a reference'); heading.id = prefix + 'choice-title-' + session.id;
      panel.setAttribute('aria-labelledby',heading.id); panel.append(heading,fieldset); dialogs.append(panel);
      panel.addEventListener('keydown',event => {
        if (event.key === 'Escape') { event.preventDefault(); if (!blocked(entry)) entry.mount.run('close'); }
        if (event.key === 'Tab') {
          const targets = focusable(entry), index = targets.indexOf(document.activeElement);
          if (!targets.length) { event.preventDefault(); panel.focus(); }
          else if (event.shiftKey && index <= 0 || !event.shiftKey && (index < 0 || index === targets.length-1)) {
            event.preventDefault(); targets[event.shiftKey ? targets.length-1 : 0].focus();
          }
        }
      });
    } else { panel.append(fieldset); panels.append(panel); }
    panel.addEventListener('focusin',event => { if (event.target !== panel) entry.lastFocus = event.target; });
    mounts.set(session.id,entry);
    entry.mount = mountForm(environment,content,{
      transport: request => {
        // DOM inert + disabled fieldset prevents ordinary input. A programmatic
        // bypass must also fail closed before any frozen-owner mutation is sent.
        if (entry.kind === 'order' && request.method === 'form.event' && blocked(entry)) {
          client.lock(); return Promise.reject(new FormError('transport'));
        }
        return client.form(session.id,request);
      },
      isActive: () => !blocked(entry),
      onChange: () => {
        if (entry.mount?.client?.transportFailed) client.lock();
        paint(); schedule();
      },
    });
    paint(); return entry;
  }
  async function reconcile() {
    if (client.terminal) return;
    for (const [id,entry] of mounts) if (!client.state.sessions.some(session => session.id === id)) {
      entry.panel.remove(); mounts.delete(id);
    }
    const currentChild = child();
    if (currentChild && !mounts.has(currentChild.id)) {
      const entry = mountSession(currentChild); await entry.mount.ready;
      if (!client.terminal && mounts.has(entry.id)) focusEntry(entry);
    }
    for (const id of [...recovering]) {
      const entry = mounts.get(id);
      if (!entry || child()) { client.lock(); return; }
      await entry.mount.refresh();
      if (client.terminal || entry.mount.client.transportFailed || entry.mount.client.outcomeUnknown || entry.mount.client.snapshot?.kind !== 'form') {
        client.lock(); return;
      }
      recovering.delete(id); paint(); focusEntry(entry);
    }
    paint();
  }
  async function perform(method, params) {
    try { const result = await client.request(method,params); status = result.error ? `Workspace: ${result.error}` : ''; return result; }
    catch { status = 'Workspace connection failed.'; }
    finally { paint(); }
  }
  function openForm(row) {
    if (opening) return opening;
    if (!client.state || client.terminal || client.state.kind === 'closed' || owner() || client.pending) return Promise.resolve();
    opening = (async () => {
      const result = await perform('workspace.open',{revision:client.state.revision,row,request:`open-${++openToken}`});
      if (!result || result.error || client.terminal) return;
      const descriptor = client.state.sessions.find(session => session.id === result.session);
      const entry = mounts.get(descriptor.id) || mountSession(descriptor);
      await entry.mount.ready; await schedule(); focusEntry(entry);
    })().finally(() => { opening = null; paint(); });
    paint(); return opening;
  }
  const create = button('New order',toolbar,() => openForm(null));
  const close = button('Close workspace',toolbar,async () => {
    if (pending()) { status = 'Save or discard pending edits and wait for all requests before closing.'; paint(); return; }
    if (mounts.size) { status = 'Close the order form before closing the workspace.'; paint(); return; }
    await perform('workspace.close',{});
  });
  list.append(listTitle,label);
  const refresh = button('Find / Refresh orders',list,() => perform('workspace.list',{code:code.value}));
  list.append(truncation,rows); background.append(title,introduction,toolbar,list,panels);
  shell.append(notice,background,dialogs); root.replaceChildren(shell);
  if (!exchange) {
    try { exchange = createTransport(environment.fetch.bind(environment),takeSessionCapability(environment.location,environment.history)); }
    catch { exchange = async () => { throw Error('Missing session'); }; }
  }
  client = new ReferenceClient(exchange,observe,() => { for (const entry of mounts.values()) entry.mount?.lock(); paint(); });
  environment.addEventListener('beforeunload',event => { if (pending()) { event.preventDefault(); event.returnValue = ''; } });
  paint(); const ready = perform('workspace.hello',{protocol:REFERENCE_PROTOCOL});
  return {ready,client,mounts,pending,openForm,settled};
}
if (typeof window !== 'undefined' && window.document?.getElementById('reference-orders-app')) mountReferenceWorkspace(window,window.document.getElementById('reference-orders-app'));
