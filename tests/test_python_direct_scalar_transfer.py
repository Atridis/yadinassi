"""Exact scalar envelopes retain the recursive transfer contract."""
from decimal import Decimal
import unittest
from yadinassi.execution.direct.python_direct_server import transfer
from yadinassi.types.values import NULL, BSLArray

class ScalarTransferTests(unittest.TestCase):
    def test_fresh_envelope_and_immutable_identity(self):
        packet=[None,NULL,'text',True,False,Decimal('1.25')]
        result=transfer(packet)
        self.assertIsNot(result,packet)
        for before,after in zip(packet,result):self.assertIs(before,after)
        result.clear();self.assertEqual(len(packet),6)
        empty=[];self.assertIsNot(transfer(empty),empty)

    def test_root_included_in_budget(self):
        self.assertEqual(len(transfer([None]*9999)),9999)
        with self.assertRaises(ValueError):transfer([None]*10000)
        with self.assertRaises(ValueError):transfer([[None]*9999])

    def test_nested_and_canonical_containers_still_copy(self):
        child=[Decimal(2)];canonical=BSLArray();canonical.items=child
        result=transfer([child,child,canonical])
        self.assertIsNot(result[0],child);self.assertIsNot(result[0],result[1])
        self.assertIsNot(result[2],canonical);self.assertIsNot(result[2].items,child)
        result[0].append(None);self.assertEqual(child,[Decimal(2)])

    def test_exact_types_and_cycle_depth_rejection(self):
        class Text(str):pass
        class Packet(list):pass
        for packet in ([Text('x')],Packet([None]),[object()]):
            with self.assertRaises((TypeError,ValueError)):transfer(packet)
        cycle=[];cycle.append(cycle)
        with self.assertRaises(ValueError):transfer(cycle)
        deep=None
        for _ in range(66):deep=[deep]
        with self.assertRaises(ValueError):transfer(deep)
