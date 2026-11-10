import test from 'node:test';
import assert from 'node:assert/strict';
import {validateSnapshot, LIMITS} from '../src/client.mjs';
import {mountForm} from '../src/app.mjs';
import {field, button, table, state, reply, response, deferred} from './fixtures.mjs';
import {all, input, buttons, environment} from './fake-dom.mjs';

const snapshot = (revision = 0, extra = {}) => state(revision, {
  items: [field('Amount', {type: 'Number', value: '1.00'}), table(), button('Discard'), button('Save')],
  discardCommands: ['Discard'], dirty: false, ...extra,
});
const edit = (node, value) => { node.value = value; node.emit('input'); };
const cell = document => all(document.root).find(node => node.tagName === 'INPUT' && node.getAttribute('aria-label') === 'Quantity, row 1');
const unload = env => {
  const event = {prevented: false, preventDefault() { this.prevented = true; }};
  env.listeners.get('beforeunload')(event); return event;
};
function host(initial = snapshot(), handle = request => ({state: snapshot(request.id - 1)})) {
  const requests = [];
  const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    const result = request.method === 'form.hello' ? {state: initial} : await handle(request);
    return response(reply(request, result.state, result.error || null));
  });
  const app = mountForm(env, env.document.root);
  return {app, env, requests};
}

test('optional discard and dirty metadata preserve legacy snapshots and accept the bounded button policy', () => {
  const legacy = state(); assert.equal(validateSnapshot(legacy), legacy);
  assert.equal(validateSnapshot(snapshot()).dirty, false);
  assert.equal(validateSnapshot(snapshot(0, {dirty: true})).dirty, true);
  assert.deepEqual(validateSnapshot(state(0, {discardCommands: []})).discardCommands, []);
  const names = Array.from({length: LIMITS.discardCommands}, (_, i) => 'Discard' + i);
  assert.deepEqual(validateSnapshot(state(0, {items: names.map(button), discardCommands: names})).discardCommands, names);
});

test('discard policy rejects malformed, duplicate, unresolved, non-button and excess entries', () => {
  for (const discardCommands of [null, undefined, false, {}, 'Discard', [null], [42], [''], ['\ud800'],
    ['x'.repeat(8193)], ['Discard', 'Discard'], ['Missing'], ['Amount'], ['Lines'], Array(65).fill('Discard')]) {
    assert.throws(() => validateSnapshot(snapshot(0, {discardCommands})), {code: 'transport'});
  }
  for (const dirty of [undefined, null, 0, 1, 'true', {}, []]) {
    assert.throws(() => validateSnapshot(snapshot(0, {dirty})), {code: 'transport'});
  }
  assert.throws(() => validateSnapshot(snapshot(0, {discard: ['Discard']})), {code: 'transport'});
});

test('trusted discard bypasses invalid scalar and cell decimals and sends only one command', async () => {
  const gate = deferred();
  const {app, env, requests} = host(snapshot(), async () => { await gate.promise; return {state: snapshot(1)}; });
  await app.ready; edit(input(env.document), 'not a decimal'); edit(cell(env.document), '1,20');
  const pending = app.run('command', 'Discard'); await app.run('command', 'Discard');
  assert.equal(app.view.hasDrafts(), true); assert.equal(requests.length, 2);
  assert.ok(buttons(env.document).filter(node => node.dataset.formAction !== 'refresh').every(node => node.disabled));
  gate.resolve(); await pending;
  assert.deepEqual(requests.slice(1).map(request => request.params), [{event: 'command', revision: 0, control: 'Discard'}]);
  assert.equal(app.view.hasDrafts(), false); assert.equal(input(env.document).value, '1.00'); assert.equal(cell(env.document).value, '1.00');
});

test('untrusted similarly named commands and Close still validate all raw drafts', async () => {
  const {app, env, requests} = host(snapshot(0, {items: [...snapshot().items, button('DiscardAll')]}));
  await app.ready; edit(cell(env.document), 'bad');
  await app.run('command', 'DiscardAll'); await app.run('command', 'Save'); await app.run('close');
  assert.equal(requests.length, 1); assert.equal(app.view.hasDrafts(), true);
  assert.ok(env.document.root.textContent.includes('supported value'));
});

test('legacy command named Discard has no implicit draft-discard permission', async () => {
  const initial = snapshot(); delete initial.discardCommands;
  const {app, env, requests} = host(initial); await app.ready; edit(input(env.document), 'bad');
  await app.run('command', 'Discard'); assert.equal(requests.length, 1); assert.equal(app.view.hasDrafts(), true);
});

test('recoverable discard failure clears raw drafts but preserves authoritative dirty buffer', async () => {
  const {app, env, requests} = host(snapshot(0, {dirty: true}), () => ({state: snapshot(1, {dirty: true}), error: 'event_failed'}));
  await app.ready; edit(input(env.document), 'bad'); edit(cell(env.document), 'bad'); await app.run('command', 'Discard');
  assert.equal(requests.length, 2); assert.equal(app.view.hasDrafts(), false); assert.equal(app.client.locked, false);
  assert.equal(input(env.document).value, '1.00'); assert.equal(cell(env.document).value, '1.00');
  assert.ok(env.document.root.textContent.includes('Completed changes')); assert.equal(unload(env).prevented, true);
});

test('lost or malformed discard response preserves drafts and locks further actions without replay', async () => {
  for (const handle of [() => { throw Error('lost'); }, () => ({state: snapshot(1, {discardCommands: ['Missing']})})]) {
    const {app, env, requests} = host(snapshot(), handle); await app.ready; edit(input(env.document), 'bad'); edit(cell(env.document), 'bad');
    await app.run('command', 'Discard'); await app.run('command', 'Discard');
    assert.equal(requests.length, 2); assert.equal(app.view.hasDrafts(), true); assert.equal(app.client.locked, true);
    assert.equal(input(env.document).value, 'bad'); assert.equal(cell(env.document).value, 'bad'); assert.equal(unload(env).prevented, true);
  }
});

test('discard cannot bypass unavailable buttons or locked sessions', async () => {
  for (const patch of [{enabled: false}, {visible: false}, {readOnly: true}]) {
    const initial = snapshot(); initial.items[2] = {...initial.items[2], ...patch};
    const {app, env, requests} = host(initial); await app.ready; edit(input(env.document), 'bad');
    await app.run('command', 'Discard'); assert.equal(requests.length, 1); assert.equal(app.view.hasDrafts(), true);
  }
  const {app, requests} = host(snapshot(0, {kind: 'closed', lifecycle: 'closed'})); await app.ready;
  await app.run('command', 'Discard'); assert.equal(requests.length, 1);
});

test('authoritative dirty state guards browser exit after applied edits and clears only on clean snapshot', async () => {
  let current = snapshot();
  const {app, env} = host(current, request => {
    current = snapshot(request.id - 1, {dirty: request.params.event !== 'command'});
    return {state: current};
  });
  await app.ready; assert.equal(unload(env).prevented, false);
  edit(input(env.document), '2.00'); assert.equal(unload(env).prevented, true);
  await app.run('change', 'Amount'); assert.equal(app.view.hasDrafts(), false);
  assert.equal(unload(env).prevented, true); assert.equal(unload(env).returnValue, '');
  await app.run('command', 'Save'); assert.equal(unload(env).prevented, false);
});

test('discard then record switch cannot leak scalar or cell drafts with reused identities and values', async () => {
  const {app, env, requests} = host(snapshot(), request => ({state: snapshot(request.id - 1)}));
  await app.ready; edit(input(env.document), '99.00'); edit(cell(env.document), '88.00');
  await app.run('command', 'Discard'); await app.run('select', 'Lines', 2); await app.run('command', 'Save');
  assert.deepEqual(requests.slice(1).map(request => request.params.event), ['command', 'select', 'command']);
  assert.equal(input(env.document).value, '1.00'); assert.equal(cell(env.document).value, '1.00');
  assert.equal(app.view.hasDrafts(), false);
});

test('pending save blocks discard, record selection and duplicate save until authoritative completion', async () => {
  const gate = deferred();
  const {app, env, requests} = host(snapshot(0, {dirty: true}), async () => { await gate.promise; return {state: snapshot(1)}; });
  await app.ready; const pending = app.run('command', 'Save');
  await app.run('command', 'Discard'); await app.run('select', 'Lines', 2); await app.run('command', 'Save');
  assert.equal(requests.length, 2); assert.equal(unload(env).prevented, true);
  gate.resolve(); await pending; assert.equal(unload(env).prevented, false);
  assert.deepEqual(requests.slice(1).map(request => request.params.control), ['Save']);
});


test('inner server transport uncertainty preserves raw discard drafts even with a valid HTTP snapshot', async () => {
  const {app, env, requests} = host(snapshot(0, {dirty: true}), () => ({state: snapshot(1, {dirty: true, uncertain: true}), error: 'outcome_unknown'}));
  await app.ready; edit(input(env.document), 'bad decimal'); edit(cell(env.document), 'invalid');
  await app.run('command', 'Discard'); await app.run('command', 'Discard');
  assert.equal(requests.length, 2); assert.equal(app.client.transportFailed, false);
  assert.equal(app.client.outcomeUnknown, true); assert.equal(app.client.locked, true);
  assert.equal(app.view.hasDrafts(), true); assert.equal(input(env.document).value, 'bad decimal');
  assert.equal(cell(env.document).value, 'invalid'); assert.equal(unload(env).prevented, true);
});
