"""Owned loopback/source preparation only; no real 1C and no native parity claim."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT,ROOT/'scripts'):
    if str(path) not in sys.path: sys.path.insert(0,str(path))
import native_1c_http_family_contract as contract
import native_1c_http_route as route
from native_1c_http_fixture import owned_fixture
from yadinassi.http_client import BSLHTTPConnection, BSLHTTPRequest


class HTTPPacketTests(unittest.TestCase):
    def test_fixed_source_and_wire_caps(self):
        raw=(ROOT/route.SOURCE).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),contract.SOURCE_SHA256)
        self.assertLessEqual(len(raw),8192)
        self.assertEqual(contract.CASE_COUNT,40)
        self.assertEqual(contract.MAX_ENCODED_BYTES,7130)
        self.assertLessEqual(contract.MAX_ENCODED_BYTES,contract.MAX_OUTPUT_BYTES)

    def test_source_bound_wrapper_closed_parameters(self):
        raw=(ROOT/route.SOURCE).read_bytes();nonce='a'*32
        result=route.program(raw,12345,nonce)
        self.assertIn(b'HTTPFamily(12345,"/tmp/onec-smoke/stage3-',result)
        self.assertLessEqual(len(result),8192)
        for port in (True,0,80,65536,'12345'):
            with self.assertRaises(ValueError):route.program(raw,port,nonce)
        with self.assertRaises(ValueError):route.program(raw+b' ',12345,nonce)
        with self.assertRaises(ValueError):route.program(raw,12345,'private/path')

    def test_wire_failure_not_available_and_nonce_binding(self):
        raw=contract.CALIBRATION+b''.join(f'HT-{n:02}: [ok|S0:]\n'.encode() for n in range(1,41))
        self.assertEqual(len(contract.require_available(raw)),40)
        failed=raw.replace(b'HT-18: [ok|S0:]',b'HT-18: [action-error]')
        self.assertEqual(contract.validate_output(failed)[17]['status'],'action-error')
        with self.assertRaises(contract.AvailabilityError):contract.require_available(failed)
        nonce='b'*32
        wrapped=b'HTTP|'+nonce.encode()+b'|entered\n'+raw+b'HTTP|'+nonce.encode()+b'|completed\n'
        self.assertEqual(route.parse_wire(wrapped,nonce),raw)
        with self.assertRaises(ValueError):route.parse_wire(wrapped,'c'*32)

    def test_fixed_loopback_fixture_routes_and_cleanup(self):
        with owned_fixture() as server:
            connection=BSLHTTPConnection('127.0.0.1',server.server_port,timeout=2)
            for target,code,data in [('/text',200,'я😀'.encode()),('/latin',200,'Привет'.encode('cp1251')),
                ('/binary',200,b'\0\xffA'),('/empty',204,b''),('/missing',404,b'missing'),
                ('/redirect',302,b'redirect'),('/query?a=1',200,b'query')]:
                response=connection.get(BSLHTTPRequest(target))
                self.assertEqual(response.get_member('StatusCode'),code)
                self.assertEqual(response.get_body_as_binary_data()._data,data)
            self.assertFalse(server.failure)
        self.assertEqual(server.fileno(),-1)

    def test_local_packet_dry_run_records_not_native_acceptance(self):
        raw=(ROOT/route.SOURCE).read_bytes()
        with tempfile.TemporaryDirectory() as temp,owned_fixture() as server:
            root=Path(temp).resolve()
            result=route.replay(raw,root,server.server_port)
            self.assertEqual(len(contract.validate_output(result)),40)
            self.assertEqual(list(root.iterdir()),[])
        # Purposefully no require_available assertion: stream behavior and other
        # native semantics remain provisional until the first actual capture.


if __name__=='__main__':unittest.main()
