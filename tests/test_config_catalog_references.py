"""Deterministic private declaration-prefix and shared-budget controls."""
import dataclasses
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'yadinassi/storage'))
import config_catalog_references as parser
from filedb_catalog import CatalogLimits, ResourceLimit, _Budget

G = '9cd510cd-abfc-11d4-9434-004095e12fc7'
O = '9fcd25a0-4822-11d4-9414-008048da11f9'
A = '22222222-2222-4222-8222-222222222222'
T = parser.CATALOG_TYPE

def node(*values):
    return '{'+','.join(values)+'}'

def collection(*keys):
    return node(T,str(len(keys)),*keys)

def general(*collections):
    return node(G,node('0','0',str(len(collections)),*collections))

def document(*components, prefix='0'):
    return node(prefix,'0',str(len(components)),*components).encode()

def positive():
    return document(general(collection(A)))

class CatalogReferenceTests(unittest.TestCase):
    def parse(self, data, *, limits=None, shared=None):
        budget = _Budget(shared or CatalogLimits())
        result = parser.project_catalog_references(data,budget=budget,limits=limits)
        return result,budget

    def test_fifty_reviewed_vectors(self):
        vectors=json.loads((ROOT/'tests/fixtures/config_catalog_reference_vectors.json').read_text())
        self.assertEqual(len(vectors),50)
        self.assertEqual(len({v['name'] for v in vectors}),50)
        for v in vectors:
            with self.subTest(v['name']):
                data=v['target_utf8'].encode() if 'target_utf8' in v else bytes.fromhex(v['target_hex'])
                if v['expected']=='candidates':
                    result,budget=self.parse(data)
                    self.assertEqual(result.references,tuple(v['private_refs']))
                    self.assertGreater(result.collection_count,0)
                    self.assertEqual(budget.counts['bytes_processed'],3*len(data))
                    self.assertEqual(budget.counts['output_bytes'],212992)
                else:
                    with self.assertRaises(parser.CatalogReferenceError): self.parse(data)

    def test_resource_reservation_precedes_walk_allocation(self):
        data=positive()
        for shared in (CatalogLimits(max_bytes_processed=3*len(data)-1),
                       CatalogLimits(max_output_bytes=212991)):
            with self.subTest(shared=shared),mock.patch.object(parser,'_Walk') as walk:
                with self.assertRaises(ResourceLimit):self.parse(data,shared=shared)
                walk.assert_not_called()
        result,budget=self.parse(data,shared=CatalogLimits(max_bytes_processed=3*len(data),max_output_bytes=212992))
        self.assertEqual(result.references,(A,))

    def test_existing_usage_not_reset_or_refunded(self):
        data=positive();budget=_Budget(CatalogLimits(max_output_bytes=212992))
        budget.charge('output_bytes',1)
        with self.assertRaises(ResourceLimit):parser.project_catalog_references(data,budget=budget)
        self.assertEqual(budget.counts['output_bytes'],1)
        self.assertEqual(budget.counts['bytes_processed'],3*len(data))
        budget=_Budget(CatalogLimits())
        for _ in range(2):
            with self.assertRaises(parser.CatalogReferenceError):parser.project_catalog_references(b'x',budget=budget)
        self.assertEqual(budget.counts['output_bytes'],2*212992)
        self.assertEqual(budget.counts['bytes_processed'],6)

    def test_token_before_frame_and_scalar_growth(self):
        data=positive()
        budget=_Budget(CatalogLimits(max_tokens=1))
        # Root frame is the only frame allocated before the next scalar charge fails.
        original=parser._Frame
        with mock.patch.object(parser,'_Frame',wraps=original) as frames:
            with self.assertRaises(ResourceLimit):parser.project_catalog_references(data,budget=budget)
            self.assertEqual(frames.call_count,1)
        self.assertEqual(budget.counts['tokens'],1)
        self.assertEqual(budget.counts['output_bytes'],212992)

    def test_exact_local_and_shared_token_limits(self):
        data=positive();_,budget=self.parse(data);used=budget.counts['tokens']
        self.parse(data,limits=parser.CatalogReferenceLimits(max_tokens=used))
        self.parse(data,shared=CatalogLimits(max_tokens=used))
        with self.assertRaises(parser.CatalogReferenceError):
            self.parse(data,limits=parser.CatalogReferenceLimits(max_tokens=used-1))
        with self.assertRaises(ResourceLimit):self.parse(data,shared=CatalogLimits(max_tokens=used-1))

    def test_depth64_and65_and_lowered_shared_depth(self):
        self.parse(document(general(collection(A)),prefix='{'*63+'0'+'}'*63))
        with self.assertRaisesRegex(parser.CatalogReferenceError,'depth'):
            self.parse(document(general(collection(A)),prefix='{'*64+'0'+'}'*64))
        with self.assertRaisesRegex(parser.CatalogReferenceError,'depth'):
            self.parse(positive(),shared=CatalogLimits(max_tree_depth=1))

    def test_references256_and257_and_across_collections(self):
        keys=[f'00000000-0000-4000-8000-{i:012x}' for i in range(257)]
        r,_=self.parse(document(general(collection(*keys[:256]))))
        self.assertEqual(len(r.references),256)
        for data in (document(general(collection(*keys))),
                     document(general(collection(*keys[:256]),collection(keys[256])))):
            with self.assertRaisesRegex(parser.CatalogReferenceError,'references'):self.parse(data)
        with self.assertRaisesRegex(parser.CatalogReferenceError,'duplicate'):
            self.parse(document(general(collection(keys[10]),collection(keys[10].upper()))))

    def test_collection_and_component_caps(self):
        r,_=self.parse(document(general(collection(A),*[collection()]*63)))
        self.assertEqual(r.collection_count,64)
        with self.assertRaisesRegex(parser.CatalogReferenceError,'collections'):
            self.parse(document(general(collection(A),*[collection()]*64)))
        unknown=node('11111111-1111-4111-8111-111111111111')
        self.parse(document(*[unknown]*15,general(collection(A))))
        with self.assertRaisesRegex(parser.CatalogReferenceError,'components'):
            self.parse(document(*[unknown]*16,general(collection(A))))
        with self.assertRaisesRegex(parser.CatalogReferenceError,'component_duplicate'):
            self.parse(document(general(collection(A)),general(collection())))

    def test_utf8_consumed_character_rules(self):
        for raw in (b'\xc0\x80',b'\xed\xa0\x80',b'\xf4\x90\x80\x80',b'\xe2\x82'):
            with self.subTest(raw=raw):
                with self.assertRaises(parser.CatalogReferenceError):
                    self.parse(positive().replace(b'{0,0,1,',b'{"'+raw+b'",0,1,',1))
                r,_=self.parse(positive()+raw)
                self.assertEqual(r.references,(A,))
        self.parse(document(general(collection(A)),prefix='"Пример 😀"'))

    def test_opaque_strings_do_not_retain_input_or_search_type(self):
        prefix='"'+('x'*100000)+T+'"'
        result,_=self.parse(document(general(collection(A)),prefix=prefix))
        self.assertEqual(dataclasses.asdict(result),{'collection_count':1,'references':(A,)})
        self.assertFalse(hasattr(result,'offset'))
        with self.assertRaisesRegex(parser.CatalogReferenceError,'input_bytes'):
            self.parse(positive(),limits=parser.CatalogReferenceLimits(max_input_bytes=len(positive())-1))
        self.parse(positive(),limits=parser.CatalogReferenceLimits(max_input_bytes=len(positive())))

    def test_supported_component_routes_and_quoted_scalars(self):
        for kind in (G,'e3687481-0a87-462c-a166-9f34594f9bba','51f2d5d8-ea4d-4064-8892-82951750031e'):
            with self.subTest(kind=kind):
                data=document(node(kind,node('0','0','1',collection(A))))
                self.assertEqual(self.parse(data)[0].references,(A,))
        operation=node(O,node('0',node('0','0','1',collection(A))))
        self.assertEqual(self.parse(document(operation))[0].references,(A,))
        with self.assertRaises(parser.CatalogReferenceError):
            self.parse(document(node(O,node('0','0','1',collection(A)))))
        data=positive().replace(G.encode(),('"'+G+'"').encode()).replace(T.encode(),('"'+T+'"').encode())
        data=data.replace(b',1,',b',"1",').replace(A.encode(),('"'+A+'"').encode())
        self.assertEqual(self.parse(data)[0].references,(A,))

    def test_allocation_state_is_bounded_without_path_history(self):
        self.assertNotIn('__dict__',parser._Frame.__dict__)
        self.assertNotIn('__dict__',parser._Walk.__dict__)
        # A large ignored value consumes bytes but no retained token/path values.
        small=positive();large=document(general(collection(A)),prefix='"'+'x'*200000+'"')
        _,a=self.parse(small);_,b=self.parse(large)
        self.assertEqual(a.counts['output_bytes'],b.counts['output_bytes'])
        self.assertEqual(a.counts['tokens'],b.counts['tokens'])

    def test_limits_types_and_finite_errors(self):
        for key in parser.CatalogReferenceLimits.__dataclass_fields__:
            for value in (True,0,-1,10**10):
                with self.subTest(key=key,value=value),self.assertRaises(parser.CatalogReferenceError):
                    parser.CatalogReferenceLimits(**{key:value})
        for data in (bytearray(positive()),memoryview(positive()),'text'):
            with self.assertRaisesRegex(parser.CatalogReferenceError,'input_type'):self.parse(data)
        with self.assertRaisesRegex(parser.CatalogReferenceError,'limits_type'):self.parse(positive(),limits={})
        with self.assertRaises(ValueError):parser.CatalogReferenceError(A)

if __name__=='__main__':unittest.main()
