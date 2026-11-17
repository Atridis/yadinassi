"""Private direct accounting preserves source temporary values, not copies."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import value_storage as snapshots, temporary_storage as storage
from yadinassi.experimental_naked_structure import new_structure, _DirectStructure
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLArray
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.configuration_source_runtime import SourceApplication
from test_source_server_call import configuration


class DirectTemporaryCaptureTests(unittest.TestCase):
    def test_default_capture_stays_closed(self):
        for value in ([], new_structure('Key', None)):
            with self.assertRaises(snapshots.SnapshotError): snapshots.capture(value)
            snapshots.capture(value, _source_direct=True)

    def test_same_accounting_and_shared_occurrences(self):
        child = new_structure('Key', Decimal(7))
        native_child = BSLStructure('Key', Decimal(7))
        native = BSLArray(); native.items = [native_child, native_child]
        direct = snapshots.capture([child, child], _source_direct=True)
        ordinary = snapshots.capture(native)
        self.assertEqual(direct._root, ordinary._root)
        self.assertEqual(storage._cost(direct), storage._cost(ordinary))

    def test_cycles_subclasses_and_malformed_fields_no_callbacks(self):
        values = []; values.append(values)
        structure = new_structure('Key', values); values[0] = structure
        with self.assertRaises(snapshots.SnapshotError): snapshots.capture(values, _source_direct=True)
        class EvilList(list):
            def __iter__(self): raise AssertionError('callback')
        class EvilStructure(_DirectStructure):
            def items(self): raise AssertionError('callback')
        for value in (EvilList(), EvilStructure()):
            with self.assertRaises(snapshots.SnapshotError): snapshots.capture(value, _source_direct=True)
        malformed = new_structure('Key', None)
        dict.__setitem__(malformed, 'key', ['Key', None])
        with self.assertRaises(snapshots.SnapshotError): snapshots.capture(malformed, _source_direct=True)

    def test_existing_node_depth_text_limits(self):
        with patch.object(snapshots, 'MAX_NODES', 3):
            with self.assertRaises(snapshots.SnapshotError): snapshots.capture([None]*3, _source_direct=True)
        with patch.object(snapshots, 'MAX_DEPTH', 1):
            with self.assertRaises(snapshots.SnapshotError): snapshots.capture([[None]], _source_direct=True)
        with patch.object(snapshots, 'MAX_TEXT_UNITS', 2):
            with self.assertRaises(snapshots.SnapshotError): snapshots.capture(new_structure('Long', None), _source_direct=True)

    def test_store_identity_remeasurement_and_failed_replace_atomicity(self):
        app = SourceApplication(configuration(''), output=lambda _: None)
        self.addCleanup(app.close); app.start()
        vm = app.interpreter; vm._context_stack.append('server')
        try:
            retained = [new_structure('Key', None)]
            store = app.temporary_storage
            address = store.put(vm, retained, BSLUUID())
            self.assertIs(store.get(vm, address), retained)
            retained.append('later')
            self.assertIs(store.get(vm, address), retained)
            before = (store._entries.copy(), store._units, store._nodes)
            with patch.object(storage, 'capture', side_effect=ValueError('capture failed')):
                with self.assertRaisesRegex(ValueError, 'capture failed'):
                    store.put(vm, [], address)
            self.assertEqual((store._entries, store._units, store._nodes), before)
            retained.append(retained)
            with self.assertRaises(snapshots.SnapshotError): store.get(vm, address)
            self.assertEqual((store._entries, store._units, store._nodes), before)
        finally:
            vm._context_stack.pop()
