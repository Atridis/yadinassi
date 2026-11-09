"""One closed Orders object session for the trusted replicated form example.

This is application infrastructure, not a native BSL global or generic object
wire format. Detached objects, backend keys, revisions and uncertain write
intents stay here for the lifetime of the server process. No read view survives
an action; no Save looks up an object by its editable code.
"""
from copy import copy
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from ..catalog_backend import (BackendError, CatalogComparison, CatalogScanRequest,
    CatalogOrder, CatalogValuePage, CatalogValueRow, CatalogKey, TabularRow)
from ..catalog_object_preparation import CatalogWriteRefused
from ..catalog_sections import BSLCatalogSection
from ..form_runtime import FormServerBinding
from ..form_tables import validate_table_data, MAX_TABLE_ROWS, MAX_TABLE_ALLOCATED
from ..invocation import _encode_scalar
from .protocol import encode_line, encode_value


class OrdersWorkbenchSession:
    """Retains one selected identity and its original optimistic revision."""
    def __init__(self, context):
        if context is None:
            raise ValueError('Orders workbench requires an existing database')
        self.context = context
        self.manager = None
        self.object = None
        self.baseline = None
        self.choices = {}
        self.line_keys = {}
        self.pending_commit = False
        self.pending_refresh = False

    def bindings(self):
        return tuple(FormServerBinding('Workbench' + name, getattr(self, method))
            for name, method in [('Browse', 'browse'), ('Load', 'load'), ('Save', 'save'),
                                 ('Reload', 'reload'), ('Resolve', 'resolve'), ('Dirty', 'dirty')])

    def _manager(self, session):
        if self.manager is None:
            manager = session.interpreter._catalogs.get_index('Orders')
            schema = manager._schema
            def shape(fields):
                return tuple((f.name, f.kind, f.qualifiers) for f in fields)
            if (schema.code_length != 8 or schema.description_length != 64 or
                    schema.numbering != 'explicit' or
                    shape(schema.fields) != (('Total', 'number', (18, 2, 'Any')),) or
                    len(schema.tabular_sections) != 1 or schema.tabular_sections[0].name != 'Lines' or
                    shape(schema.tabular_sections[0].fields) != (
                        ('ItemDescription', 'string', (128,)),
                        ('Quantity', 'number', (18, 2, 'Any')),
                        ('Price', 'number', (18, 2, 'Any')),
                        ('Amount', 'number', (18, 2, 'Any')))):
                raise BackendError('unsupported')
            self.manager = manager
        if self.manager._backend is not self.context.backend:
            raise BackendError('schema_changed')
        return self.manager

    @staticmethod
    def _image(form):
        return (tuple(form._data[k] for k in ('code', 'description', 'total')),
                tuple(values for _, values in form._tables['lines']._snapshot().rows))

    @staticmethod
    def _status(session, message):
        session.form.set_member('Status', message)

    def _locked(self, session):
        locked = self.pending_commit or self.pending_refresh
        form = session.form
        form.set_member('Locked', locked)
        form.set_member('Loaded', self.object is not None)
        for name in ('FieldCode', 'FieldDescription', 'LinesTable'):
            form.items._values[name.casefold()].read_only = locked or self.object is None
        for name in ('AddLine', 'DeleteLine', 'Recalculate', 'SaveOrder', 'Discard'):
            form.items._values[(name + 'Button').casefold()].enabled = not locked and self.object is not None
        for name in ('SearchOrders', 'OpenOrder'):
            form.items._values[(name + 'Button').casefold()].enabled = not locked
        form.items._values['ordersTable'.casefold()].enabled = not locked
        form.items._values['fieldsearchcode'].read_only = locked
        resolve = form.items._values['resolveButton'.casefold()]
        resolve.enabled = locked
        resolve.title = 'Refresh saved record' if self.pending_refresh else 'Resolve save outcome'

    def _blocked(self, session):
        if self.pending_commit or self.pending_refresh:
            self._locked(session)
            self._status(session, 'Resolve the pending save before another action')
            return True
        return False

    @staticmethod
    def _rows(table, values):
        if len(values) > MAX_TABLE_ROWS or table._allocated + len(values) > MAX_TABLE_ALLOCATED:
            raise ValueError('complete record exceeds form row limit')
        return tuple((table._allocated + index + 1, row) for index, row in enumerate(values))

    @staticmethod
    def _preflight(session, values, replacements):
        """Admit the complete final state before adopting an object or any row.

        The existing replica decoder validates types, all aggregate table/text
        budgets and selections. The complete prospective response is byte-bounded
        too, rather than exposing a truncated editable prefix on load failure.
        """
        from ..form_replication import _pack_state, _unpack_state
        form = session.form
        data = dict(form._data)
        data.update(values)
        validate_table_data(form, replacements, data)
        packet = _pack_state(session, session._replica_handler_names)
        packet['lifecycle'] = 'open'
        for attribute in packet['attributes']:
            attribute[5] = _encode_scalar(data[attribute[0].casefold()])
        for table in packet['tables']:
            key = table['name'].casefold()
            if key in replacements:
                rows = replacements[key]
                table['rows'] = [[identity, [encode_value(v) for v in row]] for identity, row in rows]
                table['allocated'] = rows[-1][0] if rows else form._tables[key]._allocated
        for item in packet['items']:
            if item[1] == 'table' and item[6].casefold() in replacements:
                item[10] = None
        encode_line({'protocol': 'yadinassi-form/1', 'id': 2147483647, 'status': 'ok',
            'accepted': True, 'revision': 2147483647, 'sequence': 2147483647,
            'messages': [], 'state': packet, 'value': {'type': 'Undefined'}})
        # The decoder also serves a client before bootstrap, when inventory may
        # initially be empty. Here the server schema is always already fixed.
        # Supply that explicit validation context without changing BSL/session
        # state or weakening the client's post-bootstrap inventory invariant.
        context = SimpleNamespace(form=form, reserved_names=session.reserved_names, _baseline=True)
        return _unpack_state(packet, context, session._replica_handlers)

    @staticmethod
    def _install(session, prepared):
        from ..form_replication import _install_state
        _install_state(session, prepared)

    def browse(self, session):
        if self._blocked(session):
            return
        try:
            manager = self._manager(session)
            code = session.form._data['searchcode']
            if type(code) is not str or len(code) > 8:
                self._status(session, 'Search by an exact code of at most 8 characters, or leave it empty')
                return
            view = manager._view()
            try:
                page = view.scan_catalog_values(manager._schema.identity,
                    CatalogScanRequest(predicate=None if not code else CatalogComparison('code', 'eq', code),
                                       order=(CatalogOrder('code'),), page_size=32),
                    ('code', 'description', manager._schema.fields[0].identity))
                if (type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows) > 32 or
                        page.continuation is not None and (type(page.continuation) is not str or len(page.continuation) != 32)):
                    raise BackendError('integrity')
                seen = set()
                for row in page.rows:
                    if (type(row) is not CatalogValueRow or type(row.key) is not CatalogKey or
                            row.key.database_id != view.database_id or row.key.catalog_id != manager._schema.identity or
                            type(row.key.record_id) is not UUID or not row.key.record_id.int or row.key in seen or
                            type(row.values) is not tuple or len(row.values) != 3 or
                            tuple(type(v) for v in row.values) != (str, str, Decimal)):
                        raise BackendError('integrity')
                    seen.add(row.key)
            finally:
                view.close()
            rows = self._rows(session.form._tables['orders'], tuple(row.values for row in page.rows))
            message = ('Showing first 32 orders; enter an exact code to find another order'
                       if page.continuation is not None else
                       'Select an order, then Open selected order' if rows else 'No matching orders')
            prepared = self._preflight(session, {'status': message}, {'orders': rows})
            self._install(session, prepared)
            self.choices = {row[0]: result.key for row, result in zip(rows, page.rows)}
        except Exception:
            self._status(session, 'Order list unavailable; current record and edits were kept')
        self._locked(session)

    def _fresh(self, session, record):
        manager = self._manager(session)
        fresh = manager._get_object(manager._ref(record))
        if fresh is None:
            raise BackendError('not_found')
        if fresh.get_member('DeletionMark'):
            raise BackendError('unsupported')
        return fresh

    def _adopt(self, session, fresh, message):
        stored = fresh._sections['lines']._stored_rows().rows
        values = tuple(row.values for row in stored)
        rows = self._rows(session.form._tables['lines'], values)
        patches = {k: fresh.get_member(k) for k in ('code', 'description', 'total')}
        patches.update(status=message, dirty=False, loaded=True, locked=False)
        prepared = self._preflight(session, patches, {'lines': rows})
        self._install(session, prepared)
        # No object or baseline is replaced until the entire projection is admitted.
        self.object = fresh
        self.baseline = self._image(session.form)
        self.line_keys = {row[0]: saved.identity for row, saved in zip(rows, stored)}
        self.pending_commit = self.pending_refresh = False
        self._locked(session)

    def load(self, session):
        if self._blocked(session):
            return
        if self.object is not None and self._image(session.form) != self.baseline:
            self._status(session, 'Unsaved changes: Save or Discard / Reload before opening another order')
            return
        selected = session.form.items._values['orderstable'].current_row
        key = self.choices.get(selected)
        if key is None:
            self._status(session, 'Select an order from the current results first')
            return
        try:
            self._adopt(session, self._fresh(session, key.record_id), 'Order loaded; edits save this same record')
        except Exception:
            self._status(session, 'Cannot load the complete order; it may be missing, deleted or exceed form limits. Current record was kept')

    def reload(self, session):
        if self._blocked(session) or self.object is None:
            return
        try:
            self._adopt(session, self._fresh(session, self.object._key.record_id), 'Changes discarded; record reloaded from the database')
        except Exception:
            self._status(session, 'Reload failed; current record and server edits were kept')

    def _candidate(self, session):
        candidate = copy(self.object)
        candidate._values = dict(self.object._values)
        for name in ('Code', 'Description', 'Total'):
            candidate.set_member(name, session.form._data[name.casefold()])
        schema = self.manager._schema.tabular_sections[0]
        rows = tuple(TabularRow(self.line_keys.get(identity) or uuid4(), values)
                     for identity, values in session.form._tables['lines']._snapshot().rows)
        section = BSLCatalogSection(candidate, schema, rows)
        section._dirty = True
        candidate._sections = {'lines': section}
        return candidate

    def _write(self, session):
        try:
            self.object.write()
        except CatalogWriteRefused:
            self.pending_commit = self.object._pending_write is not None
            self._status(session, 'Save refused by object validation; edits were kept')
        except BackendError as error:
            self.pending_commit = self.object._pending_write is not None or error.code == 'uncertain_commit'
            if self.pending_commit:
                self._status(session, 'Database save outcome uncertain. Use Resolve save outcome on this session; do not open another writer')
            elif error.code == 'conflict':
                self._status(session, 'Save conflict: the record changed elsewhere. Edits were kept; Discard / Reload adopts the database version')
            else:
                self._status(session, 'Save rejected (' + error.code + '); edits were kept')
        except BaseException:
            self.pending_commit = self.pending_commit or self.object._pending_write is not None
            self._status(session, 'Save interrupted; resolve the retained intent before continuing' if self.pending_commit
                         else 'Save failed before confirmation; edits were kept')
            raise
        else:
            self.pending_commit = False
            self.pending_refresh = True
            self._refresh(session)
        finally:
            self._locked(session)

    def _refresh(self, session):
        try:
            self._adopt(session, self._fresh(session, self.object._key.record_id), 'Order saved; you can continue editing')
        except Exception:
            self.pending_refresh = True
            self._status(session, 'Order saved, but refresh failed. Use Refresh saved record; it will not write again')

    def dirty(self, session):
        # Recalculation can repair loaded amounts even without a cell OnChange.
        session.form.set_member('Dirty', self.object is not None and self._image(session.form) != self.baseline)

    def save(self, session):
        if self._blocked(session) or self.object is None:
            return
        if self._image(session.form) == self.baseline:
            session.form.set_member('Dirty', False)
            self._status(session, 'No changes; nothing was written')
            return
        self._manager(session)
        self.object = self._candidate(session)
        self._write(session)

    def resolve(self, session):
        # An explicit healthy-channel action only. Retained Write resolves its exact
        # receipt/intent; confirmed commits can only refresh, never write again.
        if self.pending_refresh:
            self._refresh(session)
        elif self.pending_commit:
            self._write(session)
        self._locked(session)
