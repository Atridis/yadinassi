import test from 'node:test';
import assert from 'node:assert/strict';
import {FormClient, PROTOCOL, LIMITS, decimalText, validateScalar, validateSnapshot, typedInput,
  readBoundedJSON, createTransport, takeSessionCapability} from '../src/client.mjs';
import {field, button, state, reply, response, deferred} from './fixtures.mjs';

test('handshake, change, command, snapshot and close have exact wire shapes', async () => {
  const seen = []; const client = new FormClient(async request => { seen.push(request); return reply(request, state(seen.length - 1)); });
  await client.hello(); await client.event('change', {control: 'Name', value: {type: 'String', value: 'New'}});
  await client.event('command', {control: 'Run'}); await client.resync(); await client.event('close');
  assert.deepEqual(seen, [
    {jsonrpc: '2.0', id: 1, method: 'form.hello', params: {protocol: PROTOCOL}},
    {jsonrpc: '2.0', id: 2, method: 'form.event', params: {event: 'change', revision: 0, control: 'Name', value: {type: 'String', value: 'New'}}},
    {jsonrpc: '2.0', id: 3, method: 'form.event', params: {event: 'command', revision: 1, control: 'Run'}},
    {jsonrpc: '2.0', id: 4, method: 'form.snapshot', params: {}},
    {jsonrpc: '2.0', id: 5, method: 'form.event', params: {event: 'close', revision: 3}},
  ]);
});

test('repeated command clicks and refresh while busy send just one request', async () => {
  const pending = deferred(); let count = 0;
  const client = new FormClient(async request => ++count === 1 ? reply(request) : pending.promise);
  await client.hello(); const first = client.event('command', {control: 'Run'});
  assert.equal(client.busy, true); assert.throws(() => client.event('command', {control: 'Run'}), {code: 'busy'});
  await assert.rejects(client.resync(), {code: 'busy'}); assert.equal(count, 2);
  pending.resolve(reply({id: 2}, state(1))); await first; assert.equal(client.busy, false);
});

test('handler error commits completed effects before reporting finite error', async () => {
  const changed = state(1, {messages: ['Completed first effect'], items: [field('Name', {type: 'String', value: 'Updated'}), button()]});
  const client = new FormClient(async request => reply(request, request.id === 1 ? state() : changed, request.id === 1 ? null : 'event_failed'));
  await client.hello(); await assert.rejects(client.event('command', {control: 'Run'}), {code: 'event_failed'});
  assert.deepEqual(client.snapshot, changed); assert.equal(client.locked, false);
});

test('lost response locks all writes and does not retry the event', async () => {
  let count = 0; const client = new FormClient(async request => { if (++count === 1) return reply(request); throw Error('private traceback'); });
  await client.hello(); await assert.rejects(client.event('command', {control: 'Run'}), error => error.code === 'transport' && !error.message.includes('traceback'));
  assert.throws(() => client.event('close'), {code: 'transport'}); assert.equal(count, 2); assert.equal(client.transportFailed, true);
});

test('explicit snapshot recovers known transport outcome without replay', async () => {
  const methods = []; const client = new FormClient(async request => {
    methods.push(request.method); if (methods.length === 2) throw Error(); return reply(request, state(methods.length === 1 ? 0 : 1));
  });
  await client.hello(); await assert.rejects(client.event('command', {control: 'Run'})); await client.resync();
  assert.equal(client.locked, false); assert.deepEqual(methods, ['form.hello', 'form.event', 'form.snapshot']);
});

test('host unknown outcome cannot be unlocked by any subsequent snapshot', async () => {
  for (const error of [null, 'outcome_unknown']) {
    const client = new FormClient(async request => reply(request, state(request.id, {uncertain: request.id === 1}), request.id === 1 ? error : null));
    await client.hello().catch(() => {}); await client.resync();
    assert.equal(client.outcomeUnknown, true); assert.throws(() => client.event('close'), {code: 'outcome_unknown'});
  }
});

test('stale revision adopts current state without replaying the rejected change', async () => {
  const seen = []; const client = new FormClient(async request => { seen.push(request); return reply(request, state(request.id === 1 ? 0 : 8), request.id === 2 ? 'stale_revision' : null); });
  await client.hello(); await assert.rejects(client.event('change', {control: 'Name', value: {type: 'String', value: 'Draft'}}), {code: 'stale_revision'});
  assert.equal(client.snapshot.revision, 8); assert.equal(seen.length, 2); await client.resync();
  assert.equal(seen[2].method, 'form.snapshot');
});

test('out-of-order and malformed responses preserve last valid snapshot and lock', async () => {
  const alterations = [r => ({...r, id: true}), r => ({...r, extra: 'bad'}), r => ({...r, error: {message: '<script>bad</script>'}}),
    r => ({...r, result: {...r.result, protocol: 'another'}}), r => ({...r, result: {...r.result, error: 'private traceback'}}),
    r => ({...r, result: {...r.result, state: state(1)}})];
  for (const alter of alterations) {
    const client = new FormClient(async request => request.id === 1 ? reply(request, state(2)) : alter(reply(request, state(3))));
    await client.hello(); await assert.rejects(client.resync(), {code: 'transport'}); assert.equal(client.snapshot.revision, 2); assert.equal(client.locked, true);
  }
});

test('unsupported event shapes, disabled controls and wrong scalar types never reach host', async () => {
  const client = new FormClient(async request => reply(request, state(0, {items: [field(), button(), field('Locked', {type: 'String', value: ''}, {readOnly: true})]})));
  await client.hello();
  for (const [event, values] of [['other', {}], ['close', {revision: 0}], ['command', {control: 'Name'}],
    ['change', {control: 'Locked', value: {type: 'String', value: 'x'}}], ['change', {control: 'Name', value: {type: 'Boolean', value: false}}],
    ['command', {control: 'missing'}], ['command', {control: 'Run', extra: true}]]) assert.throws(() => client.event(event, values));
  assert.equal(client.id, 1);
});

test('closed, cancelled and failed lifecycle reject further events', async () => {
  for (const lifecycle of ['closed', 'cancelled', 'failed']) {
    const client = new FormClient(async request => reply(request, state(1, {kind: 'closed', lifecycle})));
    await client.hello(); assert.throws(() => client.event('close'), {code: 'closed'});
  }
});

test('request ID overflow and host request limit lock without extra requests', async () => {
  let count = 0; const client = new FormClient(async request => { count++; return reply(request, state(), request.id === 1 ? null : 'request_limit'); });
  await client.hello(); await assert.rejects(client.event('close'), {code: 'request_limit'}); await assert.rejects(client.resync(), {code: 'request_limit'}); assert.equal(count, 2);
  const overflow = new FormClient(() => { throw Error('not reached'); }); overflow.id = LIMITS.counter;
  await assert.rejects(overflow.hello(), {code: 'request_limit'});
});

test('strict snapshots reject extra keys, wrong booleans, duplicate names and count overflow', () => {
  const cases = [state(0, {extra: true}), state(true), state(0, {uncertain: 1}), state(0, {messages: [4]}),
    state(0, {messages: Array(65).fill('a')}), state(0, {items: [field(), field()]}),
    state(0, {items: Array.from({length: 129}, (_, i) => field('f' + i))}),
    state(0, {items: [field('Name', {type: 'String', value: ''}, {enabled: 1})]}),
    state(0, {items: [{...button(), value: {type: 'Null'}}]}),
    state(0, {items: [field('Name', {type: 'String', value: ''}, {view: 'checkbox'})]})];
  for (const value of cases) assert.throws(() => validateSnapshot(value), {code: 'transport'});
});

test('hostile strings remain literal data while byte and Unicode limits are enforced', () => {
  const hostile = '<img src=x onerror=alert(1)>\u0000 & " __proto__';
  assert.equal(validateSnapshot(state(0, {title: hostile, items: [field('__proto__', {type: 'String', value: hostile})]})).title, hostile);
  for (const value of ['a'.repeat(8193), 'я'.repeat(4097), '\ud800']) assert.throws(() => validateScalar({type: 'String', value}));
  assert.doesNotThrow(() => validateScalar({type: 'String', value: 'я'.repeat(4096)}));
});

test('all admitted scalar shapes are exact and no extra object members are accepted', () => {
  for (const value of [{type: 'Undefined'}, {type: 'Null'}, {type: 'String', value: ''}, {type: 'Boolean', value: false},
    {type: 'Number', value: '-0.00'}, {type: 'Date', ticks: '3155378975990000'}]) {
    assert.deepEqual(validateScalar(value), value); assert.throws(() => validateScalar({...value, extra: 1}));
  }
  for (const value of [{type: 'CatalogRef'}, {type: 'Boolean', value: 0}, {type: 'Date', ticks: '3155378975990001'},
    {type: 'Date', ticks: '01'}, {type: 'Date', ticks: -1}, {type: 'Number', value: 1.25}, null]) assert.throws(() => validateScalar(value));
});

test('decimal inputs retain large coefficients, trailing zeros, signed zero and exponent exactly', () => {
  const examples = [['999999999999999999.0100', '999999999999999999.0100'], ['-0.00', '-0.00'], ['+00012.30', '12.30'],
    ['.125', '0.125'], ['1e+4096', '1E+4096'], ['10e-8', '1.0E-7'], ['0.0000000', '0E-7'], ['1.2e2', '1.2E+2']];
  for (const [input, expected] of examples) {
    assert.equal(decimalText(input), expected);
    assert.deepEqual(typedInput(field('Amount', {type: 'Number', value: '0'}), input), {type: 'Number', value: expected});
    assert.doesNotThrow(() => validateScalar({type: 'Number', value: expected}));
  }
});

test('invalid or excessive decimals cannot become numbers or a request', () => {
  for (const input of ['NaN', 'Infinity', '1,2', '1_000', ' 1', '1e4097', '1e-4097', '9'.repeat(129), '', true, 12.5]) assert.throws(() => decimalText(input));
  for (const input of ['01', '+1', '1e2', '.5', '1.']) assert.throws(() => validateScalar({type: 'Number', value: input}));
});

test('Date, Null, Undefined and label views are explicitly read-only', () => {
  for (const value of [{type: 'Date', ticks: '1'}, {type: 'Null'}, {type: 'Undefined'}]) assert.throws(() => typedInput(field('x', value), '2'), {code: 'unavailable'});
  assert.throws(() => typedInput(field('x', {type: 'String', value: 'x'}, {view: 'label'}), '2'), {code: 'unavailable'});
  assert.deepEqual(typedInput(field('Flag', {type: 'Boolean', value: true}), false), {type: 'Boolean', value: false});
  assert.throws(() => typedInput(field('Flag', {type: 'Boolean', value: true}), 'false'));
});

test('bounded NDJSON rejects HTTP errors, wrong media, oversized, multiple frames and invalid UTF8', async () => {
  assert.deepEqual(await readBoundedJSON(response({a: 1})), {a: 1});
  const options = {headers: {'content-type': 'application/x-ndjson'}};
  for (const value of [new Response('{}\n', {status: 503, ...options}), new Response('{}\n'),
    new Response('x'.repeat(131073), options), new Response('{}\n{}\n', options), new Response('{}', options),
    new Response(new Uint8Array([0xff, 10]), options)]) await assert.rejects(readBoundedJSON(value));
});

test('transport posts only to local RPC, bounds duration and never follows redirects', async () => {
  const calls = []; const token = 'a'.repeat(43);
  const transport = createTransport(async (...args) => { calls.push(args); return response({ok: true}); }, token);
  assert.deepEqual(await transport({jsonrpc: '2.0'}), {ok: true});
  const [url, options] = calls[0]; assert.equal(url, '/rpc'); assert.equal(options.method, 'POST');
  assert.deepEqual(options.headers, {'Content-Type': 'application/x-ndjson', 'X-Yadinassi-Session': token});
  assert.equal(options.body, '{"jsonrpc":"2.0"}\n'); assert.equal(options.credentials, 'omit');
  assert.equal(options.redirect, 'error'); assert.equal(options.referrerPolicy, 'no-referrer');
  assert.equal(options.cache, 'no-store'); assert.equal(options.mode, 'same-origin');
});

test('HTTP failure locks the client and missing capability never makes a fetch', async () => {
  let count = 0; const client = new FormClient(createTransport(async () => { count++; return new Response('private error', {status: 503}); }, 'a'.repeat(43)));
  await assert.rejects(client.hello(), {code: 'transport'}); assert.equal(client.locked, true); assert.equal(count, 1);
  await assert.rejects(createTransport(() => { count++; }, null)({}), {code: 'session_missing'}); assert.equal(count, 1);
});

test('launch fragment is stripped before use and duplicate or malformed tokens are rejected', () => {
  const calls = [], history = {replaceState(...args) { calls.push(args); }};
  assert.equal(takeSessionCapability({hash: '#session=' + 'a'.repeat(43), pathname: '/'}, history), 'a'.repeat(43));
  assert.deepEqual(calls, [[null, '', '/']]);
  for (const hash of ['', '#session=short', '#session=' + 'я'.repeat(43), '#session=' + 'a'.repeat(43) + '&session=' + 'b'.repeat(43)])
    assert.equal(takeSessionCapability({hash, pathname: '/'}, history), null);
});
