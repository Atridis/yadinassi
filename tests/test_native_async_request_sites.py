"""Pinned failure-only source locations, not native cause or successful execution.
Execute the unchanged generated classifier with synthetic ErrorInfo values. Source
labels, locations and controlled errors exercise guards, never native contracts.
"""
from dataclasses import replace
from decimal import Decimal
import itertools
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.error_info import BSLErrorInfo
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.values import BSLNull
import test_native_async_request_reader as reader_fixture
import test_native_async_request_sites_integration as integration

suite = reader_fixture.suite
MODULE = integration.SOURCE_LABEL
SITES = (
    (375, '        АсинхЗапрос = AsyncReadRequest(ЭтапВхода);', 'request_key'),
    (183, '        AsyncExpectToken(Reader, JSONValueType.PropertyName);', 'request_key_call'),
    (168, '    If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;', 'request_key_read'),
    (169, '    If Reader.CurrentValueType <> Token Then Raise "ASYNC-REQUEST"; EndIf;', 'request_key_token'),
    (184, '        Key = Reader.CurrentValue;', 'request_key_current'),
    (185, '        If Request.Property(Key) Then Raise "ASYNC-REQUEST"; EndIf;', 'request_key_property'),
)
CALIBRATION_LINE = 227
CALIBRATION_SOURCE = 'Raise "ASYNC-SITE-CALIBRATION";'
_UNSET = object()


def frame(site, cause=None, *, unindented=False):
    line, source, _ = SITES[site]
    return BSLErrorInfo('PRIVATE ORIGINAL ERROR', code='PRIVATE CODE',
                        additional_information='PRIVATE ADDITIONAL',
                        module_name=MODULE, line_number=line,
                        initial_string=source.lstrip() if unindented else source,
                        cause=cause)


def sourceless(cause=None):
    return BSLErrorInfo('PRIVATE NATIVE LEAF', cause=cause)


def calibration(**changes):
    values = dict(description='ASYNC-SITE-CALIBRATION', module_name=MODULE,
                  line_number=CALIBRATION_LINE, initial_string=CALIBRATION_SOURCE)
    values.update(changes)
    return BSLErrorInfo(**values)


_REAL_GET_MEMBER = BSLErrorInfo.get_member


def controlled_get_member(info, name):
    key = name.casefold()
    if key in getattr(info, '_test_unavailable', ()):
        raise ValueError('PRIVATE UNAVAILABLE PROPERTY')
    if key in getattr(info, '_test_overrides', {}):
        return info._test_overrides[key]
    return _REAL_GET_MEMBER(info, name)


def controlled(info, *, unavailable=(), **overrides):
    # Preserve the exact production TypeOf identity; scoped class-method patch
    # supplies unavailable/wrong-typed native-property observations only.
    result = replace(info)
    object.__setattr__(result, '_test_unavailable', unavailable)
    object.__setattr__(result, '_test_overrides', overrides)
    return result


def classify(saved, *, case_id=0, calibration_value=_UNSET, source_offset=0):
    module = suite.async_client_module(case_id).decode('utf-8-sig')
    begin = module.index('&AtClient\nFunction AsyncRequestKeySite')
    end = module.index('&НаКлиенте\nПроцедура АсинхЗаписатьВход')
    source = '\n' * (module[:begin].count('\n') + source_offset) + module[begin:end]
    output = []
    vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
    vm.execute(source, MODULE)
    if calibration_value is not _UNSET:
        vm.register_function('ErrorInfo', lambda: calibration_value)
    vm.variables['saved'] = saved
    # Same guarded assignment as the actual outer catch: a helper exception must
    # never replace the original coarse stage. Actual catch is tested separately.
    with mock.patch.object(BSLErrorInfo, 'get_member', controlled_get_member):
        vm.execute('Stage = "request_key"; Try Stage = AsyncRequestKeySite(saved); Except EndTry;')
    assert output == []
    return vm.execute('Stage')


class GeneratedRequestSiteGuardTests(unittest.TestCase):
    def test_exact_generated_locations_and_append_only_labels_for_all_cases(self):
        for case_id in range(8):
            module = suite.async_client_module(case_id).decode('utf-8-sig')
            lines = module.splitlines()
            self.assertEqual(lines[CALIBRATION_LINE - 1], CALIBRATION_SOURCE)
            self.assertIn(f'Calibration.LineNumber <> {CALIBRATION_LINE}', module)
            for site, (line, source, label) in enumerate(SITES):
                self.assertEqual(lines[line - 1], source)
                for unindented in (False, True):
                    with self.subTest(case=case_id, site=site, unindented=unindented):
                        self.assertEqual(classify(frame(site, unindented=unindented), case_id=case_id), label)
            for code, (_, _, label) in enumerate(SITES[1:], 26):
                self.assertEqual(suite.ASYNC_ENTRY_LOG_MARKERS['ASYNC-ENTRY-FAILURE:' + label], code)
                self.assertEqual(suite.ASYNC_LOG_CATEGORIES[code], 'entry_' + label)

    def test_exhaustive_located_pair_transition_matrix(self):
        # Only the exact pinned callgraph, never generic deepest-frame selection.
        for first, second in itertools.product(range(6), repeat=2):
            allowed = (first == 0 and second > 0) or (first == 1 and second in (2, 3))
            expected = SITES[second][2] if allowed else 'request_key'
            with self.subTest(first=first, second=second):
                self.assertEqual(classify(frame(first, frame(second))), expected)

    def test_exact_sourceless_terminal_leaf_and_full_chain(self):
        self.assertEqual(classify(sourceless()), 'request_key')
        self.assertEqual(classify(frame(0, sourceless())), 'request_key')
        for site in range(1, 6):
            self.assertEqual(classify(frame(site, sourceless())), SITES[site][2])
        for leaf in (2, 3):
            chain = frame(0, frame(1, frame(leaf, sourceless())))
            self.assertEqual(classify(chain), SITES[leaf][2])
        for tail in (frame(2), sourceless(), 0, False, BSLNull.VALUE):
            self.assertEqual(classify(frame(1, sourceless(tail))), 'request_key')
        for changes in ({'module_name': MODULE}, {'initial_string': ' '}, {'line_number': 1}):
            self.assertEqual(classify(frame(1, replace(sourceless(), **changes))), 'request_key')

    def test_wrong_module_line_source_type_and_unavailable_fields_fail_unknown(self):
        good = frame(4)
        for changes in ({'module_name': ''}, {'module_name': MODULE + '.foreign'},
                        {'module_name': 'x' * 513}, {'line_number': 183},
                        {'line_number': 185}, {'line_number': 0},
                        {'initial_string': SITES[4][1] + ' '},
                        {'initial_string': ' ' + SITES[4][1]},
                        {'initial_string': SITES[4][1].replace('Key', 'Other')},
                        {'initial_string': 'x' * 129}):
            with self.subTest(changes=changes):
                self.assertEqual(classify(replace(good, **changes)), 'request_key')
        for name in ('modulename', 'linenumber', 'initialstring', 'cause'):
            self.assertEqual(classify(controlled(good, unavailable=(name,))), 'request_key')
        for name in ('modulename', 'linenumber', 'initialstring'):
            for value in (None, True, False, BSLNull.VALUE, Decimal('1.5')):
                self.assertEqual(classify(controlled(good, **{name: value})), 'request_key')
        for value in (False, True, Decimal(0), '', BSLNull.VALUE):
            self.assertEqual(classify(value), 'request_key')
            self.assertEqual(classify(replace(good, cause=value)), 'request_key')
        self.assertEqual(classify(controlled(good, linenumber=Decimal('184.5'))), 'request_key')
        self.assertEqual(classify(frame(1, replace(frame(2), module_name='foreign'))), 'request_key')

    def test_calibration_identity_offset_and_properties_fail_closed(self):
        good = frame(4)
        for changes in ({'description': 'wrong'}, {'module_name': ''},
                        {'module_name': 'other'}, {'module_name': 'x' * 513},
                        {'line_number': CALIBRATION_LINE - 1},
                        {'line_number': CALIBRATION_LINE + 1},
                        {'initial_string': CALIBRATION_SOURCE + ' '},
                        {'initial_string': ' ' + CALIBRATION_SOURCE}):
            with self.subTest(changes=changes):
                self.assertEqual(classify(good, calibration_value=calibration(**changes)), 'request_key')
        for name in ('description', 'modulename', 'linenumber', 'initialstring'):
            self.assertEqual(classify(good, calibration_value=controlled(calibration(), unavailable=(name,))), 'request_key')
            for value in (None, True, False, BSLNull.VALUE, Decimal('1.5')):
                self.assertEqual(classify(good, calibration_value=controlled(calibration(), **{name: value})), 'request_key')
        for value in (None, False, '', BSLNull.VALUE):
            self.assertEqual(classify(good, calibration_value=value), 'request_key')
        for offset in (-1, 1, 20):
            self.assertEqual(classify(good, source_offset=offset), 'request_key')

    def test_original_description_code_additional_are_never_read(self):
        saved = controlled(frame(4), unavailable=('description', 'code', 'additionalinformation'))
        self.assertEqual(classify(saved), 'request_key_current')

    def test_cycles_depth_overflow_and_unknown_tail_never_return_partial_match(self):
        loop = frame(2)
        object.__setattr__(loop, 'cause', loop)
        self.assertEqual(classify(loop), 'request_key')
        head = frame(0, frame(1, frame(2)))
        object.__setattr__(head.cause.cause, 'cause', head)
        self.assertEqual(classify(head), 'request_key')
        self.assertEqual(classify(frame(0, frame(1, frame(2, frame(2, sourceless()))))), 'request_key')
        unknown = BSLErrorInfo('PRIVATE', module_name=MODULE, line_number=500, initial_string='unmapped')
        self.assertEqual(classify(frame(0, frame(1, frame(2, unknown)))), 'request_key')
        self.assertEqual(classify(frame(0, frame(1, frame(2, frame(3))))), 'request_key')

    def test_actual_outer_catch_keeps_coarse_stage_on_helper_exception(self):
        vm, reader, output, module = integration.exercise_site('read_error')
        reader.position = -1
        reader.opened = reader.closed = False
        helper_calls = []
        def broken_helper(saved):
            helper_calls.append(saved)
            raise ValueError('PRIVATE DIAGNOSTIC FAILURE')
        del vm.routines['asyncrequestkeysite']
        vm.register_function('AsyncRequestKeySite', broken_helper)
        start = module.index('&НаКлиенте\nПроцедура ПриОткрытии')
        end = module.index('КонецПроцедуры', start) + len('КонецПроцедуры')
        vm.execute('\n' * module[:start].count('\n') + module[start:end], MODULE)
        vm.execute('Cancel = False; ПриОткрытии(Cancel);')
        self.assertEqual(len(helper_calls), 1)
        self.assertEqual(helper_calls[0].line_number, 168)
        self.assertEqual(output, ['ASYNC-ENTRY-FAILURE:request_key'])

    def test_actual_outer_catch_does_not_classify_other_stages(self):
        vm, reader, output, module = integration.exercise_site(None)
        reader.position = -1
        reader.opened = reader.closed = False
        reader.fault = 'request_open'
        calls = []
        del vm.routines['asyncrequestkeysite']
        vm.register_function('AsyncRequestKeySite', lambda saved: calls.append(saved))
        start = module.index('&НаКлиенте\nПроцедура ПриОткрытии')
        end = module.index('КонецПроцедуры', start) + len('КонецПроцедуры')
        vm.execute('\n' * module[:start].count('\n') + module[start:end], MODULE)
        vm.execute('Cancel = False; ПриОткрытии(Cancel);')
        self.assertEqual(calls, [])
        self.assertEqual(output, ['ASYNC-ENTRY-FAILURE:request_open'])


if __name__ == '__main__':
    unittest.main()
