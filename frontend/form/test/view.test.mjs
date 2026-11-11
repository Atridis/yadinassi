import test from 'node:test';
import assert from 'node:assert/strict';
import {createFormView} from '../src/view.mjs';
import {mountForm} from '../src/app.mjs';
import {field, button, state, reply, response, deferred} from './fixtures.mjs';
import {FakeDocument, all, input, buttons, environment} from './fake-dom.mjs';
const model = (snapshot, extra = {}) => ({snapshot, busy: false, locked: false, error: '', connected: true,
  outcomeUnknown: false, transportFailed: false, exhausted: false, ...extra});
const handlers = {change() {}, action() {}, refresh() {}};
const create = () => { const document = new FakeDocument(); return {document, view: createFormView(document, document.root, handlers)}; };
const edit = (document, value) => { const node = input(document); node.value = value; node.emit('input'); return node; };

test('renderer treats hostile names, labels, values and messages as text only', () => {
  const {document, view} = create();
  const hostile = '<img src=x onerror=alert(1)> & "';
  view.render(model(state(0, {title: hostile, messages: [hostile], items: [field('__proto__', {type: 'String', value: hostile}), {...button('constructor'), title: hostile}]})));
  assert.equal(input(document).value, hostile); assert.ok(document.root.textContent.includes(hostile));
  assert.equal(input(document).getAttribute('aria-label'), '__proto__');
  assert.equal(document.getElementById(input(document).getAttribute('aria-describedby')).textContent,
    'Applied when you leave the field or run a command');
  assert.equal(all(document.root).some(node => node.tagName === 'IMG' || node.tagName === 'SCRIPT'), false);
  edit(document, 'Safe'); assert.deepEqual(view.changes(), [{control: '__proto__', value: {type: 'String', value: 'Safe'}}]);
});

test('keyed input identity, focus and selection survive busy response and normalization', () => {
  const {document, view} = create(); const initial = state(); view.render(model(initial));
  const original = edit(document, 'Edited'); original.focus(); original.setSelectionRange(2, 5, 'backward');
  view.render(model(initial, {busy: true})); assert.equal(original.disabled, true);
  view.accept('Name'); view.render(model(state(1, {items: [field('Name', {type: 'String', value: 'Edit'}), button()]})));
  assert.equal(input(document), original); assert.equal(document.activeElement, original);
  assert.equal(original.value, 'Edit'); assert.equal(original.selectionStart, 2); assert.equal(original.selectionEnd, 4);
  assert.equal(original.selectionDirection, 'backward');
});

test('response does not steal focus from another active control', () => {
  const {document, view} = create(); view.render(model(state()));
  input(document).focus(); view.render(model(state(), {busy: true}));
  const outside = document.createElement('button'); document.body.append(outside); outside.focus();
  view.render(model(state(1))); assert.equal(document.activeElement, outside);
});

test('draft reconciliation preserves other input but adopts accepted field effects', () => {
  const {document, view} = create(); const initial = state(0, {items: [field(), field('Other')]}); view.render(model(initial));
  const fields = all(document.root).filter(node => node.tagName === 'INPUT');
  fields[0].value = 'First'; fields[0].emit('input'); fields[1].value = 'Second'; fields[1].emit('input');
  view.accept('Name'); view.render(model(state(1, {items: [field('Name', {type: 'String', value: 'Normalized'}), field('Other')]})));
  assert.equal(fields[0].value, 'Normalized'); assert.equal(fields[1].value, 'Second');
  assert.deepEqual(view.changes(), [{control: 'Other', value: {type: 'String', value: 'Second'}}]);
});

test('removed or disabled fields retain copy-only drafts and cannot be retargeted', () => {
  const {document, view} = create(); view.render(model(state())); edit(document, 'Pending');
  view.render(model(state(1, {items: [field('Different')]}))); assert.equal(view.hasDrafts(), true);
  assert.ok(document.root.textContent.includes('Name: Pending')); assert.throws(() => view.changes(), {code: 'draft_changed'});
  view.clearDrafts(); view.render(model(state(1, {items: [field('Different')]})));
  edit(document, 'Other'); view.render(model(state(2, {items: [field('Different', {type: 'String', value: 'Host'}, {enabled: false})]})));
  assert.equal(view.hasDrafts(), true); assert.equal(input(document).value, 'Host'); assert.equal(input(document).disabled, true);
  assert.ok(document.root.textContent.includes('Different: Other'));
});

test('Date and empty scalars are read-only and closed state hides all controls', () => {
  const {document, view} = create(); view.render(model(state(0, {items: [field('When', {type: 'Date', ticks: '3155378975990000'}), field('Empty', {type: 'Null'})]})));
  const fields = all(document.root).filter(node => node.tagName === 'INPUT');
  assert.equal(fields[0].value, '3155378975990000'); assert.equal(fields[0].readOnly, true); assert.equal(fields[1].readOnly, true);
  assert.ok(document.root.textContent.includes('no timezone conversion'));
  view.render(model(state(1, {kind: 'closed', lifecycle: 'cancelled'}), {locked: true}));
  assert.equal(input(document).closest('[hidden]') !== null, true); assert.ok(document.root.textContent.includes('cancelled'));
});

test('blur into a command and pointer command transition defer change to flush', () => {
  const document = new FakeDocument(), calls = [];
  const view = createFormView(document, document.root, {change: name => calls.push(name), action() {}, refresh() {}});
  view.render(model(state())); const node = edit(document, 'Changed'); const command = buttons(document).find(button => button.dataset.formAction === 'command');
  node.emit('blur', {relatedTarget: command}); assert.deepEqual(calls, []);
  command.emit('pointerdown', {bubbles: true}); node.emit('blur'); assert.deepEqual(calls, []);
  command.emit('pointercancel', {bubbles: true}); node.emit('blur'); assert.deepEqual(calls, ['Name']);
});

test('edit then immediate repeated command flushes once before command at next revision', async () => {
  const requests = [], pending = deferred(); let current = state();
  const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    if (request.params.event === 'change') {
      current = state(1, {items: [field('Name', request.params.value), button()]});
      await pending.promise;
    } else if (request.params.event === 'command') current = {...current, revision: 2};
    return response(reply(request, current));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Changed');
  const first = app.run('command', 'Run'); await app.run('command', 'Run');
  assert.equal(requests.length, 2); assert.equal(input(env.document).disabled, true);
  pending.resolve(); await first;
  assert.deepEqual(requests.slice(1).map(request => request.params), [
    {event: 'change', revision: 0, control: 'Name', value: {type: 'String', value: 'Changed'}},
    {event: 'command', revision: 1, control: 'Run'},
  ]); assert.equal(input(env.document).value, 'Changed'); assert.equal(input(env.document).disabled, false);
});

test('Close flushes field edits before close and does not leave an active form', async () => {
  const requests = []; let current = state();
  const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    if (request.params.event === 'change') current = state(1, {items: [field('Name', request.params.value), button()]});
    if (request.params.event === 'close') current = {...current, revision: 2, kind: 'closed', lifecycle: 'closed'};
    return response(reply(request, current));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Final'); await app.run('close');
  assert.deepEqual(requests.slice(1).map(request => [request.params.event, request.params.revision]), [['change', 0], ['close', 1]]);
  assert.equal(app.client.locked, true); assert.equal(input(env.document).closest('[hidden]') !== null, true);
});

test('failed flush stops before command, displays authoritative effects and finite error', async () => {
  const requests = []; const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    return response(reply(request, request.id === 1 ? state() : state(1, {items: [field('Name', {type: 'String', value: 'Changed before failure'}), button()]}),
      request.id === 1 ? null : 'event_failed'));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Changed'); await app.run('command', 'Run');
  assert.equal(requests.length, 2); assert.equal(input(env.document).value, 'Changed before failure');
  assert.ok(env.document.root.textContent.includes('Completed changes')); assert.equal(app.view.hasDrafts(), false);
});

test('lost flush response blocks command and explicit refresh never replays writes', async () => {
  const requests = []; const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    if (request.params.event === 'change') throw Error('connection lost');
    return response(reply(request, state(request.id === 1 ? 0 : 1, {items: [field('Name', {type: 'String', value: request.id === 1 ? 'Original' : 'Applied once'}), button()]})));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Pending'); await app.run('command', 'Run');
  await app.run('command', 'Run'); assert.equal(requests.length, 2); assert.equal(input(env.document).disabled, true);
  await app.refresh(); assert.deepEqual(requests.map(request => request.method), ['form.hello', 'form.event', 'form.snapshot']);
  assert.equal(input(env.document).value, 'Applied once'); assert.equal(app.client.locked, false);
});

test('authoritative unknown outcome keeps commands and Close disabled after refresh', async () => {
  const requests = []; const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    return response(reply(request, state(1, {uncertain: true}), 'outcome_unknown'));
  });
  const app = mountForm(env, env.document.root); await app.ready; await app.refresh(); await app.run('command', 'Run');
  assert.deepEqual(requests.map(request => request.method), ['form.hello', 'form.snapshot']);
  assert.ok(buttons(env.document).filter(node => node.dataset.formAction !== 'refresh').every(node => node.disabled));
  assert.ok(env.document.root.textContent.includes('cannot unlock'));
});

test('stale draft failure adopts latest host value and needs new user intent', async () => {
  const requests = []; const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    return response(reply(request, request.id === 1 ? state() : state(7, {items: [field('Name', {type: 'String', value: 'Other client'}), button()]}), request.id === 2 ? 'stale_revision' : null));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Outdated'); await app.run('command', 'Run');
  assert.equal(requests.length, 2); assert.equal(input(env.document).value, 'Other client'); assert.equal(app.client.snapshot.revision, 7);
  assert.ok(env.document.root.textContent.includes('Name: Outdated')); assert.equal(app.view.hasDrafts(), true);
  assert.throws(() => app.view.changes(), {code: 'draft_changed'});
});

test('same-document reattach is read-only and capabilities never enter storage or DOM', async () => {
  const requests = [], tokens = []; const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request); tokens.push(options.headers['X-Yadinassi-Session']); return response(reply(request));
  });
  Object.defineProperty(env, 'localStorage', {get() { throw Error('Storage forbidden'); }});
  Object.defineProperty(env, 'sessionStorage', {get() { throw Error('Storage forbidden'); }});
  const app = mountForm(env, env.document.root); await app.ready; await app.reattach();
  assert.deepEqual(requests.map(request => request.method), ['form.hello', 'form.hello']);
  assert.deepEqual(env.historyCalls, [[null, '', '/'], [null, '', '/']]); assert.equal(tokens[0], 'a'.repeat(43));
  assert.equal(env.document.root.textContent.includes(tokens[0]), false);
});

test('reattach during an in-flight action waits for completion without replaying it', async () => {
  const requests = [], pending = deferred(); const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    if (request.params.event === 'command') await pending.promise;
    return response(reply(request, state(request.id === 1 ? 0 : 1)));
  });
  const app = mountForm(env, env.document.root); await app.ready; const command = app.run('command', 'Run');
  env.location.hash = '#session=' + 'b'.repeat(43); await app.reattach(); assert.equal(requests.length, 2);
  pending.resolve(); await command; await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(requests.map(request => request.method), ['form.hello', 'form.event', 'form.hello']);
});

test('missing capability causes no network request and beforeunload only warns for pending work', async () => {
  const env = environment(() => { throw Error('No network expected'); }); env.location.hash = '';
  const app = mountForm(env, env.document.root); await app.ready;
  assert.equal(app.client, null); assert.ok(env.document.root.textContent.includes('Reopen the complete URL'));
  let prevented = false; env.listeners.get('beforeunload')({preventDefault() { prevented = true; }}); assert.equal(prevented, false);
});
