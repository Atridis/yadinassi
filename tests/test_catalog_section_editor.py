"""Reference-row UI saves owned SQLite data; no original form/native parity."""
import json
from unittest.mock import patch
import unittest
from uuid import uuid4

import test_catalog_object_preparation as fixture
from yadinassi.catalog_backend import BackendError
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import _View
from yadinassi.ui.catalog_editor import CatalogEditorApplication
from yadinassi.ui.editor_protocol import CatalogEditorSession, validate_request
from yadinassi.ui.protocol import CatalogRef, UIError


class CatalogSectionEditorTests(unittest.TestCase):
    def setUp(self):
        fixture.CatalogObjectPreparationTests.setUp(self)
        self.card.write()
        self.app = CatalogEditorApplication(self.context)
        self.addCleanup(self.app.close)
        self.catalog = str(self.card._key.catalog_id)
        self.reference = CatalogRef(self.catalog, str(self.card._key.record_id))
        self.app.select(self.catalog)
        self.app.open(self.reference)
        self.editor = self.app.editor
        self.warehouse = self.vm.variables['склад'].get_member('Ref')
        self.choice = CatalogRef(str(self.warehouse.value_type.metadata_uuid), str(self.warehouse.reference_uuid))

    def section(self): return self.editor.snapshot()['sections'][0]
    def event(self, event, **values): self.app.event(event, section='Склады', **values)
    def save(self): self.app.event('command', control='SaveButton')
    def stored(self):
        view = self.context.backend.begin_read()
        try: return view.read_catalog(self.card._key)
        finally: view.close()

    def test_row_only_add_select_save_reopen(self):
        self.event('addRow')
        row = self.section()['rows'][-1]
        self.event('changeRow', row=row['id'], value=self.choice)
        self.save()
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertFalse(self.editor.snapshot()['dirty'])
        self.assertEqual(len(self.stored().tabular_sections[0].rows), 2)
        context = SQLiteDBContext(self.context.path)
        self.addCleanup(context.close)
        app = CatalogEditorApplication(context)
        app.select(self.catalog); app.open(self.reference)
        rows = app.editor.snapshot()['sections'][0]['rows']
        self.assertEqual(rows[-1]['id'], row['id'])
        self.assertEqual(rows[-1]['field']['value']['record'], self.choice.record)

    def test_delete_renumbers_preserving_remaining_identity(self):
        first = self.section()['rows'][0]['id']
        self.event('addRow'); second = self.section()['rows'][1]['id']
        self.event('deleteRow', row=first)
        self.assertEqual([(r['id'], r['number']) for r in self.section()['rows']], [(second, 1)])
        self.save()
        self.assertEqual(str(self.stored().tabular_sections[0].rows[0].identity), second)

    def test_dirty_close_and_discard_do_not_write(self):
        before = self.stored()
        self.event('addRow'); self.app.event('closeCard')
        self.assertIsNotNone(self.app.editor)
        self.app.event('command', control='CancelButton')
        self.assertIsNone(self.app.editor)
        self.assertEqual(self.stored(), before)

    def test_invalid_row_target_and_value_are_atomic(self):
        before = self.editor.snapshot()
        row = self.section()['rows'][0]['id']
        for event, args in [('deleteRow', {'row':str(uuid4())}),
                            ('changeRow', {'row':row,'value':self.choice.record}),
                            ('changeRow', {'row':row,'value':CatalogRef(self.catalog,self.choice.record)}),
                            ('changeRow', {'row':row,'value':CatalogRef(self.choice.catalog,str(uuid4()))})]:
            with self.subTest(event=event), self.assertRaises(UIError): self.event(event, **args)
            self.assertEqual(self.editor.snapshot(), before)

    def test_deleted_row_identity_cannot_retarget_next_row(self):
        first = self.section()['rows'][0]['id']
        self.event('addRow'); self.event('deleteRow', row=first)
        before = self.editor.snapshot()
        with self.assertRaises(UIError): self.event('changeRow', row=first, value=self.choice)
        self.assertEqual(self.editor.snapshot(), before)

    def test_message_budget_rejects_before_mutation(self):
        before = self.editor.snapshot()
        with patch('yadinassi.ui.catalog_editor.MAX_LINE_BYTES', 1):
            with self.assertRaises(UIError): self.event('addRow')
        self.assertEqual(self.editor.snapshot(), before)

    def test_row_limit_rejects_without_losing_existing_rows(self):
        with patch('yadinassi.ui.catalog_editor.MAX_SECTION_ROWS', 2):
            self.event('addRow')
            before = self.editor.snapshot()
            self.assertFalse(self.section()['canAdd'])
            with self.assertRaises(UIError): self.event('addRow')
            self.assertEqual(self.editor.snapshot(), before)

    def test_repeated_save_does_not_rewrite_rows(self):
        self.event('addRow'); self.save(); before = self.stored()
        with patch.object(_View, 'update', side_effect=AssertionError('duplicate write')): self.save()
        self.assertEqual(self.editor.save_state, 'unchanged')
        self.assertEqual(self.stored(), before)

    def test_conflict_preserves_rows_and_original_revision(self):
        self.event('addRow')
        other = self.card.get_member('Ref'); other = other.get_object(other)
        other.set_member('Description', 'other'); other.write()
        self.save()
        self.assertEqual(self.editor.error, 'conflict')
        self.assertTrue(self.editor.snapshot()['dirty'])
        self.assertEqual(len(self.section()['rows']), 2)
        self.assertEqual(len(self.stored().tabular_sections[0].rows), 1)

    def test_uncertain_committed_locks_all_row_actions_and_resolves_once(self):
        self.event('addRow')
        original = _View.commit
        def lost(tx): original(tx); raise BackendError('uncertain_commit')
        with patch.object(_View, 'commit', lost): self.save()
        for event, args in [('addRow', {}), ('deleteRow', {'row':self.section()['rows'][0]['id']}),
                            ('changeRow', {'row':self.section()['rows'][0]['id'],'value':self.choice})]:
            with self.assertRaises(UIError): self.event(event, **args)
        with patch.object(_View, 'commit', side_effect=AssertionError('second write')): self.save()
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertEqual(len(self.stored().tabular_sections[0].rows), 2)

    def test_uncertain_absent_retries_same_rows(self):
        self.event('addRow'); identities = [r['id'] for r in self.section()['rows']]
        with patch.object(_View, 'commit', side_effect=BackendError('uncertain_commit')): self.save()
        self.save()
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertEqual([str(r.identity) for r in self.stored().tabular_sections[0].rows], identities)

    def test_refresh_size_failure_keeps_old_revision_and_refresh_only_lock(self):
        self.event('addRow'); revision = self.editor.object._revision
        with patch.object(self.editor, '_check_size', side_effect=UIError('message_limit')): self.save()
        self.assertTrue(self.editor.pending_refresh)
        self.assertEqual(self.editor.error, 'refresh_required')
        with self.assertRaises(UIError): self.event('addRow')
        with patch.object(_View, 'commit', side_effect=AssertionError('second write')): self.save()
        self.assertFalse(self.editor.pending_refresh)
        self.assertNotEqual(self.editor.object._revision, revision)

    def test_marked_current_reference_is_readonly_but_deletable(self):
        warehouse = self.vm.variables['склад']; warehouse.set_member('DeletionMark', True); warehouse.write()
        self.app.event('closeCard'); self.app.open(self.reference); self.editor = self.app.editor
        row = self.section()['rows'][0]
        self.assertTrue(row['field']['readOnly'])
        with self.assertRaises(UIError): self.event('changeRow', row=row['id'], value=self.choice)
        self.event('deleteRow', row=row['id']); self.save()
        self.assertEqual(self.stored().tabular_sections[0].rows, ())

    def test_protocol_row_events_are_typed_and_revision_guarded(self):
        session = CatalogEditorSession(self.app)
        def request(i, method, params):
            return json.loads(session.exchange(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params}).encode('utf-8')))
        request(1,'editor.hello',{'protocol':'yadinassi-editor/0'})
        result=request(2,'editor.event',{'event':'addRow','section':'Склады','baseRevision':0})
        self.assertIn('result',result)
        result=request(3,'editor.event',{'event':'addRow','section':'Склады','baseRevision':0})
        self.assertEqual(result['error']['data']['reason'],'stale_revision')
        self.assertEqual(len(self.section()['rows']),2)
        with self.assertRaises(UIError):
            validate_request({'jsonrpc':'2.0','id':4,'method':'editor.event','params':{
                'event':'deleteRow','section':'Склады','row':0,'baseRevision':1}})

    def test_protocol_accepts_admitted_unicode_section_names(self):
        name = 'С' * 128
        request = {'jsonrpc':'2.0','id':1,'method':'editor.event','params':{
            'event':'addRow','section':name,'baseRevision':0}}
        self.assertIs(validate_request(request), request)

    def test_existing_overlimit_sections_remain_readonly_and_preserved(self):
        self.vm.execute('Карточка.Склады.Добавить(); Карточка.Записать();')
        self.app.event('closeCard')
        with patch('yadinassi.ui.catalog_editor.MAX_SECTION_ROWS', 1):
            self.app.open(self.reference); self.editor = self.app.editor
            section = self.section()
            self.assertTrue(section['readOnly'])
            self.assertEqual(section['rowCount'], 2)
            self.assertEqual(section['rows'], [])
            with self.assertRaises(UIError): self.event('addRow')
            field = next(f for f in self.editor.snapshot()['fields'] if f['name']=='Description')
            self.app.event('change', control=field['control'], value='changed')
            self.save()
            self.assertEqual(self.editor.save_state, 'saved')
            self.assertEqual(len(self.stored().tabular_sections[0].rows), 2)

    def test_unsupported_sections_are_preserved_on_scalar_save(self):
        from pathlib import Path
        from catalog_sections_fixture import configuration_files_with_sections
        from yadinassi.configuration_xml import import_configuration
        from yadinassi import Interpreter
        context = SQLiteDBContext.create(Path(self.temp.name)/'mixed.sqlite',
            import_configuration(configuration_files_with_sections()))
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context); self.addCleanup(vm.close)
        vm.execute('O=Catalogs.Products.CreateItem(); O.Code="1"; R=O.Notes.Add(); R.Text="Keep"; O.Write();')
        obj = vm.variables['o']; identity = str(obj._key.catalog_id)
        app = CatalogEditorApplication(context)
        app.select(identity); app.open(CatalogRef(identity,str(obj._key.record_id)))
        sections = app.editor.snapshot()['sections']
        self.assertTrue(all(s['readOnly'] for s in sections))
        self.assertEqual(sections[1]['rowCount'],1)
        field = next(f for f in app.editor.snapshot()['fields'] if f['name']=='Description')
        app.event('change', control=field['control'], value='Updated')
        app.event('command', control='SaveButton')
        self.assertEqual(app.editor.save_state, 'saved')
        self.assertEqual(vm.execute('O.Ref.GetObject().Notes[0].Text'),'Keep')

    def test_new_record_with_reference_row_is_saved_once(self):
        self.app.event('closeCard'); self.app.event('create'); self.editor = self.app.editor
        code = next(f for f in self.editor.snapshot()['fields'] if f['name']=='Code')
        self.app.event('change', control=code['control'], value='2')
        self.event('addRow'); row = self.section()['rows'][0]['id']
        self.event('changeRow', row=row, value=self.choice); self.save()
        self.assertFalse(self.editor.object.is_new())
        self.assertEqual(self.editor.save_state, 'saved')
        reference = self.editor.snapshot()['reference']
        self.app.event('closeCard')
        self.app.open(CatalogRef(reference['catalog'], reference['record']))
        self.assertEqual(self.app.editor.snapshot()['sections'][0]['rows'][0]['id'], row)


    def test_node_budget_rejects_row_before_adoption(self):
        from yadinassi.ui.protocol import encode_line
        before = self.editor.snapshot()
        def nodes(value):
            if isinstance(value, dict): return 1 + sum(nodes(k) + nodes(v) for k, v in value.items())
            if isinstance(value, (tuple, list)): return 1 + sum(nodes(v) for v in value)
            return 1
        candidate = self.editor.sections.changed('addRow', 'Склады')
        prospective = self.editor.snapshot(sections=candidate)
        # The bare editor still fits. Only complete-envelope preflight rejects.
        with patch('yadinassi.ui.protocol.MAX_NODES', nodes(prospective) + 20):
            encode_line(prospective)
            with self.assertRaises(UIError): self.event('addRow')
        self.assertEqual(self.editor.snapshot(), before)
