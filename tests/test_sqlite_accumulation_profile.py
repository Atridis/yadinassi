"""Fresh accumulation owner and immutable shared-root outcomes, not native parity."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from yadinassi.accumulation_movements import (AccumulationDirection, AccumulationMovementRow,
    AccumulationReplacement)
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_accumulation import import_accumulation_configuration, PROFILE
from yadinassi.document_backend import DocumentKey, DocumentDraft
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_document_posting_state import PostedIntent
from yadinassi.transaction_backend import TransactionRequest
from test_configuration_posting import wrap

ROOT=Path(__file__).resolve().parents[1]

def accumulation_source(module=None):
    root=ROOT/'scripts/accumulation_register_behavior'
    return {'Configuration.xml':wrap('Configuration',100,'<Name>AccumulationHost</Name>',
            '<Document>OwnedAccumulationDoc</Document><AccumulationRegister>OwnedAccumulationRows</AccumulationRegister>'),
        'Documents/OwnedAccumulationDoc.xml':(root/'Document.xml').read_bytes(),
        'AccumulationRegisters/OwnedAccumulationRows.xml':(ROOT/'tests/fixtures/accumulation_register/RuntimeAccumulationRegister.xml').read_bytes(),
        'Documents/OwnedAccumulationDoc/Ext/ObjectModule.bsl':(root/'ObjectModule.bsl').read_bytes() if module is None else module}

class AccumulationProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'accumulation.sqlite'
        self.config=import_accumulation_configuration(accumulation_source(),accumulation_runtime=PROFILE)
    def create(self):
        b=SQLiteCatalogBackend.create_accumulation(self.path,self.config);self.addCleanup(b.close);return b
    def sql(self,statement,args=()):
        with closing(sqlite3.connect(self.path)) as c:
            rows=c.execute(statement,args).fetchall();c.commit();return rows
    def document(self,b,number='1'):
        key=DocumentKey(b.database_id,self.config.documents[0].identity,uuid4())
        return DocumentDraft(key,number,datetime(2024,1,1),False,())
    def movement(self,unit,key,amount=5):
        schema=self.config.registers[0]
        row=AccumulationMovementRow(1,datetime(2024,1,1),True,AccumulationDirection.RECEIPT,
            ('item',Decimal(1)),(Decimal(amount),Decimal('1.125')),('note',))
        return AccumulationReplacement(schema.identity,key,(row,),unit.read_accumulation(schema.identity,key).snapshot)
    def stage(self,b):
        operation=uuid4();unit=b.begin_unit_of_work(operation);draft=self.document(b)
        unit.stage(TransactionRequest('document_create',draft))
        unit.stage(TransactionRequest('document_set_posted',PostedIntent(draft.key,1,True)))
        request=self.movement(unit,draft.key);unit.stage(TransactionRequest('accumulation_replace',request))
        return operation,unit,draft,request
    def test_fresh_create_open_and_distinct_admission(self):
        b=self.create();self.assertEqual((b.format_version,b.storage_version),(14,7))
        self.assertEqual(b.accumulation_configuration,self.config);self.assertIsNone(b.posting_configuration)
        self.assertEqual(b._recorder_schemas,())
        with closing(SQLiteCatalogBackend(self.path)) as other:
            self.assertEqual(other.accumulation_configuration,self.config)
            self.assertEqual(other.database_id,b.database_id)
    def test_no_ir_tables_or_fake_migration_marker(self):
        self.create();names={r[0] for r in self.sql("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn('accumulation_profile',names);self.assertIn('unit_of_work_receipt',names)
        for name in ('posting_profile','recorder_movement','transaction_profile','transaction_migration'):
            self.assertNotIn(name,names)
    def test_source_bytes_are_retained(self):
        self.create();self.assertEqual(dict(self.sql('SELECT path,content FROM configuration_file')),dict(self.config.files))
    def test_existing_destination_is_never_overwritten(self):
        self.path.write_bytes(b'owned')
        with self.assertRaises(BackendError):self.create()
        self.assertEqual(self.path.read_bytes(),b'owned')
    def test_forged_config_is_refused_before_file_allocation(self):
        with self.assertRaises(BackendError):SQLiteCatalogBackend.create_accumulation(self.path,replace(self.config,name='forged'))
        self.assertFalse(self.path.exists())
    def test_ir_profile_constructor_does_not_accept_accumulation(self):
        with self.assertRaises(BackendError):SQLiteCatalogBackend.create_posting(self.path,self.config)
        self.assertFalse(self.path.exists())
    def test_source_tamper_refused_on_open_and_live_begin(self):
        b=self.create();self.sql("UPDATE configuration_file SET sha256=?",('0'*64,))
        with self.assertRaises(BackendError):b.begin_read()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_unknown_schema_object_refused(self):
        self.create();self.sql('CREATE TABLE extra(value)')
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_profile_marker_and_generation_cannot_be_changed(self):
        b=self.create();self.sql("UPDATE accumulation_profile SET profile='other'")
        with self.assertRaises(BackendError):b.begin_read()
        self.sql('UPDATE accumulation_profile SET profile=?',(PROFILE,));self.sql('UPDATE database_info SET generation=2')
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_migration_and_additive_update_are_refused(self):
        self.create()
        from yadinassi.sqlite_migration_plan import prepare
        from yadinassi.sqlite_configuration_update import prepare as update
        with self.assertRaises(BackendError):prepare(self.path,maintenance=True)
        with self.assertRaises(BackendError):update(self.path,self.config,maintenance=True)
    def test_same_root_stages_document_posted_and_accumulation(self):
        b=self.create();operation,unit,draft,request=self.stage(b);requests=unit.requests
        outcomes=unit.commit();self.assertEqual(len(outcomes),3)
        self.assertIs(b.read_document_posted(draft.key),True)
        self.assertEqual(b.read_accumulation(request.register_id,draft.key).rows,request.rows)
        self.assertEqual(b.resolve_unit_of_work(operation,requests),outcomes)
    def test_rollback_removes_all_ports_and_receipts(self):
        b=self.create();operation,unit,draft,request=self.stage(b);unit.rollback()
        self.assertIsNone(b.read_document_posted(draft.key));self.assertEqual(b.read_accumulation(request.register_id,draft.key).rows,())
        for table in ('document_record','document_posting_state','accumulation_movement','unit_of_work_receipt','accumulation_movement_receipt'):
            self.assertEqual(self.sql('SELECT COUNT(*) FROM '+table),[(0,)])
    def test_repeated_replacement_has_distinct_frozen_children(self):
        b=self.create();operation,unit,draft,first=self.stage(b)
        second=self.movement(unit,draft.key,9);unit.stage(TransactionRequest('accumulation_replace',second))
        requests=unit.requests;outcomes=unit.commit()
        self.assertEqual(self.sql('SELECT COUNT(*) FROM accumulation_movement_receipt'),[(2,)])
        self.assertEqual(b.resolve_unit_of_work(operation,requests),outcomes)
        self.assertEqual(b.read_accumulation(first.register_id,draft.key).rows,second.rows)
    def test_historical_root_survives_later_replacement(self):
        b=self.create();operation,unit,draft,first=self.stage(b);requests=unit.requests;outcomes=unit.commit()
        later=b.begin_unit_of_work(uuid4());later.stage(TransactionRequest('accumulation_replace',self.movement(later,draft.key,11)));later.commit()
        self.assertEqual(b.resolve_unit_of_work(operation,requests),outcomes)
    def test_historical_root_does_not_read_current_movement_payload(self):
        b=self.create();operation,unit,draft,first=self.stage(b);requests=unit.requests;outcomes=unit.commit()
        self.sql("UPDATE accumulation_movement SET values_json='[]'")
        self.assertEqual(b.resolve_unit_of_work(operation,requests),outcomes)
        with self.assertRaises(BackendError):b.read_accumulation(first.register_id,draft.key)
    def test_posted_change_requires_same_root_document_mutation(self):
        b=self.create();operation,unit,draft,first=self.stage(b);unit.commit()
        later=b.begin_unit_of_work(uuid4());self.addCleanup(later.close)
        with self.assertRaises(BackendError):later.stage(TransactionRequest('document_set_posted',PostedIntent(draft.key,1,False)))
        self.assertEqual(later.requests,())
    def test_failed_replacement_preserves_earlier_stages(self):
        b=self.create();operation,unit,draft,first=self.stage(b)
        with self.assertRaises(BackendError):unit.stage(TransactionRequest('accumulation_replace',replace(first,expected_snapshot='0'*64)))
        self.assertEqual(len(unit.requests),3);unit.commit()
        self.assertEqual(b.read_accumulation(first.register_id,draft.key).rows,first.rows)
    def test_savepoint_restores_journal_rows_and_child_receipts(self):
        b=self.create();operation,unit,draft,first=self.stage(b)
        with self.assertRaisesRegex(ValueError,'rollback'):
            with unit.savepoint():
                unit.stage(TransactionRequest('accumulation_replace',self.movement(unit,draft.key,99)))
                raise ValueError('rollback')
        self.assertEqual(len(unit.requests),3);unit.commit()
        self.assertEqual(self.sql('SELECT COUNT(*) FROM accumulation_movement_receipt'),[(1,)])
        self.assertEqual(b.read_accumulation(first.register_id,draft.key).rows,first.rows)
    def test_read_only_reopens_but_never_stages(self):
        self.create()
        with closing(SQLiteCatalogBackend(self.path,read_only=True)) as b:
            self.assertEqual(b.accumulation_configuration,self.config)
            with self.assertRaises(BackendError):b.begin_unit_of_work(uuid4())
    def test_ir_read_port_refused_in_new_profile(self):
        b=self.create();draft=self.document(b)
        with self.assertRaises(BackendError):b.read_recorder(self.config.registers[0].identity,draft.key)
    def test_profile14_cannot_be_opened_as_13(self):
        self.create();self.sql('PRAGMA user_version=13')
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_owner_close_never_commits(self):
        b=self.create();operation,unit,draft,request=self.stage(b);unit.close()
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(0,)])
    def test_corrupt_child_receipt_cannot_resolve_root(self):
        b=self.create();operation,unit,draft,request=self.stage(b);requests=unit.requests;unit.commit()
        self.sql("UPDATE accumulation_movement_receipt SET request_hash=?",('0'*64,))
        with self.assertRaises(BackendError):b.resolve_unit_of_work(operation,requests)
    def test_wrong_frozen_request_cannot_resolve_root(self):
        b=self.create();operation,unit,draft,request=self.stage(b);requests=unit.requests;unit.commit()
        wrong=(*requests[:-1],TransactionRequest('accumulation_replace',replace(request,rows=())))
        with self.assertRaises(BackendError):b.resolve_unit_of_work(operation,wrong)

    def test_interpreter_is_activated_but_plain_document_editor_is_not(self):
        from yadinassi import Interpreter
        from yadinassi.database_context import SQLiteDBContext
        from yadinassi.configuration_document import DocumentObjectSession
        context=SQLiteDBContext.create_accumulation(self.path,self.config);self.addCleanup(context.close)
        vm=Interpreter(database_context=context);self.addCleanup(vm.close)
        self.assertIsNotNone(vm.execute('Documents.OwnedAccumulationDoc'))
        with self.assertRaises(BackendError):DocumentObjectSession(context,self.config.documents[0],dict(self.config.files))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM document_record'),[(0,)])
    def test_direct_document_adapter_uses_source_bound_accumulation_runtime(self):
        from yadinassi.database_context import SQLiteDBContext
        from yadinassi.metadata import BSLMetadata
        from yadinassi.catalogs import BSLCatalogs
        from yadinassi.documents import BSLDocuments
        context=SQLiteDBContext.create_accumulation(self.path,self.config);self.addCleanup(context.close)
        metadata=BSLMetadata(context);catalogs=BSLCatalogs(metadata._catalogs,context)
        docs=BSLDocuments(metadata._documents,context,catalogs)
        self.assertEqual(docs.posting_runtime().configuration,self.config)
    def test_two_documents_reversed_name_uuid_order_reopen(self):
        from test_configuration_accumulation import source,document,MODULE
        files=source();files['Configuration.xml']=files['Configuration.xml'].replace(b'<Document>Order</Document>',b'<Document>AFirst</Document><Document>Order</Document>')
        files['Documents/AFirst.xml']=document('AFirst',50,300)
        files['Documents/AFirst/Ext/ObjectModule.bsl']=files[MODULE]
        self.config=import_accumulation_configuration(files,accumulation_runtime=PROFILE)
        self.assertEqual([d.name for d in self.config.documents],['Order','AFirst'])
        b=self.create()
        with closing(SQLiteCatalogBackend(self.path)) as other:self.assertEqual(other.accumulation_configuration,self.config)
        with closing(b.begin_read()) as view:self.assertEqual(view.database_id,b.database_id)
    def test_well_formed_extra_catalog_is_outside_source_grant(self):
        from yadinassi.catalog_backend import CatalogSchema
        from yadinassi import sqlite_catalog as storage
        b=self.create();schema=CatalogSchema(uuid4(),'Unowned',9,32)
        layout=storage.build_layout((schema,))
        with closing(sqlite3.connect(self.path)) as c:
            storage.register_query_collations(c)
            c.execute('INSERT INTO catalog_schema VALUES(?,?,?)',(str(schema.identity),schema.name,storage._json(storage._schema_data(schema))))
            storage.save_layout(c,layout);c.execute(storage.catalog_ddl(schema,layout))
            for ddl in storage.transaction_profile.profile_index_ddls(7,(schema,),layout):
                if 'document_record' not in ddl:c.execute(ddl)
            c.commit()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
        with self.assertRaises(BackendError):b.begin_read()

    def test_noncanonical_recorder_ids_are_not_normalized_away_on_open(self):
        from uuid import UUID
        b=self.create();original=self.document(b)
        fixed=replace(original,key=replace(original.key,record_id=UUID('abcdefab-cdef-4abc-8def-abcdefabcdef')))
        self.document=lambda owner:fixed
        operation,unit,draft,request=self.stage(b);unit.commit()
        key=str(draft.key.record_id);upper=key.upper()
        self.assertNotEqual(key,upper)
        with closing(sqlite3.connect(self.path)) as c:
            for table in ('document_record','document_posting_state','accumulation_partition','accumulation_movement'):
                c.execute('UPDATE '+table+' SET record_id=? WHERE record_id=?',(upper,key))
            c.commit();self.assertIsNone(c.execute('PRAGMA foreign_key_check').fetchone())
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_host_storage_preflight_rejects_total_source_budget_before_file(self):
        from unittest.mock import patch
        from yadinassi.sqlite_accumulation_profile import _preflight_config
        oversized=replace(self.config,files=tuple((str(n),b'x'*(1024*1024)) for n in range(9)))
        with self.assertRaises(BackendError):_preflight_config(oversized)
        self.assertFalse(self.path.exists())
    def test_host_storage_preflight_rejects_aggregate_sections(self):
        from yadinassi.catalog_backend import TabularSectionSchema
        from yadinassi.sqlite_accumulation_profile import _preflight_config
        docs=tuple(replace(self.config.documents[0],identity=uuid4(),name='Doc'+str(n),
            tabular_sections=tuple(TabularSectionSchema(uuid4(),'Section'+str(i)) for i in range(16))) for n in range(33))
        with self.assertRaises(BackendError):_preflight_config(replace(self.config,documents=docs))
        self.assertFalse(self.path.exists())

    def test_live_owner_refuses_changed_application_header(self):
        b=self.create();self.sql('PRAGMA application_id=42')
        with self.assertRaises(BackendError):b.begin_read()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
