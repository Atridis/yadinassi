"""Offline locked packet contracts. No native client/process execution."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from form_results_packet import COUNT, MAX_OUTPUT, PACKET_HASHES, SOURCE_SHA256, FORM_SHA256, packet, parse_records
from form_results_packet import route


def records(cancel_calls=0):
    rows=[]
    for n in range(1,6):
        calls=cancel_calls if n==5 else 1
        kind=('undefined' if n==2 else 'structure' if n==3 else 'string') if n<5 else ('undefined' if calls else 'none')
        trace='start,open,'
        if n==5:trace+='cancel_open,'+('notify,' if calls else '')
        elif n==4:trace+='request_close,before_close,refuse_close,request_close,before_close,closed,notify,'
        else:trace+='request_close,before_close,closed,notify,'
        rows.append(f'FR{n}={calls};{kind};{calls};{calls};{trace}finish,|')
    return ''.join(rows).encode()


def marker(raw,phase='completed'):
    return json.dumps(dict(schema=route.SCHEMA,nonce='a'*32,phase=phase,source_sha256=SOURCE_SHA256,form_sha256=FORM_SHA256,records=raw.decode())).encode()


class NativeFormResultsPacketTests(unittest.TestCase):
    def test_eight_files_are_frozen_and_no_unowned_payload(self):
        files=packet();self.assertEqual(len(files),8)
        self.assertEqual(set(files),set(PACKET_HASHES))
        for name,raw in files.items():self.assertEqual(hashlib.sha256(raw).hexdigest(),PACKET_HASHES[name])

    def test_modules_and_events_bound_in_generated_source(self):
        files=route.sources();self.assertEqual(route.validate_redump(files),route.module_digest())
        self.assertNotIn(b'SOURCE_VALUE',files[route.MODULES[0]])
        self.assertIn(SOURCE_SHA256.encode(),files[route.MODULES[0]])
        self.assertIn(b'AttachIdleHandler("TryClose"',files[route.MODULES[1]])

    def test_extra_or_missing_redump_file_rejected(self):
        files=route.sources();files['Extra.xml']=b'x'
        with self.assertRaises(ValueError):route.validate_redump(files)
        files=route.sources();del files[route.MODULES[1]]
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_child_module_change_refused(self):
        files=route.sources();files[route.MODULES[1]]+=b'\nMessage("changed");'
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_owner_module_change_refused(self):
        files=route.sources();files[route.MODULES[0]]=files[route.MODULES[0]].replace(b'"Completed"',b'"Other"')
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_child_metadata_identity_refused(self):
        files=route.sources();p='Launcher/Forms/Child.xml';files[p]=files[p].replace(b'ac97af7e',b'ac97af7f')
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_event_rebinding_refused(self):
        files=route.sources();p='Launcher/Forms/Child/Ext/Form.xml';files[p]=files[p].replace(b'ChildBeforeClose',b'ChildOpen')
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_qname_namespace_rebinding_refused(self):
        files=route.sources();p='Launcher/Forms/Main/Ext/Form.xml';files[p]=files[p].replace(b'current-config',b'foreign-config')
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_metadata_qname_namespace_rebinding_refused(self):
        files=route.sources();p='Launcher/Forms/Child.xml';files[p]=files[p].replace(b'http://v8.1c.ru/8.2/managed-application/core',b'http://foreign.invalid/core')
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_xml_external_entity_refused(self):
        files=route.sources();p='Launcher/Forms/Main/Ext/Form.xml';files[p]=b'<!DOCTYPE Form SYSTEM "file:///secret">'+files[p]
        with self.assertRaises(ValueError):route.validate_redump(files)

    def test_bom_crlf_and_event_order_only_normalization(self):
        files={p:b'\xef\xbb\xbf'+raw.replace(b'\n',b'\r\n') for p,raw in route.sources().items()}
        self.assertEqual(route.validate_redump(files),route.module_digest())

    def test_five_complete_flows(self):
        self.assertEqual(len(parse_records(records())),COUNT)

    def test_cancelled_open_observes_either_callback_outcome(self):
        self.assertEqual(parse_records(records(0))[-1][0],0)
        self.assertEqual(parse_records(records(1))[-1][0],1)

    def test_no_result_semantics_assumed(self):
        raw=records().replace(b'FR1=1;string;1;1;',b'FR1=1;other;0;0;')
        self.assertEqual(parse_records(raw)[0][:4],(1,'other',0,0))

    def test_unknown_trace_codes_and_raw_paths_refused(self):
        for raw in (records().replace(b'notify',b'/tmp/private',1),records()+b'x',b'x'*(MAX_OUTPUT+1)):
            with self.assertRaises(ValueError):parse_records(raw)

    def test_duplicate_completion_refused(self):
        with self.assertRaises(ValueError):parse_records(records().replace(b'FR1=1;',b'FR1=2;'))

    def test_missing_close_refusal_not_counted_as_completed_case(self):
        with self.assertRaises(ValueError):parse_records(records().replace(b'refuse_close,',b''))

    def test_reordered_flow_ids_refused(self):
        with self.assertRaises(ValueError):parse_records(records().replace(b'FR1=',b'FR2='))

    def test_complete_marker_bound_to_nonce_and_source(self):
        raw=marker(records());route.marker(raw,'a'*32,'completed')
        with self.assertRaises(ValueError):route.marker(raw,'b'*32,'completed')
        with self.assertRaises(ValueError):route.marker(raw.replace(SOURCE_SHA256.encode(),b'0'*64),'a'*32,'completed')

    def test_marker_duplicates_and_extra_fields_refused(self):
        raw=marker(records())
        with self.assertRaises(ValueError):route.marker(raw[:-1]+b',"records":""}','a'*32,'completed')
        with self.assertRaises(ValueError):route.marker(raw[:-1]+b',"path":"private"}','a'*32,'completed')

    def test_entered_marker_cannot_carry_records(self):
        with self.assertRaises(ValueError):route.marker(marker(records(),'entered'),'a'*32,'entered')
        route.marker(marker(b'','entered'),'a'*32,'entered')

    def test_stage_input_hashes_include_every_child_source(self):
        hashes={'scripts/form_results_packet/'+p:h for p,h in PACKET_HASHES.items()};route.verify_hashes(hashes)
        hashes.pop('scripts/form_results_packet/'+route.MODULES[1])
        with self.assertRaises(ValueError):route.verify_hashes(hashes)
