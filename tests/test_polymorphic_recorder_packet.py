"""Offline authored-packet checks, not native observations or runtime parity."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from polymorphic_recorder_behavior import route, fixture

class PolymorphicRecorderPacketTests(unittest.TestCase):
    nonce = '0123456789abcdef' * 2

    def wire(self, values=None):
        values = ['OK:R,1;I,1;'] * 8 if values is None else values
        lines = ['entered'] + [str(n)+'|'+v for n,v in enumerate(values,1)] + ['completed']
        return ('\n'.join('PRQ|'+self.nonce+'|'+v for v in lines)+'\n').encode()

    def test_source_pin_and_eight_groups(self):
        raw = route.source()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), route.SOURCE_SHA256)
        self.assertEqual(raw.count(b'For CaseNo = 1 To 8 Do'),1)
        for n in range(1,9): self.assertIn(('CaseNo='+str(n)+' Then').encode(), raw)

    def test_program_has_exact_lifecycle_markers(self):
        raw = route.program({}, self.nonce)
        self.assertEqual(raw.count(('PRQ|'+self.nonce+'|entered').encode()),1)
        self.assertEqual(raw.count(('PRQ|'+self.nonce+'|completed').encode()),1)
        self.assertLess(raw.index(b'|entered'),raw.index(b'P=Setup();'))

    def test_nonce_is_exact_bounded_hex(self):
        for n in [None,1,'a'*31,'A'*32,'a'*33,'x'*32]:
            with self.subTest(n=n), self.assertRaises(ValueError): route.program({},n)

    def test_roundtrip_and_normalized_report_excludes_nonce(self):
        values = route.parse_wire(self.wire(), self.nonce)
        report = route.normalized(self.wire(),self.nonce)
        self.assertEqual(report['groups'],values)
        self.assertNotIn(self.nonce,json.dumps(report))
        self.assertFalse(report['runtime_parity_claimed'])

    def test_missing_extra_duplicate_and_wrong_order_refused(self):
        raw=self.wire(); lines=raw.splitlines()
        for bad in [b'\n'.join(lines[:-1]), b'\n'.join(lines+[lines[-1]]),
                    raw.replace(b'|2|',b'|1|'),raw.replace(b'|1|',b'|9|')]:
            with self.assertRaises(ValueError): route.parse_wire(bad,self.nonce)

    def test_foreign_nonce_and_nonascii_refused(self):
        for bad in [self.wire().replace(self.nonce.encode(),b'f'*32),self.wire()+b'\xff']:
            with self.assertRaises(ValueError):route.parse_wire(bad,self.nonce)

    def test_budgets_and_raw_diagnostic_text_refused(self):
        for value in ['', 'X'*2049,'/tmp/private','secret=value','кириллица','line\nbreak']:
            with self.assertRaises(ValueError):route.canonical([value]*8)
        with self.assertRaises(ValueError):route.parse_wire(b'x'*32769,self.nonce)

    def test_errors_remain_observations_not_parity(self):
        report=route.normalized(self.wire(['ERR']*8),self.nonce)
        self.assertTrue(report['measurement_complete'])
        self.assertEqual(report['groups'],['ERR']*8)
        self.assertFalse(report['runtime_parity_claimed'])

    def test_observer_mutation_refused(self):
        with mock.patch.object(Path,'read_bytes',return_value=b'changed'):
            with self.assertRaises(ValueError):route.source()

    def test_symlink_source_refused(self):
        with mock.patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(ValueError):route.source()

    def test_fixture_reuses_pinned_layout_without_mutating_old_observer(self):
        setup,assets=fixture.inventory.load_saved();before=dict(assets)
        own_setup,own=fixture.load_saved()
        self.assertEqual(setup,own_setup);self.assertEqual(assets,before)
        self.assertEqual({k:v for k,v in own.items() if k!='generated/observe.bsl'},
                         {k:v for k,v in assets.items() if k!='generated/observe.bsl'})
        self.assertNotEqual(own['generated/observe.bsl'],assets['generated/observe.bsl'])
        self.assertIs(fixture.verify_redump,fixture.inventory.verify_redump)

    def test_source_covers_owned_identity_and_schema_controls(self):
        raw=route.source()
        for token in [b'SetNewObjectRef',b'M.GetRef(New UUID(',b'BeginTransaction()',b'RollbackTransaction()',
                      b'GROUP BY S.Recorder',b'LEFT JOIN Document.Receipt',b'UNION ALL',b'ISNULL(',
                      b'D.Types()',b'D.ContainsType',b'WHERE FALSE',b'ORDER BY S.Recorder DESC']:
            self.assertIn(token,raw)
        self.assertNotIn(b'ErrorDescription',raw)
        types=raw.split(b'Function Types(',1)[1].split(b'EndFunction',1)[0]
        self.assertEqual(types.count(b'Except'),1)
        self.assertLess(types.index(b'EndTry;'),types.index(b'If T.Count()>16'))
        self.assertLess(types.index(b'If T.Count()>16'),types.index(b'D=T.Columns[0].ValueType'))
        self.assertLess(types.index(b'EndTry;'),types.index(b'D.Types()'))
