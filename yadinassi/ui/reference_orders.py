"""Closed reference-order application and a server-owned child choice.

CatalogKey never enters the scalar form. The one-shot choice ticket binds an
owner generation and an exact live form row, not a position or presentation.
The Orders workbench supplies projection preflight and receipt-based writes.
This opt-in catalog profile is independent of document storage and native UI.
"""
from copy import copy
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from ..catalog_backend import (BackendError, CatalogComparison, CatalogKey,
    CatalogOrder, CatalogPredicate, CatalogScanRequest, CatalogValuePage,
    CatalogValueRow, TabularRow)
from ..catalog_sections import BSLCatalogSection
from ..form_runtime import FormServerBinding
from .order_workbench import OrdersWorkbenchSession

_UNSET = object()
APPLY_CHOICE_ENDPOINT = 9


@dataclass(frozen=True)
class OwnedChoice:
    """Host capability, never a browser-supplied result or callback address."""
    generation: int
    serial: int
    target: str
    row: int | None


def catalog_page(manager, code, fields):
    """One bounded live-record snapshot; no cursor/read transaction survives."""
    if type(code) is not str or len(code) > 8:
        raise ValueError('invalid exact code')
    predicate = CatalogComparison('deletion_mark', 'eq', False)
    if code:
        predicate = CatalogPredicate('and', (predicate, CatalogComparison('code', 'eq', code)))
    view = manager._view()
    try:
        page = view.scan_catalog_values(manager._schema.identity,
            CatalogScanRequest(predicate=predicate, order=(CatalogOrder('code'),), page_size=32), fields)
        if (type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows) > 32
                or page.continuation is not None and (type(page.continuation) is not str or len(page.continuation) != 32)):
            raise BackendError('integrity')
        seen = set()
        for row in page.rows:
            if (type(row) is not CatalogValueRow or type(row.key) is not CatalogKey
                    or row.key.database_id != view.database_id or row.key.catalog_id != manager._schema.identity
                    or type(row.key.record_id) is not UUID or not row.key.record_id.int or row.key in seen
                    or type(row.values) is not tuple or len(row.values) != len(fields)
                    or tuple(type(v) for v in row.values[:2]) != (str, str)
                    or len(row.values[0]) > 8 or len(row.values[1]) > 64):
                raise BackendError('integrity')
            seen.add(row.key)
        return page
    finally:
        view.close()


class ReferenceOrdersSession(OrdersWorkbenchSession):
    """New fixed schema; reuses complete admission and write-recovery machinery."""
    def __init__(self, context, *, initial_record=None):
        super().__init__(context, initial_record=initial_record)
        self.generation = self.choice_serial = 0
        self.choice_limit = 256
        self.active_choice = None
        self.choice_result = _UNSET
        self.apply_uncertain = False
        self.customer = None
        self.products = {}
        self.customers_manager = self.products_manager = None

    def bindings(self):
        return super().bindings() + tuple(FormServerBinding(name, method) for name, method in (
            ('ReferenceChooseCustomer', self.choose_customer),
            ('ReferenceChooseProduct', self.choose_product),
            ('ReferenceApplyChoice', self.apply_choice)))

    def _manager(self, session):
        if self.manager is None:
            catalogs = session.interpreter._catalogs
            orders, customers, products = (catalogs.get_index(n) for n in ('Orders', 'Customers', 'Products'))
            def shape(fields):
                return tuple((f.name, f.kind, f.qualifiers, f.target_catalog_id) for f in fields)
            number = ('number', (18, 2, 'Any'), None)
            if (any(m._schema.code_length != 8 or m._schema.description_length != 64
                    or m._schema.numbering != 'explicit' for m in (orders, customers, products))
                    or customers._schema.fields or customers._schema.tabular_sections
                    or products._schema.tabular_sections
                    or shape(products._schema.fields) != (('UnitPrice', *number),)
                    or shape(orders._schema.fields) != (
                        ('Customer', 'catalog_ref', (), customers._schema.identity), ('Total', *number))
                    or len(orders._schema.tabular_sections) != 1
                    or orders._schema.tabular_sections[0].name != 'Lines'
                    or shape(orders._schema.tabular_sections[0].fields) != (
                        ('Product', 'catalog_ref', (), products._schema.identity),
                        ('ItemDescription', 'string', (128,), None),
                        ('Quantity', *number), ('Price', *number), ('Amount', *number))):
                raise BackendError('unsupported')
            self.manager, self.customers_manager, self.products_manager = orders, customers, products
        if self.manager._backend is not self.context.backend:
            raise BackendError('schema_changed')
        return self.manager

    def list_page(self, session, code):
        manager = self._manager(session)
        page = catalog_page(manager, code, ('code', 'description', manager._schema.fields[1].identity))
        if any(type(row.values[2]) is not Decimal for row in page.rows):
            raise BackendError('integrity')
        return page

    def _image(self, form):
        rows = form._tables['lines']._snapshot().rows
        return (tuple(form._data[k] for k in ('code', 'description', 'total')),
                tuple(values for _, values in rows), self.customer,
                tuple(self.products.get(identity) for identity, _ in rows))

    def _locked(self, session):
        locked = self.pending_commit or self.pending_refresh or self.active_choice is not None
        form = session.form
        form.set_member('Locked', locked)
        form.set_member('Loaded', self.object is not None)
        for name in ('FieldCode', 'FieldDescription', 'LinesTable'):
            form.items._values[name.casefold()].read_only = locked or self.object is None
        form.items._values['linestable'].enabled = not locked
        for name in ('AddLine', 'DeleteLine', 'Recalculate', 'SaveOrder', 'Discard', 'ChooseCustomer', 'ChooseProduct'):
            form.items._values[(name + 'Button').casefold()].enabled = not locked and self.object is not None
        resolve = form.items._values['resolvebutton']
        resolve.enabled = (self.pending_commit or self.pending_refresh) and self.active_choice is None
        resolve.title = 'Refresh saved record' if self.pending_refresh else 'Resolve save outcome'

    def _blocked(self, session):
        if self.active_choice is not None:
            self._status(session, 'Finish or cancel the owned selection first')
            self._locked(session)
            return True
        return super()._blocked(session)

    @staticmethod
    def _record(manager, key, *, allow_missing=False):
        if (type(key) is not CatalogKey or key.database_id != manager._catalogs._metadata._database_id
                or key.catalog_id != manager._schema.identity or type(key.record_id) is not UUID):
            raise BackendError('invalid_input')
        card = manager._read(key.record_id) if key.record_id.int else None
        if card is None or card.deletion_mark:
            if allow_missing:
                return None
            raise BackendError('not_found')
        return card

    def _adopt(self, session, fresh, message):
        self._manager(session)
        stored = fresh._sections['lines']._stored_rows().rows
        customer = fresh._manager._stored(fresh._manager._schema.fields[0], fresh.get_member('Customer'))
        card = self._record(self.customers_manager, customer, allow_missing=True)
        customer_text = '' if not customer.record_id.int else (card.description if card else '[Unavailable customer]')
        values = []
        for row in stored:
            product = self._record(self.products_manager, row.values[0], allow_missing=True)
            label = product.description if product else '[Unavailable product]'
            values.append((label, *row.values[1:]))
        rows = self._rows(session.form._tables['lines'], tuple(values))
        patches = {k: fresh.get_member(k) for k in ('code', 'description', 'total')}
        patches.update(customer=customer_text, status=message, dirty=False, loaded=True, locked=False)
        prepared = self._preflight(session, patches, {'lines': rows})
        self._install(session, prepared)
        self.object = fresh
        self.customer = customer if customer.record_id.int else None
        self.products = {row[0]: saved.values[0] for row, saved in zip(rows, stored)}
        self.line_keys = {row[0]: saved.identity for row, saved in zip(rows, stored)}
        self.generation += 1
        self.pending_commit = self.pending_refresh = False
        self.baseline = self._image(session.form)
        self._locked(session)

    def browse(self, session):
        manager = self._manager(session)
        record, self.initial_record = self.initial_record, None
        fresh = manager.create_item() if record is None else self._fresh(session, record)
        self._adopt(session, fresh, 'Choose a customer and products, then save this order')

    def reload(self, session):
        if self._blocked(session) or self.object is None:
            return
        if self.object.is_new():
            self._adopt(session, self._manager(session).create_item(), 'New order drafts discarded; nothing was written')
        else:
            super().reload(session)

    def _candidate(self, session):
        self._record(self.customers_manager, self.customer)
        rows = session.form._tables['lines']._snapshot().rows
        for identity, _ in rows:
            self._record(self.products_manager, self.products.get(identity))
        candidate = copy(self.object)
        candidate._values = dict(self.object._values)
        for name in ('Code', 'Description', 'Total'):
            candidate.set_member(name, session.form._data[name.casefold()])
        candidate.set_member('Customer', self.customers_manager._ref(self.customer.record_id))
        stored = tuple(TabularRow(self.line_keys.get(identity) or uuid4(), (self.products[identity], *values[1:]))
                       for identity, values in rows)
        section = BSLCatalogSection(candidate, self.manager._schema.tabular_sections[0], stored)
        section._dirty = True
        candidate._sections = {'lines': section}
        return candidate

    def save(self, session):
        if self._blocked(session):
            return
        try:
            # Existence/deletion is rechecked at save without changing order revision.
            self._record(self.customers_manager, self.customer)
            for identity, _ in session.form._tables['lines']._snapshot().rows:
                self._record(self.products_manager, self.products.get(identity))
        except BackendError:
            self._status(session, 'Choose a live customer and a live product for every line before saving')
            return
        super().save(session)

    def _start_choice(self, session, target, row=None):
        if self._blocked(session) or self.object is None:
            return
        if self.choice_serial >= self.choice_limit:
            self._status(session, 'Selection limit reached; save or discard and reopen the order')
            return
        if row is not None:
            session.form._tables['lines']._lookup_id(row)
        self.choice_serial += 1
        self.active_choice = OwnedChoice(self.generation, self.choice_serial, target, row)
        self.choice_result = _UNSET
        self._locked(session)
        self._status(session, 'Choose a record in the child form, or cancel to keep the current value')

    def choose_customer(self, session):
        self._start_choice(session, 'Customers')

    def choose_product(self, session):
        row = session.form.items._values['linestable'].current_row
        if row is None:
            self._status(session, 'Select an order line before choosing its product')
            return
        self._start_choice(session, 'Products', row)

    def stage_result(self, ticket, result):
        if ticket is not self.active_choice or self.choice_result is not _UNSET:
            raise ValueError('retired choice capability')
        if result is not None and type(result) is not CatalogKey:
            raise TypeError('server-owned catalog identity required')
        self.choice_result = result

    @property
    def result_ready(self):
        return self.active_choice is not None and self.choice_result is not _UNSET

    def apply_choice(self, session):
        if not self.result_ready:
            raise ValueError('no owned selection result')
        ticket, result = self.active_choice, self.choice_result
        # All fallible validation runs before installation or reference mutation.
        # A fault during installation cannot be reported as "previous value kept".
        # The broker treats that exceptional outcome as workspace-wide uncertainty.
        try:
            if ticket.generation != self.generation or ticket.target not in ('Customers', 'Products'):
                raise ValueError('stale owner generation')
            if (ticket.target == 'Customers') != (ticket.row is None):
                raise ValueError('invalid selection target')
            if ticket.row is not None:
                session.form._tables['lines']._lookup_id(ticket.row)
            customer, products = self.customer, dict(self.products)
            replacements = {}
            patches = {'status': 'Selection cancelled; the previous value was kept'}
            if result is not None:
                manager = self.customers_manager if ticket.target == 'Customers' else self.products_manager
                card = self._record(manager, result)
                patches['status'] = 'Selection applied; order is not yet saved'
                if ticket.target == 'Customers':
                    patches['customer'] = card.description
                    customer = result
                else:
                    price = card.values[0]
                    if type(price) is not Decimal or not price.is_finite() or not 0 <= price <= Decimal(1000000):
                        raise ValueError('invalid product price')
                    rows = session.form._tables['lines']._snapshot().rows
                    replacements['lines'] = tuple((identity,
                        (card.description, card.description, values[2], price, values[4])
                        if identity == ticket.row else values) for identity, values in rows)
                    products[ticket.row] = result
            rows = replacements.get('lines', session.form._tables['lines']._snapshot().rows)
            prospective = (tuple(session.form._data[k] for k in ('code', 'description', 'total')),
                tuple(values for _, values in rows), customer,
                tuple(products.get(identity) for identity, _ in rows))
            patches['dirty'] = prospective != self.baseline
            prepared = self._preflight(session, patches, replacements)
        except Exception:
            self._status(session, 'Selection could not be applied; owner and previous reference were kept')
            self.active_choice = None
            self.choice_result = _UNSET
            self._locked(session)
            return
        try:
            self._install(session, prepared)
            self.customer, self.products = customer, products
            self.active_choice = None
            self.choice_result = _UNSET
            self._locked(session)
        except BaseException:
            self.apply_uncertain = True
            raise


class CatalogChoiceSession:
    """Read-only child; exact row mapping is its only selection authority."""
    def __init__(self, context, target):
        if target not in ('Customers', 'Products'):
            raise ValueError('unsupported catalog choice')
        self.context, self.target = context, target
        self.choices = {}
        self.finished = False
        self.result = None

    def bindings(self):
        return tuple(FormServerBinding('Choice' + name, method) for name, method in (
            ('Search', self.search), ('Select', self.select), ('Cancel', self.cancel)))

    def search(self, session):
        if self.finished:
            raise ValueError('choice finished')
        manager = session.interpreter._catalogs.get_index(self.target)
        page = catalog_page(manager, session.form._data['searchcode'], ('code', 'description'))
        rows = OrdersWorkbenchSession._rows(session.form._tables['choices'], tuple(row.values for row in page.rows))
        status = ('Showing first 32; use an exact code to narrow the results' if page.continuation else
                  'Select a record, then Choose' if rows else 'No matching live records')
        prepared = OrdersWorkbenchSession._preflight(session, {'status': status}, {'choices': rows})
        OrdersWorkbenchSession._install(session, prepared)
        self.choices = {row[0]: saved.key for row, saved in zip(rows, page.rows)}

    def select(self, session):
        if self.finished:
            raise ValueError('choice finished')
        selected = session.form.items._values['choicestable'].current_row
        key = self.choices.get(selected)
        if key is None:
            session.form.set_member('Status', 'Select a record from the current results first')
            return
        try:
            ReferenceOrdersSession._record(session.interpreter._catalogs.get_index(self.target), key)
        except BackendError:
            session.form.set_member('Status', 'Selected record is no longer available; refresh the results')
            return
        self.result, self.finished = key, True

    def cancel(self, session):
        if not self.finished:
            self.result, self.finished = None, True
