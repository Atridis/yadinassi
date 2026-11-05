"""Offline diagnostic contracts: never run native code or alter acceptance."""
import copy
import json
import unittest
from unittest.mock import patch
from scripts import native_1c_demo_designer as demo


class XmlDiagnosticsTests(unittest.TestCase):
    def test_equal_signatures(self):
        value = demo.xml_diagnostic(b'<a>\n<b/>\n</a>', b'<a><b /></a>')
        self.assertEqual(value['comparison'], 'equal')
        self.assertEqual(value['counts'], [0] * 7)
        self.assertNotEqual(value['before_sha256'], value['after_sha256'])

    def test_namespace_only_is_not_acceptance(self):
        a, b = b'<a xmlns:x="one"/>', b'<a xmlns:x="two"/>'
        value = demo.xml_diagnostic(a, b)
        self.assertEqual(value['comparison'], 'namespace_only')
        self.assertEqual(value['counts'], [1, 0, 0, 0, 0, 0, 0])
        expected, actual = {'Configuration.xml': a}, {'Configuration.xml': b}
        self.assertEqual(demo.redump_mismatches(expected, actual), {'Configuration.xml': 'metadata_changed'})
        with self.assertRaises(demo.DemoError):
            demo.verify_redump(expected, actual)

    def test_structural_categories(self):
        value = demo.xml_diagnostic(b'<a version="1"><b>old</b></a>',
                                    b'<z version="2"><c>new</c><d/></z>')
        self.assertEqual(value['comparison'], 'expanded_tree')
        self.assertEqual(value['counts'], [0, 1, 1, 1, 1, 1, 2])
        self.assertEqual(demo.xml_diagnostic(b'<a xmlns="one"/>', b'<a xmlns="two"/>')['comparison'],
                         'namespace_and_tree')

    def test_qname_text_semantics_remain_unknown(self):
        value = demo.xml_diagnostic(b'<a xmlns:x="one">x:T</a>', b'<a xmlns:x="two">x:T</a>')
        self.assertEqual(value['comparison'], 'namespace_only')
        # Category describes signature components, never semantic equivalence.
        self.assertNotEqual(demo.xml_signature(b'<a xmlns:x="one">x:T</a>'),
                            demo.xml_signature(b'<a xmlns:x="two">x:T</a>'))

    def test_unavailable_and_malicious_input(self):
        for raw in (b'<!DOCTYPE a [<!ENTITY x "secret">]><a>&x;</a>', b'<a><?secret value?></a>',
                    b'<a>', b'\xff', '<a/>'.encode('utf-16'), b'<a xmlns:x="a"><b xmlns:x="b"/></a>'):
            with self.subTest(raw=raw):
                value = demo.xml_diagnostic(b'<a/>', raw)
                self.assertEqual(value['comparison'], 'unavailable')
                self.assertEqual(value['reason'], 'parse_rejected')
                self.assertEqual(value['counts'], [0] * 7)
        self.assertEqual(demo.xml_diagnostic(b'<a/>', None)['reason'], 'missing')

    def test_input_and_analysis_caps(self):
        value = demo.xml_diagnostic(b'<a/>', b'x' * (demo.DIAGNOSTIC_MAX_BYTES + 1))
        self.assertEqual(value['reason'], 'input_limit')
        self.assertIsNone(value['after_sha256'])
        inputs = (b'<a>' * 97 + b'</a>' * 97,
                  b'<a>' + b'<b/>' * 4096 + b'</a>',
                  b'<a>' + b'x' * 65537 + b'</a>',
                  b'<a ' + b' '.join(('x%d="v"' % i).encode() for i in range(4097)) + b'/>')
        for raw in inputs:
            with self.subTest(size=len(raw)):
                self.assertEqual(demo.xml_diagnostic(b'<a/>', raw)['reason'], 'analysis_limit')

    def test_counts_are_capped(self):
        a = b'<a>' + b'<b>x</b>x' * 4095 + b'</a>'
        b = b'<a>' + b'<b>y</b>y' * 4095 + b'</a>'
        value = demo.xml_diagnostic(a, b)
        self.assertEqual(value['counts'][4], 4096)
        self.assertEqual(value['comparison'], 'expanded_tree')

    def test_no_content_or_unknown_paths(self):
        expected = {'Configuration.xml': b'<secret attr="credential">private</secret>'}
        actual = {'Configuration.xml': b'<other attr="password">sensitive</other>', 'secret.xml': b'<x/>'}
        value = demo.xml_diagnostics(expected, actual, {'Configuration.xml': 'metadata_changed', 'secret.xml': 'metadata_changed'})
        encoded = json.dumps(value)
        for token in ('secret', 'credential', 'private', 'password', 'sensitive', 'other'):
            self.assertNotIn(token, encoded)
        self.assertEqual(len(value['files']), 1)
        self.assertEqual(value['files'][0]['file'], demo.XML_FILES.index('Configuration.xml'))

    def test_all_fifteen_and_budget(self):
        expected = {name: b'<a xmlns:x="one"/>' for name in demo.XML_FILES}
        actual = {name: b'<a xmlns:x="two"/>' for name in demo.XML_FILES}
        mismatches = demo.redump_mismatches(expected, actual)
        value = demo.xml_diagnostics(expected, actual, mismatches)
        self.assertEqual(value['state'], 'available')
        self.assertEqual(len(value['files']), 15)
        demo.validate_xml_diagnostics(value, mismatches)
        with patch.object(demo, 'DIAGNOSTIC_MAX_OUTPUT', 128):
            self.assertEqual(demo.xml_diagnostics(expected, actual, mismatches), {'state': 'budget_limit', 'files': []})

    def test_strict_validation(self):
        mismatches = {'Configuration.xml': 'metadata_changed'}
        value = demo.xml_diagnostics({'Configuration.xml': b'<a/>'}, {'Configuration.xml': b'<b/>'}, mismatches)
        demo.validate_xml_diagnostics(value, mismatches)
        mutations = [('file', True), ('file', 99), ('comparison', 'safe_to_accept'), ('comparison', 'equal'),
                     ('reason', 'raw log'), ('counts', [False]*7), ('counts', [4097]*7),
                     ('counts', [0]*7), ('before_sha256', 'raw XML'), ('after_sha256', None)]
        for key, item in mutations:
            bad = copy.deepcopy(value)
            bad['files'][0][key] = item
            with self.subTest(key=key, item=item), self.assertRaises(demo.DemoError):
                demo.validate_xml_diagnostics(bad, mismatches)
        for bad in ({'state': 'available', 'files': value['files'] * 2},
                    {'state': 'not_reached', 'files': value['files']},
                    {'state': 'available', 'files': []}, {**value, 'raw': 'secret'}):
            with self.assertRaises(demo.DemoError):
                demo.validate_xml_diagnostics(bad, mismatches)
        with self.assertRaises(demo.DemoError):
            demo.validate_xml_diagnostics(value, {})

    def test_report_budget_and_no_false_success(self):
        hashes = demo.inventory(demo.ROOT)
        expected = {name: b'<a/>' for name in demo.XML_FILES}
        actual = {name: b'<b/>' for name in demo.XML_FILES}
        mismatches = demo.redump_mismatches(expected, actual)
        report = dict(schema=demo.SCHEMA, nonce='a'*32, status='failed', phase='witness', failure='witness_mismatch',
                      input_sha256=hashes, redump_sha256={}, mismatches=mismatches,
                      xml_diagnostics=demo.xml_diagnostics(expected, actual, mismatches))
        raw = json.dumps(report, separators=(',', ':')).encode()
        self.assertLessEqual(len(raw), 16384)
        demo.validate_report(raw, 'a'*32, hashes)
        report.update(status='ok', phase='complete', failure='none',
                      redump_sha256={name: 'a'*64 for name in demo.SOURCE_FILES})
        with self.assertRaises(demo.DemoError):
            demo.validate_report(json.dumps(report).encode(), 'a'*32, hashes)
        with self.assertRaises(demo.DemoError):
            demo.validate_report(b' ' * 16385, 'a'*32, hashes)

    def test_unavailable_validation(self):
        name = 'Configuration.xml'
        mismatches = {name: 'missing_file'}
        value = demo.xml_diagnostics({name: b'<a/>'}, {}, mismatches)
        demo.validate_xml_diagnostics(value, mismatches)
        self.assertEqual(value['files'][0]['reason'], 'missing')
        for state in ('not_reached', 'budget_limit'):
            demo.validate_xml_diagnostics(dict(state=state, files=[]), mismatches)


if __name__ == '__main__':
    unittest.main()
