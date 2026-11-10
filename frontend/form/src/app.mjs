import {FormClient, FormError, createTransport, takeSessionCapability} from './client.mjs';
import {createFormView} from './view.mjs';

/** Serialize UI intents before the first await, including blur followed by a command. */
export function mountForm(environment, root, options = {}) {
  let client = null, token = null, queuedToken = null, busy = false, error = '';
  const view = createFormView(environment.document, root, {
    change: name => run('change', name), select: (name, row) => run('select', name, row), action: (event, name) => run(event, name), refresh: () => refresh(),
  });
  const paint = () => view.render({snapshot: client?.snapshot || null, busy, error, connected: Boolean(token),
    locked: client?.locked ?? true, outcomeUnknown: client?.outcomeUnknown || false,
    transportFailed: client?.transportFailed || false, exhausted: client?.exhausted || false});
  const showError = caught => { error = caught instanceof FormError ? caught.message : new FormError('transport').message; };
  const finish = () => {
    busy = false; paint(); options.onChange?.();
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
  async function run(event, name, row) {
    if (['change', 'toggle'].includes(event) && options.isActive && !options.isActive()) return;
    if (busy || !client || client.locked) return;
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
      changes = view.changes(event === 'change' ? name : undefined);
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
      if (event === 'command') await client.event('command', {control: name});
      else if (event === 'select') await client.event('select', {control: name, row});
      else if (event === 'close') await client.event('close');
    } catch (caught) { showError(caught); }
    finally { finish(); }
  }
  async function refresh() {
    if (busy || !client || options.transport && client.transportFailed) return;
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
  if (!options.transport) environment.addEventListener('hashchange', reattach);
  if (!options.transport) environment.addEventListener('beforeunload', event => {
    if (hasPending()) { event.preventDefault(); event.returnValue = ''; }
  });
  const hasPending = () => busy || Boolean(client?.snapshot?.dirty || client?.snapshot?.uncertain || client?.outcomeUnknown || client?.transportFailed || view.hasDrafts());
  const lock = () => { if (client) client.transportFailed = true; error = new FormError('transport').message; paint(); };
  paint(); const ready = options.transport ? connect('embedded') : reattach();
  return {ready, refresh, run, reattach, hasPending, lock, get client() { return client; }, view};
}

if (typeof window !== 'undefined' && window.document?.getElementById('app')) {
  mountForm(window, window.document.getElementById('app'));
}
