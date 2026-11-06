"""Explicit editor/0 profile: one request/response, authoritative error snapshots.

The existing readonly yadinassi-ui/0 contract is unchanged. Accepted editing events
can mutate form state even on failure; no transport ACK claims persistence.
"""
from ..catalog_backend import BackendError
from .catalog_editor import CatalogEditorApplication
from .protocol import (UIError, MAX_COUNTER, bounded_text, counter, decode_line,
                       decode_value, encode_line, uuid_text)

PROTOCOL = 'yadinassi-editor/0'
_EVENTS = {'checkCard': {'reference'}, 'selectCatalog': {'catalog'}, 'create': set(), 'openCard': {'reference'},
           'change': {'control', 'value'}, 'command': {'control'}, 'closeCard': set(),
           'page': {'offset', 'limit'}, 'close': set(), 'addRow': {'section'},
           'deleteRow': {'section', 'row'}, 'changeRow': {'section', 'row', 'value'}}


def validate_request(value):
    if (type(value) is not dict or set(value) != {'jsonrpc', 'id', 'method', 'params'}
            or value['jsonrpc'] != '2.0' or type(value['id']) is not int
            or not 1 <= value['id'] <= MAX_COUNTER or type(value['params']) is not dict
            or type(value['method']) is not str):
        raise UIError('invalid_message')
    params = value['params']; method = value['method']
    if method == 'editor.hello':
        if set(params) != {'protocol'} or type(params['protocol']) is not str:
            raise UIError('invalid_message')
    elif method == 'editor.snapshot':
        if params: raise UIError('invalid_message')
    elif method == 'editor.event':
        event = params.get('event')
        if type(event) is not str or event not in _EVENTS or set(params) != {'event', 'baseRevision'} | _EVENTS[event]:
            raise UIError('invalid_message')
        counter(params['baseRevision'])
        if event == 'selectCatalog': uuid_text(params['catalog'], nonzero=True)
        elif event in ('openCard', 'checkCard'):
            if event != 'checkCard' or params['reference'] is not None: decode_value(params['reference'])
        elif event in ('change', 'command'):
            bounded_text(params['control'], 128)
            if event == 'change': decode_value(params['value'])
        elif event in ('addRow', 'deleteRow', 'changeRow'):
            bounded_text(params['section'], 512)
            if event != 'addRow': uuid_text(params['row'], nonzero=True)
            if event == 'changeRow': decode_value(params['value'])
        elif event == 'page':
            counter(params['offset'])
            if type(params['limit']) is not int or not 1 <= params['limit'] <= 64:
                raise UIError('page')
    else:
        raise UIError('method_not_found')
    return value


class CatalogEditorSession:
    def __init__(self, application):
        if type(application) is not CatalogEditorApplication:
            raise TypeError('editor requires CatalogEditorApplication')
        self.application = application
        self.revision = 0
        self._last_id = 0
        self._requests = 0
        self._hello = False
        self._busy = False

    def snapshot(self):
        return {'protocol': PROTOCOL, 'formId': 'catalog-editor', 'revision': self.revision,
                **self.application.snapshot()}

    def _error(self, request_id, reason):
        data = {'reason': reason, 'revision': self.revision}
        if self._hello:
            try:
                snapshot = self.snapshot()
                encode_line(snapshot)
                data['snapshot'] = snapshot
            except Exception:
                # Post-commit projection failures never imply rollback or safe replay.
                data['stateUnavailable'] = True
                editor = self.application.editor
                data['saveState'] = 'none' if editor is None else editor.save_state
        message = {'jsonrpc': '2.0', 'id': request_id, 'error': {
            'code': -32601 if reason == 'method_not_found' else -32000,
            'message': 'Editor request rejected', 'data': data}}
        try:
            return encode_line(message)
        except UIError:
            data.pop('snapshot', None)
            data['stateUnavailable'] = True
            editor = self.application.editor
            data['saveState'] = 'none' if editor is None else editor.save_state
            return encode_line(message)

    def exchange(self, raw):
        if self._busy:
            return self._error(None, 'busy')
        self._busy = True
        request_id = None
        try:
            request = validate_request(decode_line(raw))
            request_id = request['id']
            if request_id <= self._last_id: raise UIError('sequence')
            if self._requests >= 4096: raise UIError('request_limit')
            self._last_id = request_id; self._requests += 1
            method, params = request['method'], request['params']
            if method == 'editor.hello':
                if self._hello: raise UIError('handshake')
                if params['protocol'] != PROTOCOL: raise UIError('version')
                response = encode_line({'jsonrpc': '2.0', 'id': request_id, 'result': self.snapshot()})
                self._hello = True
                return response
            if not self._hello: raise UIError('handshake')
            if method == 'editor.snapshot':
                return encode_line({'jsonrpc': '2.0', 'id': request_id, 'result': self.snapshot()})
            if params['baseRevision'] != self.revision: raise UIError('stale_revision')
            values = {key: item for key, item in params.items() if key not in ('event', 'baseRevision')}
            for key in ('value', 'reference'):
                if key in values and not (params['event'] == 'checkCard' and values[key] is None):
                    values[key] = decode_value(values[key])
            try:
                self.application.event(params['event'], **values)
            finally:
                # This is editor request sequencing, distinct from form/row versions.
                self.revision += 1
            editor = self.application.editor
            if params['event'] == 'command' and params['control'] == 'SaveButton' and editor is not None and editor.error:
                return self._error(request_id, editor.error)
            return encode_line({'jsonrpc': '2.0', 'id': request_id, 'result': self.snapshot()})
        except UIError as error:
            return self._error(request_id, error.code)
        except BackendError as error:
            return self._error(request_id, error.code)
        except Exception:
            return self._error(request_id, 'form_error')
        finally:
            self._busy = False
