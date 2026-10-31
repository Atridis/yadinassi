"""Synthetic adversarial acquisition checks, never native acceptance evidence."""
from pathlib import Path
import copy
import json
import sys
import unittest
from unittest import mock
import test_native_1c_db_oracle_catalog_attribute_binding as fixture
import metadata_catalog_acquisition as subject
import metadata_catalog_instrument as instrument
import metadata_catalog_probe_contract as wire
from snapshots import OracleError

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / 'scripts/native_1c_db_oracle/modules'


def source(length=32, name='NativeOracleItems'):
    key = fixture.KEYS[0]
    prefix = fixture.matrix.names.document(name='"'+name+'"', code='8', kind='1',
        description='8', metadata_uuid=key)
    attrs = [fixture.constructed.attribute('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '"Payload"',
        '{"Pattern",{"S",'+str(length)+',1}}')]
    collection = fixture.constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9', '1', *attrs)
    payload = fixture.stored_literal(prefix[:-1]+b',0,0,0,0,'+collection.encode()+b'}')
    return fixture.content_source(fixture.entries(refs=(key,), payload=payload))


def scalar(text):
    return 'S'+str(len(text))+':'+''.join(f'{ord(c):04x}' for c in text)


def output(length=32):
    values={1:'N1',2:'N1',3:scalar('NativeOracleItems'),4:scalar('NativeOracleItems'),
        5:scalar('Справочник.NativeOracleItems'),6:scalar('Справочник.NativeOracleItems'),
        7:'N'+str(length),8:'N'+str(length)}
    return wire.C1+wire.C2+b''.join(f'MC-{i:02}: [ok|{values.get(i,"B1")}]\n'.encode('ascii') for i in range(1,27))


class MetadataAcquisitionTests(unittest.TestCase):
    def test_real_config_bytes_not_native_expectations(self):
        for length in (32,64):
            image=source(length)
            actual=subject.read_projection(image.read_at,image.size,limits=subject.filedb_catalog.CatalogLimits())
            self.assertEqual(actual,dict(count=1,name='NativeOracleItems',payload_length=length,applied_state='not_observed'))
        image=source(17,'ActualFromBytes')
        actual=subject.read_projection(image.read_at,image.size,limits=subject.filedb_catalog.CatalogLimits())
        self.assertEqual((actual['name'],actual['payload_length']),('ActualFromBytes',17))
    def test_owned_count_is_not_general_projector(self):
        image=fixture.source()
        with self.assertRaises(OracleError):
            subject.read_projection(image.read_at,image.size,limits=subject.filedb_catalog.CatalogLimits())
    def test_loaded_discriminator_and_forged_comparison(self):
        states=[]
        for snapshot in subject.TARGETS:
            for context in subject.CONTEXTS:
                length=64 if snapshot=='applied' else 32
                projected=dict(count=1,name='NativeOracleItems',payload_length=length,applied_state='not_observed')
                raw=output(length)
                states.append(dict(snapshot=snapshot,context=context,token=f'{len(states):032x}',wire=raw.decode(),
                    config=projected,comparison=subject.compare(wire.validate_output(raw),projected)))
        self.assertEqual(subject.applied_view_verdict(states),'owned_payload_applied_view_32_32_64_observed')
        for mutate in (lambda s:s[2]['config'].update(payload_length=64),
                       lambda s:s[2].update(wire=output(64).decode()),
                       lambda s:s[2].update(token=s[0]['token'])):
            bad=copy.deepcopy(states);mutate(bad)
            with self.assertRaises((OracleError,ValueError)):subject.applied_view_verdict(bad)
        with self.assertRaises(OracleError):subject.applied_view_verdict(states[::-1])
    def test_marker_exact_binding(self):
        marker=dict(schema=1,nonce='a'*32,token='b'*32,operation='metadata_catalog_client',status='ok',output=output().decode())
        def read(value):return subject.validate_marker(json.dumps(value).encode(),nonce='a'*32,token='b'*32,context='client')
        self.assertEqual(len(read(marker)),26)
        for key,value in (('schema',True),('nonce','b'*32),('token','c'*32),('operation','metadata_catalog_server'),('extra',1),('status','error')):
            bad=dict(marker);bad[key]=value
            with self.assertRaises(OracleError):read(bad)
    def test_instrumented_syntax_and_closed_anchors(self):
        from yadinassi.syntax.parser import parse
        probe=(MODULES/'MetadataCatalogProbe.bsl').read_bytes()
        for name in ('NativeOracleServer.bsl','ManagedApplicationModule.bsl'):
            source=(MODULES/name).read_bytes()
            rendered=instrument.instrument(source,name=name,probe=probe)
            rendered=rendered.decode().replace('@@EVIDENCE@@','"/owned"').replace('@@NONCE@@','"'+'a'*32+'"').replace('@@SETUP_USER@@','"Setup"').replace('@@CRUD_USER@@','"CRUD"')
            parse(rendered)
            self.assertNotIn('Сообщить(',instrument.observer(probe))
            crlf=instrument.instrument(source.replace(b'\n',b'\r\n'),name=name,probe=probe.replace(b'\n',b'\r\n'))
            self.assertEqual(crlf,instrument.instrument(source,name=name,probe=probe))
        with self.assertRaises(ValueError):instrument.instrument(b'invalid',name='ManagedApplicationModule.bsl',probe=probe)
    def test_summary_digest_guard(self):
        for digest in ('x'*64,'a'*63,True):
            with self.assertRaises(OracleError):subject._summary({'bytes':1,'sha256':digest})
