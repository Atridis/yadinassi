"""Standalone synthetic Copy observer/grammar tests; never native evidence."""
import copy
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTree
from yadinassi.values import HostFunction
from scripts import native_1c_tree_copy_contract as wire

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'integrational_tests/measurements/tree_copy.bsl').read_text(encoding='utf-8')
HELPERS = SOURCE[:SOURCE.index('Сообщить("TC-P:')]


def emit_capture(source=SOURCE):
    output = []
    Interpreter(output.append).execute(source)
    return ('\n'.join(output) + '\n').encode('ascii')


# Synthetic fixture only; controls are not native wrapper identity answers.
PROBE_RECORD = b'TC-P: [TFTFTFTFTTFTTFTTFTTFTTF]\n'


def capture(main):
    return PROBE_RECORD + main


def emit(source=SOURCE):
    raw = emit_capture(source)
    if raw.startswith(b'TC-P: ['):
        from scripts.native_1c_tree_access_probe import split_capture
        return split_capture(raw)[1]
    return raw


def emit_missing_capture():
    """Explicit absent-method stub retains the observer's negative regression."""
    original = BSLValueTree.get_method
    def absent(tree, name):
        if name.casefold() in ('copy', 'скопировать'):
            raise ValueError('Метод не найден: ' + name)
        return original(tree, name)
    with patch.object(BSLValueTree, 'get_method', absent):
        return emit_capture()


def maximum_capture():
    return capture(maximum_output())


def synthetic_method(mode):
    original = BSLValueTree.get_method

    def get(tree, name):
        if name.casefold() not in ('copy', 'скопировать'):
            return original(tree, name)

        def action(*args):
            # Test harness only. Deliberately accepts case9's extra argument.
            if mode == 'identity':
                return tree
            result = copy.deepcopy(tree)
            if mode in ('shallow', 'outer'):
                def pairs(a, b):
                    for old, new in zip(a, b):
                        yield old, new
                        yield from pairs(old.rows, new.rows)
                arrays = {}
                for old, new in pairs(tree.rows, result.rows):
                    for old_col, new_col in zip(tree.columns.items, result.columns.items):
                        value = old.cells[old_col]
                        if type(value).__name__ == 'BSLArray':
                            if mode == 'shallow':
                                new.cells[new_col] = value
                            else:
                                if id(value) not in arrays:
                                    cloned = copy.copy(value)
                                    cloned.items = list(value.items)
                                    arrays[id(value)] = cloned
                                new.cells[new_col] = arrays[id(value)]
            return result
        return HostFunction(name, action)
    return get


def maximum_snapshot(case):
    cols, nodes, _ = wire.LIMITS[case-1]
    next_id = 2
    schema = ''
    for _ in range(cols):
        schema += wire.IDS[next_id] + 'aa9U99090290'; next_id += 1
    rows = ''
    for _ in range(nodes):
        node = wire.IDS[next_id]; children = node; next_id += 1
        rows += node + '_04' + children + '5' + 'N9____' * cols
    return '001' + str(cols) + schema + str(nodes) + rows


def maximum_output():
    lines = ['TC-C2: [-]']
    for case in range(1, 10):
        count = wire.LIMITS[case-1][2]
        lines.append(f'TC-{case}: [S/' + '/'.join([maximum_snapshot(case)] * count) + ']')
    return ('\n'.join(lines)+'\n').encode('ascii')


class CopyObserverTests(unittest.TestCase):
    def test_missing_copy_stub_is_honest_and_calibration_passes(self):
        from scripts.native_1c_tree_access_probe import split_capture
        raw = split_capture(emit_missing_capture())[1]
        result = wire.validate_output(raw)
        self.assertEqual([r['status'] for r in result], ['M'] * 9)
        self.assertEqual(len(raw), 2003)
        for r in result:
            self.assertEqual(r['snapshots'][0], r['snapshots'][1])
            self.assertIsNone(r['snapshots'][2])

    def test_synthetic_deep_copy_exercises_every_success_path(self):
        with patch.object(BSLValueTree, 'get_method', synthetic_method('deep')):
            raw = emit()
        results = wire.validate_output(raw)
        self.assertEqual([r['status'] for r in results], ['S'] * 9)
        self.assertEqual([len(r['snapshots']) for r in results], [x[2] for x in wire.LIMITS])
        c = results[6]['snapshots']
        self.assertNotEqual(c[1]['nodes'][0][6][0][1], c[2]['nodes'][0][6][0][1])
        self.assertEqual(c[2]['nodes'][0][6][0][1], c[2]['nodes'][1][6][0][1])
        self.assertNotEqual(c[2]['nodes'][0][6][0][1], c[2]['nodes'][2][6][0][1])
        self.assertEqual(c[3]['nodes'][0][6][0][3:], (1, 2))
        self.assertEqual(c[4]['nodes'][0][6][0][3:], (3, 2))
        self.assertEqual(c[6]['nodes'][0][6][0][3:], (3, 4))
        self.assertEqual(c[7]['nodes'][0][6][0][3:], (5, 2))

    def test_outer_and_nested_array_aliasing_are_distinguishable(self):
        results = {}
        for mode in ('deep', 'shallow', 'outer'):
            with patch.object(BSLValueTree, 'get_method', synthetic_method(mode)):
                result = wire.validate_output(emit())[6]['snapshots']
            results[mode] = result
        def cell(snaps, index):
            return snaps[index]['nodes'][0][6][0]
        for mode, snaps in results.items():
            before, copied = cell(snaps, 1), cell(snaps, 2)
            self.assertEqual(before[1] == copied[1], mode == 'shallow')
            self.assertEqual(before[2] == copied[2], mode != 'deep')
            self.assertEqual(cell(snaps, 3)[3], 3 if mode == 'shallow' else 1)
            self.assertEqual(cell(snaps, 5)[4], 2 if mode == 'deep' else 4)
        self.assertEqual(len({repr(v) for v in results.values()}), 3)

    def test_same_tree_return_is_not_fabricated_as_independent(self):
        # Case6 cannot mutate identical source/result schemas successfully;
        # examine the no-mutation case to establish observable identity.
        with patch.object(BSLValueTree, 'get_method', synthetic_method('identity')):
            raw = emit(HELPERS + 'Сообщить("TC-3: [" + TCProbe(3) + "]");')
        r = wire.validate_payload(raw[len(b'TC-3: ['):-2], 3)
        self.assertEqual(r['snapshots'][1], r['snapshots'][2])

    def test_exact_maximum_encoding_and_ascii_framing(self):
        raw = maximum_output()
        wire.validate_output(raw)
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertEqual(len(raw), 6746)
        self.assertLessEqual(len(raw), 8192)
        for case, line in enumerate(raw.splitlines(keepends=True)[1:], 1):
            self.assertEqual(len(line), wire.maximum_record_size(case))
            self.assertIsNotNone(re.fullmatch(rb'TC-[1-9]: \[[ -~]*\]\n', line))

    def test_ascii_json_marker_round_trip_and_bound(self):
        raw = maximum_output()
        marker = {'schema': 'tree-copy-v1', 'nonce': 'f' * 32,
                  'phase': 'completed', 'witness': 'client',
                  'values': raw.decode('ascii').splitlines()}
        encoded = json.dumps(marker, ensure_ascii=True, separators=(',', ':')).encode('ascii')
        self.assertLess(len(encoded), 16384)
        decoded = json.loads(encoded)
        restored = ('\n'.join(decoded['values']) + '\n').encode('ascii')
        self.assertEqual(restored, raw)
        wire.validate_output(restored)
        # Profile integration must still validate its actual native serializer.

    def test_lf_crlf_source_has_identical_local_ascii_output(self):
        self.assertEqual(emit(SOURCE), emit(SOURCE.replace('\n', '\r\n')))

    def test_word_codec_preserves_case_and_rejects_unknowns(self):
        vm = Interpreter(); vm.execute(HELPERS)
        self.assertTrue(vm.execute('TCExact("Payload", "Payload")'))
        self.assertFalse(vm.execute('TCExact("Payload", "payload")'))
        self.assertFalse(vm.execute('TCExact("a", "а")'))
        with self.assertRaises(Exception):
            vm.execute('TCWord("payload")')

    def test_wire_rejects_malformed_records(self):
        raw = maximum_output()
        mutations = [raw[:-1], raw+b'\n', raw.replace(b'\n',b'\r\n'),
                     raw.replace(b'TC-2:',b'TC-1:'), raw.replace(b'TC-C2: [-]',b'TC-C2: [E]'),
                     raw.replace(b'[S/',b'[X/',1), raw.replace(b'[S/001',b'[S/z01',1),
                     raw.replace(b'/001', b'/00_', 1), raw+b'x'*8192,
                     raw.replace(b'TC-9:', 'ТС-9:'.encode()),
                     raw.replace(b'N9____',b'N9___]',1)]
        for bad in mutations:
            with self.subTest(prefix=bad[:30]), self.assertRaises(wire.ObservationError):
                wire.validate_output(bad)

    def test_error_description_is_captured_in_original_handler(self):
        self.assertIn('Исключение\n            PrivateDescription = ОписаниеОшибки();\n            Status = TCError(PrivateDescription);', SOURCE)
        self.assertNotIn('TCError(ОписаниеОшибки())', SOURCE)

    def test_both_aliases_and_extra_argument_are_executed(self):
        calls = []
        original = BSLValueTree.get_method
        def get(tree, name):
            if name.casefold() in ('copy','скопировать'):
                def action(*args):
                    calls.append((name, args)); raise ValueError('synthetic private path /not/exported')
                return HostFunction(name, action)
            return original(tree, name)
        with patch.object(BSLValueTree, 'get_method', get):
            raw = emit()
        self.assertNotIn(b'not/exported', raw)
        self.assertEqual(len(calls), 9)
        self.assertEqual(calls[7], ('Скопировать', ()))
        self.assertEqual(len(calls[8][1]), 1)
        self.assertEqual([r['status'] for r in wire.validate_output(raw)], ['O']*9)


if __name__ == '__main__':
    unittest.main()
