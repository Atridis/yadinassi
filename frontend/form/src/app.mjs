import {FormClient, FormError, createTransport, takeSessionCapability} from './client.mjs';
import {createFormView} from './view.mjs';

/** Serialize UI intents before the first await, including blur followed by a command. */
export function mountForm(environment, root) {
  let client = null, token = null, queuedToken = null, busy = false, error = '';
  const view = createFormView(environment.document, root, {
    change: name => run('change', name), action: (event, name) => run(event, name), refresh: () => refresh(),
  });
  const paint = () => view.render({snapshot: client?.snapshot || null, busy, error, connected: Boolean(token),
    locked: client?.locked ?? true, outcomeUnknown: client?.outcomeUnknown || false,
    transportFailed: client?.transportFailed || false, exhausted: client?.exhausted || false});
  const showError = caught => { error = caught instanceof FormError ? caught.message : new FormError('transport').message; };
  const finish = () => {
    busy = false; paint();
    if (queuedToken) { const next = queuedToken; queuedToken = null; connect(next); }
  };
  async function connect(incoming) {
    if (busy) { queuedToken = incoming; return; }
    busy = true; error = '';
    if (incoming !== token || !client) {
      token = incoming; view.clearDrafts();
      client = new FormClient(createTransport(environment.fetch.bind(environment), token));
    }
    paint();
    try { await client.hello(); view.clearDrafts(); }
    catch (caught) { showError(caught); }
    finally { finish(); }
  }
  async function sendChange(change) {
    const before = client.snapshot;
    try { await client.event('change', change); }
    finally {
      // An authoritative error snapshot can include effects completed before failure.
      if (client.snapshot !== before && !client.transportFailed) view.accept(change.control);
      paint();
    }
  }
  async function run(event, name) {
    if (busy || !client || client.locked) return;
    // Validate the whole local draft before applying the first field, then serialize.
    let changes;
    try { changes = view.changes(event === 'change' ? name : undefined); }
    catch (caught) { showError(caught); paint(); return; }
    if (event === 'change' && !changes.length) return;
    busy = true; error = ''; paint();
    try {
      for (const change of changes) await sendChange(change);
      if (event === 'command') await client.event('command', {control: name});
      else if (event === 'close') await client.event('close');
    } catch (caught) { showError(caught); }
    finally { finish(); }
  }
  async function refresh() {
    if (busy || !client) return;
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
  environment.addEventListener('hashchange', reattach);
  environment.addEventListener('beforeunload', event => {
    if (busy || view.hasDrafts()) { event.preventDefault(); event.returnValue = ''; }
  });
  paint(); const ready = reattach();
  return {ready, refresh, run, reattach, get client() { return client; }, view};
}

if (typeof window !== 'undefined' && window.document?.getElementById('app')) {
  mountForm(window, window.document.getElementById('app'));
}
