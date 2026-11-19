"""Known native nonconstructible table children are catchable, not preflight gaps."""
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported

NAMES=('ValueTableRow','СтрокаТаблицыЗначений','ValueTableColumn','КолонкаТаблицыЗначений',
       'ValueTableColumnCollection','КоллекцияКолонокТаблицыЗначений')


class DirectTableConstructorRejectionsTests(unittest.TestCase):
    def test_catchable_rejection_all_aliases_and_entry_routes_without_vm(self):
        for name in NAMES:
            for route in ('source','ast','prepared','eval','execute'):
                vm=Interpreter();seen=[];vm.register_function('Effect',lambda:seen.append('arg'))
                source='Before=1;Caught=False;Try New '+name+'(Effect());Except Caught=True;EndTry;After=2;'
                with self.subTest(name=name,route=route),patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                    if route=='source':vm.execute(source)
                    elif route=='ast':vm.execute_program(parse(source))
                    elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                    elif route=='eval':vm.execute('Before=1;Caught=False;Try Eval("New '+name+'(Effect())");Except Caught=True;EndTry;After=2;')
                    else:vm.execute('Before=1;Caught=False;Try Execute("New '+name+'(Effect());");Except Caught=True;EndTry;After=2;')
                self.assertEqual((vm.variables['before'],vm.variables['caught'],vm.variables['after']),(1,True,2))
                self.assertEqual(seen,[])

    def test_dynamic_constructor_keeps_target_and_parameter_effect_order(self):
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(execution_backend=backend);seen=[]
            vm.register_function('Target',lambda:seen.append('target') or 'ValueTableRow')
            vm.register_function('Parameters',lambda:seen.append('parameters') or None)
            vm.execute('Try New(Target(),Parameters());Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught']);self.assertEqual(seen,['target','parameters'])

    def test_custom_registration_cannot_grant_denied_constructor_authority(self):
        for name in NAMES:
            vm=Interpreter();seen=[];vm.register_type(name,lambda *args:seen.append('factory'))
            vm.execute('Try New '+name+';Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught']);self.assertEqual(seen,[])

    def test_unknown_constructor_remains_preflight_unsupported(self):
        vm=Interpreter();seen=[];vm.register_function('Effect',lambda:seen.append('effect'))
        with self.assertRaises(PythonDirectUnsupported):vm.execute('Effect();Try New CompletelyUnknownType;Except EndTry;')
        self.assertEqual(seen,[])

    def test_native_original_eleven_record_projection(self):
        from scripts import smoke_test
        root=Path(__file__).resolve().parents[1]
        source=(root/'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        expected=(root/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        labels=smoke_test.TABLE_COMMAND_LABELS+('ctor-row','ctor-column','ctor-columns')
        with patch.object(smoke_test,'TABLE_COMMAND_LABELS',labels):
            program,expected=smoke_test.table_command_checkpoint(source,expected)
        output=[];Interpreter(output=output.append).execute(program)
        self.assertEqual('\n'.join(output)+'\n',expected);self.assertEqual(len(labels),11)
