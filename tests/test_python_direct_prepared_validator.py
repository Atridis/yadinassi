"""Prepared validator is reusable code, never receiver/transaction authority."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch
import test_python_direct_catalog_preparation as fixture
SOURCE=fixture.SOURCE
from yadinassi.db.catalog.catalog_object_preparation import CatalogWriteRefused
from yadinassi.execution.direct.python_direct_catalog_preparation import prepared_validator
from yadinassi.execution.codegen.native_targets import target_context,LINUX_8_3_27_1508
from yadinassi.db.catalog.catalog_backend import BackendError

class PreparedValidatorTests(TestCase):
    def setUp(self):
        self.f=fixture.DirectCatalogPreparationTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.manager=self.f.card._manager
    def test_single_compile_before_transaction_and_fresh_receivers(self):
        import yadinassi.execution.direct.python_direct_catalog_preparation as direct
        original=direct.compile_owned;seen=[]
        def compile(*args,**kwargs):
            self.assertIsNone(self.f.db.backend._active);seen.append(1)
            return original(*args,**kwargs)
        with patch.object(direct,'compile_owned',compile):
            self.f.card.write();first=self.manager._direct_validator_plan
            self.f.card.set_member('Наименование','  Other  ');self.f.card.write()
            second=self.manager.create_item();second.set_member('Наименование','  Second  ')
            second.set_member('ВидНоменклатуры',self.f.kind.get_member('Ссылка'))
            second.get_member('Склады').add().set_member('Склад',self.f.warehouse.get_member('Ссылка'));second.write()
        self.assertEqual(len(seen),1);self.assertIs(self.manager._direct_validator_plan,first)
        self.assertEqual(second.get_member('Наименование'),'Second')
        self.assertEqual(self.f.card.get_member('Наименование'),'Other')
        self.assertIsNone(first._plan.last_state)
    def test_changed_options_recompile_before_opening_writer(self):
        import yadinassi.execution.direct.python_direct_catalog_preparation as direct
        self.f.card.write()
        first = self.manager._direct_validator_plan
        compile_owned = direct.compile_owned
        calls = []
        def compile(*args,**kwargs):
            self.assertIsNone(self.f.db.backend._active)
            calls.append(1)
            return compile_owned(*args,**kwargs)
        with patch.object(direct,'compile_owned',compile), target_context(LINUX_8_3_27_1508):
            self.f.card.write()
            self.assertIsNot(self.manager._direct_validator_plan,first)
        self.assertEqual(calls,[1])

    def test_compile_candidate_precedes_but_never_replaces_locked_source_proof(self):
        import sqlite3
        from contextlib import closing
        import yadinassi.execution.direct.python_direct_catalog_preparation as direct

        backend = self.f.db.backend
        compile_owned = direct.compile_owned
        calls = []
        def compile(*args,**kwargs):
            self.assertIsNone(backend._active)
            calls.append(1)
            result = compile_owned(*args,**kwargs)
            # Change the stored grant after compiling and before BEGIN.
            with closing(sqlite3.connect(self.f.db.path)) as conn,conn:
                conn.execute('UPDATE configuration_file SET sha256=? WHERE path=?',
                             ('0'*64,'Configuration.xml'))
            return result
        with patch.object(direct,'compile_owned',compile), \
             patch('yadinassi.db.catalog.catalog_object_preparation._prepare_catalog_object',
                   side_effect=AssertionError('unadmitted handler ran')):
            with self.assertRaises(BackendError):
                self.f.card.write()
        self.assertEqual(calls,[1])
        self.assertTrue(self.f.card.is_new())
        self.assertIsNone(backend._active)

    def test_source_full_schema_and_target_invalidate(self):
        first=prepared_validator(self.manager,SOURCE)
        changed=SOURCE+'\n// independently selected text\n'
        second=prepared_validator(self.manager,changed);self.assertIsNot(first,second)
        with self.assertRaisesRegex(ValueError,'changed'):prepared_validator(self.manager,changed,prepared=first)
        old=self.manager._schema
        try:
            self.manager._schema=replace(old,description_length=old.description_length+1)
            third=prepared_validator(self.manager,changed);self.assertIsNot(second,third)
            with self.assertRaisesRegex(ValueError,'changed'):prepared_validator(self.manager,changed,prepared=second)
        finally:self.manager._schema=old
        with target_context(LINUX_8_3_27_1508):
            fourth=prepared_validator(self.manager,changed);self.assertIsNot(second,fourth)
        import yadinassi.execution.direct.python_direct_catalog_preparation as direct
    def test_cached_plan_keeps_current_read_view_and_fresh_messages(self):
        self.f.card.write()
        self.f.warehouse.set_member('ПометкаУдаления',True);self.f.warehouse.write()
        for _ in range(2):
            with self.assertRaises(CatalogWriteRefused) as refused:self.f.card.write()
            self.assertEqual(len(refused.exception.messages),1)
        self.f.warehouse.set_member('ПометкаУдаления',False);self.f.warehouse.write()
        self.f.card.write()
    def test_lost_commit_acknowledgement_never_prepares_or_replays(self):
        from test_catalog_commit_cleanup_recovery import FaultConnection
        original=self.f.db.backend.begin_write
        def begin(operation):
            view=original(operation);view._connection=FaultConnection(view._connection,commit_fault='after');return view
        with patch.object(self.f.db.backend,'begin_write',begin):
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):
                self.f.card.write()
        with patch('yadinassi.execution.direct.python_direct_catalog_preparation.prepared_validator',
                   side_effect=AssertionError('compile after uncertain outcome')), \
             patch('yadinassi.db.catalog.catalog_object_preparation._prepare_catalog_object',
                   side_effect=AssertionError('handler replay')):
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):
                self.f.card.write()
            ref = self.manager._ref(self.f.card._key.record_id)
            persisted = ref.get_object(ref)
        self.assertTrue(self.f.card.is_new())
        self.assertFalse(persisted.is_new())
        self.assertEqual(persisted._revision.token,'1')
        self.assertEqual(persisted.get_member('Наименование'),'Кабель')
