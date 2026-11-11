import test from 'node:test';
import assert from 'node:assert/strict';
import {validateSnapshot} from '../src/client.mjs';
import {createFormView} from '../src/view.mjs';
import {mountForm} from '../src/app.mjs';
import {field, button, state, reply, response, deferred, table} from './fixtures.mjs';
import {FakeDocument, all, buttons, environment} from './fake-dom.mjs';

const group = (name, parent, layoutKind, controlId, extra = {}) => ({name, parent, kind: 'group', layoutKind,
  controlId, title: name, orientation: 'vertical', showTitle: true, visible: true, enabled: true, readOnly: false, ...extra});
const layout = () => state(0, {items: [group('Container', '', 'group', 10), group('Sections', 'Container', 'pages', 11),
  group('First', 'Sections', 'page', 12), group('Names', 'First', 'group', 13, {orientation: 'horizontal'}),
  {...field('Name', undefined, {controlId: 14}), parent: 'Names'}, {...button('SaveFirst'), parent: 'First'},
  group('Second', 'Sections', 'page', 15), {...field('Notes', undefined, {controlId: 16}), parent: 'Second'},
  {...button('SaveSecond'), parent: 'Second'}, {...button('Global'), parent: ''}]});
const model = (snapshot, extra = {}) => ({snapshot, busy: false, locked: false, error: '', connected: true,
  outcomeUnknown: false, transportFailed: false, exhausted: false, ...extra});
const input = (doc, label) => all(doc.root).find(node => node.tagName === 'INPUT' && node.getAttribute('aria-label') === label);
const tab = (doc, label) => buttons(doc).find(node => node.getAttribute('role') === 'tab' && node.textContent === label);
const setup = () => { const document = new FakeDocument(), calls = []; const view = createFormView(document, document.root,
  {change: name => calls.push(['change', name]), action: (event, name) => calls.push([event, name]), refresh() {}, select() {}});
  view.render(model(layout())); return {document, view, calls}; };
const edit = (doc, label, text) => { const node = input(doc, label); node.value = text; node.emit('input'); return node; };

test('layout protocol admits ordered groups, nested pages and ordinary controls', () => {
  assert.equal(validateSnapshot(layout()).items.length, 10);
});

test('layout protocol refuses missing, cyclic, forward or non-group parents', () => {
  for (const mutate of [s => delete s.items[4].parent, s => s.items[0].parent = 'Names',
    s => s.items[7].parent = 'Notes', s => s.items[7].parent = 'Name', s => s.items[4].parent = 'Second']) {
    const snapshot = layout(); mutate(snapshot); assert.throws(() => validateSnapshot(snapshot), {code: 'transport'});
  }
});

test('layout protocol rejects invalid page structures and unknown group behavior', () => {
  for (const mutate of [s => s.items[2].parent = '', s => s.items[3].parent = 'Sections',
    s => s.items[1].currentPage = 'First', s => s.items[1].orientation = 'horizontal',
    s => s.items[3].orientation = 'absolute', s => s.items[3].controlId = 10]) {
    const snapshot = layout(); mutate(snapshot); assert.throws(() => validateSnapshot(snapshot), {code: 'transport'});
  }
  const empty = state(0, {items: [group('Empty', '', 'pages', 1)]});
  assert.throws(() => validateSnapshot(empty), {code: 'transport'});
});

test('layout protocol requires authoritative inherited restrictions', () => {
  for (const [key, value] of [['visible', false], ['enabled', false], ['readOnly', true]]) {
    const snapshot = layout(); snapshot.items[0][key] = value;
    assert.throws(() => validateSnapshot(snapshot), {code: 'transport'});
    snapshot.items.filter(item => item.name !== 'Global').forEach(item => item[key] = value);
    validateSnapshot(snapshot);
  }
});

test('nested renderer preserves declared order, group titles and correct tab-panel links', () => {
  const {document} = setup();
  const first = tab(document, 'First'), second = tab(document, 'Second');
  assert.equal(first.getAttribute('aria-selected'), 'true'); assert.equal(second.getAttribute('aria-selected'), 'false');
  const panel = document.getElementById(first.getAttribute('aria-controls'));
  assert.equal(panel.getAttribute('role'), 'tabpanel'); assert.equal(panel.getAttribute('aria-labelledby'), first.id);
  assert.ok(panel.contains(input(document, 'Name'))); assert.ok(input(document, 'Notes').closest('[hidden]'));
  assert.equal(input(document, 'Name').parentNode.parentNode.className, 'group-content orientation-horizontal');
  assert.equal(document.root.textContent.includes('Names'), true);
});

test('page switching preserves exact raw drafts, node identity, selection and sends no event', () => {
  const {document, view, calls} = setup(); const node = edit(document, 'Name', 'raw pending');
  node.focus(); node.setSelectionRange(2, 7, 'backward'); tab(document, 'Second').emit('click');
  assert.equal(view.hasDrafts(), true); assert.deepEqual(calls, []);
  assert.equal(input(document, 'Name'), node); assert.ok(node.closest('[hidden]'));
  assert.throws(() => view.changes(), {code: 'draft_hidden'});
  tab(document, 'First').emit('click'); assert.equal(input(document, 'Name'), node);
  assert.equal(node.value, 'raw pending'); assert.equal(document.activeElement, node);
  assert.equal(node.selectionStart, 2); assert.equal(node.selectionEnd, 7);
  assert.deepEqual(view.changes(), [{control: 'Name', value: {type: 'String', value: 'raw pending'}}]);
});

test('hidden and detached page events cannot replay changes or commands', () => {
  const {document, view, calls} = setup(); const node = edit(document, 'Name', 'pending');
  const old = buttons(document).find(node => node.textContent === 'SaveFirst'); tab(document, 'Second').emit('click');
  node.emit('blur'); node.emit('keydown', {key: 'Enter'}); old.emit('click');
  assert.deepEqual(calls, []); assert.deepEqual(view.changes('Name'), []); assert.equal(view.isAvailable('SaveFirst'), false);
  const replacement = layout(); replacement.items[4].controlId = 99; view.render(model(replacement));
  node.emit('blur'); assert.deepEqual(calls, []); assert.ok(document.root.textContent.includes('Name: pending'));
});

test('page tabs support arrows and Home/End while disabled pages are skipped', () => {
  const {document, view} = setup(); tab(document, 'First').emit('keydown', {key: 'ArrowRight'});
  assert.equal(tab(document, 'Second').getAttribute('aria-selected'), 'true');
  assert.equal(document.activeElement, tab(document, 'Second'));
  tab(document, 'Second').emit('keydown', {key: 'Home'}); assert.equal(tab(document, 'First').getAttribute('aria-selected'), 'true');
  const snapshot = layout(); snapshot.items[6].enabled = false; snapshot.items[7].enabled = false; snapshot.items[8].enabled = false;
  view.render(model(snapshot)); tab(document, 'First').emit('keydown', {key: 'End'});
  assert.equal(tab(document, 'First').getAttribute('aria-selected'), 'true'); assert.equal(tab(document, 'Second').disabled, true);
});

test('host hides selected page: deterministic fallback with copy-only draft recovery', () => {
  const {document, view} = setup(); tab(document, 'Second').emit('click'); edit(document, 'Notes', 'never lose');
  const snapshot = layout(); snapshot.items.slice(6, 9).forEach(item => item.visible = false); view.render(model(snapshot));
  assert.equal(tab(document, 'First').getAttribute('aria-selected'), 'true'); assert.equal(tab(document, 'Second').hidden, true);
  assert.equal(view.hasDrafts(), true); assert.ok(document.root.textContent.includes('Notes: never lose'));
  assert.throws(() => view.changes(), {code: 'draft_changed'});
});

test('host updates inactive page value: raw draft is recovered, never overwritten or dispatched', () => {
  const {document, view, calls} = setup(); edit(document, 'Name', 'my text'); tab(document, 'Second').emit('click');
  const snapshot = layout(); snapshot.revision = 1; snapshot.items[4].value.value = 'server text'; view.render(model(snapshot));
  assert.equal(tab(document, 'Second').getAttribute('aria-selected'), 'true'); assert.equal(input(document, 'Name').value, 'server text');
  assert.ok(document.root.textContent.includes('Name: my text')); assert.deepEqual(calls, []);
});

test('group lock recovers pending draft without changing input identity', () => {
  const {document, view} = setup(); const node = edit(document, 'Name', 'unfinished');
  const snapshot = layout(); snapshot.items[3].readOnly = snapshot.items[4].readOnly = true; view.render(model(snapshot));
  assert.equal(input(document, 'Name'), node); assert.equal(node.readOnly, true); assert.equal(view.hasDrafts(), true);
  assert.ok(document.root.textContent.includes('Name: unfinished'));
});

test('busy or paused state blocks local page switching without later replay', () => {
  const {document, view} = setup(); const snapshot = layout(); view.render(model(snapshot, {busy: true}));
  tab(document, 'Second').emit('click'); view.render(model(snapshot));
  assert.equal(tab(document, 'First').getAttribute('aria-selected'), 'true');
  view.render(model(snapshot, {paused: true})); tab(document, 'Second').emit('click'); view.render(model(snapshot));
  assert.equal(tab(document, 'First').getAttribute('aria-selected'), 'true');
});

test('tables inside pages retain raw cell drafts and never flush a hidden cell', () => {
  const {document, view, calls} = setup(); const snapshot = layout(); snapshot.items.splice(5, 0, {...table({controlId: 30}), parent: 'First'});
  view.render(model(snapshot)); const cell = input(document, 'Quantity, row 1'); cell.value = 'bad number'; cell.emit('input');
  tab(document, 'Second').emit('click'); cell.emit('blur'); assert.deepEqual(calls, []);
  assert.throws(() => view.changes(), {code: 'draft_hidden'}); tab(document, 'First').emit('click');
  assert.equal(input(document, 'Quantity, row 1'), cell); assert.equal(cell.value, 'bad number');
  assert.throws(() => view.changes(), {code: 'invalid_input'});
});

test('mount refuses hidden commands and stops all sends when another page holds drafts', async () => {
  const requests = []; let snapshot = layout(); const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request); return response(reply(request, snapshot));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Name', 'pending');
  tab(env.document, 'Second').emit('click'); await app.run('command', 'SaveFirst'); await app.run('change', 'Name');
  assert.equal(requests.length, 1); await app.run('command', 'SaveSecond'); await app.run('close');
  assert.equal(requests.length, 1); assert.ok(env.document.root.textContent.includes('another page'));
});

test('delayed response cannot switch page or dispatch a queued hidden control', async () => {
  const requests = [], pending = deferred(); let snapshot = layout(); const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    if (request.params.event === 'change') {
      await pending.promise; snapshot = layout(); snapshot.revision = 1; snapshot.items[4].value = request.params.value;
    }
    return response(reply(request, snapshot));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Name', 'submitted');
  const operation = app.run('change', 'Name'); tab(env.document, 'Second').emit('click'); await app.run('command', 'SaveSecond');
  pending.resolve(); await operation;
  assert.equal(tab(env.document, 'First').getAttribute('aria-selected'), 'true'); assert.equal(requests.length, 2);
});

test('first flush can hide its pending command and prevents dispatch after response', async () => {
  const requests = []; let snapshot = layout(); const env = environment(async (_, options) => {
    const request = JSON.parse(options.body); requests.push(request);
    if (request.params.event === 'change') {
      snapshot = layout(); snapshot.revision = 1; snapshot.items[4].value = request.params.value;
      snapshot.items.slice(2, 6).forEach(item => item.visible = false);
    }
    return response(reply(request, snapshot));
  });
  const app = mountForm(env, env.document.root); await app.ready; edit(env.document, 'Name', 'submitted');
  await app.run('command', 'SaveFirst'); assert.equal(requests.length, 2);
  assert.equal(tab(env.document, 'Second').getAttribute('aria-selected'), 'true');
});

test('nested pages select independently and cannot make an ancestor-inactive control available', () => {
  const {document, view} = setup(); const snapshot = layout(); snapshot.items.splice(7, 1,
    group('Subsections', 'Second', 'pages', 20), group('SubFirst', 'Subsections', 'page', 21),
    {...field('Nested', undefined, {controlId: 22}), parent: 'SubFirst'}, group('SubSecond', 'Subsections', 'page', 23));
  validateSnapshot(snapshot); view.render(model(snapshot)); assert.equal(view.isAvailable('Nested'), false);
  tab(document, 'Second').emit('click'); assert.equal(view.isAvailable('Nested'), true);
  tab(document, 'SubSecond').emit('click'); assert.equal(view.isAvailable('Nested'), false);
  tab(document, 'First').emit('click'); tab(document, 'Second').emit('click');
  assert.equal(tab(document, 'SubSecond').getAttribute('aria-selected'), 'true');
});

test('group titles are text-only and do not expose a native CurrentPage command', () => {
  const {document, view} = setup(); const snapshot = layout(); snapshot.items[0].title = '<script>steal()</script>';
  snapshot.items[3].showTitle = false; view.render(model(snapshot));
  assert.ok(document.root.textContent.includes('<script>steal()</script>'));
  assert.equal(all(document.root).some(node => node.tagName === 'SCRIPT'), false);
  assert.equal(view.isAvailable('Sections'), false);
});
