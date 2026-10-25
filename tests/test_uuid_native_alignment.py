"""PR112 run40240060498 observations, plus separately labeled local bounds."""
import unittest
from yadinassi import Interpreter, BSLError
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.serialization import value_to_string_internal, value_from_string_internal
from yadinassi.xml_values import xml_string, xml_value
from yadinassi.values import BSLType, BSLArray
from yadinassi.type_descriptions import BSLTypeDescription

FIXED = "01234567-89ab-4cde-8f01-23456789abcd"
ZERO = "00000000-0000-0000-0000-000000000000"
GUID = "fc01b5df-97fe-449b-83d4-218a090e681e"

class UUIDNativeAlignmentTests(unittest.TestCase):
    def test_observed_spaced_type_display_not_lookup_alias(self):
        vm = Interpreter(lambda _: None)
        for name in ('UUID', 'УникальныйИдентификатор'):
            self.assertEqual(str(vm.execute(f'Type("{name}")')), 'Уникальный идентификатор')
        for name in ('UniqueIdentifier', 'Уникальный идентификатор'):
            with self.assertRaises(BSLError): vm.execute(f'Type("{name}")')

    def test_observed_singleton_descriptor_adjustments(self):
        d = BSLTypeDescription('УникальныйИдентификатор')
        self.assertEqual(d.types, (BSLType.UUID,))
        self.assertEqual(d.get_types().items, [BSLType.UUID])
        self.assertTrue(d.contains_type(BSLType.UUID))
        self.assertEqual(str(d.adjust_value()), ZERO)
        self.assertEqual(str(d.adjust_value(None)), ZERO)
        self.assertEqual(str(d.adjust_value(FIXED)), ZERO)  # not string-to-UUID parsing
        value = BSLUUID(FIXED)
        self.assertEqual(d.adjust_value(value), value)

    def test_local_unmeasured_descriptor_boundaries_fail_closed(self):
        d = BSLTypeDescription('UUID')
        for value in [False, 0, [], {}, object(), '', 'not-a-guid']:
            with self.subTest(value=type(value)), self.assertRaises((ValueError, TypeError)):
                d.adjust_value(value)
        for source in ('UUID,String', 'Number,UUID', 'UUID,Null'):
            with self.assertRaises(ValueError): BSLTypeDescription(source)
        with self.assertRaises(ValueError): BSLTypeDescription(d)
        with self.assertRaises(ValueError): BSLTypeDescription('UUID', None)
        a = BSLArray(); a.items = [BSLType.UUID]
        with self.assertRaises(ValueError): BSLTypeDescription(a)
        with self.assertRaises(ValueError): value_to_string_internal(d)
        vm = Interpreter(lambda _: None)
        for collection in ('ValueTable', 'ValueTree'):
            vm.execute(f't = New {collection}; d = New TypeDescription("UUID");')
            with self.assertRaises(BSLError): vm.execute('t.Columns.Add("ID", d)')
            self.assertEqual(vm.execute('t.Columns.Count()'), 0)

    def test_observed_fixed_zero_scalar_streams_and_roundtrips(self):
        for text in (FIXED, ZERO):
            value = BSLUUID(text)
            expected = '{"#",' + GUID + ',' + text + '}'
            self.assertEqual(value_to_string_internal(value), expected)
            self.assertEqual(value_from_string_internal(expected), value)
            self.assertEqual(xml_string(value), text)
            self.assertEqual(xml_value(BSLType.UUID, text), value)
        self.assertEqual(value_to_string_internal(BSLType.UUID), '{"T",' + GUID + '}')

    def test_local_scalar_model_not_two_hardcoded_observed_blobs(self):
        # Algorithmic extrapolation of canonical grammar, not extra native data.
        for text in ('ffffffff-ffff-ffff-ffff-ffffffffffff',
                     'fedcba98-7654-4321-9876-0123456789ab'):
            value = BSLUUID(text)
            self.assertEqual(value_from_string_internal(value_to_string_internal(value)), value)
            self.assertEqual(xml_value(BSLType.UUID, xml_string(value)), value)

    def test_unmeasured_noncanonical_codec_inputs_fail_closed(self):
        for text in [FIXED.upper(), ' '+FIXED, FIXED+' ', '{'+FIXED+'}',
                     FIXED.replace('-', ''), FIXED[:-1]+'g', '', 'x'*10000]:
            with self.subTest(text=text[:40]):
                with self.assertRaises((TypeError, ValueError)): xml_value(BSLType.UUID, text)
                # Existing stream parser permits separator whitespace; it is
                # syntax, not part of an unquoted UUID atom. XML has no such layer.
                if text == text.strip():
                    with self.assertRaises((TypeError, ValueError)):
                        value_from_string_internal('{"#",'+GUID+','+text+'}')
        for text in ['{"#",'+GUID+'}', '{"#",'+GUID+',"'+FIXED+'"}',
                     '{"#",'+GUID+','+FIXED+',0}', '{"T",'+GUID+'}',
                     '{"#",00000000-0000-0000-0000-000000000000,'+FIXED+'}']:
            with self.assertRaises((TypeError, ValueError)): value_from_string_internal(text)
        # Nested UUID streams and the Type-record inverse remain unmeasured.
        for value in (BSLUUID(FIXED), BSLType.UUID):
            a = BSLArray(); a.items = [value]
            with self.assertRaises(ValueError): value_to_string_internal(a)
        nested = '{"#",51e7a0d2-530b-11d4-b98a-008048da3034,1,{"#",'+GUID+','+FIXED+'}}'
        with self.assertRaises((TypeError, ValueError)): value_from_string_internal(nested)

if __name__ == '__main__': unittest.main()
