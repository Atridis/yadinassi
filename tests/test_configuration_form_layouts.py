"""Nested configuration host contracts; deliberately not native GUI evidence."""
from copy import deepcopy
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_configuration_forms import sources, pair
from test_configuration_catalog_profile import catalog_form_sources
from document_form_fixture import sources as document_sources
from test_form_tables import active
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.type_values import type_by_name, type_of
from yadinassi.serialization import value_to_string_internal
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.configuration_xml import import_catalog_forms_configuration
from yadinassi.configuration_document_profile import import_document_forms_configuration
from yadinassi.form_layout import effective_state, install_layout
from yadinassi.form_model import BSLFormGroup
from yadinassi.form_replication import _pack_state, _unpack_state
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.form_app import FormController
from yadinassi.values import BSLType

PATH = 'CommonForms/Layout/Ext/Form.xml'
MODULE = 'CommonForms/Layout/Ext/Form/Module.bsl'


def layout_sources():
    return sources('layouts')


def wrap_controls(raw, before='<UsualGroup name="Container" id="100"><ChildItems>', after='</ChildItems></UsualGroup>'):
    head, body = raw.decode().split('<ChildItems>', 1)
    children, tail = body.split('</ChildItems>', 1)
    return (head + '<ChildItems>' + before + children + after + '</ChildItems>' + tail).encode()


class ConfigurationFormLayoutTests(unittest.TestCase):
    def definition(self, files=None):
        return load_configuration_forms(layout_sources() if files is None else files).resolve('CommonForm.Layout')

    def sessions(self, files=None):
        server, client = pair(self.definition(files))
        self.addCleanup(client.interpreter.close)
        self.addCleanup(server.session.interpreter.close)
        client.open()
        return server, client

    def test_group_nominal_type_bilingual_and_exact_on_both_replicas(self):
        server, client = self.sessions()
        for name in ('FormGroup', 'formgroup', 'ГруппаФормы', 'ГРУППАФОРМЫ'):
            self.assertIs(type_by_name(name), BSLType.FORM_GROUP)
        self.assertIs(type_of(BSLType.FORM_GROUP), BSLType.TYPE)
        for form in (server.session.form, client.form):
            for name in ('workspace', 'sections', 'identitypage', 'names', 'notespage', 'actions'):
                self.assertIs(type_of(form.items._values[name]), BSLType.FORM_GROUP)
            self.assertIs(type_of(form.items._values['firstnameinput']), BSLType.FORM_FIELD)
            self.assertIs(type_of(form.items._values['applyidentity']), BSLType.FORM_BUTTON)

    def test_bsl_server_can_inspect_items_by_group_type(self):
        files = layout_sources()
        files[MODULE] = files[MODULE].replace(b'Summary = FirstName + " " + LastName + ": " + Notes;', b'''Count = 0;
            For Each Item In Items Do
                If TypeOf(Item) = Type("FormGroup") Then Count = Count + 1; EndIf;
            EndDo;
            Summary = String(Count);''')
        _, client = self.sessions(files)
        client.dispatch('command', revision=client.revision, control='ApplyIdentity')
        self.assertEqual(client.form._data['summary'], '6')

    def test_bsl_client_group_type_lookup_and_presentation(self):
        files = layout_sources()
        files[MODULE] = files[MODULE].replace(b'Items.Names.ReadOnly = Not Items.Names.ReadOnly;',
            'If ТипЗнч(Items.Names) = Тип("группаформы") And TypeOf(Items.Names) <> Type("FormField") Then Summary = String(TypeOf(Items.Sections)); EndIf;'.encode())
        _, client = self.sessions(files)
        client.dispatch('command', revision=client.revision, control='ToggleNamesButton')
        self.assertEqual(client.form._data['summary'], 'ГруппаФормы')

    def test_nominal_group_does_not_authorize_constructor_or_dynamic_add(self):
        vm = Interpreter(); self.addCleanup(vm.close)
        for expression in ('New FormGroup', 'New ГруппаФормы', 'New (Type("FormGroup"))'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError): vm.execute(expression)
        server, client = pair(load_configuration_forms(sources('counter')).resolve('CommonForm.Counter'))
        self.addCleanup(server.session.interpreter.close); self.addCleanup(client.interpreter.close)
        client.open()
        with active(server.session):
            before = tuple(server.session.form.items._values)
            with self.assertRaises(TypeError): server.session.form.items.add('Group', BSLType.FORM_GROUP)
            self.assertEqual(tuple(server.session.form.items._values), before)

    def test_group_value_and_type_native_codecs_remain_explicitly_closed(self):
        server, _ = self.sessions()
        for value in (BSLType.FORM_GROUP, server.session.form.items._values['names']):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError): value_to_string_internal(value)

    def test_two_application_instances_keep_layout_and_summary_independent(self):
        from test_configuration_app import ConfigurationApplicationTests
        helper = ConfigurationApplicationTests(); self.addCleanup(helper.doCleanups)
        broker, app = helper.setup_app('layouts')
        first = helper.open(app, 'CommonForm.Layout', token='first')['session']
        def event(sid, kind, control, value=None):
            params = {'event': kind, 'revision': app.sessions[sid][0].session.revision, 'control': control}
            if kind == 'change': params['value'] = {'type': 'String', 'value': value}
            result = helper.rpc(app, 'form', session=sid,
                request={'jsonrpc': '2.0', 'id': 1, 'method': 'form.event', 'params': params})
            self.assertIsNone(result['error']); self.assertIsNone(result['form']['result']['error'])
            return result
        event(first, 'change', 'FirstNameInput', 'Ada')
        event(first, 'command', 'ApplyIdentity')
        event(first, 'command', 'ToggleNamesButton'); event(first, 'command', 'ToggleNamesButton')
        second = helper.open(app, 'CommonForm.Layout', token='second')['session']
        # Notes remains a renderer draft until after the first instance's visibility commands.
        event(first, 'command', 'ToggleNotesButton'); event(first, 'command', 'ToggleNotesButton')
        event(second, 'change', 'NotesInput', 'Sibling draft')
        event(second, 'command', 'ApplyNotes')
        for sessions in (app.sessions, broker.sessions):
            self.assertEqual(sessions[first][0].session.form._data['summary'], 'Ada : ')
            self.assertEqual(sessions[second][0].session.form._data['summary'], ' : Sibling draft')
            self.assertTrue(sessions[second][0].session.form.items._values['notespage'].visible)

    def test_example_order_and_closed_topology(self):
        definition = self.definition()
        self.assertEqual(len(definition.layout), 14)
        self.assertEqual(definition.layout[3], ('Names', 'IdentityPage', 'group', 'horizontal', True))
        self.assertEqual(definition.layout[-1], ('SummaryLabel', '', 'control', 'vertical', True))

    def test_parent_and_client_are_detached(self):
        server, client = self.sessions()
        self.assertIsNot(server.session.form.items._values['names'], client.form.items._values['names'])
        self.assertEqual(server.session.form._layout, client.form._layout)

    def test_group_available_during_create_and_open(self):
        files = layout_sources()
        files[PATH] = files[PATH].replace(b'</Form>', b'<Events><Event name="OnCreateAtServer">Created</Event><Event name="OnOpen">Opened</Event></Events></Form>')
        files[MODULE] += b'\n&AtServer\nProcedure Created(Cancel, StandardProcessing) Items.Names.Title="Server title"; EndProcedure\n&AtClient\nProcedure Opened(Cancel) Summary=Items.Names.Title; EndProcedure'
        _, client = self.sessions(files)
        self.assertEqual(client.form._data['summary'], 'Server title')

    def test_readonly_inherits_without_overwriting_child_properties(self):
        _, client = self.sessions()
        group = client.form.items._values['names']; field = client.form.items._values['firstnameinput']
        client.dispatch('command', revision=client.revision, control='ToggleNamesButton')
        self.assertTrue(group.read_only); self.assertFalse(field.read_only)
        self.assertEqual(effective_state(field), (True, True, True))
        with self.assertRaises(ValueError): client.dispatch('change', revision=client.revision, control=field.name, value='blocked')
        client.dispatch('command', revision=client.revision, control='ToggleNamesButton')
        self.assertEqual(effective_state(field), (True, True, False))

    def test_visibility_and_enabled_derive_each_ancestor(self):
        _, client = self.sessions()
        group = client.form.items._values['workspace']; field = client.form.items._values['firstnameinput']
        group.visible = False; group.enabled = False
        self.assertEqual(effective_state(field), (False, False, False))
        self.assertTrue(field.visible); self.assertTrue(field.enabled)
        group.visible = True; group.enabled = True; field.enabled = False
        self.assertEqual(effective_state(field), (True, False, False))

    def test_parent_restriction_blocks_command_without_running_bsl(self):
        _, client = self.sessions()
        group = client.form.items._values['workspace']
        for prop, value in [('visible', False), ('enabled', False), ('read_only', True)]:
            with self.subTest(prop=prop):
                setattr(group, prop, value)
                with self.assertRaises(ValueError): client.dispatch('command', revision=client.revision, control='ApplyIdentity')
                self.assertEqual(client.form._data['summary'], '')
                setattr(group, prop, not value)

    def test_group_cannot_receive_renderer_events(self):
        _, client = self.sessions()
        for event in ('change', 'command', 'select'):
            with self.subTest(event=event), self.assertRaises(ValueError):
                client.dispatch(event, revision=client.revision, control='Names', value='x')

    def test_bsl_own_property_reads_survive_group_toggle(self):
        files = layout_sources()
        files[MODULE] = files[MODULE].replace(b'Items.Names.ReadOnly = Not Items.Names.ReadOnly;', b'Items.Names.ReadOnly = True; Summary = String(Items.FirstNameInput.ReadOnly);')
        _, client = self.sessions(files)
        client.dispatch('command', revision=client.revision, control='ToggleNamesButton')
        self.assertIn(client.form._data['summary'], ('No', 'False', 'Нет', 'Ложь'))

    def test_appearance_roundtrip_replicates_own_not_effective_flags(self):
        server, client = self.sessions()
        client.dispatch('command', revision=client.revision, control='ToggleNamesButton')
        client.dispatch('command', revision=client.revision, control='ApplyIdentity')
        field = server.session.form.items._values['firstnameinput']
        self.assertFalse(field.read_only); self.assertTrue(effective_state(field)[2])
        self.assertTrue(client.form.items._values['names'].read_only)

    def test_dynamic_schema_changes_fail_closed(self):
        server, _ = self.sessions()
        with active(server.session):
            with self.assertRaises(ValueError): server.session.form.items.add('New', BSLType.FORM_FIELD)
            with self.assertRaises(ValueError): server.session.form.items.delete(server.session.form.items._values['firstnameinput'])
            with self.assertRaises(ValueError): server.session.form.items._values['names'].set_member('CurrentPage', 'NotesPage')
            with self.assertRaises(ValueError): server.session.form.items._values['names'].get_member('DataPath')

    def test_flat_programmatic_model_unchanged(self):
        server, client = pair(load_configuration_forms(sources('counter')).resolve('CommonForm.Counter'))
        self.addCleanup(server.session.interpreter.close); self.addCleanup(client.interpreter.close)
        client.open(); self.assertEqual(client.form._layout, ())
        with active(server.session): self.assertEqual(server.session.form.items.add('Extra', BSLType.FORM_FIELD).name, 'Extra')

    def test_flat_legacy_button_dispatch_readonly_semantics_unchanged(self):
        server, client = pair(load_configuration_forms(sources('counter')).resolve('CommonForm.Counter'))
        self.addCleanup(server.session.interpreter.close); self.addCleanup(client.interpreter.close)
        client.open(); client.form.items._values['incrementbutton'].read_only = True
        client.dispatch('command', revision=client.revision, control='IncrementButton')
        self.assertEqual(client.form._data['count'], 1)

    def test_unknown_nested_behavior_is_not_ignored(self):
        for fragment in ('<AutoSave>true</AutoSave>', '<Events/>', '<CurrentPage>NotesPage</CurrentPage>', '<DataPath>FirstName</DataPath>'):
            files = layout_sources(); files[PATH] = files[PATH].replace(b'<Title>Name</Title>', ('<Title>Name</Title>' + fragment).encode())
            with self.subTest(fragment=fragment), self.assertRaises(ValueError): self.definition(files)

    def test_duplicate_name_across_pages_rejected(self):
        files = layout_sources(); files[PATH] = files[PATH].replace(b'name="NotesInput"', b'name="FIRSTNAMEINPUT"')
        with self.assertRaises(ValueError): self.definition(files)

    def test_duplicate_id_across_pages_rejected(self):
        files = layout_sources(); files[PATH] = files[PATH].replace(b'id="9"', b'id="5"')
        with self.assertRaises(ValueError): self.definition(files)

    def test_page_outside_pages_rejected(self):
        files = layout_sources(); files[PATH] = files[PATH].replace(b'<UsualGroup name="Names"', b'<Page name="Names"').replace(b'</ChildItems></UsualGroup>', b'</ChildItems></Page>', 1)
        with self.assertRaises(ValueError): self.definition(files)

    def test_nonpage_in_pages_rejected(self):
        files = layout_sources(); files[PATH] = files[PATH].replace(b'<Page name="NotesPage"', b'<UsualGroup name="NotesPage"').replace(b'</ChildItems></Page>', b'</ChildItems></UsualGroup>')
        with self.assertRaises(ValueError): self.definition(files)

    def test_empty_pages_rejected(self):
        files = sources('counter'); key = 'CommonForms/Counter/Ext/Form.xml'
        files[key] = files[key].replace(b'<ChildItems>', b'<ChildItems><Pages name="Empty" id="100"/>', 1)
        with self.assertRaises(ValueError): load_configuration_forms(files)

    def test_unmeasured_presentation_variants_rejected(self):
        for old, new in [(b'<Group>Horizontal</Group>', b'<Group>HorizontalIfPossible</Group>'), (b'TabsOnTop', b'TabsOnBottom')]:
            files = layout_sources(); files[PATH] = files[PATH].replace(old, new)
            with self.subTest(new=new), self.assertRaises(ValueError): self.definition(files)

    def test_depth_limit_enforced_without_recursive_overflow(self):
        files = sources('counter'); key = 'CommonForms/Counter/Ext/Form.xml'
        for i in range(8): files[key] = wrap_controls(files[key], f'<UsualGroup name="G{i}" id="{100+i}"><ChildItems>')
        with self.assertRaisesRegex(ValueError, 'depth'): load_configuration_forms(files)

    def test_total_item_limit_not_per_group(self):
        files = sources('counter'); key = 'CommonForms/Counter/Ext/Form.xml'
        children = ''.join(f'<InputField name="F{i}" id="{i+100}"><DataPath>Count</DataPath></InputField>' for i in range(126))
        files[key] = files[key].replace(b'<ChildItems>', ('<ChildItems><UsualGroup name="Many" id="900"><ChildItems>'+children+'</ChildItems></UsualGroup>').encode(), 1)
        with self.assertRaises(ValueError): load_configuration_forms(files)

    def test_layout_changes_full_source_identity(self):
        files = layout_sources(); before = load_configuration_forms(files)
        files[PATH] = files[PATH].replace(b'<Group>Horizontal</Group>', b'<Group>Vertical</Group>')
        after = load_configuration_forms(files)
        self.assertNotEqual(before.source_sha256, after.source_sha256)
        self.assertNotEqual(before.resolve('CommonForm.Layout').source_sha256, after.resolve('CommonForm.Layout').source_sha256)

    def test_malformed_replica_topology_is_atomic(self):
        server, client = self.sessions(); packet = _pack_state(server.session, server._handler_names)
        original = client.form._layout
        mutations = [lambda p: p['layout'][0].__setitem__(1, 'Names'), lambda p: p['layout'].pop(),
                     lambda p: p['layout'][3].__setitem__(2, 'control'), lambda p: p.pop('layout'),
                     lambda p: p['layout'][4].__setitem__(1, 'NAMES'), lambda p: p['items'].reverse()]
        for mutate in mutations:
            candidate = deepcopy(packet); mutate(candidate)
            with self.subTest(candidate=candidate['items'][0][0]), self.assertRaises(ValueError): _unpack_state(candidate, client, client._handlers)
            self.assertEqual(client.form._layout, original)

    def test_reparented_replica_cannot_change_declared_topology(self):
        server, client = self.sessions(); packet = _pack_state(server.session, server._handler_names)
        packet['layout'][4][1] = 'IdentityPage'
        with self.assertRaisesRegex(ValueError, 'immutable'): _unpack_state(packet, client, client._handlers)

    def test_group_replica_cannot_bind_event_or_data(self):
        server, client = self.sessions()
        for index, value in ((6, 'FirstName'), (7, 1), (8, 'LabelField')):
            packet = _pack_state(server.session, server._handler_names); packet['items'][0][index] = value
            with self.subTest(index=index), self.assertRaises(ValueError): _unpack_state(packet, client, client._handlers)

    def test_controller_exports_effective_flags_and_closed_layout(self):
        definition = self.definition(); server = definition.create_server()
        controller = FormController(definition.client_package(), server.exchange)
        self.addCleanup(server.session.interpreter.close); self.addCleanup(controller.session.interpreter.close)
        controller.session.open(); controller.session.form.items._values['workspace'].enabled = False
        snapshot = controller._snapshot(); group, pages, page, names, field = snapshot['items'][:5]
        self.assertEqual(group['kind'], 'group'); self.assertEqual(names['orientation'], 'horizontal')
        self.assertEqual(page['layoutKind'], 'page'); self.assertEqual(field['parent'], 'Names')
        self.assertFalse(field['enabled']); self.assertTrue(controller.session.form.items._values['firstnameinput'].enabled)
        self.assertNotIn('currentPage', pages); self.assertNotIn('action', pages)

    def test_nested_document_table_and_command_admission(self):
        files = document_sources(); key = 'Documents/Orders/Forms/Card/Ext/Form.xml'; files[key] = wrap_controls(files[key])
        imported = import_document_forms_configuration(files)
        definition = load_configuration_forms(files, document_schemas=imported.documents).resolve('Document.Orders.Form.Card')
        server, client = pair(definition); self.addCleanup(server.session.interpreter.close); self.addCleanup(client.interpreter.close)
        client.open(); self.assertEqual(client.form._layout[2][:3], ('LinesTable', 'Container', 'control'))
        client.form.items._values['container'].enabled = False
        with self.assertRaises(ValueError): client.dispatch('select', revision=client.revision, control='LinesTable', row=None)

    def test_catalog_profile_keeps_complete_source_and_no_legacy_grant(self):
        files = catalog_form_sources(); key = 'Catalogs/Items/Forms/Card/Ext/Form.xml'; files[key] = wrap_controls(files[key])
        config = import_catalog_forms_configuration(files)
        self.assertEqual({file.path:file.content for file in config.files}, files)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'layout.sqlite'
            with closing(SQLiteCatalogBackend.create_catalog_forms(path, files)) as backend:
                self.assertEqual(backend.export_configuration(), files); self.assertEqual(backend.active_form_catalogs(), ())
            changed = files[key].replace(b'Container', b'OtherName')
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (changed, sha256(changed).hexdigest(), key))
            with self.assertRaises(BackendError): SQLiteCatalogBackend(path)

    def test_reference_choice_obeys_ancestor_restrictions(self):
        from test_configuration_reference_choice import PickerTests
        # Reuse only fixture setup, not a test case or a native acquisition.
        fixture = PickerTests(); fixture.setUp()
        self.addCleanup(fixture.server.session.interpreter.close); self.addCleanup(fixture.client.interpreter.close)
        form = fixture.server.session.form; group = BSLFormGroup(form, 'Container')
        form.items._values = {'container': group, **form.items._values}
        install_layout(form, [('Container','','group','vertical',True), ('ProductField','Container','control','vertical',True), ('LinesTable','Container','control','vertical',True)])
        for attribute, value in [('visible', False), ('enabled', False), ('read_only', True)]:
            setattr(group, attribute, value)
            with self.subTest(attribute=attribute), self.assertRaises(ValueError): fixture.begin()
            setattr(group, attribute, not value)
        self.assertEqual(fixture.views_closed, 0)
