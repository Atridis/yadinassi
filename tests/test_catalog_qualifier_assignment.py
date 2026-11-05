"""Authored qualifier/atomicity tests; not CatalogObject native observations."""
from contextlib import closing, contextmanager
from dataclasses import replace
import decimal
from decimal import Decimal
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.catalog_backend import (BackendError, CatalogDraft, CatalogKey,
    CatalogSchema, FieldSchema, TabularRow, TabularSectionRows, TabularSectionSchema)
from yadinassi.catalog_qualifiers import (normalize_string, normalize_number,
    validate_string, _MAX_TEXT_CHARS, _MAX_DECIMAL_BYTES)
from yadinassi.configuration_xml import ConfigurationImport, ConfigurationFile, import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View, _encode, _decode, _json
from yadinassi.sqlite_catalog_layout import quote_identifier
from catalog_sections_fixture import configuration_files_with_sections


@contextmanager
def _sqlite_mutation(path):
    # sqlite3.Connection.__exit__ ends a transaction but does not close the
    # underlying handle. Close deterministically before TemporaryDirectory cleanup.
    with closing(sqlite3.connect(path)) as connection, connection:
        yield connection


class ScalarQualifierTests(unittest.TestCase):
    def test_utf16_variable_truncation_and_strict_validation(self):
        for text, length, expected in [('abcdef', 3, 'abc'), ('Я😀AB', 3, 'Я😀'),
                ('😀z', 2, '😀'), ('abc', 0, ''), ('', 3, ''), ('a\x00bc', 3, 'a\x00b'),
                ('e\u0301x', 1, 'e'), ('e\u0301x', 2, 'e\u0301')]:
            with self.subTest(text=text, length=length):
                self.assertEqual(normalize_string(text, length), expected)
                validate_string(expected, length)
                self.assertEqual(normalize_string(expected, length), expected)
        with self.assertRaises(ValueError): validate_string('😀', 1)

    def test_split_surrogate_and_malformed_suffix_are_never_replaced(self):
        for text, length in [('Я😀Z', 2), ('😀', 1), ('x\ud800', 1),
                             ('\udfff', 3), ('\ud83d\ude00', 2)]:
            with self.subTest(text=repr(text)), self.assertRaises(UnicodeError):
                normalize_string(text, length)

    def test_string_resource_limit_is_before_truncation(self):
        self.assertEqual(normalize_string('a' * _MAX_TEXT_CHARS, 1), 'a')
        with self.assertRaisesRegex(ValueError, 'resource limit'):
            normalize_string('a' * (_MAX_TEXT_CHARS + 1), 1)
        for value in (None, True, 123, Decimal(1), b'abc'):
            with self.subTest(value=value), self.assertRaises(TypeError):
                normalize_string(value, 3)
        for length in (True, -1, 65537, Decimal(3), '3'):
            with self.subTest(length=length), self.assertRaises(ValueError):
                normalize_string('x', length)

    def test_number_half_up_saturation_sign_and_fraction_only(self):
        examples = [('1.235', '1.24'), ('1.245', '1.25'), ('-1.245', '-1.25'),
                    ('999.995', '999.99'), ('1000', '999.99'), ('-1000', '-999.99'),
                    ('12.344', '12.34'), ('-0.005', '-0.01'), ('-0.004', '0')]
        for source, expected in examples:
            with self.subTest(source=source):
                actual = normalize_number(Decimal(source), (5, 2, 'Any'))
                self.assertEqual(actual, Decimal(expected))
                self.assertEqual(normalize_number(actual, (5, 2, 'Any')), actual)
        self.assertEqual(normalize_number(Decimal('-1.235'), (5, 2, 'Nonnegative')), 0)
        self.assertEqual(normalize_number(Decimal('1.5'), (1, 1, 'Any')), Decimal('.9'))
        self.assertEqual(normalize_number(Decimal('9.5'), (1, 0, 'Any')), 9)

    def test_extreme_exponents_are_bounded_and_zero_sign_is_preserved(self):
        for text, expected in [('1E+999999999', '999.99'), ('-1E+999999999', '-999.99'),
                               ('1E-999999999', '0'), ('-1E-999999999', '0')]:
            self.assertEqual(normalize_number(Decimal(text), (5, 2, 'Any')), Decimal(expected))
        for sign in (0, 1):
            value = Decimal((sign, (0,), -999999999))
            self.assertEqual(normalize_number(value, (5, 2, 'Any')).as_tuple(),
                             Decimal((sign, (0,), -2)).as_tuple())

    def test_ambient_decimal_context_has_no_effect_or_flags(self):
        with decimal.localcontext() as context:
            context.prec = 1; context.rounding = decimal.ROUND_DOWN
            context.Emin = -1; context.Emax = 1
            for signal in context.traps: context.traps[signal] = True
            context.clear_flags()
            field = FieldSchema(uuid4(), 'Amount', 'number', (5, 2, 'Any'))
            for source, expected in [('1.245', '1.25'), ('999.995', '999.99'), ('-0.004', '0.00')]:
                value = normalize_number(Decimal(source), field.qualifiers)
                self.assertEqual(_encode(value, field, uuid4()), ['n', expected])
            self.assertFalse(any(context.flags.values()))

    def test_number_exact_type_finiteness_resource_and_qualifier_limits(self):
        for value in (True, 1, 1.25, '1.25', None, Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity')):
            with self.subTest(value=repr(value)), self.assertRaises((TypeError, ValueError)):
                normalize_number(value, (5, 2, 'Any'))
        oversized = Decimal('1' * 10000)
        self.assertGreater(oversized.__sizeof__(), _MAX_DECIMAL_BYTES)
        with self.assertRaisesRegex(ValueError, 'resource limit'):
            normalize_number(oversized, (5, 2, 'Any'))
        for qualifiers in ((True, 2, 'Any'), (5, True, 'Any'), (39, 2, 'Any'),
                           (5, 6, 'Any'), (0, 0, 'Any'), (5, 2, 'Unknown'), [5, 2, 'Any']):
            with self.subTest(qualifiers=qualifiers), self.assertRaises(ValueError):
                normalize_number(Decimal(1), qualifiers)

    def test_hostile_default_and_current_decimal_context_are_untouched(self):
        default = decimal.DefaultContext; saved = default.copy()
        attributes = ('prec', 'rounding', 'Emin', 'Emax', 'capitals', 'clamp', 'flags', 'traps')
        try:
            with decimal.localcontext() as current:
                for context in (default, current):
                    context.prec = 1; context.rounding = decimal.ROUND_DOWN
                    context.Emin = 0; context.Emax = 0; context.clamp = 1
                    for signal in context.traps: context.traps[signal] = True
                    context.clear_flags(); context.flags[decimal.Inexact] = True
                snapshots = [context.copy() for context in (default, current)]
                field = FieldSchema(uuid4(), 'Amount', 'number', (5, 2, 'Any'))
                for source, expected in [('1.245', '1.25'), ('999.995', '999.99'), ('-0', '-0.00')]:
                    value = normalize_number(Decimal(source), field.qualifiers)
                    self.assertEqual(_encode(value, field, uuid4()), ['n', expected])
                for scale in (0, 19, 38):
                    field = FieldSchema(uuid4(), 'Wide', 'number', (38, scale, 'Any'))
                    maximum = Decimal((0, (9,) * 38, -scale))
                    actual = normalize_number(Decimal('1E+999999999'), field.qualifiers)
                    self.assertEqual(actual, maximum)
                    self.assertEqual(_encode(actual, field, uuid4()), ['n', format(maximum, 'f')])
                for context, snapshot in zip((default, current), snapshots):
                    for attribute in attributes:
                        self.assertEqual(getattr(context, attribute), getattr(snapshot, attribute))
        finally:
            for attribute in attributes: setattr(default, attribute, getattr(saved, attribute))

    def test_storage_codecs_remain_strict_not_normalizing(self):
        number = FieldSchema(uuid4(), 'Amount', 'number', (5, 2, 'Nonnegative'))
        text = FieldSchema(uuid4(), 'Text', 'string', (3,))
        for value, field in [(Decimal('1.234'), number), (Decimal('-1'), number),
                             (Decimal('1000'), number), ('four', text), ('😀😀', text)]:
            with self.subTest(value=value), self.assertRaisesRegex(BackendError, 'invalid_input'):
                _encode(value, field, uuid4())
        for encoded, field in [(['n', '1.234'], number), (['n', '-1.00'], number),
                               (['n', '1.230'], number), (['s', 'four'], text), (['s', '😀😀'], text)]:
            with self.subTest(encoded=encoded), self.assertRaisesRegex(BackendError, 'integrity'):
                _decode(encoded, field, uuid4())


class RuntimeQualifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'qualifiers.sqlite'
        self.files = {name: data.replace(b'<v8:Length>32', b'<v8:Length>3')
                .replace(b'<v8:Length>128', b'<v8:Length>3')
                .replace(b'<v8:Digits>12', b'<v8:Digits>5')
                .replace(b'<CodeLength>8', b'<CodeLength>3')
                .replace(b'<DescriptionLength>64', b'<DescriptionLength>3')
            for name, data in configuration_files_with_sections().items()}
        self.context = SQLiteDBContext.create(self.path, import_configuration(self.files))
        self.addCleanup(lambda: self.context.close())
        self.vm = Interpreter(database_context=self.context)
        self.vm.execute('O=Catalogs.Products.CreateItem(); O.Code="10"; R=O.Lines.Add();')
        self.obj = self.vm.execute('O'); self.section = self.vm.execute('O.Lines'); self.row = self.vm.execute('R')

    def test_assignments_change_detached_values_before_write_and_survive_reopen(self):
        self.vm.execute('O.Code="123456"; O.Description="Я😀AB"; O.Text="abcdef";'
                        'O.Amount=1.245; R.Text="Я😀AB"; R.Amount=-1.245;')
        self.assertEqual(self.obj.get_member('Code'), '123')
        self.assertEqual(self.obj.get_member('Description'), 'Я😀')
        self.assertEqual(self.obj.get_member('Text'), 'abc')
        self.assertEqual(self.obj.get_member('Amount'), Decimal('1.25'))
        self.assertEqual(self.row.get_member('Text'), 'Я😀')
        self.assertEqual(self.row.get_member('Amount'), Decimal('-1.25'))
        self.obj.write(); self.context.close(); self.context = SQLiteDBContext(self.path)
        vm = Interpreter(database_context=self.context)
        saved = vm.execute('Catalogs.Products.FindByCode("123").GetObject()')
        self.assertEqual(saved.get_member('Description'), 'Я😀')
        self.assertEqual(saved.get_member('Amount'), Decimal('1.25'))
        self.assertEqual(saved.get_member('Lines').get(Decimal(0)).get_member('Amount'), Decimal('-1.25'))
        self.assertEqual(self.context.backend.export_configuration(), self.files)

    def test_bad_assignments_preserve_values_bytes_dirty_revision_and_operation(self):
        self.row.set_member('Text', 'old'); self.obj.write()
        for target, name, value in [(self.obj, 'Code', 'ab😀'), (self.obj, 'Description', 'ab😀'),
                (self.obj, 'Text', 'ab😀'), (self.row, 'Text', 'ab😀'),
                (self.row, 'Text', 'abc\ud800'), (self.obj, 'Text', 'x' * 65537),
                (self.row, 'Amount', Decimal('1' * 10000)), (self.obj, 'Amount', True),
                (self.row, 'Amount', Decimal('NaN'))]:
            before = (dict(self.obj._values), dict(self.row._values), self.row._bytes,
                      self.section._bytes, self.section._dirty, self.obj._revision, self.obj._operation_id)
            with self.subTest(name=name, value=repr(value)[:80]), self.assertRaises((TypeError, ValueError)):
                target.set_member(name, value)
            self.assertEqual((dict(self.obj._values), dict(self.row._values), self.row._bytes,
                      self.section._bytes, self.section._dirty, self.obj._revision, self.obj._operation_id), before)
            self.assertIsNone(self.obj._pending_write)

    def test_conversion_and_budget_exceptions_are_before_mutation(self):
        self.obj.write()
        before = (self.row._bytes, self.section._bytes, self.section._dirty, dict(self.row._values))
        with patch('yadinassi.catalogs.normalize_field', side_effect=MemoryError('injected')):
            with self.assertRaises(MemoryError): self.row.set_member('Amount', Decimal('1.245'))
        with patch('yadinassi.catalog_sections._MAX_BUFFER_BYTES', self.obj._section_buffer_bytes()):
            with self.assertRaisesRegex(ValueError, 'buffer limit'): self.row.set_member('Text', 'abcdef')
        self.assertEqual((self.row._bytes, self.section._bytes, self.section._dirty, dict(self.row._values)), before)

    def test_nonnegative_owner_and_row_conversion_is_on_assignment(self):
        files = {name: data.replace(b'<v8:AllowedSign>Any', b'<v8:AllowedSign>Nonnegative')
                 for name, data in self.files.items()}
        context = SQLiteDBContext.create(Path(self.temp.name) / 'positive.sqlite', import_configuration(files))
        try:
            vm = Interpreter(database_context=context)
            vm.execute('O=Catalogs.Products.CreateItem(); O.Amount=-1.235; '
                       'R=O.Lines.Add(); R.Amount=-3;')
            self.assertEqual(vm.execute('O.Amount'), Decimal(0))
            self.assertEqual(vm.execute('R.Amount'), Decimal(0))
        finally: context.close()

    def test_normalized_code_collision_preserves_second_buffer(self):
        self.obj.set_member('Code', '123first'); self.obj.write()
        other = self.vm.execute('Catalogs.Products.CreateItem()')
        other.set_member('Code', '123second')
        with self.assertRaisesRegex(BackendError, 'duplicate_code'): other.write()
        self.assertTrue(other.is_new()); self.assertEqual(other.get_member('Code'), '123')
        self.assertIsNone(other._pending_write)

    def test_uncertainty_freezes_normalized_owner_and_rows(self):
        self.obj.set_member('Code', '123tail'); self.obj.set_member('Amount', Decimal('999.995'))
        self.row.set_member('Text', 'Я😀AB'); self.row.set_member('Amount', Decimal('1.245'))
        commit = _View.commit
        def lose_response(tx):
            commit(tx); raise BackendError('uncertain_commit')
        with patch.object(_View, 'commit', lose_response), self.assertRaises(BackendError): self.obj.write()
        pending = self.obj._pending_write
        self.assertEqual(pending[0].code, '123')
        self.assertEqual(pending[0].values[1], Decimal('999.99'))
        self.assertEqual(pending[0].tabular_sections[0].rows[0].values[:2], ('Я😀', Decimal('1.25')))
        for target in (self.obj, self.row):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'): target.set_member('Text', 'new')
        self.assertIs(self.obj._pending_write, pending)
        with patch.object(_View, 'commit', side_effect=AssertionError('must not recommit')): self.obj.write()
        self.assertIsNone(self.obj._pending_write); self.assertFalse(self.section._dirty)


class BackendQualifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'qualifiers.sqlite'
        fields = (FieldSchema(uuid4(), 'Text', 'string', (3,)),
                  FieldSchema(uuid4(), 'Amount', 'number', (5, 2, 'Any')),
                  FieldSchema(uuid4(), 'Positive', 'number', (5, 2, 'Nonnegative')))
        self.section = TabularSectionSchema(uuid4(), 'Lines', fields)
        self.schema = CatalogSchema(uuid4(), 'Products', 3, 3, fields, (self.section,))
        self.config = ConfigurationImport(config_uuid=uuid4(), name='Owned', activation_issues=(),
            catalogs=(self.schema,), files=(ConfigurationFile('Configuration.xml', b'<owned/>', 'xml'),), modules=())
        self.backend = SQLiteCatalogBackend.create(self.path, self.config)
        self.addCleanup(lambda: self.backend.close())

    def test_sqlite_mutation_closes_on_success_and_exception(self):
        path = self.path.with_name('mutation-check.sqlite')
        with _sqlite_mutation(path) as connection:
            connection.execute('CREATE TABLE probe(value INTEGER)')
        for fail in (False, True):
            connection = None
            try:
                with _sqlite_mutation(path) as connection:
                    connection.execute('INSERT INTO probe VALUES(?)', (2 if fail else 1,))
                    if fail: raise RuntimeError('test rollback')
            except RuntimeError:
                self.assertTrue(fail)
            self.assertIsNotNone(connection)
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute('SELECT 1')
        with _sqlite_mutation(path) as connection:
            self.assertEqual(connection.execute('SELECT value FROM probe').fetchall(), [(1,)])
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')

    def draft(self, code='123tail', *, sections=True):
        values = ('Я😀tail', Decimal('1.245'), Decimal('-1.235'))
        return CatalogDraft(CatalogKey(self.backend.database_id, self.schema.identity, uuid4()),
            code, 'abcdef', False, values,
            (TabularSectionRows(self.section.identity, (TabularRow(uuid4(), values),)),) if sections else None)

    def create(self, draft, operation=None):
        tx = self.backend.begin_write(operation or uuid4())
        try:
            tx.create(draft); return tx.commit()[0]
        finally: tx.close()

    def read(self, key):
        view = self.backend.begin_read()
        try: return view.read_catalog(key)
        finally: view.close()

    def test_direct_create_and_update_normalize_without_mutating_input(self):
        draft = self.draft(); original = repr(draft); revision = self.create(draft)
        card = self.read(draft.key)
        self.assertEqual((card.code, card.description), ('123', 'abc'))
        self.assertEqual(card.values, ('Я😀', Decimal('1.25'), Decimal(0)))
        self.assertEqual(card.tabular_sections[0].rows[0].values, card.values)
        self.assertEqual(repr(draft), original)
        changed = replace(draft, values=('xyzmore', Decimal('-1000'), Decimal('1000')))
        tx = self.backend.begin_write(uuid4())
        try: tx.update(changed, revision); tx.commit()
        finally: tx.close()
        self.assertEqual(self.read(draft.key).values, ('xyz', Decimal('-999.99'), Decimal('999.99')))

    def test_equivalent_normalized_intents_resolve_and_different_result_conflicts(self):
        draft = self.draft(); operation = uuid4(); revision = self.create(draft, operation)
        self.assertEqual(self.backend.resolve_write(operation, draft), revision)
        card = self.read(draft.key)
        equivalent = replace(draft, code=card.code, description=card.description,
                             values=card.values, tabular_sections=card.tabular_sections)
        self.assertEqual(self.backend.resolve_write(operation, equivalent), revision)
        with self.assertRaisesRegex(BackendError, 'conflict'):
            self.backend.resolve_write(operation, replace(equivalent, code='new'))

    def test_update_receipt_resolves_same_normalized_intent_and_expected_revision(self):
        draft = self.draft(); previous = self.create(draft); operation = uuid4()
        changed = replace(draft, values=('longer', Decimal('999.995'), Decimal('-1000')))
        tx = self.backend.begin_write(operation)
        try: tx.update(changed, previous); revision = tx.commit()[0]
        finally: tx.close()
        self.assertEqual(self.backend.resolve_write(operation, changed, previous), revision)
        equivalent = replace(changed, values=('lon', Decimal('999.99'), Decimal(0)))
        self.assertEqual(self.backend.resolve_write(operation, equivalent, previous), revision)
        with self.assertRaisesRegex(BackendError, 'conflict'):
            self.backend.resolve_write(operation, equivalent, revision)

    def test_receipt_normalizes_values_but_keeps_row_uuid_order_significant(self):
        draft = self.draft()
        first = draft.tabular_sections[0].rows[0]
        second = TabularRow(uuid4(), ('abcdef', Decimal('999.995'), Decimal('-1000')))
        draft = replace(draft, tabular_sections=(TabularSectionRows(self.section.identity, (first, second)),))
        operation = uuid4(); revision = self.create(draft, operation)
        card = self.read(draft.key)
        canonical = replace(draft, code=card.code, description=card.description,
                            values=card.values, tabular_sections=card.tabular_sections)
        self.assertEqual(self.backend.resolve_write(operation, canonical), revision)
        reordered = replace(canonical, tabular_sections=(TabularSectionRows(self.section.identity,
                                tuple(reversed(canonical.tabular_sections[0].rows))),))
        with self.assertRaisesRegex(BackendError, 'conflict'):
            self.backend.resolve_write(operation, reordered)

    def test_legacy_canonical_receipt_with_signed_zero_is_byte_identical(self):
        draft = replace(self.draft(sections=False), code='123', description='abc',
                        values=('old', Decimal('-0.00'), Decimal('1.23000')))
        operation = uuid4(); self.create(draft, operation)
        encoded = _json([['s', 'old'], ['n', '-0.00'], ['n', '1.23']])
        intent = [[str(self.schema.identity), str(draft.key.record_id), '123', 'abc', False, encoded, 1]]
        expected = hashlib.sha256(_json(intent).encode('utf-8')).hexdigest()
        self.assertEqual(self.backend.committed_operation(operation)[0], expected)

    def test_bad_late_row_does_not_mutate_owner_or_receipt_and_prior_change_can_commit(self):
        prior = self.draft('old'); operation = uuid4(); tx = self.backend.begin_write(operation)
        try:
            tx.create(prior)
            bad = self.draft('new')
            rows = bad.tabular_sections[0].rows
            bad = replace(bad, tabular_sections=(TabularSectionRows(self.section.identity,
                rows + (TabularRow(uuid4(), ('ab😀', Decimal(0), Decimal(0))),)),))
            before = (list(tx._changes), list(tx._intents), tx._section_write_bytes, tx._section_write_rows)
            with self.assertRaisesRegex(BackendError, 'invalid_input'): tx.create(bad)
            self.assertEqual((tx._changes, tx._intents, tx._section_write_bytes, tx._section_write_rows), before)
            self.assertIsNone(tx.read_catalog(bad.key))
            self.assertEqual(len(tx.commit()), 1)
        finally: tx.close()
        self.assertEqual(len(self.backend.committed_operation(operation)[1]), 1)

    def test_duplicate_code_and_stale_revision_leave_normalized_rows_unchanged(self):
        draft = self.draft(); revision = self.create(draft)
        with self.assertRaisesRegex(BackendError, 'duplicate_code'): self.create(self.draft('123different'))
        tx = self.backend.begin_write(uuid4())
        try: tx.update(draft, revision); tx.commit()
        finally: tx.close()
        before = self.read(draft.key)
        tx = self.backend.begin_write(uuid4())
        try:
            with self.assertRaisesRegex(BackendError, 'conflict'):
                tx.update(replace(draft, description='newer'), revision)
            self.assertEqual(tx._changes, []); self.assertEqual(tx._intents, [])
        finally: tx.close()
        self.assertEqual(self.read(draft.key), before)

    def test_resource_and_type_failures_before_sql(self):
        base = self.draft()
        for draft in (replace(base, code='x' * 65537), replace(base, description='abc\ud800'),
                replace(base, values=('ok', Decimal('1' * 10000), Decimal(0))),
                replace(base, values=('ok', True, Decimal(0)))):
            tx = self.backend.begin_write(uuid4())
            try:
                with self.assertRaisesRegex(BackendError, 'invalid_input'): tx.create(draft)
                self.assertEqual(tx._changes, []); self.assertEqual(tx._intents, [])
                self.assertIsNone(tx.read_catalog(draft.key))
            finally: tx.close()

    def test_conversion_exception_before_sql_and_receipt(self):
        draft = self.draft(); tx = self.backend.begin_write(uuid4())
        try:
            with patch('yadinassi.sqlite_catalog.normalize_field', side_effect=MemoryError('injected')):
                with self.assertRaises(MemoryError): tx.create(draft)
            self.assertEqual(tx._changes, []); self.assertEqual(tx._intents, [])
            self.assertIsNone(tx.read_catalog(draft.key))
        finally: tx.close()

    def test_late_row_conversion_exception_preserves_prior_success(self):
        draft = self.draft(); tx = self.backend.begin_write(uuid4())
        try:
            tx.create(self.draft('old'))
            before = (list(tx._changes), list(tx._intents), tx._section_write_bytes, tx._section_write_rows)
            from yadinassi.catalog_qualifiers import normalize_field
            calls = 0
            def fail_on_section(value, field):
                nonlocal calls
                calls += 1
                if calls == len(self.schema.fields) + 2: raise MemoryError('injected in row')
                return normalize_field(value, field)
            with patch('yadinassi.sqlite_catalog.normalize_field', side_effect=fail_on_section):
                with self.assertRaises(MemoryError): tx.create(draft)
            self.assertEqual((tx._changes, tx._intents, tx._section_write_bytes, tx._section_write_rows), before)
            self.assertIsNone(tx.read_catalog(draft.key))
            self.assertEqual(len(tx.commit()), 1)
        finally: tx.close()

    def test_bookkeeping_faults_rollback_sql_and_all_partial_journal_updates(self):
        from contextlib import nullcontext
        import yadinassi.sqlite_catalog as storage
        original = _View._record_change
        stages = ('Revision', '_intent', '_json', 'changes_copy', 'intents_copy',
                  '_changes', '_intents', '_section_write_bytes', '_section_write_rows', 'after_all')
        case = 0
        for updating in (False, True):
            for stage in stages:
                for error_type in (MemoryError, KeyboardInterrupt):
                    case += 1
                    with self.subTest(updating=updating, stage=stage, error=error_type.__name__):
                        target = self.draft('t%02d' % case)
                        revision = self.create(target) if updating else None
                        expected = self.read(target.key) if updating else None
                        operation = uuid4(); prior = self.draft('p%02d' % case)
                        tx = self.backend.begin_write(operation)
                        try:
                            tx.create(prior)
                            before = (tx._changes, tx._intents, tx._section_write_bytes, tx._section_write_rows)
                            def fail(view, *args):
                                if stage in ('Revision', '_intent', '_json'):
                                    guard = patch.object(storage, stage, side_effect=error_type('injected'))
                                elif stage in ('changes_copy', 'intents_copy'):
                                    attribute = '_changes' if stage == 'changes_copy' else '_intents'
                                    class FailingCopy(list):
                                        def __iter__(self): raise error_type('list allocation fault')
                                    setattr(view, attribute, FailingCopy(getattr(view, attribute)))
                                    guard = nullcontext()
                                elif stage.startswith('_'):
                                    def setter(instance, name, value):
                                        if name == stage: raise error_type('journal assignment fault')
                                        object.__setattr__(instance, name, value)
                                    guard = patch.object(_View, '__setattr__', setter, create=True)
                                else: guard = nullcontext()
                                with guard: original(view, *args)
                                if stage == 'after_all': raise error_type('post-bookkeeping fault')
                            with patch.object(_View, '_record_change', fail), self.assertRaises(error_type):
                                if updating: tx.update(replace(target, description='new'), revision)
                                else: tx.create(target)
                            self.assertIs(tx._changes, before[0]); self.assertIs(tx._intents, before[1])
                            self.assertEqual((tx._section_write_bytes, tx._section_write_rows), before[2:])
                            self.assertFalse(tx._poisoned)
                            self.assertEqual(tx.read_catalog(target.key), expected)
                            revisions = tx.commit()
                            self.assertEqual(tuple(r.record_id for r in revisions), (prior.key.record_id,))
                        finally: tx.close()
                        self.assertEqual(self.backend.resolve_write(operation, prior), revisions[0])

    def test_bookkeeping_cleanup_baseexception_poison_prevents_commit_even_if_close_fails(self):
        from test_sqlite_catalog_sections import ConnectionFault
        for fail_close in (False, True):
            operation = uuid4(); draft = self.draft()
            tx = self.backend.begin_write(operation)
            def fail_rollback(connection, sql, args):
                if sql.startswith('ROLLBACK TO '): raise KeyboardInterrupt('rollback interrupted')
                return connection.execute(sql, args)
            tx._connection = ConnectionFault(tx._connection, fail_rollback)
            try:
                from contextlib import nullcontext
                close = patch.object(tx, 'close', side_effect=OSError('close interrupted')) if fail_close else nullcontext()
                with close, patch.object(_View, '_record_change', side_effect=MemoryError('bookkeeping fault')):
                    with self.assertRaises((MemoryError, OSError)): tx.create(draft)
                self.assertTrue(tx._poisoned)
                with self.assertRaisesRegex(BackendError, 'closed'): tx.commit()
            finally: tx.close()
            self.assertIsNone(self.read(draft.key))
            self.assertIsNone(self.backend.committed_operation(operation))

    def test_matching_digest_requires_exact_canonical_receipt_revision(self):
        for updating in (False, True):
            draft = self.draft('upd' if updating else 'crt'); operation = uuid4()
            previous = self.create(draft) if updating else None
            if updating:
                tx = self.backend.begin_write(operation)
                try: tx.update(draft, previous); revision = tx.commit()[0]
                finally: tx.close()
            else: revision = self.create(draft, operation)
            catalog, record, token = str(self.schema.identity), str(draft.key.record_id), revision.token
            malformed = [[str(uuid4()), record, token], [catalog, str(uuid4()), token],
                [catalog, record, str(int(token) + 1)], [catalog, record, int(token)],
                [catalog, record, '0' + token], ['{' + catalog + '}', record, token],
                [catalog, record, '9223372036854775808'], [catalog, record, '١']]
            for entry in malformed:
                with self.subTest(updating=updating, entry=entry):
                    with _sqlite_mutation(self.path) as connection:
                        connection.execute('UPDATE commit_receipt SET revisions_json=? WHERE operation_id=?',
                                           (_json([entry]), str(operation)))
                    before = self.path.read_bytes()
                    with self.assertRaisesRegex(BackendError, 'integrity'):
                        self.backend.resolve_write(operation, draft, previous)
                    self.assertEqual(self.path.read_bytes(), before)
            with _sqlite_mutation(self.path) as connection:
                connection.execute('UPDATE commit_receipt SET revisions_json=? WHERE operation_id=?',
                                   (_json([[catalog, record, token]]), str(operation)))
            self.assertEqual(self.backend.resolve_write(operation, draft, previous), revision)

    def test_persisted_out_of_range_strings_and_numbers_are_not_repaired(self):
        draft = self.draft(); self.create(draft)
        table = quote_identifier(self.backend._layout.table_name(self.schema.identity))
        field = quote_identifier(self.backend._layout.field_name(self.schema.identity, self.schema.fields[1].identity))
        for column, bad, good in [('code', '😀😀', '123'), (field, '1.234', '1.25')]:
            with _sqlite_mutation(self.path) as connection:
                connection.execute('UPDATE %s SET %s=?' % (table, column), (bad,))
            with self.assertRaisesRegex(BackendError, 'integrity'): self.read(draft.key)
            with _sqlite_mutation(self.path) as connection:
                connection.execute('UPDATE %s SET %s=?' % (table, column), (good,))

    def test_legacy_codepoint_only_values_and_receipts_fail_closed_without_repair(self):
        draft = replace(self.draft(sections=False), code='123', description='abc',
                        values=('old', Decimal('1.25'), Decimal(0)))
        operation = uuid4(); self.create(draft, operation)
        table = quote_identifier(self.backend._layout.table_name(self.schema.identity))
        text = quote_identifier(self.backend._layout.field_name(self.schema.identity, self.schema.fields[0].identity))
        # Both were within the former three-Python-codepoint bound. One splits
        # a surrogate; the other would truncate cleanly to a different intent.
        for legacy_text, failure in [('😀😀', 'invalid_input'), ('😀ab', 'conflict')]:
            legacy = replace(draft, code=legacy_text, values=(legacy_text,) + draft.values[1:])
            encoded = _json([['s', legacy_text], ['n', '1.25'], ['n', '0.00']])
            intent = [[str(self.schema.identity), str(draft.key.record_id), legacy_text, 'abc', False, encoded, 1]]
            digest = hashlib.sha256(_json(intent).encode('utf-8')).hexdigest()
            with _sqlite_mutation(self.path) as connection:
                connection.execute('UPDATE %s SET code=?,%s=?' % (table, text), (legacy_text, legacy_text))
                connection.execute('UPDATE commit_receipt SET request_hash=? WHERE operation_id=?', (digest, str(operation)))
            before = self.path.read_bytes(); raw = repr(legacy)
            with self.assertRaisesRegex(BackendError, 'integrity'): self.read(draft.key)
            with self.assertRaisesRegex(BackendError, failure): self.backend.resolve_write(operation, legacy)
            self.assertEqual(self.backend.committed_operation(operation)[0], digest)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(repr(legacy), raw)


if __name__ == '__main__': unittest.main()
