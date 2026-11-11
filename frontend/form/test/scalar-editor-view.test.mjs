import test from 'node:test';
import assert from 'node:assert/strict';
import {LIMITS, typedInput} from '../src/client.mjs';
import {createFormView} from '../src/view.mjs';
import {mountForm} from '../src/app.mjs';
import {field, button, column, table, state, reply, deferred} from './fixtures.mjs';
import {FakeDocument, all, environment, buttons} from './fake-dom.mjs';

const date = (parts = 'dateTime', ticks = '0', extra = {}) => field('When', {type: 'Date', ticks}, {controlId: 2, editor: {kind: 'date', parts}, ...extra});
const amount = (extra = {}) => field('Amount', {type: 'Number', value: '1.00'}, {controlId: 3,
  editor: {kind: 'number', digits: 5, scale: 2, nonnegative: true}, ...extra});
const code = () => field('Code', {type: 'String', value: 'A    '}, {controlId: 4, editor: {kind: 'string', length: 5, fixed: true}});
const grid = () => table({columns: [column('Day', 'Date', {editor: {kind: 'date', parts: 'date'}}), column('Text')],
  rows: [{id: 7, values: [{type: 'Date', ticks: '0'}, {type: 'String', value: 'Row'}]}]});
const find = (document, label) => all(document.root).find(node => node.tagName === 'INPUT' && node.getAttribute('aria-label') === label);
const edit = (node, value) => { node.value = value; node.emit('input'); return node; };
const model = snapshot => ({snapshot, busy: false, locked: false, connected: true, error: ''});
const create = () => {
  const document = new FakeDocument();
  return {document, view: createFormView(document, document.root, {change() {}, select() {}, action() {}, refresh() {}})};
};
function host(initial, alter = () => null, options = {}) {
  const env = environment(), requests = []; let current = initial;
  const app = mountForm(env, env.document.root, {transport: async request => {
    requests.push(request); const result = await alter(request, current);
    if (result?.throw) throw Error('lost response');
    if (result?.state) current = result.state;
    else if (request.method === 'form.event') {
      const p = request.params;
      current = {...current, revision: current.revision + 1, items: current.items.map(item => item.name !== p.control ? item :
        p.event === 'change' ? {...item, value: p.value} : p.event === 'cell' ? {...item, rows: item.rows.map(row => row.id !== p.row ? row :
          {...row, values: row.values.map((value, index) => item.columns[index].name === p.column ? p.value : value)})} : item)};
    }
    return reply(request, current, result?.error || null);
  }, ...options});
  return {env, requests, app, get current() { return current; }};
}

test('metadata dates render ISO text and concrete hints in both fields and table cells', () => {
  const {document, view} = create(), when = date('dateTime', '621355968000000');
  view.render(model(state(0, {items: [when, {...date('time', '37230000'), name: 'Clock', title: 'Clock', controlId: 3}, grid()]})));
  assert.equal(find(document, 'When').value, '1970-01-01T00:00:00'); assert.equal(find(document, 'When').type, 'text');
  assert.equal(find(document, 'When').readOnly, false); assert.equal(find(document, 'Clock').value, '01:02:03');
  assert.equal(find(document, 'Day, row 7').value, ''); assert.match(find(document, 'Day, row 7').title, /YYYY-MM-DD/);
  assert.match(document.root.textContent, /YYYY-MM-DDTHH:mm:ss/); assert.match(document.root.textContent, /HH:mm:ss/);
  edit(find(document, 'Day, row 7'), '2024-02-29');
  assert.deepEqual(view.changes(), [{control: 'Lines', row: 7, column: 'Day', value: typedInput(date('date'), '2024-02-29')}]);
});

test('business String qualifiers are not imposed through silently truncating maxlength', () => {
  const {document, view} = create(); view.render(model(state(0, {items: [code(), amount(), grid()]})));
  assert.equal(find(document, 'Code').maxLength, LIMITS.text); assert.equal(find(document, 'Amount').maxLength, 144);
  assert.match(document.root.textContent, /5 UTF-16 units/); assert.match(document.root.textContent, /host pads with spaces/);
  edit(find(document, 'Code'), 'TOO LONG'); assert.throws(() => view.changes(), {code: 'invalid_input'});
  view.render(model(state(1, {items: [code(), amount(), grid()]}))); assert.equal(find(document, 'Code').value, 'TOO LONG');
});

test('invalid raw date blocks Save, row selection, reference choice and Close before any event', async () => {
  const ref = field('Product', {type: 'FormCatalogRef', scope: 'a'.repeat(32), target: 1, key: null, text: ''});
  let choices = 0;
  const h = host(state(0, {items: [date(), grid(), ref, button('Save')]}), undefined, {onReference() { choices++; }});
  await h.app.ready; edit(find(h.env.document, 'When'), '2023-02-29T12:00:00');
  edit(find(h.env.document, 'Text, row 7'), 'Unsent sibling');
  await h.app.run('command', 'Save'); await h.app.run('select', 'Lines', 7);
  await h.app.reference({action: 'begin', control: 'Product', row: null, column: null}); await h.app.run('close');
  assert.equal(h.requests.length, 1); assert.equal(choices, 0); assert.equal(h.app.hasPending(), true);
  assert.equal(find(h.env.document, 'When').value, '2023-02-29T12:00:00');
  assert.equal(find(h.env.document, 'Text, row 7').value, 'Unsent sibling');
});

test('correction sends one ordinary event per draft then adopts server normalization before Save', async () => {
  const initial = state(0, {items: [date(), amount(), code(), grid(), button('Save')]});
  const h = host(initial, (request, current) => {
    const p = request.params;
    if (p.event !== 'change') return null;
    const value = p.control === 'Amount' ? {type: 'Number', value: '2.50'} : p.control === 'Code' ? {type: 'String', value: 'AB   '} : p.value;
    return {state: {...current, revision: current.revision + 1, items: current.items.map(item => item.name === p.control ? {...item, value} : item)}};
  });
  await h.app.ready; edit(find(h.env.document, 'When'), 'bad date'); await h.app.run('command', 'Save'); assert.equal(h.requests.length, 1);
  edit(find(h.env.document, 'When'), '2024-02-29T12:30:45'); edit(find(h.env.document, 'Amount'), '1.2300');
  edit(find(h.env.document, 'Code'), 'AB'); edit(find(h.env.document, 'Day, row 7'), '2024-02-29');
  await h.app.run('command', 'Save');
  assert.deepEqual(h.requests.slice(1).map(request => [request.params.event, request.params.revision]),
    [['change', 0], ['change', 1], ['change', 2], ['cell', 3], ['command', 4]]);
  assert.equal(h.requests[2].params.value.value, '1.2300'); assert.equal(h.requests[3].params.value.value, 'AB');
  assert.equal(find(h.env.document, 'Amount').value, '2.50'); assert.equal(find(h.env.document, 'Code').value, 'AB   ');
  assert.equal(find(h.env.document, 'Day, row 7').value, '2024-02-29'); assert.equal(h.app.view.hasDrafts(), false);
});

test('typed empty aliases are canonical no-ops and repaint without a synthetic OnChange', async () => {
  const h = host(state(0, {items: [date(), grid()]})); await h.app.ready;
  edit(find(h.env.document, 'When'), '0001-01-01T00:00:00'); await h.app.run('change', 'When');
  edit(find(h.env.document, 'Day, row 7'), '0001-01-01'); await h.app.run('change', {control: 'Lines', row: 7, column: 'Day'});
  assert.equal(h.requests.length, 1); assert.equal(h.app.view.hasDrafts(), false);
  assert.equal(find(h.env.document, 'When').value, ''); assert.equal(find(h.env.document, 'Day, row 7').value, '');
});

test('same-type scalar baseline changes preserve the old raw input only as copyable recovery', () => {
  const {document, view} = create(); view.render(model(state(0, {items: [amount(), button('Save')]})));
  edit(find(document, 'Amount'), 'raw invalid amount');
  view.render(model(state(1, {items: [amount({value: {type: 'Number', value: '2.00'}}), button('Save')]})));
  assert.equal(find(document, 'Amount').value, '2.00'); assert.match(document.root.textContent, /raw invalid amount/);
  assert.equal(find(document, 'Amount').disabled, true); assert.throws(() => view.changes(), {code: 'draft_changed'});
  assert.equal(view.hasDrafts(), true);
});

test('scalar recreation and editor change fence raw drafts even with identical names and values', () => {
  for (const patch of [{controlId: 8}, {editor: {kind: 'number', digits: 6, scale: 2, nonnegative: true}},
    {editor: undefined}, {view: 'label'}]) {
    const {document, view} = create(); view.render(model(state(0, {items: [amount()]})));
    edit(find(document, 'Amount'), '2.00'); const next = amount(patch); if (next.editor === undefined) delete next.editor;
    view.render(model(state(1, {items: [next]})));
    assert.equal(find(document, 'Amount').value, '1.00'); assert.match(document.root.textContent, /Amount: 2.00/);
    assert.throws(() => view.changes(), {code: 'draft_changed'});
  }
});

test('semantically identical editor objects with reordered keys keep the same draft and focus', () => {
  const {document, view} = create(); view.render(model(state(0, {items: [amount()]})));
  const input = edit(find(document, 'Amount'), '2.00'); input.focus(); input.setSelectionRange(1, 3);
  view.render(model(state(1, {items: [amount({editor: {scale: 2, nonnegative: true, kind: 'number', digits: 5}})]})));
  assert.equal(find(document, 'Amount'), input); assert.equal(document.activeElement, input);
  assert.deepEqual(view.changes(), [{control: 'Amount', value: {type: 'Number', value: '2.00'}}]);
});

test('an earlier handler changing a later scalar qualifier stops flush and preserves raw text', async () => {
  const h = host(state(0, {items: [date(), amount(), button('Save')]}), (request, current) => request.params.event === 'change' ?
    {state: {...current, revision: 1, items: [{...date(), value: request.params.value}, amount({editor: {kind: 'number', digits: 6, scale: 2, nonnegative: true}}), button('Save')]}} : null);
  await h.app.ready; edit(find(h.env.document, 'When'), '2024-02-29T00:00:00'); edit(find(h.env.document, 'Amount'), '2.00');
  await h.app.run('command', 'Save'); await h.app.run('command', 'Save');
  assert.equal(h.requests.length, 2); assert.match(h.env.document.root.textContent, /Amount: 2.00/);
  assert.equal(h.app.view.hasDrafts(), true); assert.equal(find(h.env.document, 'Amount').value, '1.00');
});

test('a changed Date column editor never retargets an invalid pending cell to the new parts', () => {
  const {document, view} = create(); view.render(model(state(0, {items: [grid()]})));
  edit(find(document, 'Day, row 7'), '2024-02-30');
  const next = grid(); next.columns[0] = {...next.columns[0], editor: {kind: 'date', parts: 'time'}};
  view.render(model(state(1, {items: [next]})));
  assert.equal(find(document, 'Day, row 7').value, ''); assert.match(document.root.textContent, /2024-02-30/);
  assert.throws(() => view.changes(), {code: 'draft_changed'});
});

test('stale rejected date preserves raw input without replay and copies it aside when base changed', async () => {
  for (const ticks of ['0', '10000']) {
    const h = host(state(0, {items: [date(), button('Save')]}), request => request.params.event === 'change' ?
      {state: state(9, {items: [date('dateTime', ticks), button('Save')]}), error: 'stale_revision'} : null);
    await h.app.ready; edit(find(h.env.document, 'When'), '2024-02-29T12:30:45'); await h.app.run('command', 'Save');
    h.app.repaint(); assert.equal(h.requests.length, 2); assert.equal(h.app.view.hasDrafts(), true);
    if (ticks === '0') assert.equal(find(h.env.document, 'When').value, '2024-02-29T12:30:45');
    else { assert.match(h.env.document.root.textContent, /2024-02-29T12:30:45/); assert.throws(() => h.app.view.changes(), {code: 'draft_changed'}); }
  }
});

test('event_failed with unchanged target keeps submitted input copy-only rather than guessing assignment', async () => {
  const h = host(state(0, {items: [date(), button('Save')]}), request => request.params.event === 'change' ?
    {state: state(1, {items: [date(), button('Save')]}), error: 'event_failed'} : null);
  await h.app.ready; edit(find(h.env.document, 'When'), '2024-02-29T12:30:45'); await h.app.run('command', 'Save');
  await h.app.run('command', 'Save'); assert.equal(h.requests.length, 2);
  assert.equal(find(h.env.document, 'When').value, ''); assert.match(h.env.document.root.textContent, /2024-02-29T12:30:45/);
  assert.throws(() => h.app.view.changes(), {code: 'draft_changed'});
});

test('explicit trusted Discard clears invalid dates and copy-only recovery without sending either draft', async () => {
  const initial = state(0, {items: [date(), button('Discard')], discardCommands: ['Discard']});
  const h = host(initial, (request, current) => request.params.event === 'change' ?
    {state: {...initial, revision: 1, items: [date('dateTime', '10000'), button('Discard')]}, error: 'stale_revision'} :
    request.params.event === 'command' ? {state: {...initial, revision: current.revision + 1}} : null);
  await h.app.ready; edit(find(h.env.document, 'When'), '2024-02-29T00:00:00'); await h.app.run('change', 'When');
  assert.equal(h.app.view.hasDrafts(), true);
  const discard = buttons(h.env.document).find(node => node.textContent === 'Discard'); assert.equal(discard.disabled, false);
  await h.app.run('command', 'Discard'); assert.equal(h.app.view.hasDrafts(), false);
  edit(find(h.env.document, 'When'), 'bad date'); await h.app.run('command', 'Discard');
  assert.deepEqual(h.requests.slice(1).map(request => request.params.event), ['change', 'command', 'command']);
  assert.equal(find(h.env.document, 'When').value, '');
});

test('pending exact date change suppresses duplicate commands and adopts one delayed response', async () => {
  const gate = deferred(); const h = host(state(0, {items: [date(), button('Save')]}), async request => {
    if (request.params.event === 'change') await gate.promise;
  });
  await h.app.ready; edit(find(h.env.document, 'When'), '9999-12-31T23:59:58');
  const pending = h.app.run('command', 'Save'); await h.app.run('command', 'Save');
  assert.equal(h.requests.length, 2); assert.equal(find(h.env.document, 'When').disabled, true);
  gate.resolve(); await pending;
  assert.deepEqual(h.requests.slice(1).map(request => request.params.event), ['change', 'command']);
  assert.equal(find(h.env.document, 'When').value, '9999-12-31T23:59:58'); assert.equal(h.app.view.hasDrafts(), false);
});

test('editing a sibling leaves fractional and MAX table dates unchanged and never emits their ticks', async () => {
  const item = table({columns: [column('Fraction', 'Date', {editor: date().editor}), column('Last', 'Date', {editor: date().editor}), column('Text')],
    rows: [{id: 7, values: [{type: 'Date', ticks: '1'}, {type: 'Date', ticks: LIMITS.dateTicks}, {type: 'String', value: 'Row'}]}]});
  const h = host(state(0, {items: [item, button('Save')]})); await h.app.ready;
  assert.equal(find(h.env.document, 'Fraction, row 7').readOnly, true); assert.equal(find(h.env.document, 'Last, row 7').value, LIMITS.dateTicks);
  edit(find(h.env.document, 'Text, row 7'), 'Changed'); await h.app.run('command', 'Save');
  assert.deepEqual(h.current.items[0].rows[0].values.slice(0, 2), item.rows[0].values.slice(0, 2));
  assert.equal(h.requests[1].params.column, 'Text'); assert.equal(find(h.env.document, 'Fraction, row 7').value, '1');
});

test('retired scalar and cell DOM callbacks cannot write or flush a replacement control', () => {
  const document = new FakeDocument(), calls = [];
  const view = createFormView(document, document.root, {change(value) { calls.push(value); }, select() {}, action() {}, refresh() {}});
  view.render(model(state(0, {items: [date(), grid()]})));
  const oldField = find(document, 'When'), oldCell = find(document, 'Day, row 7');
  view.render(model(state(1, {items: [date('dateTime', '0', {controlId: 9}), {...grid(), controlId: 10, tableId: 2}]})));
  for (const node of [oldField, oldCell]) { edit(node, '2024-02-29'); node.emit('blur'); node.emit('keydown', {key: 'Enter'}); }
  assert.equal(view.hasDrafts(), false); assert.deepEqual(calls, []);
  assert.equal(find(document, 'When').value, ''); assert.equal(find(document, 'Day, row 7').value, '');
});

test('failed unchanged cell assignment keeps raw text copy-only and does not release queued selection', async () => {
  const initial = state(0, {items: [grid(), button('Save')]});
  const h = host(initial, request => request.params.event === 'cell' ? {state: {...initial, revision: 1}, error: 'event_failed'} : null);
  await h.app.ready; edit(find(h.env.document, 'Day, row 7'), '2024-02-29'); await h.app.run('select', 'Lines', 7);
  assert.equal(h.requests.length, 2); assert.match(h.env.document.root.textContent, /Lines, row 7, Day: 2024-02-29/);
  assert.equal(find(h.env.document, 'Day, row 7').value, ''); assert.throws(() => h.app.view.changes(), {code: 'draft_changed'});
});
