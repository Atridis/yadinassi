/* Yadinassi optional form renderer. MIT license: LICENSE.txt. Built from frontend/form. */
const __client = (() => {
/** Bounded form-only renderer protocol. No runtime, BSL or storage dependency. */
const PROTOCOL = 'yadinassi-form-ui/1';
const LIMITS = Object.freeze({bytes: 131072, text: 8192, controls: 128, messages: 64,
  counter: 2147483647, discardCommands: 64, tables: 4, columns: 8, rows: 32, rowIds: 4096, controlIds: 1024, cells: 256, dateTicks: '3155378975990000'});
const ERROR_MESSAGES = Object.freeze({
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
  draft_hidden: 'Unsubmitted inputs are on another page. Return to that page and apply them before running this action.',
  owned_child_open: 'Finish or close the owned form before editing its owner.',
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
  if (!match || match[0] !== input) throw new FormError('invalid_input');
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
const SECOND = 10000n, DAY = 86400n * SECOND;
// Scalar replication excludes MAX_TICKS. Use the same conservative envelope
// for fields and cells; exact values outside it remain display-only.
const EDIT_DATE_MAX = BigInt(LIMITS.dateTicks) - SECOND;
const leap = year => year % 4n === 0n && (year % 100n !== 0n || year % 400n === 0n);
const monthDays = (year, month) => month === 2n ? (leap(year) ? 29n : 28n) : [4n, 6n, 9n, 11n].includes(month) ? 30n : 31n;
const yearDays = year => { const prior = year - 1n; return prior * 365n + prior / 4n - prior / 100n + prior / 400n; };
function dateFits(value, editor) {
  const ticks = BigInt(value.ticks);
  return ticks <= EDIT_DATE_MAX && ticks % SECOND === 0n &&
    (editor.parts !== 'date' || ticks % DAY === 0n) && (editor.parts !== 'time' || ticks < DAY);
}
function dateInput(input, editor) {
  if (input === '') return {type: 'Date', ticks: '0'};
  if (typeof input !== 'string') throw new FormError('invalid_input');
  const pattern = editor.parts === 'date' ? /^(\d{4})-(\d{2})-(\d{2})$/ : editor.parts === 'time' ? /^(\d{2}):(\d{2}):(\d{2})$/
    : /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/;
  const match = pattern.exec(input);
  if (!match || match[0] !== input) throw new FormError('invalid_input');
  const parts = match.slice(1).map(BigInt);
  const [year, month, day] = editor.parts === 'time' ? [1n, 1n, 1n] : parts;
  const [hour, minute, second] = editor.parts === 'date' ? [0n, 0n, 0n] : editor.parts === 'time' ? parts : parts.slice(3);
  if (year < 1n || year > 9999n || month < 1n || month > 12n || day < 1n || day > monthDays(year, month) ||
      hour > 23n || minute > 59n || second > 59n) throw new FormError('invalid_input');
  let days = yearDays(year) + day - 1n;
  for (let m = 1n; m < month; m++) days += monthDays(year, m);
  const value = {type: 'Date', ticks: String(days * DAY + (hour * 3600n + minute * 60n + second) * SECOND)};
  if (!dateFits(value, editor)) throw new FormError('invalid_input');
  return value;
}
function dateText(value, editor) {
  const ticks = BigInt(value.ticks);
  if (ticks === 0n) return ''; // Empty, year-one midnight and time zero share one BSL value.
  const pad = (value, size = 2) => String(value).padStart(size, '0');
  const seconds = ticks / SECOND % 86400n;
  const time = pad(seconds / 3600n) + ':' + pad(seconds / 60n % 60n) + ':' + pad(seconds % 60n);
  if (editor.parts === 'time') return time;
  let low = 1n, high = 10000n, days = ticks / DAY;
  while (low + 1n < high) { const middle = (low + high) / 2n; if (yearDays(middle) <= days) low = middle; else high = middle; }
  days -= yearDays(low); let month = 1n;
  while (days >= monthDays(low, month)) { days -= monthDays(low, month); month++; }
  const date = pad(low, 4) + '-' + pad(month) + '-' + pad(days + 1n);
  return editor.parts === 'date' ? date : date + 'T' + time;
}
function numberFits(value, editor) {
  const match = /^(-?)(\d+)(?:\.(\d+))?(?:E([+-]?\d+))?$/.exec(value);
  let digits = (match[2] + (match[3] || '')).replace(/^0+/, '');
  if (!digits) return true; // Signed zero does not violate Nonnegative.
  if (editor.nonnegative && match[1]) return false;
  if (!editor.digits) return true; // Unqualified Number, not an integer-only editor.
  let exponent = Number(match[4] || '0') - (match[3] || '').length;
  const trailing = digits.length - digits.replace(/0+$/, '').length;
  digits = digits.slice(0, digits.length - trailing); exponent += trailing;
  return exponent >= -editor.scale && digits.length + exponent <= editor.digits - editor.scale;
}
function validateEditor(editor, type, value) {
  const bounded = (value, max) => Number.isInteger(value) && value >= 0 && value <= max;
  const valid = type === 'Date' ? keys(editor, ['kind', 'parts']) && editor.kind === 'date' && ['dateTime', 'date', 'time'].includes(editor.parts)
    : type === 'Number' ? keys(editor, ['kind', 'digits', 'scale', 'nonnegative']) && editor.kind === 'number' &&
      bounded(editor.digits, 128) && bounded(editor.scale, editor.digits) && typeof editor.nonnegative === 'boolean'
    : type === 'String' ? keys(editor, ['kind', 'length', 'fixed']) && editor.kind === 'string' &&
      bounded(editor.length, 65536) && typeof editor.fixed === 'boolean' && (editor.length !== 0 || !editor.fixed) : false;
  if (!valid || value && value.type !== type) throw new FormError('transport');
  // Qualifiers describe the actual value, not a requested conversion. Do not
  // accept a descriptor that would hide nonzero components or change its type.
  if (value && (type === 'Date' && (editor.parts === 'date' && BigInt(value.ticks) % DAY !== 0n ||
        editor.parts === 'time' && BigInt(value.ticks) >= DAY) ||
      type === 'Number' && !numberFits(value.value, editor) ||
      type === 'String' && editor.length && (value.value.length > editor.length || editor.fixed && value.value.length !== editor.length)))
    throw new FormError('transport');
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
    case 'FormCatalogRef': case 'FormEnumRef':
      if (keys(value, ['type', 'scope', 'target', 'key', 'text']) &&
          typeof value.scope === 'string' && /^[0-9a-f]{32}$/.test(value.scope) &&
          Number.isInteger(value.target) && value.target >= 1 && value.target <= 128 &&
          (value.key === null || typeof value.key === 'string' && /^[0-9a-f]{32}$/.test(value.key)) &&
          validText(value.text, 4096) && [...value.text].length <= 1024) return value;
      break;
    case 'Date':
      if (keys(value, ['type', 'ticks']) && typeof value.ticks === 'string' && value.ticks.length <= 19 &&
          /^(?:0|[1-9][0-9]*)$/.test(value.ticks) && String(BigInt(value.ticks)) === value.ticks && BigInt(value.ticks) <= BigInt(LIMITS.dateTicks)) return value;
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
    const table = item?.kind === 'table', group = item?.kind === 'group';
    const shape = group ? ['name', 'kind', 'title', 'visible', 'enabled', 'readOnly', 'controlId', 'parent', 'layoutKind', 'orientation', 'showTitle'] : table ? ['name', 'kind', 'title', 'visible', 'enabled', 'readOnly', 'controlId', 'tableId', 'columns', 'rows', 'currentRow']
      : ['name', 'kind', 'title', 'visible', 'enabled', 'readOnly', 'view', 'value'];
    if (!group && record(item) && Object.hasOwn(item, 'parent')) shape.push('parent');
    if (item?.kind === 'field' && Object.hasOwn(item, 'editor')) shape.push('editor');
    if (item?.kind === 'field' && Object.hasOwn(item, 'controlId')) shape.push('controlId');
    if (!keys(item, shape) || !validText(item.name) || !item.name.length || names.has(item.name) ||
        !validText(item.title) || !['field', 'button', 'table', 'group'].includes(item.kind) ||
        ['visible', 'enabled', 'readOnly'].some(name => typeof item[name] !== 'boolean')) throw new FormError('transport');
    names.add(item.name);
    if (Object.hasOwn(item, 'controlId')) {
      if (!integer(item.controlId) || !item.controlId || item.controlId > LIMITS.controlIds || controlIds.has(item.controlId)) throw new FormError('transport');
      controlIds.add(item.controlId);
    }
    if (group) {
      if (!['group', 'pages', 'page'].includes(item.layoutKind) || !['vertical', 'horizontal'].includes(item.orientation) ||
          typeof item.showTitle !== 'boolean' || item.layoutKind === 'pages' && (item.orientation !== 'vertical' || !item.showTitle))
        throw new FormError('transport');
    } else if (table) {
      if (!integer(item.tableId) || !item.tableId || !Array.isArray(item.columns) || !item.columns.length ||
          item.columns.length > LIMITS.columns || !Array.isArray(item.rows) || item.rows.length > LIMITS.rows)
        throw new FormError('transport');
      const columns = new Set(), rows = new Set();
      for (const column of item.columns) {
        const shape = ['name', 'title', 'type', 'readOnly'];
        if (record(column) && Object.hasOwn(column, 'editor')) shape.push('editor');
        if (!keys(column, shape) || !validText(column.name) || !column.name.length ||
            columns.has(column.name) || !validText(column.title) || !['String', 'Number', 'Boolean', 'Date', 'FormCatalogRef', 'FormEnumRef'].includes(column.type) ||
            typeof column.readOnly !== 'boolean') throw new FormError('transport');
        if (Object.hasOwn(column, 'editor')) validateEditor(column.editor, column.type);
        columns.add(column.name);
      }
      for (const row of item.rows) {
        if (!keys(row, ['id', 'values']) || !integer(row.id) || !row.id || row.id > LIMITS.rowIds || rows.has(row.id) ||
            !Array.isArray(row.values) || row.values.length !== item.columns.length) throw new FormError('transport');
        rows.add(row.id);
        row.values.forEach((value, index) => {
          validateScalar(value);
          if (!['Null', 'Undefined', item.columns[index].type].includes(value.type)) throw new FormError('transport');
          if (Object.hasOwn(item.columns[index], 'editor')) validateEditor(item.columns[index].editor, item.columns[index].type, value);
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
        if (Object.hasOwn(item, 'editor')) validateEditor(item.editor, item.value.type, item.value);
        if (item.view === 'checkbox' && item.value.type !== 'Boolean') throw new FormError('transport');
      }
    }
  }
  const nested = state.items.some(item => item.kind === 'group');
  const ancestors = new Map(), depths = new Map(), pageCounts = new Map();
  for (const item of state.items) {
    if (!nested) { if (Object.hasOwn(item, 'parent')) throw new FormError('transport'); continue; }
    if (!Object.hasOwn(item, 'parent') || !validText(item.parent)) throw new FormError('transport');
    const parent = ancestors.get(item.parent);
    if (item.parent && (!parent || parent.kind !== 'group') ||
        (item.layoutKind === 'page') !== (parent?.layoutKind === 'pages')) throw new FormError('transport');
    if (parent && (!parent.visible && item.visible || !parent.enabled && item.enabled || parent.readOnly && !item.readOnly))
      throw new FormError('transport');
    const depth = (depths.get(item.parent) || 0) + 1;
    if (depth > 8) throw new FormError('transport');
    if (item.layoutKind === 'pages') pageCounts.set(item.name, 0);
    if (item.layoutKind === 'page') pageCounts.set(item.parent, pageCounts.get(item.parent) + 1);
    ancestors.set(item.name, item); depths.set(item.name, depth);
  }
  if ([...pageCounts.values()].some(count => count === 0)) throw new FormError('transport');
  if ((state.discardCommands || []).some(name => !state.items.some(item => item.name === name && item.kind === 'button')))
    throw new FormError('transport');
  if (new TextEncoder().encode(JSON.stringify(state)).length > LIMITS.bytes) throw new FormError('transport');
  return state;
}
function scalarText(value, editor) {
  validateScalar(value);
  if (['FormCatalogRef', 'FormEnumRef'].includes(value.type)) return value.text;
  if (value.type === 'Boolean') return value.value ? 'Yes' : 'No';
  if (value.type === 'Date') return editor?.kind === 'date' && dateFits(value, editor) ? dateText(value, editor) : value.ticks;
  if (value.type === 'Undefined') return 'Undefined';
  if (value.type === 'Null') return 'Null';
  return value.value;
}
function editable(item) {
  return item?.kind === 'field' && item.visible && item.enabled && !item.readOnly && item.view !== 'label' &&
    (['String', 'Number', 'Boolean'].includes(item.value.type) || item.value.type === 'Date' && item.editor?.kind === 'date' && dateFits(item.value, item.editor));
}
function inputHint(item) {
  const type = item.value.type, editor = item.editor;
  if (type === 'FormEnumRef') return 'Enumeration · choose a declared value; no text editing';
  if (type === 'FormCatalogRef') return 'Catalog reference · choose an existing record; no text editing';
  if (type === 'Date') {
    if (!editor || !dateFits(item.value, editor)) return 'Exact date ticks · read-only · no timezone conversion';
    return (editor.parts === 'date' ? 'YYYY-MM-DD' : editor.parts === 'time' ? 'HH:mm:ss' : 'YYYY-MM-DDTHH:mm:ss') +
      ' · whole seconds · blank = empty date · no timezone conversion' + (!editable(item) ? ' · Read-only' : '');
  }
  if (['Null', 'Undefined'].includes(type)) return 'Typed empty value · read-only';
  if (!editable(item)) return 'Read-only';
  if (type === 'Number') return 'Exact decimal · use a decimal point (.)' + (editor ?
    (editor.digits ? ' · ' + editor.digits + ' digits, ' + editor.scale + ' decimal places' : ' · unqualified precision') +
    (editor.nonnegative ? ' · nonnegative' : '') + ' · no rounding or clamping' : '');
  if (type === 'String' && editor?.length) return 'Up to ' + editor.length + ' UTF-16 units' +
    (editor.fixed ? ' · host pads with spaces' : '') + ' · no truncation';
  return type === 'Boolean' ? '' : 'Applied when you leave the field or run a command';
}
/** A bounded cell uses exactly the same scalar input rules as an ordinary field. */
function tableCell(item, rowId, columnName) {
  if (item?.kind !== 'table') return null;
  const index = item.columns.findIndex(column => column.name === columnName);
  const row = item.rows.find(row => row.id === rowId), column = item.columns[index];
  return !row || !column ? null : {kind: 'field', visible: item.visible, enabled: item.enabled,
    readOnly: item.readOnly || column.readOnly, view: 'input', value: row.values[index],
    ...(Object.hasOwn(column, 'editor') ? {editor: column.editor} : {})};
}
function typedInput(item, input) {
  if (!editable(item)) throw new FormError('unavailable');
  if (item.value.type === 'Boolean') {
    if (typeof input !== 'boolean') throw new FormError('invalid_input');
    return {type: 'Boolean', value: input};
  }
  if (item.value.type === 'Date') return dateInput(input, item.editor);
  if (item.value.type === 'Number') {
    const value = decimalText(input);
    if (item.editor && !numberFits(value, item.editor)) throw new FormError('invalid_input');
    return {type: 'Number', value};
  }
  if (!validText(input) || item.editor?.length && input.length > item.editor.length) throw new FormError('invalid_input');
  return {type: 'String', value: input};
}
function scalarEqual(left, right) {
  if (['FormCatalogRef', 'FormEnumRef'].includes(left?.type) || ['FormCatalogRef', 'FormEnumRef'].includes(right?.type))
    return Boolean(left && right && left.type === right.type && left.scope === right.scope &&
      left.target === right.target && left.key === right.key);
  return Boolean(left && right && left.type === right.type && left.value === right.value && left.ticks === right.ticks);
}
function validateEditValue(item, value) {
  validateScalar(value);
  if (value.type !== item.value.type || value.type === 'Date' && !dateFits(value, item.editor) ||
      value.type === 'Number' && item.editor && !numberFits(value.value, item.editor) ||
      value.type === 'String' && item.editor?.length && value.value.length > item.editor.length)
    throw new FormError('invalid_input');
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
        validateEditValue(item, values.value);
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
        validateEditValue(cell, values.value);
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

return {PROTOCOL, LIMITS, ERROR_MESSAGES, FormError, decimalText, validateScalar, validateSnapshot, scalarText, editable, inputHint, tableCell, typedInput, scalarEqual, FormClient, readBoundedJSON, createTransport, takeSessionCapability};
})();
const __attachment = (() => {
const {createTransport, readBoundedJSON} = __client;

const BROWSER_PROTOCOL = 'yadinassi-browser-attachment/1';
const RESUME_KEY = 'yadinassi.browser.resume/1';
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
class AttachmentRefusal extends Error {
  constructor(code) { super(messages[code] || messages.connection); this.name = 'AttachmentRefusal'; this.code = code; this.preDispatch = true; }
}
function documentInstance(environment = globalThis) {
  const bytes = new Uint8Array(16);
  (environment.crypto || globalThis.crypto).getRandomValues(bytes);
  return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
}
function readBrowserLaunch(environment) {
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
  if (['demo.hello','demo.snapshot'].includes(request.method))
    return objectKeys(request.params,['protocol']) && request.params.protocol === 'yadinassi-main-demo/1';
  if (request.method === 'demo.dispatch') {
    const params=request.params,nested=params?.request;
    if (!objectKeys(params,['epoch','request']) || typeof params.epoch !== 'string' || !/^[0-9a-f]{32}$/.test(params.epoch) ||
        !objectKeys(nested,['jsonrpc','id','method','params']) || nested.jsonrpc !== '2.0' || !Number.isSafeInteger(nested.id) || nested.id < 1) return false;
    if (['editor.hello','editor.snapshot','application.hello','application.snapshot'].includes(nested.method)) return true;
    return nested.method === 'application.form' && ['form.hello','form.snapshot'].includes(nested.params?.request?.method);
  }
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
class BrowserAttachment {
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
  async inspectDemo(callback) {
    if (typeof callback !== 'function' || this.demoInspection || this.busy || this.rpcActive || this.suspended || this.info?.closed || this.info?.role !== 'writer') throw new AttachmentRefusal('not_writer');
    const pin={attachment:this.info.attachment,generation:this.info.generation};
    const current=()=>this.info?.role==='writer'&&!this.info.closed&&!this.suspended&&this.info.attachment===pin.attachment&&this.info.generation===pin.generation;
    this.demoInspection={current,snapshot:null,epoch:null};
    try {
      const result=await callback();
      const observed=this.demoInspection.snapshot;
      if (!current()) throw new AttachmentRefusal('not_writer');
      if (objectKeys(result,['protocol','epoch','ready']) && result.protocol==='yadinassi-main-demo/1' && result.ready===true &&
          observed?.kind==='main-demo' && observed.uncertain===false && observed.epoch===result.epoch &&
          this.demoInspection.epoch===result.epoch && !this.rpcActive) {
        this.businessUnknown=false;this.paused=false;this.message='';
      }
      return result;
    } finally { this.demoInspection=null;this.changed(); }
  }
  async exchange(request) {
    if (this.demoInspection && (!this.demoInspection.current() || !['demo.hello','demo.snapshot','demo.dispatch'].includes(request.method) || !readOnlyRPC(request))) throw new AttachmentRefusal('not_writer');
    if (!this.demoInspection && !this.writable && !(this.reconciling && this.info?.role === 'writer' && !this.suspended && readOnlyRPC(request))) throw new AttachmentRefusal('not_writer');
    this.rpcActive++;
    try {
      const result = await this.post('/rpc', request, this.credential, {'X-Yadinassi-Attachment': this.info.attachment, 'X-Yadinassi-Generation': String(this.info.generation)});
      if (this.demoInspection) {
        if (!this.demoInspection.current()) throw new AttachmentRefusal('not_writer');
        const state=result?.result?.state;
        if (request.method==='demo.snapshot' && result?.result?.protocol==='yadinassi-main-demo/1' && result.result.error===null) this.demoInspection.snapshot=state;
        if (request.method==='demo.dispatch' && result?.result?.protocol==='yadinassi-main-demo/1' && result.result.error===null && state?.epoch===request.params.epoch &&
            objectKeys(result.result.payload,['jsonrpc','id','result']) && result.result.payload.jsonrpc==='2.0' && result.result.payload.id===request.params.request.id) this.demoInspection.epoch=state.epoch;
      }
      if (result?.result?.state?.kind === 'closed') { this.info = {...this.info, closed: true}; this.paused = true; this.stopHeartbeat(); this.changed(); }
      return result;
    } catch (error) {
      if (!(error instanceof AttachmentRefusal)) this.businessUnknown = true;
      this.fail(error); throw error;
    } finally { this.rpcActive--; }
  }
}
/** Shared ownership boundary. Legacy and test-injected exchanges remain separate. */
function createBrowserHost(environment, root) {
  const launch = readBrowserLaunch(environment);
  if (!launch.enabled) return {enabled: false, content: root, instance: documentInstance(environment),
    transport: createTransport(environment.fetch.bind(environment), launch.launcher), launcher: launch.launcher,
    start: async callback => { try { return await callback(); } catch { return false; } }, setPending() {}, setInspectionAllowed() {}, notify() {}};
  const document = environment.document, banner = document.createElement('section'), description = document.createElement('p'),
    detail = document.createElement('p'), actions = document.createElement('div'), takeover = document.createElement('button'),
    check = document.createElement('button'), content = document.createElement('div');
  banner.className = 'browser-ownership'; banner.setAttribute('aria-label', 'Browser tab ownership');
  description.setAttribute('role', 'status'); description.setAttribute('aria-live', 'polite');
  takeover.type = check.type = 'button'; takeover.textContent = 'Take control'; check.textContent = 'Check connection';
  actions.append(takeover, check); banner.append(description, detail, actions); root.replaceChildren(banner, content);
  let inspectionAllowed = () => false, inspectionWriter = null;
  const attachment = new BrowserAttachment(environment, launch, () => paint());
  function paint() {
    const writable = attachment.writable;
    if (writable) inspectionWriter = {attachment: attachment.info.attachment, generation: attachment.info.generation};
    else if (attachment.suspended || attachment.info?.role !== 'writer' || attachment.info?.closed ||
        attachment.info?.attachment !== inspectionWriter?.attachment || attachment.info?.generation !== inspectionWriter?.generation) inspectionWriter = null;
    // DOM inspection is not writer authority. Opt-in only after the consumer
    // has locked all business controls; the transport gate remains unchanged.
    let inspection = false;
    try {
      inspection = !writable && Boolean(inspectionWriter) && attachment.info?.role === 'writer' && !attachment.info.closed &&
        !attachment.suspended && !attachment.reconciling && !attachment.busy && !attachment.rpcActive &&
        (attachment.businessUnknown || attachment.uncertain()) && inspectionAllowed() === true;
    } catch { inspection = false; }
    content.inert = !(writable || inspection); content.setAttribute('aria-disabled', String(!(writable || inspection)));
    content.dataset.inspection = String(inspection);
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
  return {enabled: true, inspect:callback=>attachment.inspectDemo(callback), content, instance: attachment.instance, attachment, transport: request => attachment.exchange(request),
    setPending(pending, uncertain = () => false) { attachment.pending = pending; attachment.uncertain = uncertain; paint(); },
    setInspectionAllowed(predicate) { inspectionAllowed = typeof predicate === 'function' ? predicate : () => false; paint(); }, notify: paint,
    start(callback) { attachment.reconcile = callback; return attachment.attach(); }};
}

return {BROWSER_PROTOCOL, RESUME_KEY, AttachmentRefusal, documentInstance, readBrowserLaunch, BrowserAttachment, createBrowserHost};
})();
const __view = (() => {
const {FormError, editable, tableCell, scalarText, inputHint, typedInput, scalarEqual, LIMITS} = __client;

// DOM identity belongs to a retained view, never to a host control or table ID.
// BigInt keeps allocation monotonic without wrapping or reusing retired prefixes.
let viewSerial = 0n;

/** Keyed, text-only DOM renderer. The host can name controls but cannot supply HTML. */
function createFormView(document, root, handlers) {
  const idPrefix = 'form-view-' + ++viewSerial + '-';
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
  const recovered = element('section', 'notice warning'); recovered.setAttribute('aria-label', 'Unsubmitted inputs from earlier state'); recovered.hidden = true;
  const actions = element('div', 'form-actions');
  panel.append(panelHeader, empty, fields, messages, actions);
  const footer = element('footer', 'page-footer', 'Changes are handled by the host. Refresh reads state only and never repeats a command.');
  main.append(header, error, lock, recovered, panel, footer); root.replaceChildren(main);
  const controls = new Map(); const drafts = new Map(), cellDrafts = new Map(), recovery = new Map();
  const remember = (key, label, draft) => { if (draft) recovery.set(key, {label, value: draft.value}); };
  // Snapshot IDs fence replaced controls. Legacy snapshots without IDs still
  // bind to the exact visible type, editor and baseline, never just raw text.
  const binding = item => JSON.stringify([item.value.type, item.controlId ?? null, item.view,
    item.editor ? Object.keys(item.editor).sort().map(key => [key, item.editor[key]]) : null]);
  const draftFor = (item, value) => ({value, base: {...item.value}, binding: binding(item)});
  const matches = (item, draft) => editable(item) && draft.binding === binding(item) && scalarEqual(item.value, draft.base);
  let current = null, isBusy = false, focusMemory = null, actionPointer = false, lastModel = null;
  const pageSelections = new Map(), pageFocus = new Map();
  let serial = 0;
  const sameValue = (item, input) => item.value.type === 'Boolean' ? item.value.value === input : scalarText(item.value, item.editor) === input;
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
  const isDisplayed = item => {
    if (!item || !item.visible) return false;
    let node = item;
    while (node) {
      if (node.layoutKind === 'page' && pageSelections.get(node.parent)?.name !== node.name) return false;
      node = node.parent ? current?.items.find(item => item.name === node.parent) : null;
    }
    return true;
  };
  const available = target => {
    const item = current?.items.find(item => item.name === (typeof target === 'string' ? target : target?.control));
    return Boolean(item && item.kind !== 'group' && item.enabled && isDisplayed(item));
  };
  function reconcilePages() {
    const names = new Set();
    for (const item of current?.items || []) if (item.layoutKind === 'pages') {
      names.add(item.name);
      const pages = current.items.filter(page => page.layoutKind === 'page' && page.parent === item.name && page.visible);
      const old = pageSelections.get(item.name);
      const selected = old?.id === item.controlId && pages.find(page => page.name === old.name && page.enabled);
      const next = selected || pages.find(page => page.enabled) || pages[0];
      pageSelections.set(item.name, {id: item.controlId, name: next?.name || null});
    }
    for (const name of pageSelections.keys()) if (!names.has(name)) pageSelections.delete(name);
    for (const [name, saved] of pageFocus) if (!current?.items.some(item => item.name === name && item.controlId === saved.id)) pageFocus.delete(name);
  }
  function selectPage(name, keyboard = false) {
    const page = controls.get(name), pages = controls.get(page?.item.parent);
    if (!page?.tab || page.tab.disabled || isBusy || !isDisplayed(pages?.item)) return;
    const old = pageSelections.get(pages.item.name)?.name;
    if (old === name) return;
    const previous = controls.get(old), saved = captureFocus();
    if (previous?.row.contains(saved?.node)) pageFocus.set(old, {...saved, id: previous.item.controlId});
    pageSelections.set(pages.item.name, {id: pages.item.controlId, name});
    render(lastModel);
    page.tab.focus({preventScroll: true});
    const remembered = pageFocus.get(name);
    if (!keyboard && remembered && page.row.contains(remembered.node) && !remembered.node.disabled) {
      remembered.node.focus({preventScroll: true});
      restoreFocus(remembered);
    }
  }
  function makeGroup(item) {
    const row = element('section', 'layout-group'), heading = element('h2', 'group-title'), content = element('div', 'group-content');
    row.id = idPrefix + 'group-' + ++serial;
    heading.id = row.id + '-title'; row.setAttribute('aria-labelledby', heading.id);
    row.append(heading);
    const result = {row, heading, content, item};
    if (item.layoutKind === 'pages') {
      result.tabbar = element('div', 'page-tabs'); result.tabbar.setAttribute('role', 'tablist'); row.append(result.tabbar);
    }
    if (item.layoutKind === 'page') {
      result.tab = element('button', 'page-tab'); result.tab.type = 'button'; result.tab.dataset.formAction = 'page';
      result.tab.id = row.id + '-tab'; result.tab.setAttribute('role', 'tab'); result.tab.setAttribute('aria-controls', row.id);
      row.setAttribute('role', 'tabpanel'); row.setAttribute('aria-labelledby', result.tab.id);
      result.tab.addEventListener('pointerdown', event => {
        // Keep the current editor/selection until the local page switch owns it.
        event.preventDefault();
      });
      result.tab.addEventListener('click', () => { if (controls.get(item.name) === result) selectPage(item.name); });
      result.tab.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || result.tab.disabled) return;
        const tabs = [...controls.values()].filter(control => control.item.parent === item.parent && control.tab && !control.tab.hidden && !control.tab.disabled);
        const index = tabs.indexOf(result);
        if (index < 0 || !tabs.length) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        selectPage(tabs[next].item.name, true); tabs[next].tab.focus({preventScroll: true});
      });
    }
    row.append(content); return result;
  }
  function renderGroup(control, model, active) {
    const item = control.item;
    control.row.className = 'layout-group layout-' + item.layoutKind;
    control.content.className = 'group-content orientation-' + item.orientation;
    control.heading.textContent = item.title || item.name;
    control.heading.hidden = !item.showTitle || item.layoutKind === 'page';
    if (control.tabbar) control.tabbar.setAttribute('aria-label', item.title || item.name);
    if (control.tab) {
      const parent = controls.get(item.parent);
      const selected = pageSelections.get(item.parent)?.name === item.name;
      control.tab.textContent = item.title || item.name; control.tab.hidden = !item.visible;
      control.tab.setAttribute('aria-selected', String(selected)); control.tab.tabIndex = selected ? 0 : -1;
      control.tab.disabled = model.paused || model.busy || !active || !item.enabled || !isDisplayed(parent?.item);
      const index = current.items.filter(page => page.parent === item.parent && page.layoutKind === 'page').findIndex(page => page.name === item.name);
      if (parent.tabbar.children[index] !== control.tab) parent.tabbar.insertBefore(control.tab, parent.tabbar.children[index] || null);
      control.row.hidden = !selected || !item.visible || current.kind === 'closed';
    }
  }
  function referenceActions(parent, locator) {
    if (!handlers.reference) return null;
    const group = element('span', 'reference-actions');
    const choose = element('button', 'quiet', 'Choose'), clear = element('button', 'quiet', 'Clear');
    for (const [node, action] of [[choose, 'begin'], [clear, 'clear']]) {
      node.type = 'button'; node.dataset.formAction = 'reference';
      node.addEventListener('click', () => { if (!node.disabled) handlers.reference({action, ...locator}); });
    }
    group.append(choose, clear); parent.append(group); return {group, choose, clear};
  }
  function paintReference(actions, field, label, disabled) {
    if (!actions) return;
    const reference = ['FormCatalogRef', 'FormEnumRef'].includes(field?.value?.type); actions.group.hidden = !reference;
    const unavailable = disabled || !reference || !field.visible || !field.enabled || field.readOnly || field.view === 'label';
    actions.choose.disabled = unavailable; actions.clear.disabled = unavailable || field.value.key === null;
    actions.choose.setAttribute('aria-label', 'Choose ' + label); actions.clear.setAttribute('aria-label', 'Clear ' + label);
  }
  function makeControl(item) {
    const row = element(item.kind === 'button' || ['FormCatalogRef', 'FormEnumRef'].includes(item.value?.type) ? 'div' : 'label', item.kind === 'button' ? 'command' : 'field');
    const caption = element('span', 'field-title');
    const input = element(item.kind === 'button' ? 'button' : 'input');
    const hint = element('small', 'field-hint');
    const id = idPrefix + 'control-' + ++serial;
    input.id = id;
    if (item.kind === 'button') {
      input.type = 'button'; input.dataset.formAction = 'command'; input.className = 'primary';
      input.addEventListener('click', () => { if (controls.get(item.name)?.input === input && !input.disabled && available(item.name)) handlers.action('command', item.name); });
      row.append(input);
    } else {
      row.htmlFor = id; hint.id = id + '-hint'; input.setAttribute('aria-describedby', hint.id);
      input.type = item.value.type === 'Boolean' ? 'checkbox' : 'text';
      // A checkbox activation, including its label, owns the preceding blur.
      // Its change intent flushes all pending fields before applying the toggle.
      if (input.type === 'checkbox') row.dataset.formAction = input.dataset.formAction = 'toggle';
      input.autocomplete = 'off'; input.spellcheck = false;
      const live = () => controls.get(item.name)?.input === input && available(item.name);
      input.addEventListener('input', () => {
        const active = controls.get(item.name)?.item;
        if (!live() || isBusy || recovery.size || !editable(active)) return;
        const value = input.type === 'checkbox' ? input.checked : input.value;
        if (sameValue(active, value)) drafts.delete(item.name);
        else drafts.set(item.name, draftFor(active, value));
      });
      input.addEventListener('change', () => {
        if (live() && input.type === 'checkbox' && !isBusy && editable(controls.get(item.name)?.item)) handlers.action('toggle', item.name);
      });
      input.addEventListener('blur', event => {
        // Commands and checkbox activations own their serialized flush path.
        if (live() && input.type !== 'checkbox' && !isBusy && !actionPointer &&
            !event.relatedTarget?.closest('[data-form-action]')) handlers.change(item.name);
      });
      input.addEventListener('keydown', event => {
        if (live() && event.key === 'Enter' && !event.isComposing && input.type !== 'checkbox') {
          event.preventDefault(); handlers.change(item.name);
        }
      });
      row.append(caption, input, hint);
    }
    const reference = ['FormCatalogRef', 'FormEnumRef'].includes(item.value?.type) ? referenceActions(row, {control: item.name, row: null, column: null}) : null;
    return {row, caption, input, hint, item, reference};
  }
  const cellKey = (control, controlId, tableId, row, column) => JSON.stringify([control, controlId, tableId, row, column]);
  function discardTable(name) {
    for (const [key, draft] of cellDrafts) if (draft.control === name) { remember(key, name + ', row ' + draft.row + ', ' + draft.column, draft); cellDrafts.delete(key); }
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
    help.id = idPrefix + 'table-help-' + ++serial;
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
    input.id = idPrefix + 'cell-' + ++serial; input.autocomplete = 'off'; input.spellcheck = false;
    const name = control.item.name, controlId = control.item.controlId, tableId = control.item.tableId;
    const locator = {control: name, row: rowId, column: column.name};
    const key = cellKey(name, controlId, tableId, rowId, column.name);
    const currentCell = () => tableCell(controls.get(name)?.item, rowId, column.name);
    const live = () => available(name) && controls.get(name)?.item.tableId === tableId && controls.get(name)?.item.controlId === controlId &&
      controls.get(name)?.rows.get(rowId)?.cells.get(column.name)?.input === input;
    input.addEventListener('input', () => {
      const active = currentCell();
      if (!live() || isBusy || recovery.size || !editable(active)) return;
      const value = input.type === 'checkbox' ? input.checked : input.value;
      if (sameValue(active, value)) cellDrafts.delete(key);
      else cellDrafts.set(key, {...locator, controlId, tableId, ...draftFor(active, value)});
    });
    input.addEventListener('change', () => {
      if (live() && input.type === 'checkbox' && !isBusy && editable(currentCell())) handlers.action('toggle', locator);
    });
    input.addEventListener('blur', event => {
      if (live() && input.type !== 'checkbox' && !isBusy && !actionPointer &&
          !event.relatedTarget?.closest('[data-form-action]')) handlers.change(locator);
    });
    input.addEventListener('keydown', event => {
      if (live() && event.key === 'Enter' && !event.isComposing && input.type !== 'checkbox') {
        event.preventDefault(); handlers.change(locator);
      }
    });
    const reference = ['FormCatalogRef', 'FormEnumRef'].includes(column.type) ? referenceActions(cell, locator) : null;
    return {cell, input, type: column.type, key, reference};
  }
  function renderTable(control, model, active) {
    const item = control.item;
    const disabled = recovery.size > 0 || model.paused || model.busy || model.locked || !active || !item.enabled || !item.visible;
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
        paintReference(cell.reference, field, (column.title || column.name) + ', row ' + data.id, disabled);
        input.type = value.type === 'Boolean' ? 'checkbox' : 'text';
        if (input.type === 'checkbox') input.dataset.formAction = 'toggle';
        else delete input.dataset.formAction;
        input.className = 'cell-input' + (value.type === 'Number' ? ' decimal-cell' : '');
        input.disabled = disabled || input.type === 'checkbox' && readOnly; input.readOnly = readOnly;
        input.setAttribute('aria-label', (column.title || column.name) + ', row ' + data.id);
        input.setAttribute('aria-describedby', control.help.id);
        input.setAttribute('aria-readonly', readOnly ? 'true' : 'false');
        input.title = inputHint(field);
        const draft = cellDrafts.get(cell.key), text = draft ? draft.value : value.type === 'Boolean' ? value.value : scalarText(value, field.editor);
        if (input.type === 'checkbox') input.checked = text === true;
        else if (input.value !== text) input.value = text;
        input.maxLength = value.type === 'Number' ? 144 : LIMITS.text;
        input.inputMode = value.type === 'Number' ? 'decimal' : 'text';
      });
    });
  }
  function reconcileDrafts() {
    for (const [name, draft] of drafts) {
      const item = current?.items.find(item => item.name === name);
      if (!matches(item, draft)) { remember('field:' + name, name, draft); drafts.delete(name); }
    }
    for (const [key, draft] of cellDrafts) {
      const item = current?.items.find(item => item.name === draft.control);
      const cell = tableCell(item, draft.row, draft.column);
      if (item?.tableId !== draft.tableId || item?.controlId !== draft.controlId || !matches(cell, draft)) {
        remember(key, draft.control + ', row ' + draft.row + ', ' + draft.column, draft); cellDrafts.delete(key);
      }
    }
  }
  function render(model) {
    lastModel = model;
    const savedFocus = captureFocus();
    if (model.busy && !isBusy) focusMemory = savedFocus;
    const wasBusy = isBusy; isBusy = model.busy; current = model.snapshot;
    reconcilePages(); reconcileDrafts();
    const active = current?.kind === 'form' && current.lifecycle === 'open';
    title.textContent = current?.title || 'Local form'; document.title = title.textContent + ' · Yadinassi';
    panel.setAttribute('aria-busy', model.busy ? 'true' : 'false');
    status.textContent = model.busy ? 'Working…' : !current ? 'Not connected' : current.uncertain || model.outcomeUnknown ? 'Outcome unknown'
      : model.transportFailed ? 'Connection lost' : model.paused ? 'Paused' : model.locked && current.lifecycle === 'open' ? 'Locked'
      : current.lifecycle === 'open' ? 'Connected' : current.lifecycle === 'cancelled' ? 'Cancelled'
      : current.lifecycle === 'failed' ? 'Failed' : 'Closed';
    status.className = 'badge ' + (current?.uncertain || model.outcomeUnknown ? 'unsafe' : active ? 'connected' : '');
    revision.textContent = current ? 'Revision ' + current.revision : 'Local session';
    refresh.disabled = model.paused || model.busy || !model.connected || model.exhausted || Boolean(model.refreshUnavailable);
    close.disabled = recovery.size > 0 || model.paused || model.busy || model.locked || !active;
    close.hidden = !current || current.kind === 'closed';
    error.textContent = model.error || ''; error.hidden = !model.error;
    lock.hidden = !(model.outcomeUnknown || current?.uncertain || model.transportFailed);
    lock.textContent = model.outcomeUnknown || current?.uncertain
      ? model.refreshUnavailable ? 'The outcome is unknown and this session is locked. Copy pending edits before leaving. Refresh and replay are unavailable.'
        : 'This session is locked because the host cannot determine the outcome. Refresh can inspect state but cannot unlock or repeat the action.'
      : model.refreshUnavailable ? 'Editing is locked and refresh is unavailable. Copy pending edits before leaving. No command will be retried.'
      : 'Editing is locked. Use Refresh state to read the host’s result before continuing. No command will be retried.';
    empty.hidden = Boolean(current && current.kind !== 'closed' && current.items.some(item => item.visible));
    empty.textContent = !current ? (model.busy ? 'Connecting to the local host…' : 'Open the complete launch URL to attach to a form.')
      : current.kind === 'closed' ? 'This form is ' + current.lifecycle + '. You can close this tab.' : 'No visible controls.';
    const names = new Set((current?.items || []).map(item => item.name));
    for (const [name, control] of controls) if (!names.has(name)) { remember('field:' + name, name, drafts.get(name)); control.row.remove(); control.tab?.remove(); controls.delete(name); drafts.delete(name); discardTable(name); }
    const nested = current?.items.some(item => item.kind === 'group');
    fields.className = 'fields' + (nested ? ' nested-layout' : '');
    const positions = new Map();
    for (const item of current?.items || []) {
      let control = controls.get(item.name);
      if (control && (control.item.kind !== item.kind || control.item.layoutKind !== item.layoutKind || control.item.value?.type !== item.value?.type || control.item.tableId !== item.tableId || control.item.controlId !== item.controlId)) {
        remember('field:' + item.name, item.name, drafts.get(item.name)); control.row.remove(); control.tab?.remove(); controls.delete(item.name); drafts.delete(item.name); discardTable(item.name); control = null;
      }
      if (!control) { control = item.kind === 'group' ? makeGroup(item) : item.kind === 'table' ? makeTable(item) : makeControl(item); controls.set(item.name, control); }
      control.item = item;
      const {row, caption, input, hint} = control;
      const parent = item.parent ? controls.get(item.parent).content : !nested && item.kind === 'button' ? actions : fields;
      const position = positions.get(parent) || 0; positions.set(parent, position + 1);
      if (parent.children[position] !== row) parent.insertBefore(row, parent.children[position] || null);
      row.hidden = !item.visible || current.kind === 'closed';
      if (item.kind === 'group') { renderGroup(control, model, active); continue; }
      if (item.kind === 'table') { renderTable(control, model, active); continue; }
      const readOnly = item.kind === 'field' && !editable(item);
      if (readOnly) { remember('field:' + item.name, item.name, drafts.get(item.name)); drafts.delete(item.name); }
      paintReference(control.reference, item, item.title || item.name, recovery.size > 0 || model.paused || model.busy || model.locked || !active);
      input.disabled = model.paused || (recovery.size > 0 && (item.kind !== 'button' || !current.discardCommands?.includes(item.name))) || model.busy || model.locked || !active || !item.enabled || !item.visible ||
        (item.kind === 'button' && item.readOnly) || (input.type === 'checkbox' && readOnly);
      input.readOnly = readOnly;
      if (item.kind === 'button') input.textContent = item.title || item.name;
      else {
        caption.textContent = item.title || item.name;
        input.setAttribute('aria-label', caption.textContent);
        row.className = 'field' + (item.value.type === 'Boolean' ? ' checkbox-field' : '') + (readOnly ? ' read-only' : '');
        const draft = drafts.get(item.name);
        const value = draft ? draft.value : item.value.type === 'Boolean' ? item.value.value : scalarText(item.value, item.editor);
        if (input.type === 'checkbox') input.checked = value === true;
        else if (input.value !== value) input.value = value;
        input.maxLength = item.value.type === 'Number' ? 144 : LIMITS.text;
        input.inputMode = item.value.type === 'Number' ? 'decimal' : 'text';
        hint.textContent = inputHint(item);
        hint.hidden = !hint.textContent;
      }
    }
    // A locked transport never authorizes a send. Local page inspection and
    // selectable raw-text recovery still work, without clearing any draft/lock.
    const lockedDrafts = model.locked && !model.busy ? [
      ...Array.from(drafts, ([name, draft]) => ({label: name, value: draft.value})),
      ...Array.from(cellDrafts.values(), draft => ({label: draft.control + ', row ' + draft.row + ', ' + draft.column, value: draft.value})),
    ] : [];
    recovered.hidden = recovery.size === 0 && lockedDrafts.length === 0;
    recovered.replaceChildren(element('p', '', recovery.size
      ? 'These inputs no longer match the host state and were not applied. Copy any text you need, then use Refresh state to discard them and continue.'
      : 'These unsubmitted inputs are retained while editing is locked. Copy any text you need before Refresh state discards them. Switching pages does not send or retry anything.'),
      ...[...recovery.values(), ...lockedDrafts].map(draft => element('p', 'draft-recovery-value', draft.label + ': ' + String(draft.value))));
    const nextMessages = current?.messages || [];
    // Rebuild only the bounded message list, never input nodes or host-supplied markup.
    messages.replaceChildren(...nextMessages.map(message => element('p', '', message)));
    messages.hidden = !nextMessages.length;
    actions.hidden = nested || !current || current.kind === 'closed' || !current.items.some(item => item.kind === 'button' && item.visible);
    if (!model.busy) { restoreFocus(wasBusy ? focusMemory : savedFocus); focusMemory = null; }
  }
  return {
    render,
    isAvailable: available,
    focusReference(locator) {
      const control = controls.get(locator.control);
      const target = locator.row === null ? control?.reference?.choose : control?.rows?.get(locator.row)?.cells.get(locator.column)?.reference?.choose;
      if (!target || target.disabled || target.closest('[hidden]')) return false;
      target.focus({preventScroll: true}); return true;
    },
    accept(change) {
      if (typeof change === 'string') drafts.delete(change);
      else if (!Object.hasOwn(change, 'row')) drafts.delete(change.control);
      else {
        const item = current?.items.find(item => item.name === change.control);
        cellDrafts.delete(cellKey(change.control, item?.controlId, item?.tableId, change.row, change.column));
      }
    },
    recover(change) {
      if (!Object.hasOwn(change, 'row')) {
        remember('field:' + change.control, change.control, drafts.get(change.control)); drafts.delete(change.control);
      } else {
        const item = current?.items.find(item => item.name === change.control);
        const key = cellKey(change.control, item?.controlId, item?.tableId, change.row, change.column);
        remember(key, change.control + ', row ' + change.row + ', ' + change.column, cellDrafts.get(key)); cellDrafts.delete(key);
      }
    },
    // Kept for the attachment host's existing lifecycle API. Reconciliation
    // protects raw inputs on every authoritative update, not only takeovers.
    beginOwnershipReconcile() {},
    endOwnershipReconcile() {},
    clearDrafts() { drafts.clear(); cellDrafts.clear(); recovery.clear(); },
    hasDrafts() { return drafts.size + cellDrafts.size + recovery.size > 0; },
    changes(only) {
      if (recovery.size) throw new FormError('draft_changed');
      const changes = [];
      if (only !== undefined && !available(only)) return changes;
      if (only === undefined && ([...drafts.keys()].some(name => !available(name)) ||
          [...cellDrafts.values()].some(draft => !available(draft.control)))) throw new FormError('draft_hidden');
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
const {FormClient, FormError, tableCell, scalarEqual, createTransport, takeSessionCapability} = __client;
const {createFormView} = __view;
const {createBrowserHost, AttachmentRefusal} = __attachment;

/** Serialize UI intents before the first await, including blur followed by a command. */
function mountForm(environment, root, options = {}) {
  const browserHost = options.transport ? null : createBrowserHost(environment, root);
  root = browserHost?.content || root;
  let client = null, token = browserHost?.launcher || null, queuedToken = null, busy = false, error = '';
  const view = createFormView(environment.document, root, {
    reference: options.onReference ? action => run('reference', action) : null,
    change: name => run('change', name), select: (name, row) => run('select', name, row), action: (event, name) => run(event, name), refresh: () => refresh(),
  });
  const paint = () => view.render({paused: Boolean(options.referenceActive?.() || options.businessBlocked?.()), snapshot: client?.snapshot || null, busy, error, connected: Boolean(token),
    locked: client?.locked ?? true, outcomeUnknown: client?.outcomeUnknown || false,
    transportFailed: client?.transportFailed || false, exhausted: client?.exhausted || false,
    refreshUnavailable: Boolean(options.transport && client?.transportFailed)});
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
    let accepted = false;
    try { await client.event(Object.hasOwn(change, 'row') ? 'cell' : 'change', change); accepted = true; }
    catch (caught) {
      // event_failed can mean assignment failed before OnChange (e.g. an
      // aggregate budget). Only consume a visibly completed target change.
      if (caught?.code === 'event_failed' && client.snapshot !== before && !client.transportFailed) {
        const oldItem = before.items.find(item => item.name === change.control);
        const newItem = client.snapshot.items.find(item => item.name === change.control);
        const oldField = Object.hasOwn(change, 'row') ? tableCell(oldItem, change.row, change.column) : oldItem;
        const newField = Object.hasOwn(change, 'row') ? tableCell(newItem, change.row, change.column) : newItem;
        accepted = Boolean(newField && oldItem.controlId === newItem.controlId && oldItem.tableId === newItem.tableId &&
          !scalarEqual(newField.value, oldField.value));
        if (!accepted) view.recover(change);
      }
      throw caught;
    }
    finally {
      if (accepted && client.snapshot !== before && !client.transportFailed) view.accept(change);
      paint();
    }
  }
  function referenceTarget(action) {
    const item = client.snapshot.items.find(item => item.name === action.control);
    const field = action.row === null && action.column === null ? item : tableCell(item, action.row, action.column);
    if (!field || field.kind !== 'field' || !field.visible || !field.enabled || field.readOnly || field.view === 'label' ||
        !['FormCatalogRef', 'FormEnumRef'].includes(field.value.type)) throw new FormError('unavailable');
    return {value: field.value, controlId: item.controlId, tableId: item.tableId};
  }
  async function run(event, name, row) {
    if (['change', 'toggle'].includes(event) && options.isActive && !options.isActive()) return;
    if (busy || !client || client.locked || options.businessBlocked?.() || options.referenceActive?.() && event !== 'reference') return;
    const reference = event === 'reference';
    if (reference && !options.onReference) return;
    const referenceStart = reference && ['begin', 'clear'].includes(name?.action);
    if ((['change', 'toggle', 'command', 'select'].includes(event) || referenceStart) && !view.isAvailable(name)) return;
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
    if (['change', 'toggle'].includes(event) && !changes.length) { paint(); return; }
    busy = true; error = ''; paint();
    try {
      for (const change of changes) {
        if (options.businessBlocked?.()) throw new FormError('owned_child_open');
        // An earlier handler may delete, retype or supersede a later draft. Do not
        // retarget it or run a command that silently lost part of the user's edit.
        const locator = Object.hasOwn(change, 'row') ? change : change.control;
        const pending = view.changes(locator);
        if (!pending.some(value => JSON.stringify(value) === JSON.stringify(change))) throw new FormError('draft_changed');
        await sendChange(change);
      }
      if (options.businessBlocked?.()) throw new FormError('owned_child_open');
      if ((['command', 'select'].includes(event) || referenceStart) && !view.isAvailable(name)) throw new FormError('draft_changed');
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
  async function recoverReadOnly() {
    if(busy||!client||client.outcomeUnknown||client.snapshot?.uncertain)throw new FormError('transport');
    busy=true;view.beginOwnershipReconcile();paint();
    try { return await (client.snapshot?client.resync():client.hello()); }
    finally { finish();view.endOwnershipReconcile(); }
  }
  async function refresh() {
    if (busy || !client || options.businessBlocked?.() || options.referenceActive?.() || options.transport && client.transportFailed) return;
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
  // A completion is an already executed trusted host event, not a second browser
  // request. Preserve raw drafts/recovery and consume only its exact snapshot.
  const adoptExternal = reply => {
    if (!client || busy || client.busy || client.locked) throw new FormError('transport');
    error = '';
    try { client.adopt(reply,1); }
    catch (caught) {
      showError(caught);
      if (client.transportFailed || client.outcomeUnknown) throw caught;
    }
    paint();
  };
  paint();
  if (browserHost?.enabled) {
    client = new FormClient(browserHost.transport); token = 'attached';
    browserHost.setPending(hasPending, () => Boolean(client.transportFailed || client.outcomeUnknown || client.snapshot?.uncertain));
    browserHost.setInspectionAllowed(() => Boolean(client.locked && !busy && !client.busy && !options.referenceActive?.() &&
      client.snapshot?.items.some(item => item.kind === 'group')));
  }
  const ready = options.transport ? connect('embedded') : browserHost.enabled ? browserHost.start(reconcileOwnership) : token ? connect(token) : reattach();
  return {ready, refresh, reconcileOwnership, recoverReadOnly, adoptExternal, run, repaint: paint, reference: action => run('reference', action), reattach, hasPending, lock, browserHost, get client() { return client; }, view};
}

if (typeof window !== 'undefined' && window.document?.getElementById('app')) {
  mountForm(window, window.document.getElementById('app'));
}

return {mountForm};
})();

/* Embedded form renderer is the reviewed shared __app module, bundled below. */
'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('session');
history.replaceState(null, '', location.pathname);
const root=document.getElementById('workspace'), title=document.createElement('h1'), status=document.createElement('p'), select=document.createElement('select'), open=document.createElement('button'), close=document.createElement('button'), formRoot=document.createElement('section');
const search=document.createElement('input'), find=document.createElement('button');search.maxLength=128;search.setAttribute('aria-label','Поиск объявленных форм');find.textContent='Найти формы';
select.setAttribute('aria-label','Объявленная форма'); open.textContent='Открыть форму'; close.textContent='Закрыть сеанс'; status.setAttribute('role','status');
const limitations=document.createElement('ul');limitations.setAttribute('aria-label','Неподдерживаемые возможности формы');
const tabs=document.createElement('nav');tabs.setAttribute('aria-label','Открытые формы');
const explorer=document.createElement('section'),explorerTitle=document.createElement('h2');explorerTitle.textContent='Объекты конфигурации';
const objectSearch=document.createElement('input'),families=document.createElement('select'),objects=document.createElement('select'),objectFind=document.createElement('button'),inspect=document.createElement('button'),detail=document.createElement('section'),inventoryStatus=document.createElement('p');
objectSearch.maxLength=128;objectSearch.setAttribute('aria-label','Поиск объектов');families.setAttribute('aria-label','Тип объекта');objects.setAttribute('aria-label','Объект конфигурации');
objectFind.textContent='Найти объекты';inspect.textContent='Описание объекта';detail.setAttribute('aria-label','Метаданные выбранного объекта');inventoryStatus.setAttribute('role','status');
explorer.append(explorerTitle,objectSearch,families,objectFind,objects,inspect,inventoryStatus,detail);
root.append(title,status,explorer,search,find,select,open,close,tabs,limitations,formRoot);
let id=0,busy=false,view=null,state=null,failed=false,inFlight=0;
const mounts=new Map();
async function call(method,params={}) {
  const response=await fetch('/rpc',{method:'POST',headers:{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':token||''},body:JSON.stringify({jsonrpc:'2.0',id:++id,method,params})+'\n'});
  if(!response.ok)throw Error('Связь потеряна. Команда не повторяется автоматически.');
  const reply=await response.json();if(reply.error)throw Error('Запрос отклонён');return reply.result;
}
function paint(){
  if([...mounts.values()].some(entry=>entry.view.client?.transportFailed||entry.view.client?.outcomeUnknown||entry.view.client?.snapshot?.uncertain)){
    failed=true;status.textContent='Результат действия неизвестен. Формы и черновики сохранены в этой вкладке; переключение и повтор команд заблокированы.';
  }
  const blocked=busy||failed||inFlight>0||!state||state.kind==='closed';
  open.disabled=blocked||!select.value;
  search.disabled=find.disabled=select.disabled=Boolean(blocked);
  close.disabled=blocked||[...mounts.values()].some(entry=>entry.view.client?.snapshot?.kind!=='closed');
  for(const button of tabs.children)button.disabled=Boolean(blocked);
  for(const control of [objectSearch,families,objects,objectFind,inspect,...detail.querySelectorAll('button')])control.disabled=Boolean(blocked);
  inspect.disabled=Boolean(blocked)||!objects.value;
  for(const entry of mounts.values())entry.view.repaint();
}
async function formCall(generation,request){
  if(failed||generation!==state?.generation)throw Error('Неактивная форма');
  inFlight++;paint();
  try{return await call('workspace.form',{generation,request});}
  finally{inFlight--;paint();}
}
async function apply(reply){
  if(reply.protocol!=='yadinassi-source-workspace/1')throw Error('Неизвестный протокол');state=reply.state;
  title.textContent=state.name+' · Source workspace';status.textContent=state.error|| (state.kind==='closed'?'Сеанс закрыт':'Формы в памяти: без сохранения объектов базы и без заявления о совместимости с 1С.');
  const previous=select.value;select.replaceChildren();
  for(const name of state.forms){const option=document.createElement('option');option.value=name;option.textContent=name;select.append(option);}
  if(state.forms.includes(previous))select.value=previous;
  if(state.omitted_forms)status.textContent+=' Ещё '+state.omitted_forms+' форм: уточните поиск.';
  limitations.replaceChildren();for(const diagnostic of state.form_diagnostics||[]){const item=document.createElement('li');item.textContent=diagnostic.path+': '+diagnostic.reason;limitations.append(item);}
  const previousObject=objects.value;objects.replaceChildren();
  for(const name of state.objects||[]){const option=document.createElement('option');option.value=option.textContent=name;objects.append(option);}
  if((state.objects||[]).includes(previousObject))objects.value=previousObject;
  families.replaceChildren();for(const family of ['',...(state.object_families||[])]){const option=document.createElement('option');option.value=family;option.textContent=family||'Все типы';families.append(option);}families.value=state.object_family||'';
  inventoryStatus.textContent='Показано объектов: '+(state.objects||[]).length+(state.omitted_objects?'; ещё '+state.omitted_objects+', уточните поиск.':'.');
  if(state.omitted_families)inventoryStatus.textContent+=' Других типов: '+state.omitted_families+'. Используйте поиск по полному имени.';
  detail.replaceChildren();
  if(state.object_detail){
    const data=state.object_detail,heading=document.createElement('h3'),path=document.createElement('p'),notice=document.createElement('p');
    heading.textContent=data.name;path.textContent='XML: '+data.source_path;
    notice.textContent=data.execution==='metadata_only'?'Только метаданные: объявленной исполняемой формы нет. CRUD и хранилище не предоставляются.':'Объявленные формы открываются явно и могут выдавать ошибки неподдерживаемых возможностей. CRUD и хранилище не предоставляются.';
    detail.append(heading,path,notice);
    for(const name of data.forms){const button=document.createElement('button');button.textContent='Открыть '+name;button.addEventListener('click',()=>action('workspace.open',{name}));detail.append(button);}
    if(data.omitted_forms){const note=document.createElement('p');note.textContent='Ещё форм: '+data.omitted_forms+'. Уточните общий поиск форм.';detail.append(note);}
  }
  const entries=state.open_forms||[];
  for(const [generation,entry] of mounts){
    if(!entries.some(item=>item.generation===generation)){entry.panel.remove();mounts.delete(generation);}
  }
  tabs.replaceChildren();
  for(const item of entries){
    const button=document.createElement('button');button.textContent=item.name+(item.active?'':' (закрыта)');
    button.setAttribute('aria-current',item.generation===state.generation?'page':'false');
    button.addEventListener('click',()=>action('workspace.select',{generation:item.generation}));tabs.append(button);
  }
  if(state.active && !mounts.has(state.generation)){
    const generation=state.generation,panel=document.createElement('section');formRoot.append(panel);
    const mount=__app.mountForm(window,panel,{transport:request=>formCall(generation,request),
      isActive:()=>state?.generation===generation,
      businessBlocked:()=>busy||failed||state?.generation!==generation,
      onChange:()=>paint()});
    mounts.set(generation,{panel,view:mount});await mount.ready;
  }
  view=mounts.get(state.generation)?.view||null;
  for(const [generation,entry] of mounts)entry.panel.hidden=generation!==state.generation;
  paint();
}
async function action(method,params){if(busy||failed||inFlight)return;busy=true;paint();try{await apply(await call(method,params));}catch(error){failed=true;status.textContent=error.message;}finally{busy=false;paint();}}
objectFind.addEventListener('click',()=>action('workspace.objects',{query:objectSearch.value,family:families.value}));
inspect.addEventListener('click',()=>action('workspace.inspect',{name:objects.value}));
objectSearch.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.objects',{query:objectSearch.value,family:families.value});}});
find.addEventListener('click',()=>action('workspace.search',{query:search.value}));
search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();action('workspace.search',{query:search.value});}});
open.addEventListener('click',()=>action('workspace.open',{name:select.value}));close.addEventListener('click',()=>action('workspace.close',{}));
window.addEventListener('beforeunload',event=>{if([...mounts.values()].some(entry=>entry.view.hasPending())){event.preventDefault();event.returnValue='';}});
action('workspace.snapshot',{});
