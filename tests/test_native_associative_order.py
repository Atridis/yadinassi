"""Independent permutations/mutations; no generated native expectations."""
import unittest
from scripts.native_associative_order import equivalent, signature
from tests.test_native_1c_map_contract import (
    mapping, sequence, scalar, string, MAP, FIXED_MAP, STRUCTURE, FIXED_STRUCTURE,
    ARRAY, FIXED_ARRAY,
)

class AssociativeOrderTests(unittest.TestCase):
    def test_four_kinds_permute_recursively_inside_ordered_arrays(self):
        for kind in (MAP,FIXED_MAP,STRUCTURE,FIXED_STRUCTURE):
            a=((string('First'),scalar('N',b'1')),(string('Second'),scalar('U')))
            left=sequence(ARRAY,(mapping(a,kind),scalar('B',b'1')))
            right=sequence(ARRAY,(mapping(a[::-1],kind),scalar('B',b'1')))
            self.assertTrue(equivalent(left,right))
            self.assertNotEqual(left,right)
    def test_ordered_sequences_types_and_bindings_stay_exact(self):
        a=((string('a'),scalar('N',b'1')),(string('b'),scalar('N',b'2')))
        left=mapping(a)
        self.assertFalse(equivalent(left,mapping(((a[0][0],a[1][1]),(a[1][0],a[0][1])))))
        self.assertFalse(equivalent(left,mapping(a,FIXED_MAP)))
        for kind in (ARRAY,FIXED_ARRAY):
            self.assertFalse(equivalent(sequence(kind,(left,scalar('U'))),sequence(kind,(scalar('U'),left))))
    def test_scalars_raw_spelling_and_structure_name_spelling_stay_exact(self):
        for before,after in ((scalar('N',b'1'),scalar('N',b'1.0')),(scalar('N',b'1'),scalar('B',b'1'))):
            self.assertFalse(equivalent(mapping(((string('a'),before),)),mapping(((string('a'),after),))))
        self.assertFalse(equivalent(mapping(((string('a'),scalar('U')),),STRUCTURE),mapping(((string('A'),scalar('U')),),STRUCTURE)))
    def test_duplicate_typed_keys_and_invalid_structure_names_reject(self):
        pairs=((scalar('N',b'1'),scalar('U')),(scalar('N',b'1.0'),scalar('L')))
        for kind,entries in ((MAP,pairs),(STRUCTURE,((string('a'),scalar('U')),(string('A'),scalar('L')))),(STRUCTURE,((string('bad-name'),scalar('U')),))):
            payload=mapping(entries,kind)
            with self.assertRaises(ValueError):equivalent(payload,payload)
        pairs=((scalar('N',b'1'),scalar('U')),(scalar('B',b'1'),scalar('L')),(string('1'),scalar('N',b'3')))
        self.assertTrue(equivalent(mapping(pairs),mapping(pairs[::-1])))
    def test_counts_delimiters_trailing_data_and_limits_reject(self):
        valid=mapping(((string('a'),scalar('U')),))
        for bad in (valid.replace(b'{1,',b'{2,',1),valid+b'garbage',valid.replace(b',\n',b';\n',1),b'{"S","'+b'x'*5000+b'"}',b'\xff'):
            with self.assertRaises(ValueError):equivalent(bad,bad)
        self.assertFalse(equivalent(valid,valid.replace(b',\n',b', ',1)))
    def test_uuid_comparison_is_opt_in_and_preserves_keys_values_and_container_identity(self):
        a=b'11111111-2222-4333-8444-55555555555a'
        z=b'00000000-0000-0000-0000-000000000000'
        type_id=b'fc01b5df-97fe-449b-83d4-218a090e681e'

        def uuid(raw):
            return b'{"#",'+type_id+b','+raw+b'}'

        pairs=((uuid(a),uuid(z)),(uuid(z),uuid(a)),(string(a.decode()),scalar('U')))
        left=mapping(pairs)
        right=mapping(pairs[::-1])
        with self.assertRaises(ValueError):signature(left)
        self.assertNotEqual(left,right)
        self.assertEqual(signature(left,uuid_scalars=True),signature(right,uuid_scalars=True))
        self.assertNotEqual(signature(left,uuid_scalars=True),
                            signature(mapping(((uuid(a),uuid(a)),*pairs[1:])),uuid_scalars=True))
        for different in (mapping(pairs,FIXED_MAP),
                          mapping(((string(a.decode()),uuid(z)), (uuid(z),uuid(a))))):
            self.assertNotEqual(signature(left,uuid_scalars=True),signature(different,uuid_scalars=True))
        source=sequence(ARRAY,(left,mapping(pairs,FIXED_MAP)))
        swapped=sequence(ARRAY,(mapping(pairs,FIXED_MAP),left))
        self.assertNotEqual(signature(source,uuid_scalars=True),signature(swapped,uuid_scalars=True))
        for corrupt in (left.replace(a,a.upper(),1), left.replace(a,z,1),
                        left.replace(type_id, b'00000000-0000-0000-0000-000000000000',1),
                        left+b'unparsed'):
            with self.assertRaises(ValueError):signature(corrupt,uuid_scalars=True)

    def test_descriptor_key_semantics_do_not_collapse_numeric_boolean_keys(self):
        def descriptor(kinds):
            return b'{"#",f5c65050-3bbb-11d5-b988-0050bae0a95d,{"Pattern"'+b''.join(b',{"'+k+b'"}' for k in kinds)+b'}}'
        pairs=((descriptor((b'N',)),scalar('N',b'1')),(descriptor((b'S',)),scalar('N',b'2')))
        self.assertTrue(equivalent(mapping(pairs),mapping(pairs[::-1])))
        duplicate=mapping(((descriptor((b'N',b'S')),scalar('U')),(descriptor((b'S',b'N')),scalar('L'))))
        with self.assertRaises(ValueError):signature(duplicate)
        # Identity-bearing array/map keys are outside this comparator subset.
        bad=mapping(((sequence(ARRAY,()),scalar('U')),))
        with self.assertRaises(ValueError):signature(bad)


class BoundProfileTests(unittest.TestCase):
    def records(self):
        from tests.test_native_1c_map_contract import records
        from tests.test_descriptor_map_runtime import NATIVE_SUFFIX
        from tests.native_observations import extract_payload
        from scripts import native_associative_order as relation
        rows=records()
        for ordinal,label in relation._CHECKS_EXTRA.items():rows[ordinal-1]=(label,b'true')
        pairs=((string('First'),scalar('N',b'1')),(string('Second'),scalar('U')))
        for ordinal,label in relation._PINNED_EXTRA.items():
            payload=(extract_payload(NATIVE_SUFFIX,label).encode('utf-8')
                     if label in relation.DESCRIPTOR_HISTORY_LABELS else mapping(pairs,STRUCTURE))
            rows[ordinal-1]=(label,payload)
        return rows
    def compare(self,left,right=None,source=None):
        from tests.test_native_1c_map_contract import encode
        from scripts.native_associative_order import compare_collections,SOURCE_SHA256
        return compare_collections(encode(left),encode(left if right is None else right),
                                   SOURCE_SHA256 if source is None else source)
    def test_v2_accepts_named_structure_permutation_without_rewriting_bytes(self):
        rows=self.records();changed=list(rows)
        pairs=((string('Second'),scalar('U')),(string('First'),scalar('N',b'1')))
        for ordinal in (295,298):changed[ordinal-1]=(rows[ordinal-1][0],mapping(pairs,STRUCTURE))
        result=self.compare(rows,changed)
        self.assertEqual(result['status'],'equivalent',result)
        self.assertEqual(result['profile'],'associative-order-v2')
        self.assertEqual(result['byte_equal_records'],1021)
        self.assertEqual(result['accepted_labels'],['internal.structure.order-ab.payload','internal.structure.order-ab.roundtrip.payload'])
    def test_source_unknown_field_record_moves_and_content_changes_reject(self):
        rows=self.records()
        self.assertEqual(self.compare(rows,source='0'*64)['reason'],'source_mismatch')
        for ordinal in (10,295,824):
            changed=list(rows);label,payload=changed[ordinal-1]
            changed[ordinal-1]=(label,payload.replace(b'101',b'102',1) if ordinal==824 else payload+b' ')
            self.assertEqual(self.compare(rows,changed)['status'],'rejected')
        moved=list(rows);moved[294],moved[298]=moved[298],moved[294]
        self.assertEqual(self.compare(moved)['reason'],'record_mismatch')
    def test_history_noncodec_step_and_malformed_field_remain_strict(self):
        from scripts.native_associative_order import equivalent_codec_history,codec_history_signature
        rows=self.records();payload=rows[823][1]
        self.assertTrue(equivalent_codec_history(payload,payload))
        self.assertFalse(equivalent_codec_history(payload,payload.replace(b'get-first:ok:{""N"",101}',b'get-first:ok:{""N"",102}')))
        for bad in (payload[:-1]+b';]',payload+b'garbage',payload.replace(b'codec-write',b'other-field',1)):
            with self.assertRaises(ValueError):codec_history_signature(bad)
    def test_descriptor_duplicate_and_scalar_spelling_mutations_are_not_permutations(self):
        from scripts.native_associative_order import equivalent_codec_history
        payload=self.records()[823][1]
        # The codec string is doubly quote-escaped. Alter a descriptor type,
        # leaving its pair value intact: this is not merely reordering pairs.
        changed=payload.replace(b'{""""S""""}',b'{""""N""""}',1)
        with self.assertRaises(ValueError):equivalent_codec_history(payload,changed)
    def test_named_payload_root_schema_rejects_even_identical_wrong_types(self):
        rows=self.records()
        for a,b in ((283,286),(295,298),(303,306)):
            changed=list(rows)
            for ordinal in (a,b):changed[ordinal-1]=(rows[ordinal-1][0],b'{"N",123}')
            self.assertEqual(self.compare(changed)['status'],'rejected')
    def test_named_history_root_type_and_count_reject_even_identical_mutations(self):
        from scripts.native_associative_order import codec_history_signature
        from tests.test_native_1c_map_contract import MAP,FIXED_MAP
        payload=self.records()[823][1]
        with self.assertRaises(ValueError):
            codec_history_signature(payload,expected_root=FIXED_MAP,expected_count=2)
        with self.assertRaises(ValueError):
            codec_history_signature(payload,expected_root=MAP,expected_count=1)

    def test_structure_roundtrip_guards_reject_identical_false(self):
        from scripts.native_associative_order import _CHECKS_EXTRA
        rows=self.records()
        for ordinal,label in _CHECKS_EXTRA.items():
            changed=list(rows);changed[ordinal-1]=(label,b'false')
            self.assertEqual(self.compare(changed)['reason'],'roundtrip_failed')
