import {createTransport, readBoundedJSON} from './client.mjs';

export const BROWSER_PROTOCOL = 'yadinassi-browser-attachment/1';
export const RESUME_KEY = 'yadinassi.browser.resume/1';
const tokenText = value => typeof value === 'string' && /^[A-Za-z0-9_-]{32,128}$/.test(value);
const objectKeys = (value, names) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).length === names.length && names.every(name => Object.hasOwn(value, name));
const safeCounter = value => Number.isSafeInteger(value) && value >= 0;
const refusalCodes = ['not_writer', 'stale_generation', 'busy', 'outcome_unknown', 'unauthorized', 'closed', 'capacity', 'invalid_message'];
const messages = {
  not_writer: 'This application is controlled in another tab. Take control here to continue.',
  stale_generation: 'Control changed. Check the current tab ownership before continuing.',
  busy: 'The host is completing another request. Check ownership again after it finishes.',
  outcome_unknown: 'A previous request has an unknown outcome. Editing remains locked; no action will be repeated.',
  unauthorized: 'This connection link has expired. Reopen the complete URL printed by the launcher.',
  closed: 'This application session is closed. Start the launcher again to open it.',
  capacity: 'Too many browser attachments. Restart the launcher after resolving any pending edits.',
  invalid_message: 'The browser connection was rejected. Reopen the complete launcher URL.',
  connection: 'Cannot verify the connection. Pending input stays in this page; check the connection before continuing.',
};
export class AttachmentRefusal extends Error {
  constructor(code) { super(messages[code] || messages.connection); this.name = 'AttachmentRefusal'; this.code = code; this.preDispatch = true; }
}
export function documentInstance(environment = globalThis) {
  const bytes = new Uint8Array(16);
  (environment.crypto || globalThis.crypto).getRandomValues(bytes);
  return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
}
export function readBrowserLaunch(environment) {
  const params = new URLSearchParams(environment.location.hash.slice(1));
  const values = params.getAll('session');
  const launcher = values.length === 1 && tokenText(values[0]) ? values[0] : null;
  const requested = params.getAll('attachment').length === 1 && params.get('attachment') === '1';
  if (environment.location.hash) environment.history.replaceState(null, '', environment.location.pathname);
  let resume = null;
  // A full legacy launch URL explicitly selects its legacy protocol, even if
  // this origin previously had an attachment. Never persist the launcher key.
  if (!launcher || requested) {
    try { const stored = environment.sessionStorage.getItem(RESUME_KEY); if (tokenText(stored)) resume = stored; } catch { /* Storage can be unavailable. */ }
  }
  return {enabled: requested || !launcher && Boolean(resume), launcher, resume};
}
function validateStatus(value, issued, previous) {
  const keys = ['protocol', 'attachment', 'role', 'generation', 'leaseSeconds', 'graceSeconds', 'recovery', 'closed'];
  if (issued) keys.push('credential', 'resume');
  if (!objectKeys(value, keys) || value.protocol !== BROWSER_PROTOCOL ||
      typeof value.attachment !== 'string' || !/^attachment-[1-9][0-9]{0,5}$/.test(value.attachment) ||
      !['writer', 'observer'].includes(value.role) || !safeCounter(value.generation) ||
      !Number.isInteger(value.leaseSeconds) || value.leaseSeconds < 10 || value.leaseSeconds > 3600 ||
      !Number.isInteger(value.graceSeconds) || value.graceSeconds < 1 || value.graceSeconds > 3600 ||
      typeof value.recovery !== 'boolean' || typeof value.closed !== 'boolean' ||
      issued && (!tokenText(value.credential) || !tokenText(value.resume)) ||
      previous && (value.attachment !== previous.attachment || value.generation < previous.generation)) throw Error('Invalid attachment response');
  return value;
}
function readOnlyRPC(request) {
  if (['form.hello', 'form.snapshot', 'editor.hello', 'editor.snapshot', 'workspace.hello', 'application.hello'].includes(request.method)) return true;
  return ['workspace.form', 'application.form'].includes(request.method) &&
    ['form.hello', 'form.snapshot'].includes(request.params?.request?.method);
}
async function attachmentJSON(response) {
  if (response.ok) return readBoundedJSON(response);
  if ([403, 409].includes(response.status)) {
    // Decode only the closed, fixed pre-dispatch refusal envelope. A generic
    // HTTP failure remains an unknown business outcome, never a retry signal.
    const value = await readBoundedJSON({ok: true, body: response.body, headers: response.headers});
    if (objectKeys(value, ['protocol', 'error']) && value.protocol === BROWSER_PROTOCOL && refusalCodes.includes(value.error))
      throw new AttachmentRefusal(value.error);
  }
  throw Error('Connection unavailable');
}
export class BrowserAttachment {
  constructor(environment, launch, changed = () => {}) {
    this.environment = environment; this.instance = documentInstance(environment); this.bootstrap = launch.launcher || launch.resume;
    this.changed = changed; this.info = null; this.credential = null; this.paused = true; this.suspended = false;
    this.busy = false; this.rpcActive = 0; this.businessUnknown = false; this.message = ''; this.timer = null;
    this.pending = () => false; this.uncertain = () => false; this.reconcile = async () => {};
    this.reconciling = false; this.commandTail = Promise.resolve(); this.hiddenEpoch = 0; this.heartbeatPending = false;
    this.hide = () => this.detach();
    this.show = () => { this.suspended = false; this.paused = true; this.changed(); this.check().catch(() => {}); };
    environment.addEventListener('pagehide', this.hide); environment.addEventListener('pageshow', this.show);
  }
  get writable() { return Boolean(this.info?.role === 'writer' && !this.info.closed && !this.paused && !this.suspended && !this.businessUnknown && !this.uncertain()); }
  get pendingState() { return Boolean(this.pending() || this.rpcActive || this.businessUnknown || this.uncertain()); }
  async post(path, body, key, headers = {}, keepalive = false) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 35000);
    try {
      return await attachmentJSON(await this.environment.fetch(path, {method: 'POST', cache: 'no-store', credentials: 'omit',
        mode: 'same-origin', redirect: 'error', referrerPolicy: 'no-referrer', keepalive, signal: controller.signal,
        headers: {'Content-Type': 'application/x-ndjson', 'X-Yadinassi-Session': key, ...headers}, body: JSON.stringify(body) + '\n'}));
    } finally { clearTimeout(timer); }
  }
  adopt(value, issued = false) {
    validateStatus(value, issued, this.info);
    if (this.info && (value.generation !== this.info.generation || value.role !== this.info.role)) this.paused = true;
    if (issued) {
      this.credential = value.credential;
      try { this.environment.sessionStorage.setItem(RESUME_KEY, value.resume); } catch { /* Reopen launcher after reload if unavailable. */ }
      this.bootstrap = value.resume;
    }
    const {credential, resume, ...publicStatus} = value; this.info = publicStatus;
    if (value.role !== 'writer' || value.closed) this.paused = true;
    this.changed();
  }
  fail(error) {
    this.paused = true; this.message = error instanceof AttachmentRefusal ? error.message : messages.connection;
    if (error?.code === 'unauthorized' || error?.code === 'closed') {
      this.stopHeartbeat();
      try { this.environment.sessionStorage.removeItem(RESUME_KEY); } catch { /* No storage dependency. */ }
    }
    if (error?.code === 'outcome_unknown') this.businessUnknown = true;
    this.changed();
  }
  async attach() {
    if (!tokenText(this.bootstrap)) { this.fail(new AttachmentRefusal('unauthorized')); return false; }
    if (this.busy) return false;
    this.busy = true; this.message = ''; this.changed();
    try {
      const result = await this.post('/attachment', {action: 'attach', instance: this.instance}, this.bootstrap);
      this.adopt(result, true); this.startHeartbeat(); await this.synchronize(); return true;
    } catch (error) { this.fail(error); return false; }
    finally { this.busy = false; this.changed(); }
  }
  command(action, keepalive = false) {
    const operation = async () => {
      if (!this.info || !this.credential) throw new AttachmentRefusal('unauthorized');
      const result = await this.post('/attachment', {action, generation: this.info.generation, pending: this.pendingState}, this.credential,
        {'X-Yadinassi-Attachment': this.info.attachment}, keepalive);
      this.adopt(result); return result;
    };
    // Detach must start inside pagehide, not wait behind a paused promise chain.
    if (keepalive) return operation();
    const result = this.commandTail.then(operation);
    this.commandTail = result.catch(() => {}); return result;
  }
  async synchronize() {
    if (this.info?.role !== 'writer' || this.info.closed || this.suspended || this.businessUnknown || this.uncertain()) return;
    const epoch = this.hiddenEpoch;
    this.paused = true; this.reconciling = true; this.changed();
    try { await this.reconcile(); if (epoch === this.hiddenEpoch && !this.suspended) { this.paused = false; this.message = ''; } }
    finally { this.reconciling = false; this.changed(); }
  }
  async check() {
    if (this.busy || this.suspended) return false;
    if (!this.info) return this.attach();
    this.busy = true; this.paused = true; this.message = ''; this.changed();
    try { await this.command('status'); this.startHeartbeat(); await this.synchronize(); return true; }
    catch (error) { this.fail(error); return false; }
    finally { this.busy = false; this.changed(); }
  }
  async takeover() {
    if (this.busy || this.suspended || this.businessUnknown || this.uncertain()) return false;
    this.busy = true; this.paused = true; this.message = ''; this.changed();
    try { await this.command('takeover'); this.startHeartbeat(); await this.synchronize(); return true; }
    catch (error) { this.fail(error); return false; }
    finally { this.busy = false; this.changed(); }
  }
  startHeartbeat() {
    if (this.timer !== null || this.suspended || this.info?.closed) return;
    const schedule = this.environment.setInterval?.bind(this.environment) || setInterval;
    this.timer = schedule(() => {
      if (this.busy || this.suspended || this.heartbeatPending) return;
      this.heartbeatPending = true;
      this.command('heartbeat').catch(error => { if (error?.code !== 'busy') this.fail(error); }).finally(() => { this.heartbeatPending = false; });
    }, 15000);
    this.timer?.unref?.();
  }
  stopHeartbeat() {
    if (this.timer !== null) (this.environment.clearInterval?.bind(this.environment) || clearInterval)(this.timer);
    this.timer = null;
  }
  detach() {
    this.hiddenEpoch++; this.paused = true; this.suspended = true; this.stopHeartbeat(); this.changed();
    if (!this.info) return Promise.resolve();
    return this.command('detach', true).catch(() => {}); // Advisory only; never Save, Discard or Close.
  }
  dispose() { this.stopHeartbeat(); this.environment.removeEventListener?.('pagehide', this.hide); this.environment.removeEventListener?.('pageshow', this.show); }
  async exchange(request) {
    if (!this.writable && !(this.reconciling && this.info?.role === 'writer' && !this.suspended && readOnlyRPC(request))) throw new AttachmentRefusal('not_writer');
    this.rpcActive++;
    try {
      const result = await this.post('/rpc', request, this.credential, {'X-Yadinassi-Attachment': this.info.attachment, 'X-Yadinassi-Generation': String(this.info.generation)});
      if (result?.result?.state?.kind === 'closed') { this.info = {...this.info, closed: true}; this.paused = true; this.stopHeartbeat(); this.changed(); }
      return result;
    } catch (error) {
      if (!(error instanceof AttachmentRefusal)) this.businessUnknown = true;
      this.fail(error); throw error;
    } finally { this.rpcActive--; }
  }
}
/** Shared ownership boundary. Legacy and test-injected exchanges remain separate. */
export function createBrowserHost(environment, root) {
  const launch = readBrowserLaunch(environment);
  if (!launch.enabled) return {enabled: false, content: root, instance: documentInstance(environment),
    transport: createTransport(environment.fetch.bind(environment), launch.launcher), launcher: launch.launcher,
    start: async callback => { try { return await callback(); } catch { return false; } }, setPending() {}, notify() {}};
  const document = environment.document, banner = document.createElement('section'), description = document.createElement('p'),
    detail = document.createElement('p'), actions = document.createElement('div'), takeover = document.createElement('button'),
    check = document.createElement('button'), content = document.createElement('div');
  banner.className = 'browser-ownership'; banner.setAttribute('aria-label', 'Browser tab ownership');
  description.setAttribute('role', 'status'); description.setAttribute('aria-live', 'polite');
  takeover.type = check.type = 'button'; takeover.textContent = 'Take control'; check.textContent = 'Check connection';
  actions.append(takeover, check); banner.append(description, detail, actions); root.replaceChildren(banner, content);
  const attachment = new BrowserAttachment(environment, launch, () => paint());
  function paint() {
    const writable = attachment.writable;
    content.inert = !writable; content.setAttribute('aria-disabled', String(!writable));
    banner.dataset.role = attachment.info?.role || 'connecting';
    description.textContent = attachment.info?.closed ? messages.closed : attachment.businessUnknown || attachment.uncertain() ? messages.outcome_unknown
      : attachment.message || (writable ? 'You control this application in this tab.' : attachment.info?.role === 'observer'
        ? 'Another tab may control this application. Take control here to edit.' : 'Checking tab ownership before editing…');
    detail.textContent = attachment.pendingState || attachment.info?.recovery
      ? 'Pending changes or a recovery state need attention. Unsubmitted input is kept only in its original page; it is not restored in another tab.'
      : 'Closing the last tab allows the host to stop after a grace period when it is safe. Refresh does not repeat an action.';
    takeover.hidden = !attachment.info || attachment.info.closed || writable;
    takeover.disabled = attachment.busy || attachment.suspended || attachment.businessUnknown || attachment.uncertain();
    check.disabled = attachment.busy || attachment.suspended || Boolean(attachment.info?.closed);
  }
  takeover.addEventListener('click', () => attachment.takeover()); check.addEventListener('click', () => attachment.check());
  paint();
  return {enabled: true, content, instance: attachment.instance, attachment, transport: request => attachment.exchange(request),
    setPending(pending, uncertain = () => false) { attachment.pending = pending; attachment.uncertain = uncertain; paint(); }, notify: paint,
    start(callback) { attachment.reconcile = callback; return attachment.attach(); }};
}
