import {FormClient, FormError, tableCell, scalarEqual, createTransport, takeSessionCapability} from './client.mjs';
import {createFormView} from './view.mjs';
import {createBrowserHost, AttachmentRefusal} from './attachment.mjs';

/** Serialize UI intents before the first await, including blur followed by a command. */
export function mountForm(environment, root, options = {}) {
  const browserHost = options.transport ? null : createBrowserHost(environment, root);
  root = browserHost?.content || root;
  let client = null, token = browserHost?.launcher || null, queuedToken = null, busy = false, error = '';
  const view = createFormView(environment.document, root, {
    reference: options.onReference ? action => run('reference', action) : null,
    change: name => run('change', name), select: (name, row) => run('select', name, row), action: (event, name) => run(event, name), refresh: () => refresh(),
  });
  const paint = () => view.render({paused: Boolean(options.referenceActive?.()), snapshot: client?.snapshot || null, busy, error, connected: Boolean(token),
    locked: client?.locked ?? true, outcomeUnknown: client?.outcomeUnknown || false,
    transportFailed: client?.transportFailed || false, exhausted: client?.exhausted || false});
  const showError = caught => { error = caught instanceof FormError || caught?.preDispatch === true ? caught.message : new FormError('transport').message; };
  const finish = () => {
    busy = false; paint(); options.onChange?.(); browserHost?.notify();
    if (queuedToken) { const next = queuedToken; queuedToken = null; connect(next); }
  };
  async function connect(incoming) {
    if (busy) { queuedToken = incoming; return; }
    busy = true; error = '';
    if (incoming !== token || !client) {
      token = incoming; view.clearDrafts();
      client = new FormClient(options.transport || createTransport(environment.fetch.bind(environment), token));
    }
    paint();
    try { await client.hello(); view.clearDrafts(); }
    catch (caught) { showError(caught); }
    finally { finish(); }
  }
  async function sendChange(change) {
    const before = client.snapshot;
    try { await client.event(Object.hasOwn(change, 'row') ? 'cell' : 'change', change); }
    finally {
      // An authoritative error snapshot can include effects completed before failure.
      if (client.snapshot !== before && !client.transportFailed) view.accept(change);
      paint();
    }
  }
  function referenceTarget(action) {
    const item = client.snapshot.items.find(item => item.name === action.control);
    const field = action.row === null && action.column === null ? item : tableCell(item, action.row, action.column);
    if (!field || field.kind !== 'field' || !field.visible || !field.enabled || field.readOnly || field.view === 'label' ||
        field.value.type !== 'FormCatalogRef') throw new FormError('unavailable');
    return {value: field.value, controlId: item.controlId, tableId: item.tableId};
  }
  async function run(event, name, row) {
    if (['change', 'toggle'].includes(event) && options.isActive && !options.isActive()) return;
    if (busy || !client || client.locked || options.referenceActive?.() && event !== 'reference') return;
    const reference = event === 'reference';
    if (reference && !options.onReference) return;
    const referenceStart = reference && ['begin', 'clear'].includes(name?.action);
    let target;
    if (referenceStart) {
      try { target = referenceTarget(name); } catch (caught) { showError(caught); paint(); return; }
    }
    // Only an explicit host policy may discard unvalidated local drafts. Keep
    // them until an authoritative response, including a recoverable handler error.
    if (event === 'command' && client.snapshot.discardCommands?.includes(name)) {
      busy = true; error = ''; paint();
      const before = client.snapshot;
      try { await client.event('command', {control: name}); }
      catch (caught) { showError(caught); }
      finally {
        if (client.snapshot !== before && !client.transportFailed && !client.outcomeUnknown && !client.snapshot.uncertain) view.clearDrafts();
        finish();
      }
      return;
    }
    // Validate the whole local draft before applying the first field, then serialize.
    let changes;
    try {
      // A picker cancellation must not validate unrelated raw filter text or drafts.
      changes = reference && !referenceStart ? [] : view.changes(event === 'change' ? name : undefined);
      if (event === 'toggle') {
        // Validate every draft first, then apply the newly activated checkbox
        // last, even when declaration order puts it before the field just left.
        const target = change => typeof name === 'string'
          ? !Object.hasOwn(change, 'row') && change.control === name
          : change.control === name.control && change.row === name.row && change.column === name.column;
        changes = [...changes.filter(change => !target(change)), ...changes.filter(target)];
      }
    }
    catch (caught) { showError(caught); paint(); return; }
    if (['change', 'toggle'].includes(event) && !changes.length) return;
    busy = true; error = ''; paint();
    try {
      for (const change of changes) {
        // An earlier handler may delete, retype or supersede a later draft. Do not
        // retarget it or run a command that silently lost part of the user's edit.
        const locator = Object.hasOwn(change, 'row') ? change : change.control;
        const pending = view.changes(locator);
        if (!pending.some(value => JSON.stringify(value) === JSON.stringify(change))) throw new FormError('draft_changed');
        await sendChange(change);
      }
      if (reference) {
        if (referenceStart) {
          const latest = referenceTarget(name);
          if (latest.controlId !== target.controlId || latest.tableId !== target.tableId || !scalarEqual(latest.value, target.value))
            throw new FormError('draft_changed');
        }
        let nested;
        try { nested = await options.onReference({revision: client.snapshot.revision, action: name}); }
        catch (caught) { if (caught?.preDispatch !== true) client.transportFailed = true; throw caught; }
        client.adopt(nested);
      } else if (event === 'command') await client.event('command', {control: name});
      else if (event === 'select') await client.event('select', {control: name, row});
      else if (event === 'close') await client.event('close');
    } catch (caught) { showError(caught); }
    finally { finish(); }
  }
  async function reconcileOwnership() {
    if (busy) throw new AttachmentRefusal('busy');
    if (!client || client.transportFailed || client.outcomeUnknown) throw new FormError('transport');
    busy = true; view.beginOwnershipReconcile(); paint();
    try { return await (client.snapshot ? client.resync() : client.hello()); }
    finally { finish(); view.endOwnershipReconcile(); }
  }
  async function refresh() {
    if (busy || !client || options.referenceActive?.() || options.transport && client.transportFailed) return;
    busy = true; error = ''; paint();
    try { await client.resync(); view.clearDrafts(); }
    catch (caught) { showError(caught); }
    finally { finish(); }
  }
  const reattach = () => {
    try {
      const incoming = takeSessionCapability(environment.location, environment.history);
      if (incoming) return connect(incoming);
      if (!token) { error = new FormError('session_missing').message; paint(); }
    } catch { error = new FormError('session_missing').message; paint(); }
  };
  if (!options.transport && !browserHost?.enabled) environment.addEventListener('hashchange', reattach);
  if (!options.transport) environment.addEventListener('beforeunload', event => {
    if (hasPending()) { event.preventDefault(); event.returnValue = ''; }
  });
  const hasPending = () => busy || Boolean(client?.snapshot?.dirty || client?.snapshot?.uncertain || client?.outcomeUnknown || client?.transportFailed || view.hasDrafts());
  const lock = () => { if (client) client.transportFailed = true; error = new FormError('transport').message; paint(); };
  paint();
  if (browserHost?.enabled) {
    client = new FormClient(browserHost.transport); token = 'attached';
    browserHost.setPending(hasPending, () => Boolean(client.transportFailed || client.outcomeUnknown || client.snapshot?.uncertain));
  }
  const ready = options.transport ? connect('embedded') : browserHost.enabled ? browserHost.start(reconcileOwnership) : token ? connect(token) : reattach();
  return {ready, refresh, reconcileOwnership, run, repaint: paint, reference: action => run('reference', action), reattach, hasPending, lock, browserHost, get client() { return client; }, view};
}

if (typeof window !== 'undefined' && window.document?.getElementById('app')) {
  mountForm(window, window.document.getElementById('app'));
}
