"""Hostile-value and live authority contracts on the current direct runtime.

The old plain-plan eligibility gate no longer exists. Test the actual public
boundary rather than its removed cache/adapter decision.
"""
import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.syntax.parser import parse
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from configuration_runtime_fixture import module_files


class DirectHostileBoundaryTests(unittest.TestCase):
    def value(self,events,answer):
        class Meta(type):
            def __eq__(self,other):events.append('eq');return answer
            __hash__=type.__hash__
        class Value(metaclass=Meta):pass
        return Value()

    def test_foreign_parameter_never_invokes_metaclass(self):
        for answer in (False,True):
            with self.subTest(answer=answer):
                events=[];value=self.value(events,answer)
                vm=Interpreter();self.addCleanup(vm.close);vm.variables['x']=value
                vm.execute('Function F(Val x) Return x;EndFunction r=F(x);')
                self.assertIs(vm.variables['r'],value);self.assertEqual(events,[])

    def test_foreign_literal_rejected_before_effects_or_hooks(self):
        for answer in (False,True):
            with self.subTest(answer=answer):
                events=[];output=[];program=parse('Message("bad"); Function F() Return 1;EndFunction r=F();')
                program[1].body[0].value.value=self.value(events,answer)
                vm=Interpreter(output=output.append);self.addCleanup(vm.close)
                with self.assertRaisesRegex(PythonDirectUnsupported,'immutable parser values'):vm.execute_program(program)
                self.assertEqual(events,[]);self.assertEqual(output,[])

    def test_custom_storage_policy_not_silently_ignored(self):
        output=[];vm=Interpreter(output=output.append);self.addCleanup(vm.close)
        with patch.object(vm,'set_variable',side_effect=AssertionError('storage hook called')), \
             self.assertRaisesRegex(PythonDirectUnsupported,'custom storage hooks'):
            vm.execute('Message("bad");')
        self.assertEqual(output,[])

    def app(self,output):
        source='Function F(Val X) Export Message(X);Return X+1;EndFunction'
        app=ConfigurationApplication.from_files(module_files([('Tools',source,{})]),output=output)
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    def test_live_call_authority_after_warm_call(self):
        output=[];app=self.app(output.append)
        self.assertEqual(app.execute('Tools.F(3)'),Decimal(4));self.assertEqual(output,['3'])
        with patch.object(app,'check_call',side_effect=PermissionError('revoked call')):
            with self.assertRaisesRegex(PermissionError,'revoked call'):app.execute('Tools.F(4)')
        self.assertEqual(output,['3'])

    def test_live_host_authority_after_warm_call(self):
        output=[];app=self.app(output.append)
        app.execute('Tools.F(3);')
        with patch.object(app,'check_host_service',side_effect=PermissionError('revoked host')):
            with self.assertRaisesRegex(PermissionError,'revoked host'):app.execute('Tools.F(4);')
        self.assertEqual(output,['3'])

    def test_owner_revoked_by_callback_cannot_resume(self):
        output=[];app=None
        def emit(value):
            output.append(value);app.state='exiting'
        app=self.app(emit)
        with self.assertRaises(BoundaryViolation):app.execute('R=Tools.F(3);Message("after");')
        self.assertEqual(output,['3']);self.assertNotIn('r',app.interpreter.variables)


if __name__=='__main__':unittest.main()
