"""One constant-batch admission; no stale proof crosses later operations."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from test_source_session_parameters import declaration
from test_configuration_source_runtime import source
from yadinassi.configuration_source import import_source
from yadinassi.source_constant_store import SourceConstantStore


def package(count):
    names = tuple('Value'+str(n) for n in range(count))
    xml = source().files[0].content
    files = {'Configuration.xml':xml.replace(b'</Configuration>',
        ('<ChildObjects>'+''.join('<Constant>'+n+'</Constant>' for n in names)+
         '</ChildObjects></Configuration>').encode())}
    for name in names:
        files['Constants/'+name+'.xml'] = declaration(name,'<v8:Type>xs:boolean</v8:Type>').replace(
            b'SessionParameter',b'Constant')
    return import_source(files), names


class ConstantBatchAdmissionTests(unittest.TestCase):
    def store(self,count):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        config,names = package(count)
        store = SourceConstantStore.create(Path(tmp.name)/'scratch.sqlite',config)
        self.addCleanup(store.close)
        # Author test data through exact store encodings without N setup audits.
        store._connection.executemany('INSERT INTO constant_value VALUES(?,?)',
            [(str(store._definitions[n.casefold()].identity),'["boolean",true]') for n in names])
        return store,names

    def test_admission_and_value_queries_are_batched_for_16_64_256(self):
        for n in (16,64,256):
            with self.subTest(n=n):
                store,names = self.store(n)
                trace=[];store._connection.set_trace_callback(trace.append)
                self.assertEqual(store.get_many(names),dict.fromkeys((n.casefold() for n in names),True))
                self.assertEqual(sum('FROM sqlite_master' in sql for sql in trace),1)
                self.assertEqual(sum('FROM source_binding' in sql for sql in trace),1)
                self.assertEqual(sum('FROM constant_schema' in sql for sql in trace),1)
                self.assertEqual(sum('FROM constant_value' in sql for sql in trace),1)

    def test_later_same_connection_schema_tamper_rechecked(self):
        store,names=self.store(16);self.assertEqual(len(store.get_many(names)),16)
        store._connection.execute('CREATE TABLE foreign_data(x)')
        with self.assertRaisesRegex(ValueError,'file/schema integrity'):store.get_many(names)

    def test_external_commit_not_hidden_by_prior_batch(self):
        store,names=self.store(16);store.get_many(names)
        with closing(sqlite3.connect(store.path)) as connection,connection:
            connection.execute('UPDATE constant_value SET value_json=?',('["boolean",false]',))
        self.assertEqual(store.get_many(names),dict.fromkeys((n.casefold() for n in names),False))

    def test_pending_values_visible_and_error_rolls_back_explicit_transaction(self):
        store,names=self.store(16)
        store.begin_transaction();store.set(names[0],False)
        self.assertIs(store.get_many(names)[names[0].casefold()],False)
        with self.assertRaisesRegex(ValueError,'unknown constant'):store.get_many((*names,'Missing'))
        self.assertFalse(store.transaction_active)
        self.assertIs(store.get(names[0]),True)

    def test_ordered_uninitialized_error_precedes_later_unknown_name(self):
        store,names=self.store(2)
        store._connection.execute('DELETE FROM constant_value WHERE identity=?',
                                  (str(store._definitions[names[0].casefold()].identity),))
        with self.assertRaisesRegex(ValueError,'uninitialized constant: '+names[0]):
            store.get_many((names[0],'Missing'))

    def test_iterator_side_effect_is_checked_before_using_batch(self):
        store,names=self.store(2)
        def names_with_effect():
            yield names[0]
            store._connection.execute('CREATE TABLE foreign_data(x)')
            yield names[1]
        with self.assertRaisesRegex(ValueError,'file/schema integrity'):
            store.get_many(names_with_effect())

    def test_iterator_committing_explicit_transaction_gets_new_read_snapshot(self):
        store,names=self.store(2);store.begin_transaction()
        def iterator():
            store.commit_transaction()
            yield from names
        trace=[];store._connection.set_trace_callback(trace.append)
        self.assertEqual(len(store.get_many(iterator())),2)
        self.assertIn('COMMIT',trace);self.assertIn('BEGIN',trace);self.assertIn('ROLLBACK',trace)
        self.assertLess(trace.index('COMMIT'),trace.index('BEGIN'))

    def test_iterator_beginning_explicit_transaction_keeps_it_open(self):
        store,names=self.store(2)
        def iterator():
            store.begin_transaction()
            yield from names
        self.assertEqual(len(store.get_many(iterator())),2)
        self.assertTrue(store.transaction_active)
        store.rollback_transaction()

    def test_iterator_exception_rolls_back_explicit_transaction(self):
        store,names=self.store(2)
        def iterator():
            store.begin_transaction();store.set(names[0],False)
            yield names[0]
            raise RuntimeError('iterator failed')
        with self.assertRaisesRegex(RuntimeError,'iterator failed'):store.get_many(iterator())
        self.assertFalse(store.transaction_active);self.assertIs(store.get(names[0]),True)

    @unittest.skipUnless(hasattr(sqlite3.Connection,'setlimit'),'Python 3.11+ limit API')
    def test_lowered_variable_limit_chunks_without_duplicate_names(self):
        store,names=self.store(64)
        store._connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,16)
        trace=[];store._connection.set_trace_callback(trace.append)
        self.assertEqual(len(store.get_many(names+names)),64)
        self.assertEqual(sum('FROM constant_value' in sql for sql in trace),4)
