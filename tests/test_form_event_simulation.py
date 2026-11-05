"""Local simulation evidence only; synthetic source is not native evidence."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import unittest
from unittest.mock import patch

from yadinassi import form_event_simulation as sim
from yadinassi.form_module_analysis import FormModuleAnalysisError
from yadinassi.user_messages import UserMessageRecord
from yadinassi.errors import BSLError
from test_form_module_analysis import SOURCE, CATALOG, FORM, DEFINITION, binding


class FormEventSimulationTests(unittest.TestCase):
    def run_event(self, **changes):
        args = dict(source=SOURCE, binding=binding(), catalog_xml=CATALOG,
                    form_xml=FORM, definition_xml=DEFINITION, event='OnChange',
                    code='01', description=' abc ')
        args.update(changes)
        return sim.simulate_form_event(**args)

    def test_client_trims_original_handler(self):
        result = self.run_event()
        self.assertEqual(dict(result.snapshot.values),
            {'Code': '01', 'Description': 'abc', 'DeletionMark': False})
        self.assertEqual(result.messages, ())
        self.assertFalse(result.cancel)
        self.assertFalse(result.native_parity)

    def test_client_short_name_field_message(self):
        result = self.run_event(description=' x ')
        self.assertEqual(dict(result.snapshot.values)['Description'], 'x')
        self.assertEqual(result.messages, (sim.FormEventMessage('At least three characters', 'Объект.Наименование'),))
        self.assertFalse(result.cancel)

    def test_server_short_name_cancels(self):
        result = self.run_event(event='BeforeWriteAtServer', description=' x ')
        self.assertTrue(result.cancel)
        self.assertEqual(result.messages[0].text, 'Please enter a longer name')
        self.assertEqual(dict(result.snapshot.values)['Description'], 'x')

    def test_server_accepts_long_name(self):
        result = self.run_event(event='BeforeWriteAtServer')
        self.assertFalse(result.cancel)
        self.assertEqual(result.messages, ())
        self.assertEqual(dict(result.snapshot.values)['Description'], 'abc')

    def test_server_early_return_and_existing_cancel(self):
        for cancel in (False, True):
            result = self.run_event(event='BeforeWriteAtServer', description=' x ',
                                    deletion_mark=True, cancel=cancel)
            self.assertEqual(dict(result.snapshot.values)['Description'], ' x ')
            self.assertEqual(result.snapshot.revision, 0)
            self.assertEqual(result.cancel, cancel)
            self.assertEqual(result.messages, ())

    def test_server_does_not_clear_existing_cancel(self):
        self.assertTrue(self.run_event(event='BeforeWriteAtServer', cancel=True).cancel)

    def test_immutable_result_and_input_isolation(self):
        text = ' x '
        result = self.run_event(description=text)
        self.assertEqual(text, ' x ')
        for obj, name in ((result, 'cancel'), (result.snapshot, 'revision'),
                          (result.messages[0], 'text')):
            with self.assertRaises(FrozenInstanceError): setattr(obj, name, None)
        with self.assertRaises(TypeError): result.snapshot.values[0] = ('Code', 'changed')

    def test_every_call_fresh_state_and_budget(self):
        first = self.run_event(event='BeforeWriteAtServer', description=' x ')
        for _ in range(8):
            self.assertEqual(self.run_event(event='BeforeWriteAtServer', description=' x '), first)
            self.assertEqual(self.run_event().messages, ())

    def test_reject_non_scalar_host_inputs_before_vm(self):
        class Text(str): pass
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('VM constructed')):
            for name, value in (('description', []), ('code', object()),
                                ('description', Text('abc')), ('cancel', 1),
                                ('deletion_mark', 0), ('description', 'x' * 65537)):
                with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                    self.run_event(**{name: value})

    def test_fresh_hash_and_metadata_admission_before_vm(self):
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('VM constructed')):
            for changes in ({'source': SOURCE + b' '}, {'catalog_xml': CATALOG + b' '},
                            {'form_xml': FORM + b' '}, {'definition_xml': DEFINITION + b' '},
                            {'binding': replace(binding(), configuration_generation=0)}):
                with self.subTest(changes=tuple(changes)), self.assertRaises(FormModuleAnalysisError):
                    self.run_event(**changes)

    def test_no_public_analysis_or_receiver_or_paths(self):
        with self.assertRaises(ValueError): self.run_event(binding=object())
        for name in ('analysis', 'receiver', 'module_path', 'sink', 'database_context'):
            with self.subTest(name=name), self.assertRaises(TypeError): self.run_event(**{name: object()})

    def test_reject_event_and_client_cancel(self):
        for event in ('Write', 'NameChanged', '', None, 1):
            with self.subTest(event=event), self.assertRaises(ValueError): self.run_event(event=event)
        with self.assertRaises(ValueError): self.run_event(cancel=True)

    def test_unsafe_source_fresh_matching_hash_still_rejected(self):
        for extra in ('Сообщить("bad");', 'Новый Файл("x");', 'Выполнить "x=1";',
                      'Объект.Записать();', 'Сообщение.УстановитьДанные(Объект);'):
            source = SOURCE.replace(' Объект.Наименование ='.encode(),
                                    (' ' + extra + '\n Объект.Наименование =').encode(), 1)
            with self.subTest(extra=extra), self.assertRaises(FormModuleAnalysisError):
                self.run_event(source=source, binding=binding(source))

    def test_reserved_handler_name_rejected_after_static_admission(self):
        for name in ('Сообщение', 'Объект', 'СокрЛП', 'ТекущийОбъект'):
            source = SOURCE.replace(b'NameChanged', name.encode())
            definition = DEFINITION.replace(b'NameChanged', name.encode())
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'collision'):
                self.run_event(source=source, definition_xml=definition,
                               binding=binding(source, definition=definition))

    def test_no_module_activation_marshalling_or_db_context(self):
        with patch.object(sim.Interpreter, 'execute', side_effect=AssertionError('execute')), \
             patch.object(sim.Interpreter, 'execute_program', side_effect=AssertionError('module')), \
             patch.object(sim.Interpreter, '_new_server_activation', side_effect=AssertionError('crossing')):
            self.run_event()
            self.run_event(event='BeforeWriteAtServer', description=' x ')

    def test_vm_closed_capabilities_and_cleanup(self):
        instances = []
        original = sim._EventInterpreter
        class Spy(original):
            def __init__(self, sink):
                super().__init__(sink); instances.append(self)
        with patch.object(sim, '_EventInterpreter', Spy): self.run_event(description=' x ')
        vm = instances[0]
        self.assertIsNone(vm.database_context)
        self.assertEqual(set(vm.functions), {'сокрлп', 'стрдлина'})
        self.assertEqual(set(vm.types), {'сообщениепользователю'})
        self.assertEqual(vm.routines, {})
        self.assertEqual(vm.imports, {})
        self.assertEqual(vm.pending_promises, ())
        program, _ = sim._parse(SOURCE)
        for name in ('Metadata', 'ThisObject', 'Catalogs', 'Eval', 'Message'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                vm.visit_Name(sim.ast.Name(program[0].token, name))

    def test_sink_rejects_routing_and_overflow_no_retry(self):
        original = sim._EventInterpreter
        records = [UserMessageRecord('x', 'Объект.Наименование', 'Object', None, None),
                   UserMessageRecord('x', 'Объект.Наименование', '', object(), None),
                   UserMessageRecord('x', 'Объект.Наименование', '', None, object()),
                   UserMessageRecord('x' * 1025, 'Объект.Наименование', '', None, None)]
        for record in records:
            class Invalid(original):
                def __init__(self, sink):
                    super().__init__(sink); sink(record)
            with self.subTest(record=record), patch.object(sim, '_EventInterpreter', Invalid), self.assertRaises(ValueError):
                self.run_event()
        class Overflow(original):
            def __init__(self, sink):
                super().__init__(sink)
                sink(UserMessageRecord('x', 'Объект.Наименование', '', None, None))
        with patch.object(sim, '_EventInterpreter', Overflow), self.assertRaises((ValueError, BSLError)):
            self.run_event(description=' x ')
        self.assertEqual(self.run_event().messages, ())

    def test_execution_budget_failure_then_fresh_success(self):
        original = sim._EventInterpreter
        class Exhausted(original):
            def __init__(self, sink):
                super().__init__(sink); self._remaining = 0
        with patch.object(sim, '_EventInterpreter', Exhausted), self.assertRaises(ValueError): self.run_event()
        self.assertEqual(self.run_event().messages, ())
