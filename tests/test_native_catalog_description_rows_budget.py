"""Independent rectangular wire maxima; synthetic sizes, not native evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import catalog_description_rows as p
import catalog_description_measurement as measurement
import inputs
import protocol
import snapshots
import test_native_catalog_description_rows_policy as fixtures


def wire(value):
    # Independent serializer: do not let the production cap hide oversize proofs.
    return json.dumps(value,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii')


def longest(values):return max(values,key=lambda v:len(wire(v)))


def comparison_envelope():
    physical={n:snapshots.MAX_FILE_BYTES for n in p.PHYSICAL_NUMBERS}
    physical.update(status=longest(('layout_observed','layout_unresolved')),descriptor_sha256='f'*64,
        active_count_known=False,utf16_count_matches=False,description_type=longest(('NVC','absent','unresolved')),value_sha256='f'*64)
    return {'status':longest(p.OUTCOMES),'metadata_matches':False,'physical':physical,
        'witness_sha256':'f'*64,'native_utf16_units':measurement.MAX_ACTUAL_UNITS,
        'native_unicode_scalars':measurement.MAX_ACTUAL_UNITS,'native_trailing_spaces':measurement.MAX_ACTUAL_UNITS,
        'count_evidence':longest(('not_distinguished','supplementary_utf16_units_observed')),
        'native_compatibility':'not_claimed'}


def capture_envelope():
    state={'snapshot':longest(p.TARGETS),'observe_token':'f'*32,'typed_uuid_verdict':'not_applicable',
        'origin':{'bytes':snapshots.MAX_FILE_BYTES,'sha256':'f'*64},
        'postimage':{'bytes':snapshots.MAX_FILE_BYTES,'sha256':'f'*64},
        'witness':{'sha256':'f'*64,'nonce':'f'*32,'token':'f'*32,'case':longest(p.CASES),
            'operation':'observe','present':False,'utf16_units':measurement.MAX_ACTUAL_UNITS,
            'scalar_count':measurement.MAX_ACTUAL_UNITS,'trailing_spaces':measurement.MAX_ACTUAL_UNITS},
        'comparison':comparison_envelope()}
    # Reserve all four comparison objects even though baseline is null.
    return {'schema':p.CAPTURE_SCHEMA,'profile_id':p.PROFILE_ID,'profile_sha256':p.PROFILE_SHA256,
        'states':[copy.deepcopy(state) for _ in p.TARGETS]}


def report_envelope():
    report=p.empty_report('f'*32,fixtures.provenance(),description_case=longest(p.CASES))
    report.update(status='failed',failed_stage=longest(protocol.STAGES),
        failure_kind=longest(protocol.FAILURES),accepted=False,description_measurement=None)
    report['provenance']['actual_version']=protocol.VERSION
    # Core fields are fixed-count; every independent scalar reserves its longest
    # admitted spelling, even if not simultaneously attainable in a valid report.
    for stage in report['stages']:stage.update(status='not_started',checks={k:False for k in stage['checks']})
    logical_values=[protocol.expected_logical(n) for n in protocol.SNAPSHOTS]
    logical={k:longest([v[k] for v in logical_values]) for k in logical_values[0]}
    physical={'bytes':snapshots.MAX_FILE_BYTES,'sha256':'f'*64,'page_analysis':'unsupported',
        'header':{'status':'header_layout_match','version':[255,255,255,255],
            'page_size':65536,'page_count':(1<<32)-1}}
    report['snapshots']=[{'id':n,'physical':copy.deepcopy(physical),'logical':copy.deepcopy(logical),
        'quiescent':False,'copy_verified':False} for n in protocol.SNAPSHOTS]
    report['artifacts']=[{'id':n,'source':src,'status':'ok','physical':{'bytes':snapshots.MAX_FILE_BYTES,
        'sha256':'f'*64,'header':'unknown','page_analysis':'unsupported'}} for n,src in protocol.ARTIFACTS.items()]
    changes={k:snapshots.MAX_FILE_BYTES for k in ('changed_bytes','unchanged_bytes','added_bytes','removed_bytes','changed_windows')}
    changes['size_delta']=-snapshots.MAX_FILE_BYTES
    samples=[snapshots.MAX_FILE_BYTES]*snapshots.MAX_SAMPLES
    report['comparisons']=[]
    for n,(src,ctrl,treat) in protocol.COMPARISONS.items():
        pair={'predecessor_bytes':snapshots.MAX_FILE_BYTES,'treatment_bytes':snapshots.MAX_FILE_BYTES,'treatment':changes.copy()}
        windows={'window_bytes':snapshots.WINDOW_BYTES,'count':snapshots.MAX_FILE_BYTES}
        if ctrl is None:
            pair['interpretation']='observational_before_after_not_causation';windows.update(changed_count=snapshots.MAX_FILE_BYTES,changed_sample=samples.copy())
        else:
            pair.update(control_bytes=snapshots.MAX_FILE_BYTES,control=changes.copy(),interpretation='physical_byte_differences_not_causation')
            for k in ('overlap','control_only','treatment_only'):windows.update({k+'_count':snapshots.MAX_FILE_BYTES,k+'_sample':samples.copy()})
        pair['byte_windows']=windows
        report['comparisons'].append({'id':n,'kind':'observational' if ctrl is None else 'matched_control','source':src,'control':ctrl,'treatment':treat,'physical':pair})
    report['rejected_basename']='1Cv8'+'X'*48
    report['failure_context']={'operation':longest(protocol.COMMAND_STAGES),'site':longest(protocol.CONTEXT_SITES),
        'bsl_phase':longest(protocol.BSL_PHASES),'region':longest(protocol.INVENTORY_REGIONS),
        'reason':longest(protocol.INVENTORY_REASONS),'entry_class':longest(snapshots.ENTRY_CLASSES),'entry_shape':longest(snapshots.ENTRY_SHAPES)}
    return report


def aggregate_envelope():
    return {'schema':p.AGGREGATE_SCHEMA,'lane':p.LANE,'accepted':True,'cases':[
        {'case':longest(p.CASES),'outcome':longest(p.OUTCOMES),'report_sha256':'f'*64,
         'source_sha256':'f'*64,'run_id':10**20-1,'run_attempt':10**6} for _ in p.CASES]}


def proof_results():
    shell=len(wire(report_envelope()))
    return {'sources':len(inputs.CATALOG_DESCRIPTION_ROWS_SOURCE_FILES),'physical_comparison':len(wire(comparison_envelope())),
        'capture_rectangular':len(wire(capture_envelope())),'capture_cap':p.MAX_CAPTURE_BYTES,
        'report_without_capture':shell,'report_full_capture_plus_newline':shell-4+p.MAX_CAPTURE_BYTES+1,
        'report_cap':protocol.MAX_REPORT_BYTES,'aggregate_plus_newline':len(wire(aggregate_envelope()))+1,
        'aggregate_cap':p.MAX_AGGREGATE_BYTES}


class DescriptionBudgetTests(unittest.TestCase):
    def test_full_rectangular_envelope_and_unchanged_caps(self):
        result=proof_results()
        self.assertEqual(result['sources'],42)
        self.assertEqual((result['capture_cap'],result['report_cap']),(8192,32768))
        self.assertLessEqual(result['capture_rectangular']+1,result['capture_cap'])
        self.assertLessEqual(result['report_full_capture_plus_newline'],result['report_cap'])
        self.assertLessEqual(result['aggregate_plus_newline'],result['aggregate_cap'])
        report=report_envelope()
        self.assertEqual(tuple(len(report[k]) for k in ('stages','snapshots','comparisons','artifacts')),(13,11,5,3))
        self.assertEqual(set(report['failure_context']),{'operation','site','bsl_phase','region','reason','entry_class','entry_shape'})
        self.assertEqual(len(report['cleanup']),4)
        self.assertEqual(result,EXPECTED)

    def test_bounds_cover_each_actual_public_field_without_private_strings(self):
        maximum=comparison_envelope()
        for case in p.CASES:
            for empty in (False,True):
                report=fixtures.fixture(case,empty=empty);fixtures.validate(report)
                self.assertLessEqual(len(wire(report))+1,proof_results()['report_full_capture_plus_newline'])
                for state in report['description_measurement']['states'][1:]:
                    actual=state['comparison'];self.assertEqual(set(actual),set(maximum));self.assertEqual(set(actual['physical']),set(maximum['physical']))
                    for key,value in actual['physical'].items():self.assertLessEqual(len(wire(value)),len(wire(maximum['physical'][key])),key)
                    self.assertLessEqual(len(wire(actual)),len(wire(maximum)))
        self.assertNotIn('actual_description',wire(capture_envelope()).decode())
        self.assertNotIn('actual_uuid',wire(capture_envelope()).decode())

    def test_private_schema3_witness_full_escaped_bound(self):
        maximum={'schema':3,'nonce':'f'*32,'token':'f'*32,'case':'description17','operation':'observe',
                 'present':False,'actual_description':'\x01'*128,'actual_uuid':'f'*8+'-'+ 'f'*4+'-'+ 'f'*4+'-'+ 'f'*4+'-'+ 'f'*12}
        size=len(wire(maximum))+3
        self.assertEqual(size,1007)
        self.assertLessEqual(size,measurement.WITNESS_LIMIT)
        raw=wire({**maximum,'present':True})
        value=measurement.validate_witness(raw,nonce='f'*32,token='f'*32,case='description17',operation='observe',rows=True)
        self.assertEqual(value.utf16_units,128)

    def test_budget_constructor_in_optimized_subprocess_has_same_values(self):
        # The external normal/-O invocation runs these same unittest assertions;
        # bound construction itself contains no optimization-removable assert.
        import ast
        tree=ast.parse(Path(__file__).read_text(encoding='utf-8'))
        self.assertFalse(any(isinstance(node,ast.Assert) for node in ast.walk(tree)))

EXPECTED = {'sources':42,'physical_comparison':1078,'capture_rectangular':6983,'capture_cap':8192,'report_without_capture':20219,'report_full_capture_plus_newline':28408,'report_cap':32768,'aggregate_plus_newline':633,'aggregate_cap':2048}
if __name__=='__main__':unittest.main()
