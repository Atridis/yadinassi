import {FormError, editable, tableCell, scalarText, inputHint, typedInput, scalarEqual, LIMITS} from './client.mjs';

// DOM identity belongs to a retained view, never to a host control or table ID.
// BigInt keeps allocation monotonic without wrapping or reusing retired prefixes.
let viewSerial = 0n;

/** Keyed, text-only DOM renderer. The host can name controls but cannot supply HTML. */
export function createFormView(document, root, handlers) {
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
  let current = null, isBusy = false, focusMemory = null, actionPointer = false;
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
    const reference = field?.value?.type === 'FormCatalogRef'; actions.group.hidden = !reference;
    const unavailable = disabled || !reference || !field.visible || !field.enabled || field.readOnly || field.view === 'label';
    actions.choose.disabled = unavailable; actions.clear.disabled = unavailable || field.value.key === null;
    actions.choose.setAttribute('aria-label', 'Choose ' + label); actions.clear.setAttribute('aria-label', 'Clear ' + label);
  }
  function makeControl(item) {
    const row = element(item.kind === 'button' || item.value?.type === 'FormCatalogRef' ? 'div' : 'label', item.kind === 'button' ? 'command' : 'field');
    const caption = element('span', 'field-title');
    const input = element(item.kind === 'button' ? 'button' : 'input');
    const hint = element('small', 'field-hint');
    const id = idPrefix + 'control-' + ++serial;
    input.id = id;
    if (item.kind === 'button') {
      input.type = 'button'; input.dataset.formAction = 'command'; input.className = 'primary';
      input.addEventListener('click', () => handlers.action('command', item.name));
      row.append(input);
    } else {
      row.htmlFor = id; hint.id = id + '-hint'; input.setAttribute('aria-describedby', hint.id);
      input.type = item.value.type === 'Boolean' ? 'checkbox' : 'text';
      // A checkbox activation, including its label, owns the preceding blur.
      // Its change intent flushes all pending fields before applying the toggle.
      if (input.type === 'checkbox') row.dataset.formAction = input.dataset.formAction = 'toggle';
      input.autocomplete = 'off'; input.spellcheck = false;
      const live = () => controls.get(item.name)?.input === input;
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
    const reference = item.value?.type === 'FormCatalogRef' ? referenceActions(row, {control: item.name, row: null, column: null}) : null;
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
    const live = () => controls.get(name)?.item.tableId === tableId && controls.get(name)?.item.controlId === controlId &&
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
    const reference = column.type === 'FormCatalogRef' ? referenceActions(cell, locator) : null;
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
    const savedFocus = captureFocus();
    if (model.busy && !isBusy) focusMemory = savedFocus;
    const wasBusy = isBusy; isBusy = model.busy; current = model.snapshot;
    reconcileDrafts();
    const active = current?.kind === 'form' && current.lifecycle === 'open';
    title.textContent = current?.title || 'Local form'; document.title = title.textContent + ' · Yadinassi';
    panel.setAttribute('aria-busy', model.busy ? 'true' : 'false');
    status.textContent = model.busy ? 'Working…' : !current ? 'Not connected' : current.uncertain || model.outcomeUnknown ? 'Outcome unknown'
      : current.lifecycle === 'open' ? 'Connected' : current.lifecycle === 'cancelled' ? 'Cancelled'
      : current.lifecycle === 'failed' ? 'Failed' : 'Closed';
    status.className = 'badge ' + (current?.uncertain || model.outcomeUnknown ? 'unsafe' : active ? 'connected' : '');
    revision.textContent = current ? 'Revision ' + current.revision : 'Local session';
    refresh.disabled = model.paused || model.busy || !model.connected || model.exhausted;
    close.disabled = recovery.size > 0 || model.paused || model.busy || model.locked || !active;
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
    for (const [name, control] of controls) if (!names.has(name)) { remember('field:' + name, name, drafts.get(name)); control.row.remove(); controls.delete(name); drafts.delete(name); discardTable(name); }
    let fieldIndex = 0, actionIndex = 0;
    for (const item of current?.items || []) {
      let control = controls.get(item.name);
      if (control && (control.item.kind !== item.kind || control.item.value?.type !== item.value?.type || control.item.tableId !== item.tableId || control.item.controlId !== item.controlId)) {
        remember('field:' + item.name, item.name, drafts.get(item.name)); control.row.remove(); controls.delete(item.name); drafts.delete(item.name); discardTable(item.name); control = null;
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
    recovered.hidden = recovery.size === 0;
    recovered.replaceChildren(element('p', '', 'These inputs no longer match the host state and were not applied. Copy any text you need, then use Refresh state to discard them and continue.'),
      ...Array.from(recovery.values(), draft => element('p', '', draft.label + ': ' + String(draft.value))));
    const nextMessages = current?.messages || [];
    // Rebuild only the bounded message list, never input nodes or host-supplied markup.
    messages.replaceChildren(...nextMessages.map(message => element('p', '', message)));
    messages.hidden = !nextMessages.length;
    actions.hidden = !current || current.kind === 'closed' || !current.items.some(item => item.kind === 'button' && item.visible);
    if (!model.busy) { restoreFocus(wasBusy ? focusMemory : savedFocus); focusMemory = null; }
  }
  return {
    render,
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
