from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.configuration.configuration_main_demo import PROFILE,import_main_demo_configuration
from yadinassi.db.catalog.catalog_object_preparation import CatalogWriteRefused,prepare_catalog_object,write_prepared_catalog_object
from yadinassi.db.catalog.catalog_backend import BackendError

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/demo/Catalogs/Номенклатура/Ext/ObjectModule.bsl').read_text(encoding='utf-8-sig')

class DirectCatalogPreparationTests(unittest.TestCase):
    def setUp(self, *, allow_extensions=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        files={p.relative_to(ROOT/'examples/demo').as_posix():p.read_bytes() for p in (ROOT/'examples/demo').rglob('*') if p.is_file()}
        self.db=SQLiteDBContext.create_main_demo(Path(temp.name)/'db.sqlite',import_main_demo_configuration(files,profile=PROFILE));self.addCleanup(self.db.close)
        self.vm=Interpreter(database_context=self.db, allow_extensions=allow_extensions);self.addCleanup(self.vm.close)
        self.cats=self.vm._catalogs
        self.kind=self.cats.get_member('ВидыНоменклатуры').create_item();self.kind.set_member('Наименование','Товары');self.kind.write()
        self.warehouse=self.cats.get_member('Склады').create_item();self.warehouse.set_member('Наименование','Основной');self.warehouse.write()
        self.card=self.cats.get_member('Номенклатура').create_item();self.card.set_member('Наименование','  Кабель  ')
        self.card.set_member('ВидНоменклатуры',self.kind.get_member('Ссылка'))
        self.card.get_member('Склады').add().set_member('Склад',self.warehouse.get_member('Ссылка'))

    def test_original_handler_writes_without_vm_execution(self):
        from yadinassi.db.catalog.catalog_object_preparation import _ObjectInterpreter
        with patch.object(_ObjectInterpreter,'execute_program',side_effect=AssertionError('VM execution')),patch.object(_ObjectInterpreter,'execute',side_effect=AssertionError('VM execution')):
            self.card.write()
        self.assertFalse(self.card.is_new());self.assertEqual(self.card.get_member('Наименование'),'Кабель')
        ref=self.card.get_member('Ссылка');saved=ref.get_object(ref)
        self.assertEqual(saved.get_member('Наименование'),'Кабель');self.assertEqual(saved.get_member('Склады').count(),1)

    def test_scalar_update_runs_handler_without_replacing_loaded_sections(self):
        self.card.write()
        backend=self.db.backend
        definition=self.card._manager._schema
        table=backend._section_layout.table_name(definition.identity,definition.tabular_sections[0].identity)
        connect=backend._connect
        trace=[]
        def open_connection(**kwargs):
            connection=connect(**kwargs)
            connection.set_trace_callback(trace.append)
            return connection
        before=self.card._write_draft()
        ref=self.card.get_member('Ref')
        row_ids=tuple(row.identity for row in self.card.get_member('Склады')._stored_rows().rows)
        self.assertIsNone(before.tabular_sections)
        self.card.set_member('Description','  Updated  ')
        with patch.object(backend,'_connect',side_effect=open_connection):
            self.card.write()
        self.assertEqual(self.card.get_member('Description'),'Updated')  # BeforeWrite trimmed.
        owner_table=backend._layout.table_name(definition.identity)
        self.assertTrue(any(sql.startswith('UPDATE') and owner_table in sql for sql in trace))
        self.assertFalse(any(sql.startswith(('DELETE','INSERT')) and table in sql for sql in trace))
        saved=ref.get_object(ref)
        self.assertEqual(tuple(row.identity for row in saved.get_member('Склады')._stored_rows().rows),row_ids)

    def test_denied_original_write_keeps_database_empty_and_messages(self):
        self.card.set_member('Наименование',' x ')
        self.card.set_member('ВидНоменклатуры',self.cats.get_member('ВидыНоменклатуры').empty_ref())
        self.card.get_member('Склады').clear()
        with self.assertRaises(CatalogWriteRefused) as result:self.card.write()
        self.assertEqual(len(result.exception.messages),3);self.assertTrue(self.card.is_new())
        self.assertIsNone(self.card._pending_write)
        self.assertIs(self.card._manager.select().next(),False)

    def test_duplicate_equal_separate_references_refuses_update(self):
        self.card.write()
        ref=self.warehouse.get_member('Ссылка')
        separate=self.warehouse._manager._ref(ref.reference_uuid)
        self.assertIsNot(ref,separate);self.assertEqual(ref,separate)
        self.card.get_member('Склады').add().set_member('Склад',separate)
        with self.assertRaises(CatalogWriteRefused) as error:self.card.write()
        self.assertIn('повтор',error.exception.messages[0].text.lower())
        cardref=self.card.get_member('Ссылка');saved=cardref.get_object(cardref)
        self.assertEqual(saved.get_member('Склады').count(),1)

    def test_marked_reference_checked_through_writer_view(self):
        self.card.write();self.warehouse.set_member('ПометкаУдаления',True);self.warehouse.write()
        self.card.set_member('Наименование','Другой товар')
        with self.assertRaises(CatalogWriteRefused):self.card.write()
        ref=self.card.get_member('Ссылка');self.assertEqual(ref.get_object(ref).get_member('Наименование'),'Кабель')

    def test_foreign_source_cannot_replace_selected_handler(self):
        with self.assertRaises(BackendError):write_prepared_catalog_object('Процедура ПередЗаписью(Отказ) КонецПроцедуры',self.card)
        self.assertTrue(self.card.is_new())

    def test_unavailable_method_rejected_before_candidate_mutation(self):
        source='Процедура ПередЗаписью(Отказ) Наименование="changed";ЭтотОбъект.Записать();КонецПроцедуры'
        with self.assertRaisesRegex(ValueError,'unavailable'):prepare_catalog_object(source,self.card)
        self.assertEqual(self.card.get_member('Наименование'),'  Кабель  ')

    def test_host_explicit_transaction_does_not_gain_handler_authority(self):
        from yadinassi.db import database_transactions as tx
        with self.assertRaises(BackendError):
            with tx.execution(self.db.backend):
                tx.begin(self.db.backend);self.card.write()
        self.assertIsNone(tx.current(self.db.backend));self.assertTrue(self.card.is_new())

    def test_host_preparation_without_write_retains_existing_api(self):
        with patch.object(self.db.backend,'begin_write',side_effect=AssertionError('write')):
            self.assertEqual(prepare_catalog_object(SOURCE,self.card),(False,()))
        self.assertTrue(self.card.is_new());self.assertEqual(self.card.get_member('Наименование'),'Кабель')

if __name__=='__main__':unittest.main()
