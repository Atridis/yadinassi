"""Read-only detached metadata is not a database receiver grant."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from test_source_metadata import files
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_metadata import SourceMetadataRoot, SourceMetadataObject
from yadinassi.metadata import _DeclaredMetadataCollection
from yadinassi.runtime import Interpreter
from yadinassi.execution_policy import execution_backend_policy
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.errors import BSLError
from yadinassi.values import HostFunction

DENIED=(BoundaryViolation, BSLError, ValueError, TypeError)

class DetachedMetadataTests(unittest.TestCase):
    def setUp(self):
        scope=execution_backend_policy('python-direct');scope.__enter__();self.addCleanup(scope.__exit__,None,None,None)
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name));guard.start();self.addCleanup(guard.stop)
        self.out=[];self.vm=Interpreter(output=self.out.append);self.addCleanup(self.vm.close)
        self.root=SourceMetadataRoot(import_source(files()));self.vm.variables['md']=self.root
    def run_bsl(self,text):return self.vm.execute(text)
    def test_original_iteration_index_and_nested_get(self):
        self.assertEqual(self.run_bsl('n=0;For Each s In md.Subsystems Do n=n+1;EndDo;n'),Decimal(2))
        self.assertEqual(self.run_bsl('md.CommonModules["Helpers"].Name'),'Helpers')
        self.assertEqual(self.run_bsl('md.Subsystems.Get(0).Subsystems.Count()'),Decimal(1))
        self.assertEqual(self.run_bsl('md.Подсистемы.Получить(0).Имя'),'Features')
    def test_identity_and_empty_collection_survive_executions(self):
        a=self.run_bsl('md.Subsystems');b=self.run_bsl('md.Subsystems');self.assertIs(a,b)
        x=self.run_bsl('md.Subsystems.Find("Features")');self.assertIs(x,self.run_bsl('md.Subsystems.Get(0)'))
        self.assertIsNone(self.run_bsl('md.Subsystems.Find("Absent")'))
        self.assertEqual(self.run_bsl('md.Catalogs.Count()'),Decimal(0))
    def test_read_only_and_unknown_api(self):
        for text in ('md.Name="Other";','md.Subsystems[0]=Undefined;','md.Subsystems.Get(0).Name="Other";',
                     'md.Version','md.FindByFullName("Subsystem.Features")'):
            with self.subTest(text=text),self.assertRaises(DENIED):self.run_bsl(text)
        self.assertEqual(self.run_bsl('md.Name'),'Demo')
    def test_prepopulated_root_is_explicitly_outside_initial_admission(self):
        self.root.get_member('Subsystems')
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems.Count()')
    def test_foreign_collection_does_not_gain_admission(self):
        foreign=SourceMetadataRoot(import_source(files())).get_member('Subsystems')
        self.vm.variables['foreign']=foreign
        with self.assertRaises(DENIED):self.run_bsl('foreign.Count()')
        self.assertEqual(self.run_bsl('md.Subsystems.Count()'),Decimal(2))
    def test_forged_root_and_subclass_rejected(self):
        forged=object.__new__(SourceMetadataRoot);forged.__dict__.update(self.root.__dict__)
        self.vm.variables['md']=forged
        with self.assertRaises(DENIED):self.run_bsl('md.Name')
        class SubRoot(SourceMetadataRoot):pass
        self.vm.variables['md']=SubRoot(import_source(files()))
        with self.assertRaises(DENIED):self.run_bsl('md.Name')
    def test_constructed_source_cannot_bypass_xml_admission(self):
        from dataclasses import replace
        source=import_source(files())
        modified=tuple(replace(item,content=b'<!DOCTYPE x [<!ENTITY y "injected">]>'+item.content)
                       if item.path=='Configuration.xml' else item for item in source.files)
        self.vm.variables['md']=SourceMetadataRoot(replace(source,files=modified))
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems')
    def test_uuid_payload_mutation_rejected_before_comparison_callback(self):
        calls=[]
        class Evil:
            def __eq__(self,other):calls.append('eq');return False
            def __ne__(self,other):calls.append('ne');return True
        identity=self.root._entry.identity
        saved=identity.int
        try:
            object.__setattr__(identity,'int',Evil())
            with self.assertRaises(DENIED):self.run_bsl('md.Name')
            self.assertEqual(calls,[])
        finally:object.__setattr__(identity,'int',saved)
    def test_instance_dictionary_keys_rejected_without_equality_callback(self):
        calls=[]
        class Key:
            def __hash__(self):return hash('_root')
            def __eq__(self,other):calls.append('eq');return False
        self.root.__dict__[Key()]=0
        calls.clear()
        with self.assertRaises(DENIED):self.run_bsl('md.Name')
        self.assertEqual(calls,[])
    def test_origin_mutation_rejected(self):
        self.root._files=dict(self.root._files)
        with self.assertRaises(DENIED):self.run_bsl('md.Name')
    def test_noncanonical_cache_container_rejected_without_callback(self):
        calls=[]
        class Evil(dict):
            def items(self):calls.append('items');raise AssertionError('callback')
            def get(self,*args):calls.append('get');raise AssertionError('callback')
            def __iter__(self):calls.append('iter');raise AssertionError('callback')
        self.root._collections=Evil()
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems')
        self.assertEqual(calls,[])
    def test_tampered_xml_cache_rejected(self):
        self.run_bsl('md.Subsystems')
        self.root._xml.find('{http://v8.1c.ru/8.3/MDClasses}ChildObjects')[0].text='Other'
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems.Count()')
    def test_collection_replacement_and_foreign_child_rejected(self):
        original=self.run_bsl('md.Subsystems')
        self.root._collections['Subsystem']=_DeclaredMetadataCollection(tuple(original))
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems.Count()')
    def test_foreign_child_entry_rejected_before_path_hash_callback(self):
        from yadinassi.configuration_source import SourceMetadata
        calls=[]
        class Path:
            def __hash__(self):calls.append('hash');return 0
        collection=self.run_bsl('md.Subsystems')
        old=collection._items['features']
        entry=SourceMetadata(old._entry.identity,'Subsystem','Features',Path())
        collection._items['features']=SourceMetadataObject(self.root,entry)
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems.Count()')
        self.assertEqual(calls,[])
    def test_callback_mutation_denied_before_method_body(self):
        collection=self.run_bsl('md.Subsystems')
        def mutate():
            collection._items={}
            return Decimal(0)
        self.vm.functions['mutate']=HostFunction('Mutate',mutate)
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems.Get(Mutate())')
    def test_noncanonical_lookup_hooks_never_called(self):
        calls=[]
        with patch.object(SourceMetadataObject,'_collection',lambda *args:calls.append('called')):
            with self.assertRaises(DENIED):self.run_bsl('md.Subsystems')
        self.assertEqual(calls,[])
    def test_parser_factory_hook_never_called(self):
        from yadinassi import configuration_source_metadata as module
        calls=[]
        with patch.object(module.ET,'XMLPullParser',lambda *args,**kwargs:calls.append('factory')):
            with self.assertRaises(DENIED):self.run_bsl('md.Subsystems')
        self.assertEqual(calls,[])
    def test_graph_seal_does_not_keep_dropped_root_alive(self):
        import gc,weakref
        self.run_bsl('md.Subsystems')
        observed=weakref.ref(self.root)
        self.vm.variables.pop('md');self.root=None
        gc.collect()
        self.assertIsNone(observed())
    def test_namespace_constant_hooks_never_called(self):
        from yadinassi import configuration_source_metadata as module
        from yadinassi import configuration_source as admission
        calls=[]
        class Evil(str):
            def __radd__(self,left):calls.append('radd');return left+str(self)
        for target in (module,admission):
            with self.subTest(target=target.__name__),patch.object(target,'MD',Evil(target.MD)):
                with self.assertRaises(DENIED):self.run_bsl('md.Subsystems.Count()')
        self.assertEqual(calls,[])
    def test_family_table_keys_rejected_before_lookup_callback(self):
        from yadinassi import configuration_source_metadata as module
        calls=[];table=module._COLLECTIONS;saved=dict(table);key=next(iter(table))
        class Evil:
            def __hash__(self):return hash(key)
            def __eq__(self,other):calls.append('eq');return other==key
        try:
            value=table.pop(key);table[Evil()]=value;calls.clear()
            with self.assertRaises(DENIED):self.run_bsl('md.Name')
            self.assertEqual(calls,[])
        finally:table.clear();table.update(saved)
    def test_source_path_descriptor_hook_never_called(self):
        from pathlib import PurePosixPath
        calls=[]
        def suffix(value):calls.append('suffix');return '.xml'
        with patch.object(PurePosixPath,'suffix',property(suffix)):
            with self.assertRaises(DENIED):self.run_bsl('md.Name')
        self.assertEqual(calls,[])
    def test_parser_hook_never_called(self):
        from yadinassi import configuration_source_metadata as module
        calls=[]
        with patch.object(module.ET,'iterparse',lambda *args,**kwargs:calls.append('parser')):
            with self.assertRaises(DENIED):self.run_bsl('md.Subsystems')
        self.assertEqual(calls,[])
    def test_host_preloaded_child_not_accepted_after_adoption(self):
        self.assertEqual(self.run_bsl('md.Name'),'Demo')
        self.root.get_member('Subsystems')
        with self.assertRaises(DENIED):self.run_bsl('md.Subsystems.Count()')
    def test_saved_calls_and_iterators_expire_with_boundary(self):
        from yadinassi.python_direct_detached_metadata import DetachedMetadataBoundary
        from yadinassi.python_direct_database import CatalogBoundary
        from yadinassi.experimental_naked_boundaries import BoundaryContext
        class Context(DetachedMetadataBoundary,CatalogBoundary,BoundaryContext):pass
        ctx=Context();ctx.vm=self.vm;ctx.enter()
        collection=ctx.get_member(self.root,'Subsystems')
        count=ctx.resolve_member(collection,'Count')
        iterator=ctx.resolve_member(collection,'__iter__')()
        self.assertEqual(count(),Decimal(2));next(iterator)
        ctx.leave()
        with self.assertRaises(BoundaryViolation):count()
        with self.assertRaises(BoundaryViolation):next(iterator)
        ctx.enter()
        with self.assertRaises(BoundaryViolation):count()
        ctx.leave()
    def test_database_metadata_collection_not_granted(self):
        from yadinassi.metadata import BSLCatalogMetadataCollection
        # An exact foreign database class must not become detached merely because
        # it looks like another read-only metadata collection.
        forged=object.__new__(BSLCatalogMetadataCollection)
        self.vm.variables['foreign']=forged
        with self.assertRaises(DENIED):self.run_bsl('foreign.Count()')
    def test_detached_root_can_be_read_by_another_standalone_vm(self):
        child=self.run_bsl('md.Subsystems.Get(0)')
        other=Interpreter(output=lambda _:None);self.addCleanup(other.close);other.variables['md']=self.root
        self.assertIs(other.execute('md.Subsystems.Get(0)'),child)
        other.close()
        self.assertEqual(self.run_bsl('md.Subsystems.Count()'),Decimal(2))

if __name__=='__main__':unittest.main()
