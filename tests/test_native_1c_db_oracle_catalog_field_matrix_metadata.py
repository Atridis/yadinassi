"""Closed fixture construction tests; not native Number-code compatibility."""
from pathlib import Path, PurePosixPath
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/native_1c_db_oracle'))
import test_native_1c_db_oracle_metadata as original
m, NONCE = original.m, original.NONCE
import catalog_field_matrix as matrix


class MatrixMetadataTest(unittest.TestCase):
    setUp = original.MetadataTest.setUp
    mutate = original.MetadataTest.mutate
    def matrix_inject(self):
        return m.inject(self.source, self.target, nonce=NONCE,
                        evidence=PurePosixPath('/tmp/onec-db-oracle/evidence'), catalog_field_matrix=True)

    def test_fixed_profiles_empty_and_no_extra_rights(self):
        self.matrix_inject()
        m.inspect(self.target, 1, catalog_field_matrix=True)
        for name, kind in matrix.VARIANTS:
            _, xml = m.read_xml(self.target / f'Catalogs/{name}.xml')
            catalog = m.single(xml, 'Catalog')
            props = m.single(catalog, 'Properties')
            self.assertEqual(m.single(props, 'CodeLength').text, '2')
            self.assertEqual(m.single(props, 'CodeType').text, kind)
            self.assertEqual(m.single(props, 'DescriptionLength').text, '16')
            self.assertEqual(list(m.single(catalog, 'ChildObjects')), [])
            for role in (m.SETUP_ROLE, m.CRUD_ROLE):
                self.assertNotIn(name, (self.target / f'Roles/{role}/Ext/Rights.xml').read_text())
        server = self.target / m.MODULE_FILES['NativeOracleServer.bsl']
        old = m._module('NativeOracleServer.bsl', NONCE, '/tmp/onec-db-oracle/evidence')
        self.assertEqual(server.read_bytes(), matrix.server_module(old, m.DraftError))
        self.assertEqual(server.read_text(encoding='utf-8-sig').count('Объект.Код = "K1"'), 1)
        with self.assertRaises(m.DraftError):
            m.inspect(self.target, 1)

    def test_matrix_promotion_changes_only_original_payload(self):
        self.matrix_inject()
        before = m._hashes(self.target)
        v2 = self.root / 'matrix-v2'
        m.promote_v2(self.target, v2, catalog_field_matrix=True)
        after = m._hashes(v2)
        self.assertEqual([n for n in before if before[n] != after[n]], ['Catalogs/NativeOracleItems.xml'])
        m.verify_redump(v2, v2, 2, catalog_field_matrix=True)

    def test_missing_extra_rejected(self):
        self.matrix_inject()
        (self.target / next(iter(matrix.FILES))).unlink()
        with self.assertRaises(m.DraftError): m.inspect(self.target, 1, catalog_field_matrix=True)

    def test_extra_scalar_change_rejected(self):
        self.matrix_inject()
        path = 'Catalogs/NativeOracleNumberDescription.xml'
        self.mutate(self.target, path, '<CodeLength>2</CodeLength>', '<CodeLength>3</CodeLength>')
        with self.assertRaises(m.DraftError): m.inspect(self.target, 1, catalog_field_matrix=True)

    def test_extra_uuid_collision_rejected(self):
        self.matrix_inject()
        a, b = [self.target / f'Catalogs/{name}.xml' for name, _ in matrix.VARIANTS]
        _, left = m.read_xml(a)
        _, right = m.read_xml(b)
        old = m.single(right, 'Catalog').attrib['uuid']
        new = m.single(left, 'Catalog').attrib['uuid']
        self.mutate(self.target, b.relative_to(self.target), old, new)
        with self.assertRaises(m.DraftError): m.inspect(self.target, 1, catalog_field_matrix=True)

    def test_matrix_exact_shape_rejects_expansion(self):
        self.matrix_inject()
        path = self.target / 'Catalogs/NativeOracleStringDescription.xml'
        before = path.read_bytes()
        edits = ((b'<DescriptionLength>16</DescriptionLength>', b'<DescriptionLength>17</DescriptionLength>'),
                 (b'<ChildObjects/>', b'<ChildObjects><Unexpected/></ChildObjects>'),
                 (b'<Hierarchical>false</Hierarchical>', b'<Hierarchical>true</Hierarchical>'),
                 (b'CatalogObject.NativeOracleStringDescription', b'CatalogObject.NativeOracleNumberDescription'))
        for old, new in edits:
            with self.subTest(anchor=old):
                self.assertIn(old, before)
                path.write_bytes(before.replace(old, new, 1))
                with self.assertRaises(m.DraftError):
                    m.inspect(self.target, 1, catalog_field_matrix=True)
                path.write_bytes(before)
        rights = self.target / f'Roles/{m.CRUD_ROLE}/Ext/Rights.xml'
        rights.write_bytes(rights.read_bytes().replace(b'Catalog.NativeOracleItems',
                          b'Catalog.NativeOracleStringDescription'))
        with self.assertRaises(m.DraftError):
            m.inspect(self.target, 1, catalog_field_matrix=True)

    def test_fixed_transform_does_not_silently_accept_anchor_changes(self):
        with self.assertRaises(m.DraftError): matrix.server_module(b'no count guard', m.DraftError)
        with self.assertRaises(m.DraftError): matrix.server_module(
            ('Метаданные.Справочники.Количество() <> 1' * 2).encode(), m.DraftError)
        with self.assertRaises(m.DraftError):
            matrix.catalog(b'<ChildObjects/>', *matrix.VARIANTS[0], m.DraftError)

    def test_unknown_fixed_selector_rejected(self):
        for value in (None, 1, 'true'):
            with self.subTest(value=value), self.assertRaises(m.DraftError):
                m.inject(self.source, self.target, nonce=NONCE,
                         evidence=PurePosixPath('/tmp/onec-db-oracle/evidence'), catalog_field_matrix=value)
        with self.assertRaises(m.DraftError):
            matrix.catalog(b'', 'other', 'String', m.DraftError)


if __name__ == '__main__':
    unittest.main()
