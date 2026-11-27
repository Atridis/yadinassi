from decimal import Decimal
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.text.strings import join
from yadinassi.types.values import BSLArray,BSLFixedArray,NULL
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

class DirectStringJoinTests(unittest.TestCase):
    def test_source_ast_prepared_and_bilingual_collections(self):
        from yadinassi.syntax.parser import parse
        source='A=New Array;A.Add(12.5);A.Add(True);A.Add(Undefined);A.Add(New Array);A.Add(New Structure);A.Add(New Map);R=СтрСоединить(A,"|");S=StrConcat(A,"|");'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            if route=='source':vm.execute(source)
            elif route=='ast':vm.execute_program(parse(source))
            else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['r'],'12,5|Да||Массив|Структура|Соответствие')
            self.assertEqual(vm.variables['s'],vm.variables['r'])
            self.assertEqual(len(vm.variables['a']),6)

    def test_bilingual_join_accepts_exact_published_plain_array(self):
        from yadinassi.execution.direct.python_direct_plain_array import _DIRECT_PLAIN_ARRAY_TYPE
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm=Interpreter();self.addCleanup(vm.close)
                vm.execute('A=New Array; A.Add(12.5); A.Add(-2.5); A.Add(0);')
                self.assertIs(type(vm.variables['a']),_DIRECT_PLAIN_ARRAY_TYPE)
                source='R=СтрСоединить(A,"|"); S=StrConcat(A,"|");'
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertEqual((vm.variables['r'],vm.variables['s']),('12,5|-2,5|0','12,5|-2,5|0'))

    def test_canonical_arrays_and_fixed_arrays_unchanged(self):
        canonical=BSLArray();canonical.items=[Decimal('12.5'),True,None,NULL,'я']
        expected='12,5|Да|||я'
        self.assertEqual(join(canonical,'|'),expected)
        self.assertEqual(join(BSLFixedArray(canonical),'|'),expected)
        self.assertEqual(join(canonical.items,'|'),expected)
        canonical.add([])
        self.assertEqual(join(canonical,'|'),expected+'|Массив')
        self.assertEqual(join(BSLFixedArray(canonical),'|'),expected+'|Массив')
        self.assertEqual(join([]),'')
        self.assertEqual(join(['a','b'],[]),'aМассивb')

    def test_utf16_halves_and_input_identity(self):
        parts=['\ud83d','\ude42'];before=list(parts)
        self.assertEqual(join(parts),'🙂');self.assertEqual(parts,before)
        child=[];parts=[child,child]
        self.assertEqual(join(parts,':'),'Массив:Массив')
        self.assertIs(parts[0],child);self.assertIs(parts[1],child)

    def test_nonarrays_and_subclasses_rejected(self):
        class Child(list):
            def __iter__(self):raise AssertionError('subclass iteration')
        for value in ('x',None,{},(),Child()):
            with self.assertRaises(TypeError):join(value)

    def test_custom_override_and_runtime_revocation(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('StrConcat',lambda *args:'custom')
        self.assertEqual(vm.execute('StrConcat(New Array)'),'custom')
        vm=Interpreter(allow_extensions=True);vm.execute('A=New Array;A.Add("x");')
        def close():vm.close();return '|'
        vm.register_function('Close',close)
        with self.assertRaises(BoundaryViolation):vm.execute('R=StrConcat(A,Close());')
        self.assertNotIn('r',vm.variables)

    def test_string_separator_chain_presents_undefined_after_dynamic_text(self):
        setup = 'Function F() Return "a"; EndFunction '
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = Interpreter()
                self.addCleanup(vm.close)
                source = (setup + 'A=F(); R=F()+":"+Undefined; S=A+":"+Undefined; '
                          'I=20; J=22; N=I+J;')
                plan = vm.prepare(source)
                if prepared:
                    vm.execute_prepared(plan)
                else:
                    vm.execute(source)
                self.assertEqual((vm.variables['r'], vm.variables['s']), ('a:', 'a:'))
                self.assertEqual(vm.variables['n'], 42)
                self.assertIn("n = i + j", plan._plan.generated_source)
                self.assertIn("s = _String(a + ':', None)", plan._plan.generated_source)

    def test_original_strings_completes(self):
        source=Path(__file__).resolve().parents[1]/'integrational_tests/tests/strings.bsl'
        rows=[];vm=Interpreter(rows.append,compilation_profile='managed-thick-file',native_target='linux-8.3.27.1508')
        vm.execute(source.read_text(encoding='utf-8-sig'))
        self.assertEqual(len(rows),385)
        self.assertTrue(rows[0].startswith('pipeline.names:'))
