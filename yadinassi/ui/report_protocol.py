"""Closed presentation-only stock statement envelopes; no database authority."""
import re
from ..invocation import _decode_scalar, _encode_scalar


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError('invalid report envelope')


def _text(value, limit):
    if type(value) is not str or len(value) > limit:
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


def _ticket(value, prefix):
    return type(value) is str and re.fullmatch(prefix + r'-[0-9a-f]{32}-[1-9][0-9]{0,15}', value) is not None


def has_statements(configuration):
    return configuration is not None and any(r.view == 'BalanceAndTurnovers' for r in configuration.reports)


def declarations(configuration):
    return [{'id': r.name, 'title': r.register + ' ' + r.view, 'view': r.view,
             **({'periodicities': list(r.periodicities),
                 'filters': [{'id': f.dimension, 'title': f.dimension} for f in r.filters]}
                if r.view == 'BalanceAndTurnovers' else {})} for r in configuration.reports]


def _grant(configuration, name):
    if type(name) is not str:
        raise ValueError('invalid report name')
    grant = next((r for r in configuration.reports if r.name == name), None)
    if grant is None:
        raise ValueError('unknown report')
    return grant


def _filters(values, grant):
    if type(values) is not list or len(values) != len(grant.filters):
        raise ValueError('invalid report selections')
    for value, declared in zip(values, grant.filters):
        _keys(value, 'id mode text')
        if (value['id'] != declared.dimension or value['mode'] not in ('all', 'empty', 'selected')
                or not _text(value['text'], 1152)
                or value['mode'] == 'all' and value['text'] != ''
                or value['mode'] == 'empty' and value['text'] != '(empty reference)'):
            raise ValueError('invalid typed report filter')


def validate_setup(value, configuration, report=None):
    _keys(value, 'report ticket filters choice')
    grant = _grant(configuration, value['report'])
    if (grant.view != 'BalanceAndTurnovers' or report is not None and value['report'] != report
            or not _ticket(value['ticket'], 'setup')):
        raise ValueError('invalid report setup')
    _filters(value['filters'], grant)
    choice = value['choice']
    if choice is None:
        return
    _keys(choice, 'filter ticket code rows error')
    if (choice['filter'] not in [f.dimension for f in grant.filters]
            or not _ticket(choice['ticket'], 'choice') or not _text(choice['code'], 64)
            or choice['error'] not in (None, 'too_many_matches')
            or type(choice['rows']) is not list or len(choice['rows']) > 32
            or choice['error'] is not None and choice['rows']):
        raise ValueError('invalid report choice')
    seen = set()
    for row in choice['rows']:
        _keys(row, 'choice code description')
        if (type(row['choice']) is not str or re.fullmatch('[0-9a-f]{32}', row['choice']) is None
                or row['choice'] in seen or not _text(row['code'], 64) or not _text(row['description'], 1024)):
            raise ValueError('invalid report choice row')
        seen.add(row['choice'])


def validate_page(value, rows):
    _keys(value, 'snapshot cursor previous next offset total')
    if (type(value['snapshot']) is not str or re.fullmatch(r'report-[A-Za-z0-9_-]{32}-[1-9][0-9]{0,15}', value['snapshot']) is None
            or type(value['offset']) is not int or type(value['total']) is not int
            or not 0 <= value['offset'] <= value['total'] <= 1000
            or not 0 <= len(rows) <= 50 or value['offset'] + len(rows) > value['total']
            or value['total'] > 0 and not rows
            or (value['previous'] is None) != (value['offset'] == 0)
            or (value['next'] is None) != (value['offset'] + len(rows) == value['total'])):
        raise ValueError('invalid report page')
    cursors = []
    for key in ('cursor', 'previous', 'next'):
        token = value[key]
        if key != 'cursor' and token is None:
            continue
        if type(token) is not str or re.fullmatch(r'page-[A-Za-z0-9_-]{32}', token) is None or token in cursors:
            raise ValueError('invalid report cursor')
        cursors.append(token)


def validate_projection(result, configuration, request, *, paged=True):
    grant = _grant(configuration, request['report'])
    statement = grant.view == 'BalanceAndTurnovers'
    _keys(request, 'report at start end' + (' periodicity setup' if statement else ''))
    _keys(result, 'report view at start end columns rows' + (' periodicity setup filters' if statement else '')
          + (' page' if statement and paged else ''))
    if (result['view'] != grant.view or any(result[k] != request[k] for k in request)
            or type(result['columns']) is not list or not 1 <= len(result['columns']) <= 32
            or type(result['rows']) is not list or len(result['rows']) > 1000
            or len(result['rows']) * len(result['columns']) > 25000):
        raise ValueError('invalid report projection')
    if statement:
        if result['periodicity'] not in grant.periodicities or not _ticket(result['setup'], 'setup'):
            raise ValueError('invalid statement options')
        _filters(result['filters'], grant)
        if paged:
            validate_page(result['page'], result['rows'])
    from ..inventory_application_reports import _columns
    schema = next(s for s in configuration.registers if s.identity == grant.register_id)
    kinds = {'string': 'String', 'number': 'Number', 'boolean': 'Boolean', 'datetime': 'Date',
             'catalog_ref': 'Catalog', 'document_ref': 'Document', 'accumulation_direction': 'String'}
    expected = [{'name': c.name, 'type': kinds[c.kind]} for c in _columns(schema, grant.view, result.get('periodicity'))]
    if result['columns'] != expected:
        raise ValueError('report columns differ from exact admitted register')
    for column in result['columns']:
        _keys(column, 'name type')
        if not _text(column['name'], 128):
            raise ValueError('invalid report column')
    for row in result['rows']:
        if type(row) is not list or len(row) != len(result['columns']):
            raise ValueError('invalid report row')
        for value, column in zip(row, result['columns']):
            if type(value) is not dict or value.get('type') != column['type']:
                raise ValueError('invalid typed report cell')
            if column['type'] in ('Catalog', 'Document'):
                _keys(value, 'type text')
                if not _text(value['text'], 1152):
                    raise ValueError('invalid report presentation')
            elif _encode_scalar(_decode_scalar(value)) != value:
                raise ValueError('noncanonical report scalar')


def validate_next_page(result, previous, payload, configuration):
    _keys(payload, 'snapshot cursor')
    if previous is None or previous.get('page', {}).get('snapshot') != payload['snapshot']:
        raise ValueError('retired report snapshot')
    request = {k: previous[k] for k in ('report', 'at', 'start', 'end', 'periodicity', 'setup')}
    validate_projection(result, configuration, request)
    if ({k: v for k, v in previous.items() if k not in ('rows', 'page')}
            != {k: v for k, v in result.items() if k not in ('rows', 'page')}
            or result['page']['snapshot'] != payload['snapshot'] or result['page']['cursor'] != payload['cursor']
            or result['page']['total'] != previous['page']['total']):
        raise ValueError('report page changed snapshot')
