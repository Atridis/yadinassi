/* Yadinassi optional form renderer. MIT license: LICENSE.txt. Built from frontend/form. */
const __client = (() => {
/** Bounded form-only renderer protocol. No runtime, BSL or storage dependency. */
const PROTOCOL = 'yadinassi-form-ui/0';
const LIMITS = Object.freeze({bytes: 131072, text: 8192, controls: 128, messages: 64,
  counter: 2147483647, dateTicks: '3155378975990000'});
const ERROR_MESSAGES = Object.freeze({
  invalid_request: 'The host rejected this request. The displayed state is authoritative.',
  stale_revision: 'The form changed elsewhere. Review the latest state before another action.',
  event_failed: 'The handler returned an error. Completed changes are shown below.',
  closed: 'This form session is closed.',
  outcome_unknown: 'The host cannot determine the outcome. This session is locked; do not repeat the action.',
  busy: 'Another request is in progress. No additional action was sent.',
  request_limit: 'The session request limit has been reached. No additional action was sent.',
  transport: 'Connection interrupted or response invalid. The outcome may be unknown. Refresh state before another action; do not repeat the action.',
  invalid_input: 'Enter a supported value within the field limit.',
  unavailable: 'This control is unavailable or read-only.',
  session_missing: 'Reopen the complete URL printed by the launcher to reconnect. The session key is not stored in this browser.',
});
class FormError extends Error {
  constructor(code) { super(ERROR_MESSAGES[code] || ERROR_MESSAGES.transport); this.name = 'FormError'; this.code = code; }
}
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value) &&
  [Object.prototype, null].includes(Object.getPrototypeOf(value));
const keys = (value, names) => record(value) && Object.keys(value).length === names.length &&
  names.every(name => Object.hasOwn(value, name));
const integer = value => Number.isInteger(value) && value >= 0 && value <= LIMITS.counter;
function validText(value, maximum = LIMITS.text) {
  if (typeof value !== 'string' || value.length > maximum) return false;
  // TextEncoder substitutes lone surrogates. Reject them instead of silently changing data.
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(++index);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
    } else if (code >= 0xdc00 && code <= 0xdfff) return false;
  }
  return new TextEncoder().encode(value).length <= maximum;
}
/** Python Decimal's finite canonical spelling, calculated entirely from text. */
function decimalText(input) {
  if (typeof input !== 'string' || input.length > 144) throw new FormError('invalid_input');
  const match = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d{1,5}))?$/.exec(input);
  if (!match) throw new FormError('invalid_input');
  const fraction = match[3] ?? match[4] ?? '';
  let digits = ((match[2] || '') + fraction).replace(/^0+/, '') || '0';
  // Only the small, bounded exponent is an integer. The coefficient never enters JS Number.
  const exponent = Number(match[5] || '0') - fraction.length;
  if (digits.length > 128 || Math.abs(exponent) > 4096) throw new FormError('invalid_input');
  const adjusted = digits.length + exponent - 1;
  let result;
  if (exponent <= 0 && adjusted >= -6) {
    const split = digits.length + exponent;
    result = exponent === 0 ? digits : split > 0 ? digits.slice(0, split) + '.' + digits.slice(split)
      : '0.' + '0'.repeat(-split) + digits;
  } else {
    result = digits[0] + (digits.length > 1 ? '.' + digits.slice(1) : '') + 'E' + (adjusted >= 0 ? '+' : '') + adjusted;
  }
  result = (match[1] === '-' ? '-' : '') + result;
  if (result.length > 144) throw new FormError('invalid_input');
  return result;
}
function validateScalar(value) {
  if (!record(value) || typeof value.type !== 'string') throw new FormError('transport');
  switch (value.type) {
    case 'Undefined': case 'Null': if (keys(value, ['type'])) return value; break;
    case 'String': if (keys(value, ['type', 'value']) && validText(value.value)) return value; break;
    case 'Boolean': if (keys(value, ['type', 'value']) && typeof value.value === 'boolean') return value; break;
    case 'Number':
      if (keys(value, ['type', 'value'])) {
        try { if (decimalText(value.value) === value.value) return value; } catch { /* Reject noncanonical scalars. */ }
      }
      break;
    case 'Date':
      if (keys(value, ['type', 'ticks']) && typeof value.ticks === 'string' && value.ticks.length <= 19 &&
          /^(?:0|[1-9][0-9]*)$/.test(value.ticks) && BigInt(value.ticks) <= BigInt(LIMITS.dateTicks)) return value;
      break;
  }
  throw new FormError('transport');
}
function validateSnapshot(state) {
  if (!keys(state, ['kind', 'revision', 'lifecycle', 'title', 'uncertain', 'items', 'messages']) ||
      !['form', 'closed'].includes(state.kind) || !integer(state.revision) ||
      !['open', 'cancelled', 'closed', 'failed'].includes(state.lifecycle) ||
      !validText(state.title) || typeof state.uncertain !== 'boolean' ||
      !Array.isArray(state.items) || state.items.length > LIMITS.controls ||
      !Array.isArray(state.messages) || state.messages.length > LIMITS.messages ||
      state.messages.some(message => !validText(message))) throw new FormError('transport');
  const names = new Set();
  for (const item of state.items) {
    if (!keys(item, ['name', 'kind', 'title', 'visible', 'enabled', 'readOnly', 'view', 'value']) ||
        !validText(item.name) || !item.name.length || names.has(item.name) || !validText(item.title) ||
        !['field', 'button'].includes(item.kind) || !['input', 'checkbox', 'label'].includes(item.view) ||
        ['visible', 'enabled', 'readOnly'].some(name => typeof item[name] !== 'boolean')) throw new FormError('transport');
    names.add(item.name);
    if (item.kind === 'button') { if (item.value !== null) throw new FormError('transport'); }
    else {
      validateScalar(item.value);
      if (item.view === 'checkbox' && item.value.type !== 'Boolean') throw new FormError('transport');
    }
  }
  if (new TextEncoder().encode(JSON.stringify(state)).length > LIMITS.bytes) throw new FormError('transport');
  return state;
}
function scalarText(value) {
  validateScalar(value);
  if (value.type === 'Boolean') return value.value ? 'Yes' : 'No';
  if (value.type === 'Date') return value.ticks;
  if (value.type === 'Undefined') return 'Undefined';
  if (value.type === 'Null') return 'Null';
  return value.value;
}
function editable(item) {
  return item?.kind === 'field' && item.visible && item.enabled && !item.readOnly && item.view !== 'label' &&
    ['String', 'Number', 'Boolean'].includes(item.value.type);
}
function typedInput(item, input) {
  if (!editable(item)) throw new FormError('unavailable');
  if (item.value.type === 'Boolean') {
    if (typeof input !== 'boolean') throw new FormError('invalid_input');
    return {type: 'Boolean', value: input};
  }
  if (item.value.type === 'Number') return {type: 'Number', value: decimalText(input)};
  if (!validText(input)) throw new FormError('invalid_input');
  return {type: 'String', value: input};
}
function scalarEqual(left, right) { return JSON.stringify(left) === JSON.stringify(right); }
class FormClient {
  constructor(exchange) {
    this.exchange = exchange; this.id = 0; this.snapshot = null; this.busy = false;
    this.transportFailed = false; this.outcomeUnknown = false; this.exhausted = false;
  }
  get locked() {
    return this.transportFailed || this.outcomeUnknown || this.exhausted || !this.snapshot ||
      this.snapshot.kind === 'closed' || this.snapshot.lifecycle !== 'open';
  }
  async request(method, params) {
    if (this.busy) throw new FormError('busy');
    if (this.exhausted || this.id >= LIMITS.counter) { this.exhausted = true; throw new FormError('request_limit'); }
    this.busy = true;
    const id = ++this.id;
    try {
      let reply;
      try {
        reply = await this.exchange({jsonrpc: '2.0', id, method, params});
        if (!keys(reply, ['jsonrpc', 'id', 'result']) || reply.jsonrpc !== '2.0' || reply.id !== id ||
            !keys(reply.result, ['protocol', 'state', 'error']) || reply.result.protocol !== PROTOCOL ||
            !(reply.result.error === null || ['invalid_request', 'stale_revision', 'event_failed', 'closed',
              'outcome_unknown', 'busy', 'request_limit'].includes(reply.result.error))) throw new FormError('transport');
        validateSnapshot(reply.result.state);
        if (this.snapshot && reply.result.state.revision < this.snapshot.revision) throw new FormError('transport');
      } catch {
        this.transportFailed = true;
        throw new FormError('transport');
      }
      // Even a failed handler can have completed effects. Adopt its whole snapshot first.
      this.snapshot = reply.result.state;
      this.transportFailed = false;
      this.outcomeUnknown ||= this.snapshot.uncertain || reply.result.error === 'outcome_unknown';
      this.exhausted ||= reply.result.error === 'request_limit';
      if (reply.result.error !== null) throw new FormError(reply.result.error);
      return this.snapshot;
    } finally { this.busy = false; }
  }
  hello() { return this.request('form.hello', {protocol: PROTOCOL}); }
  resync() { return this.request('form.snapshot', {}); }
  event(event, values = {}) {
    if (this.busy) throw new FormError('busy');
    if (this.locked) throw new FormError(this.outcomeUnknown ? 'outcome_unknown' : this.transportFailed ? 'transport' : this.exhausted ? 'request_limit' : 'closed');
    const params = {event, revision: this.snapshot.revision};
    if (event === 'close') {
      if (!keys(values, [])) throw new FormError('invalid_input');
    } else if (event === 'change' || event === 'command') {
      if (!keys(values, event === 'change' ? ['control', 'value'] : ['control'])) throw new FormError('invalid_input');
      const item = this.snapshot.items.find(candidate => candidate.name === values.control);
      if (!item || !item.visible || !item.enabled || item.readOnly ||
          (event === 'change' ? !editable(item) : item.kind !== 'button')) throw new FormError('unavailable');
      params.control = item.name;
      if (event === 'change') {
        validateScalar(values.value);
        if (values.value.type !== item.value.type) throw new FormError('invalid_input');
        params.value = values.value;
      }
    } else throw new FormError('invalid_input');
    return this.request('form.event', params);
  }
}
async function readBoundedJSON(response) {
  if (!response.ok || !response.body?.getReader ||
      !/^application\/x-ndjson(?:;\s*charset=utf-8)?$/i.test(response.headers.get('content-type') || '')) throw new FormError('transport');
  const reader = response.body.getReader(); const chunks = []; let size = 0;
  try {
    for (;;) {
      const {done, value} = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > LIMITS.bytes) throw new FormError('transport');
      chunks.push(value);
    }
  } catch (error) { try { await reader.cancel(); } catch { /* The connection may already be closed. */ } throw error; }
  finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  const text = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
  if (!text.endsWith('\n') || text.slice(0, -1).includes('\n')) throw new FormError('transport');
  return JSON.parse(text);
}
function createTransport(fetcher, token, timeout = 35000) {
  return async request => {
    if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new FormError('session_missing');
    const body = JSON.stringify(request) + '\n';
    if (new TextEncoder().encode(body).length > LIMITS.bytes) throw new FormError('invalid_input');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      return await readBoundedJSON(await fetcher('/rpc', {method: 'POST', cache: 'no-store', credentials: 'omit',
        mode: 'same-origin', redirect: 'error', referrerPolicy: 'no-referrer', signal: controller.signal,
        headers: {'Content-Type': 'application/x-ndjson', 'X-Yadinassi-Session': token}, body}));
    } finally { clearTimeout(timer); }
  };
}
function takeSessionCapability(location, history) {
  const params = new URLSearchParams(location.hash.slice(1));
  if (location.hash) history.replaceState(null, '', location.pathname);
  const values = params.getAll('session');
  return values.length === 1 && /^[A-Za-z0-9_-]{32,128}$/.test(values[0]) ? values[0] : null;
}

return {PROTOCOL, LIMITS, ERROR_MESSAGES, FormError, decimalText, validateScalar, validateSnapshot, scalarText, editable, typedInput, scalarEqual, FormClient, readBoundedJSON, createTransport, takeSessionCapability};
})();
const __view = (() => {
const {editable, scalarText, typedInput, scalarEqual, LIMITS} = __client;

/** Keyed, text-only DOM renderer. The host can name controls but cannot supply HTML. */
function createFormView(document, root, handlers) {
  const element = (tag, className = '', text = '') => {
    const node = document.createElement(tag); node.className = className; node.textContent = text; return node;
  };
  const main = element('main', 'workspace');
  const header = element('header', 'page-header');
  const heading = element('div', 'heading');
  const brand = element('span', 'brand', 'YADINASSI / FORM');
  const title = element('h1', '', 'Local form');
  const subtitle = element('p', 'subtitle', 'Runtime-owned state · exact values · local connection');
  heading.append(brand, title, subtitle);
  const headerActions = element('div', 'header-actions');
  const refresh = element('button', 'quiet', 'Refresh state');
  refresh.type = 'button'; refresh.dataset.formAction = 'refresh';
  refresh.title = 'Read the latest state without repeating an action. Unsubmitted inputs will be replaced.';
  refresh.addEventListener('click', () => handlers.refresh());
  const close = element('button', 'quiet', 'Close form');
  close.type = 'button'; close.dataset.formAction = 'close';
  close.addEventListener('click', () => handlers.action('close'));
  headerActions.append(refresh, close); header.append(heading, headerActions);
  const error = element('section', 'notice error'); error.setAttribute('role', 'alert'); error.hidden = true;
  const lock = element('section', 'notice warning'); lock.setAttribute('role', 'status'); lock.hidden = true;
  const panel = element('section', 'panel'); panel.setAttribute('aria-label', 'Form');
  const panelHeader = element('div', 'panel-header');
  const status = element('span', 'badge'); status.setAttribute('role', 'status');
  const revision = element('span', 'revision'); panelHeader.append(status, revision);
  const empty = element('div', 'empty');
  const fields = element('div', 'fields');
  const messages = element('section', 'messages'); messages.setAttribute('aria-label', 'Form messages');
  messages.setAttribute('aria-live', 'polite'); messages.setAttribute('aria-atomic', 'true');
  const actions = element('div', 'form-actions');
  panel.append(panelHeader, empty, fields, messages, actions);
  const footer = element('footer', 'page-footer', 'Changes are handled by the host. Refresh reads state only and never repeats a command.');
  main.append(header, error, lock, panel, footer); root.replaceChildren(main);
  const controls = new Map(); const drafts = new Map();
  let current = null, isBusy = false, focusMemory = null, actionPointer = false;
  let serial = 0;
  const sameValue = (item, input) => item.value.type === 'Boolean' ? item.value.value === input : scalarText(item.value) === input;
  const captureFocus = () => {
    const node = document.activeElement;
    if (!node || !root.contains(node)) return null;
    return {node, start: node.selectionStart, end: node.selectionEnd, direction: node.selectionDirection};
  };
  const restoreFocus = saved => {
    if (!saved || !root.contains(saved.node) || saved.node.disabled || saved.node.hidden ||
        saved.node.closest('[hidden]')) return;
    const active = document.activeElement;
    if (active && active !== document.body && active !== saved.node) return;
    saved.node.focus({preventScroll: true});
    if (typeof saved.start === 'number' && saved.node.setSelectionRange) {
      const length = saved.node.value.length;
      saved.node.setSelectionRange(Math.min(saved.start, length), Math.min(saved.end, length), saved.direction || 'none');
    }
  };
  main.addEventListener('pointerdown', event => { actionPointer = Boolean(event.target.closest('[data-form-action]')); });
  const releasePointer = () => { setTimeout(() => { actionPointer = false; }, 0); };
  main.addEventListener('pointerup', releasePointer); main.addEventListener('pointercancel', () => { actionPointer = false; });
  function makeControl(item) {
    const row = element(item.kind === 'button' ? 'div' : 'label', item.kind === 'button' ? 'command' : 'field');
    const caption = element('span', 'field-title');
    const input = element(item.kind === 'button' ? 'button' : 'input');
    const hint = element('small', 'field-hint');
    const id = 'form-control-' + ++serial;
    input.id = id;
    if (item.kind === 'button') {
      input.type = 'button'; input.dataset.formAction = 'command'; input.className = 'primary';
      input.addEventListener('click', () => handlers.action('command', item.name));
      row.append(input);
    } else {
      row.htmlFor = id; hint.id = id + '-hint'; input.setAttribute('aria-describedby', hint.id);
      input.type = item.value.type === 'Boolean' ? 'checkbox' : 'text';
      input.autocomplete = 'off'; input.spellcheck = false;
      input.addEventListener('input', () => {
        const active = controls.get(item.name)?.item;
        if (isBusy || !editable(active)) return;
        const value = input.type === 'checkbox' ? input.checked : input.value;
        if (sameValue(active, value)) drafts.delete(item.name);
        else drafts.set(item.name, {type: active.value.type, value});
      });
      input.addEventListener('change', () => {
        if (input.type === 'checkbox' && !isBusy) handlers.change(item.name);
      });
      input.addEventListener('blur', event => {
        // Clicking or tabbing to a command belongs to its serialized flush path.
        if (input.type !== 'checkbox' && !isBusy && !actionPointer &&
            !event.relatedTarget?.closest('[data-form-action]')) handlers.change(item.name);
      });
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.isComposing && input.type !== 'checkbox') {
          event.preventDefault(); handlers.change(item.name);
        }
      });
      row.append(caption, input, hint);
    }
    return {row, caption, input, hint, item};
  }
  function render(model) {
    const savedFocus = captureFocus();
    if (model.busy && !isBusy) focusMemory = savedFocus;
    const wasBusy = isBusy; isBusy = model.busy; current = model.snapshot;
    const active = current?.kind === 'form' && current.lifecycle === 'open';
    title.textContent = current?.title || 'Local form'; document.title = title.textContent + ' · Yadinassi';
    panel.setAttribute('aria-busy', model.busy ? 'true' : 'false');
    status.textContent = model.busy ? 'Working…' : !current ? 'Not connected' : current.uncertain || model.outcomeUnknown ? 'Outcome unknown'
      : current.lifecycle === 'open' ? 'Connected' : current.lifecycle === 'cancelled' ? 'Cancelled'
      : current.lifecycle === 'failed' ? 'Failed' : 'Closed';
    status.className = 'badge ' + (current?.uncertain || model.outcomeUnknown ? 'unsafe' : active ? 'connected' : '');
    revision.textContent = current ? 'Revision ' + current.revision : 'Local session';
    refresh.disabled = model.busy || !model.connected || model.exhausted;
    close.disabled = model.busy || model.locked || !active;
    close.hidden = !current || current.kind === 'closed';
    error.textContent = model.error || ''; error.hidden = !model.error;
    lock.hidden = !(model.outcomeUnknown || current?.uncertain || model.transportFailed);
    lock.textContent = model.outcomeUnknown || current?.uncertain
      ? 'This session is locked because the host cannot determine the outcome. Refresh can inspect state but cannot unlock or repeat the action.'
      : 'Editing is locked. Use Refresh state to read the host’s result before continuing. No command will be retried.';
    empty.hidden = Boolean(current && current.kind !== 'closed' && current.items.some(item => item.visible));
    empty.textContent = !current ? (model.busy ? 'Connecting to the local host…' : 'Open the complete launch URL to attach to a form.')
      : current.kind === 'closed' ? 'This form is ' + current.lifecycle + '. You can close this tab.' : 'No visible controls.';
    const names = new Set((current?.items || []).map(item => item.name));
    for (const [name, control] of controls) if (!names.has(name)) { control.row.remove(); controls.delete(name); drafts.delete(name); }
    let fieldIndex = 0, actionIndex = 0;
    for (const item of current?.items || []) {
      let control = controls.get(item.name);
      if (control && (control.item.kind !== item.kind || control.item.value?.type !== item.value?.type)) {
        control.row.remove(); controls.delete(item.name); drafts.delete(item.name); control = null;
      }
      if (!control) { control = makeControl(item); controls.set(item.name, control); }
      control.item = item;
      const {row, caption, input, hint} = control;
      const parent = item.kind === 'button' ? actions : fields;
      const position = item.kind === 'button' ? actionIndex++ : fieldIndex++;
      if (parent.children[position] !== row) parent.insertBefore(row, parent.children[position] || null);
      row.hidden = !item.visible || current.kind === 'closed';
      const readOnly = item.kind === 'field' && !editable(item);
      if (readOnly) drafts.delete(item.name);
      input.disabled = model.busy || model.locked || !active || !item.enabled || !item.visible ||
        (item.kind === 'button' && item.readOnly) || (input.type === 'checkbox' && readOnly);
      input.readOnly = readOnly;
      if (item.kind === 'button') input.textContent = item.title || item.name;
      else {
        caption.textContent = item.title || item.name;
        input.setAttribute('aria-label', caption.textContent);
        row.className = 'field' + (item.value.type === 'Boolean' ? ' checkbox-field' : '') + (readOnly ? ' read-only' : '');
        const draft = drafts.get(item.name);
        const value = draft?.type === item.value.type ? draft.value : item.value.type === 'Boolean' ? item.value.value : scalarText(item.value);
        if (input.type === 'checkbox') input.checked = value === true;
        else if (input.value !== value) input.value = value;
        input.maxLength = item.value.type === 'Number' ? 144 : LIMITS.text;
        input.inputMode = item.value.type === 'Number' ? 'decimal' : 'text';
        hint.textContent = item.value.type === 'Date' ? 'Date ticks · read-only · no timezone conversion'
          : ['Null', 'Undefined'].includes(item.value.type) ? 'Typed empty value · read-only'
          : readOnly ? 'Read-only' : item.value.type === 'Number' ? 'Exact decimal · use a decimal point (.)'
          : item.value.type === 'Boolean' ? '' : 'Applied when you leave the field or run a command';
        hint.hidden = !hint.textContent;
      }
    }
    const nextMessages = current?.messages || [];
    // Rebuild only the bounded message list, never input nodes or host-supplied markup.
    messages.replaceChildren(...nextMessages.map(message => element('p', '', message)));
    messages.hidden = !nextMessages.length;
    actions.hidden = !current || current.kind === 'closed' || !current.items.some(item => item.kind === 'button' && item.visible);
    if (!model.busy) { restoreFocus(wasBusy ? focusMemory : savedFocus); focusMemory = null; }
  }
  return {
    render,
    accept(name) { drafts.delete(name); },
    clearDrafts() { drafts.clear(); },
    hasDrafts() { return drafts.size > 0; },
    changes(onlyName) {
      const changes = [];
      for (const item of current?.items || []) {
        const draft = drafts.get(item.name);
        if (!draft || onlyName !== undefined && item.name !== onlyName) continue;
        const value = typedInput(item, draft.value);
        if (!scalarEqual(value, item.value)) changes.push({control: item.name, value});
      }
      return changes;
    },
  };
}

return {createFormView};
})();
const __app = (() => {
const {FormClient, FormError, createTransport, takeSessionCapability} = __client;
const {createFormView} = __view;

/** Serialize UI intents before the first await, including blur followed by a command. */
function mountForm(environment, root) {
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

return {mountForm};
})();
