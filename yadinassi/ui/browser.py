"""Persistent, synchronous headless browser session; not a managed form runtime.

The five allowed events are host navigation commands, not BSL handlers. Both BSL
execution contexts remain untouched. Requests are processed one at a time.
"""
from .catalog_view import CatalogRepository
from .protocol import (CatalogRef, PROTOCOL, UIError, decode_line, decode_value,
                       encode_line, error_response, validate_request)


class CatalogBrowserSession:
    def __init__(self, repository):
        if type(repository) is not CatalogRepository:
            raise TypeError('catalog UI requires CatalogRepository')
        self._repository = repository
        self._hello = False
        self._closed = False
        self._busy = False
        self._last_id = 0
        self._requests = 0
        self._revision = 0
        self._view = None
        self._card = None
        self._page = None

    def _state(self, *, view=None, card=None, page=None):
        if view is None:
            return {'kind': 'catalogs', 'catalogs': [
                {'id': item.identity, 'name': item.name, 'rowSupport': 'not-checked'}
                for item in self._repository.inventory()]}
        return {'kind': 'card' if card is not None else 'list',
                'list': view.page(*(page or (0, 8))),
                'card': card.wire() if card is not None else None}

    def _snapshot(self):
        return {'formId': 'catalog-browser', 'revision': self._revision,
                'capabilities': self._repository.capabilities(),
                'state': self._state(view=self._view, card=self._card, page=self._page)}

    def exchange(self, raw):
        """One bounded NDJSON request -> result/error and optional UI notification.

        IDs are positive, strictly increasing and consumed on admitted requests,
        including semantic failure. No action is replayed on a duplicate ID.
        Output encoding is completed before any navigation state is committed.
        """
        request_id = None
        if self._busy:
            return (encode_line(error_response(None, 'busy')),)
        self._busy = True
        try:
            decoded = decode_line(raw)
            if (type(decoded) is dict and decoded.get('jsonrpc') == '2.0'
                    and type(decoded.get('method')) is str and 'id' not in decoded):
                # Renderer notifications never dispatch actions in this profile.
                # JSON-RPC notifications must not receive an error response.
                return ()
            request = validate_request(decoded)
            request_id = request['id']
            if self._closed:
                raise UIError('closed')
            if request_id <= self._last_id:
                raise UIError('sequence')
            if self._requests >= 4096:
                raise UIError('request_limit')
            self._last_id = request_id
            self._requests += 1
            messages, commit = self._request(request)
            encoded = tuple(encode_line(message) for message in messages)
            commit()
            return encoded
        except UIError as error:
            return (encode_line(error_response(request_id, error.code)),)
        except Exception:
            # Never put a Python exception, source path or physical record in IPC.
            return (encode_line(error_response(request_id, 'internal_error')),)
        finally:
            self._busy = False

    def _request(self, request):
        method, params, request_id = request['method'], request['params'], request['id']
        result = {'jsonrpc': '2.0', 'id': request_id,
                  'result': {'protocol': PROTOCOL, 'revision': self._revision}}
        if method == 'ui.hello':
            if self._hello:
                raise UIError('handshake')
            if params['protocol'] != PROTOCOL:
                raise UIError('version')
            notification = {'jsonrpc': '2.0', 'method': 'ui.open', 'params': self._snapshot()}
            return [result, notification], lambda: setattr(self, '_hello', True)
        if not self._hello:
            raise UIError('handshake')
        if method == 'ui.snapshot':
            self._repository.check_source()
            result['result']['snapshot'] = self._snapshot()
            return [result], lambda: None
        if params['baseRevision'] != self._revision:
            raise UIError('stale_revision')
        event = params['event']
        view, card, page = self._view, self._card, self._page
        if event != 'close':
            self._repository.check_source()
        if event == 'selectCatalog':
            view, card, page = self._repository.load(params['catalog']), None, (0, 8)
        elif event == 'openCard':
            if view is None:
                raise UIError('catalog_identity')
            card = view.card(decode_value(params['reference']))
        elif event == 'followReference':
            if card is None:
                raise UIError('reference_field')
            reference = card.value(params['field'])
            if type(reference) is not CatalogRef:
                raise UIError('reference_field')
            if reference.record == '00000000-0000-0000-0000-000000000000':
                raise UIError('empty_reference')
            view = self._repository.load(reference.catalog)
            card, page = view.card(reference), (0, 8)
        elif event == 'page':
            if view is None:
                raise UIError('page')
            page, card = (params['offset'], params['limit']), None
        revision = self._revision + 1
        result['result']['revision'] = revision
        if event == 'close':
            notification = {'jsonrpc': '2.0', 'method': 'ui.close', 'params': {
                'formId': 'catalog-browser', 'baseRevision': self._revision, 'revision': revision}}
        else:
            notification = {'jsonrpc': '2.0', 'method': 'ui.patch', 'params': {
                'formId': 'catalog-browser', 'baseRevision': self._revision, 'revision': revision,
                'state': self._state(view=view, card=card, page=page)}}
        def commit():
            if event == 'close':
                self._repository.close()
            self._revision = revision
            self._closed = event == 'close'
            self._view, self._card, self._page = view, card, page
        return [result, notification], commit
