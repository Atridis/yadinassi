import datetime
import decimal
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from yadinassi.configuration_xml import ConfigurationImport, ConfigurationFile
from uuid import UUID, uuid4

from yadinassi.catalog_backend import (BackendError,CatalogSchema,FieldSchema,CatalogKey,
                                      CatalogDraft,CatalogSelection)
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


def configuration():
    target, product = uuid4(), uuid4()
    fields = (FieldSchema(uuid4(),'Text','string',(32,)),
              FieldSchema(uuid4(),'Amount','number',(12,2,'Any')),
              FieldSchema(uuid4(),'Active','boolean'),
              FieldSchema(uuid4(),'Date','datetime',('DateTime',)),
              FieldSchema(uuid4(),'Category','catalog_ref',(),target))
    return ConfigurationImport(config_uuid=uuid4(),name='Owned',activation_issues=(),
        catalogs=(CatalogSchema(target,'Categories',8,32),CatalogSchema(product,'Products',8,64,fields)),
        files=(ConfigurationFile(path='Configuration.xml',kind='xml',content=b'<owned/>'),
               ConfigurationFile(path='CommonModules/Owned/Ext/Module.bsl',kind='module',content=b'// owned code')),modules=())


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.path=Path(self.directory.name)/'owned.sqlite'
        self.config=configuration(); self.backend=SQLiteCatalogBackend.create(self.path,self.config)
        self.category,self.product=self.config.catalogs
    def tearDown(self):
        self.backend.close(); self.directory.cleanup()
    def draft(self,*,record=None,code='10',amount=decimal.Decimal('1.25')):
        return CatalogDraft(CatalogKey(self.backend.database_id,self.product.identity,record or uuid4()),code,'Product',False,
            ('text',amount,True,datetime.datetime(1,1,1),CatalogKey(self.backend.database_id,self.category.identity,UUID(int=0))))
    def test_path_leaf_reparse_and_untrusted_ancestor_stay_closed(self):
        from unittest import mock
        from types import SimpleNamespace
        import yadinassi.sqlite_catalog as storage
        original = os.lstat
        def fake(path):
            info = original(path)
            if os.path.abspath(path) == os.path.abspath(self.backend.path):
                return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink,
                    st_size=info.st_size, st_file_attributes=0x400)
            return info
        with mock.patch.object(storage.os, 'lstat', side_effect=fake):
            with self.assertRaisesRegex(BackendError, 'invalid_input'):
                SQLiteCatalogBackend(self.path)
        alias = self.path.parent/'alias'
        try:alias.symlink_to(self.path.parent, target_is_directory=True)
        except (OSError, NotImplementedError):return
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            SQLiteCatalogBackend(alias/self.path.name)
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            SQLiteCatalogBackend.create(alias/'must-not-exist.sqlite', self.config)
        self.assertFalse((self.path.parent/'must-not-exist.sqlite').exists())

    def test_create_edit_rollback_reopen_and_stored_code(self):
        draft=self.draft(); tx=self.backend.begin_write(uuid4()); tx.create(draft); revision=tx.commit()[0]
        self.backend.close(); self.backend=SQLiteCatalogBackend(self.path)
        view=self.backend.begin_read(); card=view.read_catalog(draft.key); view.close()
        self.assertEqual(card.values,draft.values); self.assertEqual(card.revision,revision)
        changed=CatalogDraft(draft.key,draft.code,'Edited',False,draft.values)
        tx=self.backend.begin_write(uuid4());tx.update(changed,revision); tx.rollback()
        view=self.backend.begin_read();self.assertEqual(view.read_catalog(draft.key).description,'Product');view.close()
        tx=self.backend.begin_write(uuid4());tx.update(changed,revision); new=tx.commit()[0]
        self.assertNotEqual(new,revision)
        view=self.backend.begin_read();self.assertEqual(view.read_catalog(draft.key).description,'Edited');view.close()
        self.assertEqual(self.backend.export_configuration()['CommonModules/Owned/Ext/Module.bsl'],b'// owned code')
    def test_stale_duplicate_busy_and_closed_view(self):
        draft=self.draft();tx=self.backend.begin_write(uuid4());tx.create(draft);rev=tx.commit()[0]
        tx=self.backend.begin_write(uuid4());tx.update(draft,rev);tx.commit()
        tx=self.backend.begin_write(uuid4())
        with self.assertRaisesRegex(BackendError,'conflict'):tx.update(draft,rev)
        tx.close()
        tx=self.backend.begin_write(uuid4())
        with self.assertRaisesRegex(BackendError,'duplicate_code'):tx.create(self.draft())
        with self.assertRaisesRegex(BackendError,'busy'):self.backend.begin_read()
        tx.close()
        with self.assertRaisesRegex(BackendError,'closed'):tx.catalogs()
    def test_exact_types_cross_database_and_bounds(self):
        for amount in (1.25,decimal.Decimal('NaN'),decimal.Decimal('1.001')):
            tx=self.backend.begin_write(uuid4())
            with self.assertRaises(BackendError):tx.create(self.draft(amount=amount))
            tx.close()
        view=self.backend.begin_read()
        with self.assertRaises(BackendError):view.read_catalog(CatalogKey(uuid4(),self.product.identity,uuid4()))
        with self.assertRaises(BackendError):view.select_catalog(self.product.identity,CatalogSelection(True))
        view.close()
    def test_read_only_view_and_foreign_reference(self):
        view=self.backend.begin_read()
        with self.assertRaisesRegex(BackendError,'unsupported'):view.create(self.draft())
        view.close()
        draft=self.draft(); invalid=CatalogDraft(draft.key,draft.code,draft.description,False,draft.values[:-1]+(CatalogKey(self.backend.database_id,self.category.identity,uuid4()),))
        tx=self.backend.begin_write(uuid4())
        with self.assertRaisesRegex(BackendError,'not_found'):tx.create(invalid)
        tx.rollback()
    def test_overflow_not_silent_truncation_and_single_writer(self):
        tx=self.backend.begin_write(uuid4());tx.create(self.draft(code='10'));tx.create(self.draft(code='20'));tx.commit()
        view=self.backend.begin_read()
        with self.assertRaisesRegex(BackendError,'unsupported'):view.select_catalog(self.product.identity,CatalogSelection(1))
        view.close()
        other=SQLiteCatalogBackend(self.path)
        tx=self.backend.begin_write(uuid4())
        try:
            with self.assertRaisesRegex(BackendError,'busy'):other.begin_write(uuid4())
        finally:tx.close();other.close()
    def test_failed_create_never_overwrites_existing_file(self):
        before=self.path.read_bytes()
        with self.assertRaises(BackendError):SQLiteCatalogBackend.create(self.path,self.config)
        self.assertEqual(before,self.path.read_bytes())
    def test_readonly_open_never_writes_or_creates(self):
        before=self.path.read_bytes()
        readonly=SQLiteCatalogBackend(self.path,read_only=True)
        self.assertFalse(readonly.capabilities().catalog_update)
        with self.assertRaisesRegex(BackendError,'unsupported'):readonly.begin_write(uuid4())
        view=readonly.begin_read();self.assertEqual(len(view.catalogs()),2);view.close();readonly.close()
        self.assertEqual(before,self.path.read_bytes())
        absent=Path(self.directory.name)/'absent.sqlite'
        with self.assertRaises(BackendError):SQLiteCatalogBackend(absent,read_only=True)
        self.assertFalse(absent.exists())
    def test_commit_resolution_binds_exact_intent(self):
        operation=uuid4();draft=self.draft();tx=self.backend.begin_write(operation);tx.create(draft);revision=tx.commit()[0]
        self.assertEqual(self.backend.resolve_write(operation,draft),revision)
        changed=CatalogDraft(draft.key,draft.code,'Other',False,draft.values)
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.resolve_write(operation,changed)
        self.assertIsNone(self.backend.resolve_write(uuid4(),draft))
    def test_hostile_revision_and_persisted_corruption_are_closed(self):
        from dataclasses import replace
        draft=self.draft();tx=self.backend.begin_write(uuid4());tx.create(draft);rev=tx.commit()[0]
        for token in ('9'*5000,'01','0','-1','9223372036854775808'):
            tx=self.backend.begin_write(uuid4())
            with self.assertRaises(BackendError) as error:tx.update(draft,replace(rev,token=token))
            self.assertEqual(error.exception.code,'conflict');tx.close()
        connection=sqlite3.connect(self.path)
        connection.execute('UPDATE catalog_schema SET definition=? WHERE identity=?',('{bad',str(self.product.identity)));connection.commit();connection.close()
        with self.assertRaises(BackendError) as error:self.backend.begin_read()
        self.assertEqual(error.exception.code,'schema_changed')
    def test_exact_transaction_change_limit_can_commit(self):
        from unittest.mock import patch
        with patch('yadinassi.sqlite_catalog._MAX_ROWS',2):
            tx=self.backend.begin_write(uuid4());tx.create(self.draft(code='10'));tx.create(self.draft(code='20'))
            with self.assertRaisesRegex(BackendError,'unsupported'):tx.create(self.draft(code='30'))
            self.assertEqual(len(tx.commit()),2)
    def test_configuration_file_bounds_refuse_before_creation(self):
        from dataclasses import replace
        for file in (ConfigurationFile('a.xml',b'x'*(1024*1024+1),'xml'),ConfigurationFile('a'*257,b'x','xml')):
            path=Path(self.directory.name)/'rejected.sqlite'
            with self.assertRaises(BackendError):SQLiteCatalogBackend.create(path,replace(self.config,files=(file,)))
            self.assertFalse(path.exists())
    def test_inactive_archive_persists_code_but_refuses_data_operations(self):
        from dataclasses import replace
        code=b'Procedure BeforeWrite(Cancel)\nCancel=True;\nEndProcedure'
        config=replace(self.config,files=self.config.files+(ConfigurationFile('Ext/Module.bsl',code,'module'),),activation_issues=('module execution unsupported',))
        path=Path(self.directory.name)/'inactive.sqlite'
        with self.assertRaisesRegex(BackendError,'unsupported'):SQLiteCatalogBackend.create(path,config)
        self.assertFalse(path.exists())
        archive=SQLiteCatalogBackend.create(path,config,activate=False)
        self.assertFalse(archive.capabilities().catalog_read)
        with self.assertRaisesRegex(BackendError,'unsupported'):archive.begin_read()
        with self.assertRaisesRegex(BackendError,'unsupported'):archive.begin_write(uuid4())
        archive.close();archive=SQLiteCatalogBackend(path,read_only=True)
        self.assertEqual(archive.export_configuration()['Ext/Module.bsl'],code)
        self.assertEqual(archive.activation_issues,('module execution unsupported',));archive.close()
    def test_activation_issues_require_bounded_list(self):
        for invalid in ('{}','""','"issue"','[1]'):
            connection=sqlite3.connect(self.path);connection.execute('UPDATE database_info SET activation_issues=?',(invalid,));connection.commit();connection.close()
            with self.assertRaises(BackendError) as error:SQLiteCatalogBackend(self.path)
            self.assertEqual(error.exception.code,'integrity')
    def test_sqlite_integrity_and_foreign_keys_enabled(self):
        connection=sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone(),('ok',))
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(),[])
        finally:connection.close()

if __name__=='__main__':unittest.main()

class RecoveryTests(BackendTests):
    def test_crash_before_commit_rolls_back_and_after_commit_is_resolvable(self):
        import subprocess
        import sys
        record,operation=uuid4(),uuid4()
        code = '''import os,sys
from uuid import UUID
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.catalog_backend import CatalogKey,CatalogDraft
b=SQLiteCatalogBackend(sys.argv[1]); t=b.begin_write(UUID(sys.argv[4]))
t.create(CatalogDraft(CatalogKey(b.database_id,UUID(sys.argv[2]),UUID(sys.argv[3])),"20","Crash",False,()))
if sys.argv[5]=="commit": t.commit()
os._exit(17)
'''
        args=[sys.executable,'-c',code,str(self.path),str(self.category.identity),str(record),str(operation)]
        self.assertEqual(subprocess.run(args+['abort'],check=False).returncode,17)
        view=self.backend.begin_read();self.assertIsNone(view.read_catalog(CatalogKey(self.backend.database_id,self.category.identity,record)));view.close()
        self.assertIsNone(self.backend.committed_operation(operation))
        self.assertEqual(subprocess.run(args+['commit'],check=False).returncode,17)
        receipt=self.backend.committed_operation(operation)
        self.assertEqual(len(receipt[1]),1)
        with self.assertRaisesRegex(BackendError,'conflict'):self.backend.begin_write(operation)
        view=self.backend.begin_read();self.assertEqual(view.read_catalog(CatalogKey(self.backend.database_id,self.category.identity,record)).description,'Crash');view.close()
