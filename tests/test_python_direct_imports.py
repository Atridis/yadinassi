"""Direct imports preserve namespace authority and activation lifetimes."""
from cProfile import Profile
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.runtime import _Module, _Namespace
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import make_boundary


class DirectImportBoundaryTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory=Path(directory.name)
        self.main=str(self.directory/'Main.bsl')
        self.events=[]
        self.vm=Interpreter(output=self.events.append, allow_extensions=True)
        self.addCleanup(self.vm.close)

    def module(self, source):
        (self.directory/'Side.bsl').write_text(source,encoding='utf-8')

    def load(self, source='Function F(Val X=1) Export Touch();Return X;EndFunction'):
        self.vm.register_function('Touch',lambda:self.events.append('body'))
        self.module(source)
        self.vm.execute('// #Import Side.bsl\n',self.main)
        return self.vm.imports['side'].interpreter

    def test_source_ast_prepared_have_no_vm_fallback_or_prepare_io(self):
        source='// #Import Side.bsl\nR=Side.F(40);'
        self.module('Message("init");Function F(Val X) Export Return X+2;EndFunction')
        for route in ('source','ast','prepared'):
            with self.subTest(route=route):
                events=[];vm=Interpreter(output=events.append);self.addCleanup(vm.close)
                if route=='prepared':
                    with patch.object(Path,'read_text',side_effect=AssertionError('prepare IO')):
                        plan=vm.prepare(source,self.main)
                    self.assertEqual(events,[]);self.assertEqual(vm.imports,{})
                    vm.execute_prepared(plan)
                elif route=='ast':vm.execute_program(parse(source,self.main))
                else:vm.execute(source,self.main)
                self.assertEqual(vm.variables['r'],42);self.assertEqual(events,['init'])

    def test_plain_import_uses_scoped_parent_lease_instead_of_full_audit(self):
        self.module('Function F(Val X) Export Return X+StrLen("a");EndFunction')
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('// #Import Side.bsl\n', self.main)
        profile = Profile()
        profile.runcall(vm.execute_prepared, vm.prepare('R=Side.F(41);', self.main))
        self.assertEqual(vm.variables['r'], 42)
        self.assertFalse(any(not isinstance(entry.code, str)
                             and entry.code.co_name == '_check'
                             and entry.code.co_filename == make_boundary.__code__.co_filename
                             for entry in profile.getstats()))

    def test_plain_import_rechecks_parent_after_external_effect(self):
        self.module('Function F() Export Message("close");Message("after");Return 42;EndFunction')
        events = []
        def output(value):
            events.append(value)
            vm.close()
        vm = Interpreter(output=output)
        self.addCleanup(vm.close)
        vm.execute('// #Import Side.bsl\n', self.main)
        with self.assertRaises(BoundaryViolation):
            vm.execute('R=Side.F();', self.main)
        self.assertEqual(events, ['close'])
        self.assertNotIn('r', vm.variables)

    def test_cache_namespace_and_family_rebindings_precede_arguments(self):
        child=self.load();self.vm.register_function('Argument',lambda:self.events.append('argument') or 1)
        mutations=((self.vm,'_module_cache',{}),(child,'_family_owner',child),
                   (child,'_module_cache',{}),(self.vm,'imports',{'side':_Module(child)}))
        for obj,name,value in mutations:
            with self.subTest(name=name),patch.object(obj,name,value):
                with self.assertRaises(BoundaryViolation):self.vm.execute('Side.F(Argument())')
                self.assertEqual(self.events,[])

    def test_owner_close_during_argument_stops_body(self):
        self.load()
        def close():self.vm.close();return 1
        self.vm.register_function('CloseOwner',close)
        with self.assertRaises(BoundaryViolation):self.vm.execute('Side.F(CloseOwner())')
        self.assertEqual(self.events,[])

    def test_loader_and_receiver_class_hooks_fail_before_effects(self):
        self.load();self.vm.register_function('Argument',lambda:self.events.append('argument') or 1)
        for cls,name in ((Interpreter,'_load_module'),(_Module,'get_member'),(_Namespace,'__repr__')):
            with self.subTest(cls=cls,name=name),patch.object(cls,name,side_effect=AssertionError('hook'),create=True):
                with self.assertRaises(BoundaryViolation):self.vm.execute('Side.F(Argument())')
                self.assertEqual(self.events,[])

    def test_retained_callable_and_export_reference_expire_with_caller(self):
        self.load('Var X Export;X=7;Function F() Export Return X;EndFunction')
        context=make_boundary(self.vm);context.enter()
        try:
            call=context.resolve_import_call(('side','f'),require_value=True,argument_count=0)
            reference=context.import_reference(('side','x'))
            self.assertEqual(reference.get(),7)
        finally:context.leave()
        for operation in (call,reference.get,lambda:reference.set(9)):
            with self.assertRaises(BoundaryViolation):operation()
        self.assertEqual(self.vm.imports['side'].interpreter.variables['x'],7)

    def test_callee_boundary_and_single_use_callable_expire_after_return(self):
        child=self.load('Function F() Export Return 42;EndFunction')
        contexts=[];original=make_boundary
        def capture(vm,**kwargs):
            context=original(vm,**kwargs)
            if vm is child:contexts.append(context)
            return context
        parent=original(self.vm);parent.enter()
        try:
            with patch('yadinassi.execution.direct.python_direct.make_boundary',capture):
                call=parent.resolve_import_call(('side','f'),require_value=True,argument_count=0)
                self.assertEqual(contexts,[])
                self.assertEqual(call(),42)
            with self.assertRaises(BoundaryViolation):call()
            self.assertEqual(len(contexts),1)
            with self.assertRaises(BoundaryViolation):contexts[0]._check()
        finally:parent.leave()

    def test_detached_metadata_enters_child_boundary_and_retained_method_expires(self):
        from test_source_metadata import files
        from yadinassi.configuration.configuration_source import import_source
        from yadinassi.configuration.configuration_source_metadata import SourceMetadataRoot
        child=self.load('Var MD;Function Read() Export Return MD.Subsystems.Count();EndFunction')
        child.variables['md']=SourceMetadataRoot(import_source(files()))
        from yadinassi.execution.direct.python_direct_detached_metadata import DetachedMetadataBoundary
        retained=[];original=DetachedMetadataBoundary.resolve_member
        def capture(context,value,name):
            bound=original(context,value,name)
            if context.vm is child and name.casefold()=='count':retained.append(bound)
            return bound
        with patch.object(DetachedMetadataBoundary,'resolve_member',capture):
            self.assertEqual(self.vm.execute('Side.Read()'),2)
        self.assertEqual(len(retained),1)
        with self.assertRaises(BoundaryViolation):retained[0]()

    def test_namespaces_never_escape_as_values_or_python_members(self):
        self.load('Function F() Export Return 42;EndFunction')
        for expression in ('Side','Side.F','Side.__dict__','Side.interpreter','Side[0]','Side.F.__class__'):
            with self.subTest(expression=expression),self.assertRaises((BSLError,BoundaryViolation)):
                self.vm.execute('Result='+expression)
        self.assertNotIn('result',self.vm.variables)

    def test_import_recursion_and_same_side_error_description(self):
        self.load('''Function Sum(Val N) Export If N=0 Then Return 0;EndIf;Return N+Sum(N-1);EndFunction
Function Describe() Export Return ErrorDescription();EndFunction
Procedure Inner() Export Try Raise "inner";Except Captured=ErrorDescription();EndTry;EndProcedure''')
        self.assertEqual(self.vm.execute('Side.Sum(5)'),15)
        self.vm.execute('Try Raise "outer";Except Before=Side.Describe();Side.Inner();After=Side.Describe();EndTry;',self.main)
        self.assertTrue(self.vm.variables['before'].endswith('outer'))
        self.assertEqual(self.vm.variables['after'],'')

    def test_argument_failure_creates_no_child_activation(self):
        child=self.load()
        contexts=[];original=make_boundary
        def capture(vm,**kwargs):
            context=original(vm,**kwargs)
            if vm is child:contexts.append(context)
            return context
        with patch('yadinassi.execution.direct.python_direct.make_boundary',capture):
            with self.assertRaises(BSLError):self.vm.execute('Side.F(1/0)')
        self.assertEqual(contexts,[]);self.assertEqual(self.events,[])
        self.assertEqual(self.vm.execute('Side.F(7)'),7)
        self.assertEqual(self.events,['body'])

    def test_nested_load_budgets_reject_without_partial_publication_and_recover(self):
        from yadinassi.execution.direct import python_direct_imports as imports
        self.module('// #Import Leaf.bsl\nMessage("side");Function F() Export Return Leaf.F();EndFunction')
        (self.directory/'Leaf.bsl').write_text('Message("leaf");Function F() Export Return 42;EndFunction',encoding='utf-8')
        for limit in ('_MAX_MODULES','_MAX_DEPTH'):
            with self.subTest(limit=limit):
                events=[];vm=Interpreter(output=events.append);self.addCleanup(vm.close)
                with patch.object(imports,limit,2):
                    with self.assertRaises(BSLError):vm.execute('// #Import Side.bsl\nMessage("main");',self.main)
                self.assertEqual(events,[]);self.assertEqual(vm.imports,{})
                self.assertEqual(vm._module_cache,{});self.assertEqual(vm._loading,[])
                self.assertEqual(vm.execute('// #Import Side.bsl\nSide.F()',self.main),42)
                self.assertEqual(events,['leaf','side'])
                self.assertEqual(len(vm._module_cache),2)

    def test_prepared_late_namespace_layout_change_refuses_before_effects(self):
        from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
        self.module('Function F() Export Return 42;EndFunction')
        self.vm.register_function('Touch',lambda:self.events.append('effect'))
        prepared=self.vm.prepare('Touch();Saved=9;',self.main)
        self.vm.execute('// #Import Side.bsl\nSaved=7;',self.main)
        with self.assertRaises(PythonDirectUnsupported):self.vm.execute_prepared(prepared)
        self.assertEqual(self.events,[]);self.assertEqual(self.vm.variables['saved'],7)

    def test_parent_revocation_inside_child_stops_subsequent_effects(self):
        self.module('Function F() Export Revoke();ChildAfter();Return 42;EndFunction')
        for change in ('imports','configuration'):
            with self.subTest(change=change):
                events=[];vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
                def revoke():
                    events.append('revoke')
                    if change=='imports':vm.imports.clear()
                    else:vm._configuration_runtime=object()
                vm.register_function('Revoke',revoke)
                vm.register_function('ChildAfter',lambda:events.append('after'))
                vm.execute('// #Import Side.bsl\n',self.main)
                try:
                    with self.assertRaises(BoundaryViolation):vm.execute('Side.F()')
                    self.assertEqual(events,['revoke'])
                finally:vm._configuration_runtime=None

    def test_successful_descendant_cache_survives_failed_parent_collection(self):
        import gc
        (self.directory/'Leaf.bsl').write_text('Message("leaf-init");Function F() Export Return 42;EndFunction',encoding='utf-8')
        self.module('// #Import Leaf.bsl\nRaise "parent-failed";')
        with self.assertRaises(BSLError):self.vm.execute('// #Import Side.bsl\n',self.main)
        self.assertEqual(self.events,['leaf-init']);self.assertEqual(self.vm.imports,{})
        gc.collect()
        self.vm.execute('// #Import Leaf.bsl\nR=Leaf.F();',self.main)
        self.assertEqual(self.vm.variables['r'],42);self.assertEqual(self.events,['leaf-init'])

    def test_released_child_and_reopened_root_do_not_revive_old_grants(self):
        child=self.load();child.close()
        with self.assertRaises(BoundaryViolation):self.vm.execute('Side.F()')
        self.assertEqual(self.events,[])
        self.vm.close()
        # The public family reset does not grant old cached imported children.
        Interpreter._require_family(self.vm)
        with self.assertRaises(BoundaryViolation):self.vm.execute('Side.F()')
        self.assertEqual(self.events,[])

    def test_definition_time_loader_seal_rejects_pre_lazy_patch(self):
        import subprocess
        import textwrap
        script=textwrap.dedent('''
            import sys
            from yadinassi import Interpreter
            from yadinassi.runtime import _Module
            from unittest.mock import patch
            from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
            cls,name=((Interpreter,'_load_module') if sys.argv[1]=='loader' else (_Module,'get_member'))
            events=[]
            with patch.object(cls,name,side_effect=lambda *a:events.append('hook')):
                vm=Interpreter(output=events.append)
                try:vm.execute('// #Import Missing.bsl\\nMessage("body");','Main.bsl')
                except BoundaryViolation:pass
                else:raise RuntimeError('pre-lazy hook was admitted')
                if events:raise RuntimeError('effect before denial')
        ''')
        for target in ('loader','receiver'):
            with self.subTest(target=target):
                result=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-c',script,target],
                                      text=True,capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
