"""Source ValueStorage retains bounded immutable snapshots without VM dispatch."""
import unittest
from unittest.mock import patch
import test_source_storage_values as existing
import test_source_session_types as sessions
from test_configuration_source_runtime import source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


def poison(test):
    for name in ('_execute_program','call_routine','_planned_routine_block'):
        guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
        guard.start();test.addCleanup(guard.stop)


class SourceStorageValuesNoVM(existing.SourceStorageValueTests):
    def setUp(self):
        super().setUp();poison(self)


class DirectSourceValueStorage(unittest.TestCase):
    def setUp(self):poison(self)
    def app(self, *, allow_extensions=False):
        app=SourceApplication(source(b''),output=lambda _:None, allow_extensions=allow_extensions)
        self.addCleanup(app.close);app.start();return app

    def test_typed_session_snapshot_isolation(self):
        original=sessions.SourceSessionTypesTests()
        self.addCleanup(original.doCleanups)
        original.test_value_storage_snapshot_isolation()

    def test_bilingual_constructor_and_saved_scalar_get(self):
        vm=self.app().interpreter
        self.assertEqual(vm.execute('S=New ХранилищеЗначения("value"); F=S.Получить; F();'),'value')
        self.assertEqual(vm.execute('S.Get();'),'value')

    def test_list_structure_snapshot_independent_gets(self):
        vm=self.app().interpreter
        vm.execute('A=New Array; A.Add(1); S=New ValueStorage(New Structure("Items",A)); A.Add(2);')
        storage=vm.variables['s']
        first=storage.get();first.get_member('Items').items.append(99)
        self.assertEqual(storage.get().get_member('Items').items,[1])

    def test_cycles_and_unknown_objects_do_not_publish(self):
        vm=self.app(allow_extensions=True).interpreter
        with self.assertRaises(Exception):vm.execute('A=New Array;A.Add(A);S=New ValueStorage(A);')
        self.assertNotIn('s',vm.variables)
        vm.register_function('Unknown',lambda:object())
        with self.assertRaises(Exception):vm.execute('S=New ValueStorage(Unknown());')
        self.assertNotIn('s',vm.variables)

    def test_arity_denied_before_argument_effect(self):
        vm=self.app(allow_extensions=True).interpreter;effects=[]
        vm.register_function('Touch',lambda:effects.append(1) or 1)
        with self.assertRaises(Exception):vm.execute('S=New ValueStorage(Touch(),Touch());')
        self.assertEqual(effects,[])

    def test_plain_value_storage_is_separate_from_source_scalar_get(self):
        vm=Interpreter();self.addCleanup(vm.close)
        self.assertEqual(vm.execute('S=New ValueStorage(1); S.Get();'),1)
        self.assertEqual(vm.execute('S=New ValueStorage(New Structure("Value",2)); S.Get().Value;'),2)
        owner=self.app().interpreter
        owner.execute('S=New ValueStorage(New Structure("Value",2));')
        with self.assertRaisesRegex(BSLError,'scalar snapshots only'):
            owner.execute('S.Get();')

    def test_source_form_scalar_storage(self):
        import test_source_forms as forms
        from yadinassi.configuration.configuration_source import import_source
        from yadinassi.forms.source_forms import SourceFormController
        mapping=forms.files(b'&AtServer\nProcedure Created(Cancel, StandardProcessing)\n'
            b'S=New ValueStorage("stored");Greeting=S.Get();EndProcedure\n'
            b'&AtClient\nProcedure Go(Command) EndProcedure')
        app=SourceApplication(import_source(mapping));self.addCleanup(app.close);app.start()
        controller=SourceFormController(app,'CommonForm.Main')
        self.assertIsNone(controller.exchange(forms.request())['result']['error'])
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'stored')
