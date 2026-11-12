"""Cross-surface navigation preserves exact owners and retires opaque epochs."""
from pathlib import Path
import tempfile
import unittest
from test_main_demo_configuration import source
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.database_launch import binding
from yadinassi.ui.main_demo_host import MainDemoHost, PROTOCOL
from yadinassi.ui.configuration_app import PROTOCOL as APP_PROTOCOL

class MainDemoHostTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/'demo.sqlite'
        self.config = import_main_demo_configuration(source(), profile=PROFILE)
        with SQLiteDBContext.create_main_demo(self.path, self.config) as context:
            self.expected = binding(context.backend.launch_snapshot())
        self.host = MainDemoHost(self.path, self.expected);self.addCleanup(self.host.close)

    def rpc(self, method, **params):
        return self.host.exchange({'jsonrpc':'2.0','id':1,'method':'demo.'+method,'params':params})['result']

    def test_switch_retains_database_binding_and_retires_epoch(self):
        old = self.host.epoch
        result = self.rpc('select', epoch=old, surface='documents')
        self.assertIsNone(result['error']);self.assertNotEqual(result['state']['epoch'],old)
        self.assertEqual(self.host.broker.posting_configuration,self.config)
        nested={'jsonrpc':'2.0','id':1,'method':'application.hello','params':{'protocol':APP_PROTOCOL}}
        self.assertIsNone(self.rpc('dispatch',epoch=self.host.epoch,request=nested)['payload']['result']['error'])
        self.assertEqual(self.rpc('dispatch',epoch=old,request=nested)['error'],'stale_surface')
        self.assertIsNone(self.rpc('select',epoch=self.host.epoch,surface='catalogs')['error'])
        self.assertEqual(binding(self.host.owner.backend.launch_snapshot()),self.expected)

    def test_original_product_form_refuses_empty_write_and_switch(self):
        product=next(c for c in self.config.catalogs if c.name=='Номенклатура')
        self.host.owner.select(str(product.identity));self.host.owner.open()
        editor=self.host.owner.editor
        self.assertIsNotNone(editor._source_record)
        self.host.owner.event('command',control='SaveButton')
        self.assertTrue(editor.object.is_new())
        self.assertEqual(self.rpc('select',epoch=self.host.epoch,surface='documents')['error'],'finish_current_surface')
        self.assertIs(self.host.owner.editor,editor)
        self.assertFalse(self.host.idle_close())

    def test_wrong_namespace_and_extra_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            self.rpc('dispatch',epoch=self.host.epoch,request={'method':'application.hello'})
        with self.assertRaises(ValueError):
            self.rpc('select',epoch=self.host.epoch,surface='documents',discard=True)
        self.assertEqual(self.host.surface,'catalogs')

    def test_document_open_fences_switch_without_implicit_close(self):
        self.rpc('select',epoch=self.host.epoch,surface='documents')
        def dispatch(method,**params):
            return self.rpc('dispatch',epoch=self.host.epoch,request={
                'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['payload']['result']
        dispatch('hello',protocol=APP_PROTOCOL)
        opened=dispatch('open',entry=1,request='one');self.assertIsNone(opened['error'])
        self.assertEqual(self.rpc('select',epoch=self.host.epoch,surface='catalogs')['error'],'finish_current_surface')
        self.assertIn(opened['session'],self.host.owner.sessions)

    def test_clean_close_retires_owner_and_snapshot_never_replays(self):
        epoch=self.host.epoch
        self.assertIsNone(self.rpc('close',epoch=epoch)['error'])
        state=self.rpc('snapshot',protocol=PROTOCOL)['state']
        self.assertEqual(state['kind'],'closed');self.assertIsNone(state['epoch'])
        self.assertIsNone(self.host.owner)

    def test_original_kind_change_handler_normalizes_and_survives_navigation(self):
        kind=next(c for c in self.config.catalogs if c.name=='ВидыНоменклатуры')
        owner=self.host.owner;owner.select(str(kind.identity));owner.open()
        owner.editor.change('InputData1',' x ')
        self.assertTrue(owner.editor.snapshot()['originalForm'])
        self.assertTrue(owner.editor.snapshot()['fieldMessages'])
        owner.editor.change('InputData1','  Материалы  ')
        owner.event('command',control='SaveButton')
        self.assertEqual(owner.editor.snapshot()['saveState'],'saved')
        owner.event('closeCard')
        self.assertIsNone(self.rpc('select',epoch=self.host.epoch,surface='documents')['error'])
        self.assertIsNone(self.rpc('select',epoch=self.host.epoch,surface='catalogs')['error'])
        self.host.owner.select(str(kind.identity))
        self.assertIn('Материалы',str(self.host.owner.snapshot()['state']['list']))

    def test_product_reference_sections_save_list_check_and_reopen_in_same_database(self):
        from yadinassi.ui.protocol import CatalogRef
        owner=self.host.owner
        kind=owner.catalogs.get_member('ВидыНоменклатуры').create_item()
        kind.set_member('Description','Товары');kind.write()
        warehouse=owner.catalogs.get_member('Склады').create_item()
        warehouse.set_member('Description','Основной');warehouse.write()
        def ref(obj):
            value=obj.get_member('Ref')
            return CatalogRef(str(value.value_type.metadata_uuid),str(value.reference_uuid))
        product=next(c for c in self.config.catalogs if c.name=='Номенклатура')
        owner.select(str(product.identity));owner.open();editor=owner.editor
        def change(name,value):
            field=next(f for f in editor.snapshot()['fields'] if f['name']==name)
            editor.change(field['control'],value)
        change('Description','  Кабель  ');change('ВидНоменклатуры',ref(kind))
        editor.row_event('addRow','Склады')
        row=editor.snapshot()['sections'][0]['rows'][0]['id']
        editor.row_event('changeRow','Склады',row,ref(warehouse))
        owner.event('command',control='SaveButton')
        self.assertEqual(editor.snapshot()['saveState'],'saved')
        record=ref(editor.object);owner.event('closeCard')
        owner.check_card(record)
        self.assertTrue(owner.snapshot()['state']['listCheck']['available'])
        self.assertIsNone(self.rpc('select',epoch=self.host.epoch,surface='documents')['error'])
        self.assertIsNone(self.rpc('select',epoch=self.host.epoch,surface='catalogs')['error'])
        self.host.owner.select(str(product.identity));self.host.owner.open(record)
        reopened=self.host.owner.editor.snapshot()
        self.assertEqual(next(f['inputText'] for f in reopened['fields'] if f['name']=='Description'),'Кабель')
        self.assertEqual(len(reopened['sections'][0]['rows']),1)

    def test_failed_cleanup_invalidates_epoch_without_reopening_or_replay(self):
        from unittest.mock import patch
        epoch=self.host.epoch;owner=self.host.owner
        original=owner.close
        def close_then_fail():
            original();raise OSError('cleanup failure')
        with patch.object(owner,'close',side_effect=close_then_fail), patch.object(self.host,'_activate') as activate:
            with self.assertRaises(OSError):self.rpc('select',epoch=epoch,surface='documents')
            activate.assert_not_called()
        state=self.rpc('snapshot',protocol=PROTOCOL)['state']
        self.assertTrue(state['uncertain']);self.assertFalse(state['canSwitch']);self.assertIsNone(state['epoch'])
        self.assertEqual(self.rpc('select',epoch=epoch,surface='documents')['error'],'stale_surface')

    def test_foreign_binding_never_opens_a_catalog_owner(self):
        with self.assertRaises(ValueError):MainDemoHost(self.path,self.expected+'changed')

    def test_failed_cleanup_before_close_is_retained_for_cleanup_only(self):
        from unittest.mock import patch
        owner=self.host.owner;epoch=self.host.epoch
        with patch.object(owner,'close',side_effect=OSError('before close')), patch.object(self.host,'_activate') as activate:
            with self.assertRaises(OSError):self.rpc('select',epoch=epoch,surface='documents')
            activate.assert_not_called()
        self.assertIsNone(self.host.owner);self.assertEqual(self.host._retired,[owner])
        self.assertFalse(owner.backend._closed)
        self.assertEqual(self.rpc('dispatch',epoch=epoch,request={'method':'editor.snapshot'})['error'],'stale_surface')
        self.host.close()
        self.assertTrue(owner.backend._closed);self.assertEqual(self.host._retired,[])
