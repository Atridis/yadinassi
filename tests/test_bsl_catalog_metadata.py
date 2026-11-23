"""BSL metadata surface over a logical backend read view."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.configuration.configuration_diagnostics import ImportRefusal
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.configuration.metadata import BSLCatalogMetadataCollection
from sqlite_catalog_fixture import configuration_files


def catalog_configuration(names):
    # Use the existing fieldless catalog XML template; only invent the test's
    # own catalog names/identities and declare their explicit tree order.
    files = configuration_files()
    root = files['Configuration.xml'].replace(
        b'<Catalog>Categories</Catalog><Catalog>Products</Catalog>',
        ''.join(f'<Catalog>{name}</Catalog>' for name in names).encode('utf-8'))
    template = files['Catalogs/Categories.xml']
    result = {'Configuration.xml': root}
    for name in names:
        record = re.sub(rb'uuid="[^"]+"', f'uuid="{uuid4()}"'.encode(), template, count=1)
        result[f'Catalogs/{name}.xml'] = record.replace(
            b'<Name>Categories</Name>', f'<Name>{name}</Name>'.encode('utf-8'))
    return result


class CatalogMetadataRuntimeTests(unittest.TestCase):
    def runtime(self, names=('DifferentCatalog',)):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        context = SQLiteDBContext.create(Path(directory.name) / 'metadata.sqlite',
                                         import_configuration(catalog_configuration(names)))
        self.addCleanup(context.close)
        runtime = Interpreter(database_context=context)
        self.addCleanup(runtime.close)
        return runtime, context

    def test_lookup_is_lazy_even_without_database(self):
        runtime = Interpreter()
        self.addCleanup(runtime.close)
        for text in ('Metadata', 'Метаданные.Справочники',
                     'Если Ложь Тогда Metadata.Catalogs.Count(); КонецЕсли;'):
            runtime.execute(text)
        for text in ('Metadata.Catalogs.Count()', 'Metadata.Catalogs.Find("X")',
                     'Metadata.Catalogs.X', 'Metadata.Catalogs[0]'):
            with self.subTest(text=text), self.assertRaisesRegex(BSLRuntimeError, 'db required'):
                runtime.execute(text)
        self.assertEqual(runtime.execute('20 + 22'), Decimal(42))
        runtime.execute('Попытка Metadata.Catalogs.Count(); Исключение X = 42; КонецПопытки;')
        self.assertEqual(runtime.execute('X'), Decimal(42))

    def test_aliases_dynamic_names_identity_and_one_snapshot(self):
        runtime, _ = self.runtime(('ИнойСправочник',))
        statements = []
        connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        with patch.object(sqlite3, 'connect', traced_connect):
            self.assertEqual(runtime.execute('Metadata.Catalogs.Count()'), Decimal(1))
            self.assertEqual(runtime.execute('Метаданные.Справочники.ИнойСправочник.Имя'), 'ИнойСправочник')
            self.assertEqual(runtime.execute('Metadata.Catalogs[0].FullName()'), 'Справочник.ИнойСправочник')
            self.assertTrue(runtime.execute('(Metadata.Catalogs.Find("инойсправочник") = Метаданные.Справочники.ИнойСправочник)'))
            self.assertTrue(runtime.execute('(Metadata.Catalogs["ИНОЙСПРАВОЧНИК"] = Metadata.Catalogs[0])'))
        self.assertEqual(statements.count('SELECT definition FROM catalog_schema ORDER BY name,identity'), 1)

    def test_multi_names_count_not_invented_numeric_order(self):
        runtime, context = self.runtime(('Second', 'First'))
        self.assertEqual(runtime.execute('Metadata.Catalogs.Count()'), Decimal(2))
        self.assertEqual(runtime.execute('Metadata.Catalogs.First.Name'), 'First')
        self.assertEqual(runtime.execute('Metadata.Catalogs[0].Name'), 'Second')
        self.assertEqual(runtime.execute('Metadata.Catalogs[1].Name'), 'First')
        # The logical-only collection has the same rows, but has no source
        # declaration tree attached and must not guess an ordering.
        logical_only = BSLCatalogMetadataCollection(context)
        self.assertEqual(logical_only.count(), Decimal(2))
        with self.assertRaisesRegex(ValueError, 'ordering is unsupported'):
            logical_only.get(Decimal(0))

    def test_find_general_scalar_rule_and_missing_name(self):
        runtime, _ = self.runtime()
        for text in ('"Absent"', '1', '42', '-7', '1.5'):
            with self.subTest(text=text):
                self.assertIsNone(runtime.execute(f'Metadata.Catalogs.Find({text})'))
        for text in ('Истина', 'Undefined', 'Новый Массив'):
            with self.subTest(text=text), self.assertRaises(BSLRuntimeError):
                runtime.execute(f'Metadata.Catalogs.Find({text})')

    def test_readonly_arity_bounds_and_excluded_surfaces(self):
        runtime, _ = self.runtime()
        failures = ('Metadata.Catalogs.Find()', 'Metadata.Catalogs.Find("DifferentCatalog", 1)',
                    'Metadata.Catalogs.Count(1)', 'Metadata.Catalogs.Absent',
                    'Metadata.Catalogs[-1]', 'Metadata.Catalogs[1]', 'Metadata.Catalogs[0.5]',
                    'Metadata.Catalogs[Истина]', 'Metadata.Catalogs["Absent"]',
                    'Metadata.Catalogs.DifferentCatalog.Name = "Changed";',
                    'Metadata.Catalogs[0] = Undefined;', 'Metadata.Catalogs = Undefined;',
                    'Metadata.Catalogs.DifferentCatalog.FullName(1)',
                    'String(Metadata)', 'String(Metadata.Catalogs)',
                    'String(Metadata.Catalogs[0])')
        for text in failures:
            with self.subTest(text=text), self.assertRaises(BSLRuntimeError): runtime.execute(text)
        self.assertEqual(runtime.execute('Metadata.Catalogs[0].Name'), 'DifferentCatalog')

    def test_context_availability_and_missing_database_are_lazy(self):
        for directive in ('', '&AtServer\n', '&AtServerNoContext\n',
                          '&AtClientAtServerNoContext\n'):
            with self.subTest(directive=directive):
                runtime, _ = self.runtime()
                runtime.execute(directive + 'Function ReadName() '
                                'Return Metadata.Catalogs[0].Name; EndFunction')
                self.assertEqual(runtime.execute('ReadName()'), 'DifferentCatalog')
                missing = Interpreter()
                self.addCleanup(missing.close)
                missing.execute(directive + 'Function Lazy() '
                                'Return Metadata.Catalogs = Метаданные.Справочники; EndFunction\n'
                                + directive + 'Function ReadName() '
                                'Return Metadata.Catalogs[0].Name; EndFunction')
                self.assertTrue(missing.execute('Lazy()'))
                with self.assertRaisesRegex(BSLRuntimeError, 'db required'):
                    missing.execute('ReadName()')

    def test_server_metadata_stays_local_and_does_not_shadow_a_parameter(self):
        runtime = Interpreter()
        self.addCleanup(runtime.close)
        runtime.execute('''&AtServer
Function GetRoot() Return Metadata; EndFunction
&AtServerNoContext
Function Echo(Val Metadata) Return Metadata; EndFunction''')
        self.assertEqual(runtime.execute('Echo("local")'), 'local')
        with self.assertRaisesRegex(BSLRuntimeError, 'Межконтекстная передача'):
            runtime.execute('GetRoot()')

    def test_method_name_catalogs_remain_accessible_without_guessing_precedence(self):
        runtime, _ = self.runtime(('Count', 'Find'))
        self.assertEqual(runtime.execute('Metadata.Catalogs.Count()'), Decimal(2))
        self.assertEqual(runtime.execute('Metadata.Catalogs.Find("Count").Name'), 'Count')
        self.assertEqual(runtime.execute('Metadata.Catalogs["Find"].Name'), 'Find')
        with self.assertRaisesRegex(BSLRuntimeError, 'method-name property'):
            runtime.execute('Metadata.Catalogs.Count')

    def test_failed_load_is_not_cached(self):
        runtime, context = self.runtime(('Recovered',))
        with closing(sqlite3.connect(context.path, isolation_level=None)) as lock:
            lock.execute('BEGIN EXCLUSIVE')
            with self.assertRaises(BSLRuntimeError):
                runtime.execute('Metadata.Catalogs.Count()')
        self.assertEqual(runtime.execute('Metadata.Catalogs[0].Name'), 'Recovered')

    def test_ambiguous_casefold_rejected(self):
        # Real SQLite activation never receives ambiguous names: they are
        # refused before building the database, not silently collapsed.
        with self.assertRaisesRegex(ImportRefusal, 'case-colliding paths'):
            import_configuration(catalog_configuration(('Same', 'same')))

    def test_index_argument_can_be_read_without_mutation(self):
        runtime, _ = self.runtime()
        runtime.execute('Функция Read(Value) Возврат Value.Name; КонецФункции')
        self.assertEqual(runtime.execute('Read(Metadata.Catalogs[0])'), 'DifferentCatalog')
        runtime.execute('Процедура Write(Value) Value = Undefined; КонецПроцедуры')
        with self.assertRaisesRegex(BSLRuntimeError, 'read-only'):
            runtime.execute('Write(Metadata.Catalogs[0]);')

if __name__ == '__main__': unittest.main()
