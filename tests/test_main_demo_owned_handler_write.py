"""Ordinary source policy is consumed after the one actual writer admits it."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

import test_main_demo_runtime as support
from yadinassi.db.catalog import catalog_object_preparation as preparation
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite import sqlite_inventory_enum_profile as profile
from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier


class MainDemoOwnedHandlerWriteTests(unittest.TestCase):
    def setUp(self):
        fixture = support.MainDemoRuntimeTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.vm = fixture.vm
        self.path = fixture.path
        self.backend = fixture.context.backend
        self.vm.execute(support.SEED)
        self.card = self.vm.variables['карточка']
        self.table = quote_identifier(self.backend._layout.table_name(self.card._key.catalog_id))

    def published(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute('SELECT revision,description FROM '+self.table).fetchone()

    def test_original_handler_runs_after_fresh_and_only_admission(self):
        connections, verified = [], []
        connect, read_source = self.backend._connect, profile.read_source
        original = preparation._prepare_catalog_object

        def tracked_connect(*args, **kwargs):
            conn = connect(*args, **kwargs)
            trace = []
            conn.set_trace_callback(trace.append)
            connections.append((conn, trace))
            return conn

        def tracked_source(conn, *args, **kwargs):
            source = read_source(conn, *args, **kwargs)
            verified.append(conn)
            return source

        def handler(source, receiver, **kwargs):
            self.assertIs(receiver, self.card)
            writer = kwargs['write_view']
            self.assertEqual(verified, [writer._connection])
            self.assertIs(self.backend._active, writer)
            self.assertTrue(writer._connection.in_transaction)
            self.assertIn('BEGIN IMMEDIATE', connections[0][1])
            self.assertFalse(any(sql.startswith('UPDATE '+self.table) for sql in connections[0][1]))
            self.assertIn('ПередЗаписью',source)
            return original(source, receiver, **kwargs)

        self.card.set_member('Description','  Новый кабель  ')
        with patch.object(self.backend,'_connect',side_effect=tracked_connect), \
             patch.object(profile,'read_source',side_effect=tracked_source), \
             patch.object(preparation,'_prepare_catalog_object',side_effect=handler) as prepare:
            self.vm.execute('Карточка.Записать();')
        prepare.assert_called_once()
        self.assertEqual(len(connections),1)
        self.assertEqual(self.published(), (2,'Новый кабель'))
        warehouse = self.vm.variables['склад']._key
        warehouse_table = quote_identifier(self.backend._layout.table_name(warehouse.catalog_id))
        self.assertTrue(any('FROM '+warehouse_table in sql and str(warehouse.record_id) in sql
                            for sql in connections[0][1]),connections[0][1])
        self.assertIsNone(self.backend._active)

    def test_schema_and_source_changes_refuse_before_handler(self):
        before = self.published()
        self.card.set_member('Description', 'Must not persist')
        with closing(sqlite3.connect(self.path)) as conn:
            for table, col, key_col, key, replacement in (
                    ('configuration_file','sha256','path','Configuration.xml','0'*64),
                    ('catalog_schema','name','identity',str(self.card._key.catalog_id),'Wrong name')):
                with self.subTest(table=table):
                    value, = conn.execute(f'SELECT {col} FROM {table} WHERE {key_col}=?',(key,)).fetchone()
                    conn.execute(f'UPDATE {table} SET {col}=? WHERE {key_col}=?',(replacement,key))
                    conn.commit()
                    with patch.object(preparation,'_prepare_catalog_object') as handler,self.assertRaises(BackendError):
                        self.card.write()
                    handler.assert_not_called()
                    self.assertIsNone(self.backend._active)
                    self.assertEqual(self.published(),before)
                    conn.execute(f'UPDATE {table} SET {col}=? WHERE {key_col}=?',(value,key))
                    conn.commit()
        self.card.write()
        self.assertEqual(self.published(), (2,'Must not persist'))

    def test_late_in_memory_source_replacement_is_not_handler_authority(self):
        from dataclasses import replace
        from hashlib import sha256
        from yadinassi.db.sqlite.sqlite_catalog import _View

        config = self.backend.accumulation_configuration
        identity, path, digest = next(grant for grant in config.catalog_handlers
                                     if grant[0] == self.card._key.catalog_id)
        changed = 'Процедура ПередЗаписью(Отказ) КонецПроцедуры'.encode()
        forged = replace(config,
            catalog_handlers=tuple((i,p,sha256(changed).hexdigest()) if i==identity else (i,p,h)
                                   for i,p,h in config.catalog_handlers),
            files=tuple((p,changed if p==path else raw) for p,raw in config.files))
        original = _View.catalog_schema
        self.addCleanup(setattr,self.backend,'accumulation_configuration',config)
        def late(writer, catalog_id):
            answer = original(writer,catalog_id)
            if (writer._backend is self.backend and writer._operation_id is not None
                    and self.backend._active is writer and catalog_id==identity):
                self.backend.accumulation_configuration = forged
            return answer

        before = self.published()
        self.card.set_member('Description', 'Not persisted')
        with patch.object(_View,'catalog_schema',late), \
             patch.object(preparation,'_prepare_catalog_object') as handler,self.assertRaises(BackendError):
            self.card.write()
        handler.assert_not_called()
        self.assertEqual(self.published(),before)
        self.assertIsNone(self.backend._active)

    def test_custom_policy_and_explicit_source_keep_the_existing_lookup(self):
        policy = self.backend.catalog_write_preparation
        select = self.backend._main_demo_write_source
        self.card.set_member('Description', 'Via custom policy')
        with patch.object(self.backend,'catalog_write_preparation',wraps=policy) as custom, \
             patch.object(self.backend,'_main_demo_write_source',wraps=select) as lookup:
            self.card.write()
        custom.assert_called_once_with(self.card._key.catalog_id)
        lookup.assert_called_once()
        self.assertEqual(self.published(), (2,'Via custom policy'))

        source = policy(self.card._key.catalog_id)
        self.card.set_member('Description', 'Via explicit source')
        with patch.object(self.backend,'_main_demo_write_source',wraps=select) as lookup:
            self.card._write(preparation=(source,False))
        lookup.assert_called_once()
        self.assertEqual(self.published(), (3,'Via explicit source'))
