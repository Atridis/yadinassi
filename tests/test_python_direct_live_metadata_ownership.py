"""Independent live metadata provenance and callback-boundary regressions."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from yadinassi import Interpreter,BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.configuration import metadata
import test_configuration_metadata_graph as fixture

DENIED=(BoundaryViolation,BSLRuntimeError,ValueError,TypeError)

class MetadataShellOwnershipTests(unittest.TestCase):
    def test_no_database_shells_are_inert_and_local(self):
        vm, other = Interpreter(), Interpreter()
        self.addCleanup(vm.close)
        self.addCleanup(other.close)
        with patch('sqlite3.connect', side_effect=AssertionError('unexpected SQLite access')):
            self.assertIs(vm.execute('Metadata.Catalogs;'), vm.execute('Метаданные.Справочники;'))
            vm.variables['foreign'] = other.execute('Metadata.Catalogs;')
            with self.assertRaises(BoundaryViolation):
                vm.execute('Foreign.Count();')
            with self.assertRaisesRegex(BSLRuntimeError, 'db required'):
                vm.execute('Metadata.Catalogs.Count();')


class LiveMetadataOwnershipTests(unittest.TestCase):
    def setUp(self):
        owner=fixture.MetadataGraphTests();self.addCleanup(owner.doCleanups)
        self.vm,self.context=owner.runtime(allow_extensions=True)
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name));guard.start();self.addCleanup(guard.stop)
    def prepared(self):
        self.vm.execute('P=Metadata.Catalogs.Products;C=P.Attributes;A=C.Text;S=P.StandardAttributes;F=S[0];')
        return self.vm
    def test_live_graph_without_vm(self):
        vm=self.prepared()
        self.assertEqual(vm.execute('C.Count();'),5)
        self.assertEqual(vm.execute('S.Count();'),4)
        self.assertEqual(vm.execute('A.Name;'),'Text')
        self.assertIs(vm.execute('C.Find("Text");'),vm.variables['a'])
        vm.execute('N=0;For Each V In S Do N=N+1;EndDo;')
        self.assertEqual(vm.variables['n'],4)
    def test_same_context_other_vm_cannot_borrow(self):
        vm=self.prepared();other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        for name,code in (('p','X.Name;'),('c','X.Count();'),('a','X.Name;'),('s','X.Count();'),('f','X.Name;')):
            other.variables['x']=vm.variables[name]
            with self.subTest(name=name),self.assertRaises(DENIED):other.execute(code)
    def _import_reader(self,vm):
        directory=TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        folder=Path(directory.name)
        (folder/'helper.bsl').write_text(
            'Function Name() Export Return Metadata.Catalogs.Products.Name; EndFunction '
            'Function Read(Val Item) Export Return Item.Name; EndFunction',
            encoding='utf-8')
        vm.execute('// #Import helper.bsl\n',source=str(folder/'main.bsl'))
        return vm.imports['helper'].interpreter

    def test_import_keeps_its_issued_graph_and_rejects_foreign_graph(self):
        vm=self.prepared();self._import_reader(vm)
        self.assertEqual(vm.execute('Helper.Name()'),'Products')
        self.assertEqual(vm.execute('Helper.Read(P)'),'Products')
        independent=Interpreter(database_context=self.context)
        self.addCleanup(independent.close)
        vm.set_variable('Foreign',independent.execute('Metadata.Catalogs.Products'))
        with self.assertRaises(BoundaryViolation):vm.execute('Helper.Read(Foreign)')

    def test_root_manager_publication_is_not_resealable_with_child_managers(self):
        vm=self.prepared();root=vm._metadata
        child=self._import_reader(vm)
        old=root._catalog_managers,root._document_managers
        try:
            root._catalog_managers,root._document_managers=child._catalogs,child._documents
            with self.assertRaises(BoundaryViolation):vm.execute('Helper.Name()')
        finally:
            root._catalog_managers,root._document_managers=old
        self.assertEqual(vm.execute('Helper.Name()'),'Products')

    def test_closed_context_revokes_registered_child(self):
        vm=self.prepared();self.context.close()
        with self.assertRaises(DENIED):vm.execute('A.Name;')
    def test_generation_change_revokes_child(self):
        vm=self.prepared();backend=self.context._backend;old=backend.configuration_generation
        backend.configuration_generation=old+1
        try:
            with self.assertRaises(DENIED):vm.execute('C.Count();')
        finally:backend.configuration_generation=old
    def test_class_and_instance_callbacks_never_execute(self):
        vm=self.prepared();effects=[]
        with patch.object(metadata.StandardAttributeDescription,'get_member',lambda *a:effects.append('class')):
            with self.assertRaises(DENIED):vm.execute('F.Name;')
        c=vm.variables['c'];c._snapshot=lambda:effects.append('instance')
        try:
            with self.assertRaises(DENIED):vm.execute('C.Count();')
        finally:del c._snapshot
        self.assertEqual(effects,[])
    def test_coherent_foreign_collection_replacement_is_not_admitted(self):
        vm=self.prepared();other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.execute('P=Metadata.Catalogs.Products;C=P.Attributes;')
        p=vm.variables['p'];old=p._children['attributes'];p._children['attributes']=other.variables['c']
        try:
            with self.assertRaises(DENIED):vm.execute('P.Attributes.Count();')
        finally:p._children['attributes']=old
    def test_late_argument_mutation_cannot_rebind_receiver(self):
        vm=self.prepared();p=vm.variables['p'];old=p._root
        def touch():p._root=object();return Decimal(0)
        vm.register_function('Touch',touch)
        try:
            with self.assertRaises(DENIED):vm.execute('C.Get(Touch());')
        finally:p._root=old
    def test_iteration_rechecks_after_body_effect(self):
        vm=self.prepared();p=vm.variables['p'];old=p._root;effects=[]
        def touch():effects.append('body');p._root=object()
        vm.register_function('Touch',touch)
        try:
            with self.assertRaises(DENIED):vm.execute('For Each V In C Do Touch();EndDo;')
        finally:p._root=old
        self.assertEqual(effects,['body'])
    def test_forged_lazy_description_is_not_published(self):
        vm=self.prepared();a=vm.variables['a'];old=a._description;effects=[]
        class Trap:
            def get_member(self,name):effects.append(name)
        a._description=Trap()
        try:
            with self.assertRaises(DENIED):vm.execute('A.Type.StringQualifiers.Length;')
        finally:a._description=old
        self.assertEqual(effects,[])
    def test_readonly_error_keeps_rhs_effect_order(self):
        vm=self.prepared();effects=[]
        vm.register_function('Touch',lambda:effects.append('rhs') or 'x')
        for code in ('Metadata.Name=Touch();','A.Name=Touch();','C[0]=Touch();','S[0]=Touch();'):
            effects.clear()
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError):vm.execute(code)
            self.assertEqual(effects,['rhs'])
