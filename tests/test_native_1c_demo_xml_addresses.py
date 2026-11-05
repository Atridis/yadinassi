"""Offline source-address diagnostics; no Docker/native execution."""
import copy
import hashlib
import inspect
import json
import unittest
from scripts import native_1c_demo_designer as demo


class XmlAddressTests(unittest.TestCase):
    def detail(self, before, after):
        return demo.xml_diagnostic(before, after)

    def kinds(self, value):
        return [demo.ADDRESS_KINDS[item[1]] for item in value['addresses']]

    def validate(self, value, before):
        demo.validate_xml_diagnostics({'state': 'available', 'files': [dict(file=9, **value)]},
                                      {'Configuration.xml': 'metadata_changed'},
                                      {'Configuration.xml': before})

    def test_unique_insert_does_not_cascade(self):
        before = b'<r><a>same</a><b>same</b></r>'
        value = self.detail(before, b'<r><new>private</new><a>same</a><b>same</b></r>')
        self.assertEqual(value['addresses'], [[0, 5, 0, 1]])
        self.validate(value, before)

    def test_unique_reorder_still_fails_acceptance(self):
        before, after = b'<r><a/><b/></r>', b'<r><b/><a/></r>'
        value = self.detail(before, after)
        self.assertEqual(value['addresses'], [[0, 7, 0, 1]])
        self.assertEqual(demo.redump_mismatches({'Configuration.xml': before},
                                               {'Configuration.xml': after}),
                         {'Configuration.xml': 'metadata_changed'})

    def test_repeated_group_is_ambiguous(self):
        before, after = b'<r><a>one</a><a>two</a><b/></r>', b'<r><a>two</a><a>one</a><b/></r>'
        value = self.detail(before, after)
        self.assertEqual(value['addresses'], [[1, 8, 0, 2]])
        self.validate(value, before)
        # Moving an unchanged repeated group relative to another name is visible.
        moved = self.detail(b'<r><a/><b/><a/></r>', b'<r><a/><a/><b/></r>')
        self.assertEqual(moved['addresses'], [[0, 7, 0, 1]])
        inserted = self.detail(b'<r><a/><b/><a/></r>', b'<r><a/><a/><b/><new/></r>')
        self.assertIn([0, 5, 0, 1], inserted['addresses'])
        self.assertIn([0, 7, 0, 1], inserted['addresses'])

    def test_preorder_and_source_attribute_slots(self):
        before = b'<r version="1"><a/><b z="remove" a="before">old</b></r>'
        value = self.detail(before, b'<r version="2"><a/><b a="after" new="secret">new</b></r>')
        self.assertIn([2, 0, 0, 1], value['addresses'])
        self.assertIn([2, 1, 1, 1], value['addresses'])
        self.assertIn([2, 2, 0, 1], value['addresses'])
        self.assertIn([2, 3, 0, 1], value['addresses'])
        self.assertEqual(value['addresses'][-1], [0, 0, 0, 1])
        self.validate(value, before)

    def test_removed_node_and_tail_are_source_addressed(self):
        before = b'<r><a/>before<b><c/></b></r>'
        value = self.detail(before, b'<r><a/>after</r>')
        self.assertIn([2, 6, 0, 1], value['addresses'])
        self.assertIn([1, 4, 0, 1], value['addresses'])
        self.validate(value, before)

    def test_changed_root_stops_identity_claims(self):
        value = self.detail(b'<a><c>one</c></a>', b'<b><c>two</c></b>')
        self.assertEqual(value['addresses'], [[0, 9, 0, 1]])
        namespaced = self.detail(b'<a xmlns="one"><c/></a>', b'<a xmlns="two"><c/></a>')
        self.assertEqual(namespaced['addresses'], [[0, 9, 0, 1]])
        namespace_only = self.detail(b'<a xmlns:x="one"/>', b'<a xmlns:x="two"/>')
        self.assertEqual(namespace_only['addresses'], [])
        self.assertEqual(namespace_only['omitted'], 0)

    def test_no_native_values_or_names_exported(self):
        before = b'<root source="known"><public/></root>'
        value = self.detail(before, b'<root source="PASSWORD" TOKEN="SECRET"><PRIVATE>MEDICAL</PRIVATE></root>')
        encoded = json.dumps(value)
        for token in ('PASSWORD', 'TOKEN', 'SECRET', 'PRIVATE', 'MEDICAL', 'root', 'public', 'known'):
            self.assertNotIn(token, encoded)
        self.validate(value, before)

    def test_local_detail_cap_prioritizes_structure(self):
        before = b'<r version="1">' + b''.join(('<n%d a="x"/>' % i).encode() for i in range(30)) + b'</r>'
        after = b'<r version="2"><extra/>' + b''.join(('<n%d a="y"/>' % i).encode() for i in range(30)) + b'</r>'
        value = self.detail(before, after)
        self.assertEqual(len(value['addresses']), 12)
        self.assertEqual(value['omitted'], 20)
        self.assertEqual(value['addresses'][0], [0, 5, 0, 1])
        self.assertNotIn([0, 0, 0, 1], value['addresses'])
        self.validate(value, before)

    def test_global_budget_preserves_all_file_summaries(self):
        before = b'<r>' + b''.join(('<n%d a="x"/>' % i).encode() for i in range(30)) + b'</r>'
        after = before.replace(b'"x"', b'"y"')
        expected = {name: before for name in demo.XML_FILES}
        actual = {name: after for name in demo.XML_FILES}
        mismatches = demo.redump_mismatches(expected, actual)
        value = demo.xml_diagnostics(expected, actual, mismatches)
        self.assertEqual(value['state'], 'available')
        self.assertEqual(len(value['files']), 15)
        self.assertLessEqual(len(json.dumps(value, separators=(',', ':')).encode()), 6144)
        self.assertTrue(all(item['addresses'] and item['omitted'] > 0 for item in value['files']))
        demo.validate_xml_diagnostics(value, mismatches, expected)

    def test_strict_address_validation(self):
        before = b'<r a="one"><b/></r>'
        value = self.detail(before, b'<r a="two"><b>changed</b></r>')
        for entry in ([True, 0, 0, 1], [2, 3, 0, 1], [0, 10, 0, 1], [0, 0, 1, 1],
                      [1, 0, 0, 1], [0, 3, 1, 1], [0, 3, 0, 2], [0, 5, 0, 4097],
                      [0, 3, 0, False], ['raw', 3, 0, 1], [0, 3, 0]):
            bad = copy.deepcopy(value)
            bad['addresses'] = [entry]
            with self.subTest(entry=entry), self.assertRaises(demo.DemoError):
                self.validate(bad, before)
        for addresses, omitted in ((value['addresses'] * 2, 0), ([], 0), ([], True), ([], -1),
                                   ([], 32769), (value['addresses'], 32768)):
            bad = dict(value, addresses=addresses, omitted=omitted)
            with self.subTest(addresses=addresses, omitted=omitted), self.assertRaises(demo.DemoError):
                self.validate(bad, before)

    def test_unavailable_and_namespace_only_cannot_claim_addresses(self):
        for after in (None, b'<!DOCTYPE a><a/>', b'<a xmlns:x="two"/>'):
            before = b'<a xmlns:x="one"/>'
            value = self.detail(before, after)
            for fields in ({'addresses': [[0, 9, 0, 1]]}, {'omitted': 1}):
                with self.assertRaises(demo.DemoError):
                    self.validate(dict(value, **fields), before)

    def test_report_envelope_for_real_source_with_synthetic_differences(self):
        expected = demo.source_files()
        # Exact source IDs remain host-valid. Native content is synthetic here.
        actual = {name: raw.replace(b'version="2.17"', b'version="2.99"') if name.endswith('.xml') else raw
                  for name, raw in expected.items()}
        # Ensure all XML differ even if version spelling changes in the fixture.
        for name in demo.XML_FILES:
            actual[name] = b'<changed />'
        mismatches = demo.redump_mismatches(expected, actual)
        report = dict(schema=demo.SCHEMA, nonce='a'*32, status='failed', phase='witness',
                      failure='witness_mismatch', input_sha256=demo.inventory(demo.ROOT), redump_sha256={},
                      mismatches=mismatches, xml_diagnostics=demo.xml_diagnostics(expected, actual, mismatches))
        raw = json.dumps(report, separators=(',', ':')).encode()
        self.assertLessEqual(len(raw), 16384)
        demo.validate_report(raw, 'a'*32, report['input_sha256'])

    def test_acceptance_functions_unchanged(self):
        expected = ACCEPTANCE_HASHES
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256(inspect.getsource(getattr(demo, name)).encode()).hexdigest(), digest)


ACCEPTANCE_HASHES = {'xml_signature': '115d702ba02c09a8a39c3217e92bf2b66e04eab4a72e5aaea057986162ab62b5', 'redump_mismatches': '96a7c04fe4ea20509e2ba3549c33e12404d1e017f71b9463d75581476ebdab45', 'verify_redump': '43c07c864d42242a3fe66007c40ee682c526c81935b1e7699070aff38c5809bd', 'operations': 'a954dc5919b3eae09aed8e7b38640ba21efd1d79d7d4f91ed7f22a836cf8f767', 'container_command': '4e6e92f80f9dde06bf46f942ed0e3ce6e119da79c8e7595d9c49c8bd326298bb'}

if __name__ == '__main__':
    unittest.main()
