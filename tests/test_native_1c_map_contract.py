"""Synthetic adversarial tests, not new observations of native 1C behavior."""
import importlib.util
import itertools
import json
from pathlib import Path
import random
import unittest


SPEC = importlib.util.spec_from_file_location(
    "native_1c_map_contract_test", Path(__file__).parents[1] / "scripts/native_1c_map_contract.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)

SOURCE = "bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada"
MAP = b"3d48feae-a9c6-4c5a-a099-9eb6477630c6"
FIXED_MAP = b"220455ea-6c85-4513-996f-bbe79ed07774"
ARRAY = b"51e7a0d2-530b-11d4-b98a-008048da3034"
FIXED_ARRAY = b"4500381b-db30-4a10-9db4-990038032acf"
STRUCTURE = b"4238019d-7e49-4fc9-91db-b6b951d5cf8e"
FIXED_STRUCTURE = b"3ee983d7-ace7-40f9-bb7e-2e916fcddd56"
NUMBER_TYPE = b"b0be78f2-0ee6-4d31-a3bb-77dd32ba5bec"
BOOLEAN_TYPE = b"5d4125ad-f6e7-4313-be32-f71d0ab60915"
BASES = ((283, "internal.map.typed-keys"), (287, "internal.map.typed-keys-again"),
         (291, "internal.map.reverse-insertion"), (303, "internal.array.nested"))
NESTED_CHECKS = ("structure-type", "fixed-structure-type", "fixed-map-type", "record-value",
                 "string-value", "map-value", "typed-keys")


def scalar(tag, value=None):
    tag = tag.encode("ascii")
    return b'{"' + tag + b'"' + (b"," + value if value is not None else b"") + b"}"


def string(value):
    return scalar("S", b'"' + value.encode("utf-8").replace(b'"', b'""') + b'"')


def sequence(identifier, values):
    values = tuple(values)
    return (b'{"#",' + identifier + b",\n{" + str(len(values)).encode("ascii")
            + (b",\n" + b",\n".join(values) + b"\n" if values else b"") + b"}\n}")


def mapping(pairs, identifier=MAP):
    return sequence(identifier, (b"{\n" + key + b",\n" + value + b"\n}" for key, value in pairs))


# Deliberately not the fixture's five specific keys or values.
PAIRS = ((scalar("U"), string("unset-17")),
         (scalar("B", b"1"), scalar("N", b"-17.25")),
         (scalar("N", b"42"), string('value,"quoted"')),
         (string("42"), scalar("L")),
         (scalar("T", BOOLEAN_TYPE), scalar("D", b"20261021123456")))


def nested(pairs):
    return sequence(ARRAY, (
        mapping(((string("First"), scalar("N", b"9")),
                 (string("Second"), scalar("U"))), STRUCTURE),
        mapping(((string("Items"), sequence(FIXED_ARRAY, (scalar("B", b"0"), string("x")))),
                 (string("Lookup"), mapping(((string("inside"), scalar("N", b"11")),)))),
                FIXED_STRUCTURE),
        mapping(pairs, FIXED_MAP)))


def records(pairs=PAIRS):
    rows = [(f"record.{number}", b"ok") for number in range(1, 974)]
    for ordinal, base in BASES:
        before = mapping(pairs) if ordinal != 303 else nested(pairs)
        after = mapping(tuple(reversed(pairs))) if ordinal != 303 else nested(tuple(reversed(pairs)))
        for offset, suffix, payload in ((0, ".payload", before), (1, ".roundtrip.type", b"true"),
                                         (2, ".roundtrip.count", b"true"),
                                         (3, ".roundtrip.payload", after)):
            rows[ordinal + offset - 1] = (base + suffix, payload)
    for ordinal, name in enumerate(NESTED_CHECKS, 307):
        rows[ordinal - 1] = ("internal.nested." + name, b"true")
    return rows


def encode(rows):
    return b"".join(label.encode("ascii") + b": [" + payload + b"]\n" for label, payload in rows)


def change(rows, ordinal, payload=None, label=None):
    rows = list(rows)
    old_label, old_payload = rows[ordinal - 1]
    rows[ordinal - 1] = (old_label if label is None else label,
                         old_payload if payload is None else payload)
    return rows


class MapContractTests(unittest.TestCase):
    def compare(self, a, b=None, source=SOURCE):
        if isinstance(a, list):
            a = encode(a)
        if isinstance(b, list):
            b = encode(b)
        return contract.compare_collections(a, a if b is None else b, source)

    def reject(self, a, b=None, reason=None):
        result = self.compare(a, b)
        self.assertEqual(result["status"], "rejected", result)
        self.assertEqual(result["records"], 0)
        self.assertEqual(result["byte_equal_records"], 0)
        self.assertEqual(result["accepted_labels"], [])
        self.assertIn(result["reason"], contract.REASONS - {"none"})
        if reason is not None:
            self.assertEqual(result["reason"], reason)
        return result

    def test_all_120_pair_permutations_and_both_roundtrips(self):
        original = encode(records())
        for permutation in itertools.permutations(PAIRS):
            with self.subTest(permutation=permutation):
                result = self.compare(original, encode(records(permutation)))
                self.assertEqual(result["status"], "equivalent", result)
                expected = [] if permutation == PAIRS else list(contract.ELIGIBLE_LABELS)
                self.assertEqual(result["accepted_labels"], expected)
                self.assertEqual(result["byte_equal_records"], 973 - len(expected))

    def test_alternate_legitimate_typed_bindings_and_counts(self):
        extra_array = (scalar("L"), sequence(ARRAY, (string("a"), string("b"))))
        extra_map = (scalar("D", b"00010101000000"), mapping(((string("q"), scalar("B", b"1")),)))
        variants = ((), PAIRS[:1], PAIRS[:2], PAIRS,
                    (*PAIRS, extra_array, extra_map),
                    tuple((scalar("N", str(i).encode()), string(f"v-{i}")) for i in range(19)))
        for pairs in variants:
            with self.subTest(count=len(pairs)):
                result = self.compare(records(pairs), records(tuple(reversed(pairs))))
                self.assertEqual(result["status"], "equivalent", result)

    def test_boolean_number_string_undefined_and_type_keys_do_not_collide(self):
        pairs = ((scalar("B", b"0"), string("b")), (scalar("N", b"0"), string("n")),
                 (string("0"), string("s")), (scalar("U"), string("u")),
                 (scalar("T", NUMBER_TYPE), string("t")))
        self.assertEqual(self.compare(records(pairs), records(pairs[::-1]))["status"], "equivalent")

    def test_raw_scalar_spelling_types_and_uuid_are_not_normalized(self):
        variants = ((scalar("N", b"42.0"), PAIRS[2][1]),
                    (scalar("N", b"+42"), PAIRS[2][1]),
                    (string("042"), PAIRS[2][1]),
                    (scalar("T", NUMBER_TYPE), PAIRS[2][1]),
                    (PAIRS[2][0], string('value,"Quoted"')))
        for variant in variants:
            changed = (*PAIRS[:2], variant, *PAIRS[3:])
            self.reject(records(), records(changed), "typed_difference")

    def test_value_binding_is_not_a_bag_of_independent_keys_and_values(self):
        changed = ((PAIRS[0][0], PAIRS[1][1]), (PAIRS[1][0], PAIRS[0][1]), *PAIRS[2:])
        self.reject(records(), records(changed), "typed_difference")

    def test_missing_extra_and_duplicate_pairs_are_not_erased(self):
        self.reject(records(), records(PAIRS[:-1]), "typed_difference")
        self.reject(records(), records((*PAIRS, (string("new"), scalar("U")))), "typed_difference")
        for pairs in ((*PAIRS, PAIRS[0]), (*PAIRS, (PAIRS[0][0], string("other"))),
                      ((scalar("N", b"0"), string("a")), (scalar("N", b"0.0"), string("b")))):
            self.reject(records(pairs), reason="unsupported_payload")

    def test_declared_counts_are_validated_even_when_both_files_match(self):
        for replacement in (b"4", b"6", b"05", b"-1", b"+5", b"256", b'"5"'):
            malformed = mapping(PAIRS).replace(b"\n{5,", b"\n{" + replacement + b",", 1)
            self.reject(change(records(), 283, malformed), reason="unsupported_payload")

    def test_ordered_array_and_fixed_array_order_are_preserved(self):
        for identifier in (ARRAY, FIXED_ARRAY):
            before = ((string("items"), sequence(identifier, (scalar("N", b"1"), scalar("N", b"2")))),)
            after = ((string("items"), sequence(identifier, (scalar("N", b"2"), scalar("N", b"1")))),)
            self.reject(records(before), records(after), "typed_difference")

    def test_structure_and_fixed_structure_member_order_are_preserved(self):
        pairs = ((string("First"), scalar("N", b"1")), (string("Second"), scalar("N", b"2")))
        for identifier in (STRUCTURE, FIXED_STRUCTURE):
            before = ((string("obj"), mapping(pairs, identifier)),)
            after = ((string("obj"), mapping(pairs[::-1], identifier)),)
            self.reject(records(before), records(after), "typed_difference")

    def test_map_order_is_ignored_recursively_but_container_uuid_is_not(self):
        inner = ((string("one"), scalar("U")), (string("two"), scalar("L")))
        for identifier in (MAP, FIXED_MAP):
            a = records(((string("nested"), mapping(inner, identifier)),))
            b = records(((string("nested"), mapping(inner[::-1], identifier)),))
            self.assertEqual(self.compare(a, b)["status"], "equivalent")
        self.reject(records(((string("nested"), mapping(inner, MAP)),)),
                    records(((string("nested"), mapping(inner, FIXED_MAP)),)), "typed_difference")

    def test_unsupported_tags_uuid_aliases_references_and_cycles_fail_closed(self):
        malformed = (b'{"R",0}', b'{"ref",1}', b'{"@",0}', b'{"U",0}', b'{"n",1}',
                     b'{"N",1,5}', b'{"B",2}', b'{"D",20260230000000}', b'{"D",2026}',
                     b'{"T",00000000-0000-0000-0000-000000000000}',
                     b'{"#",00000000-0000-0000-0000-000000000000,{0}}',
                     b'{"#",' + MAP + b',{1,0}}', b'{"#",' + MAP + b',0,{0}}',
                     b'{"S","a"\\0041"}', b'{"S","unterminated}', b'{"S",bare}')
        for value in malformed:
            with self.subTest(value=value):
                self.reject(records(((string("key"), value),)))

    def test_identity_bearing_container_keys_are_not_structurally_equated(self):
        for identifier in (ARRAY, FIXED_ARRAY, MAP, FIXED_MAP, STRUCTURE, FIXED_STRUCTURE):
            self.reject(records(((sequence(identifier, ()), string("value")),)),
                        reason="unsupported_payload")

    def test_structure_duplicate_case_alias_and_wrong_key_type_fail_closed(self):
        for entries in (((string("Name"), scalar("U")), (string("name"), scalar("L"))),
                        ((scalar("N", b"1"), scalar("U")),)):
            self.reject(records(((string("nested"), mapping(entries, STRUCTURE)),)),
                        reason="unsupported_payload")

    def test_structure_identifier_keys_must_be_valid_even_when_inputs_match(self):
        for identifier in (STRUCTURE, FIXED_STRUCTURE):
            for name in ("", "1name", "has space", "has-hyphen", "punctuation!", "a\n"):
                entries = ((string(name), scalar("U")),)
                self.reject(records(((string("nested"), mapping(entries, identifier)),)),
                            reason="unsupported_payload")
            entries = ((string("_Имя42"), scalar("N", b"1")),)
            self.assertEqual(self.compare(records(((string("nested"), mapping(entries, identifier)),)))
                             ["status"], "equivalent")

    def test_raw_whitespace_escaping_and_unicode_are_preserved(self):
        a = records(((string('a\\b,"c"\nд'), string("e\u0301")),))
        b = records(((string('a\\b,"c"\nд'), string("é")),))
        self.reject(a, b, "typed_difference")
        for ordinal in (283, 286):
            b = change(a, ordinal, a[ordinal - 1][1].replace(b",\n", b", \n", 1))
            self.reject(a, b, "typed_difference")
        b = change(a, 283, b" " + a[282][1])
        self.reject(a, b, "typed_difference")

    def test_label_like_text_inside_strings_cannot_forge_record_boundaries(self):
        text = 'PRIVATE]\ninternal.map.typed-keys.payload: [{"U"}]\nrecord.fake: ["x"]'
        pairs = ((string(text), string("brackets [] ] [, braces {} and quotes \"")), *PAIRS[:2])
        a, b = records(pairs), records(pairs[::-1])
        result = self.compare(a, b)
        self.assertEqual(result["status"], "equivalent", result)
        self.assertEqual(result["records"], 973)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_complete_payload_consumption_and_pair_arity(self):
        for payload in (mapping(PAIRS) + b"garbage", mapping(PAIRS) + b'{"U"}',
                        mapping(PAIRS)[:-1], mapping(PAIRS).replace(b'"U"}', b'"U"}, {"L"}', 1),
                        mapping(PAIRS).replace(b"{\n", b"{,\n", 1)):
            self.reject(change(records(), 283, payload))

    def test_roundtrip_validation_on_both_sides_even_for_exact_files(self):
        different = mapping(((string("other"), scalar("N", b"77")),))
        for ordinal, _ in BASES:
            payload = nested(((string("other"), scalar("N", b"77")),)) if ordinal == 303 else different
            self.reject(change(records(), ordinal + 3, payload), reason="roundtrip_failed")

    def test_all_type_count_and_seven_nested_checks_must_be_true_on_both_sides(self):
        checks = [ordinal + offset for ordinal, _ in BASES for offset in (1, 2)] + list(range(307, 314))
        for ordinal in checks:
            for payload in (b"false", b"1", b"True", b'"true"', b"true "):
                self.reject(change(records(), ordinal, payload), reason="roundtrip_failed")

    def test_wrong_root_kind_is_not_accepted_even_in_coordinated_inputs(self):
        self.reject(change(records(), 283, mapping(PAIRS, FIXED_MAP)), reason="unsupported_payload")
        self.reject(change(records(), 303, sequence(FIXED_ARRAY, ())), reason="unsupported_payload")

    def test_nonscoped_records_remain_byte_exact_including_other_maps(self):
        original = records()
        for ordinal in (1, 275, 282, 295, 296, 297, 298, 299, 300, 301, 302, 314, *range(759, 974)):
            self.reject(original, change(original, ordinal, b"different"), "ineligible_difference")
        a = change(original, 100, mapping(PAIRS))
        b = change(original, 100, mapping(PAIRS[::-1]))
        self.reject(a, b, "ineligible_difference")

    def test_all_thirteen_exclude_records_remain_byte_strict(self):
        # These are synthetic payloads, not native expectations. Every EXCLUDE
        # label stays outside the unchanged eight-label typed-Map allowance.
        labels = ["fill.exclude-missing." + variant + "." + name
                  for variant in ("target-only", "source-only", "neither")
                  for name in ("missing", "missing-first", "first-missing")]
        labels += ["fill.exclude-missing.control.first", "fill.exclude-missing.control.first-last",
                   "fill.exclude-source-order.source-only.first",
                   "fill.exclude-source-order.source-only.between"]
        rows = records()
        for ordinal, label in enumerate(labels, 842):
            self.assertNotIn(label, contract.ELIGIBLE_LABELS)
            rows = change(rows, ordinal, b'error;{"N",1};{"N",2};{"N",3};{"N",3};{"B",0};{"U"}', label)
        self.assertEqual(self.compare(rows)["status"], "equivalent")
        for ordinal in range(842, 855):
            self.reject(rows, change(rows, ordinal,
                b'error;{"N",10};{"N",20};{"N",30};{"N",3};{"B",0};{"U"}'),
                "ineligible_difference")

    def test_historical_length_and_hash_cannot_claim_appended_checkpoint(self):
        self.reject(records()[:797], reason="record_mismatch")
        self.reject(records()[:828], reason="record_mismatch")
        for count, digest in ((841, "e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232"),
                              (852, "fef5af9c34d3af7ae73e427ac1e846c539246530aa9bcd5858932fc397754ed9")):
            self.reject(records()[:count], reason="record_mismatch")
            self.assertEqual(self.compare(records(), source=digest)["reason"], "source_mismatch")
        self.assertEqual(self.compare(records(), source="b3bf181de84a575335ce7e4794ced459ad252eb7853cc42095fb62521dc6a409")["reason"], "source_mismatch")
        result = self.compare(records(), source=
            "f8a5be47e937e39500c51a2b9c8fdaaf4becd68aa908cf7e99abe068a6c8cd4a")
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "source_mismatch")
        self.assertEqual(len(contract.ELIGIBLE_LABELS), 8)
        self.assertTrue(all(ordinal < 798 for ordinal in contract._ELIGIBLE))

    def test_fixed_record_count_labels_ordinals_and_uniqueness(self):
        original = records()
        self.reject(original[:-1], reason="record_mismatch")
        self.reject([*original, ("extra", b"ok")], reason="invalid_framing")
        self.reject(change(original, 283, label="unapproved.payload"), reason="record_mismatch")
        self.reject(change(original, 1, label=original[1][0]), reason="record_mismatch")
        moved = list(original)
        moved[282], moved[286] = moved[286], moved[282]
        self.reject(moved, reason="record_mismatch")

    def test_strict_outer_framing_utf8_suffix_and_boundary_tricks(self):
        raw = encode(records())
        malformed = (raw + b"\n", b"\n" + raw, b"\xef\xbb\xbf" + raw, raw[:-1],
                     raw.replace(b"]\n", b"]\r\n", 1), raw.replace(b": [", b":[", 1),
                     raw.replace(b"ok", b"\xff", 1), raw.replace(b"ok", b"\x00", 1),
                     raw.replace(b"ok", b'"unterminated', 1),
                     raw.replace(b"ok", b"]\nrecord.forged: [ok", 1))
        for payload in malformed:
            self.reject(payload)

    def test_source_hash_is_pinned_and_not_silently_guessed(self):
        raw = encode(records())
        for source in (None, 0, "", "a" * 64, SOURCE.upper(), SOURCE + "\n"):
            result = self.compare(raw, source=source)
            self.assertEqual(result["reason"], "source_mismatch")

    def test_file_record_scalar_depth_and_node_resource_limits(self):
        for raw in (b"", b"x" * (contract.MAX_FILE + 1), bytearray(encode(records())), None):
            self.reject(raw, reason="input_limit")
        self.reject(change(records(), 283, b" " * (contract.MAX_RECORD + 1)), reason="payload_limit")
        self.reject(records(((string("key"), string("x" * 255)),)), reason="payload_limit")
        deep = scalar("U")
        for _ in range(13):
            deep = sequence(ARRAY, (deep,))
        self.reject(records(((string("deep"), deep),)), reason="payload_limit")
        wide = sequence(ARRAY, (scalar("U") for _ in range(130)))
        self.reject(records(((string("wide"), wide),)), reason="payload_limit")

    def test_failure_reports_are_finite_and_never_expose_input(self):
        secret = "PRIVATE_SYNTHETIC_SENTINEL"
        result = self.reject(records(), records(((string(secret), scalar("U")),)))
        self.assertEqual(set(result), {"status", "profile", "records", "byte_equal_records",
                                       "accepted_labels", "reason"})
        self.assertNotIn(secret, json.dumps(result))
        self.assertLess(len(json.dumps(result)), 256)

    def test_mutation_fuzz_is_bounded_and_does_not_throw_or_mutate_raw_buffers(self):
        randomizer = random.Random(337)
        original = encode(records())
        for _ in range(200):
            payload = bytearray(original)
            index = randomizer.randrange(len(payload))
            payload[index] = randomizer.randrange(256)
            mutated = bytes(payload)
            result = self.compare(mutated)
            self.assertIn(result["status"], ("equivalent", "rejected"))
            self.assertIn(result["reason"], contract.REASONS)
            self.assertEqual(mutated, bytes(payload))
        self.assertEqual(original, encode(records()))


if __name__ == "__main__":
    unittest.main()
