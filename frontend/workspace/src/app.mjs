import {createTransport, takeSessionCapability, scalarText} from '../../form/src/client.mjs';
import {mountForm} from '../../form/src/app.mjs';
import {createBrowserHost, documentInstance} from '../../form/src/attachment.mjs';
import {WORKSPACE_PROTOCOL, WorkspaceClient} from './client.mjs';

export function mountWorkspace(environment, root, exchange = null) {
  const browserHost = exchange ? null : createBrowserHost(environment, root);
  root = browserHost?.content || root;
  const instance = browserHost?.instance || documentInstance(environment);
  const document = environment.document;
  const el = (tag, text = '') => { const node = document.createElement(tag); node.textContent = text; return node; };
  const shell = el('main'), title = el('h1','Orders workspace'), toolbar = el('nav'), tabs = el('nav'), panels = el('div');
  shell.className = 'orders-workspace'; tabs.setAttribute('aria-label','Open forms');
  const notice = el('p'); notice.setAttribute('role','status');
  const list = el('section'), label = el('label','Find exact code '), code = el('input'); code.maxLength = 8; code.dataset.formAction = 'workspace-navigation'; label.append(code);
  const rows = el('div'), truncation = el('p');
  const button = (text, parent, action) => {
    const node = el('button',text); node.type = 'button'; node.dataset.formAction = 'workspace-navigation';
    // Navigation never blurs an input into a form event. Keyboard targets also carry data-form-action.
    node.addEventListener('pointerdown', event => event.preventDefault()); node.addEventListener('click', action); parent.append(node); return node;
  };
  const mounts = new Map(), openings = new Map(); let active = null, navigation = 0, openToken = 0, status = '';
  let client;
  function show(id) {
    navigation++; active = id;
    for (const [key, entry] of mounts) {
      if (!entry.panel.hidden) {
        const focus = document.activeElement;
        if (entry.panel.contains(focus)) entry.focus = {node:focus,start:focus.selectionStart,end:focus.selectionEnd};
      }
      entry.panel.hidden = key !== id; entry.tab.setAttribute('aria-selected',String(key === id));
    }
    list.hidden = id !== null;
    const saved = mounts.get(id)?.focus;
    if (saved?.node && !saved.node.disabled) { saved.node.focus({preventScroll:true}); if (typeof saved.start === 'number') saved.node.setSelectionRange(saved.start,saved.end); }
    paint();
  }
  const pending = () => Boolean(client.pending || client.terminal || client.state?.uncertain || [...mounts.values()].some(entry => entry.mount.hasPending()));
  function paint() {
    browserHost?.notify();
    notice.textContent = client.terminal ? 'Connection lost or invalid response. All forms are locked. Copy pending edits before leaving. Restart the workspace; requests will not be replayed.' : status;
    const disabled = client.terminal || !client.state || client.state.kind === 'closed';
    refresh.disabled = disabled; create.disabled = disabled || client.state.sessions.length >= 4; close.disabled = disabled; code.disabled = disabled;
    const current = mounts.get(active)?.mount.client;
    discard.hidden = !client.state?.sessions.some(session => session.id === active && session.kind === 'intake');
    discard.disabled = disabled || Boolean(client.pending || client.state?.uncertain || current?.busy || current?.outcomeUnknown || current?.snapshot?.uncertain);
    rows.replaceChildren();
    for (const order of client.state?.orders || []) {
      const row = el('p'); row.append(el('span', `${order.code} · ${order.description} · ${scalarText(order.total)} `));
      const open = button('Open order',row, () => openForm(order.id)); open.disabled = disabled || client.state.sessions.length >= 4; rows.append(row);
    }
    truncation.textContent = client.state?.truncated ? 'More than 32 orders exist. Enter an exact code to narrow the results.' : '';
  }
  async function perform(method, params) {
    try { const result = await client.request(method,params); status = result.error ? `Workspace: ${result.error}` : ''; return result; }
    catch { status = 'Workspace connection failed.'; }
    finally { paint(); }
  }
  function reconcile() {
    for (const [id,entry] of mounts) if (!client.state.sessions.some(session => session.id === id)) {
      entry.panel.remove(); entry.tab.remove(); mounts.delete(id); if (active === id) show(null);
    }
    paint();
  }
  function openForm(row) {
    const key = `${client.state.revision}:${row === null ? 'new' : row}`;
    if (openings.has(key)) return openings.get(key);
    const opening = performOpen(row).finally(() => openings.delete(key));
    openings.set(key, opening);
    return opening;
  }
  async function performOpen(row) {
    const generation = ++navigation;
    const title = row === null ? 'New order' : `Order ${client.state.orders.find(order => order.id === row)?.code || row}`;
    const result = await perform('workspace.open',{revision:client.state.revision,row,request:`open-${instance}-${++openToken}`});
    if (!result || result.error || client.terminal) return;
    const id = result.session;
    await ensureSession(id, title);
    if (generation === navigation && mounts.has(id)) show(id);
    paint();
  }
  async function ensureSession(id, title) {
    if (!mounts.has(id)) {
      const panel = el('section'); panel.hidden = true; panels.append(panel);
      const tab = button(title,tabs, () => show(id));
      const entry = {panel,tab,mount:null,focus:null};
      entry.mount = mountForm(environment,panel, {transport: request => client.form(id,request),isActive: () => active === id,onChange: () => {
        if (entry.mount?.client?.transportFailed) client.lock();
        reconcile();
      }});
      mounts.set(id,entry);
      await entry.mount.ready;
    }
  }
  button('Orders',toolbar, () => show(null));
  const create = button('New order',toolbar, () => openForm(null));
  const close = button('Close workspace',toolbar, async () => {
    if (pending()) { status = 'Save or discard every form, including hidden tabs, and wait for pending requests before closing.'; paint(); return; }
    if (mounts.size) { status = 'Close each form tab before closing the workspace.'; paint(); return; }
    await perform('workspace.close',{});
  });
  async function discardActive() {
    if (discard.disabled || discard.hidden) return;
    const result = await perform('workspace.discard',{session:active});
    if (result && result.error === null) reconcile();
  }
  const discard = button('Discard new order',toolbar, discardActive);
  list.append(label);
  const refresh = button('Find / Refresh orders',list, () => perform('workspace.list',{code:code.value}));
  list.append(truncation,rows); shell.append(title,toolbar,tabs,notice,list,panels); root.replaceChildren(shell);
  if (!exchange) exchange = browserHost.transport;
  client = new WorkspaceClient(exchange, () => paint(), () => { for (const entry of mounts.values()) entry.mount.lock(); paint(); });
  environment.addEventListener('beforeunload',event => { if (pending()) { event.preventDefault(); event.returnValue = ''; } });
  browserHost?.setPending(pending, () => Boolean(client.terminal || client.state?.uncertain));
  const resume = async () => {
    if (client.terminal) throw Error('Unknown previous outcome');
    const retained = new Set(mounts.keys());
    const result = await client.request('workspace.hello',{protocol:WORKSPACE_PROTOCOL});
    reconcile();
    for (const session of client.state.sessions) {
      await ensureSession(session.id, session.kind === 'intake' ? 'New order' : 'Retained order');
      if (retained.has(session.id)) await mounts.get(session.id).mount.reconcileOwnership();
    }
    if (active === null && mounts.size) show(mounts.keys().next().value);
    return result;
  };
  paint(); const ready = browserHost ? browserHost.start(resume) : resume();
  return {ready,client,mounts,show,pending,openForm,discardActive,browserHost};
}
if (typeof window !== 'undefined' && window.document?.getElementById('orders-app')) mountWorkspace(window,window.document.getElementById('orders-app'));
