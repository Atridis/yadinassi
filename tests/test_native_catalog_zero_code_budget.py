"""Independent integrated numeric envelope maxima; no native evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import catalog_zero_code_policy as p
import catalog_zero_code_measurement as measurement
import inputs
import protocol
import snapshots
import test_native_catalog_zero_code_policy as fixtures

def wire(value):return json.dumps(value,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii')
def longest(values):return max(values,key=lambda value:len(wire(value)))

def comparison_envelope():
    physical={k:4096 for k in p.PHYSICAL_NUMBERS}
    physical.update(status='layout_unresolved',runtime_support='not_claimed',descriptor_sha256='f'*64,active_count_known=False)
    return dict(schema=1,metadata_matches=False,code_availability='unavailable',uuid_verdict='unresolved',
        description_verdict='not_applicable',physical=physical,witness_sha256='f'*64)

def private_witness_envelope():
    return dict(schema=1,nonce='f'*32,token='f'*32,case=longest(p.CASES),operation='observe',present=False,
        code_type='string',code_state='unavailable',actual_code='\uffff'*128,actual_uuid='f'*36,
        actual_description='\uffff'*128,code_length=2047,description_length=2047,payload_length=2047,autonumbering=False)


def capture_envelope():
    state={'snapshot':longest(p.TARGETS),'observe_token':'f'*32,
        'origin':{'bytes':snapshots.MAX_FILE_BYTES,'sha256':'f'*64},
        'postimage':{'bytes':snapshots.MAX_FILE_BYTES,'sha256':'f'*64},
        'witness':{'sha256':'f'*64,'nonce':'f'*32,'token':'f'*32,'case':longest(p.CASES),
            'operation':'observe','present':False,'code_length':0,'description_length':8,
            'payload_length':64,'autonumbering':False,'code_type':'string','code_state':'unavailable','code_is_empty':False},'comparison':comparison_envelope()}
    return {'schema':p.CAPTURE_SCHEMA,'profile_id':p.PROFILE_ID,'profile_sha256':p.PROFILE_SHA256,
        'runtime_support':'not_claimed','states':[copy.deepcopy(state)for _ in p.TARGETS]}

def diagnostic_envelope():
    # Rectangular maxima; need not describe one simultaneously valid execution.
    value = dict(schema=1,nonce='f'*32,token='f'*32,bootstrap='valid_ok',result='valid_ok',completion='valid_error',pending='valid_error',
        **{name:dict(state='unavailable',module_error=False,undefined_symbol=False,syntax_error=False)for name in ('out','console')})

    value['frontier'] = {point:dict(state='invalid',status='returned',phase=longest(protocol.BSL_PHASES)) for point in measurement.FRONTIER_POINTS}
    value['compile'] = dict(state=longest(measurement.COMPILE_STATES),result_code=255,log_state='unavailable',issues=[dict(module=longest(measurement.COMPILE_MODULES),line=65535,column=65535,category=longest(measurement.COMPILE_CATEGORIES)) for _ in range(8)],truncated=False)
    return value

def report_envelope():
    report=p.empty_report('f'*32,fixtures.provenance(),zero_case=longest(p.CASES))
    report.update(status='failed',failed_stage=longest(protocol.STAGES),
        failure_kind=longest(protocol.FAILURES),accepted=False,zero_code_measurement=None)
    report['provenance']['actual_version']=protocol.VERSION
    # Core fields are fixed-count; every independent scalar reserves its longest
    # admitted spelling, even if not simultaneously attainable in a valid report.
    for stage in report['stages']:stage.update(status='not_started',checks={k:False for k in stage['checks']})
    logical_values=[p.expected_logical(n) for n in protocol.SNAPSHOTS]
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
    report['zero_bootstrap_failure']=diagnostic_envelope()
    return report


def aggregate_envelope():
    return {'schema':p.AGGREGATE_SCHEMA,'lane':p.LANE,'accepted':True,'cases':[
        {'case':longest(p.CASES),'outcome':longest(p.OUTCOMES),'report_sha256':'f'*64,
        'source_sha256':'f'*64,'run_id':10**20-1,'run_attempt':10**6}for _ in p.CASES]}

def proof_results():
    shell=len(wire(report_envelope()))
    return {'diagnostic':len(wire(diagnostic_envelope())),'sources':len(inputs.CATALOG_ZERO_CODE_SOURCE_FILES),'comparison':len(wire(comparison_envelope())),
        'capture_plus_newline':len(wire(capture_envelope()))+1,'capture_cap':p.MAX_CAPTURE_BYTES,
        'report_without_capture':shell,'report_full_capture_plus_newline':shell-4+p.MAX_CAPTURE_BYTES+1,
        'report_cap':protocol.MAX_REPORT_BYTES,'aggregate_plus_newline':len(wire(aggregate_envelope()))+1,
        'aggregate_cap':p.MAX_AGGREGATE_BYTES,'private_witness_plus_bom':len(wire(private_witness_envelope()))+3}

class ZeroIntegrationBudgetTests(unittest.TestCase):
    def test_rectangular_source_logicaltag_and_full_capture_reservation(self):
        result=proof_results();self.assertEqual(result['sources'],42)
        self.assertEqual((result['capture_cap'],result['report_cap'],result['aggregate_cap']),(8192,32768,2048))
        for actual,cap in [('capture_plus_newline','capture_cap'),('report_full_capture_plus_newline','report_cap'),('aggregate_plus_newline','aggregate_cap')]:self.assertLessEqual(result[actual],result[cap])
        self.assertLessEqual(result['private_witness_plus_bom'],measurement.WITNESS_LIMIT)
        report=report_envelope();self.assertEqual(tuple(len(report[k])for k in ('stages','snapshots','comparisons','artifacts')),(13,11,5,3))
        self.assertEqual(len(report['provenance']['sources']),42)
        self.assertTrue(all(s['logical']['code']=='observed_no_code'for s in report['snapshots']))
        self.assertEqual(result,EXPECTED)

    def test_actual_outcomes_and_closed_private_projection_bounds(self):
        maximum=comparison_envelope()
        for case in p.CASES:
            for outcome in (p.OUTCOMES if case=='zero8' else ('readback_matches','layout_unresolved')):
                report=fixtures.fixture(case,outcome=outcome);fixtures.validate(report)
                self.assertLessEqual(len(wire(report))+1,proof_results()['report_full_capture_plus_newline'])
                self.assertLessEqual(len(wire(report['zero_code_measurement']))+1,proof_results()['capture_plus_newline'])
                for state in report['zero_code_measurement']['states'][1:]:
                    actual=state['comparison'];self.assertEqual(set(actual),set(maximum));self.assertEqual(set(actual['physical']),set(maximum['physical']))
                    for key,value in actual['physical'].items():self.assertLessEqual(len(wire(value)),len(wire(maximum['physical'][key])))
        for key in ('actual_code','actual_uuid','actual_description','raw_bytes','number_hash'):
            self.assertNotIn(('"'+key+'":').encode(),wire(capture_envelope()))

    def test_no_optimization_removable_proof_assertions(self):
        import ast
        self.assertFalse(any(isinstance(node,ast.Assert)for node in ast.walk(ast.parse(Path(__file__).read_text(encoding='utf-8')))))

EXPECTED = {'diagnostic': 1489, 'sources': 42, 'comparison': 620, 'capture_plus_newline': 5373, 'capture_cap': 8192, 'report_without_capture': 21869, 'report_full_capture_plus_newline': 30058, 'report_cap': 32768, 'aggregate_plus_newline': 612, 'aggregate_cap': 2048, 'private_witness_plus_bom': 1921}
if __name__=='__main__':unittest.main()
