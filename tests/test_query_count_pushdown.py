"""COUNT physical plan equivalence, not performance or new native evidence."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch
from yadinassi.db.query import query_pushdown, relational_queries, queries, query_parser
from yadinassi.db.catalog.catalog_backend import BackendError, CatalogAggregateRequest, CatalogAggregateResult
from yadinassi.db.query.queries import BSLQuery
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier
import test_catalog_queries as fixtures

class CountPushdownTests(unittest.TestCase):
    setUp=fixtures.CatalogQueryTests.setUp
    tearDown=fixtures.CatalogQueryTests.tearDown
    def query(self,text='SELECT COUNT(*) AS N FROM Catalog.Products'):
        return BSLQuery(self.vm._catalogs,text).execute()
    def sql(self,statement,args=(), *, corrupt=False):
        with closing(sqlite3.connect(self.context.path)) as c,c:
            if corrupt: c.execute('PRAGMA ignore_check_constraints=ON')
            return c.execute(statement,args).fetchall()
    def table(self):
        self.manager=self.vm._catalogs.get_index('Products')
        return quote_identifier(self.context.backend._layout.table_name(self.manager._schema.identity))
    def test_no_materialization_and_result_metadata_equivalence(self):
        with patch.object(query_pushdown,'count_eligible',return_value=False):expected=self.query()
        with patch.object(relational_queries._Plan,'load',side_effect=AssertionError('materialization')):actual=self.query()
        self.assertEqual(actual._rows,((Decimal(3),),));self.assertEqual(actual._rows,expected._rows)
        self.assertEqual(actual._columns,expected._columns)
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Products");S=Q.Execute().Select();S.Next();Message(S.N);')
        self.assertEqual(self.output,['3'])
    def test_empty_and_duplicate_payload_values(self):
        table=self.table();self.sql('UPDATE '+table+' SET description=?',('same',))
        self.assertEqual(self.query()._rows,((Decimal(3),),))
        self.sql('DELETE FROM '+table)
        self.assertEqual(self.query()._rows,((Decimal(0),),))
    def assert_normalized_key_failure(self, error):
        for projection, suffix in (('COUNT(Ref)', ''),
                                   ('COUNT(*)', 'WHERE 1=1'),
                                   ('COUNT(*)', 'WHERE 1=0'),
                                   ('COUNT(DISTINCT Ref)', ''),
                                   ('COUNT(*)', 'WHERE DeletionMark=FALSE'),
                                   ('COUNT(*)+0', 'ORDER BY N')):
            sql = f'SELECT {projection} AS N FROM Catalog.Products {suffix}'
            with self.subTest(query=sql), self.assertRaisesRegex(BackendError, error):
                self.query(sql)

    def test_count_does_not_decode_duplicate_logical_ids_but_ref_does(self):
        table=self.table();ids=self.sql('SELECT record_id FROM '+table)
        alias=ids[0][0].replace('-','').upper()
        self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(alias,ids[1][0]))
        self.assertEqual(self.query()._rows,((Decimal(3),),))
        with self.assertRaisesRegex(BackendError,'integrity'):
            self.query('SELECT Ref FROM Catalog.Products')
        self.assert_normalized_key_failure('integrity')
        with patch.object(query_pushdown,'count_eligible',return_value=False):
            with self.assertRaisesRegex(BackendError,'integrity'):self.query()
    def test_unique_uuid_alias_and_null_reference_remain_valid(self):
        table=self.table();record=self.sql('SELECT record_id FROM '+table)[0][0]
        self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(record.replace('-','').upper(),record))
        field=next(f for f in self.manager._schema.fields if f.name=='Category')
        column=quote_identifier(self.context.backend._layout.field_name(self.manager._schema.identity,field.identity))
        self.sql('UPDATE '+table+' SET '+column+'=NULL')
        for enabled in (False,True):
            with patch.object(query_pushdown,'count_eligible',wraps=query_pushdown.count_eligible) as eligible:
                if not enabled:eligible.return_value=False
                self.assertEqual(self.query()._rows,((Decimal(3),),))
    def test_normalized_count_preserves_uuid_parser_alias_domain(self):
        table = self.table()
        record = self.sql('SELECT record_id FROM '+table)[0][0]
        for alias in ('{'+record.replace('-','').upper()+'}', '1_'+'0'*30,
                      '\N{ARABIC-INDIC DIGIT ONE}'+'0'*31):
            with self.subTest(alias=alias):
                self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(alias,record))
                try:
                    self.assertEqual(self.query('SELECT COUNT(Ref) FROM Catalog.Products')._rows,
                                     ((Decimal(3),),))
                    self.assertEqual(self.query('SELECT COUNT(DISTINCT Ref) FROM Catalog.Products')._rows,
                                     ((Decimal(3),),))
                    self.assertEqual(self.query('SELECT COUNT(*) FROM Catalog.Products WHERE 1=0')._rows,
                                     ((Decimal(0),),))
                finally:
                    self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(record,alias))

    def test_count_ignores_unprojected_corruption_but_field_read_rejects_it(self):
        table=self.table();field=next(f for f in self.manager._schema.fields if f.name=='Amount')
        column=quote_identifier(self.context.backend._layout.field_name(self.manager._schema.identity,field.identity))
        self.assertEqual(self.query()._rows,((Decimal(3),),))
        statement = 'UPDATE '+table+' SET '+column+'=? WHERE code=?'
        invalid = ('not-a-number','3')
        with self.assertRaisesRegex(sqlite3.IntegrityError,'CHECK constraint failed'):
            self.sql(statement,invalid)
        # Deliberate disk corruption, not a valid typed-storage write.
        self.sql(statement,invalid,corrupt=True)
        self.assertEqual(self.query()._rows,((Decimal(3),),))
        self.assertEqual(self.query('SELECT COUNT(Ref) FROM Catalog.Products WHERE 1=1')._rows,
                         ((Decimal(3),),))
        with self.assertRaisesRegex(BackendError,'integrity'):
            self.query('SELECT Amount FROM Catalog.Products')
    def test_input_and_result_limits_preserved(self):
        for module,name in ((query_parser,'MAX_ROWS'),(queries,'_MAX_CELLS')):
            with patch.object(module,name,2),self.assertRaises(ValueError):self.query()
    def test_out_of_shape_declines_and_capability_optional(self):
        for suffix in (' WHERE Active=TRUE',' GROUP BY Active',' ORDER BY COUNT(DISTINCT Ref)'):
            with patch.object(_View,'aggregate_catalog',side_effect=AssertionError('unexpected pushdown')):
                self.query('SELECT COUNT(*) AS N FROM Catalog.Products'+suffix)
        with patch.object(_View,'aggregate_catalog',None):self.assertEqual(self.query()._rows,((Decimal(3),),))
        with patch.object(_View,'aggregate_catalog',return_value=None):self.assertEqual(self.query()._rows,((Decimal(3),),))
        with patch.object(_View,'aggregate_catalog',return_value=CatalogAggregateResult(True)),self.assertRaises(BackendError):self.query()
    def test_count_normal_forms_and_constant_predicates_use_one_native_statement(self):
        cases = (
            ('COUNT(*) AS N', '', (Decimal(3),)),
            ('COUNT(*) AS N', 'WHERE 1=1', (Decimal(3),)),
            ('COUNT(P.Ref) AS N', '', (Decimal(3),)),
            ('COUNT(DISTINCT P.Ref)+0.00 AS N', 'ORDER BY N', (Decimal('3.00'),)),
            ('COUNT(P.Ref)+0 AS N, "caption" AS Marker',
             'WHERE 1+1=2 ORDER BY N DESC', (Decimal(3), 'caption')),
            ('COUNT(*)+0.00 AS N, TRUE AS Marker', 'ORDER BY N', (Decimal('3.00'), True)),
            ('COUNT(*) AS N, 1 AS Marker', 'WHERE 1=0', (Decimal(0), Decimal(1))),
            ('COUNT(*) AS N', 'WHERE NULL=1', (Decimal(0),)),
            ('COUNT(*) AS N', 'WHERE NULL IS NULL', (Decimal(3),)),
        )
        for empty in (False, True):
            if empty: self.sql('DELETE FROM '+self.table())
            self.query()
            connection = self.context.backend._read_handle.connection
            for projection, suffix, values in cases:
                text = f'SELECT {projection} FROM Catalog.Products AS P {suffix}'
                with self.subTest(empty=empty, text=text):
                    with patch.object(query_pushdown, 'count_eligible', return_value=False):
                        residual = self.query(text)
                    trace = []
                    connection.set_trace_callback(trace.append)
                    try:
                        with patch.object(relational_queries._Plan, 'load',
                                          side_effect=AssertionError('materialization')):
                            result = self.query(text)
                    finally:
                        connection.set_trace_callback(None)
                    self.assertEqual(result._columns, residual._columns)
                    self.assertEqual(result._rows, residual._rows)
                    if not empty:
                        self.assertEqual(result._rows, (values,))
                    self.assertEqual(len(trace), 1)
                    if projection == 'COUNT(*) AS N' and not suffix:
                        self.assertTrue(trace[0].startswith('SELECT COUNT(*) '))
                        self.assertNotIn('record_id', trace[0])
                    else:
                        self.assertTrue(trace[0].startswith('SELECT COUNT(*),'))
                        self.assertIn('record_id GLOB', trace[0])
                    self.assertFalse(connection.in_transaction)

    def test_nullable_and_distinct_nonidentity_counts_remain_residual(self):
        table = self.table()
        field = next(f for f in self.manager._schema.fields if f.name == 'Category')
        column = quote_identifier(self.context.backend._layout.field_name(self.manager._schema.identity, field.identity))
        self.sql('UPDATE '+table+' SET '+column+'=NULL')
        for field, expected in (('Category', 3), ('DISTINCT Category', 1)):
            text = f'SELECT COUNT({field})+0 AS N FROM Catalog.Products ORDER BY N'
            with self.subTest(text=text), patch.object(_View, 'aggregate_catalog',
                    side_effect=AssertionError('arbitrary reference count selected')):
                self.assertEqual(self.query(text)._rows, ((Decimal(expected),),))

    def test_deletion_mark_count_one_statement_with_selected_input_budget(self):
        table = self.table()
        self.sql('UPDATE '+table+' SET deletion_mark=1 WHERE code=?', ('1',))
        self.query()
        connection = self.context.backend._read_handle.connection
        for projection, pred, expected in (
                ('COUNT(*)', 'FALSE', 2),
                ('COUNT(*)', 'TRUE', 1),
                ('COUNT(DISTINCT P.Ref)', 'FALSE', 2)):
            text = f'SELECT {projection} AS N FROM Catalog.Products AS P WHERE P.DeletionMark={pred}'
            with self.subTest(text=text):
                with patch.object(query_pushdown, 'count_eligible', return_value=False):
                    residual = self.query(text)
                trace = []
                connection.set_trace_callback(trace.append)
                try:
                    with patch.object(relational_queries._Plan, 'load',
                                      side_effect=AssertionError('materialization')):
                        result = self.query(text)
                finally:
                    connection.set_trace_callback(None)
                self.assertEqual(result._rows, ((Decimal(expected),),))
                self.assertEqual(result._rows, residual._rows)
                self.assertEqual(result._columns, residual._columns)
                self.assertEqual(len(trace), 1, trace)
                self.assertIn('COUNT(CASE WHEN deletion_mark=', trace[0])
        text = 'SELECT COUNT(*) FROM Catalog.Products WHERE DeletionMark=TRUE'
        with patch.object(queries, '_MAX_CELLS', 1):
            self.assertEqual(self.query(text)._rows, ((Decimal(1),),))
        with patch.object(queries, '_MAX_CELLS', 1), self.assertRaisesRegex(ValueError, 'input resource'):
            self.query('SELECT COUNT(*) FROM Catalog.Products WHERE DeletionMark=FALSE')

    def test_shared_catalog_witness_qualifies_projected_text_units(self):
        from yadinassi.db.sqlite.sqlite_document_count import catalog_header_witness
        table = self.table()
        with closing(self.context.backend.begin_query_read()) as view:
            raw = view._view
            valid, units, args = catalog_header_witness(
                raw, self.manager._schema, alias='src', text_fields=('description', 'deletion_mark', 'code'))
            row = raw._connection.execute(f'SELECT SUM({valid}),SUM({units}) FROM {table} AS src', args).fetchone()
        self.assertEqual(row, (3, 15))

    def test_total_neutrals_and_nonascii_hidden_text_keep_native_header_count(self):
        table = self.table()
        self.sql('UPDATE '+table+' SET description=? WHERE code=?', ('Склад😀', '1'))
        self.query()
        connection = self.context.backend._read_handle.connection
        cases = (
            ('SELECT COUNT(DISTINCT Ref) FROM Catalog.Products', 3),
            ('SELECT COUNT(*) FROM Catalog.Products WHERE DeletionMark=FALSE AND 1=1', 3),
            ('SELECT COUNT(*) FROM Catalog.Products WHERE (1=0 OR NOT (NULL IS NOT NULL)) '
             'AND (DeletionMark=FALSE OR 2=3)', 3),
        )
        for statement, count in cases:
            with self.subTest(statement=statement):
                trace = []
                connection.set_trace_callback(trace.append)
                try:
                    with patch.object(relational_queries._Plan, 'load',
                                      side_effect=AssertionError('materialized input')):
                        self.assertEqual(self.query(statement)._rows, ((Decimal(count),),))
                finally:
                    connection.set_trace_callback(None)
                self.assertEqual(len(trace), 1, trace)
                self.assertTrue(trace[0].startswith('SELECT COUNT(*)'), trace)
        with self.assertRaisesRegex(ValueError, 'division by zero'):
            self.query('SELECT COUNT(*) FROM Catalog.Products WHERE DeletionMark=FALSE AND 1/0=1')
        self.assertEqual(self.query('SELECT COUNT(*) FROM Catalog.Products WHERE '
                                    'DeletionMark=FALSE AND NULL=NULL')._rows, ((Decimal(0),),))

    def test_neutral_filter_keeps_original_full_input_charge(self):
        table = self.table()
        self.sql('UPDATE '+table+' SET deletion_mark=1 WHERE code=?', ('1',))
        prefix = 'SELECT COUNT(*) FROM Catalog.Products WHERE '
        with patch.object(queries, '_MAX_CELLS', 1):
            self.assertEqual(self.query(prefix+'DeletionMark=TRUE')._rows, ((Decimal(1),),))
            self.assertEqual(self.query(prefix+'DeletionMark=TRUE AND DeletionMark=TRUE')._rows,
                             ((Decimal(1),),))
            for predicate in ('DeletionMark=TRUE AND 1=1', 'DeletionMark=TRUE OR 1=0'):
                with self.subTest(predicate=predicate):
                    for native in (False, True):
                        from contextlib import nullcontext
                        oracle = (nullcontext() if native else
                                  patch.object(query_pushdown, 'count_eligible', return_value=False))
                        with oracle, self.assertRaisesRegex(ValueError, 'input resource'):
                            self.query(prefix+predicate)

    def test_unicode_witness_accounts_characters_and_declines_invalid_utf8(self):
        from yadinassi.db.sqlite.sqlite_document_count import catalog_header_witness
        table = self.table()
        length = self.manager._schema.description_length
        describe = 'Склад😀'
        self.sql('UPDATE '+table+' SET description=?', (describe,))
        with closing(self.context.backend.begin_query_read()) as view:
            raw = view._view
            valid, units, args = catalog_header_witness(raw, self.manager._schema,
                                                       text_fields=('description',))
            sql = f'SELECT SUM({valid}), SUM({units}) FROM {table}'
            self.assertEqual(raw._connection.execute(sql,args).fetchone(), (3, 3*len(describe)))
        statement = 'SELECT COUNT(DISTINCT Ref) FROM Catalog.Products'
        # Keep the storage failure and its classification on the strict residual.
        self.sql('UPDATE '+table+" SET description=CAST(x'ff' AS TEXT) WHERE code='1'")
        with patch.object(query_pushdown, 'count_eligible', return_value=False):
            with self.assertRaises(BackendError) as expected:
                self.query(statement)
        with self.assertRaises(BackendError) as actual:
            self.query(statement)
        self.assertEqual(actual.exception.code, expected.exception.code)
        self.sql('UPDATE '+table+' SET description=? WHERE code=?', ('😀'*length, '1'))
        with self.assertRaisesRegex(BackendError, 'integrity'):
            self.query(statement)

    def test_sql_unicode_witness_matches_strict_utf16_qualifier_boundaries(self):
        from yadinassi.db.catalog.catalog_qualifiers import validate_string
        from yadinassi.db.sqlite.sqlite_query_indexes import register_query_collations
        from yadinassi.db.sqlite.sqlite_text_witness import text_check

        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE TABLE sample(text TEXT)')
            register_query_collations(connection)
            for value, units in (('А', 1), ('😀', 2), ('e\u0301', 2), ('😀a', 3)):
                with self.subTest(value=value):
                    validate_string(value, units)
                    with self.assertRaisesRegex(ValueError, 'catalog String length'):
                        validate_string(value, units-1)
                    connection.execute('DELETE FROM sample')
                    connection.execute('INSERT INTO sample VALUES(?)', (value,))
                    fitting, too_short = (text_check('text', limit) for limit in (units, units-1))
                    self.assertEqual(connection.execute(
                        f'SELECT {fitting},{too_short},length(text) FROM sample').fetchone(),
                        (1, 0, len(value)))
            validate_string('А\0', 2)
            connection.execute("INSERT INTO sample VALUES(?),(CAST(x'ff' AS TEXT))", ('А\0',))
            witness = text_check('text', 2)
            self.assertEqual(connection.execute(
                f'SELECT {witness} FROM sample WHERE rowid>1 ORDER BY rowid').fetchall(), [(0,), (0,)])

    def test_tight_unicode_catalog_header_remains_on_native_count(self):
        table = self.table()
        units = self.manager._schema.description_length
        value = '😀'*(units//2)+'А'*(units%2)
        self.sql('UPDATE '+table+' SET description=? WHERE code=?', (value, '1'))
        with patch.object(relational_queries._Plan, 'load',
                          side_effect=AssertionError('qualifier-fitting row declined')):
            self.assertEqual(self.query('SELECT COUNT(DISTINCT Ref) FROM Catalog.Products')._rows,
                             ((Decimal(3),),))
        self.sql('UPDATE '+table+' SET description=? WHERE code=?', (value+'А', '1'))
        with self.assertRaisesRegex(BackendError, 'integrity'):
            self.query('SELECT COUNT(DISTINCT Ref) FROM Catalog.Products')

    def test_sql_unicode_witness_cannot_treat_utf16_database_blob_as_utf8(self):
        from yadinassi.db.sqlite.sqlite_query_indexes import register_query_collations
        from yadinassi.db.sqlite.sqlite_text_witness import text_check
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute("PRAGMA encoding='UTF-16le'")
            connection.execute('CREATE TABLE sample(text TEXT)')
            register_query_collations(connection)
            connection.execute('INSERT INTO sample VALUES(?)', ('꧃',))
            witness = text_check('text', 1)
            self.assertEqual(connection.execute(
                f'SELECT hex(CAST(text AS BLOB)),{witness} FROM sample').fetchone(), ('C3A9', 0))

    def test_deletion_mark_parameter_requires_exact_boolean(self):
        query = BSLQuery(self.vm._catalogs, 'SELECT COUNT(*) FROM Catalog.Products WHERE DeletionMark=&Mark')
        query.set_parameter('Mark', False)
        with patch.object(relational_queries._Plan, 'load', side_effect=AssertionError('materialization')):
            self.assertEqual(query.execute()._rows, ((Decimal(3),),))
        query.set_parameter('Mark', Decimal(0))
        with patch.object(_View, 'aggregate_catalog', side_effect=AssertionError('mixed-kind filter')):
            with self.assertRaisesRegex((TypeError, ValueError), 'exact field type'):
                query.execute()
        with patch.object(_View, 'aggregate_catalog', side_effect=AssertionError('NULL filter')):
            self.assertEqual(self.query('SELECT COUNT(*) FROM Catalog.Products WHERE DeletionMark=NULL')._rows,
                             ((Decimal(0),),))

    def test_marked_corrupt_hidden_payload_is_not_removed_before_validation(self):
        table = self.table()
        amount = next(field for field in self.manager._schema.fields if field.name == 'Amount')
        column = quote_identifier(self.context.backend._layout.field_name(self.manager._schema.identity, amount.identity))
        self.sql('UPDATE '+table+' SET deletion_mark=1,'+column+'=? WHERE code=?',
                 ('broken', '1'), corrupt=True)
        for expected_fast in (False, True):
            with self.subTest(fast=expected_fast), patch.object(
                    query_pushdown, 'count_eligible', wraps=query_pushdown.count_eligible) as eligible:
                if not expected_fast:
                    eligible.return_value = False
                for expression in ('COUNT(*) FROM Catalog.Products WHERE DeletionMark=FALSE',
                                   'COUNT(DISTINCT Ref) FROM Catalog.Products'):
                    with self.assertRaisesRegex(BackendError, 'integrity'):
                        self.query('SELECT ' + expression)

    def test_constant_empty_filter_preserves_input_budget(self):
        with patch.object(queries, '_MAX_CELLS', 2), self.assertRaisesRegex(ValueError, 'input resource'):
            self.query('SELECT COUNT(*) AS N FROM Catalog.Products WHERE 1=0')

    @unittest.skipUnless(hasattr(sqlite3.Connection, 'setlimit'), 'requires live SQLite limits')
    def test_normalized_count_declines_before_preparing_under_lower_limits(self):
        text = 'SELECT COUNT(Ref) AS N FROM Catalog.Products'
        with patch.object(query_pushdown, 'count_eligible', return_value=False):
            expected = self.query(text)
        # Warm only the residual, not the optional SQL: SQLite can reuse a
        # statement prepared before a lower connection limit was installed.
        connection = self.context.backend._read_handle.connection
        for category, limit in ((sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH, 32),
                                (sqlite3.SQLITE_LIMIT_LENGTH, 200),
                                (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 1)):
            with self.subTest(category=category):
                prior = connection.setlimit(category, limit)
                try:
                    with patch('yadinassi.db.sqlite.sqlite_single_statement.fetch_one',
                               side_effect=AssertionError('optional proof reached SQLite')):
                        result = self.query(text)
                    self.assertEqual(result._rows, expected._rows)
                    self.assertEqual(result._columns, expected._columns)
                    trace = []
                    connection.set_trace_callback(trace.append)
                    try:
                        self.assertEqual(self.query()._rows, expected._rows)
                    finally:
                        connection.set_trace_callback(None)
                    self.assertEqual(len(trace), 1, trace)
                    self.assertTrue(trace[0].startswith('SELECT COUNT(*) FROM '))
                finally:
                    connection.setlimit(category, prior)
        self.assertEqual(self.query(text)._rows, expected._rows)

    def test_normalized_count_statement_failure_is_not_a_decline(self):
        self.query()
        with patch('yadinassi.db.sqlite.sqlite_single_statement.fetch_one',
                   side_effect=sqlite3.OperationalError('driver error')):
            with self.assertRaisesRegex(BackendError, '^storage_error$'):
                self.query('SELECT COUNT(Ref) AS N FROM Catalog.Products')
        self.assertIsNone(self.context.backend._active)
        self.assertEqual(self.query('SELECT COUNT(Ref) AS N FROM Catalog.Products')._rows, ((Decimal(3),),))

    def test_warm_count_does_not_decode_rows_after_external_update(self):
        self.query()
        table=self.table();self.sql('UPDATE '+table+' SET description=?',('changed',))
        with patch.object(_View,'_scalar',side_effect=AssertionError('unexpected row decoding')):
            self.assertEqual(self.query()._rows,((Decimal(3),),))

    def test_count_does_not_decode_malformed_ids_but_ref_does(self):
        table=self.table();record=self.sql('SELECT record_id FROM '+table)[0][0]
        for invalid,error in (('not-a-uuid','integrity'),
                              (record+'\0','integrity'),
                              (record.encode('ascii'),'integrity'),
                              ('00000000-0000-0000-0000-000000000000','invalid_input'),
                              ('{'+record+'}','integrity')):
            with self.subTest(record_id=invalid):
                self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(invalid,record))
                try:
                    self.assertEqual(self.query()._rows,((Decimal(3),),))
                    with self.assertRaisesRegex(BackendError,error):
                        self.query('SELECT Ref FROM Catalog.Products')
                    self.assert_normalized_key_failure(error)
                    with patch.object(query_pushdown,'count_eligible',return_value=False):
                        with self.assertRaisesRegex(BackendError,error):self.query()
                finally:self.sql('UPDATE '+table+' SET record_id=? WHERE record_id=?',(record,invalid))
    def test_internal_writer_invalidates_unique_proof_and_closed_view_rejects(self):
        self.query()
        self.vm.execute('P=Catalogs.Products.CreateItem();P.Code="4";P.Write();')
        self.assertEqual(self.query()._rows,((Decimal(4),),))
        manager=self.vm._catalogs.get_index('Products');view=self.context.backend.begin_read()
        try:self.assertEqual(view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest()).count,4)
        finally:view.close()
        with self.assertRaisesRegex(BackendError,'closed'):view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
    def test_readonly_sql_and_warm_distinct_proof_are_separate(self):
        manager=self.vm._catalogs.get_index('Products');backend=self.context.backend
        view=backend.begin_read();sql=[];view._connection.set_trace_callback(sql.append)
        try:
            view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
            self.assertTrue(any('COUNT(DISTINCT' in line for line in sql));sql.clear()
            view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
            self.assertFalse(any('COUNT(DISTINCT' in line for line in sql))
            self.assertTrue(any('SELECT COUNT(*) FROM' in line for line in sql))
            with self.assertRaises(sqlite3.OperationalError):view._connection.execute('DELETE FROM database_info')
        finally:view.close()
    def test_count_sees_external_commits_on_the_same_read_connection(self):
        table=self.table();backend=self.context.backend
        self.assertEqual(self.query()._rows,((Decimal(3),),))
        connection=backend._read_handle.connection
        for code, expected in (('1',2),('2',1)):
            self.sql('DELETE FROM '+table+' WHERE code=?',(code,))
            self.assertEqual(self.query()._rows,((Decimal(expected),),))
            self.assertIs(backend._read_handle.connection,connection)
    def test_wal_storage_is_still_explicitly_unsupported(self):
        self.table();backend=self.context.backend
        backend._close_idle_read_handle();self.sql('PRAGMA journal_mode=WAL')
        with self.assertRaisesRegex(BackendError,'unsupported'):self.query()

    def test_top_zero_is_existing_parser_rejection_empty_or_nonempty(self):
        for empty in (False,True):
            if empty:self.sql('DELETE FROM '+self.table())
            with patch.object(_View,'aggregate_catalog',side_effect=AssertionError('not reached')):
                with self.assertRaisesRegex(ValueError,'TOP outside supported bounds'):
                    self.query('SELECT TOP 0 COUNT(*) AS N FROM Catalog.Products')
    def test_invalid_provider_results_and_operation_fail_closed(self):
        for value in (-1,'3',True,10**30):
            with patch.object(_View,'aggregate_catalog',return_value=CatalogAggregateResult(value)):
                with self.assertRaises((BackendError,ValueError)):self.query()
        with closing(self.context.backend.begin_read()) as view:
            manager=self.vm._catalogs.get_index('Products')
            for request in (object(),CatalogAggregateRequest('raw SQL')):
                with self.assertRaisesRegex(BackendError,'invalid_input'):
                    view.aggregate_catalog(manager._schema.identity,request)
    def test_active_transaction_staged_write_declines_to_current_executor(self):
        from yadinassi import Interpreter
        from yadinassi.db.database_context import SQLiteDBContext
        from yadinassi.db.sqlite.sqlite_migration_plan import prepare,apply
        path=self.context.path;self.context.close()
        apply(path,prepare(path,maintenance=True),maintenance=True)
        self.context=SQLiteDBContext(path)
        self.vm=Interpreter(database_context=self.context,output=self.output.append)
        original=_View.aggregate_catalog;declines=[]
        def observe(view,*args):
            result=original(view,*args)
            if not view._cache_validation_allowed():declines.append(result)
            return result
        load=relational_queries._Plan.load;loads=[]
        def observed_load(plan,*args):
            loads.append(1);return load(plan,*args)
        with patch.object(_View,'aggregate_catalog',observe),patch.object(relational_queries._Plan,'load',observed_load):
            self.vm.execute('''BeginTransaction();P=Catalogs.Products.CreateItem();P.Code="4";P.Write();
Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Products");S=Q.Execute().Select();S.Next();Message(S.N);
Q=New Query("SELECT COUNT(Ref)+0 AS N FROM Catalog.Products WHERE 1=1 ORDER BY N");
S=Q.Execute().Select();S.Next();Message(S.N);RollbackTransaction();''')
        self.assertEqual(self.output,['4','4']);self.assertEqual(loads,[1,1]);self.assertTrue(all(item is None for item in declines))
        self.assertEqual(self.query()._rows,((Decimal(3),),))
    def test_failed_close_retires_new_count_proof(self):
        from test_sqlite_catalog_admission_cleanup import AdmissionFaultConnection
        backend=self.context.backend;manager=self.vm._catalogs.get_index('Products')
        view=backend.begin_read();view.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest())
        self.assertTrue(any(key[0]=='catalog-count-unique-v1' for key in view._validated_sources))
        proxy=AdmissionFaultConnection(view._connection,rollback_error=sqlite3.OperationalError('rollback'),close_error=sqlite3.OperationalError('close'))
        view._connection=proxy;backend._read_handle.connection=proxy
        try:
            with self.assertRaisesRegex(BackendError,'storage_error'):view.close()
            self.assertIsNone(backend._read_handle)
            with self.assertRaisesRegex(BackendError,'busy'):backend.begin_read()
        finally:proxy.disable_faults();view.close()
        with closing(backend.begin_read()) as fresh:
            self.assertFalse(any(key[0]=='catalog-count-unique-v1' for key in fresh._validated_sources))
            self.assertEqual(fresh.aggregate_catalog(manager._schema.identity,CatalogAggregateRequest()).count,3)
