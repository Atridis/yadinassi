"""Host-only draft evidence with synthetic source, never native activation."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import unittest
from unittest.mock import patch

from yadinassi import form_event_simulation as sim
from yadinassi.errors import BSLError
from yadinassi.form_module_analysis import FormModuleAnalysisError
from test_form_module_analysis import SOURCE, CATALOG, FORM, DEFINITION, binding


class FormDraftSessionTests(unittest.TestCase):
    def make(self, **changes):
        args = dict(source=SOURCE, binding=binding(), catalog_xml=CATALOG,
                    form_xml=FORM, definition_xml=DEFINITION, code='01',
                    description=' original ')
        args.update(changes)
        return sim.FormDraftSession(**args)

    def test_initial_image_does_not_run_or_normalize_with_bsl(self):
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            session = self.make(description=' x ')
        state = session.snapshot()
        self.assertEqual(state.revision, 0)
        self.assertEqual(dict(state.baseline),
            {'Code': '01', 'Description': ' x ', 'DeletionMark': False})
        self.assertEqual(state.values, state.baseline)
        self.assertEqual(state.messages, ())
        self.assertFalse(state.native_parity)
        self.assertEqual(session.binding, binding())

    def test_change_atomically_adopts_normalized_image_and_messages(self):
        session = self.make(); original = session.snapshot()
        short = session.change_description(' x ', revision=0)
        self.assertIs(session.snapshot(), short)
        self.assertEqual(short.revision, 1)
        self.assertEqual(short.baseline, original.values)
        self.assertEqual(dict(short.values),
            {'Code': '01', 'Description': 'x', 'DeletionMark': False})
        self.assertEqual(short.messages,
            (sim.FormEventMessage('At least three characters', 'Объект.Наименование'),))
        good = session.change_description(' longer ', revision=1)
        self.assertEqual(good.revision, 2)
        self.assertEqual(dict(good.values)['Description'], 'longer')
        self.assertEqual(good.messages, ())
        self.assertEqual(good.baseline, original.values)
        self.assertEqual(dict(short.values)['Description'], 'x')
        self.assertEqual(dict(original.values)['Description'], ' original ')

    def test_each_accepted_event_owns_one_revision_even_for_equal_values(self):
        session = self.make()
        for revision in range(8):
            state = session.change_description(' same ', revision=revision)
            self.assertEqual(state.revision, revision + 1)
            prepared = session.prepare_save(revision=revision + 1)
            # The private server receiver has only one setter, not this revision.
            self.assertEqual(prepared.revision, revision + 1)
            self.assertIs(session.snapshot(), state)

    def test_stale_or_inexact_revision_rejected_before_admission(self):
        class Revision(int): pass
        class Hostile:
            def __eq__(self, other): raise AssertionError('comparison hook')
        session = self.make()
        before = session.change_description('first', revision=0)
        with patch.object(sim, 'analyze_form_module', side_effect=AssertionError('admitted')):
            for revision in (0, -1, 2, True, False, 1.0, '1', None, Revision(1), Hostile()):
                with self.subTest(revision=type(revision).__name__):
                    with self.assertRaisesRegex(ValueError, 'stale revision'):
                        session.change_description('second', revision=revision)
                    with self.assertRaisesRegex(ValueError, 'stale revision'):
                        session.prepare_save(revision=revision)
        self.assertIs(session.snapshot(), before)

    def test_hostile_description_inputs_do_not_invoke_hooks_or_change_state(self):
        class Text(str):
            def encode(self, *args, **kwargs): raise AssertionError('encode hook')
        class Hostile:
            def __str__(self): raise AssertionError('string hook')
        session = self.make(); before = session.snapshot()
        invalid = ([], {}, (), b'abc', 1, True, None, Text('abc'), Hostile(),
                   'x\x00y', 'x' * 65537, 'x' * 101 + '\ud800', 'a' * 99 + '\U0001f600')
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for value in invalid:
                with self.subTest(type=type(value).__name__), self.assertRaises((TypeError, ValueError)):
                    session.change_description(value, revision=0)
                self.assertIs(session.snapshot(), before)

    def test_initial_image_exact_types_and_existing_qualifiers(self):
        class Text(str): pass
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for name, value in (('code', Text('01')), ('code', []), ('description', {}),
                                ('description', 'x\x00'), ('deletion_mark', 0),
                                ('deletion_mark', 'false')):
                with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                    self.make(**{name: value})
            session = self.make(code='1234567890', description='x' * 101)
        self.assertEqual(dict(session.snapshot().baseline)['Code'], '123456789')
        self.assertEqual(dict(session.snapshot().baseline)['Description'], 'x' * 100)
        changed = session.change_description('x' * 101, revision=0)
        self.assertEqual(dict(changed.values)['Description'], 'x' * 100)

    def test_read_only_code_and_closed_input_surface(self):
        session = self.make(); before = session.snapshot()
        for key in ('code', 'deletion_mark', 'control', 'field', 'event', 'values'):
            with self.subTest(key=key), self.assertRaises(TypeError):
                session.change_description('abc', revision=0, **{key: 'forged'})
        for name in ('change_control', 'patch', 'set_member', 'get_member', 'commit', 'adopt', 'write'):
            self.assertFalse(hasattr(session, name))
        self.assertIs(session.snapshot(), before)
        self.assertEqual(dict(session.change_description('changed', revision=0).values)['Code'], '01')

    def test_no_caller_receiver_ast_sink_backend_or_paths(self):
        session = self.make()
        for key in ('analysis', 'ast', 'receiver', 'sink', 'callback', 'backend',
                    'database_context', 'catalog_path', 'module_path', 'data_key'):
            with self.subTest(key=key):
                with self.assertRaises(TypeError): self.make(**{key: object()})
                with self.assertRaises(TypeError):
                    session.change_description('abc', revision=0, **{key: object()})
                with self.assertRaises(TypeError):
                    session.prepare_save(revision=0, **{key: object()})
        with self.assertRaises(AttributeError): session.binding = binding()

    def test_save_prepares_detached_candidate_without_adopting_it(self):
        session = self.make(); before = session.snapshot()
        prepared = session.prepare_save(revision=0)
        self.assertEqual(prepared.revision, 0)
        self.assertEqual(dict(prepared.candidate),
            {'Code': '01', 'Description': 'original', 'DeletionMark': False})
        self.assertFalse(prepared.cancel)
        self.assertFalse(prepared.native_parity)
        self.assertEqual(prepared.messages, ())
        self.assertIs(session.snapshot(), before)
        self.assertEqual(dict(before.values)['Description'], ' original ')
        self.assertEqual(before.values, before.baseline)

    def test_refusal_keeps_edit_buffer_revision_and_client_messages(self):
        session = self.make(); initial = session.snapshot()
        edited = session.change_description(' x ', revision=0)
        refused = session.prepare_save(revision=1)
        self.assertTrue(refused.cancel)
        self.assertEqual(refused.revision, 1)
        self.assertEqual(dict(refused.candidate)['Description'], 'x')
        self.assertEqual(refused.messages,
            (sim.FormEventMessage('Please enter a longer name', 'Объект.Наименование'),))
        self.assertIs(session.snapshot(), edited)
        self.assertEqual(edited.baseline, initial.values)
        self.assertNotEqual(edited.messages, refused.messages)
        fixed = session.change_description(' fixed ', revision=1)
        self.assertFalse(session.prepare_save(revision=2).cancel)
        self.assertEqual(fixed.messages, ())

    def test_refused_preparation_does_not_copy_normalization_into_loaded_buffer(self):
        session = self.make(description=' x '); before = session.snapshot()
        refused = session.prepare_save(revision=0)
        self.assertTrue(refused.cancel)
        self.assertEqual(dict(refused.candidate)['Description'], 'x')
        self.assertIs(session.snapshot(), before)
        self.assertEqual(dict(before.values)['Description'], ' x ')

    def test_repeated_preparations_are_informational_not_persistence(self):
        session = self.make(description=' x '); before = session.snapshot()
        first = session.prepare_save(revision=0)
        for _ in range(5):
            self.assertEqual(session.prepare_save(revision=0), first)
            self.assertIs(session.snapshot(), before)
        session.change_description('new', revision=0)
        with self.assertRaises(ValueError): session.prepare_save(revision=first.revision)
        self.assertEqual(dict(first.candidate)['Description'], 'x')
        self.assertFalse(hasattr(first, 'commit'))

    def test_cancel_is_exact_and_never_cleared_or_adopted(self):
        session = self.make(); before = session.snapshot()
        for cancel in (0, 1, 'false', None, [], {}):
            with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
                with self.subTest(cancel=cancel), self.assertRaises(TypeError):
                    session.prepare_save(revision=0, cancel=cancel)
            self.assertIs(session.snapshot(), before)
        self.assertTrue(session.prepare_save(revision=0, cancel=True).cancel)
        self.assertFalse(session.prepare_save(revision=0).cancel)
        self.assertIs(session.snapshot(), before)

    def test_deletion_mark_early_return_uses_session_not_private_revision(self):
        session = self.make(description=' x ', deletion_mark=True)
        for cancel in (False, True):
            prepared = session.prepare_save(revision=0, cancel=cancel)
            self.assertEqual(dict(prepared.candidate)['Description'], ' x ')
            self.assertEqual(prepared.cancel, cancel)
            self.assertEqual(prepared.messages, ())
        for revision in range(3): session.change_description(' x ', revision=revision)
        prepared = session.prepare_save(revision=3)
        self.assertEqual(prepared.revision, 3)  # The private receiver never changed.
        self.assertFalse(prepared.cancel)
        self.assertEqual(prepared.messages, ())

    def test_all_returned_state_is_recursively_immutable_and_independent(self):
        session = self.make()
        state = session.change_description(' x ', revision=0)
        prepared = session.prepare_save(revision=1)
        for obj, field in ((state, 'revision'), (state, 'baseline'), (state, 'values'),
                           (state.messages[0], 'text'), (prepared, 'revision'),
                           (prepared, 'candidate'), (prepared, 'cancel'),
                           (prepared.messages[0], 'field'), (session.binding, 'source_sha256')):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(obj, field, None)
        for values in (state.baseline, state.values, prepared.candidate):
            with self.assertRaises(TypeError): values[0] = ('Code', 'forged')
            with self.assertRaises(TypeError): values[0][1] = 'forged'
        session.change_description('later', revision=1)
        self.assertEqual(dict(state.values)['Description'], 'x')
        self.assertEqual(dict(prepared.candidate)['Description'], 'x')

    def test_constructor_and_each_event_freshly_admit_exact_captured_bytes(self):
        source = b'\xef\xbb\xbf' + SOURCE.replace(b'\n', b'\r\n')
        bound = binding(source)
        before_hash = sha256(source).hexdigest()
        with patch.object(sim, 'analyze_form_module', wraps=sim.analyze_form_module) as analyze, \
             patch.object(sim, '_parse', wraps=sim._parse) as parse:
            session = self.make(source=source, binding=bound)
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(parse.call_count, 0)  # No execution parse during construction.
            session.change_description(' x ', revision=0)
            session.prepare_save(revision=1)
            session.prepare_save(revision=1)
        self.assertEqual(analyze.call_count, 4)
        self.assertEqual(parse.call_count, 3)
        for call in analyze.call_args_list:
            self.assertIs(call.args[0], source)
            self.assertIs(call.args[1], bound)
            self.assertIs(call.kwargs['catalog_xml'], CATALOG)
            self.assertIs(call.kwargs['form_xml'], FORM)
            self.assertIs(call.kwargs['definition_xml'], DEFINITION)
        for call in parse.call_args_list: self.assertIs(call.args[0], source)
        self.assertEqual(sha256(source).hexdigest(), before_hash)

    def test_source_binding_and_metadata_mismatch_rejected_before_execution(self):
        changes = ({'source': SOURCE + b' '}, {'catalog_xml': CATALOG + b' '},
                   {'form_xml': FORM + b' '}, {'definition_xml': DEFINITION + b' '},
                   {'binding': replace(binding(), configuration_generation=True)},
                   {'binding': replace(binding(), catalog_id=binding().form_id)},
                   {'source': bytearray(SOURCE)}, {'catalog_xml': bytearray(CATALOG)})
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for change in changes:
                with self.subTest(change=tuple(change)), self.assertRaises(FormModuleAnalysisError):
                    self.make(**change)
        with self.assertRaises(ValueError): self.make(binding=object())

    def test_re_admission_failure_never_uses_cached_analysis_or_changes_state(self):
        session = self.make(); before = session.snapshot()
        # Trusted-host fault injection, not a public mutation interface.
        for name, value in (('_source', SOURCE + b' '), ('_catalog_xml', CATALOG + b' '),
                            ('_form_xml', FORM + b' '), ('_definition_xml', DEFINITION + b' '),
                            ('_binding', replace(binding(), form_id=binding().catalog_id))):
            old = getattr(session, name)
            try:
                setattr(session, name, value)
                with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
                    with self.assertRaises(FormModuleAnalysisError):
                        session.change_description('new', revision=0)
                    with self.assertRaises(FormModuleAnalysisError): session.prepare_save(revision=0)
                self.assertIs(session.snapshot(), before)
            finally:
                setattr(session, name, old)
        self.assertEqual(session.change_description(' new ', revision=0).revision, 1)

    def test_new_matching_hash_cannot_admit_arbitrary_execution(self):
        source = SOURCE.replace(' Объект.Наименование ='.encode(),
                                ' Объект.Записать();\n Объект.Наименование ='.encode(), 1)
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            with self.assertRaises(FormModuleAnalysisError):
                self.make(source=source, binding=binding(source))

    def test_failure_after_private_mutation_and_message_has_no_partial_state(self):
        original = sim._EventInterpreter
        observed, created, closed = [], [], []
        class Failure(original):
            def __init__(self, sink):
                def observe(record):
                    observed.append(record)
                    sink(record)
                super().__init__(observe)
                created.append(self)

            def visit_ExpressionStatement(self, node):
                yield from super().visit_ExpressionStatement(node)
                raise ValueError('failure after private mutation and message')

            def close(self):
                closed.append(self)
                return super().close()

        for event in ('change', 'save'):
            session = self.make(description=' x ')
            if event == 'change': session.change_description(' z ', revision=0)
            before = session.snapshot(); count = len(created)
            with patch.object(sim, '_EventInterpreter', Failure):
                with self.subTest(event=event), self.assertRaises((ValueError, BSLError)):
                    if event == 'change': session.change_description(' y ', revision=1)
                    else: session.prepare_save(revision=0)
            self.assertEqual(len(created), count + 1)  # No retry.
            self.assertIn(created[-1], closed)
            self.assertEqual(created[-1].variables['объект'].get_member('Description'),
                             'y' if event == 'change' else 'x')
            self.assertIs(session.snapshot(), before)
            self.assertEqual(session.change_description(' recovered ', revision=before.revision).revision,
                             before.revision + 1)
        self.assertEqual(len(observed), 2)

    def test_message_rejection_after_private_change_keeps_session_state(self):
        original = sim._EventInterpreter
        for invalid in ('routing', 'overflow'):
            class Failure(original):
                def __init__(self, sink):
                    def fail(record):
                        if invalid == 'routing': sink(replace(record, data_path='forbidden'))
                        else:
                            sink(record)
                            sink(record)
                    super().__init__(fail)
            session = self.make(); before = session.snapshot()
            with patch.object(sim, '_EventInterpreter', Failure):
                with self.subTest(invalid=invalid), self.assertRaises((ValueError, BSLError)):
                    session.change_description(' x ', revision=0)
            self.assertIs(session.snapshot(), before)

    def test_no_module_activation_marshalling_or_database_context(self):
        instances = []; original = sim._EventInterpreter
        class Spy(original):
            def __init__(self, sink):
                super().__init__(sink)
                instances.append(self)
        with patch.object(sim, '_EventInterpreter', Spy), \
             patch.object(sim.Interpreter, 'execute', side_effect=AssertionError('execute')), \
             patch.object(sim.Interpreter, 'execute_program', side_effect=AssertionError('module')), \
             patch.object(sim.Interpreter, '_new_server_activation', side_effect=AssertionError('crossing')):
            session = self.make()
            session.change_description('x', revision=0)
            for _ in range(3): session.prepare_save(revision=1)
        self.assertEqual(len(instances), 4)
        for vm in instances:
            self.assertIsNone(vm.database_context)
            self.assertEqual(vm.routines, {})
            self.assertEqual(vm.imports, {})
            self.assertEqual(vm.pending_promises, ())
