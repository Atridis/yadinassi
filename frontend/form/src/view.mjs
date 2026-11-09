import {editable, scalarText, typedInput, scalarEqual, LIMITS} from './client.mjs';

/** Keyed, text-only DOM renderer. The host can name controls but cannot supply HTML. */
export function createFormView(document, root, handlers) {
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
