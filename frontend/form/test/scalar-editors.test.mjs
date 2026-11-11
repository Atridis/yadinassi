import test from 'node:test';
import assert from 'node:assert/strict';
import {FormClient, LIMITS, validateSnapshot, editable, scalarText, inputHint, tableCell, typedInput} from '../src/client.mjs';
import {field, button, column, table, state, reply} from './fixtures.mjs';

const date = (parts = 'dateTime', ticks = '0', extra = {}) => field('When', {type: 'Date', ticks}, {editor: {kind: 'date', parts}, ...extra});
const number = (digits = 5, scale = 2, nonnegative = false) => field('Amount', {type: 'Number', value: '0'}, {editor: {kind: 'number', digits, scale, nonnegative}});
const string = (length = 5, fixed = false) => field('Code', {type: 'String', value: fixed ? ' '.repeat(length) : ''}, {editor: {kind: 'string', length, fixed}});
const snapshot = item => state(0, {items: [item]});
const dates = item => table({columns: [column('When', 'Date', {editor: item.editor})], rows: [{id: 1, values: [item.value]}]});
const invalid = fn => assert.throws(fn, {code: 'invalid_input'});
const DAY = 864000000n;

test('optional closed editors preserve the legacy snapshot and Date display contract', () => {
  const old = field('When', {type: 'Date', ticks: '10000'});
  assert.equal(validateSnapshot(snapshot(old)).items[0], old);
  assert.equal(editable(old), false); assert.equal(scalarText(old.value), '10000');
  for (const item of [date(), date('date'), date('time'), number(), string(), string(5, true), string(0), number(0, 0)]) {
    assert.equal(validateSnapshot(snapshot(item)).items[0], item); assert.equal(editable(item), true);
  }
  assert.doesNotThrow(() => validateSnapshot(snapshot(dates(date()))));
});

test('editor shapes reject unknown keys, wrong kinds, unsafe counts and contradictory qualifiers', () => {
  for (const editor of [null, [], {kind: 'date'}, {kind: 'date', parts: 'DateTime'}, {kind: 'date', parts: 'date', extra: true},
    {kind: 'number', digits: 5, scale: 2, nonnegative: false}, {kind: 'datetime', parts: 'dateTime'}])
    assert.throws(() => validateSnapshot(snapshot({...date(), editor})), {code: 'transport'});
  for (const patch of [{digits: -1}, {digits: 129}, {digits: true}, {digits: 1.5}, {scale: 6}, {scale: -1}, {scale: true},
    {scale: 129}, {digits: 0, scale: 1}, {nonnegative: 1}, {extra: true}])
    assert.throws(() => validateSnapshot(snapshot({...number(), editor: {...number().editor, ...patch}})), {code: 'transport'});
  for (const patch of [{length: -1}, {length: 65537}, {length: true}, {length: 1.5}, {fixed: 1}, {length: 0, fixed: true}, {extra: true}])
    assert.throws(() => validateSnapshot(snapshot({...string(), editor: {...string().editor, ...patch}})), {code: 'transport'});
  for (const item of [{...button(), editor: date().editor}, {...dates(date()), editor: date().editor},
    field('Boolean', {type: 'Boolean', value: true}, {editor: number().editor}),
    {...date(), value: {type: 'Null'}}, {...date(), value: {type: 'Undefined'}}])
    assert.throws(() => validateSnapshot(snapshot(item)), {code: 'transport'});
});

test('column editor and actual cell types must agree including null and undefined', () => {
  const item = dates(date());
  for (const editor of [{...date().editor, arbitrary: true}, string().editor, null])
    assert.throws(() => validateSnapshot(snapshot({...item, columns: [column('When', 'Date', {editor})]})), {code: 'transport'});
  for (const value of [{type: 'Null'}, {type: 'Undefined'}, {type: 'Number', value: '1'}])
    assert.throws(() => validateSnapshot(snapshot({...item, rows: [{id: 1, values: [value]}]})), {code: 'transport'});
});

test('authoritative values cannot contradict their editor qualifiers or hide date components', () => {
  for (const item of [date('date', '10000'), date('time', String(DAY)),
    {...number(), value: {type: 'Number', value: '1000'}}, {...number(), value: {type: 'Number', value: '1.001'}},
    {...number(5, 2, true), value: {type: 'Number', value: '-1'}},
    {...string(2), value: {type: 'String', value: 'ABC'}}, {...string(2, true), value: {type: 'String', value: 'A'}}])
    assert.throws(() => validateSnapshot(snapshot(item)), {code: 'transport'});
  assert.doesNotThrow(() => validateSnapshot(snapshot(number(128, 128))));
  assert.doesNotThrow(() => validateSnapshot(snapshot(string(65536))));
});

test('optional scalar IDs share the table identity budget and cannot appear on buttons', () => {
  assert.doesNotThrow(() => validateSnapshot(state(0, {items: [date('dateTime', '0', {controlId: 2}), dates(date())]})));
  for (const controlId of [0, true, 1.5, 1025, '2'])
    assert.throws(() => validateSnapshot(snapshot({...date(), controlId})), {code: 'transport'});
  for (const items of [[{...date(), controlId: 1}, dates(date())], [{...date(), controlId: 2}, {...string(), controlId: 2}],
    [{...button(), controlId: 2}]]) assert.throws(() => validateSnapshot(state(0, {items})), {code: 'transport'});
});

test('DateTime text has exact epoch, one-second, Unix-era and conservative upper-bound values', () => {
  for (const [input, ticks] of [['0001-01-01T00:00:01', '10000'], ['0001-01-02T00:00:00', String(DAY)],
    ['1970-01-01T00:00:00', '621355968000000'], ['2000-01-01T00:00:00', '630822816000000'],
    ['9999-12-31T23:59:58', '3155378975980000']]) {
    const value = typedInput(date(), input); assert.deepEqual(value, {type: 'Date', ticks});
    assert.equal(scalarText(value, date().editor), input);
  }
  invalid(() => typedInput(date(), '9999-12-31T23:59:59'));
});

test('Gregorian leap years and month lengths round-trip without host timezone conversion', () => {
  for (const input of ['0004-02-29', '0400-02-29', '1600-02-29', '1900-02-28', '2000-02-29', '2024-02-29', '9999-12-31'])
    assert.equal(scalarText(typedInput(date('date'), input), date('date').editor), input);
  const february = BigInt(typedInput(date('date'), '2024-02-28').ticks);
  assert.equal(BigInt(typedInput(date('date'), '2024-03-01').ticks) - february, 2n * DAY);
  const common = BigInt(typedInput(date('date'), '1900-02-28').ticks);
  assert.equal(BigInt(typedInput(date('date'), '1900-03-01').ticks) - common, DAY);
});

test('invalid calendars and imprecise or localized date spellings are never normalized', () => {
  for (const input of ['0000-01-01', '10000-01-01', '0001-00-01', '2024-13-01', '2024-01-00', '2024-04-31',
    '2023-02-29', '0100-02-29', '1900-02-29', '2024-2-29', '24-02-29', '29.02.2024', '2024-02-29 ', ' 2024-02-29', '2024-02-29\n'])
    invalid(() => typedInput(date('date'), input));
  for (const input of ['2024-02-29', '2024-02-29 12:30:45', '2024-02-29t12:30:45', '2024-02-29T12:30',
    '2024-02-29T12:30:45Z', '2024-02-29T12:30:45+00:00', '2024-02-29T12:30:45.0', '2024-02-29T24:00:00'])
    invalid(() => typedInput(date(), input));
});

test('Time editor uses whole seconds on day one and rejects overflow or missing components', () => {
  for (const [input, ticks] of [['00:00:01', '10000'], ['01:02:03', '37230000'], ['23:59:59', '863990000']]) {
    const value = typedInput(date('time'), input); assert.equal(value.ticks, ticks);
    assert.equal(scalarText(value, date('time').editor), input);
  }
  for (const input of ['24:00:00', '12:60:00', '12:00:60', '1:02:03', '12:30', '12:30:00.1', '12:30:00Z', ' 12:30:00'])
    invalid(() => typedInput(date('time'), input));
});

test('blank, day-one midnight and time zero all use the existing typed zero with no new flag', () => {
  for (const [parts, alias] of [['date', '0001-01-01'], ['time', '00:00:00'], ['dateTime', '0001-01-01T00:00:00']]) {
    const item = date(parts);
    for (const text of ['', alias]) assert.deepEqual(typedInput(item, text), {type: 'Date', ticks: '0'});
    assert.equal(scalarText(item.value, item.editor), ''); assert.match(inputHint(item), /blank = empty date/);
  }
});

test('fractional and upper-end stored dates remain lossless readonly fields and cells', () => {
  for (const item of [date('dateTime', '1'), date('time', '12345'), date('dateTime', LIMITS.dateTicks),
    date('dateTime', '3155378975980001')]) {
    assert.doesNotThrow(() => validateSnapshot(snapshot(dates(item))));
    for (const target of [item, tableCell(dates(item), 1, 'When')]) {
      assert.equal(editable(target), false); assert.equal(scalarText(target.value, target.editor), item.value.ticks);
      assert.match(inputHint(target), /Exact date ticks.*read-only/);
      assert.throws(() => typedInput(target, ''), {code: 'unavailable'});
    }
  }
});

test('date labels format exact supported values but cannot become editable', () => {
  const item = date('dateTime', '10000', {view: 'label'});
  assert.equal(editable(item), false); assert.equal(scalarText(item.value, item.editor), '0001-01-01T00:00:01');
  assert.match(inputHint(item), /Read-only/); assert.throws(() => typedInput(item, ''), {code: 'unavailable'});
});

test('number qualifiers preflight exact magnitude without floating-point or hidden clamping', () => {
  const item = number();
  for (const input of ['999.99', '-999.99', '999.9900', '+0001.2300', '9.9999e2']) assert.doesNotThrow(() => typedInput(item, input));
  assert.equal(typedInput(item, '+0001.2300').value, '1.2300');
  for (const input of ['1000', '-1000', '1e3', '999.991', '1.23001', '0.001']) invalid(() => typedInput(item, input));
  const large = number(28, 4);
  assert.equal(typedInput(large, '999999999999999999999999.9999').value, '999999999999999999999999.9999');
  invalid(() => typedInput(large, '1000000000000000000000000'));
});

test('numeric trailing zero precision is harmless but nonzero excess precision is rejected', () => {
  for (const input of ['1.2300', '0.00000', '-0.00000', '1.0000', '12300e-4']) assert.doesNotThrow(() => typedInput(number(), input));
  for (const input of ['1.2301', '0.00001', '-0.00001', '12301e-4']) invalid(() => typedInput(number(), input));
  assert.equal(typedInput(number(2, 2), '.9900').value, '0.9900'); invalid(() => typedInput(number(2, 2), '1'));
  assert.equal(typedInput(number(3, 0), '12.000').value, '12.000'); invalid(() => typedInput(number(3, 0), '12.001'));
});

test('nonnegative disallows negative values but zero and unqualified precision retain BSL meaning', () => {
  invalid(() => typedInput(number(0, 0, true), '-0.01'));
  for (const input of ['-0', '-0.0000', '0', '1e100', '1e-100', '1.23456789'])
    assert.doesNotThrow(() => typedInput(number(0, 0, true), input));
  assert.equal(typedInput(number(0, 0), '-1.23456789').value, '-1.23456789');
});

test('numeric qualifier boundaries retain the existing coefficient and exponent resource limits', () => {
  assert.equal(typedInput(number(128, 0), '9'.repeat(128)).value, '9'.repeat(128));
  assert.doesNotThrow(() => typedInput(number(128, 128), '1e-128'));
  invalid(() => typedInput(number(128, 128), '1e-129'));
  for (const input of ['9'.repeat(129), '1e4097', 'NaN', 'Infinity', '1,2', ' 1', '1\n']) invalid(() => typedInput(number(0, 0), input));
});

test('string preflight uses UTF-16 units without truncating, padding or splitting surrogate pairs', () => {
  assert.equal(typedInput(string(3), '😀A').value, '😀A');
  invalid(() => typedInput(string(2), '😀A')); invalid(() => typedInput(string(1), '😀'));
  invalid(() => typedInput(string(5), '\ud800')); invalid(() => typedInput(string(5), '\udc00'));
  assert.equal(typedInput(string(5, true), 'AB').value, 'AB');
  assert.equal(typedInput(string(5, true), '').value, '');
  invalid(() => typedInput(string(5, true), 'ABCDEF'));
});

test('String length zero is unqualified and the separate UTF-8 transport limit still applies', () => {
  assert.equal(typedInput(string(0), 'x'.repeat(8192)).value.length, 8192);
  invalid(() => typedInput(string(0), 'x'.repeat(8193)));
  invalid(() => typedInput(string(65536), '😀'.repeat(2049)));
  assert.equal(typedInput(string(65536), '😀'.repeat(2048)).value.length, 4096);
});

test('fields and table cells share exactly the same trusted editor and typed input path', () => {
  for (const [item, input] of [[date(), '2024-02-29T12:30:45'], [date('date'), '2024-02-29'], [date('time'), '12:30:45'],
    [number(), '1.2300'], [string(), 'ABC']]) {
    const grid = table({columns: [column('Value', item.value.type, {editor: item.editor})], rows: [{id: 7, values: [item.value]}]});
    const cell = tableCell(grid, 7, 'Value');
    assert.deepEqual(cell.editor, item.editor); assert.deepEqual(typedInput(cell, input), typedInput(item, input));
  }
});

test('FormClient sends ordinary exact Date change and cell events without descriptors', async () => {
  const requests = [], initial = state(0, {items: [date('dateTime', '0', {controlId: 2}), dates(date())]});
  const client = new FormClient(async request => { requests.push(request); return reply(request, {...initial, revision: requests.length - 1}); });
  await client.hello();
  await client.event('change', {control: 'When', value: typedInput(date(), '0001-01-01T00:00:01')});
  await client.event('cell', {control: 'Lines', row: 1, column: 'When', value: typedInput(date(), '')});
  assert.deepEqual(requests.slice(1).map(request => request.params), [
    {event: 'change', revision: 0, control: 'When', value: {type: 'Date', ticks: '10000'}},
    {event: 'cell', revision: 1, control: 'Lines', row: 1, column: 'When', value: {type: 'Date', ticks: '0'}},
  ]);
});

test('direct client calls cannot bypass date envelope or Number/String input qualifiers', async () => {
  const items = [date('date'), number(5, 2, true), string(2), dates(date())];
  const client = new FormClient(async request => reply(request, state(0, {items}))); await client.hello();
  for (const [control, value] of [['When', {type: 'Date', ticks: '10000'}], ['Amount', {type: 'Number', value: '-1'}],
    ['Amount', {type: 'Number', value: '1.001'}], ['Code', {type: 'String', value: 'ABC'}]])
    invalid(() => client.event('change', {control, value}));
  for (const ticks of ['1', LIMITS.dateTicks]) invalid(() => client.event('cell', {control: 'Lines', row: 1, column: 'When', value: {type: 'Date', ticks}}));
  assert.equal(client.id, 1);
});
