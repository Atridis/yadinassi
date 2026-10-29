"""Direction, all-bit preservation, strict admission and bounded diagnostics."""
import importlib.util
from pathlib import Path
import random
import unittest
from uuid import UUID

# Load the storage boundary itself, without initializing the interpreter.
PATH = Path(__file__).resolve().parents[1] / 'yadinassi/storage/catalog_reference_uuid.py'
SPEC = importlib.util.spec_from_file_location('catalog_reference_uuid_boundary', PATH)
codec = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codec)
decode = codec.decode_catalog_reference_uuid
encode = codec.encode_catalog_reference_uuid


class CatalogUUIDTests(unittest.TestCase):
    def test_two_distinct_byte_vectors(self):
        # Fixed expected physical bytes, not computed by the implementation.
        # Derived from the accepted paired native permutation observations;
        # these synthetic constants are not retained private native witnesses.
        vectors = (
            ('00112233-4455-4677-8899-aabbccddeeff',
             '8899aabbccddeeff4677445500112233'),
            ('d3a17c09-e652-4b8f-95c0-2e74b836fa61',
             '95c02e74b836fa614b8fe652d3a17c09'),
        )
        for canonical, physical_hex in vectors:
            with self.subTest(canonical=canonical):
                value, physical = UUID(canonical), bytes.fromhex(physical_hex)
                self.assertEqual(decode(physical), value)
                self.assertEqual(encode(value), physical)
                self.assertNotEqual(physical, value.bytes)
                self.assertNotEqual(physical, value.bytes_le)

    def test_all_128_bit_basis_vectors_in_each_direction(self):
        # Independently stated physical index for each canonical byte index.
        physical_positions = (12, 13, 14, 15, 10, 11, 8, 9,
                              0, 1, 2, 3, 4, 5, 6, 7)
        for canonical_index, physical_index in enumerate(physical_positions):
            for bit in range(8):
                with self.subTest(byte=canonical_index, bit=bit):
                    c, p = bytearray(16), bytearray(16)
                    c[canonical_index] = p[physical_index] = 1 << bit
                    self.assertEqual(decode(bytes(p)).bytes, bytes(c))
                    self.assertEqual(encode(UUID(bytes=bytes(c))), bytes(p))

    def test_two_sided_inverse_seeded_samples(self):
        generator = random.Random(146)
        for _ in range(1024):
            physical = generator.getrandbits(128).to_bytes(16, 'big')
            value = UUID(int=generator.getrandbits(128))
            self.assertEqual(encode(decode(physical)), physical)
            self.assertEqual(decode(encode(value)), value)

    def test_zero_and_all_ones_are_algebra_not_storage_semantics(self):
        for byte in (0, 255):
            physical = bytes([byte]) * 16
            value = UUID(bytes=physical)
            self.assertEqual(decode(physical), value)
            self.assertEqual(encode(value), physical)
            self.assertIs(type(decode(physical)), UUID)
            self.assertIs(type(encode(value)), bytes)

    def assert_code(self, function, value, code):
        with self.assertRaises(codec.CatalogUUIDError) as error:
            function(value)
        self.assertEqual(error.exception.code, code)
        self.assertEqual(error.exception.args, (code,))
        self.assertEqual(str(error.exception), code)

    def test_exact_bytes_admission_without_conversion_hooks(self):
        class BytesChild(bytes):
            pass
        class Explosive:
            def __bytes__(self):
                raise AssertionError('must not coerce')
            def __repr__(self):
                raise AssertionError('must not disclose')
        for value in (None, True, 16, 'private', [], tuple(range(16)),
                      bytearray(16), memoryview(bytes(16)), BytesChild(bytes(16)),
                      Explosive()):
            self.assert_code(decode, value, 'bytes_type')
        for length in (0, 1, 15, 17, 1024):
            self.assert_code(decode, bytes(length), 'bytes_length')

    def test_exact_uuid_admission(self):
        class UUIDChild(UUID):
            pass
        for value in (None, True, 0, bytes(16), bytearray(16),
                      str(UUID(int=0)), UUIDChild(int=0)):
            self.assert_code(encode, value, 'uuid_type')

    def test_malformed_exact_uuid_has_finite_diagnostic(self):
        self.assert_code(encode, object.__new__(UUID), 'uuid_value')
        class IntegerChild(int):
            pass
        for integer in (None, True, -1, 1 << 128, 'private', IntegerChild(1)):
            value = UUID(int=0)
            object.__setattr__(value, 'int', integer)
            self.assert_code(encode, value, 'uuid_value')

    def test_diagnostic_constructor_is_closed(self):
        for code in codec.CatalogUUIDError.codes:
            self.assertEqual(codec.CatalogUUIDError(code).args, (code,))
        for code in (None, [], {}, 'private'):
            with self.assertRaises(ValueError) as error:
                codec.CatalogUUIDError(code)
            self.assertEqual(str(error.exception), 'invalid catalog UUID diagnostic')

    def test_only_stdlib_import(self):
        import ast
        tree = ast.parse(PATH.read_text(encoding='utf-8'))
        imports = [node for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertEqual(len(imports), 1)
        self.assertIsInstance(imports[0], ast.ImportFrom)
        self.assertEqual(imports[0].module, 'uuid')
        self.assertEqual([alias.name for alias in imports[0].names], ['UUID'])


if __name__ == '__main__':
    unittest.main()
