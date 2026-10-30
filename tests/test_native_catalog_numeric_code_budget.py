"""Independent standalone projections only; no integrated report budget claim."""
import json
import unittest
import test_native_catalog_numeric_code_measurement as fixture
import catalog_numeric_code_measurement as m


def wire(value):return json.dumps(value,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii')


def physical_envelope():
    # Independent rectangular scalar bounds. No observed fixture sizes.
    return dict(status='layout_unresolved',runtime_support='not_claimed',descriptor_sha256='f'*64,
        code_length=38,description_length=8,payload_length=64,field_count=16,record_size=4096,
        active_count=1,active_count_known=False,code_type='unresolved',code_ordinal=15,
        code_offset=4096,code_width=4096,code_precision=38,code_scale=0,digit_count=38,
        previous_ordinal=15,previous_offset=4096,next_ordinal=15,next_offset=4096,
        previous_displacement=4096,next_displacement=4096)


def comparison_envelope():
    return dict(status='case_metadata_mismatch',metadata_matches=False,code_verdict='not_compared',
        uuid_verdict='not_compared',description_verdict='not_compared',physical=physical_envelope(),
        witness_sha256='f'*64,runtime_support='not_claimed')


def proof_results():
    private=fixture.raw(case='number6',operation='observe',actual_description='\u0800'*128,
        actual_code='-'+'1'*77+'.0',code_length=2047,description_length=2047,payload_length=2047)
    return dict(private_witness_with_bom=len(private)+3,private_cap=m.WITNESS_LIMIT,
        physical_projection=len(wire(physical_envelope())),comparison=len(wire(comparison_envelope())),
        standalone_projection_cap=2048,integrated_capture_cap=8192,integrated_report_cap=32768,
        integrated_envelope_proven=False)


class NumericCodeBudgetTests(unittest.TestCase):
    def test_independent_rectangular_private_and_projection_bounds(self):
        value=proof_results()
        self.assertLessEqual(value['private_witness_with_bom'],2048)
        self.assertLessEqual(value['comparison'],2048)
        self.assertLessEqual(value['physical_projection'],2048)
        self.assertFalse(value['integrated_envelope_proven'])

    def test_real_projection_key_closure_and_serialized_bounds(self):
        import test_native_catalog_numeric_code_physical as f
        observation=f.read(f.source(number=123))
        witness=fixture.read(fixture.raw(actual_uuid=str(observation.typed_uuid),actual_description=observation.records.rows[0].fields[5].value))
        actual=m.compare_readback(observation,witness,case='number3')
        self.assertEqual(set(actual),set(comparison_envelope()))
        self.assertEqual(set(actual['physical']),set(physical_envelope()))
        self.assertLessEqual(len(wire(actual)),len(wire(comparison_envelope())))

if __name__=='__main__':unittest.main()
