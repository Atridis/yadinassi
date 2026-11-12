"""Stock imports are reusable; live storage, source and transaction authority are not."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_accumulation_movements import AccumulationMovementPort

ROOT = Path(__file__).resolve().parents[1]


class StockAdmissionChecks:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'stock.sqlite'
        self.files, config = self.make_source()
        self.backend = self.create(self.path, config)
        self.addCleanup(self.backend.close)
        self.config = self.backend.accumulation_configuration
        self.profile_module = importlib.import_module(self.module)
        self.importer = getattr(self.profile_module, self.import_name)

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(statement, args).fetchall()
            db.commit()
            return rows

    def read(self):
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(view.database_id, self.backend.database_id)

    def assert_refused_then_repaired(self, change, repair):
        entry = self.backend._prepared_source._entry
        change()
        with self.assertRaises(BackendError): self.read()
        self.assertIs(self.backend._prepared_source._entry, entry)
        self.assertIsNone(self.backend._active)
        repair()
        with patch(self.module + '.' + self.import_name) as importer:
            self.read()
            importer.assert_not_called()

    def admit(self, connection, **options):
        schemas = (self.backend._schemas, self.backend._document_schemas) if self.version == 15 else (self.backend._document_schemas,)
        return self.profile_module.admit(connection, self.backend.database_id, *schemas, **options)

    def test_twenty_three_snapshots_reuse_exact_import_without_compilation(self):
        with patch(self.module + '.' + self.import_name) as importer, \
                patch('yadinassi.document_posting_program.compile_handlers') as compiler:
            for _ in range(23): self.read()
            importer.assert_not_called(); compiler.assert_not_called()
        self.assertIs(self.backend._prepared_source._entry.value, self.config)

    def test_each_backend_is_cold_and_owns_one_positive_entry(self):
        with patch(self.module + '.' + self.import_name, wraps=self.importer) as importer:
            with closing(SQLiteCatalogBackend(self.path)) as other:
                self.assertEqual(importer.call_count, 1)
                self.assertIsNot(other._prepared_source, self.backend._prepared_source)
                for _ in range(3):
                    with closing(other.begin_read()): pass
                self.assertEqual(importer.call_count, 1)

    def test_readonly_backend_retains_source_without_write_authority(self):
        with closing(SQLiteCatalogBackend(self.path, read_only=True)) as other:
            with patch(self.module + '.' + self.import_name) as importer:
                with closing(other.begin_read()): pass
                importer.assert_not_called()
            with self.assertRaises(BackendError): other.begin_unit_of_work(uuid4())

    def test_close_clears_positive_entry_and_cannot_reopen_owner(self):
        self.assertIsNotNone(self.backend._prepared_source._entry)
        self.backend.close()
        self.assertIsNone(self.backend._prepared_source._entry)
        with self.assertRaises(BackendError): self.read()

    def test_clear_requires_one_fresh_positive_import(self):
        self.backend._prepared_source.clear()
        with patch(self.module + '.' + self.import_name, wraps=self.importer) as importer:
            self.read(); self.read()
            self.assertEqual(importer.call_count, 1)

    def test_actual_source_bytes_are_rehashed_and_repair_recovers(self):
        raw = self.files['Configuration.xml']
        self.assert_refused_then_repaired(
            lambda: self.sql("UPDATE configuration_file SET content=x'00' WHERE path='Configuration.xml'"),
            lambda: self.sql("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'", (raw,)))

    def test_stored_digest_is_not_reuse_authority(self):
        digest = sha256(self.files['Configuration.xml']).hexdigest()
        self.assert_refused_then_repaired(
            lambda: self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'", ('0' * 64,)),
            lambda: self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'", (digest,)))

    def test_rehashed_changed_source_same_generation_misses_and_is_refused(self):
        path = next(p for p in self.files if p.endswith('.bsl'))
        raw = self.files[path]; changed = raw + b'\n// changed source\n'
        self.assert_refused_then_repaired(
            lambda: self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (changed, sha256(changed).hexdigest(), path)),
            lambda: self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (raw, sha256(raw).hexdigest(), path)))

    def test_source_kind_remains_checked(self):
        self.assert_refused_then_repaired(
            lambda: self.sql("UPDATE configuration_file SET kind='module' WHERE path='Configuration.xml'"),
            lambda: self.sql("UPDATE configuration_file SET kind='xml' WHERE path='Configuration.xml'"))

    def test_extra_source_file_cannot_use_prior_entry(self):
        self.assert_refused_then_repaired(
            lambda: self.sql('INSERT INTO configuration_file VALUES(?,?,?,?)', ('Extra.xml', 'xml', b'<extra/>', sha256(b'<extra/>').hexdigest())),
            lambda: self.sql("DELETE FROM configuration_file WHERE path='Extra.xml'"))

    def test_missing_source_file_cannot_use_prior_entry(self):
        path = next(p for p in self.files if p.endswith('.bsl')); raw = self.files[path]
        self.assert_refused_then_repaired(
            lambda: self.sql('DELETE FROM configuration_file WHERE path=?', (path,)),
            lambda: self.sql('INSERT INTO configuration_file VALUES(?,?,?,?)', (path, 'module', raw, sha256(raw).hexdigest())))

    def test_marker_profile_is_exact_not_a_cross_profile_cache(self):
        self.assert_refused_then_repaired(
            lambda: self.sql('UPDATE ' + self.marker + " SET profile='accumulation-reference-forms-v1'"),
            lambda: self.sql('UPDATE ' + self.marker + ' SET profile=?', (self.config.profile,)))

    def test_marker_source_digest_is_still_compared(self):
        self.assert_refused_then_repaired(
            lambda: self.sql('UPDATE ' + self.marker + ' SET source_digest=?', ('0' * 64,)),
            lambda: self.sql('UPDATE ' + self.marker + ' SET source_digest=?', (self.config.source_digest,)))

    def test_database_identity_is_live_before_publishing_admission(self):
        self.assert_refused_then_repaired(
            lambda: self.sql('UPDATE database_info SET database_uuid=?', (str(uuid4()),)),
            lambda: self.sql('UPDATE database_info SET database_uuid=?', (str(self.backend.database_id),)))

    def test_configuration_identity_remains_live(self):
        self.assert_refused_then_repaired(
            lambda: self.sql('UPDATE database_info SET configuration_uuid=?', (str(uuid4()),)),
            lambda: self.sql('UPDATE database_info SET configuration_uuid=?', (str(self.config.identity),)))

    def test_generation_is_not_hidden_by_source_cache(self):
        self.assert_refused_then_repaired(
            lambda: self.sql('UPDATE database_info SET generation=2'),
            lambda: self.sql('UPDATE database_info SET generation=1'))

    def test_activation_issues_remain_exact(self):
        self.assert_refused_then_repaired(
            lambda: self.sql("UPDATE database_info SET activation_issues='[\"unowned\"]'"),
            lambda: self.sql("UPDATE database_info SET activation_issues='[]'"))

    def test_application_id_is_still_checked(self):
        original = self.sql('PRAGMA application_id')[0][0]
        self.assert_refused_then_repaired(lambda: self.sql('PRAGMA application_id=1'),
                                         lambda: self.sql('PRAGMA application_id=' + str(original)))

    def test_user_version_cannot_promote_another_profile(self):
        self.assert_refused_then_repaired(lambda: self.sql('PRAGMA user_version=13'),
                                         lambda: self.sql('PRAGMA user_version=' + str(self.version)))

    def test_sql_schema_change_cannot_hit_positive_entry(self):
        self.sql('CREATE TABLE unowned(value)')
        with self.assertRaises(BackendError): self.read()

    def test_document_schema_equality_stays_live(self):
        identity, name = self.sql('SELECT identity,name FROM document_schema LIMIT 1')[0]
        self.assert_refused_then_repaired(
            lambda: self.sql("UPDATE document_schema SET name='Changed' WHERE identity=?", (identity,)),
            lambda: self.sql('UPDATE document_schema SET name=? WHERE identity=?', (name, identity)))

    def test_register_fields_same_source_are_checked_on_hit_and_after_repair(self):
        identity, raw = self.sql('SELECT register_id,definition FROM accumulation_register_schema LIMIT 1')[0]
        data = json.loads(raw); data[6][0][1] = 'ChangedResource'
        changed = json.dumps(data, separators=(',', ':'))
        self.assert_refused_then_repaired(
            lambda: self.sql('UPDATE accumulation_register_schema SET definition=? WHERE register_id=?', (changed, identity)),
            lambda: self.sql('UPDATE accumulation_register_schema SET definition=? WHERE register_id=?', (raw, identity)))

    def test_recorder_membership_same_source_is_checked_on_hit_and_after_repair(self):
        register, document = self.sql('SELECT register_id,document_id FROM accumulation_register_document LIMIT 1')[0]
        self.assert_refused_then_repaired(
            lambda: self.sql('DELETE FROM accumulation_register_document WHERE register_id=? AND document_id=?', (register, document)),
            lambda: self.sql('INSERT INTO accumulation_register_document VALUES(?,?)', (register, document)))

    def test_port_schema_validation_is_not_cached(self):
        with patch.object(AccumulationMovementPort, '_require', side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError): self.read()
        self.read()

    def test_failed_import_does_not_publish_and_repair_can_admit(self):
        self.backend._prepared_source.clear()
        with patch(self.module + '.' + self.import_name, side_effect=ValueError('refused')):
            with self.assertRaises(BackendError): self.read()
        self.assertIsNone(self.backend._prepared_source._entry)
        self.read(); self.assertIsNotNone(self.backend._prepared_source._entry)

    def test_interrupted_import_does_not_publish(self):
        self.backend._prepared_source.clear()
        with patch(self.module + '.' + self.import_name, side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.read()
        self.assertIsNone(self.backend._prepared_source._entry)
        self.read()

    def test_failed_register_admission_does_not_publish_parsed_candidate(self):
        self.backend._prepared_source.clear()
        with patch.object(AccumulationMovementPort, '_require', side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError): self.read()
        self.assertIsNone(self.backend._prepared_source._entry)
        self.read()

    def test_wrong_cached_type_never_becomes_a_source_grant(self):
        cache = self.backend._prepared_source
        original = cache._entry
        cache._entry = replace(original, value=object())
        with self.assertRaises(BackendError): self.read()
        cache._entry = original
        self.read()

    def test_explicit_row_validation_still_runs_on_cache_hit(self):
        with closing(self.backend.begin_read()) as view:
            with patch('yadinassi.sqlite_accumulation_movements.validate_database_budget', side_effect=BackendError('integrity')):
                with self.assertRaises(BackendError):
                    self.admit(view._connection, validate_rows=True, _prepared=self.backend._prepared_source)

    def test_uncached_standalone_admission_preserves_original_contract(self):
        with closing(self.backend.begin_read()) as view:
            with patch(self.module + '.' + self.import_name, wraps=self.importer) as importer:
                self.assertEqual(self.admit(view._connection), self.config)
                self.assertEqual(self.admit(view._connection), self.config)
                self.assertEqual(importer.call_count, 2)

    def test_file_replacement_is_refused_even_for_identical_configuration(self):
        other_path = self.path.with_name('replacement.sqlite')
        with closing(self.create(other_path, self.config)): pass
        self.backend._close_idle_read_handle()
        os.replace(other_path, self.path)
        with self.assertRaises(BackendError): self.read()

    def test_positive_entry_does_not_keep_a_read_lease_or_writer_lock(self):
        view = self.backend.begin_read(); view.close()
        self.assertIsNone(self.backend._active)
        with self.assertRaises(BackendError): view.catalogs()
        self.sql('UPDATE database_info SET name=name')
        self.read()


class PreparedScalarStockTests(StockAdmissionChecks, unittest.TestCase):
    version = 14
    marker = 'accumulation_profile'
    module = 'yadinassi.sqlite_accumulation_profile'
    import_name = 'import_accumulation_configuration'
    create = staticmethod(SQLiteCatalogBackend.create_accumulation)

    @staticmethod
    def make_source():
        from test_configuration_accumulation import source, import_source
        files = source()
        return files, import_source(files)


class PreparedReferenceStockTests(StockAdmissionChecks, unittest.TestCase):
    version = 15
    marker = 'inventory_profile'
    module = 'yadinassi.sqlite_inventory_profile'
    import_name = 'import_inventory_configuration'
    create = staticmethod(SQLiteCatalogBackend.create_inventory)

    @staticmethod
    def make_source():
        from test_inventory_reference_profile import source, imported
        files = source()
        return files, imported(files)

    def test_reference_catalog_metadata_is_still_live(self):
        identity, raw = self.sql('SELECT identity,definition FROM catalog_schema LIMIT 1')[0]
        self.assert_refused_then_repaired(
            lambda: self.sql("UPDATE catalog_schema SET definition='[]' WHERE identity=?", (identity,)),
            lambda: self.sql('UPDATE catalog_schema SET definition=? WHERE identity=?', (raw, identity)))


class PreparedStockTransactionTests(unittest.TestCase):
    def setUp(self):
        from test_accumulation_posting_runtime import AccumulationPostingRuntimeTests
        AccumulationPostingRuntimeTests.setUp(self)

    def make(self, *args, **kwargs):
        from test_accumulation_posting_runtime import AccumulationPostingRuntimeTests
        return AccumulationPostingRuntimeTests.make(self, *args, **kwargs)

    def new(self, *args, **kwargs):
        from test_accumulation_posting_runtime import AccumulationPostingRuntimeTests
        return AccumulationPostingRuntimeTests.new(self, *args, **kwargs)

    def post(self): self.vm.execute('O.Write(DocumentWriteMode.Posting);')

    def rows(self, obj):
        return self.backend.read_accumulation(self.config.registers[0].identity, obj._key).rows

    def test_staged_balance_uses_owned_transaction_and_rollback_not_cached_rows(self):
        from decimal import Decimal
        self.new()
        with patch('yadinassi.sqlite_accumulation_profile.import_accumulation_configuration') as importer:
            self.vm.execute('Q=New Query("SELECT AmountBalance AS N FROM AccumulationRegister.Rows.Balance(&At)");'
                'Q.SetParameter("At",Date(2024,1,2));BeginTransaction();O.Write(DocumentWriteMode.Posting);'
                'S=Q.Execute().Select();S.Next();Inside=S.N;RollbackTransaction();'
                'S=Q.Execute().Select();HasAfter=S.Next();')
            self.assertEqual(self.vm.execute('Inside'), Decimal('7.25'))
            self.assertFalse(self.vm.execute('HasAfter'))
            importer.assert_not_called()

    def test_committed_stock_and_external_payload_corruption_remain_live(self):
        obj = self.new(); self.post(); self.assertEqual(len(self.rows(obj)), 1)
        with closing(sqlite3.connect(self.path)) as db:
            original = db.execute('SELECT values_json FROM accumulation_movement').fetchone()[0]
            db.execute("UPDATE accumulation_movement SET values_json='[]'"); db.commit()
        with patch('yadinassi.sqlite_accumulation_profile.import_accumulation_configuration') as importer:
            with self.assertRaises(BackendError): self.rows(obj)
            with closing(sqlite3.connect(self.path)) as db:
                db.execute('UPDATE accumulation_movement SET values_json=?', (original,)); db.commit()
            self.assertEqual(len(self.rows(obj)), 1)
            importer.assert_not_called()

    def test_new_read_lease_cannot_gain_commit_rollback_authority(self):
        from yadinassi.database_transactions import begin, current, execution
        with patch('yadinassi.sqlite_accumulation_profile.import_accumulation_configuration') as importer:
            with execution(self.backend):
                begin(self.backend)
                owner = current(self.backend)
                lease = self.backend.begin_read()
                with self.assertRaises(BackendError): lease.commit()
                lease.rollback()  # Retires only this borrowed lease.
                self.assertEqual(owner.unit.state, 'open')
                self.assertTrue(owner.unit._view._connection.in_transaction)
                self.assertIs(current(self.backend), owner)
                owner.rollback()
            importer.assert_not_called()

    def test_owner_rollback_never_replays_or_commits(self):
        self.new()
        # One public BSL activation owns both staging and rollback. Starting a
        # separate vm.execute inside a host transaction is correctly refused.
        self.vm.execute('BeginTransaction();O.Write(DocumentWriteMode.Posting);RollbackTransaction();')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM document_record').fetchone(), (0,))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM unit_of_work_receipt').fetchone(), (0,))


class PreparedInventoryTransactionTests(unittest.TestCase):
    def test_staged_reference_stock_query_uses_owner_and_repair_is_not_a_source_change(self):
        from yadinassi import Interpreter
        from yadinassi.database_context import SQLiteDBContext
        from test_inventory_reference_profile import imported
        temporary = tempfile.TemporaryDirectory(dir=ROOT.parent); self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'inventory.sqlite'
        context = SQLiteDBContext.create_inventory(path, imported()); self.addCleanup(context.close)
        vm = Interpreter(database_context=context, output=lambda value: None); self.addCleanup(vm.close)
        vm.execute('P=Catalogs.Products.CreateItem();P.Code="P";P.Write();'
            'W=Catalogs.Warehouses.CreateItem();W.Code="W";W.Write();'
            'D=Documents.Receipt.CreateDocument();D.Number="1";D.Date=Date(2024,1,1);D.Warehouse=W.Ref;'
            'L=D.Lines.Add();L.Product=P.Ref;L.Quantity=2;L.Amount=3;'
            'Q=New Query("SELECT QuantityBalance AS N FROM AccumulationRegister.Stock.Balance(&At)");'
            'Q.SetParameter("At",Date(2024,1,2));')
        with patch('yadinassi.sqlite_inventory_profile.import_inventory_configuration') as importer:
            vm.execute('BeginTransaction();D.Write(DocumentWriteMode.Posting);'
                'S=Q.Execute().Select();S.Next();Inside=S.N;RollbackTransaction();'
                'S=Q.Execute().Select();HasAfter=S.Next();')
            self.assertEqual(vm.execute('Inside'), 2)
            self.assertFalse(vm.execute('HasAfter'))
            importer.assert_not_called()
        self.assertIsNone(context.backend._active)
