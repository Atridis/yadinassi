"""Only exact file services accept their known positional defaults."""
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.streams.file_io import binary_from_string, find_files
from yadinassi.syntax.parser import parse


class DirectFileOptionalHolesTests(unittest.TestCase):
    def vm(self, **kwargs):
        vm = Interpreter(**kwargs)
        self.addCleanup(vm.close)
        return vm

    def test_binary_encoding_hole_and_aliases_source_ast_prepared(self):
        for route, name in (('source', 'GetBinaryDataFromString'),
                            ('ast', 'ПолучитьДвоичныеДанныеИзСтроки'),
                            ('prepared', 'Encode')):
            with self.subTest(route=route):
                vm = self.vm(allow_extensions=route == 'prepared')
                if route == 'prepared':
                    vm.register_function('Encode', binary_from_string)
                source = f'Base64String({name}("é",,True));'
                if route == 'source':
                    result = vm.execute(source)
                elif route == 'ast':
                    result = vm.execute_program(parse(source))
                else:
                    plan = vm.prepare(source)
                    self.assertIn('resolve_optional_service', plan._plan.generated_source)
                    result = vm.execute_prepared(plan)
                self.assertEqual(result, '77u/w6k=')

    def test_find_file_mask_hole_uses_existing_exact_path_behavior(self):
        vm = self.vm(allow_extensions=True)
        vm.register_function('FindAlias', find_files)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.txt'
            path.write_text('sample', encoding='utf-8')
            vm.variables['path'] = str(path)
            for name in ('FindFiles', 'НайтиФайлы', 'FindAlias'):
                with self.subTest(name=name):
                    self.assertEqual(vm.execute(f'{name}(Path,,True).Count();'), 1)
            vm.variables['path'] = str(path.with_name('missing.txt'))
            self.assertEqual(vm.execute('FindFiles(Path,,True).Count();'), 0)

    def test_required_holes_and_other_services_reject_before_effects(self):
        vm = self.vm(allow_extensions=True)
        seen = []
        vm.register_function('Effect', lambda: seen.append(1) or 'text')
        for source in ('GetBinaryDataFromString(,Effect(),True);',
                       'FindFiles(,Effect(),False);',
                       'GetBinaryDataFromString(Effect(),,,True);',
                       'StrLen(Effect(),);'):
            with self.subTest(source=source), self.assertRaisesRegex(BSLError, 'Пропуск аргументов'):
                vm.execute(source)
        self.assertEqual(seen, [])

    def test_replacement_of_registry_binding_applies_only_to_future_calls(self):
        vm = self.vm(allow_extensions=True)
        seen = []

        def replace():
            seen.append('value')
            vm.register_function('GetBinaryDataFromString', lambda *args: seen.append(args))
            return 'é'

        def bom():
            seen.append('bom')
            return True

        vm.register_function('Replace', replace)
        vm.register_function('Bom', bom)
        plan = vm.prepare('Base64String(GetBinaryDataFromString(Replace(),,Bom()));')
        self.assertEqual(vm.execute_prepared(plan), '77u/w6k=')
        self.assertEqual(seen, ['value', 'bom'])
        with self.assertRaisesRegex(BSLError, 'Пропуск аргументов'):
            vm.execute_prepared(plan)
        self.assertEqual(seen, ['value', 'bom'])
        vm.execute('GetBinaryDataFromString("ordinary", "UTF-8", False);')
        self.assertEqual(seen[-1], ('ordinary', 'UTF-8', False))

    def test_mutated_bound_implementation_never_receives_inserted_none(self):
        vm = self.vm(allow_extensions=True)
        seen = []
        binding = vm.functions['getbinarydatafromstring']

        def mutate():
            binding.function = lambda *args: seen.append(args)
            return 'é'

        vm.register_function('Mutate', mutate)
        with self.assertRaisesRegex(BoundaryViolation, 'implementation changed'):
            vm.execute('GetBinaryDataFromString(Mutate(),,True);')
        self.assertEqual(seen, [])

    def test_shadowed_native_service_keeps_bsl_routine_resolution(self):
        vm = self.vm()
        vm.execute('Function GetBinaryDataFromString(Val X, Val Y=6, Val Z=8) Return Y; EndFunction')
        self.assertEqual(vm.execute('GetBinaryDataFromString("ordinary");'), 6)
        # The persisted BSL routine supplies its own default, not the
        # positional None used by the overshadowed file builtin.
        self.assertEqual(vm.execute('GetBinaryDataFromString("ordinary",,True);'), 6)

    def test_nonhole_call_keeps_ordinary_resolver(self):
        vm = self.vm()
        plan = vm.prepare('Base64String(GetBinaryDataFromString("é","UTF-8",True));')
        source = plan._plan.generated_source
        self.assertIn('resolve_service', source)
        self.assertNotIn('resolve_optional_service', source)
        self.assertEqual(vm.execute_prepared(plan), '77u/w6k=')
