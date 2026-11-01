"""Minimal immutable ordinary native observations; no installation/session data."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT,ROOT/'scripts'):
    if str(path) not in sys.path: sys.path.insert(0,str(path))
from test_native_data_hashing_family_measurement import emit, SOURCE
from yadinassi import Interpreter
from native_1c_data_hashing_family_contract import require_available,validate_output
FIXTURE=ROOT/'tests/fixtures/data_hashing_family/native-ordinary-v1'
class HashingNativeAcquisitionTests(unittest.TestCase):
    def test_immutable_source_and_native40_identity(self):
        receipt=json.loads((FIXTURE/'receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['source_sha256'],'7a126ea8f2dc1b94b9926b2a12d25554933c32fd7dbca7534ac84104c1027ab6')
        self.assertEqual(receipt['output_sha256'],'f3460e71937c9d6dc29fce76181350845e66456b77d11c8d13ed11ab3882c8ed')
        for name,key in [('original40.bsl','source_sha256'),('original40.out','output_sha256')]:
            self.assertEqual(hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest(),receipt[key])
        self.assertEqual(len(require_available((FIXTURE/'original40.out').read_bytes())),40)
    def test_original38_matches_and_two_unresolved_representation_cases(self):
        native=validate_output((FIXTURE/'original40.out').read_bytes())
        local=validate_output(emit(source=(FIXTURE/'original40.bsl').read_text(encoding='utf-8')))
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b],[5,10])
        for n in (5,10):
            self.assertEqual(native[n-1]['units'],tuple(map(ord,'Нет:64')))
            self.assertEqual(local[n-1]['units'],tuple(map(ord,'Да:64')))
    def test_sha512_chunks_preserve_raw_linebreak_and_complete_digest_bytes(self):
        fixture=FIXTURE.parent/'native-sha512-v1'
        receipt=json.loads((fixture/'receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['source_sha256'],'0747e214310432fc0bc36af922d7443d15ff0c082bc9b8356403a7ca874b827d')
        self.assertEqual(receipt['output_sha256'],'315983a268fae9793eb264a72d9dc836311bcd4372e6caa9fabfa2e8fc123cd3')
        for name,key in [('original40.bsl','source_sha256'),('original40.out','output_sha256')]:
            self.assertEqual(hashlib.sha256((fixture/name).read_bytes()).hexdigest(),receipt[key])
        native=require_available((fixture/'original40.out').read_bytes())
        local=validate_output(emit(source=(fixture/'original40.bsl').read_text(encoding='utf-8')))
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b],[5,10,30,33])
        for text,ids in (('',(5,15,30)),('abc',(10,20,33))):
            parts=[''.join(map(chr,native[n-1]['units'])) for n in ids]
            length,first=parts[0].split(':',1);whole=first+parts[1]+parts[2]
            self.assertEqual((int(length),len(whole)),(90,90))
            self.assertEqual(whole[64:66],'\r\n')
            unwrapped=whole[:64]+whole[66:]
            self.assertEqual(base64.b64decode(unwrapped,validate=True),hashlib.sha512(text.encode()).digest())
            self.assertEqual(whole,unwrapped[:64]+'\r\n'+unwrapped[64:])

    def test_final_vector_observer_only_accepts_the_measured_separator(self):
        helper=SOURCE.split('Функция HFFile',1)[0]
        expected=base64.b64encode(hashlib.sha512(b'abc').digest()).decode('ascii')
        transforms=((lambda text:text,True),
            (lambda text:text[:64]+'\r\n'+text[64:],True),
            (lambda text:text[:64]+'\n'+text[64:],False),
            (lambda text:text[:76]+'\r\n'+text[76:],False),
            (lambda text:text[:64]+'  '+text[64:],False),
            (lambda text:text[:64]+'\r\n'+text[64:]+'\r\n',False))
        for transform,accepted in transforms:
            out=[];vm=Interpreter(out.append)
            vm.register_function('Base64String',lambda value:transform(base64.b64encode(value._data).decode('ascii')))
            vm.execute(helper+'\nСообщить(HFVector(HashFunction.SHA512,"abc","'+expected+'"));')
            self.assertEqual(out,['Да:64' if accepted else 'Нет:64'])

if __name__=='__main__':unittest.main()
