"""Ordinary BSL uses a touched-domain proof, raw storage remains strict."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_sqlite_register_integration import configuration
from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_register_layout import register_table


class RuntimeRegisterAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = configuration()
        self.db, self.vm = self.open(self.cfg,'audit.sqlite')
        self.backend = self.db.backend
        self.schema = self.cfg.information_registers[0]
        self.vm.execute('R=InformationRegisters.Orders.CreateRecordManager();'
                        'R.Item="A";R.Amount=1;R.Write();')

    def open(self,cfg,name):
        db = SQLiteDBContext.create(Path(self.tmp.name)/name,cfg)
        self.addCleanup(db.close)
        vm = Interpreter(database_context=db)
        self.addCleanup(vm.close)
        return db,vm

    @staticmethod
    def sql(db,text,args=()):
        with closing(sqlite3.connect(db.path)) as peer, peer:
            return peer.execute(text,args).fetchall()

    def test_record_set_and_select_ignore_unrelated_metadata_but_raw_does_not(self):
        self.sql(self.db,'UPDATE document_schema SET definition=?',('[]',))
        with patch.object(self.backend,'_validate_transaction_admission',
                          side_effect=AssertionError('unrelated admission')):
            self.vm.execute('''R.Read();R.Amount=2;R.Write();
S=InformationRegisters.Orders.CreateRecordSet();S.Filter.Item.Set("A");
S.Read();S[0].Amount=3;S.Write();
T=InformationRegisters.Orders.Select();Found=T.Next();Result=T.Amount;''')
        self.assertTrue(self.vm.execute('Found'))
        self.assertEqual(self.vm.execute('Result'),3)
        with self.assertRaises(BackendError): self.backend.begin_register_read()
        self.assertIsNone(self.backend._active)

    def test_touched_schema_sequence_and_generation_all_fail_without_a_write(self):
        table = register_table(self.schema)
        for column,changed,restore in (
                ('information_register_schema SET definition','[]',
                 self.sql(self.db,'SELECT definition FROM information_register_schema')[0][0]),
                ('information_register_sequence SET next_value','not a sequence',
                 self.sql(self.db,'SELECT next_value FROM information_register_sequence')[0][0]),
                ('database_info SET generation',99,1)):
            with self.subTest(column=column):
                self.vm.execute('R.Amount=5;')
                self.sql(self.db,'UPDATE '+column+'=?',(changed,))
                with self.assertRaises(BSLRuntimeError): self.vm.execute('R.Write();')
                with self.assertRaises(BSLRuntimeError): self.vm.execute('R.Read();')
                self.assertEqual(self.sql(self.db,'SELECT revision FROM '+table),[(1,)])
                self.assertIsNone(self.backend._active)
                self.sql(self.db,'UPDATE '+column+'=?',(restore,))
        self.vm.execute('R.Write();')
        self.assertEqual(self.sql(self.db,'SELECT revision FROM '+table),[(2,)])

    def test_public_read_override_still_owns_the_read(self):
        with patch.object(self.backend, 'begin_read',
                          side_effect=BackendError('unsupported')) as opened:
            with self.assertRaisesRegex(BSLRuntimeError,'unsupported'):
                self.vm.execute('R.Read();')
            opened.assert_called_once()
        self.assertIsNone(self.backend._active)

    def test_opened_identity_accepts_preexisting_empty_issue_json_spelling(self):
        self.sql(self.db,'UPDATE database_info SET activation_issues=?',('[ ]',))
        with SQLiteDBContext(self.db.path) as reopened, closing(Interpreter(database_context=reopened)) as vm:
            vm.execute('R=InformationRegisters.Orders.CreateRecordManager();R.Item="A";R.Read();')
            self.assertEqual(vm.execute('R.Amount'),1)

    def test_scoped_ddl_mismatch_with_same_schema_cookie(self):
        table = register_table(self.schema)
        cookie = self.sql(self.db,'PRAGMA schema_version')[0][0]
        with closing(sqlite3.connect(self.db.path)) as peer, peer:
            peer.execute(f'CREATE TRIGGER diagnostic_scope BEFORE INSERT ON {table.upper()} BEGIN SELECT 1; END')
            peer.execute('PRAGMA schema_version='+str(cookie))
        self.assertEqual(self.sql(self.db,'PRAGMA schema_version'),[(cookie,)])
        with self.assertRaises(BSLRuntimeError): self.vm.execute('R.Read();')
        with self.assertRaises(BSLRuntimeError): self.vm.execute('R.Amount=4;R.Write();')
        self.assertEqual(self.sql(self.db,'SELECT revision FROM '+table),[(1,)])
        self.assertIsNone(self.backend._active)

    def test_schema_definition_is_not_trusted_through_mutable_host_alias(self):
        manager = self.vm._information_registers.get_index('Orders')
        field = manager._schema.resources[0]
        object.__setattr__(field,'qualifiers',(12,3,'Any'))
        try:
            with self.assertRaises(BSLRuntimeError): self.vm.execute('R.Read();')
            self.assertIsNone(self.backend._active)
        finally:
            object.__setattr__(field,'qualifiers',(12,2,'Any'))
        self.assertEqual(self.vm.execute('R.Read();R.Amount'),1)

    def test_related_catalog_manifest_and_foreign_key_remain_required(self):
        cfg = configuration()
        catalog = cfg.catalogs[0]
        register, = cfg.information_registers
        key = replace(register.dimensions[0],kind='catalog_ref',qualifiers=(),
                      target_catalog_id=catalog.identity)
        cfg = replace(cfg,information_registers=(replace(register,dimensions=(key,)),))
        db,vm = self.open(cfg,'related.sqlite')
        vm.execute('C=Catalogs.Orders.CreateItem();C.Description="real";C.Write();'
                   'R=InformationRegisters.Orders.CreateRecordManager(); R.Item=C.Ref;R.Amount=2;R.Write();')
        vm.execute(f'Q=InformationRegisters.Orders.CreateRecordManager();'
                   f'Q.Item=Catalogs.Orders.GetRef(New UUID("{uuid4()}"));Q.Amount=7;')
        with self.assertRaises(BSLRuntimeError): vm.execute('Q.Write();')
        old = self.sql(db,'SELECT definition FROM catalog_schema')[0][0]
        self.sql(db,'UPDATE catalog_schema SET definition=?',('[]',))
        with self.assertRaises(BSLRuntimeError): vm.execute('R.Read();')
        self.assertIsNone(db.backend._active)
        self.sql(db,'UPDATE catalog_schema SET definition=?',(old,))
        self.assertEqual(vm.execute('R.Read();R.Amount'),2)
