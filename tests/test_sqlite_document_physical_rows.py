from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import UUID, uuid4

from yadinassi import Interpreter
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.catalog.catalog_backend import CatalogKey, FieldSchema, TabularRow, TabularSectionRows
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.document.document_backend import DocumentDraft, DocumentKey
from yadinassi.db.sqlite.sqlite_document_layout import data_table, section_table
from yadinassi.db.sqlite.sqlite_typed_rows import attribute_column
from test_document_configuration_xml import document_files


class PhysicalDocumentRowsTests(unittest.TestCase):
    def test_obsolete_document_header_in_posting_database_is_not_admitted(self):
        from yadinassi.configuration.configuration_posting import PROFILE, import_posting_configuration
        from yadinassi.db.catalog.catalog_backend import BackendError
        from test_document_posting_runtime import posting_source

        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        path = Path(directory.name)/'typed-posting.sqlite'
        with SQLiteDBContext.create_posting(path,import_posting_configuration(posting_source(),posting_runtime=PROFILE)):
            pass
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("ALTER TABLE document_record ADD COLUMN values_json TEXT NOT NULL DEFAULT '[]'")
        with self.assertRaisesRegex(BackendError,'unsupported'): SQLiteDBContext(path)

    def test_document_create_reopen_and_order_scale_columns_without_json(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        path = Path(directory.name)/'typed.sqlite'
        config = import_configuration(document_files())
        original, = config.documents
        wide = FieldSchema(uuid4(),'Wide','number',(38,17,'Any'))
        line_wide = replace(wide,identity=uuid4())
        source, = original.tabular_sections
        lines = replace(source,fields=(*source.fields,line_wide))
        schema = replace(original,fields=(*original.fields,wide),tabular_sections=(lines,))
        old = config.documents[0]
        config = replace(config,documents=(schema,))
        amount = next(field for field in schema.fields if field.name == 'Amount')
        numbers = (
            ('n1',Decimal('10.00'),Decimal('-999999999999999999999.12345678901234567')),
            ('n2',Decimal('2.01'),Decimal('0')),
            ('n3',Decimal('2.00'),Decimal('10')),
            ('n4',Decimal('10.00'),Decimal('10')),
        )
        when = datetime(2026,11,9,12,30,5)
        with SQLiteDBContext.create(path,config) as db:
            target = CatalogKey(db.backend.database_id,old.fields[-1].target_catalog_id,UUID(int=0))
            for number,small,large in numbers:
                values = ('payload',small,True,when,target,large)
                part = (TabularSectionRows(lines.identity,(TabularRow(uuid4(),(True,large)),)),)
                draft = DocumentDraft(DocumentKey(db.backend.database_id,schema.identity,uuid4()),number,when,False,values,part)
                with closing(db.backend.begin_document_write(uuid4())) as tx:
                    tx.create(draft); tx.commit()
        with closing(sqlite3.connect(path)) as connection:
            names = {row[1] for row in connection.execute('PRAGMA table_info(document_record)')}
            self.assertFalse(names & {'values_json','sections_json'})
            owner = data_table(schema); child = section_table(schema,lines)
            kinds = tuple(connection.execute(
                f'SELECT typeof("{attribute_column(amount)}"),typeof("{attribute_column(wide)}") FROM "{owner}"'))
            self.assertEqual(kinds,(('integer','blob'),)*4)
            self.assertEqual(tuple(connection.execute(
                f'SELECT typeof("{attribute_column(line_wide)}") FROM "{child}"')),(('blob',),)*4)
        with SQLiteDBContext(path) as db, closing(Interpreter(database_context=db)) as vm:
            result = vm.execute('Q=New Query("SELECT TOP 3 D.Number AS N, D.Wide, D.Amount FROM Document.Orders AS D ORDER BY D.Wide, D.Amount DESC"); Q.Execute()')
            self.assertEqual(result._rows,tuple(numbers[i][:1] + (numbers[i][2],numbers[i][1]) for i in (0,1,3)))
            restored = vm.execute('D=Documents.Orders.FindByNumber("n1").GetObject(); D.Lines.Get(0).Wide')
            self.assertEqual(restored,numbers[0][2])
