import {PROTOCOL} from '../src/client.mjs';
export const field = (name = 'Name', value = {type: 'String', value: 'Original'}, extra = {}) => ({
  name, kind: 'field', title: name, visible: true, enabled: true, readOnly: false,
  view: value.type === 'Boolean' ? 'checkbox' : 'input', value, ...extra,
});
export const button = (name = 'Run') => ({name, kind: 'button', title: name, visible: true,
  enabled: true, readOnly: false, view: 'label', value: null});
export const state = (revision = 0, extra = {}) => ({kind: 'form', revision, lifecycle: 'open',
  title: 'Sample form', uncertain: false, items: [field(), button()], messages: [], ...extra});
export const reply = (request, snapshot = state(), error = null) => ({jsonrpc: '2.0', id: request.id,
  result: {protocol: PROTOCOL, state: snapshot, error}});
export const response = value => new Response(JSON.stringify(value) + '\n', {headers: {'content-type': 'application/x-ndjson; charset=utf-8'}});
export const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; };
export const column = (name = 'Description', type = 'String', extra = {}) => ({name, title: name, type, readOnly: false, ...extra});
export const table = (extra = {}) => ({name: 'Lines', kind: 'table', title: 'Order lines', visible: true, enabled: true,
  readOnly: false, controlId: 1, tableId: 1, columns: [column(), column('Quantity', 'Number'), column('Active', 'Boolean')],
  rows: [{id: 1, values: [{type: 'String', value: 'First'}, {type: 'Number', value: '1.00'}, {type: 'Boolean', value: true}]},
    {id: 2, values: [{type: 'String', value: 'Second'}, {type: 'Number', value: '2.00'}, {type: 'Boolean', value: false}]}],
  currentRow: null, ...extra});
