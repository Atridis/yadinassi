/** Bounded form-only renderer protocol. No runtime, BSL or storage dependency. */
export const PROTOCOL = 'yadinassi-form-ui/1';
export const LIMITS = Object.freeze({bytes: 131072, text: 8192, controls: 128, messages: 64,
  counter: 2147483647, discardCommands: 64, tables: 4, columns: 8, rows: 32, rowIds: 4096, controlIds: 1024, cells: 256, dateTicks: '3155378975990000'});
export const ERROR_MESSAGES = Object.freeze({
  reference_refused: 'The reference selection was refused. Review the current value and choose again.',
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
export class FormError extends Error {
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
export function decimalText(input) {
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
export function validateScalar(value) {
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
    case 'FormCatalogRef':
      if (keys(value, ['type', 'scope', 'target', 'key', 'text']) &&
          typeof value.scope === 'string' && /^[0-9a-f]{32}$/.test(value.scope) &&
          Number.isInteger(value.target) && value.target >= 1 && value.target <= 128 &&
          (value.key === null || typeof value.key === 'string' && /^[0-9a-f]{32}$/.test(value.key)) &&
          validText(value.text, 4096) && [...value.text].length <= 1024) return value;
      break;
    case 'Date':
      if (keys(value, ['type', 'ticks']) && typeof value.ticks === 'string' && value.ticks.length <= 19 &&
          /^(?:0|[1-9][0-9]*)$/.test(value.ticks) && BigInt(value.ticks) <= BigInt(LIMITS.dateTicks)) return value;
      break;
  }
  throw new FormError('transport');
}
export function validateSnapshot(state) {
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
            columns.has(column.name) || !validText(column.title) || !['String', 'Number', 'Boolean', 'Date', 'FormCatalogRef'].includes(column.type) ||
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
export function scalarText(value) {
  validateScalar(value);
  if (value.type === 'FormCatalogRef') return value.text;
  if (value.type === 'Boolean') return value.value ? 'Yes' : 'No';
  if (value.type === 'Date') return value.ticks;
  if (value.type === 'Undefined') return 'Undefined';
  if (value.type === 'Null') return 'Null';
  return value.value;
}
export function editable(item) {
  return item?.kind === 'field' && item.visible && item.enabled && !item.readOnly && item.view !== 'label' &&
    ['String', 'Number', 'Boolean'].includes(item.value.type);
}
/** A bounded cell uses exactly the same scalar input rules as an ordinary field. */
export function tableCell(item, rowId, columnName) {
  if (item?.kind !== 'table') return null;
  const index = item.columns.findIndex(column => column.name === columnName);
  const row = item.rows.find(row => row.id === rowId), column = item.columns[index];
  return !row || !column ? null : {kind: 'field', visible: item.visible, enabled: item.enabled,
    readOnly: item.readOnly || column.readOnly, view: 'input', value: row.values[index]};
}
export function typedInput(item, input) {
  if (!editable(item)) throw new FormError('unavailable');
  if (item.value.type === 'Boolean') {
    if (typeof input !== 'boolean') throw new FormError('invalid_input');
    return {type: 'Boolean', value: input};
  }
  if (item.value.type === 'Number') return {type: 'Number', value: decimalText(input)};
  if (!validText(input)) throw new FormError('invalid_input');
  return {type: 'String', value: input};
}
export function scalarEqual(left, right) {
  if (left?.type === 'FormCatalogRef' || right?.type === 'FormCatalogRef')
    return Boolean(left && right && left.type === right.type && left.scope === right.scope &&
      left.target === right.target && left.key === right.key);
  return Boolean(left && right && left.type === right.type && left.value === right.value && left.ticks === right.ticks);
}
export class FormClient {
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
      } catch (error) {
        if (error?.preDispatch === true) throw error;
        this.transportFailed = true; throw new FormError('transport');
      }
      return this.adopt(reply, id);
    } finally { this.busy = false; }
  }
  /** Adopt a host reference result without fabricating a form event or consuming its request ID. */
  adopt(reply, expectedId = 1) {
    try {
      if (!keys(reply, ['jsonrpc', 'id', 'result']) || reply.jsonrpc !== '2.0' || reply.id !== expectedId ||
          !keys(reply.result, ['protocol', 'state', 'error']) || reply.result.protocol !== PROTOCOL ||
          !(reply.result.error === null || ['invalid_request', 'stale_revision', 'event_failed', 'closed',
            'outcome_unknown', 'busy', 'request_limit', 'reference_refused'].includes(reply.result.error))) throw new FormError('transport');
      validateSnapshot(reply.result.state);
      if (this.snapshot && reply.result.state.revision < this.snapshot.revision) throw new FormError('transport');
    } catch { this.transportFailed = true; throw new FormError('transport'); }
    // Authoritative failures can contain completed effects, including presentation changes.
    this.snapshot = reply.result.state; this.transportFailed = false;
    this.outcomeUnknown ||= this.snapshot.uncertain || reply.result.error === 'outcome_unknown';
    this.exhausted ||= reply.result.error === 'request_limit';
    if (reply.result.error !== null) throw new FormError(reply.result.error);
    return this.snapshot;
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
export async function readBoundedJSON(response) {
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
export function createTransport(fetcher, token, timeout = 35000) {
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
export function takeSessionCapability(location, history) {
  const params = new URLSearchParams(location.hash.slice(1));
  if (location.hash) history.replaceState(null, '', location.pathname);
  const values = params.getAll('session');
  return values.length === 1 && /^[A-Za-z0-9_-]{32,128}$/.test(values[0]) ? values[0] : null;
}
