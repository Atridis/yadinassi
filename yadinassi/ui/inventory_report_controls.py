"""Broker-owned report filters; opaque chooser tokens never grant object writes.

Only committed selections survive cancellation. Scans and report reads are
separate admitted snapshots; the latter revalidates the selected typed keys.
This module owns no database lease, transaction root, form or callback evaluator.
"""
from dataclasses import dataclass
import secrets
from uuid import UUID

from ..catalog_backend import BackendError, CatalogKey
from ..document_backend import DocumentKey
from ..inventory_host_operations import canonical
from ..inventory_application_reports import (InventoryReports, InventoryReportFilter,
    InventoryReportChoices, InventoryReportChoice, InventoryReportResult,
    MAX_CHOICES, MAX_LABELS, MAX_LABEL_LENGTH, _statement_options)

MAX_GENERATION = 2147483647


def _keys(value, names):
    if type(value) is not dict or any(type(k) is not str for k in value) or set(value) != set(names.split()):
        raise BackendError('invalid_input')


def _text(value, limit):
    if type(value) is not str or len(value) > limit or '\x00' in value:
        raise BackendError('invalid_input')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise BackendError('invalid_input') from None
    return value


def _catalog_key(key, database, target):
    return (type(key) is CatalogKey and all(type(v) is UUID for v in
            (key.database_id,key.catalog_id,key.record_id))
            and key.database_id == database and key.catalog_id == target)


@dataclass(frozen=True, slots=True)
class _Selection:
    value: InventoryReportFilter
    text: str


@dataclass(frozen=True, slots=True)
class _Chooser:
    dimension: str
    ticket: str
    snapshot: InventoryReportChoices
    tokens: tuple[str, ...]


class InventoryReportControls:
    """One live setup per broker, distinct from detached result pagination."""
    def __init__(self, service, configuration):
        if type(service) is not InventoryReports:
            raise BackendError('unsupported')
        try:
            configuration = canonical(configuration)
        except (TypeError, ValueError):
            raise BackendError('unsupported') from None
        if configuration != service._configuration:
            raise BackendError('schema_changed')
        service._admit()
        self._service, self._configuration = service, configuration
        self._binding = service._binding
        self._nonce = secrets.token_hex(16)
        self._generation = 0
        self.clear()

    def _verify(self):
        self._service._admit()
        if (self._service._configuration != self._configuration
                or self._service._binding != self._binding):
            raise BackendError('schema_changed')

    def _grant(self, name):
        if type(name) is not str:
            raise BackendError('invalid_input')
        grant = next((r for r in self._configuration.reports if r.name == name), None)
        if grant is None or grant.view != 'BalanceAndTurnovers':
            raise BackendError('unsupported')
        return grant

    def _ticket(self, kind):
        if self._generation >= MAX_GENERATION:
            raise BackendError('unsupported')
        self._generation += 1
        return kind+'-'+self._nonce+'-'+str(self._generation)

    def clear(self):
        self._report = self._setup = self._choice = None
        self._selections = ()

    def _filter_state(self):
        selected = {s.value.dimension_id: s for s in self._selections}
        return [{'id':f.dimension,'mode':('all' if f.dimension_id not in selected else
                  'selected' if selected[f.dimension_id].value.key.record_id.int else 'empty'),
                 'text':selected[f.dimension_id].text if f.dimension_id in selected else ''}
                for f in self._grant(self._report).filters]

    @property
    def state(self):
        if self._report is None:
            return None
        choice = self._choice
        return {'report':self._report,'ticket':self._setup,'filters':self._filter_state(),
                'choice':None if choice is None else {'filter':choice.dimension,'ticket':choice.ticket,
                    'code':choice.snapshot.code,'rows':[{'choice':token,'code':row.code,'description':row.description}
                        for token,row in zip(choice.tokens,choice.snapshot.rows)],'error':choice.snapshot.error}}

    def _check_setup(self, report, ticket):
        if type(report) is not str or type(ticket) is not str or report != self._report or ticket != self._setup:
            raise BackendError('invalid_input')
        return self._grant(report)

    def _check_choice(self, ticket):
        if type(ticket) is not str or self._choice is None or ticket != self._choice.ticket:
            raise BackendError('invalid_input')
        return self._choice

    def _scan(self, grant, field, code):
        # Even a failed new scan retires its old rows. Committed selections and
        # the setup remain unchanged; an old apply cannot target a replacement.
        self._choice = None
        snapshot = self._service.choices(grant.name, field.dimension, code)
        if (type(snapshot) is not InventoryReportChoices
                or type(snapshot.database_id) is not UUID
                or type(snapshot.configuration_generation) is not int
                or type(snapshot.source_digest) is not str
                or (snapshot.database_id,snapshot.configuration_generation) != self._binding
                or snapshot.source_digest != self._configuration.source_digest
                or type(snapshot.report) is not str or snapshot.report != grant.name
                or type(snapshot.dimension) is not str or snapshot.dimension != field.dimension
                or type(snapshot.dimension_id) is not UUID or snapshot.dimension_id != field.dimension_id
                or type(snapshot.catalog_id) is not UUID or snapshot.catalog_id != field.catalog_id
                or type(snapshot.code) is not str or snapshot.code != code
                or type(snapshot.rows) is not tuple or len(snapshot.rows) > MAX_CHOICES
                or snapshot.error is not None and (type(snapshot.error) is not str or snapshot.error != 'too_many_matches')
                or snapshot.error is not None and snapshot.rows):
            raise BackendError('integrity')
        seen = set()
        for row in snapshot.rows:
            if (type(row) is not InventoryReportChoice
                    or not _catalog_key(row.key,self._binding[0],field.catalog_id)
                    or not row.key.record_id.int or row.key in seen):
                raise BackendError('integrity')
            _text(row.code,64); _text(row.description,1024); seen.add(row.key)
        ticket = self._ticket('choice')
        tokens = tuple(secrets.token_hex(16) for _ in snapshot.rows)
        if len(set(tokens)) != len(tokens):
            raise BackendError('integrity')
        choice = _Chooser(field.dimension,ticket,snapshot,tokens)
        self._choice = choice

    def _select(self, grant, field, value, text):
        selected = {s.value.dimension_id:s for s in self._selections}
        if value is None:
            selected.pop(field.dimension_id,None)
        else:
            selected[field.dimension_id] = _Selection(value,text)
        selections = tuple(selected[f.dimension_id] for f in grant.filters if f.dimension_id in selected)
        ticket = self._ticket('setup')
        self._setup, self._selections, self._choice = ticket, selections, None

    def action(self, params):
        self._verify()
        if (type(params) is not dict or any(type(k) is not str for k in params)
                or type(params.get('action')) is not str):
            raise BackendError('invalid_input')
        action = params['action']
        if action == 'open':
            _keys(params,'report action'); grant = self._grant(params['report'])
            ticket = self._ticket('setup')
            self._report,self._setup,self._selections,self._choice = grant.name,ticket,(),None
            return self.state
        fields = {'begin':'filter','clear':'filter','empty':'filter','filter':'choice code',
                  'apply':'choice value','cancel':'choice'}
        if action not in fields:
            raise BackendError('invalid_input')
        _keys(params,'report ticket action '+fields[action])
        grant = self._check_setup(params['report'],params['ticket'])
        if action in ('begin','clear','empty'):
            name = params['filter']
            field = None if type(name) is not str else next((f for f in grant.filters if f.dimension == name),None)
            if field is None:
                raise BackendError('invalid_input')
            if action == 'begin':
                self._scan(grant,field,'')
            elif action == 'clear':
                self._select(grant,field,None,'')
            else:
                value = InventoryReportFilter(field.dimension_id,CatalogKey(self._binding[0],field.catalog_id,UUID(int=0)),self._binding[1])
                self._select(grant,field,value,'(empty reference)')
        else:
            choice = self._check_choice(params['choice'])
            field = next(f for f in grant.filters if f.dimension == choice.dimension)
            if action == 'filter':
                self._scan(grant,field,_text(params['code'],64))
            elif action == 'cancel':
                self._choice = None
            else:
                token = params['value']
                if type(token) is not str or token not in choice.tokens:
                    raise BackendError('invalid_input')
                row = choice.snapshot.rows[choice.tokens.index(token)]
                value = InventoryReportFilter(field.dimension_id,row.key,self._binding[1])
                self._select(grant,field,value,row.description or row.code)
        return self.state

    def resolve(self, report, ticket):
        self._verify();grant = self._check_setup(report,ticket)
        if self._choice is not None:
            raise BackendError('busy')
        values = tuple(s.value for s in self._selections)
        return _statement_options(grant,grant.periodicities[0],values,self._binding)

    def display(self, result):
        self._verify()
        if (type(result) is not InventoryReportResult or type(result.database_id) is not UUID
                or type(result.configuration_generation) is not int or type(result.source_digest) is not str
                or (result.database_id,result.configuration_generation) != self._binding
                or result.source_digest != self._configuration.source_digest):
            raise BackendError('schema_changed')
        grant = self._grant(result.report)
        if (type(result.register_id) is not UUID or result.register_id != grant.register_id
                or type(result.register) is not str or result.register != grant.register
                or type(result.view) is not str or result.view != grant.view):
            raise BackendError('invalid_input')
        values = _statement_options(grant,result.periodicity,result.filters,self._binding)
        if type(result.labels) is not tuple or len(result.labels) > MAX_LABELS:
            raise BackendError('invalid_input')
        labels = {}
        for pair in result.labels:
            if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) not in (CatalogKey,DocumentKey):
                raise BackendError('invalid_input')
            key,label = pair
            target = key.catalog_id if type(key) is CatalogKey else key.document_id
            if (any(type(v) is not UUID for v in (key.database_id,target,key.record_id))
                    or key.database_id != self._binding[0] or key in labels):
                raise BackendError('invalid_input')
            labels[key] = _text(label,MAX_LABEL_LENGTH)
        selected = {value.dimension_id:value.key for value in values}
        rendered = []
        for field in grant.filters:
            key = selected.get(field.dimension_id)
            if key is None:
                mode,text = 'all',''
            elif not key.record_id.int:
                mode,text = 'empty','(empty reference)'
            elif key not in labels:
                raise BackendError('invalid_input')
            else:
                mode,text = 'selected',labels[key]
            rendered.append({'id':field.dimension,'mode':mode,'text':text})
        return rendered
