"""Caller-side effects cannot turn a checked source call into another grant."""
import unittest
from unittest.mock import patch
from test_source_server_call import configuration
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.runtime import Interpreter


class SourceServerCallSecurity(unittest.TestCase):
    def setUp(self):
        for name in ('_execute_program', 'call_routine', '_planned_routine_block'):
            poison = patch.object(Interpreter, name, side_effect=AssertionError('legacy ' + name))
            poison.start()
            self.addCleanup(poison.stop)

    def app(self, body, output, *, allow_extensions=False):
        app = SourceApplication(configuration('', body), output=output, allow_extensions=allow_extensions)
        self.addCleanup(app.close)
        app.start()
        return app

    def test_origin_changes_during_argument_rejected_before_body(self):
        for operation in ('registry', 'close', 'instance'):
            with self.subTest(operation=operation):
                output = []
                holder = {}
                def emit(value):
                    output.append(value)
                    if value != 'arg':
                        return
                    app = holder['app']
                    owner = app._instances[('serverapi', 'server', False)]
                    if operation == 'registry':
                        owner.server_routines['run'] = None
                    elif operation == 'close':
                        owner.close()
                    else:
                        app._instances[('serverapi', 'server', False)] = app.interpreter
                app = self.app('Function Run(Val X) Export Message("wrong"); Return X; EndFunction', emit)
                holder['app'] = app
                app.interpreter.execute('Function Touch() Message("arg"); Return 1; EndFunction')
                with self.assertRaises((BSLError, BoundaryViolation, ValueError, TypeError)):
                    app.interpreter.execute('ServerAPI.Run(Touch())')
                self.assertEqual(output, ['arg'])
                self.assertEqual(app.interpreter.execution_context, 'client')

    def test_arity_and_procedure_value_rejected_before_argument(self):
        for body, code in (
            ('Function Run(Val X) Export Return X; EndFunction', 'ServerAPI.Run(Touch(),Touch())'),
            ('Procedure Run(Val X) Export EndProcedure', 'A=ServerAPI.Run(Touch())'),
        ):
            with self.subTest(body=body):
                output = []
                app = self.app(body, output.append)
                app.interpreter.execute('Function Touch() Message("wrong"); Return 1; EndFunction')
                with self.assertRaises(BSLError):
                    app.interpreter.execute(code)
                self.assertEqual(output, [])

    def test_cycle_packet_rejected_without_server_effect(self):
        output = []
        app = self.app('Function Run(Val X) Export Message("wrong"); Return 1; EndFunction', output.append)
        app.interpreter.execute('A=New Array; A.Add(A);')
        with self.assertRaises(BSLError):
            app.interpreter.execute('ServerAPI.Run(A)')
        self.assertEqual(output, [])
        self.assertEqual(app.interpreter.execution_context, 'client')

    def test_safe_mode_rejects_before_argument(self):
        output = []
        app = self.app('Function Run(Val X) Export Message("wrong-server"); Return X; EndFunction', output.append)
        app.interpreter.execute('Function Touch() Message("wrong-arg"); Return 1; EndFunction')
        with self.assertRaises(BSLError):
            app.interpreter.execute('SetSafeMode(True); ServerAPI.Run(Touch());')
        self.assertEqual(output, [])

    def test_changed_origin_host_binding_rejected_before_argument(self):
        for operation in ('wrapper', 'callback', 'extra'):
            with self.subTest(operation=operation):
                output = []
                app = self.app('Function Run(Val X) Export Return X; EndFunction', output.append, allow_extensions=True)
                app.interpreter.execute('Function Touch() Message("wrong"); Return 1; EndFunction')
                owner = app.module('serverapi', app.interpreter).interpreter
                if operation == 'wrapper':
                    owner.register_function('StrLen', lambda value: 999)
                elif operation == 'callback':
                    owner.functions['strlen'].function = lambda value: 999
                else:
                    owner.register_function('Custom', lambda: 999)
                with self.assertRaises((BSLError, BoundaryViolation, ValueError)):
                    app.interpreter.execute('ServerAPI.Run(Touch())')
                self.assertEqual(output, [])

    def test_source_transaction_blocks_crossing_and_callee_activation(self):
        import tempfile
        from pathlib import Path
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = []
        app = SourceApplication(configuration('',
            'Function Run() Export Message("wrong"); Return 1; EndFunction\n'
            'Procedure Begin() Export BeginTransaction(); EndProcedure'),
            scratch_database=Path(directory.name) / 'scratch.sqlite', output=output.append)
        self.addCleanup(app.close)
        app.start()
        app.constant_store.begin_transaction()
        with self.assertRaises((BSLError, ValueError)):
            app.interpreter.execute('ServerAPI.Run()')
        self.assertEqual(output, [])
        self.assertFalse(app.constant_store.transaction_active)
        with self.assertRaisesRegex(BSLError, 'synchronous|admission'):
            app.interpreter.execute('ServerAPI.Begin()')
        self.assertFalse(app.constant_store.transaction_active)
        self.assertEqual(app.interpreter.execution_context, 'client')

    def test_activation_revoked_after_return_and_error(self):
        from yadinassi.execution.direct.source.python_direct_source_server import _ACTIVE, check_activation
        for finish in ('Return 1;', 'Raise "stop";'):
            with self.subTest(finish=finish):
                captured = []
                def emit(value):
                    captured.append(_ACTIVE.get()[-1][0])
                app = self.app('Function Run() Export Message("capture"); ' + finish + ' EndFunction', emit)
                app.interpreter.execute('Try A=ServerAPI.Run(); Except EndTry;')
                self.assertEqual(len(captured), 1)
                fresh = captured[0]
                self.assertTrue(fresh._family_released)
                self.assertEqual(_ACTIVE.get(), ())
                with self.assertRaises(BoundaryViolation):
                    check_activation(fresh)
                self.assertEqual(app.interpreter.execution_context, 'client')

    def test_factory_hook_rejected_before_callback(self):
        from yadinassi.configuration.configuration_source_runtime import _SourceInterpreter
        output = []
        app = self.app('Function Run() Export Return 1; EndFunction', output.append)
        app.module('serverapi', app.interpreter)
        callback = unittest.mock.Mock(side_effect=AssertionError('wrong-constructor'))
        with patch.object(_SourceInterpreter, '__init__', callback):
            with self.assertRaises(BoundaryViolation):
                app.interpreter.execute('ServerAPI.Run()')
        callback.assert_not_called()

    def test_base_factory_hooks_rejected_before_callback(self):
        for name in ('__init__', 'register_function', 'register_type', '_bind_schema_scope',
                     '_register_platform_function', '_register_platform_type',
                     '_register_function', '_register_type', '_record_platform_binding'):
            with self.subTest(name=name):
                app = self.app('Function Run() Export Return 1; EndFunction', lambda _: None)
                app.module('serverapi', app.interpreter)
                callback = unittest.mock.Mock(side_effect=AssertionError('wrong-base-hook'))
                with patch.object(Interpreter, name, callback):
                    with self.assertRaises(BoundaryViolation):
                        app.interpreter.execute('ServerAPI.Run()')
                callback.assert_not_called()

    def test_fresh_host_binding_mutation_rejected_before_next_callback(self):
        from yadinassi.execution.direct.source.python_direct_source_server import _ACTIVE
        output = []
        def emit(value):
            output.append(value)
            if value == 'first':
                fresh = _ACTIVE.get()[-1][0]
                fresh.functions['message'].function = lambda value: output.append('wrong')
        app = self.app('Function Run() Export Message("first"); Message("second"); Return 1; EndFunction', emit)
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('ServerAPI.Run()')
        self.assertEqual(output, ['first'])
        self.assertEqual(_ACTIVE.get(), ())
        self.assertEqual(app.interpreter.execution_context, 'client')

    def test_default_mutation_is_not_reauthorized_at_first_call(self):
        import copy
        from decimal import Decimal
        for timing in ('before', 'during'):
            for mutation in ('parameter', 'node', 'value'):
                with self.subTest(timing=timing, mutation=mutation):
                    output = []
                    holder = {}
                    def change():
                        routine = holder['owner'].server_routines['run']
                        if mutation == 'parameter':
                            routine.parameters[0] = copy.copy(routine.parameters[0])
                        elif mutation == 'node':
                            routine.parameters[0].default = copy.copy(routine.parameters[0].default)
                        else:
                            routine.parameters[0].default.value = Decimal(999)
                    def emit(value):
                        output.append(value)
                        if timing == 'during' and value == 'arg':
                            change()
                    app = self.app('Function Run(Val X=1) Export Message("wrong"); Return X; EndFunction', emit)
                    holder['owner'] = app.module('serverapi', app.interpreter).interpreter
                    app.interpreter.execute('Function Touch() Message("arg"); Return 1; EndFunction')
                    if timing == 'before':
                        change()
                    with self.assertRaises(BoundaryViolation):
                        app.interpreter.execute('ServerAPI.Run(Touch())')
                    self.assertEqual(output, [] if timing == 'before' else ['arg'])
                    self.assertEqual(app.interpreter.execution_context, 'client')

    def test_mutated_signature_rejected_before_host_protocols(self):
        for field in ('parameters', 'name'):
            with self.subTest(field=field):
                callbacks = []
                class TrapList(list):
                    def __len__(self):
                        callbacks.append('len')
                        return super().__len__()
                    def __iter__(self):
                        callbacks.append('iter')
                        return super().__iter__()
                class TrapName:
                    def casefold(self):
                        callbacks.append('casefold')
                        return 'run'
                holder = {}
                def emit(value):
                    routine = holder['owner'].server_routines['run']
                    if field == 'parameters':
                        routine.parameters = TrapList(routine.parameters)
                    else:
                        routine.name = TrapName()
                app = self.app('Function Run(Val X=1) Export Return X; EndFunction', emit)
                holder['owner'] = app.module('serverapi', app.interpreter).interpreter
                app.interpreter.execute('Function Touch() Message("arg"); Return 1; EndFunction')
                with self.assertRaises(BoundaryViolation):
                    app.interpreter.execute('ServerAPI.Run(Touch())')
                self.assertEqual(callbacks, [])


if __name__ == '__main__':
    unittest.main()
