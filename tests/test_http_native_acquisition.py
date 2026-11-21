"""Minimal public observations; no private transport, credentials or native runs."""
import errno
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT,ROOT/'scripts'):
    if str(path) not in sys.path:sys.path.insert(0,str(path))
import native_1c_http_family_contract as contract
import native_1c_http_route as route
from native_1c_http_fixture import owned_fixture
FIXTURE=ROOT/'tests/fixtures/http_family/native-initial'

class HTTPNativeAcquisitionTests(unittest.TestCase):
    def test_minimal_literal_identity_and_available_records(self):
        receipt=json.loads((FIXTURE/'receipt.json').read_text(encoding='utf-8'))
        source=(FIXTURE/'source.bsl').read_bytes();raw=(FIXTURE/'output.txt').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),'3d975d1dafa02811b760386dfc2cf31fc4d81fb046a0b6e85a1f1a8c9c91cf97')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'d159e9a8b3a11329b453871870e44794478edd30a4ea4681ffa1e31ecb91d971')
        self.assertEqual(receipt['source_sha256'],hashlib.sha256(source).hexdigest())
        self.assertEqual(receipt['output_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(contract.require_available(raw)),40)
        self.assertEqual({p.name for p in FIXTURE.iterdir()},{'source.bsl','output.txt','receipt.json'})
    def test_current_packet_retains_observations(self):
        self.assertEqual((ROOT/route.SOURCE).read_bytes(),(FIXTURE/'source.bsl').read_bytes())
    def test_all40_exact_local_replay(self):
        with tempfile.TemporaryDirectory(prefix='http-observed-') as tmp,owned_fixture() as fixture:
            root=Path(tmp).resolve()
            actual=route.replay((FIXTURE/'source.bsl').read_bytes(),root,fixture.server_port)
            self.assertEqual(actual,(FIXTURE/'output.txt').read_bytes())
            self.assertEqual(list(root.iterdir()),[])


    def test_replay_releases_request_file_before_its_in_program_unlink(self):
        from yadinassi.http import http_client

        handles, files_open_at_unlink = [], []
        open_regular, unlink = http_client._open_regular, os.unlink

        def track(path):
            handle = open_regular(path)
            handles.append(handle)
            return handle

        with tempfile.TemporaryDirectory(prefix='http-open-file-') as tmp, owned_fixture() as fixture:
            root = Path(tmp).resolve()
            input_file = root / 'http-in.bin'

            def deny_open_file(path, *args, **kwargs):
                if Path(path) == input_file:
                    live = sum(not handle.closed for handle in handles)
                    files_open_at_unlink.append(live)
                    if live:
                        # POSIX normally permits this unlink; Windows does not.
                        raise PermissionError(errno.EACCES, 'request file is open', path)
                return unlink(path, *args, **kwargs)

            with patch.object(http_client, '_open_regular', track), patch.object(os, 'unlink', deny_open_file):
                actual = route.replay((FIXTURE/'source.bsl').read_bytes(), root, fixture.server_port)
            self.assertEqual(actual, (FIXTURE/'output.txt').read_bytes())
            self.assertEqual(list(root.iterdir()), [])
        self.assertEqual(len(handles), 4)
        self.assertEqual(files_open_at_unlink, [0, 0, 0, 0])
