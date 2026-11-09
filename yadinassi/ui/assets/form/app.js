/* Yadinassi optional form renderer. MIT license: LICENSE.txt. Built from frontend/form. */
const __client = (() => {
/** Bounded form-only renderer protocol. No runtime, BSL or storage dependency. */
const PROTOCOL = 'yadinassi-form-ui/1';
const LIMITS = Object.freeze({bytes: 131072, text: 8192, controls: 128, messages: 64,
  counter: 2147483647, discardCommands: 64, tables: 4, columns: 8, rows: 32, rowIds: 4096, controlIds: 1024, cells: 256, dateTicks: '3155378975990000'});
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
  draft_changed: 'The host changed or removed a pending edit. Review the latest values before running the action again.',
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
  const shape = ['kind', 'revision', 'lifecycle', 'title', 'uncertain', 'items', 'messages'];
  for (const optional of ['discardCommands', 'dirty']) {
    if (record(state) && Object.hasOwn(state, optional)) shape.push(optional);
  }
  if (!keys(state, shape) ||
      !['form', 'closed'].includes(state.kind) || !integer(state.revision) ||
      !['open', 'cancelled', 'closed', 'failed'].includes(state.lifecycle) ||
      !validText(state.title) || typeof state.uncertain !== 'boolean' ||
      !Array.isArray(state.items) || state.items.length > LIMITS.controls ||
      !Array.isArray(state.messages) || state.messages.length > LIMITS.messages ||
      state.messages.some(message => !validText(message))) throw new FormError('transport');
  if (Object.hasOwn(state, 'dirty') && typeof state.dirty !== 'boolean') throw new FormError('transport');
  if (Object.hasOwn(state, 'discardCommands') && (!Array.isArray(state.discardCommands) ||
      state.discardCommands.length > LIMITS.discardCommands ||
      state.discardCommands.some(name => !validText(name) || !name.length) ||
      new Set(state.discardCommands).size !== state.discardCommands.length)) throw new FormError('transport');
  const names = new Set(), tables = new Map(), controlIds = new Set(); let cells = 0;
  for (const item of state.items) {
    const table = item?.kind === 'table';
    const shape = table ? ['name', 'kind', 'title', 'visible', 'enabled', 'readOnly', 'controlId', 'tableId', 'columns', 'rows', 'currentRow']
      : ['name', 'kind', 'title', 'visible', 'enabled', 'readOnly', 'view', 'value'];
    if (!keys(item, shape) || !validText(item.name) || !item.name.length || names.has(item.name) ||
        !validText(item.title) || !['field', 'button', 'table'].includes(item.kind) ||
        ['visible', 'enabled', 'readOnly'].some(name => typeof item[name] !== 'boolean')) throw new FormError('transport');
    names.add(item.name);
    if (table) {
      if (!integer(item.controlId) || !item.controlId || item.controlId > LIMITS.controlIds || controlIds.has(item.controlId) ||
          !integer(item.tableId) || !item.tableId || !Array.isArray(item.columns) || !item.columns.length ||
          item.columns.length > LIMITS.columns || !Array.isArray(item.rows) || item.rows.length > LIMITS.rows)
        throw new FormError('transport');
      controlIds.add(item.controlId);
      const columns = new Set(), rows = new Set();
      for (const column of item.columns) {
        if (!keys(column, ['name', 'title', 'type', 'readOnly']) || !validText(column.name) || !column.name.length ||
            columns.has(column.name) || !validText(column.title) || !['String', 'Number', 'Boolean', 'Date'].includes(column.type) ||
            typeof column.readOnly !== 'boolean') throw new FormError('transport');
        columns.add(column.name);
      }
      for (const row of item.rows) {
        if (!keys(row, ['id', 'values']) || !integer(row.id) || !row.id || row.id > LIMITS.rowIds || rows.has(row.id) ||
            !Array.isArray(row.values) || row.values.length !== item.columns.length) throw new FormError('transport');
        rows.add(row.id);
        row.values.forEach((value, index) => {
          validateScalar(value);
          if (!['Null', 'Undefined', item.columns[index].type].includes(value.type)) throw new FormError('transport');
        });
      }
      if (item.currentRow !== null && (!integer(item.currentRow) || !rows.has(item.currentRow))) throw new FormError('transport');
      if (tables.has(item.tableId)) throw new FormError('transport');
      tables.set(item.tableId, true); cells += item.rows.length * item.columns.length;
      if (tables.size > LIMITS.tables || cells > LIMITS.cells) throw new FormError('transport');
    } else {
      if (!['input', 'checkbox', 'label'].includes(item.view)) throw new FormError('transport');
      if (item.kind === 'button') { if (item.value !== null) throw new FormError('transport'); }
      else {
        validateScalar(item.value);
        if (item.view === 'checkbox' && item.value.type !== 'Boolean') throw new FormError('transport');
      }
    }
  }
  if ((state.discardCommands || []).some(name => !state.items.some(item => item.name === name && item.kind === 'button')))
    throw new FormError('transport');
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
/** A bounded cell uses exactly the same scalar input rules as an ordinary field. */
function tableCell(item, rowId, columnName) {
  if (item?.kind !== 'table') return null;
  const index = item.columns.findIndex(column => column.name === columnName);
  const row = item.rows.find(row => row.id === rowId), column = item.columns[index];
  return !row || !column ? null : {kind: 'field', visible: item.visible, enabled: item.enabled,
    readOnly: item.readOnly || column.readOnly, view: 'input', value: row.values[index]};
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
function scalarEqual(left, right) {
  return Boolean(left && right && left.type === right.type && left.value === right.value && left.ticks === right.ticks);
}
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
    } else if (event === 'cell' || event === 'select') {
      if (!keys(values, event === 'cell' ? ['control', 'row', 'column', 'value'] : ['control', 'row']))
        throw new FormError('invalid_input');
      const item = this.snapshot.items.find(candidate => candidate.name === values.control);
      if (item?.kind !== 'table' || !item.visible || !item.enabled || event === 'cell' && item.readOnly) throw new FormError('unavailable');
      if (values.row !== null && (!integer(values.row) || !values.row || !item.rows.some(row => row.id === values.row)))
        throw new FormError('invalid_input');
      params.control = item.name; params.row = values.row;
      if (event === 'cell') {
        const cell = tableCell(item, values.row, values.column);
        if (!editable(cell)) throw new FormError('unavailable');
        validateScalar(values.value);
        if (values.value.type !== cell.value.type) throw new FormError('invalid_input');
        params.column = values.column; params.value = values.value;
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

return {PROTOCOL, LIMITS, ERROR_MESSAGES, FormError, decimalText, validateScalar, validateSnapshot, scalarText, editable, tableCell, typedInput, scalarEqual, FormClient, readBoundedJSON, createTransport, takeSessionCapability};
})();
const __view = (() => {
const {editable, tableCell, scalarText, typedInput, scalarEqual, LIMITS} = __client;

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
  const controls = new Map(); const drafts = new Map(), cellDrafts = new Map();
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
  const cellKey = (control, controlId, tableId, row, column) => JSON.stringify([control, controlId, tableId, row, column]);
  function discardTable(name) {
    for (const [key, draft] of cellDrafts) if (draft.control === name) cellDrafts.delete(key);
  }
  function makeTable(item) {
    const row = element('section', 'form-table');
    const toolbar = element('div', 'table-toolbar'), heading = element('h2', 'table-title');
    const summary = element('span', 'table-summary'); summary.setAttribute('role', 'status');
    const clear = element('button', 'quiet table-clear', 'Clear selection');
    clear.type = 'button'; clear.dataset.formAction = 'select';
    clear.addEventListener('click', () => handlers.select(item.name, null));
    toolbar.append(heading, summary, clear);
    const help = element('p', 'table-help', 'Edit cells, then use a form command. Selecting a row first applies all pending edits.');
    help.id = 'form-table-help-' + ++serial;
    const scroll = element('div', 'table-scroll'); scroll.tabIndex = 0;
    scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', item.title || item.name);
    const table = element('table', 'data-table'), caption = element('caption', 'sr-only');
    const head = element('thead'), headerRow = element('tr');
    const selected = element('th', 'selection-heading', 'Current row'); selected.setAttribute('scope', 'col');
    headerRow.append(selected); head.append(headerRow);
    const body = element('tbody'); table.append(caption, head, body); scroll.append(table);
    const empty = element('p', 'table-empty', 'No rows.');
    row.append(toolbar, help, scroll, empty);
    return {row, heading, summary, clear, help, scroll, caption, headerRow, body, empty,
      headers: new Map(), rows: new Map(), item};
  }
  function makeCell(control, rowId, column) {
    const cell = element('td'), input = element('input', 'cell-input'); cell.append(input);
    input.id = 'form-cell-' + ++serial; input.autocomplete = 'off'; input.spellcheck = false;
    const name = control.item.name, controlId = control.item.controlId, tableId = control.item.tableId;
    const locator = {control: name, row: rowId, column: column.name};
    const key = cellKey(name, controlId, tableId, rowId, column.name);
    const currentCell = () => tableCell(controls.get(name)?.item, rowId, column.name);
    input.addEventListener('input', () => {
      const active = currentCell();
      if (isBusy || controls.get(name)?.item.tableId !== tableId || controls.get(name)?.item.controlId !== controlId || !editable(active)) return;
      const value = input.type === 'checkbox' ? input.checked : input.value;
      if (sameValue(active, value)) cellDrafts.delete(key);
      else cellDrafts.set(key, {...locator, controlId, tableId, type: active.value.type, value, base: active.value});
    });
    input.addEventListener('change', () => { if (input.type === 'checkbox' && !isBusy) handlers.change(locator); });
    input.addEventListener('blur', event => {
      if (input.type !== 'checkbox' && !isBusy && !actionPointer &&
          !event.relatedTarget?.closest('[data-form-action]')) handlers.change(locator);
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.isComposing && input.type !== 'checkbox') {
        event.preventDefault(); handlers.change(locator);
      }
    });
    return {cell, input, type: column.type, key};
  }
  function renderTable(control, model, active) {
    const item = control.item;
    const disabled = model.busy || model.locked || !active || !item.enabled || !item.visible;
    control.heading.textContent = item.title || item.name;
    control.caption.textContent = (item.title || item.name) + '. ' + control.help.textContent;
    control.scroll.setAttribute('aria-label', item.title || item.name);
    control.summary.textContent = item.rows.length + (item.rows.length === 1 ? ' row' : ' rows') +
      (item.currentRow === null ? ' · No row selected' : ' · Selected row ' + item.currentRow);
    control.clear.disabled = disabled || item.currentRow === null;
    control.clear.setAttribute('aria-label', 'Clear selection in ' + (item.title || item.name));
    control.empty.hidden = item.rows.length > 0;
    const columns = new Set(item.columns.map(column => column.name));
    for (const [name, header] of control.headers) if (!columns.has(name)) { header.remove(); control.headers.delete(name); }
    item.columns.forEach((column, index) => {
      let header = control.headers.get(column.name);
      if (!header) { header = element('th'); header.setAttribute('scope', 'col'); control.headers.set(column.name, header); }
      header.textContent = column.title || column.name;
      header.title = column.type + (column.readOnly ? ' · Read-only' : '');
      if (control.headerRow.children[index + 1] !== header)
        control.headerRow.insertBefore(header, control.headerRow.children[index + 1] || null);
    });
    const rows = new Set(item.rows.map(row => row.id));
    for (const [id, row] of control.rows) if (!rows.has(id)) { row.node.remove(); control.rows.delete(id); }
    item.rows.forEach((data, position) => {
      let row = control.rows.get(data.id);
      if (!row) {
        const node = element('tr'), label = element('th', 'row-selector'); label.setAttribute('scope', 'row');
        const select = element('button', 'select-row'); select.type = 'button'; select.dataset.formAction = 'select';
        select.addEventListener('click', () => handlers.select(item.name, data.id));
        label.append(select); node.append(label); row = {node, select, cells: new Map()}; control.rows.set(data.id, row);
      }
      if (control.body.children[position] !== row.node) control.body.insertBefore(row.node, control.body.children[position] || null);
      const selected = item.currentRow === data.id;
      row.node.className = selected ? 'current-row' : '';
      row.select.textContent = (selected ? 'Selected ' : 'Select ') + data.id;
      row.select.setAttribute('aria-label', (selected ? 'Selected row ' : 'Select row ') + data.id + ' in ' + (item.title || item.name));
      row.select.setAttribute('aria-pressed', selected ? 'true' : 'false');
      row.select.disabled = disabled;
      for (const [name, cell] of row.cells) if (!columns.has(name)) { cell.cell.remove(); row.cells.delete(name); }
      item.columns.forEach((column, index) => {
        const value = data.values[index]; let cell = row.cells.get(column.name);
        if (cell && (cell.type !== column.type || cell.valueType !== value.type)) {
          cell.cell.remove(); cellDrafts.delete(cell.key); row.cells.delete(column.name); cell = null;
        }
        if (!cell) { cell = makeCell(control, data.id, column); cell.valueType = value.type; row.cells.set(column.name, cell); }
        if (row.node.children[index + 1] !== cell.cell) row.node.insertBefore(cell.cell, row.node.children[index + 1] || null);
        const field = tableCell(item, data.id, column.name), readOnly = !editable(field), input = cell.input;
        input.type = value.type === 'Boolean' ? 'checkbox' : 'text';
        input.className = 'cell-input' + (value.type === 'Number' ? ' decimal-cell' : '');
        input.disabled = disabled || input.type === 'checkbox' && readOnly; input.readOnly = readOnly;
        input.setAttribute('aria-label', (column.title || column.name) + ', row ' + data.id);
        input.setAttribute('aria-describedby', control.help.id);
        input.setAttribute('aria-readonly', readOnly ? 'true' : 'false');
        input.title = value.type === 'Date' ? 'Date ticks · read-only · no timezone conversion'
          : ['Null', 'Undefined'].includes(value.type) ? 'Typed empty value · read-only'
          : readOnly ? 'Read-only' : value.type === 'Number' ? 'Exact decimal · use a decimal point (.)' : '';
        const draft = cellDrafts.get(cell.key), text = draft ? draft.value : value.type === 'Boolean' ? value.value : scalarText(value);
        if (input.type === 'checkbox') input.checked = text === true;
        else if (input.value !== text) input.value = text;
        input.maxLength = value.type === 'Number' ? 144 : LIMITS.text;
        input.inputMode = value.type === 'Number' ? 'decimal' : 'text';
      });
    });
  }
  function reconcileCells() {
    for (const [key, draft] of cellDrafts) {
      const item = current?.items.find(item => item.name === draft.control);
      const cell = tableCell(item, draft.row, draft.column);
      if (item?.tableId !== draft.tableId || item?.controlId !== draft.controlId || !editable(cell) || cell.value.type !== draft.type ||
          !scalarEqual(cell.value, draft.base)) cellDrafts.delete(key);
    }
  }
  function render(model) {
    const savedFocus = captureFocus();
    if (model.busy && !isBusy) focusMemory = savedFocus;
    const wasBusy = isBusy; isBusy = model.busy; current = model.snapshot;
    reconcileCells();
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
    for (const [name, control] of controls) if (!names.has(name)) { control.row.remove(); controls.delete(name); drafts.delete(name); discardTable(name); }
    let fieldIndex = 0, actionIndex = 0;
    for (const item of current?.items || []) {
      let control = controls.get(item.name);
      if (control && (control.item.kind !== item.kind || control.item.value?.type !== item.value?.type || control.item.tableId !== item.tableId || control.item.controlId !== item.controlId)) {
        control.row.remove(); controls.delete(item.name); drafts.delete(item.name); discardTable(item.name); control = null;
      }
      if (!control) { control = item.kind === 'table' ? makeTable(item) : makeControl(item); controls.set(item.name, control); }
      control.item = item;
      const {row, caption, input, hint} = control;
      const parent = item.kind === 'button' ? actions : fields;
      const position = item.kind === 'button' ? actionIndex++ : fieldIndex++;
      if (parent.children[position] !== row) parent.insertBefore(row, parent.children[position] || null);
      row.hidden = !item.visible || current.kind === 'closed';
      if (item.kind === 'table') { renderTable(control, model, active); continue; }
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
    accept(change) {
      if (typeof change === 'string') drafts.delete(change);
      else if (!Object.hasOwn(change, 'row')) drafts.delete(change.control);
      else {
        const item = current?.items.find(item => item.name === change.control);
        cellDrafts.delete(cellKey(change.control, item?.controlId, item?.tableId, change.row, change.column));
      }
    },
    clearDrafts() { drafts.clear(); cellDrafts.clear(); },
    hasDrafts() { return drafts.size + cellDrafts.size > 0; },
    changes(only) {
      const changes = [];
      for (const item of current?.items || []) {
        if (item.kind === 'table') {
          for (const row of item.rows) for (const column of item.columns) {
            if (only !== undefined && (typeof only !== 'object' || only.control !== item.name || only.row !== row.id || only.column !== column.name)) continue;
            const key = cellKey(item.name, item.controlId, item.tableId, row.id, column.name), draft = cellDrafts.get(key);
            if (!draft) continue;
            const field = tableCell(item, row.id, column.name), value = typedInput(field, draft.value);
            if (!scalarEqual(value, field.value)) changes.push({control: item.name, row: row.id, column: column.name, value});
            else cellDrafts.delete(key);
          }
        } else {
          const draft = drafts.get(item.name);
          if (!draft || only !== undefined && item.name !== only) continue;
          const value = typedInput(item, draft.value);
          if (!scalarEqual(value, item.value)) changes.push({control: item.name, value});
          else drafts.delete(item.name);
        }
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
function mountForm(environment, root, options = {}) {
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
    if (event === 'change' && options.isActive && !options.isActive()) return;
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
    try { changes = view.changes(event === 'change' ? name : undefined); }
    catch (caught) { showError(caught); paint(); return; }
    if (event === 'change' && !changes.length) return;
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

return {mountForm};
})();
