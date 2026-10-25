"""Entire schema-6 envelope and conditional private-writer model, not native evidence.

Independent maxima may coexist here even when a validator rejects the shape.
This charges every key, collection, exact source path, finite diagnostic and
trailing newline, rather than only currently observed small successful output.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'tests')]
import inputs
import protocol
import record_observation as metadata
import record_validation as policy
import snapshots
import test_native_1c_db_oracle_record_budget as previous

wire = previous.wire


def identity():
    value = previous.identity()
    value['sources'] = {path:'c'*64 for path in inputs.ROW_SOURCE_FILES}
    return value


def pinned_projections_envelope():
    # Physical identifiers have at most 64 non-escapable ASCII characters. All
    # logical/path/type cells and ordered declarations have exact admitted values.
    # Ignore aggregate768-unit limits for this bound: they can only reduce it.
    native = {'schema':1,'target':metadata.TARGET,'table':{'storage_name':'A'*64,
        'logical_name':metadata.TARGET,'metadata_name':metadata.TARGET,'fields':[]}}
    physical = {'schema':1,'target':metadata.TARGET,'table':{'name':'A'*64,
        'record_lock_token':'0','fields':[]}}
    for _,logical,path,decl in policy.ROLE_VECTOR:
        native['table']['fields'].append({'storage_name':'A'*64,'logical_name':logical,
            'metadata_name':path,'type_text':''})
        physical['table']['fields'].append(dict(zip(
            ('name','type_token','nullability','length','precision','case_token'),('A'*64,*decl))))
    return native,physical


def success_capture_envelope():
    measured = previous.bound_capture_skeleton()
    measured['native'],measured['reader'] = pinned_projections_envelope()
    return {'schema':policy.CAPTURE_SCHEMA,'status':'matched','profile_id':policy.PROFILE_ID,
        'profile_sha256':'f'*64,'record_reader_source_sha256':'f'*64,'metadata':measured,
        'states':[{'snapshot':identifier,'origin_sha256':'f'*64,'observe_token':'d'*32,
            'observer_bytes':snapshots.MAX_FILE_BYTES,'observer_sha256':'f'*64,
            'origin_framing':previous.longest(policy.FRAMINGS),
            'observer_framing':previous.longest(policy.FRAMINGS),'verdict':policy.STATE_VERDICT}
            for identifier in policy.TARGETS]}


def failure_capture_bound():
    return len(wire({'schema':policy.CAPTURE_SCHEMA,'status':'failed',
        'category':previous.longest(policy.DIAGNOSTICS),
        'code':previous.longest(code for codes in policy.DIAGNOSTICS.values() for code in codes)}))


def report_envelope():
    report = previous.complete_report_upper_envelope()
    del report['record_observation']
    report.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=identity(),record_readback=None)
    # Charge generous128-byte values to every finite optional diagnostic, as
    # the fresh independent schema-5 audit does. Their domains are checked below.
    report.update(failed_stage='X'*128,failure_kind='X'*128)
    report['failure_context'] = {key:'X'*128 for key in report['failure_context']}
    for snapshot in report['snapshots']:
        snapshot.update(quiescent=False,copy_verified=False)
    for key,success in (('reader_validation',metadata.VERDICT),
            ('metadata_validation',metadata.METADATA_VERDICT),('mapping_validation',policy.MAPPING_VERDICT),
            ('layout_validation',policy.LAYOUT_VERDICT),('record_validation',policy.VERDICT)):
        report[key] = previous.longest(('not_run','failed','discarded',success))
    return report


def report_bound():
    # Full enclosing cap, not the smaller seven-field capture currently derived.
    return len(wire(report_envelope()))-len(b'null')+policy.MAX_CAPTURE_BYTES+1


def private_marker_bound():
    # Native operation/BSL schema is unchanged and allows up to16 fields, not7.
    # ASCII escaping, four-space indentation, CRLF, final CRLF and optional BOM
    # are an explicit conditional model, NOT a verified native-writer envelope.
    # The BSL writer uses unmeasured defaults. Its runtime32768-byte read cap
    # is authoritative and fails closed regardless of formatting. Reserve6144
    # native projection cap rather than the smaller derived5938 projection.
    native = previous.native_projection(metadata.MAX_FIELDS)
    native['table'].update(storage_name='',logical_name='\ufffd'*metadata.MAX_TEXT_UNITS)
    for field in native['table']['fields']: field['storage_name']=''
    marker={'schema':1,'nonce':'a'*32,'token':'b'*32,'operation':metadata.OPERATION,'status':'ok',
        'actual_version':protocol.VERSION,'user':'NativeOracleSetup','role_verified':True,
        'nonprivileged':True,'metadata_version':1,'count':None,'code':None,'payload':None,
        'amount':None,'deletion_mark':None,'same_reference':None,'users_verified':True,
        'payload_length':32,'amount_digits':9,'amount_scale':2,'record_metadata':native}
    pretty=json.dumps(marker,ensure_ascii=True,indent=4,allow_nan=False).replace('\n','\r\n').encode('ascii')
    return len(pretty)+metadata.MAX_NATIVE_BYTES-len(wire(native))+2+3


def proof_results():
    native,physical=pinned_projections_envelope()
    return {'source_count':len(inputs.ROW_SOURCE_FILES),'native_pinned_projection':len(wire(native)),
        'physical_pinned_projection':len(wire(physical)),'complete_success_capture':len(wire(success_capture_envelope())),
        'finite_failure_capture':failure_capture_bound(),'capture_cap':policy.MAX_CAPTURE_BYTES,
        'public_envelope_without_capture':len(wire(report_envelope())),
        'public_report_with_full_capture_cap_and_newline':report_bound(),
        'public_report_cap':protocol.MAX_REPORT_BYTES,'public_margin':protocol.MAX_REPORT_BYTES-report_bound(),
        'private_marker':private_marker_bound(),'private_marker_cap':protocol.MAX_REPORT_BYTES}


class CompleteReadbackBudgetTests(unittest.TestCase):
    def test_exact_versions_source_inventory_and_unchanged_caps(self):
        self.assertEqual((policy.SCHEMA,policy.CAPTURE_SCHEMA),(6,7))
        self.assertEqual((len(inputs.SOURCE_FILES),len(inputs.RECORD_SOURCE_FILES),len(inputs.ROW_SOURCE_FILES)),(20,21,23))
        self.assertEqual(inputs.ROW_SOURCE_FILES,{**inputs.RECORD_SOURCE_FILES,
            policy.MODULE_SOURCE:'record_validation.py',policy.READER_SOURCE:'filedb_records.py'})
        self.assertEqual((metadata.MAX_NATIVE_BYTES,metadata.MAX_PHYSICAL_BYTES,policy.MAX_CAPTURE_BYTES,
                          protocol.MAX_REPORT_BYTES),(6144,4096,12288,32768))
        self.assertEqual((snapshots.MAX_FILE_BYTES,snapshots.MAX_LIVE_BYTES),(67108864,536870912))

    def test_entire_report_collections_cleanup_and_optional_diagnostics_charged(self):
        value=report_envelope()
        self.assertEqual(tuple(map(lambda k:len(value[k]),('stages','snapshots','artifacts','comparisons'))),(13,11,3,5))
        self.assertEqual(set(value)-set(protocol.empty_report(previous.NONCE,identity())),
                         policy.EXTRA_KEYS|{'rejected_basename','failure_context'})
        self.assertEqual(len(value['cleanup']),4)
        self.assertTrue(all(v is False for v in value['cleanup'].values()))
        for item in value['stages']:
            self.assertEqual(set(item['checks']),set(protocol.CHECKS[item['id']]))
            self.assertTrue(all(v is False for v in item['checks'].values()))
        for comparison in value['comparisons']:
            samples=[v for k,v in comparison['physical']['byte_windows'].items() if k.endswith('_sample')]
            self.assertTrue(all(len(v)==snapshots.MAX_SAMPLES for v in samples))
        self.assertEqual(report_bound(),len(wire(value))-4+12288+1)
        self.assertLessEqual(report_bound(),protocol.MAX_REPORT_BYTES)

    def test_every_optional_finite_domain_fits_generous128_allowance(self):
        domains=set(protocol.STAGES)|set(protocol.FAILURES)|{metadata.FAILURE_KIND,policy.FAILURE_KIND}
        domains.update(protocol.COMMAND_STAGES);domains.add('enterprise_'+metadata.OPERATION)
        for domain in (protocol.CONTEXT_SITES,protocol.BSL_PHASES,metadata.PHASES,
                       protocol.INVENTORY_REGIONS,protocol.INVENTORY_REASONS,
                       snapshots.ENTRY_CLASSES,snapshots.ENTRY_SHAPES): domains.update(domain)
        self.assertTrue(all(type(value) is str and value.isascii() and len(value)<=128 for value in domains))

    def test_complete_capture_and_every_failure_variant_fit_without_truncation(self):
        self.assertLessEqual(len(wire(success_capture_envelope())),policy.MAX_CAPTURE_BYTES)
        self.assertLess(failure_capture_bound(),len(wire(success_capture_envelope())))
        for category,codes in policy.DIAGNOSTICS.items():
            for code in codes:
                self.assertLessEqual(len(wire({'schema':7,'status':'failed','category':category,'code':code})),failure_capture_bound())
        self.assertLessEqual(private_marker_bound(),protocol.MAX_REPORT_BYTES)

    def test_reviewed_complete_envelopes_are_pinned(self):
        self.assertEqual(proof_results(),{
            'source_count':23,'native_pinned_projection':1998,'physical_pinned_projection':1293,
            'complete_success_capture':5622,'finite_failure_capture':113,'capture_cap':12288,
            'public_envelope_without_capture':19162,
            'public_report_with_full_capture_cap_and_newline':31447,
            'public_report_cap':32768,'public_margin':1321,
            'private_marker':8931,'private_marker_cap':32768})

if __name__=='__main__': unittest.main()
