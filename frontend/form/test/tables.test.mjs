import test from 'node:test';
import assert from 'node:assert/strict';
import {FormClient, PROTOCOL, LIMITS, validateSnapshot, tableCell, typedInput} from '../src/client.mjs';
import {createFormView} from '../src/view.mjs';
import {mountForm} from '../src/app.mjs';
import {field, button, column, table, state, reply, response, deferred} from './fixtures.mjs';
import {FakeDocument, all, buttons, environment} from './fake-dom.mjs';
const model = (snapshot, extra = {}) => ({snapshot, busy: false, locked: false, error: '', connected: true,
  outcomeUnknown: false, transportFailed: false, exhausted: false, ...extra});
const tableState = (revision = 0, item = table(), extra = {}) => state(revision, {items: [item, button()], ...extra});
const cell = (document, row = 1, name = 'Description') => all(document.root)
  .find(node => node.tagName === 'INPUT' && node.getAttribute('aria-label') === name + ', row ' + row);
const edit = (node, value) => { if (node.type === 'checkbox') node.checked = value; else node.value = value; node.emit('input'); return node; };
const select = (document, row) => buttons(document).find(node => node.getAttribute('aria-label')?.startsWith('Select row ' + row + ' '));
const create = handlers => {
  const document = new FakeDocument();
  return {document, view: createFormView(document, document.root, {change() {}, action() {}, select() {}, refresh() {}, ...handlers})};
};
const replaceCell = (item, row, name, value) => ({...item, rows: item.rows.map(entry => entry.id !== row ? entry :
  {...entry, values: entry.values.map((original, index) => item.columns[index].name === name ? value : original)})});
function host(initial = tableState(), alter = () => null) {
  const requests = []; let current = initial;
  const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    const result = await alter(request, current);
    if (result?.throw) throw Error('Lost reply');
    if (result?.state) current = result.state;
    else if (request.method === 'form.event') {
      const p = request.params;
      current = {...current, revision: current.revision + 1, items: current.items.map(item => {
        if (item.name !== p.control) return item;
        if (p.event === 'cell') return {...replaceCell(item, p.row, p.column, p.value), currentRow: p.row};
        if (p.event === 'select') return {...item, currentRow: p.row};
        if (p.event === 'change') return {...item, value: p.value};
        return item;
      })};
      if (p.event === 'close') current = {...current, kind: 'closed', lifecycle: 'closed'};
    }
    return response(reply(request, current, result?.error || null));
  });
  const app = mountForm(env, env.document.root);
  return {app, env, requests, get current() { return current; }};
}

test('UI /1 sends exact cell and row-selection shapes with exact decimal strings', async () => {
  assert.equal(PROTOCOL, 'yadinassi-form-ui/1');
  const requests = []; const client = new FormClient(async request => { requests.push(request); return reply(request, tableState(requests.length - 1)); });
  await client.hello(); await client.event('cell', {control: 'Lines', row: 2, column: 'Quantity', value: {type: 'Number', value: '999999999999999999.0100'}});
  await client.event('select', {control: 'Lines', row: 2}); await client.event('select', {control: 'Lines', row: null});
  assert.deepEqual(requests.slice(1).map(request => request.params), [
    {event: 'cell', revision: 0, control: 'Lines', row: 2, column: 'Quantity', value: {type: 'Number', value: '999999999999999999.0100'}},
    {event: 'select', revision: 1, control: 'Lines', row: 2}, {event: 'select', revision: 2, control: 'Lines', row: null},
  ]);
});

test('table snapshots reject closed-shape, identity, row, column and selection violations', () => {
  const invalid = [
    {...table(), extra: true}, {...table(), controlId: 0}, {...table(), controlId: 1025}, {...table(), controlId: true},
    {...table(), tableId: 0}, {...table(), tableId: LIMITS.counter + 1}, {...table(), tableId: 1.2},
    {...table(), currentRow: 3}, {...table(), currentRow: true}, {...table(), currentRow: 0},
    {...table(), columns: []}, {...table(), columns: [column(), column()]},
    {...table(), columns: [column('X', 'ValueTable')]}, {...table(), columns: [column('X', 'String', {readOnly: 1})]},
    {...table(), columns: [column('X', 'String', {extra: true})]},
    {...table(), rows: [{id: 0, values: table().rows[0].values}]},
    {...table(), rows: [{id: 4097, values: table().rows[0].values}]},
    {...table(), rows: [{id: true, values: table().rows[0].values}]},
    {...table(), rows: [table().rows[0], table().rows[0]]},
    {...table(), rows: [{...table().rows[0], extra: true}]},
    {...table(), rows: [{id: 1, values: [{type: 'String', value: 'Short'}]}]},
    replaceCell(table(), 1, 'Quantity', {type: 'String', value: 'wrong'}),
    replaceCell(table(), 1, 'Active', {type: 'Boolean', value: 1}),
  ];
  for (const item of invalid) assert.throws(() => validateSnapshot(tableState(0, item)), {code: 'transport'});
  for (const duplicate of [table({name: 'Other', controlId: 2}), table({name: 'Other', tableId: 2})])
    assert.throws(() => validateSnapshot(state(0, {items: [table(), duplicate]})), {code: 'transport'});
});

test('all table count budgets accept boundaries and reject overflow', () => {
  const big = table({columns: Array.from({length: 8}, (_, i) => column('C' + i)),
    rows: Array.from({length: 32}, (_, i) => ({id: i + 1, values: Array.from({length: 8}, () => ({type: 'String', value: ''}))}))});
  assert.doesNotThrow(() => validateSnapshot(tableState(0, big)));
  assert.throws(() => validateSnapshot(tableState(0, {...big, rows: [...big.rows, {...big.rows[0], id: 33}]})));
  assert.throws(() => validateSnapshot(tableState(0, {...big, columns: [...big.columns, column('C9')]})));
  assert.throws(() => validateSnapshot(state(0, {items: [big, table({name: 'Other', tableId: 2, controlId: 2})]})));
  const items = Array.from({length: 4}, (_, i) => table({name: 'T' + i, tableId: i + 1, controlId: i + 1, rows: []}));
  assert.doesNotThrow(() => validateSnapshot(state(0, {items})));
  assert.throws(() => validateSnapshot(state(0, {items: [...items, table({name: 'T4', tableId: 5, controlId: 5, rows: []})]})));
});

test('table scalar values include display-only empty and date tags and respect frame bytes', () => {
  const item = table({columns: [column('When', 'Date'), column('Absent'), column('Empty')],
    rows: [{id: 4096, values: [{type: 'Date', ticks: '3155378975990000'}, {type: 'Undefined'}, {type: 'Null'}]}], currentRow: 4096});
  assert.doesNotThrow(() => validateSnapshot(tableState(0, item)));
  const large = table({columns: [column()], rows: Array.from({length: 5}, (_, i) => ({id: i + 1, values: [{type: 'String', value: 'a'.repeat(8000)}]}))});
  // The host's separate 32 KiB internal encoding budget is not this UI projection.
  assert.doesNotThrow(() => validateSnapshot(tableState(0, large)));
  assert.throws(() => validateSnapshot(tableState(0, {...large, rows: Array.from({length: 17}, (_, i) => ({...large.rows[0], id: i + 1}))})), {code: 'transport'});
});

test('cell inputs share exact scalar parsing and cannot edit Date, Null or Undefined', () => {
  assert.deepEqual(typedInput(tableCell(table(), 1, 'Quantity'), '+00012.300'), {type: 'Number', value: '12.300'});
  assert.deepEqual(typedInput(tableCell(table(), 1, 'Active'), false), {type: 'Boolean', value: false});
  for (const value of [{type: 'Null'}, {type: 'Undefined'}, {type: 'Date', ticks: '1'}]) {
    const item = table({columns: [column('Value', value.type === 'Date' ? 'Date' : 'String')], rows: [{id: 1, values: [value]}]});
    assert.throws(() => typedInput(tableCell(item, 1, 'Value'), 'x'), {code: 'unavailable'});
  }
  assert.equal(tableCell(table(), 99, 'Quantity'), null);
});

test('invalid cell and select events are blocked before any request', async () => {
  const client = new FormClient(async request => reply(request, tableState())); await client.hello();
  const base = {control: 'Lines', row: 1, column: 'Quantity', value: {type: 'Number', value: '1'}};
  for (const value of [{...base, row: null}, {...base, row: true}, {...base, row: 99}, {...base, column: 'Missing'},
    {...base, extra: true}, {...base, value: {type: 'String', value: '1'}}, {...base, control: 'Run'}])
    assert.throws(() => client.event('cell', value));
  for (const value of [{control: 'Lines', row: 99}, {control: 'Lines', row: false}, {control: 'Run', row: null},
    {control: 'Lines', row: 1, value: null}]) assert.throws(() => client.event('select', value));
  assert.equal(client.id, 1);
});

test('table visibility, enabled, read-only and column locks reject edits', async () => {
  for (const patch of [{visible: false}, {enabled: false}, {readOnly: true}]) {
    const client = new FormClient(async request => reply(request, tableState(0, table(patch)))); await client.hello();
    if (!patch.readOnly) assert.throws(() => client.event('select', {control: 'Lines', row: 1}), {code: 'unavailable'});
    assert.throws(() => client.event('cell', {control: 'Lines', row: 1, column: 'Description', value: {type: 'String', value: 'X'}}), {code: 'unavailable'});
  }
  const item = table({columns: table().columns.map(column => ({...column, readOnly: true}))});
  const client = new FormClient(async request => reply(request, tableState(0, item))); await client.hello();
  assert.throws(() => client.event('cell', {control: 'Lines', row: 1, column: 'Description', value: {type: 'String', value: 'X'}}), {code: 'unavailable'});
  assert.equal(client.id, 1);
});

test('malformed table reply preserves last valid state and locks without replay', async () => {
  const client = new FormClient(async request => reply(request, tableState(request.id, request.id === 1 ? table() : table({currentRow: 99}))));
  await client.hello(); await assert.rejects(client.event('select', {control: 'Lines', row: 1}), {code: 'transport'});
  assert.equal(client.snapshot.revision, 1); assert.equal(client.locked, true); assert.equal(client.id, 2);
});

test('table uses semantic headings, labels, literal text and visible selected row', () => {
  const {view, document} = create(); const hostile = '<script>bad()</script>';
  view.render(model(tableState(0, replaceCell(table({title: hostile, currentRow: 2}), 1, 'Description', {type: 'String', value: hostile}))));
  assert.equal(cell(document).value, hostile);
  assert.equal(all(document.root).filter(node => node.tagName === 'TABLE').length, 1);
  assert.ok(all(document.root).filter(node => node.tagName === 'TH').every(node => ['col', 'row'].includes(node.getAttribute('scope'))));
  assert.ok(document.root.textContent.includes(hostile)); assert.ok(document.root.textContent.includes('Selected row 2'));
  assert.equal(cell(document, 1, 'Quantity').value, '1.00'); assert.equal(cell(document, 1, 'Active').type, 'checkbox');
  assert.equal(all(document.root).some(node => node.tagName === 'SCRIPT'), false);
  const selected = buttons(document).find(node => node.getAttribute('aria-pressed') === 'true');
  assert.equal(selected.parentNode.parentNode.className, 'current-row');
});

test('keyed table rows and cells retain identity, drafts, focus and selection through insertion and reorder', () => {
  const {view, document} = create(); const initial = tableState(); view.render(model(initial));
  const original = edit(cell(document, 2), 'Pending row two'); original.focus(); original.setSelectionRange(2, 7, 'backward');
  const row = original.parentNode.parentNode, tableNode = row.parentNode.parentNode;
  view.render(model(initial, {busy: true}));
  view.render(model(tableState(1, table({rows: [table().rows[1], {...table().rows[0], id: 3}, table().rows[0]]}))));
  assert.equal(cell(document, 2), original); assert.equal(original.parentNode.parentNode, row); assert.equal(row.parentNode.parentNode, tableNode);
  assert.equal(original.value, 'Pending row two'); assert.equal(document.activeElement, original);
  assert.equal(original.selectionStart, 2); assert.equal(original.selectionEnd, 7);
  assert.deepEqual(view.changes(), [{control: 'Lines', row: 2, column: 'Description', value: {type: 'String', value: 'Pending row two'}}]);
});

test('deleting a row keeps its drafts copy-only and preserves surviving keyed cells', () => {
  const {view, document} = create(); view.render(model(tableState()));
  const removed = edit(cell(document, 1), 'Remove draft'), kept = edit(cell(document, 2), 'Keep draft');
  view.render(model(tableState(1, table({rows: [table().rows[1]]}))));
  assert.equal(document.root.contains(removed), false); assert.equal(cell(document, 2), kept); assert.equal(kept.value, 'Keep draft');
  assert.ok(document.root.textContent.includes('Remove draft')); assert.throws(() => view.changes(), {code: 'draft_changed'});
});

test('changed authoritative cell recovers the stale draft while other cells survive', () => {
  const {view, document} = create(); view.render(model(tableState()));
  edit(cell(document, 1), 'Stale'); edit(cell(document, 2), 'Still pending');
  const changed = replaceCell(replaceCell(table(), 1, 'Description', {type: 'String', value: 'Server effect'}),
    2, 'Description', {value: 'Second', type: 'String'});
  view.render(model(tableState(1, changed)));
  assert.equal(cell(document, 1).value, 'Server effect'); assert.equal(cell(document, 2).value, 'Still pending');
  assert.ok(document.root.textContent.includes('Stale')); assert.throws(() => view.changes(), {code: 'draft_changed'});
});

test('replacing control or table identity prevents same-name draft retargeting', () => {
  for (const patch of [{controlId: 2}, {tableId: 2}]) {
    const {view, document} = create(); view.render(model(tableState())); const original = edit(cell(document), 'Old identity');
    view.render(model(tableState(1, table(patch)))); assert.notEqual(cell(document), original); assert.equal(view.hasDrafts(), true);
    assert.ok(document.root.textContent.includes('Old identity')); assert.throws(() => view.changes(), {code: 'draft_changed'});
  }
});

test('column reorder preserves drafts by name and retyping recovers incompatible input', () => {
  const {view, document} = create(); view.render(model(tableState()));
  const original = edit(cell(document), 'Pending'); edit(cell(document, 1, 'Quantity'), '12.50');
  const initial = table(); const reordered = {...initial, columns: [initial.columns[1], initial.columns[0], initial.columns[2]],
    rows: initial.rows.map(row => ({...row, values: [row.values[1], row.values[0], row.values[2]]}))};
  view.render(model(tableState(1, reordered))); assert.equal(cell(document), original); assert.equal(view.changes().length, 2);
  const retyped = {...reordered, columns: [column('Quantity'), ...reordered.columns.slice(1)],
    rows: reordered.rows.map(row => ({...row, values: [{type: 'String', value: 'Host text'}, ...row.values.slice(1)]}))};
  view.render(model(tableState(2, retyped))); assert.throws(() => view.changes(), {code: 'draft_changed'}); assert.equal(cell(document), original);
  assert.ok(document.root.textContent.includes('12.50')); assert.equal(original.value, 'Pending');
  assert.equal(cell(document, 1, 'Quantity').value, 'Host text');
});

test('table dates and empty scalars remain exact display-only values', () => {
  const {view, document} = create(); const item = table({columns: [column('When', 'Date'), column('Missing'), column('Empty')],
    rows: [{id: 1, values: [{type: 'Date', ticks: '3155378975990000'}, {type: 'Undefined'}, {type: 'Null'}]}]});
  view.render(model(tableState(0, item)));
  for (const [name, value] of [['When', '3155378975990000'], ['Missing', 'Undefined'], ['Empty', 'Null']]) {
    assert.equal(cell(document, 1, name).readOnly, true); assert.equal(cell(document, 1, name).value, value);
  }
  assert.ok(cell(document, 1, 'When').title.includes('no timezone conversion'));
});

test('read-only table blocks cells but session locks also disable selection', () => {
  const {view, document} = create(); view.render(model(tableState())); edit(cell(document), 'Pending');
  view.render(model(tableState(1, table({readOnly: true}))));
  assert.equal(view.hasDrafts(), true); assert.equal(cell(document).readOnly, true); assert.equal(cell(document, 1, 'Active').disabled, true);
  assert.equal(select(document, 2).disabled, true); assert.ok(document.root.textContent.includes('Pending'));
  view.clearDrafts(); view.render(model(tableState(1, table({readOnly: true})))); assert.equal(select(document, 2).disabled, false);
  view.render(model(tableState(2), {locked: true, outcomeUnknown: true}));
  assert.ok(buttons(document).filter(node => node.dataset.formAction === 'select').every(node => node.disabled));
  assert.ok(all(document.root).filter(node => node.tagName === 'INPUT').every(node => node.disabled));
});

test('cell blur into selection or command defers to full flush and Enter ignores composition', () => {
  const calls = []; const {view, document} = create({change: locator => calls.push(locator)}); view.render(model(tableState()));
  const node = edit(cell(document), 'Draft'), selection = select(document, 2);
  node.emit('blur', {relatedTarget: selection}); assert.equal(calls.length, 0);
  selection.emit('pointerdown', {bubbles: true}); node.emit('blur'); assert.equal(calls.length, 0);
  selection.emit('pointercancel', {bubbles: true}); node.emit('blur');
  node.emit('keydown', {key: 'Enter', isComposing: true}); assert.equal(calls.length, 1);
  node.emit('keydown', {key: 'Enter'}); assert.deepEqual(calls, Array(2).fill({control: 'Lines', row: 1, column: 'Description'}));
});

test('all scalar fields and row drafts flush in display order before command and reject duplicate clicks', async () => {
  const gate = deferred(); const setup = host(state(0, {items: [field(), table(), button('Save')]}), async request => {
    if (request.params.event === 'change') await gate.promise;
  });
  const {app, env, requests} = setup; await app.ready;
  edit(all(env.document.root).find(node => node.tagName === 'INPUT'), 'Header');
  edit(cell(env.document, 2), 'Second edit'); edit(cell(env.document, 1, 'Quantity'), '999999999999999999.0100');
  const first = app.run('command', 'Save'); await app.run('command', 'Save'); await app.run('select', 'Lines', 2);
  assert.equal(requests.length, 2); gate.resolve(); await first;
  assert.deepEqual(requests.slice(1).map(request => [request.params.event, request.params.revision, request.params.row]),
    [['change', 0, undefined], ['cell', 1, 1], ['cell', 2, 2], ['command', 3, undefined]]);
  assert.equal(requests[2].params.value.value, '999999999999999999.0100'); assert.equal(app.view.hasDrafts(), false);
});

test('explicit row selection flushes every cell before selecting requested row or null', async () => {
  const {app, env, requests} = host(); await app.ready;
  edit(cell(env.document, 1), 'One'); edit(cell(env.document, 2), 'Two');
  select(env.document, 1).emit('click'); await new Promise(resolve => setTimeout(resolve, 0));
  buttons(env.document).find(node => node.textContent === 'Clear selection').emit('click');
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(requests.slice(1).map(request => [request.params.event, request.params.revision, request.params.row]),
    [['cell', 0, 1], ['cell', 1, 2], ['select', 2, 1], ['select', 3, null]]);
  assert.ok(env.document.root.textContent.includes('No row selected'));
});

test('Close flushes multiple cells then closes without further writes', async () => {
  const {app, env, requests} = host(); await app.ready; edit(cell(env.document, 1), 'Final'); edit(cell(env.document, 2, 'Quantity'), '3.00');
  await app.run('close'); await app.run('select', 'Lines', 1);
  assert.deepEqual(requests.slice(1).map(request => request.params.event), ['cell', 'cell', 'close']);
  assert.equal(app.client.locked, true); assert.ok(cell(env.document).closest('[hidden]'));
});

test('Boolean cell changes dispatch tagged Boolean and current row comes from host', async () => {
  const {app, env, requests} = host(); await app.ready;
  const checkbox = edit(cell(env.document, 2, 'Active'), true); checkbox.emit('change');
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(requests[1].params, {event: 'cell', revision: 0, control: 'Lines', row: 2, column: 'Active', value: {type: 'Boolean', value: true}});
  assert.ok(env.document.root.textContent.includes('Selected row 2')); assert.equal(app.view.hasDrafts(), false);
});

test('invalid later draft prevents all fields, cells, command and selection from being sent', async () => {
  const {app, env, requests} = host(state(0, {items: [field(), table(), button()]})); await app.ready;
  edit(all(env.document.root).find(node => node.tagName === 'INPUT'), 'Header'); edit(cell(env.document, 1), 'Valid');
  edit(cell(env.document, 2, 'Quantity'), '1,20');
  await app.run('command', 'Run'); await app.run('select', 'Lines', 1); await app.run('close');
  assert.equal(requests.length, 1); assert.ok(env.document.root.textContent.includes('supported value')); assert.equal(app.view.hasDrafts(), true);
});

test('handler deleting a later draft row stops flush without retargeting or running command', async () => {
  const {app, env, requests} = host(tableState(), (request, current) => request.params.event === 'cell' ?
    {state: {...current, revision: 1, items: [table({rows: [{...table().rows[0], values: [request.params.value, ...table().rows[0].values.slice(1)]}]}), button()]}} : null);
  await app.ready; edit(cell(env.document, 1), 'Edited first'); edit(cell(env.document, 2), 'Deleted'); await app.run('command', 'Run');
  assert.equal(requests.length, 2); assert.equal(cell(env.document, 2), undefined);
  assert.ok(env.document.root.textContent.includes('pending edit')); assert.equal(app.view.hasDrafts(), true);
  assert.ok(env.document.root.textContent.includes('Deleted')); assert.throws(() => app.view.changes(), {code: 'draft_changed'});
});

test('handler changing another pending cell stops stale flush and preserves unaffected drafts', async () => {
  const {app, env, requests} = host(tableState(), (request, current) => request.params.event === 'cell' ?
    {state: {...current, revision: 1, items: [replaceCell(replaceCell(table(), 1, 'Description', request.params.value), 1, 'Quantity', {type: 'Number', value: '10'}), button()]}} : null);
  await app.ready; edit(cell(env.document, 1), 'Edited first'); edit(cell(env.document, 1, 'Quantity'), '2.00'); edit(cell(env.document, 2), 'Keep');
  await app.run('command', 'Run'); assert.equal(requests.length, 2); assert.equal(cell(env.document, 1, 'Quantity').value, '10');
  assert.equal(cell(env.document, 2).value, 'Keep'); assert.throws(() => app.view.changes(), {code: 'draft_changed'});
  assert.ok(env.document.root.textContent.includes('2.00'));
});

test('handler errors adopt accepted cell effects and retain unaffected row drafts for new intent', async () => {
  const {app, env, requests} = host(tableState(), request => request.params.event === 'cell' ?
    {state: tableState(1, replaceCell(table(), 1, 'Description', {type: 'String', value: 'Completed'})), error: 'event_failed'} : null);
  await app.ready; edit(cell(env.document, 1), 'Edited first'); edit(cell(env.document, 2), 'Keep'); await app.run('command', 'Run');
  assert.equal(requests.length, 2); assert.equal(cell(env.document, 1).value, 'Completed'); assert.equal(cell(env.document, 2).value, 'Keep');
  assert.ok(env.document.root.textContent.includes('Completed changes')); assert.equal(app.client.locked, false);
});

test('stale cell rejection adopts authoritative value and never sends queued selection', async () => {
  const {app, env, requests} = host(tableState(), request => request.params.event === 'cell' ?
    {state: tableState(9, replaceCell(table(), 1, 'Description', {type: 'String', value: 'Other client'})), error: 'stale_revision'} : null);
  await app.ready; edit(cell(env.document), 'Stale'); await app.run('select', 'Lines', 2);
  assert.equal(requests.length, 2); assert.equal(cell(env.document).value, 'Other client'); assert.equal(app.client.snapshot.revision, 9);
  assert.ok(env.document.root.textContent.includes('Stale')); assert.equal(app.view.hasDrafts(), true);
});

test('lost cell response locks edits and selection until read-only refresh without replay', async () => {
  const {app, env, requests} = host(tableState(), request => request.params.event === 'cell' ? {throw: true} :
    request.method === 'form.snapshot' ? {state: tableState(1, replaceCell(table(), 1, 'Description', {type: 'String', value: 'Applied once'}))} : null);
  await app.ready; edit(cell(env.document), 'Pending'); await app.run('command', 'Run'); await app.run('select', 'Lines', 2);
  assert.equal(requests.length, 2); assert.equal(cell(env.document).disabled, true);
  await app.refresh(); assert.deepEqual(requests.map(request => request.method), ['form.hello', 'form.event', 'form.snapshot']);
  assert.equal(cell(env.document).value, 'Applied once'); assert.equal(app.view.hasDrafts(), false); assert.equal(app.client.locked, false);
});

test('authoritative unknown table outcome remains locked after clean refresh', async () => {
  const {app, env, requests} = host(tableState(), request => request.params.event === 'cell' ?
    {state: tableState(1, table(), {uncertain: true}), error: 'outcome_unknown'} : request.method === 'form.snapshot' ? {state: tableState(1)} : null);
  await app.ready; edit(cell(env.document), 'Pending'); await app.run('command', 'Run'); await app.refresh(); await app.run('select', 'Lines', 2);
  assert.equal(requests.length, 3); assert.equal(app.client.locked, true);
  assert.ok(buttons(env.document).filter(node => node.dataset.formAction !== 'refresh').every(node => node.disabled));
});

test('Delete stays an ordinary command following flush and preserves surviving row identity', async () => {
  const {app, env, requests} = host(tableState(0, table(), {items: [table(), button('Delete')]}), (request, current) => request.params.event === 'command' ?
    {state: {...current, revision: current.revision + 1, items: [table({rows: [table().rows[1]]}), button('Delete')]}} : null);
  await app.ready; const surviving = cell(env.document, 2); edit(cell(env.document), 'Delete me'); await app.run('command', 'Delete');
  assert.deepEqual(requests.slice(1).map(request => request.params.event), ['cell', 'command']);
  assert.equal(requests[2].params.control, 'Delete'); assert.equal(cell(env.document, 1), undefined); assert.equal(cell(env.document, 2), surviving);
});

test('equivalent decimal spelling clears a no-op draft without sending or warning on unload', async () => {
  const {app, env, requests} = host(); await app.ready; edit(cell(env.document, 1, 'Quantity'), '+0001.00');
  await app.run('change', {control: 'Lines', row: 1, column: 'Quantity'});
  let prevented = false; env.listeners.get('beforeunload')({preventDefault() { prevented = true; }});
  assert.equal(requests.length, 1); assert.equal(app.view.hasDrafts(), false); assert.equal(prevented, false);
});


test('independent tables with equal row IDs preserve separate drafts and flush locators', () => {
  const {view, document} = create(); const other = table({name: 'Other', tableId: 2, controlId: 2, title: 'Other lines'});
  view.render(model(state(0, {items: [table(), other]})));
  const inputs = all(document.root).filter(node => node.tagName === 'INPUT' && node.getAttribute('aria-label') === 'Description, row 1');
  edit(inputs[0], 'First table'); edit(inputs[1], 'Second table');
  assert.deepEqual(view.changes(), [
    {control: 'Lines', row: 1, column: 'Description', value: {type: 'String', value: 'First table'}},
    {control: 'Other', row: 1, column: 'Description', value: {type: 'String', value: 'Second table'}},
  ]);
  view.render(model(state(1, {items: [other]})));
  assert.throws(() => view.changes(), {code: 'draft_changed'}); assert.ok(document.root.textContent.includes('First table'));
  assert.equal(cell(document), inputs[1]); assert.equal(inputs[1].value, 'Second table');
});


test('read-only table supports view-only selection and clearing without cell mutation', async () => {
  const {app, env, requests} = host(tableState(0, table({readOnly: true})));
  await app.ready;
  assert.equal(select(env.document, 2).disabled, false);
  await app.run('select', 'Lines', 2);
  assert.equal(app.client.snapshot.items[0].currentRow, 2);
  await app.run('select', 'Lines', null);
  assert.equal(app.client.snapshot.items[0].currentRow, null);
  assert.deepEqual(requests.slice(1).map(request => request.params.event), ['select', 'select']);
  assert.throws(() => app.client.event('cell', {control: 'Lines', row: 1, column: 'Description', value: {type: 'String', value: 'X'}}), {code: 'unavailable'});
});

test('retained views isolate DOM IDs and label/ARIA references despite identical host identities', () => {
  const document = new FakeDocument();
  const roots = [document.createElement('section'), document.createElement('section')];
  document.root.append(...roots); roots[0].hidden = true;
  const handlers = {change() {}, action() {}, select() {}, refresh() {}};
  const snapshot = state(0, {items: [field(), table(), button()]});
  const views = roots.map(root => createFormView(document, root, handlers));
  for (const view of views) view.render(model(snapshot));
  const verify = () => {
    const nodes = all(document.root).filter(node => node.id);
    assert.equal(new Set(nodes.map(node => node.id)).size, nodes.length);
    for (const root of roots) {
      const labels = all(root).filter(node => node.htmlFor);
      assert.ok(labels.length > 0);
      for (const label of labels) {
        const target = document.getElementById(label.htmlFor);
        assert.ok(root.contains(target)); assert.ok(label.contains(target));
        assert.equal(target.tagName, 'INPUT');
      }
      const described = all(root).filter(node => node.getAttribute('aria-describedby'));
      assert.ok(described.length > 1); // Scalar hint and every table cell's help.
      for (const node of described) for (const id of node.getAttribute('aria-describedby').split(/\s+/)) {
        const target = document.getElementById(id);
        assert.ok(root.contains(target)); assert.ok(target.textContent.length > 0);
      }
    }
  };
  verify();
  const originalIds = roots.map(root => all(root).filter(node => node.id).map(node => node.id));
  roots[0].hidden = false; roots[1].hidden = true;
  for (const view of views) view.render(model({...snapshot, revision: 1}));
  verify();
  assert.deepEqual(roots.map(root => all(root).filter(node => node.id).map(node => node.id)), originalIds);
  // Remounting never reuses an old view's prefix, even though its nodes are gone.
  createFormView(document, roots[0], handlers).render(model(snapshot));
  verify();
  const retired = new Set(originalIds[0]);
  assert.ok(all(roots[0]).filter(node => node.id).every(node => !retired.has(node.id)));
  assert.deepEqual(snapshot.items[1], table());
});
