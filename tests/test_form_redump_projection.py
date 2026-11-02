"""Failed-only owned-source structure IDs: never raw XML/unknown strings."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
from form_runtime_packet import route
from test_form_runtime_route import files
from test_native_form_runtime_profile import envelope,host,NONCE,identity_validator


class FormRedumpProjectionTests(unittest.TestCase):
    def test_owned_structure_numeric_projection_does_not_admit_xml(self):
        data=files();projection=route.redump_projection(data,'form_xml')
        self.assertEqual(route.validate_redump_projection(projection),projection)
        self.assertEqual(projection['presence'],31)
        self.assertEqual(projection['xml_status'],'parsed')
        self.assertEqual(projection['namespaces'],[[1,1],[2,2],[3,3]])
        altered=dict(data);altered[route.DIAGNOSTIC_FILES[2]]=route.form_xml().replace(b'<MainAttribute>true',b'<MainAttribute>false')
        different=route.redump_projection(altered,'form_xml')
        self.assertNotEqual(different['rows'],projection['rows'])
        with self.assertRaises(ValueError):route.validate_redump(altered)
        newer=dict(data);newer[route.DIAGNOSTIC_FILES[2]]=route.form_xml().replace(b'version="2.4"',b'version="2.20"')
        self.assertIn([1,16],route.redump_projection(newer,'form_xml')['rows'][0][2])
        route.validate_redump(newer)  # Exact measured2.20 compatibility only.

    def test_unknown_namespace_attributes_text_are_always_redacted(self):
        canary='PRIVATE_CANARY_9417'
        data=files();raw=route.form_xml().replace(b'version="2.4"',b'version="'+canary.encode()+b'" unknown="'+canary.encode()+b'" xmlns:private="urn:'+canary.encode()+b'"')
        raw=raw.replace(b'<MainAttribute>true',b'<MainAttribute>'+canary.encode())
        data[route.DIAGNOSTIC_FILES[2]]=raw
        projection=route.redump_projection(data,'form_xml');route.validate_redump_projection(projection)
        rendered=json.dumps(projection)
        for forbidden in (canary,'urn:','private','unknown','<','MainAttribute'):
            self.assertNotIn(forbidden,rendered)
        self.assertIn([0,0],projection['namespaces'])
        self.assertIn([0,0],projection['rows'][0][2])
        self.assertEqual(projection['rows'][-1][3],0)
        with self.assertRaises(ValueError):route.validate_redump(data)
        data[route.DIAGNOSTIC_FILES[2]]=b'<private name="Object" unknown="true">FormCreate</private>'
        row=route.redump_projection(data,'form_xml')['rows'][0]
        self.assertEqual(row,[0,0,[[0,0],[0,0]],0,0,0])

    def test_dtd_oversize_depth_and_attribute_limits_reject_without_rows(self):
        for raw in (b'<!DOCTYPE Form [<!ENTITY x "PRIVATE">]><Form>&x;</Form>',
                    b'x'*8193,('<x>'*18+'PRIVATE'+'</x>'*18).encode(),
                    ('<x '+' '.join('a'+str(n)+'="PRIVATE"' for n in range(9))+'/>').encode()):
            result=route.redump_projection({route.DIAGNOSTIC_FILES[2]:raw},'form_xml')
            route.validate_redump_projection(result)
            self.assertNotEqual(result['xml_status'],'parsed')
            self.assertEqual(result['rows'],[]);self.assertEqual(result['namespaces'],[])
            self.assertNotIn('PRIVATE',json.dumps(result))

    def test_projection_schema_rejects_unknown_fields_strings_and_out_of_range_ids(self):
        value=route.redump_projection(files(),'form_xml')
        for edit in (lambda v:v.update(extra='PRIVATE'),lambda v:v.update(subphase='PRIVATE'),
                     lambda v:v.update(presence=True),lambda v:v.update(extra_count=33),
                     lambda v:v['rows'][0].__setitem__(1,999),lambda v:v['rows'][0].__setitem__(3,'PRIVATE'),
                     lambda v:v['namespaces'][0].__setitem__(1,'PRIVATE')):
            bad=copy.deepcopy(value);edit(bad)
            with self.assertRaises(ValueError):route.validate_redump_projection(bad)

    def test_host_accepts_projection_only_as_failed_no_output_redump(self):
        value,hashes,_=envelope();stage=value['report']['stage3']
        stage['redump_projection']=route.redump_projection(files(),'form_xml')
        with self.assertRaises(host.FormError):host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity_validator)
        value['outputs']=[];value['report'].update(status='stage3_failed',native_tests_completed=False)
        stage.update(status='failed',failure_phase='redump',failure_kind='module_mismatch',entered=False,completed=False,process_exited=False,witness_verified=False)
        with self.assertRaises(host.FormError) as caught:host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity_validator)
        self.assertEqual(caught.exception.native_failure['redump_projection'],stage['redump_projection'])
        for key,bad_value in (('input_sha256',{}),('source_sha256',None),('form_sha256',None),('module_sha256',None),('entered',True),('process_exited',True),('witness_verified',True)):
            bad=copy.deepcopy(value);bad['report']['stage3'][key]=bad_value
            with self.assertRaises(host.FormError) as rejected:host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity_validator)
            self.assertFalse(hasattr(rejected.exception,'native_failure'))
        stage['failure_phase']='enterprise'
        with self.assertRaises(host.FormError) as caught:host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,identity_validator)
        self.assertFalse(hasattr(caught.exception,'native_failure'))
