"""Offline framing/template checks, never native form acceptance."""
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from scripts.inventory_enum_forms_packet.records import GROUPS, MAX_OUTPUT, parse_records

ROOT = Path(__file__).resolve().parents[1] / 'scripts/inventory_enum_forms_packet'


def wire():
    return ''.join(name + '=observed;0\n' for name in GROUPS).encode('ascii')


class EnumFormsPacketTests(unittest.TestCase):
    def test_complete_ordered_records(self):
        self.assertEqual(parse_records(wire()), tuple((name, ('observed', '0')) for name in GROUPS))

    def test_observation_is_not_truth_acceptance(self):
        self.assertEqual(parse_records(wire())[0][1][-1], '0')

    def test_exact_bytes_only(self):
        for value in (wire().decode(), bytearray(wire()), None):
            with self.subTest(kind=type(value)), self.assertRaises(ValueError): parse_records(value)

    def test_bounds(self):
        for value in (b'', b'x' * (MAX_OUTPUT + 1)):
            with self.assertRaises(ValueError): parse_records(value)

    def test_all_groups_required(self):
        with self.assertRaises(ValueError): parse_records(wire().split(b'\n', 1)[1])

    def test_duplicate_or_reordered_group_refused(self):
        for value in (wire().replace(GROUPS[1].encode(), GROUPS[0].encode()),
                      wire().replace(GROUPS[0].encode(), b'unknown')):
            with self.assertRaises(ValueError): parse_records(value)

    def test_no_extra_record_or_missing_final_delimiter(self):
        for value in (wire() + b'extra=x\n', wire()[:-1]):
            with self.assertRaises(ValueError): parse_records(value)

    def test_payload_is_bounded_data_only(self):
        for payload in (b'', b'a' * 97, b'a;' * 16 + b'a', b'private/path', b'x\x00', 'значение'.encode()):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_records(wire().replace(b'observed;0', payload, 1))

    def test_configuration_object_binding_is_not_external(self):
        ns = {'f': 'http://v8.1c.ru/8.3/xcf/logform', 'v8': 'http://v8.1c.ru/8.1/data/core'}
        for owner, kind in (('Products', 'Catalog'), ('Receipt', 'Document')):
            form = ET.fromstring((ROOT / owner / 'Form.xml').read_bytes())
            obj = form.find("f:Attributes/f:Attribute[@name='Object']", ns)
            self.assertEqual(obj.find('f:Type/v8:Type', ns).text, f'cfg:{kind}Object.{owner}')
            self.assertEqual(obj.find('f:MainAttribute', ns).text, 'true')

    def test_real_event_binding_names(self):
        ns = {'f': 'http://v8.1c.ru/8.3/xcf/logform'}
        for owner in ('Products', 'Receipt'):
            form = ET.fromstring((ROOT / owner / 'Form.xml').read_bytes())
            events = tuple((e.attrib['name'], e.text) for e in form.findall('f:Events/f:Event', ns))
            self.assertEqual(events, (('OnCreateAtServer', 'ObservedCreate'), ('OnOpen', 'ObservedOpen')))

    def test_form_metadata_distinct_identities(self):
        from uuid import UUID
        ns = {'m': 'http://v8.1c.ru/8.3/MDClasses'}
        ids = []
        for owner in ('Products', 'Receipt'):
            form = ET.fromstring((ROOT / owner / 'Card.xml').read_bytes()).find('m:Form', ns)
            ids.append(UUID(form.attrib['uuid']))
            self.assertEqual(form.find('m:Properties/m:Name', ns).text, 'Card')
            self.assertEqual(form.find('m:Properties/m:FormType', ns).text, 'Managed')
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(value.int for value in ids))

    def test_no_saved_native_observations_or_runtime_claim(self):
        self.assertFalse((ROOT / 'observations.out').exists())
        self.assertFalse((ROOT / 'provenance.json').exists())


class EnumFormsMaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(ROOT.parent))
        from inventory_enum_forms_packet import material
        cls.material = material

    def test_authored_material_is_accepted(self):
        for owner in ('Products', 'Receipt'):
            self.material.managed_form((ROOT/owner/'Form.xml').read_bytes())
            self.material.metadata_form((ROOT/owner/'Card.xml').read_bytes())
            for filename, project in (('Card.xml',self.material.metadata_form),('Form.xml',self.material.managed_form)):
                raw=(ROOT/owner/filename).read_bytes()
                self.assertEqual(project(raw),project(raw.replace(b'version="2.4"',b'version="2.20"')))

    def test_unknown_root_behavior_refused(self):
        raw=(ROOT/'Products/Form.xml').read_bytes()
        for extra in (b'<Event name="OnClose">Injected</Event>',b'<Command name="Write"/>',b'<Events/>'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.material.managed_form(raw.replace(b'</Form>',extra+b'</Form>'))

    def test_additional_attribute_refused(self):
        raw=(ROOT/'Products/Form.xml').read_bytes()
        with self.assertRaises(ValueError):
            self.material.managed_form(raw.replace(b'</Attributes>',b'<Attribute name="Other" id="2"/></Attributes>'))

    def test_attribute_behavior_and_extra_attributes_refused(self):
        raw=(ROOT/'Products/Form.xml').read_bytes()
        for value in (raw.replace(b'</Attribute>',b'<Event name="OnChange">Injected</Event></Attribute>'),
                      raw.replace(b'name="Object"',b'name="Object" behavior="injected"')):
            with self.assertRaises(ValueError): self.material.managed_form(value)

    def test_command_and_parameter_defaults_must_be_empty(self):
        raw=(ROOT/'Products/Form.xml').read_bytes()
        for name in (b'Commands',b'Parameters',b'CommandInterface',b'ChildItems'):
            injected=b'<'+name+b'><Unknown/></'+name+b'>'
            with self.assertRaises(ValueError):
                self.material.managed_form(raw.replace(b'</Form>',injected+b'</Form>'))

    def test_metadata_passive_properties_do_not_define_parity(self):
        raw=(ROOT/'Products/Card.xml').read_bytes()
        changed=raw.replace(b'<Comment/>',b'<Comment>Designer presentation</Comment>')
        changed=changed.replace(b'</Properties>',b'<DesignerDefault>true</DesignerDefault></Properties>')
        changed=changed.replace(b'PersonalComputer',b'PlatformApplication')
        self.assertEqual(self.material.metadata_form(raw),self.material.metadata_form(changed))
        changed=raw.replace(b'<Name>Card</Name>',b'<Name>Other</Name>')
        self.assertNotEqual(self.material.metadata_form(raw),self.material.metadata_form(changed))

    def test_form_passive_defaults_do_not_define_parity(self):
        raw=(ROOT/'Products/Form.xml').read_bytes()
        changed=raw.replace(b'</Form>',b'<Title>Designer presentation</Title><AutoTitle>false</AutoTitle></Form>')
        changed=changed.replace(b'<MainAttribute>',b'<SavedData>true</SavedData><MainAttribute>')
        self.assertEqual(self.material.managed_form(raw),self.material.managed_form(changed))

    def test_diagnostics_are_finite_component_labels_only(self):
        from scripts.inventory_enum_forms_packet import route
        expected={}
        for kind,owner in (('Catalog','Products'),('Document','Receipt')):
            prefix=kind+'s/'+owner
            expected[prefix+'.xml']=('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><'+kind+'><ChildObjects><Form>Card</Form></ChildObjects></'+kind+'></MetaDataObject>').encode()
            expected[prefix+'/Forms/Card.xml']=(ROOT/owner/'Card.xml').read_bytes()
            expected[prefix+'/Forms/Card/Ext/Form.xml']=(ROOT/owner/'Form.xml').read_bytes()
            expected[prefix+'/Forms/Card/Ext/Form/Module.bsl']=b'// exact module'
        actual=dict(expected)
        actual['Catalogs/Products/Forms/Card/Ext/Form/Module.bsl']=b'// other'
        self.assertEqual(self.material.diagnostic(expected,actual),['products_module'])
        actual=dict(expected)
        key='Documents/Receipt/Forms/Card/Ext/Form.xml'
        actual[key]=actual[key].replace(b'>ObservedOpen<',b'>Other<')
        self.assertEqual(self.material.diagnostic(expected,actual),['receipt_binding'])
        self.assertTrue(self.material.valid_diagnostic(['receipt_binding']))
        for invalid in ([],['/private/path'],['receipt_binding']*2,'receipt_binding'):
            self.assertFalse(self.material.valid_diagnostic(invalid))

    def test_type_and_event_binding_changes_are_material(self):
        raw=(ROOT/'Products/Form.xml').read_bytes()
        with self.assertRaises(ValueError):
            self.material.managed_form(raw.replace(b'>ObservedOpen<',b'>Injected<'))
        changed=raw.replace(b'CatalogObject.Products',b'DocumentObject.Receipt')
        self.assertNotEqual(self.material.managed_form(raw),self.material.managed_form(changed))


class EnumFormsRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0,str(ROOT.parent))
        from inventory_enum_forms_packet import route
        cls.route=route

    def trace(self):
        events=[]
        for flow in range(1,8):
            for instance in ((1,2) if flow==3 else (1,)):
                events.extend(dict(flow=flow,instance=instance,code=code) for code in ('create','open','observed'))
        events.extend(dict(flow=8,instance=i,code=c) for i,c in ((1,'create'),(1,'open'),(2,'create'),(2,'open'),(1,'observed'),(2,'observed')))
        return dict(nonce='a'*32,events=events)

    def encode(self,value):
        import json
        return json.dumps(value).encode()

    def test_complete_actual_lifecycle_trace(self):
        self.assertTrue(self.route.lifecycle(self.encode(self.trace()),'a'*32))

    def test_missing_lifecycle_is_not_openform_argument_proof(self):
        value=self.trace();value['events'].pop()
        with self.assertRaises(ValueError):self.route.lifecycle(self.encode(value),'a'*32)

    def test_same_nonce_required(self):
        with self.assertRaises(ValueError):self.route.lifecycle(self.encode(self.trace()),'b'*32)

    def test_independent_instances_must_both_be_open(self):
        value=self.trace();value['events'][-6:]=[dict(flow=8,instance=i,code=c) for i in (1,2) for c in ('create','open','observed')]
        with self.assertRaises(ValueError):self.route.lifecycle(self.encode(value),'a'*32)

    def test_duplicate_instance_event_refused(self):
        value=self.trace();value['events'][1]=dict(value['events'][0])
        with self.assertRaises(ValueError):self.route.lifecycle(self.encode(value),'a'*32)

    def test_boolean_lifecycle_identity_refused(self):
        value=self.trace();value['events'][0]['instance']=True
        with self.assertRaises(ValueError):self.route.lifecycle(self.encode(value),'a'*32)

    def test_packet_assets_are_exact_and_launcher_only_sources(self):
        assets=self.route.packet();sources=self.route.sources()
        self.assertTrue(set(sources)<set(assets))
        self.assertTrue(all(p=='Launcher.xml' or p.startswith('Launcher/') for p in sources))
        self.assertNotIn(b'SOURCE_VALUE',sources[self.route.EXECUTABLE_MODULES[0]])

    def test_packet_hash_drift_refused(self):
        hashes={'scripts/inventory_enum_forms_packet/'+p:h for p,h in self.route.PACKET_HASHES.items()}
        self.route.verify_hashes(hashes)
        hashes[next(iter(hashes))]='0'*64
        with self.assertRaises(ValueError):self.route.verify_hashes(hashes)

    def test_extra_executable_or_modified_module_refused(self):
        files={p:self.route.sources()[p] for p in self.route.EXECUTABLE_MODULES}
        self.route.validate_executable_redump(files)
        for changed in (dict(files,unexpected=b'x'),{**files,self.route.EXECUTABLE_MODULES[0]:b'changed'}):
            with self.assertRaises(ValueError):self.route.validate_executable_redump(changed)

    def marker(self):
        return dict(schema=self.route.SCHEMA,nonce='a'*32,phase='completed',source_sha256=self.route.SOURCE_SHA256,form_sha256=self.route.FORM_SHA256,records=wire().decode())

    def test_completed_marker_requires_all_eight_records(self):
        value=self.marker();self.route.marker(self.encode(value),'a'*32,'completed')
        value['records']=''
        with self.assertRaises(ValueError):self.route.marker(self.encode(value),'a'*32,'completed')

    def test_marker_source_and_form_binding(self):
        for key in ('source_sha256','form_sha256'):
            value=self.marker();value[key]='0'*64
            with self.assertRaises(ValueError):self.route.marker(self.encode(value),'a'*32,'completed')

    def test_duplicate_json_witness_key_refused(self):
        raw=self.encode(self.trace()).replace(b'{',b'{"nonce":"b",',1)
        with self.assertRaises(ValueError):self.route.lifecycle(raw,'a'*32)


    def test_generated_module_pipeline_preserves_exact_source_admission(self):
        import sys
        sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import full_suite
        sources=self.route.sources()
        generated={p:full_suite.generated_module(raw) if p.endswith('.bsl') else raw for p,raw in sources.items()}
        self.assertEqual(self.route.validate_redump(generated),self.route.module_digest())
        generated['Launcher.xml']+=b' '
        with self.assertRaises(ValueError):self.route.validate_redump(generated)

    def test_fixed_module_accessor_matches_launcher_source(self):
        self.assertEqual(self.route.module(),self.route.sources()[self.route.EXECUTABLE_MODULES[0]])
        self.assertLessEqual(len(self.route.module()),self.route.MAX_SOURCE)
        import sys
        sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import native_1c_owned_enum_forms_profile as host
        import owned_enum_forms_suite as stage
        self.assertEqual(host.staged_files(),stage.INPUT_FILES)
        self.assertEqual(set(stage.empty_report('a'*32)),host.STAGE_KEYS)
        self.assertTrue(all((ROOT.parent.parent/source).is_file() for source in stage.INPUT_FILES))
        self.assertEqual(len(set(stage.INPUT_FILES.values())),len(stage.INPUT_FILES))


    def test_host_requires_configuration_and_lifecycle_acceptance_before_export(self):
        import base64, copy, hashlib, json, sys
        sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import native_1c_owned_enum_forms_profile as host
        import owned_enum_forms_suite as stage
        nonce='a'*32; raw=wire(); hashes={p:hashlib.sha256((ROOT.parent.parent/p).read_bytes()).hexdigest() for p in host.staged_files()}
        report=stage.empty_report(nonce)
        report.update(status='ok',failure_kind='none',failure_phase='final',input_sha256=hashes,
                      source_sha256=self.route.SOURCE_SHA256,form_sha256=self.route.FORM_SHA256,
                      module_sha256=self.route.module_digest(),roundtrip_sha256=self.route.module_digest(),
                      output_sha256=hashlib.sha256(raw).hexdigest(),output_size=len(raw),record_count=8)
        report.update({flag:True for flag in host.FLAGS})
        report['lifecycle_events']=self.trace()['events']
        report['process_diagnostics'].update(stage='after_exit',reason='none')
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'stage.json';stage.write_report(output,report)
            self.assertLessEqual(output.stat().st_size,stage.MAX_STAGE_REPORT)
            self.assertEqual(json.loads(output.read_bytes()),report)
        envelope=dict(schema=host.SCHEMA,profile=host.PROFILE,nonce=nonce,
                      report=dict(status='ok',native_tests_completed=True,stage3=report),
                      outputs=[dict(name='owned-enum-forms.out',size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),data_b64=base64.b64encode(raw).decode())])
        # Bootstrap envelope validation has its own suite; this test isolates the
        # NEW stage acceptance, not a substitute permissive production validator.
        validator=lambda raw,**kwargs:json.loads(raw)
        self.assertEqual(host.validate_envelope(self.encode(envelope),nonce,hashes,validator)[1],raw)
        bad=copy.deepcopy(envelope);bad['report']['stage3']['lifecycle_progress']=[]
        with self.assertRaises(host.FormError):host.validate_envelope(self.encode(bad),nonce,hashes,validator)
        bad=copy.deepcopy(envelope);bad['report']['stage3']['launcher_progress']=dict(phase='before_open',flow=1)
        with self.assertRaises(host.FormError):host.validate_envelope(self.encode(bad),nonce,hashes,validator)
        for flag in ('config_verified','lifecycle_verified','quiet','process_exited'):
            bad=copy.deepcopy(envelope);bad['report']['stage3'][flag]=False
            with self.subTest(flag=flag), self.assertRaises(host.FormError):
                host.validate_envelope(self.encode(bad),nonce,hashes,validator)
        bad=copy.deepcopy(envelope);bad['report']['stage3']['lifecycle_events'][0]['code']='observed'
        with self.assertRaises(host.FormError):host.validate_envelope(self.encode(bad),nonce,hashes,validator)


class EnumFormsCheckoutTests(unittest.TestCase):
    def test_autocrlf_checkout_preserves_every_authored_asset(self):
        import hashlib, shutil, subprocess, tempfile
        from scripts.inventory_enum_forms_packet.assets import ASSET_HASHES
        if shutil.which('git') is None:
            self.skipTest('git required for real checkout contract')
        with tempfile.TemporaryDirectory() as temp:
            repo=Path(temp)
            def git(*args):
                return subprocess.run(['git','-C',str(repo),*args],check=True,
                                      stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            git('init','-q');git('config','core.autocrlf','true')
            (repo/'.gitattributes').write_bytes((ROOT.parent.parent/'.gitattributes').read_bytes())
            for name in ASSET_HASHES:
                target=repo/'scripts/inventory_enum_forms_packet'/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/name).read_bytes())
            git('add','.gitattributes','scripts')
            git('checkout-index','--all','--force')
            for name,digest in ASSET_HASHES.items():
                with self.subTest(name=name):
                    self.assertEqual(hashlib.sha256((repo/'scripts/inventory_enum_forms_packet'/name).read_bytes()).hexdigest(),digest)

    def test_install_failure_phases_are_closed_and_preserved(self):
        import json, sys
        sys.path.insert(0,str(ROOT.parent));sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import native_1c_owned_enum_forms_profile as host
        import owned_enum_forms_suite as stage
        self.assertEqual(host.PHASES,stage.PHASES)
        for phase in ('install_load','install_update','install_redump','install_material'):
            report=stage.empty_report('a'*32)
            report.update(status='failed',failure_kind='module_mismatch',failure_phase=phase,redump_projection=['products_module'])
            envelope=dict(schema=host.SCHEMA,profile=host.PROFILE,nonce='a'*32,
                          report=dict(status='stage3_failed',native_tests_completed=False,stage3=report),outputs=[])
            with self.subTest(phase=phase), self.assertRaises(host.FormError) as caught:
                host.validate_envelope(json.dumps(envelope).encode(),'a'*32,{},
                                       validator=lambda raw,**kwargs:json.loads(raw))
            self.assertEqual(caught.exception.native_failure['failure_phase'],phase)
            self.assertEqual(caught.exception.native_failure['redump_projection'],['products_module'])
            self.assertFalse(caught.exception.native_failure['completed'])
        report['failure_phase']='private/arbitrary/path'
        with self.assertRaises(host.FormError) as caught:
            host.validate_envelope(json.dumps(envelope).encode(),'a'*32,{},
                                   validator=lambda raw,**kwargs:json.loads(raw))
        self.assertFalse(hasattr(caught.exception,'native_failure'))


class EnumFormsFailureProgressTests(unittest.TestCase):
    def test_progress_is_finite_incomplete_diagnostic_not_acceptance(self):
        import json
        from scripts.inventory_enum_forms_packet import route
        nonce = 'a' * 32
        events = [dict(flow=1, instance=1, code='create')]
        raw = json.dumps(dict(nonce=nonce, events=events)).encode()
        self.assertEqual(route.lifecycle_progress(raw, nonce), events)
        with self.assertRaises(ValueError):
            route.lifecycle(raw, nonce)

    def test_progress_rejects_sensitive_extra_or_unbounded_values(self):
        import json
        from scripts.inventory_enum_forms_packet import route
        nonce = 'a' * 32
        valid = dict(flow=1, instance=1, code='create')
        for events in ([dict(valid, path='/private')], [dict(valid, code='/private')],
                       [dict(valid, flow=True)], [dict(valid, instance=2)], [valid]*31):
            with self.subTest(events=events), self.assertRaises(ValueError):
                route.lifecycle_progress(json.dumps(dict(nonce=nonce, events=events)).encode(), nonce)
        with self.assertRaises(ValueError):
            route.lifecycle_progress(json.dumps(dict(nonce='b'*32, events=[])).encode(), nonce)

    def test_dynamic_attributes_use_form_receiver(self):
        import re
        from scripts.inventory_enum_forms_packet import route
        packet = route.packet()
        lifecycle = packet['lifecycle.bsl'].decode().split('&AtClientAtServerNoContext', 1)[0]
        observer = packet['Products/observer.bsl'].decode()
        for source in (lifecycle, observer):
            code = re.sub(r'"[^"\n]*"', '', source)
            for name in ('ProbeFlow', 'ProbeInstance', 'ProbeWaits', 'ExplicitChangeCount', 'ProbeTracePath', 'ProbeNonce'):
                self.assertIsNone(re.search(r'(?<![\w.])' + name + r'\b', code), name)
        self.assertIn('ThisObject.ProbeFlow = Parameters.Flow', lifecycle)
        self.assertIn('ThisObject.ExplicitChangeCount = ThisObject.ExplicitChangeCount + 1', observer)


    def test_failure_envelope_exports_only_valid_progress(self):
        import json, sys
        sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import native_1c_owned_enum_forms_profile as host
        import owned_enum_forms_suite as stage
        nonce='a'*32
        report=stage.empty_report(nonce)
        progress=[dict(flow=1,instance=1,code='create')]
        report.update(status='failed',failure_kind='timeout',failure_phase='enterprise',lifecycle_progress=progress,
                      native_diagnostic=dict(category='compile_error',module='ProductsCard',line=12,identifier='ProbeFlow'),
                      launcher_progress=dict(phase='before_open',flow=1))
        envelope=dict(schema=host.SCHEMA,profile=host.PROFILE,nonce=nonce,
                      report=dict(status='stage3_failed',native_tests_completed=False,stage3=report),outputs=[])
        validator=lambda raw,**kwargs:json.loads(raw)
        with self.assertRaises(host.FormError) as caught:
            host.validate_envelope(json.dumps(envelope).encode(),nonce,{},validator)
        self.assertEqual(caught.exception.native_failure['lifecycle_progress'],progress)
        self.assertEqual(caught.exception.native_failure['native_diagnostic']['module'],'ProductsCard')
        self.assertEqual(caught.exception.native_failure['launcher_progress'],dict(phase='before_open',flow=1))
        progress[0]['code']='/private/path'
        with self.assertRaises(host.FormError) as caught:
            host.validate_envelope(json.dumps(envelope).encode(),nonce,{},validator)
        self.assertFalse(hasattr(caught.exception,'native_failure'))


class EnumFormsNativeDiagnosticTests(unittest.TestCase):
    def test_only_finite_owned_location_and_identifier_exported(self):
        import sys
        sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import diagnostics
        from scripts.inventory_enum_forms_packet import failure_diagnostics as diagnostic
        value=diagnostic.summarize('{Справочник.Products.Форма.Card.Форма(12, 4)}: Переменная не определена (ProbeFlow)', diagnostics)
        self.assertEqual(value['module'],'ProductsCard')
        self.assertEqual(value['line'],12)
        diagnostic.validate(value,set())
        private=diagnostic.summarize('{Private.Module(12, 4)}: Переменная не определена (secret_value)', diagnostics)
        self.assertIsNone(private['module'])
        self.assertIsNone(private['identifier'])
        for change in (dict(module='/private'),dict(identifier='secret'),dict(line=True),dict(line=126)):
            with self.subTest(change=change),self.assertRaises(ValueError):
                diagnostic.validate({**value,**change},set())

    def test_check_uses_bounded_designer_and_closed_phase(self):
        import sys
        sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import owned_enum_forms_suite as stage
        import native_1c_owned_enum_forms_profile as host
        self.assertIn('check_config',stage.PHASES)
        self.assertEqual(stage.PHASES,host.PHASES)
        source=(ROOT.parent/'native_1c_bootstrap/owned_enum_forms_suite.py').read_text()
        self.assertIn("designer('check',['/CheckConfig','-ThickClientManagedApplication','-Server'])",source)
        self.assertLess(source.index("designer('check'"),source.index("phase='enterprise'"))

    def test_launcher_progress_is_source_bound_finite_and_not_acceptance(self):
        import json
        from scripts.inventory_enum_forms_packet import route
        value=dict(schema='native-owned-enum-forms-progress-v1',nonce='a'*32,
                   phase='before_open',flow=1,source_sha256=route.SOURCE_SHA256,form_sha256=route.FORM_SHA256)
        self.assertEqual(route.launcher_progress(json.dumps(value).encode(),'a'*32),dict(phase='before_open',flow=1))
        for change in (dict(nonce='b'*32),dict(phase='/private'),dict(flow=True),dict(flow=9),dict(source_sha256='0'*64),dict(extra='secret')):
            with self.subTest(change=change),self.assertRaises(ValueError):
                route.launcher_progress(json.dumps({**value,**change}).encode(),'a'*32)
        self.assertFalse(route.valid_launcher_progress(dict(phase='before_open',flow=1,path='secret')))

    def test_console_only_and_empty_out_are_finite(self):
        import sys,tempfile
        sys.path.insert(0,str(ROOT.parent/'native_1c_bootstrap'))
        import diagnostics,full_suite
        from scripts.inventory_enum_forms_packet import failure_diagnostics as diagnostic
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            root=Path(temp).resolve()
            (root/'enterprise.log').write_bytes(b'')
            (root/'enterprise-console.log').write_text('{Справочник.Products.Форма.Card.Форма(12, 4)}: Переменная не определена (ProbeFlow)', encoding='utf-8')
            value=diagnostic.collect(root,full_suite,diagnostics)
            self.assertEqual(value['module'],'ProductsCard')
            diagnostic.validate(value,set())
            (root/'enterprise-console.log').write_bytes(b'x'*(diagnostic.MAX_LOG+1))
            self.assertEqual(diagnostic.collect(root,full_suite,diagnostics)['category'],'evidence_invalid')

    def test_open_error_is_closed_and_never_completion(self):
        import json
        from scripts.inventory_enum_forms_packet import route
        for phase in ('open_error_unknown','open_error_access','open_error_variable','open_error_field','open_error_method'):
            value=dict(schema='native-owned-enum-forms-progress-v1',nonce='a'*32,
                       phase=phase,flow=1,source_sha256=route.SOURCE_SHA256,form_sha256=route.FORM_SHA256)
            self.assertEqual(route.launcher_progress(json.dumps(value).encode(),'a'*32),dict(phase=phase,flow=1))
        source=route.module().decode()
        self.assertIn('Try\n  OpenForm',source)
        self.assertIn('Left(ErrorDescription(), 4096)',source)
        self.assertNotIn('SaveJSON(Request.progress, Description)',source)
        self.assertIn('Progress(Phase);\n  ЗавершитьРаботуСистемы(Ложь);\n  Return False;',source)
        self.assertIn('EndTry;\n Progress("after_open");\n Return True;',source)
        self.assertEqual(source.count('If Not OpenOwned('),3)
