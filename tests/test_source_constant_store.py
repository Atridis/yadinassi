"""Explicit source constants storage: no guessed initial values or foreign DBs."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_configuration_source_runtime import source
from test_source_session_parameters import declaration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_constants import source_constant_definitions
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.dates import BSLDate, TICKS_PER_SECOND


def configuration(extra=None):
    types = {
        'Text': '<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>16</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>',
        'Amount': '<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>6</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>',
        'Flag': '<v8:Type>xs:boolean</v8:Type>',
        'Date': '<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>',
        'Unsupported': '<v8:Type>v8:AnyRef</v8:Type>',
    }
    config = source().files[0].content
    children = ''.join('<Constant>'+name+'</Constant>' for name in types)
    files = {'Configuration.xml': config.replace(b'</Configuration>', ('<ChildObjects>'+children+'</ChildObjects></Configuration>').encode())}
    for name, body in types.items():
        xml = declaration(name, body).replace(b'SessionParameter', b'Constant')
        files['Constants/'+name+'.xml'] = xml.replace(b'</Properties>', b'<DataHistory>DontUse</DataHistory><FillChecking>DontCheck</FillChecking></Properties>')
    files.update(extra or {})
    return source(extra=files)


class SourceConstantStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)/'constants.sqlite'

    def store(self, package=None):
        result = SourceConstantStore.create(self.path, configuration() if package is None else package)
        self.addCleanup(result.close)
        return result

    def test_profile_and_source_binding_are_persisted(self):
        store = self.store()
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT profile,source_sha256,configuration_uuid FROM source_binding').fetchone()
        self.assertEqual(row, ('source-scalar-constants-extensions-v3', store.source_sha256, str(store.config_uuid)))

    def test_existing_file_never_overwritten(self):
        self.path.write_bytes(b'owner data')
        with self.assertRaises((ValueError, OSError)): self.store()
        self.assertEqual(self.path.read_bytes(), b'owner data')

    def test_symlink_destination_never_followed(self):
        target = self.path.with_name('target'); target.write_bytes(b'owner data')
        try: self.path.symlink_to(target)
        except OSError: self.skipTest('symlink unavailable')
        with self.assertRaises((ValueError, OSError)): self.store()
        self.assertEqual(target.read_bytes(), b'owner data')

    def test_missing_values_are_not_fake_defaults(self):
        store = self.store()
        for name in ('Text', 'Amount', 'Flag', 'Date'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'uninitialized constant'):
                store.get(name)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM constant_value').fetchone(), (0,))

    def test_scalar_roundtrips(self):
        store = self.store()
        for name, value in [('Text', 'Привет'), ('Amount', Decimal('42.25')), ('Flag', True), ('Date', BSLDate(TICKS_PER_SECOND))]:
            store.set(name, value)
            self.assertEqual(store.get(name), value)
            self.assertIs(type(store.get(name)), type(value))

    def test_committed_bytes_persist_after_close(self):
        store = self.store(); store.set('Flag', True); store.close()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT value_json FROM constant_value').fetchone(), ('["boolean",true]',))

    def test_each_get_reads_database(self):
        store = self.store(); store.set('Flag', True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE constant_value SET value_json=?', ('["boolean",false]',))
        self.assertIs(store.get('Flag'), False)

    def test_failed_validation_preserves_committed_value(self):
        store = self.store(); store.set('Text', 'original')
        for value in ('x' * 17, 42, True):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                store.set('Text', value)
            self.assertEqual(store.get('Text'), 'original')

    def test_numeric_qualifiers_reject_rounding_clamping_nonfinite(self):
        store = self.store(); store.set('Amount', Decimal('42'))
        for value in (Decimal('10000'), Decimal('1.234'), Decimal('NaN'), True, 42):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                store.set('Amount', value)
        self.assertEqual(store.get('Amount'), Decimal('42'))

    def test_numeric_text_bound_preserves_previous_value_without_transaction(self):
        store = self.store(); store.set('Amount', Decimal('42'))
        accepted = Decimal('1.' + '0' * 254)
        store.set('Amount', accepted)
        self.assertEqual(store.get('Amount').as_tuple(), accepted.as_tuple())
        statements = []
        store._connection.set_trace_callback(statements.append)
        with self.assertRaisesRegex(ValueError, 'Number text bound'):
            store.set('Amount', Decimal('1.' + '0' * 255))
        self.assertFalse(any(sql.upper().startswith('BEGIN') for sql in statements))
        self.assertEqual(store.get('Amount').as_tuple(), accepted.as_tuple())

    def test_date_boundary_and_fractional_ticks_rejected(self):
        store = self.store()
        for value in (BSLDate(1), BSLDate(0, boundary=True), None):
            with self.subTest(value=repr(value)), self.assertRaises((ValueError, TypeError)):
                store.set('Date', value)

    def test_boolean_not_integer(self):
        store = self.store()
        with self.assertRaises(TypeError): store.set('Flag', 0)

    def test_unsupported_known_and_unknown_names_are_distinct(self):
        store = self.store()
        self.assertTrue(store.has('Unsupported'))
        self.assertFalse(store.has('Missing'))
        with self.assertRaisesRegex(ValueError, 'unsupported constant'): store.get('Unsupported')
        with self.assertRaisesRegex(ValueError, 'unknown constant'): store.get('Missing')

    def test_nonempty_constant_module_blocks_set(self):
        store = self.store(configuration({'Constants/Text/Ext/ValueManagerModule.bsl': b'Procedure BeforeWrite(Cancel) EndProcedure'}))
        with self.assertRaisesRegex(ValueError, 'module execution'): store.set('Text', 'value')
        with self.assertRaisesRegex(ValueError, 'uninitialized'): store.get('Text')

    def test_history_policy_blocks_set(self):
        source = configuration(); mapping = {item.path: item.content for item in source.files}
        mapping['Constants/Text.xml'] = mapping['Constants/Text.xml'].replace(b'>DontUse<', b'>Use<')
        store = self.store(import_source(mapping))
        with self.assertRaisesRegex(ValueError, 'data history'): store.set('Text', 'value')

    def test_binding_tamper_rejected(self):
        store = self.store()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE source_binding SET source_sha256=?', ('0' * 64,))
        with self.assertRaisesRegex(ValueError, 'binding integrity'): store.get('Text')

    def test_value_tamper_rejected(self):
        store = self.store(); store.set('Flag', True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE constant_value SET value_json=?', ('["boolean",1]',))
        with self.assertRaisesRegex(ValueError, 'storage integrity'): store.get('Flag')

    def test_closed_store_rejected_and_close_idempotent(self):
        store = self.store(); store.close(); store.close()
        with self.assertRaisesRegex(ValueError, 'closed'): store.get('Text')
        with self.assertRaisesRegex(ValueError, 'closed'): store.set('Text', 'value')

    def test_declaration_names_match_source_inventory(self):
        source = configuration(); mapping = {item.path: item.content for item in source.files}
        del mapping['Constants/Text.xml']
        with self.assertRaisesRegex(ValueError, 'inventory'):
            source_constant_definitions(import_source(mapping))
