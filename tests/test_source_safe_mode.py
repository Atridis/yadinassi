"""Source-only safe counters and execution boundaries, not native captures."""
import unittest

from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.safe_mode import require_external_access


class SourceSafeModeTests(unittest.TestCase):
    def vm(self):
        output = []
        app = SourceApplication(source(), output=output.append)
        self.addCleanup(app.close)
        app.start()
        return app, app.interpreter, output

    def test_baseline_and_balanced_counter(self):
        _, vm, output = self.vm()
        vm.execute('''Procedure Main()
Message(SafeMode()); SetSafeMode(True); SetSafeMode(True);
Message(SafeMode()); SetSafeMode(False); Message(SafeMode());
SetSafeMode(False); Message(SafeMode()); EndProcedure; Main();''')
        self.assertEqual(output, ['Нет', 'Да', 'Да', 'Нет'])

    def test_false_cannot_remove_caller_counter(self):
        _, vm, output = self.vm()
        vm.execute('''Procedure Child()
Try SetSafeMode(False); Except Message("denied"); EndTry;
Message(SafeMode()); EndProcedure;
Procedure Main() SetSafeMode(True); Child(); Message(SafeMode()); EndProcedure;
Main(); Message(SafeMode());''')
        self.assertEqual(output, ['denied', 'Да', 'Да', 'Нет'])

    def test_callee_own_counter_does_not_disable_parent(self):
        _, vm, output = self.vm()
        vm.execute('''Procedure Child() SetSafeMode(True); SetSafeMode(False); EndProcedure;
Procedure Main() SetSafeMode(True); Child(); Message(SafeMode()); EndProcedure;
Main(); Message(SafeMode());''')
        self.assertEqual(output, ['Да', 'Нет'])

    def test_return_cleans_unbalanced_own_counter(self):
        _, vm, output = self.vm()
        vm.execute('Procedure Child() SetSafeMode(True); Return; EndProcedure; Child(); Message(SafeMode());')
        self.assertEqual(output, ['Нет'])

    def test_exception_cleans_own_counter(self):
        _, vm, output = self.vm()
        vm.execute('Procedure Child() SetSafeMode(True); Raise "stop"; EndProcedure; Try Child(); Except EndTry; Message(SafeMode());')
        self.assertEqual(output, ['Нет'])

    def test_execute_and_eval_inherit_safe_mode(self):
        _, vm, output = self.vm()
        vm.execute('Procedure Main() SetSafeMode(True); Message(Eval("SafeMode()")); Execute "Message(SafeMode());"; EndProcedure; Main();')
        self.assertEqual(output, ['Да', 'Да'])

    def test_russian_aliases(self):
        _, vm, output = self.vm()
        vm.execute('Procedure Main() УстановитьБезопасныйРежим(True); Message(БезопасныйРежим()); EndProcedure; Main();')
        self.assertEqual(output, ['Да'])

    def test_profile_names_and_nonboolean_values_rejected(self):
        for value in ('"profile"', '1', 'Undefined'):
            with self.subTest(value=value):
                _, vm, _ = self.vm()
                with self.assertRaisesRegex(BSLError, 'Boolean only'):
                    vm.execute('Procedure Main() SetSafeMode(' + value + '); EndProcedure; Main();')

    def test_extra_false_is_error(self):
        _, vm, _ = self.vm()
        with self.assertRaisesRegex(BSLError, 'inactive frame'):
            vm.execute('Procedure Main() SetSafeMode(False); EndProcedure; Main();')

    def test_root_setter_is_not_a_fake_routine(self):
        _, vm, _ = self.vm()
        with self.assertRaisesRegex(BSLError, 'BSL routine frame'):
            vm.execute('SetSafeMode(True);')

    def test_real_effect_boundary_denies_before_effect(self):
        _, vm, output = self.vm()
        effects = []
        def external():
            require_external_access('test effect')
            effects.append('effect')
        vm.register_function('External', external)
        vm.execute('Procedure Main() SetSafeMode(True); Try External(); Except Message("denied"); EndTry; EndProcedure; Main();')
        self.assertEqual(effects, [])
        self.assertEqual(output, ['denied'])
        vm.execute('External();')
        self.assertEqual(effects, ['effect'])

    def test_guard_context_does_not_leak_outside_execution(self):
        _, vm, _ = self.vm()
        with self.assertRaises(BSLError):
            vm.execute('Procedure Main() SetSafeMode(True); Raise "stop"; EndProcedure; Main();')
        require_external_access('outside source execution')

    def test_asynchronous_call_from_safe_scope_refused(self):
        _, vm, _ = self.vm()
        with self.assertRaisesRegex(BSLError, 'asynchronous'):
            vm.execute('Async Function Child() Return 1; EndFunction; Procedure Main() SetSafeMode(True); Child(); EndProcedure; Main();')

    def test_source_sessions_do_not_share_counter(self):
        first, vm, _ = self.vm()
        second, other, output = self.vm()
        def foreign():
            other.execute('Message(SafeMode());')
        vm.register_function('Foreign', foreign)
        with self.assertRaisesRegex(BSLError, 'another application'):
            vm.execute('Procedure Main() SetSafeMode(True); Foreign(); EndProcedure; Main();')
        other.execute('Message(SafeMode());')
        self.assertEqual(output, ['Нет'])

    def test_setter_is_procedure_not_undefined_function(self):
        _, vm, _ = self.vm()
        with self.assertRaises(BSLError):
            vm.execute('Procedure Main() Value=SetSafeMode(True); EndProcedure; Main();')

    def test_dynamic_fragment_cannot_disable_caller(self):
        _, vm, output = self.vm()
        vm.execute('''Procedure Main() SetSafeMode(True);
Try Execute "SetSafeMode(False);"; Except Message("denied"); EndTry;
Message(SafeMode()); EndProcedure; Main(); Message(SafeMode());''')
        self.assertEqual(output, ['denied', 'Да', 'Нет'])

    def test_dynamic_fragment_counter_is_local_and_cleaned_on_error(self):
        _, vm, output = self.vm()
        vm.execute('''Procedure Main()
Execute "SetSafeMode(True); Message(SafeMode());"; Message(SafeMode());
Try Execute "SetSafeMode(True); Raise;"; Except EndTry;
Message(SafeMode()); EndProcedure; Main();''')
        self.assertEqual(output, ['Да', 'Нет', 'Нет'])
