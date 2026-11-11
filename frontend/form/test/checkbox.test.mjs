import test from 'node:test';
import assert from 'node:assert/strict';
import {mountForm} from '../src/app.mjs';
import {field, button, table, state, reply, response, deferred} from './fixtures.mjs';
import {all, environment} from './fake-dom.mjs';

const flag = (extra = {}) => field('Active', {type: 'Boolean', value: false}, extra);
const amount = () => field('Amount', {type: 'Number', value: '1.00'});
const initial = () => state(0, {items: [amount(), flag(), button()]});
const control = (env, name) => all(env.document.root).find(node => node.tagName === 'INPUT' && node.getAttribute('aria-label') === name);
const edit = (node, value) => { node.value = value; node.emit('input'); };
const settle = () => new Promise(resolve => setTimeout(resolve, 0));
function apply(current, request) {
  const p = request.params;
  if (request.method !== 'form.event') return current;
  return {...current, revision: current.revision + 1, items: current.items.map(item => {
    if (item.name !== p.control) return item;
    if (p.event === 'change') return {...item, value: p.value};
    if (p.event === 'cell') return {...item, currentRow: p.row, rows: item.rows.map(row => row.id !== p.row ? row :
      {...row, values: row.values.map((value, index) => item.columns[index].name === p.column ? p.value : value)})};
    return item;
  })};
}
function host(snapshot = initial(), handle = () => null, options = {}) {
  const requests = []; let current = snapshot;
  const env = environment(async (_, settings) => {
    const request = JSON.parse(settings.body); requests.push(request);
    const result = await handle(request, current);
    current = result?.state || apply(current, request);
    if (result?.lost) throw Error('Lost response');
    return response(reply(request, current, result?.error || null));
  });
  const app = mountForm(env, env.document.root, options);
  return {app, env, requests};
}
function transition(source, checkbox, {label = false, keyboard = false} = {}) {
  // Model native ordering explicitly: pointerdown/focus transfer causes text
  // blur before the checkbox's default activation emits input and change.
  const target = label ? checkbox.parentNode.children[0] : checkbox;
  if (!keyboard) target.emit('pointerdown', {bubbles: true});
  if (label) target.emit('pointerup', {bubbles: true});
  source.emit('blur', {relatedTarget: label ? null : checkbox});
  assert.equal(checkbox.disabled, false, 'source blur must not disable the activation target');
  checkbox.focus();
  if (!keyboard && !label) target.emit('pointerup', {bubbles: true});
  checkbox.checked = !checkbox.checked; checkbox.emit('input'); checkbox.emit('change');
}

test('scalar checkbox pointer and label clicks preserve intent and serialize text before one toggle', async () => {
  for (const label of [false, true]) {
    const gate = deferred();
    const {app, env, requests} = host(initial(), async request => {
      if (request.params.event === 'change' && request.params.control === 'Amount') await gate.promise;
    });
    await app.ready; const source = control(env, 'Amount'), checkbox = control(env, 'Active');
    edit(source, '10'); transition(source, checkbox, {label});
    assert.equal(requests.length, 2); assert.equal(checkbox.checked, true); assert.equal(checkbox.disabled, true);
    checkbox.emit('change'); await app.run('toggle', 'Active'); assert.equal(requests.length, 2);
    gate.resolve(); await settle();
    assert.deepEqual(requests.slice(1).map(request => request.params), [
      {event: 'change', revision: 0, control: 'Amount', value: {type: 'Number', value: '10'}},
      {event: 'change', revision: 1, control: 'Active', value: {type: 'Boolean', value: true}},
    ]);
    assert.equal(checkbox.checked, true); assert.equal(checkbox.disabled, false); assert.equal(app.view.hasDrafts(), false);
  }
});

test('keyboard text-to-checkbox transition applies prior draft before earlier-declared checkbox', async () => {
  const {app, env, requests} = host(state(0, {items: [flag(), amount(), button()]})); await app.ready;
  const source = control(env, 'Amount'), checkbox = control(env, 'Active'); edit(source, '2.50');
  transition(source, checkbox, {keyboard: true}); await settle();
  assert.deepEqual(requests.slice(1).map(request => [request.params.control, request.params.revision]), [['Amount', 0], ['Active', 1]]);
  assert.equal(checkbox.checked, true); assert.equal(app.view.hasDrafts(), false);
});

test('leaving a table text cell for scalar checkbox flushes every scalar and cell draft', async () => {
  const {app, env, requests} = host(state(0, {items: [flag(), amount(), table(), button()]})); await app.ready;
  const source = control(env, 'Description, row 1'), checkbox = control(env, 'Active');
  edit(control(env, 'Amount'), '3.75'); edit(source, 'Changed cell'); transition(source, checkbox); await settle();
  assert.deepEqual(requests.slice(1).map(request => [request.params.event, request.params.control, request.params.revision]),
    [['change', 'Amount', 0], ['cell', 'Lines', 1], ['change', 'Active', 2]]);
  assert.equal(requests[2].params.row, 1); assert.equal(requests[2].params.column, 'Description');
});

test('scalar or table text to table checkbox flushes prior drafts and preserves exact row identity', async () => {
  for (const sourceName of ['Amount', 'Description, row 1']) {
    const {app, env, requests} = host(state(0, {items: [table(), amount(), button()]})); await app.ready;
    edit(control(env, 'Amount'), '5'); edit(control(env, 'Description, row 1'), 'First draft');
    const checkbox = control(env, 'Active, row 2'); transition(control(env, sourceName), checkbox); await settle();
    assert.deepEqual(requests.slice(1).map(request => request.params), [
      {event: 'cell', revision: 0, control: 'Lines', row: 1, column: 'Description', value: {type: 'String', value: 'First draft'}},
      {event: 'change', revision: 1, control: 'Amount', value: {type: 'Number', value: '5'}},
      {event: 'cell', revision: 2, control: 'Lines', row: 2, column: 'Active', value: {type: 'Boolean', value: true}},
    ]);
    assert.equal(checkbox.checked, true); assert.equal(app.view.hasDrafts(), false);
  }
});

test('checkbox intent prevalidates all scalar and table drafts without losing invalid local input', async () => {
  for (const invalid of ['Amount', 'Quantity, row 1']) {
    const {app, env, requests} = host(state(0, {items: [flag(), amount(), table(), button()]})); await app.ready;
    edit(control(env, 'Amount'), '7'); edit(control(env, invalid), 'bad decimal');
    const checkbox = control(env, 'Active'); transition(control(env, invalid), checkbox); await settle();
    assert.equal(requests.length, 1); assert.equal(checkbox.checked, true); assert.equal(control(env, invalid).value, 'bad decimal');
    assert.equal(app.view.hasDrafts(), true); assert.ok(env.document.root.textContent.includes('supported value'));
    edit(control(env, invalid), '8'); await app.run('command', 'Run');
    assert.equal(requests.filter(request => request.params.control === 'Active').length, 1);
    assert.equal(requests.at(-1).params.event, 'command'); assert.equal(app.view.hasDrafts(), false);
  }
});

test('failed preceding handler stops before checkbox while retaining authoritative effects and pending toggle', async () => {
  const {app, env, requests} = host(initial(), (request, current) => request.params.control === 'Amount'
    ? {state: apply(current, request), error: 'event_failed'} : null);
  await app.ready; const source = control(env, 'Amount'), checkbox = control(env, 'Active'); edit(source, '9');
  transition(source, checkbox); await settle();
  assert.equal(requests.length, 2); assert.equal(source.value, '9'); assert.equal(checkbox.checked, true);
  assert.equal(app.client.snapshot.items.find(item => item.name === 'Active').value.value, false);
  assert.equal(app.view.hasDrafts(), true); assert.ok(env.document.root.textContent.includes('Completed changes'));
});

test('lost preceding response locks pending checkbox and explicit snapshot never replays the toggle', async () => {
  const {app, env, requests} = host(initial(), request => request.params.control === 'Amount' ? {lost: true} : null);
  await app.ready; const source = control(env, 'Amount'), checkbox = control(env, 'Active'); edit(source, '9');
  transition(source, checkbox); await settle();
  await app.run('toggle', 'Active'); assert.equal(requests.length, 2); assert.equal(app.client.locked, true);
  assert.equal(checkbox.disabled, true); assert.equal(app.view.hasDrafts(), true);
  await app.refresh(); await settle();
  assert.deepEqual(requests.map(request => request.method), ['form.hello', 'form.event', 'form.snapshot']);
  assert.equal(checkbox.checked, false); assert.equal(source.value, '9'); assert.equal(app.client.locked, false);
});

test('earlier handler replacing checkbox table or deleting its row stops without retargeting', async () => {
  for (const replacement of [item => ({...item, tableId: 2}), item => ({...item, rows: item.rows.filter(row => row.id !== 2)})]) {
    const {app, env, requests} = host(state(0, {items: [amount(), table(), button()]}), (request, current) => request.params.control === 'Amount'
      ? {state: {...apply(current, request), items: apply(current, request).items.map(item => item.kind === 'table' ? replacement(item) : item)}} : null);
    await app.ready; const source = control(env, 'Amount'), checkbox = control(env, 'Active, row 2'); edit(source, '11');
    transition(source, checkbox); await settle();
    assert.equal(requests.length, 2); assert.equal(app.client.locked, false);
    assert.ok(env.document.root.textContent.includes('changed')); assert.equal(requests.some(request => request.params.event === 'cell'), false);
  }
});

test('disabled, hidden, read-only or inactive checkbox cannot flush another pending input', async () => {
  for (const patch of [{enabled: false}, {visible: false}, {readOnly: true}]) {
    const {app, env, requests} = host(state(0, {items: [amount(), flag(patch), button()]})); await app.ready;
    edit(control(env, 'Amount'), '4'); const checkbox = control(env, 'Active'); checkbox.checked = true;
    checkbox.emit('input'); checkbox.emit('change'); await settle(); assert.equal(requests.length, 1);
  }
  const {app, env, requests} = host(initial(), () => null, {isActive: () => false}); await app.ready;
  edit(control(env, 'Amount'), '4'); const checkbox = control(env, 'Active'); checkbox.checked = true;
  checkbox.emit('input'); checkbox.emit('change'); await settle(); assert.equal(requests.length, 1); assert.equal(app.view.hasDrafts(), true);
});

test('cancelled checkbox pointer does not suppress a later ordinary text blur', async () => {
  const {app, env, requests} = host(); await app.ready;
  const source = control(env, 'Amount'), checkbox = control(env, 'Active'); edit(source, '4');
  checkbox.emit('pointerdown', {bubbles: true}); checkbox.emit('pointercancel', {bubbles: true});
  source.emit('blur'); await settle();
  assert.deepEqual(requests.slice(1).map(request => request.params.control), ['Amount']); assert.equal(checkbox.checked, false);
});
