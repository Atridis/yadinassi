"""Canonical constructors: independent values and argument effect contracts."""
import unittest
import json
from decimal import Decimal
from yadinassi import Interpreter, BSLError
from yadinassi.collections.plain_value_list import PlainValueList
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectASTCanonicalConstructorTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);self.events=[]
        vm.register_function('Touch',lambda:self.events.append('touch') or Decimal(3))
        return vm

    def test_canonical_constructor_values(self):
        cases=[
            ('A=New Array;A.Add(7);F=New FixedArray(A);R=F.Get(0);',{'r':7}),
            ('A=New Structure("N",7);F=New FixedStructure(A);R=F.N;',{'r':7}),
            ('A=New Map;A.Insert(1,7);F=New FixedMap(A);R=F.Get(1);',{'r':7}),
            ('T=New TypeDescription("Number");R=T.AdjustValue("7");',{'r':7}),
            ('T=New NumberQualifiers(8,2);R=T.Digits;',{'r':8}),
            ('T=New ValueTree;R=T.Rows.Count();',{'r':0}),
            ('U=New UUID("12345678-1234-5678-1234-567812345678");R=String(U);',{'r':'12345678-1234-5678-1234-567812345678'}),
            ('W=New JSONWriter;W.SetString();W.WriteStartObject();W.WritePropertyName("x");W.WriteValue(7);W.WriteEndObject();R=W.Close();',{'json':{'x':7}}),
            ('R=New TextDocument;R.SetText("hello");S=R.GetText();',{'s':'hello'}),
        ]
        for source,expected in cases:
            with self.subTest(source=source):
                vm=self.vm();vm.execute(source)
                for name,value in expected.items():self.assertEqual(json.loads(vm.variables['r']) if name=='json' else vm.variables[name],value)

    def test_unconstructible_and_invalid_arity_preserve_argument_effects(self):
        for source in ('X=1;R=New ValueTableRow(Touch());','R=New JSONWriter(Touch());','R=New UUID(Touch());'):
            with self.subTest(source=source):
                vm=self.vm()
                with self.assertRaises(BSLError):vm.execute(source)
                self.assertEqual(self.events,[] if 'ValueTableRow' in source else ['touch']);self.assertNotIn('r',vm.variables)
        vm=self.vm();vm.execute('R=New NumberQualifiers(Touch(),2);N=R.Digits;')
        self.assertEqual(self.events,['touch']);self.assertEqual(vm.variables['n'],3)

    def test_replaced_constructor_rejected_before_argument(self):
        vm=self.vm();vm.register_type('ValueList',lambda *args:object())
        with self.assertRaises(BoundaryViolation):vm.execute('X=1;T=New ValueList(Touch());')
        self.assertEqual(self.events,[]);self.assertNotIn('t',vm.variables)

    def test_prepared_value_list_checks_reached_binding_before_arguments(self):
        for alias in ('ValueList', 'СписокЗначений'):
            for replace in ('before_run', 'earlier_statement', 'during_argument'):
                with self.subTest(alias=alias, replace=replace):
                    vm = self.vm()

                    def replacement():
                        self.fail('noncanonical factory must not run')

                    def rebind():
                        self.events.append('rebind')
                        vm.register_type(alias, replacement)

                    vm.register_function('Rebind', rebind)
                    prefix = 'Rebind();' if replace == 'earlier_statement' else ''
                    actual = 'Rebind()' if replace == 'during_argument' else 'Touch()'
                    plan = vm.prepare(prefix + f'T=New {alias}({actual});')
                    if replace == 'before_run':
                        vm.register_type(alias, replacement)
                    with self.assertRaises(BoundaryViolation):
                        vm.execute_prepared(plan)
                    self.assertEqual(self.events, [] if replace == 'before_run' else ['rebind'])
                    self.assertNotIn('t', vm.variables)

    def test_value_list_static_construction_remains_native(self):
        source = 'T=New ValueList;For I=1 To 3 Do T.Add(I);EndDo;'
        for extensions in (False, True):
            with self.subTest(extensions=extensions):
                vm = Interpreter(allow_extensions=extensions)
                self.addCleanup(vm.close)
                plan = vm.prepare(source)
                generated = plan._plan.generated_source
                if extensions:
                    self.assertIn("resolve_service('new:valuelist', plain_value_list=True)()", generated)
                else:
                    self.assertIn('_PrivateValueList()', generated)
                    self.assertNotIn('new:valuelist', generated)
                vm.execute_prepared(plan)
                result = vm.variables['t']
                self.assertIs(type(result), PlainValueList)
                self.assertEqual([item[0] for item in result], [1, 2, 3])

    def test_constructor_argument_close_stops_following_effects(self):
        vm=self.vm();vm.register_function('Touch',vm.close)
        with self.assertRaises(BoundaryViolation):vm.execute('X=1;T=New TypeDescription(Touch());Y=2;')
        self.assertNotIn('t',vm.variables);self.assertNotIn('y',vm.variables)
