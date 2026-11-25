"""Narrow scalar construction, not generic host-member admission."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.types.unique_identifiers import BSLUUID
from yadinassi.types.values import HostFunction

TEXT='6fe6c569-c38f-4f76-a3a6-bea52c24ed0a'

class DirectUUIDTests(unittest.TestCase):
    def test_aliases_and_current_canonical_value(self):
        vm=Interpreter()
        vm.execute(f'a=New UUID("{TEXT}");b=New УникальныйИдентификатор("{TEXT.upper()}");')
        self.assertIs(type(vm.variables['a']),BSLUUID)
        self.assertEqual(vm.variables['a'],vm.variables['b'])

    def test_invalid_arguments_remain_catchable(self):
        vm=Interpreter()
        vm.execute('caught=0;Try a=New UUID(7);Except caught=caught+1;EndTry;'
                   'Try a=New UUID("invalid");Except caught=caught+1;EndTry;'
                   'Try a=New UUID("x","y");Except caught=caught+1;EndTry;')
        self.assertEqual(vm.variables['caught'],3)
        self.assertNotIn('a',vm.variables)

    def test_overridden_constructor_rejected_before_source_effects(self):
        vm=Interpreter(allow_extensions=True);effects=[]
        vm.types['uuid']=HostFunction('UUID',lambda *args:effects.append('constructor'))
        vm.register_function('Argument',lambda:effects.append('argument'))
        with self.assertRaises(PythonDirectUnsupported):vm.execute('x=1;a=New UUID(Argument());')
        self.assertEqual(effects,[]);self.assertNotIn('x',vm.variables)

    def test_live_override_rejected_before_argument(self):
        vm=Interpreter(allow_extensions=True);effects=[]
        def change():vm.types['uuid']=HostFunction('UUID',lambda *args:effects.append('constructor'))
        vm.register_function('Change',change)
        vm.register_function('Argument',lambda:effects.append('argument'))
        with self.assertRaises(BoundaryViolation):vm.execute('Change();a=New UUID(Argument());')
        self.assertEqual(effects,[])

    def test_constructor_bound_before_argument_registry_change(self):
        vm=Interpreter(allow_extensions=True);effects=[]
        def argument():
            effects.append('argument')
            vm.types['uuid']=HostFunction('UUID',lambda *args:effects.append('replacement'))
            return TEXT
        vm.register_function('Argument',argument)
        vm.execute('a=New UUID(Argument());')
        self.assertEqual(effects,['argument'])
        self.assertEqual(vm.variables['a'],BSLUUID(TEXT))

    def test_prepared_module_rechecks_current_constructor(self):
        vm=Interpreter(allow_extensions=True);prepared=vm.prepare(f'a=New UUID("{TEXT}");')
        vm.types['uuid']=HostFunction('UUID',lambda *args:None)
        with self.assertRaises(PythonDirectUnsupported):vm.execute_prepared(prepared)
        self.assertNotIn('a',vm.variables)

    def test_original_catalog_replay_completes_without_legacy_dispatch(self):
        import sys
        from pathlib import Path
        scripts=str(Path(__file__).resolve().parents[1]/'scripts')
        with patch.object(sys,'path',[scripts]+sys.path):
            from catalog_object_behavior.replay import replay
        rows=replay()
        self.assertEqual(rows,[True]*8+['initial','initial',True,True,'edited',False,True,True,'100',1,False,'first-update','stale-update',True,True,True])
