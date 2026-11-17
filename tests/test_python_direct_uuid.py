"""Narrow scalar construction, not generic host-member admission."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.values import HostFunction
from yadinassi.errors import BSLRuntimeError

TEXT='6fe6c569-c38f-4f76-a3a6-bea52c24ed0a'

class DirectUUIDTests(unittest.TestCase):
    def test_aliases_and_current_canonical_value(self):
        vm=Interpreter()
        with patch.object(vm,'_compiled',side_effect=AssertionError('legacy')):
            vm.execute(f'a=New UUID("{TEXT}");b=New УникальныйИдентификатор("{TEXT.upper()}");')
        self.assertIs(type(vm.variables['a']),BSLUUID)
        self.assertEqual(vm.variables['a'],vm.variables['b'])
        self.assertEqual(vm.execution_backend_stats['fallback'],0)

    def test_invalid_arguments_remain_catchable(self):
        vm=Interpreter()
        vm.execute('caught=0;Try a=New UUID(7);Except caught=caught+1;EndTry;'
                   'Try a=New UUID("invalid");Except caught=caught+1;EndTry;'
                   'Try a=New UUID("x","y");Except caught=caught+1;EndTry;')
        self.assertEqual(vm.variables['caught'],3)
        self.assertNotIn('a',vm.variables)

    def test_overridden_constructor_rejected_before_source_effects(self):
        vm=Interpreter();effects=[]
        vm.types['uuid']=HostFunction('UUID',lambda *args:effects.append('constructor'))
        vm.register_function('Argument',lambda:effects.append('argument'))
        with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;a=New UUID(Argument());')
        self.assertEqual(effects,[]);self.assertNotIn('x',vm.variables)

    def test_live_override_rejected_before_argument(self):
        vm=Interpreter();effects=[]
        def change():vm.types['uuid']=HostFunction('UUID',lambda *args:effects.append('constructor'))
        vm.register_function('Change',change)
        vm.register_function('Argument',lambda:effects.append('argument'))
        with self.assertRaises(BoundaryViolation):vm.execute('Change();a=New UUID(Argument());')
        self.assertEqual(effects,[])

    def test_constructor_bound_before_argument_registry_change(self):
        vm=Interpreter();effects=[]
        def argument():
            effects.append('argument')
            vm.types['uuid']=HostFunction('UUID',lambda *args:effects.append('replacement'))
            return TEXT
        vm.register_function('Argument',argument)
        vm.execute('a=New UUID(Argument());')
        self.assertEqual(effects,['argument'])
        self.assertEqual(vm.variables['a'],BSLUUID(TEXT))

    def test_prepared_module_rechecks_current_constructor(self):
        vm=Interpreter();prepared=vm.prepare(f'a=New UUID("{TEXT}");')
        vm.types['uuid']=HostFunction('UUID',lambda *args:None)
        with self.assertRaises(PythonDirectUnsupported):vm.execute_prepared(prepared)
        self.assertNotIn('a',vm.variables)

    def test_original_catalog_replay_reaches_metadata_after_selection(self):
        import sys
        from pathlib import Path
        scripts=str(Path(__file__).resolve().parents[1]/'scripts')
        with patch.object(sys,'path',[scripts]+sys.path):
            from catalog_object_behavior.replay import replay
        original=Interpreter.register_function;rows=[]
        def register(vm,name,function,*args,**kwargs):
            if name=='CBOEmit':
                actual=function
                def function(number,value):
                    rows.append(value)
                    return actual(number,value)
            return original(vm,name,function,*args,**kwargs)
        # This deliberately records the next unsupported operation, not a claim
        # that the complete native comparison passed.
        with patch.object(Interpreter,'register_function',register),patch.object(Interpreter,'block',side_effect=AssertionError('legacy block')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            with self.assertRaisesRegex(BSLRuntimeError,'Metadata'):
                replay()
        self.assertEqual(rows,[True]*8+['initial','initial',True,True,'edited',False,True,True,'100',1,False,'first-update','stale-update',True,True])
