"""Real MainDemo BSL COUNT keeps enum owner/source witness and data proofs."""
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import sqlite3
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.query.queries import BSLQuery
from yadinassi.db.query.relational_queries import _Plan
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier
import test_main_demo_runtime as fixtures

class EnumCountPushdownTests(unittest.TestCase):
    def setUp(self):
        fixtures.MainDemoRuntimeTests.setUp(self);self.vm.execute(fixtures.SEED)
        self.backend=self.context.backend
        self.schema=next(s for s in self.backend._schemas if s.name=='Номенклатура')
        self.table=quote_identifier(self.backend._layout.table_name(self.schema.identity))
    def query(self):return BSLQuery(self.vm._catalogs,'SELECT COUNT(*) AS N FROM Catalog.Номенклатура')
    def mutate(self,sql,args=()):
        with closing(sqlite3.connect(self.path)) as c,c:c.execute(sql,args)
    def test_actual_bsl_query_and_batch_use_provider_without_load(self):
        with patch.object(_Plan,'load',side_effect=AssertionError('materialization')):
            self.assertEqual(self.query().execute()._rows,((Decimal(1),),))
            self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Номенклатура");S=Q.Execute().Select();S.Next();Message(S.N);')
            batch=BSLQuery(self.vm._catalogs,'SELECT COUNT(*) AS N FROM Catalog.Номенклатура;SELECT COUNT(*) AS N FROM Catalog.Номенклатура')
            self.assertEqual([r._rows for r in batch.execute_batch().items],[((Decimal(1),),)]*2)
        self.assertEqual(self.output,['1'])
        self.assertTrue(any(k[0]=='catalog-count-unique-v1' for k in self.backend._read_handle.proofs))
    def test_unprojected_reference_corruption_invalidates_warm_count(self):
        self.query().execute()
        column=quote_identifier(self.backend._layout.field_name(self.schema.identity,self.schema.fields[0].identity))
        self.mutate('UPDATE '+self.table+' SET '+column+'=?',('not-a-uuid',))
        with self.assertRaises(BackendError):self.query().execute()
    def test_rehashed_source_is_not_new_authority(self):
        self.query().execute()
        with closing(sqlite3.connect(self.path)) as c:raw=c.execute("SELECT content FROM configuration_file WHERE path='Configuration.xml'").fetchone()[0]+b'\n'
        self.mutate("UPDATE configuration_file SET content=?,sha256=? WHERE path='Configuration.xml'",(raw,sha256(raw).hexdigest()))
        with self.assertRaises(BackendError):self.query().execute()
    def test_enum_owner_revocation_and_mapping_changes_reject_before_provider(self):
        self.query().execute();scope=self.vm._metadata._enum_storage_scope
        with patch.object(_View,'aggregate_catalog',side_effect=AssertionError('must reject first')):
            old=scope.generation;scope.generation=-1
            try:
                with self.assertRaises(BackendError):self.query().execute()
            finally:scope.generation=old
            managers=scope.namespace._managers;key=next(iter(managers));value=managers.pop(key)
            try:
                with self.assertRaises(BackendError):self.query().execute()
            finally:managers[key]=value
    def test_foreign_unused_enum_parameter_still_rejects(self):
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        foreign=other.execute('Enums.Units.Piece')
        q=self.query();q.set_parameter('Unused',foreign)
        with patch.object(_View,'aggregate_catalog',side_effect=AssertionError('must reject first')):
            with self.assertRaises(BackendError):q.execute()
    def test_own_write_refreshes_count_and_transaction_stays_residual(self):
        self.query().execute();self.vm.execute(fixtures.SEED)
        self.assertEqual(self.query().execute()._rows,((Decimal(2),),))
        load=_Plan.load;seen=[]
        def observe(plan,*args):seen.append(1);return load(plan,*args)
        with patch.object(_Plan,'load',observe):
            self.vm.execute('BeginTransaction();Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Номенклатура");S=Q.Execute().Select();S.Next();Message(S.N);RollbackTransaction();')
        self.assertEqual(seen,[1]);self.assertEqual(self.output,['2'])
    def test_same_owned_readonly_snapshot_and_post_provider_revocation(self):
        from yadinassi.configuration.demos.inventory_enum_runtime import _POINT_READ
        original=_View.aggregate_catalog;observed=[]
        def provider(view,*args):
            witness=_POINT_READ.get();self.assertIsNotNone(witness)
            self.assertIs(witness[1],view);self.assertIs(self.backend._active,view)
            self.assertTrue(view._connection.in_transaction)
            self.assertEqual(view._connection.execute('PRAGMA query_only').fetchone(),(1,))
            observed.append(view);return original(view,*args)
        with patch.object(_View,'aggregate_catalog',provider):self.query().execute()
        self.assertEqual(len(observed),1)
        scope=self.vm._metadata._enum_storage_scope;generation=scope.generation
        def revoke(view,*args):
            result=original(view,*args);scope.generation=-1;return result
        try:
            with patch.object(_View,'aggregate_catalog',revoke),self.assertRaises(BackendError):self.query().execute()
        finally:scope.generation=generation
        self.assertIsNone(self.backend._active)
    def test_missing_physical_capability_is_explicit_relational_residual(self):
        from yadinassi.db.sqlite.sqlite_documents import DocumentView
        load=_Plan.load;seen=[]
        def observe(plan,*args):seen.append(1);return load(plan,*args)
        with patch.object(DocumentView,'aggregate_catalog',None),patch.object(_Plan,'load',observe):
            self.assertEqual(self.query().execute()._rows,((Decimal(1),),))
        self.assertEqual(seen,[1])

class EnumFieldCountTests(unittest.TestCase):
    def setUp(self):
        from test_inventory_enum_relational_reporting import EnumRelationalGuardTests
        EnumRelationalGuardTests.setUp(self)
    def test_unused_enum_field_corruption_is_not_hidden(self):
        query=lambda:BSLQuery(self.vm._catalogs,'SELECT COUNT(*) AS N FROM Catalog.Products').execute()
        with patch.object(_Plan,'load',side_effect=AssertionError('materialization')):
            self.assertEqual(query()._rows,((Decimal(3),),))
        backend=self.context.backend;schema=next(s for s in backend._schemas if s.name=='Products')
        field=next(f for f in schema.fields if f.kind=='enum_ref')
        table=quote_identifier(backend._layout.table_name(schema.identity))
        column=quote_identifier(backend._layout.field_name(schema.identity,field.identity))
        with closing(sqlite3.connect(self.context.path)) as c,c:
            c.execute('UPDATE '+table+' SET '+column+'=?',('ffffffff-ffff-ffff-ffff-ffffffffffff',))
        with self.assertRaises(BackendError):query()
