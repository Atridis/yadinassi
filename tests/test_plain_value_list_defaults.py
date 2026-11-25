from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.collections.plain_value_list import PlainValueList
from yadinassi.types.type_descriptions import BSLTypeDescription


class PlainValueListDefaultTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.addCleanup(self.vm.close)

    def test_historical_collections_default_properties_in_source_eval_and_prepared(self):
        # Compare two existing native observations without invoking unrelated
        # ForEach/presentation cases in the full Collections probe.
        proof = (Path(__file__).parent / 'fixtures/native_windows/collections.out').read_text(encoding='utf-8')
        record = proof.split('table.list.identity: [\n', 1)[1].split('\n]', 1)[0]
        consumed = self.vm.prepare('''
            V=New ValueList; V.Add(10); V.Add(20);
            D=V.ValueType; R=Eval("V.ТипЗначения");
            A=D.Types(); A.Add(Type("String"));
        ''')
        self.vm.execute_prepared(consumed)
        self.assertIs(type(self.vm.variables['d']), BSLTypeDescription)
        self.assertEqual(self.vm.variables['d'], self.vm.variables['r'])
        self.assertEqual(self.vm.execute('V.ValueType.Types().Count()'), 0)
        self.assertEqual(self.vm.execute('D.AdjustValue()'), None)
        self.assertEqual(self.vm.execute('V.ТипЗначения.Типы().Количество()'), 0)
        self.assertIn('  ValueType=[]', record.splitlines())
        undefined = self.vm.execute('ValueToStringInternal(V.AvailableValues)')
        self.assertIn('  AvailableValues=' + undefined, record.splitlines())
        self.assertIsNone(self.vm.execute('V.ДоступныеЗначения'))

    def test_imported_list_returns_only_the_same_public_defaults(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'Side.bsl').write_text(
                'Var Box Export; Box=New Structure("Values",New ValueList);',
                encoding='utf-8')
            self.vm.execute('// #Import Side.bsl\nD=Side.Box.Values.ТипЗначения; N=D.Types().Count();',
                            str(root / 'Main.bsl'))
            self.assertEqual(self.vm.variables['n'], 0)
            self.assertIsNone(self.vm.execute('Side.Box.Values.AvailableValues'))
            with self.assertRaisesRegex(BSLError, 'Поле объекта'):
                self.vm.execute('Side.Box.Values.__class__')

    def test_no_writable_or_subclass_grant(self):
        self.vm.execute('V=New ValueList; Procedure SetMember(X) X=1;EndProcedure')
        for source in ('V.ValueType=Undefined;', 'V.AvailableValues=Undefined;',
                       'SetMember(V.ValueType);', 'SetMember(V.AvailableValues);'):
            with self.subTest(source=source), self.assertRaises((BSLError, BoundaryViolation)):
                self.vm.execute(source)
        self.assertEqual(self.vm.execute('V.ValueType.Types().Count()'), 0)
        self.assertIsNone(self.vm.execute('V.AvailableValues'))

        class Foreign(PlainValueList):
            @property
            def ValueType(self):
                raise AssertionError('host attribute read')
        self.vm.variables['foreign'] = Foreign()
        with self.assertRaises(BoundaryViolation):
            self.vm.execute('foreign.ValueType')
