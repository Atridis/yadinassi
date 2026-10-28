"""Synthetic name binding, resource graph, privacy and closed lifecycle tests."""
import copy
import dataclasses
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import config_catalog_identity_binding as policy
import config_catalog_name as parser
import config_framing_reader as core
import inputs
import protocol
import snapshots
import test_config_catalog_standard as standard_names
import test_native_1c_db_oracle_catalog_reference_policy as old
import test_native_1c_db_oracle_catalog_reference_reader as reader_fixture
import test_native_1c_db_oracle_catalog_reference_budget as old_budget
from test_native_1c_db_oracle_catalog_reference_reader import A,B,GUID,stored_literal,successful_source,content_source,entries
NONCE=old.NONCE
EXPECTED_ENVELOPE = {'sources':26,'projection':2020,'capture':3096,'report':31852,'report_cap':32768}


class names:
    @staticmethod
    def document(name='"Invented"', code='2', kind='1', description='0', skipped='0', *, metadata_uuid=A):
        node = standard_names.node
        fields = ['0'] * 20
        fields[9] = node('0', node('0', node('1', '0', metadata_uuid), name))
        fields[17:20] = [code, kind, description]
        return node(skipped, node(*fields)).encode()

    @staticmethod
    def prefix(*args, **kwargs):
        return names.document(*args, **kwargs)[:-2] + b','


def identity():
    result=old.identity();result['sources']={path:'c'*64 for path in policy.CATALOG_SOURCE_FILES};return result


def manifest():
    return policy._IdentityManifest(NONCE,'a'*64,'b'*64,A,'NativeOracleItems',2,1,0)


def source(**kwargs):
    return successful_source(payload=stored_literal(names.document(name='"NativeOracleItems"')),**kwargs)


def private():
    image=source()
    return policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())


def projection():return policy.compare_private(private(),manifest(),nonce=NONCE)


def evidence():
    value=old.previous.evidence();value.update(reader=private(),identity_manifest=manifest());return value


def fixture():
    value=old.fixture();del value['config_catalog_observation']
    value.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=identity(),
        config_catalog_identity_binding=None,reader_validation=policy.VERDICT,observation_validation=policy.VERDICT)
    value['config_catalog_identity_binding']=policy.bind_capture(evidence(),value)
    return value


def envelope():
    projected=old_budget.projection_envelope()
    projected.update(recipe_id=policy.RECIPE_ID,recipe_sha256=policy.RECIPE_SHA256,
        catalog_name_count=1,catalog_name_validation='owned_declared_key_name_matched',
        catalog_identity_validation='owned_uuid_code_description_matched')
    capture=copy.deepcopy(fixture()['config_catalog_identity_binding']);capture['reader']=None
    capture['origin']['bytes']=capture['postimage']['bytes']=snapshots.MAX_FILE_BYTES
    report=old_budget.report_envelope();del report['config_catalog_observation']
    report.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=identity(),config_catalog_identity_binding=None)
    for key in ('reader_validation','observation_validation'):
        report[key]=old_budget.previous.old.longest(('not_run','failed','discarded',policy.VERDICT))
    wire=protocol.encode
    return {'sources':len(policy.CATALOG_SOURCE_FILES),'projection':len(wire(projected)),
        'capture':len(wire(capture))-4+policy.MAX_PROJECTION_BYTES,
        'report':len(wire(report))-4+policy.MAX_CAPTURE_BYTES+1,
        'report_cap':protocol.MAX_REPORT_BYTES}


class CatalogIdentityBindingTests(unittest.TestCase):
    def test_complete_synthetic_report_and_private_values_absent(self):
        report=fixture();policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity())
        report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
        policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity(),final=True)
        raw=protocol.encode(report)
        for value in (A,GUID,'NativeOracleItems'):
            self.assertNotIn(value.encode(),raw)
        self.assertEqual(report['native_compatibility'],'not_claimed')
        self.assertEqual(report['config_catalog_identity_binding']['reader']['file_identity'],'not_observed')

    def test_independent_uuid_name_and_manifest_mismatches(self):
        for changed,code in ((dataclasses.replace(manifest(),key=B),'config_catalog_key_mismatch'),
                             (dataclasses.replace(manifest(),name='Different'),'config_catalog_name_mismatch'),
                             (dataclasses.replace(manifest(),nonce='f'*32),'config_catalog_manifest')):
            with self.assertRaises(policy.ObservationFailure) as error:
                policy.compare_private(private(),changed,nonce=NONCE)
            self.assertEqual(error.exception.code,code)
            self.assertNotIn(changed.name,str(error.exception))

    def test_internal_uuid_is_independent_and_must_equal_external_and_xml(self):
        # Parser receives actual bytes only; external declaration and XML stay A.
        for internal in (B, GUID):
            image = successful_source(payload=stored_literal(names.document(
                name='"NativeOracleItems"', metadata_uuid=internal)))
            actual = policy.read_owned_projection(image.read_at, image.size,
                limits=policy.reader.CatalogLimits())
            self.assertEqual(actual.names[0][1].metadata_uuid, internal)
            with self.assertRaises(policy.ObservationFailure) as error:
                policy.compare_private(actual, manifest(), nonce=NONCE)
            self.assertEqual(error.exception.code, 'config_catalog_uuid_mismatch')
            self.assertNotIn(internal, str(error.exception))
        original = private()
        for invalid in (None, True, 'private-invalid'):
            fields = dataclasses.replace(original.names[0][1], metadata_uuid=invalid)
            with self.assertRaises(policy.ObservationFailure):
                policy.compare_private(dataclasses.replace(original, names=((A, fields),)),
                                       manifest(), nonce=NONCE)
        # Case is normalized only by the parser, not relaxed by the comparator.
        lower = 'abcdefab-cdef-4abc-8def-abcdefabcdef'
        rows = entries(refs=(lower,), payload=stored_literal(names.document(
            name='"NativeOracleItems"', metadata_uuid=lower.upper())))
        rows[0] = (lower.upper(), rows[0][1], 0)
        image = content_source(rows)
        actual = policy.read_owned_projection(image.read_at, image.size,
            limits=policy.reader.CatalogLimits())
        self.assertEqual(actual.names[0][1].metadata_uuid, lower)
        self.assertEqual(policy.compare_private(actual, dataclasses.replace(manifest(), key=lower), nonce=NONCE)
                         ['catalog_identity_validation'], 'owned_uuid_code_description_matched')

    def test_old_standard_lane_does_not_acquire_uuid_validation(self):
        import config_catalog_standard_binding as prior
        import test_native_1c_db_oracle_catalog_standard_binding as prior_fixture
        image = successful_source(payload=stored_literal(names.document(
            name='"NativeOracleItems"', metadata_uuid='invalid-private-uuid')))
        old_result = prior.read_owned_projection(image.read_at, image.size,
            limits=prior.reader.CatalogLimits())
        self.assertEqual(prior.compare_private(old_result, prior_fixture.manifest(), nonce=NONCE)
                         ['catalog_standard_validation'], 'owned_code_description_matched')
        with self.assertRaises(policy.reader.InvalidStructure):
            policy.read_owned_projection(image.read_at, image.size, limits=policy.reader.CatalogLimits())
        self.assertEqual(prior.RECIPE_SHA256,
            '984cd24e251525d9d4a11dcad373344ce95bd6af0d6b33d77f472e2d8922f0e4')

    def test_uuid_and_scalar_failure_poison_private_decoder(self):
        for options in ({'metadata_uuid': 'not-a-guid'}, {'metadata_uuid': '00000000-0000-0000-0000-000000000000'},
                        {'kind': '2'}, {'code': '2147483648'}):
            decoders = []
            init = core._ConfigContentDecoder.__init__
            def remember(obj, *args, **kwargs):
                init(obj, *args, **kwargs); decoders.append(obj)
            image = successful_source(payload=stored_literal(names.document(**options)))
            with mock.patch.object(core._ConfigContentDecoder, '__init__', remember):
                with self.assertRaises(policy.reader.InvalidStructure) as error:
                    policy.read_owned_projection(image.read_at, image.size,
                        limits=policy.reader.CatalogLimits())
            self.assertEqual(error.exception.code, 'config_catalog_identity_prefix')
            self.assertTrue(decoders[0].failed)
            self.assertGreaterEqual(decoders[0].budget.counts['output_bytes'],
                                    parser.IDENTITY_OUTPUT_RESERVATION + 262144)

    def test_independent_each_standard_field_mismatch_and_exact_private_types(self):
        for field, different in (('code_length',3), ('code_type',0), ('description_length',1)):
            with self.subTest(field=field):
                changed = dataclasses.replace(manifest(), **{field:different})
                with self.assertRaises(policy.ObservationFailure) as error:
                    policy.compare_private(private(), changed, nonce=NONCE)
                self.assertEqual(error.exception.code, 'config_catalog_standard_mismatch')
                self.assertNotEqual(policy.manifest_digest(changed),policy.manifest_digest(manifest()))
                original = private()
                fields = dataclasses.replace(original.names[0][1], **{field:True})
                with self.assertRaises(policy.ObservationFailure):
                    policy.compare_private(dataclasses.replace(original,names=((A,fields),)),manifest(),nonce=NONCE)
        for field in ('code_length','code_type','description_length'):
            for value in (True,-1,'2',None,2147483648):
                with self.subTest(field=field,value=value), self.assertRaises(policy.ObservationFailure):
                    policy.validate_manifest(dataclasses.replace(manifest(),**{field:value}),nonce=NONCE)

    def test_manifest_validation_rejects_bad_values(self):
        for key,bad in (('key','bad'),('key','0'*36),('name',''),('name','x'*257),
                        ('name','\ud800'),('name','a\n'),('catalog_sha256','bad'),('nonce',True)):
            with self.subTest(key=key),self.assertRaises(policy.ObservationFailure):
                policy.validate_manifest(dataclasses.replace(manifest(),**{key:bad}),nonce=NONCE)

    def test_private_reader_cannot_skip_binding(self):
        for value in (projection(),None,policy._PrivateProjection({},()),
                      policy._PrivateProjection({},((A,'NativeOracleItems',2,1,0),(B,'Other')))):
            with self.assertRaises(policy.OracleError):policy.compare_private(value,manifest(),nonce=NONCE)
        data=evidence();data.pop('identity_manifest')
        with self.assertRaises(policy.OracleError):policy.bind_capture(data,fixture())

    def test_one_resource_graph_name_parser_uses_same_budget(self):
        budgets=[];readers=[];calls=[];decoders=[]
        init=core.CatalogReader.__init__;decode=core._ConfigContentDecoder.__init__
        project=parser.project_catalog_identity_prefix;chain=core._ConfigBlobChains.read
        def ri(obj,*a,**kw):init(obj,*a,**kw);readers.append(obj)
        def di(obj,*a,**kw):decode(obj,*a,**kw);decoders.append(obj)
        def project_name(data,**kw):
            self.assertEqual(set(kw),{'budget','limits'});budgets.append(kw['budget']);return project(data,**kw)
        def cr(obj,start,length):calls.append((id(obj),start));return chain(obj,start,length)
        with mock.patch.object(core.CatalogReader,'__init__',ri),mock.patch.object(core._ConfigContentDecoder,'__init__',di),mock.patch.object(parser,'project_catalog_identity_prefix',project_name),mock.patch.object(core._ConfigBlobChains,'read',cr):
            result=private()
        self.assertEqual(result.names,((A,parser.CatalogIdentityPrefix(A,'NativeOracleItems',2,1,0)),))
        self.assertEqual(len(readers),1);self.assertEqual(len(decoders),1)
        self.assertIs(budgets[0],readers[0]._budget);self.assertIs(budgets[0],decoders[0].budget)
        self.assertEqual([start for _,start in calls],[2,3,1])
        self.assertEqual(len({ident for ident,_ in calls}),1)

    def test_selected_entry_order_and_partial_suffix(self):
        rows=entries(payload=stored_literal(names.prefix(name='"NativeOracleItems"')+b'\xff'))
        for order in (rows,rows[::-1],rows[1:]+rows[:1]):
            image=content_source(order)
            result=policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())
            self.assertEqual(policy.compare_private(result,manifest(),nonce=NONCE)['catalog_name_count'],1)

    def test_aliases_missing_duplicate_and_invalid_name_fail_closed(self):
        cases=((source(refs=(GUID,)),'config_catalog_self_reference'),
               (source(refs=(B,)),'config_catalog_reference_missing'),
               (source(refs=(A,A)),'config_catalog_prefix'),
               (successful_source(payload=stored_literal(b'PRIVATE invalid')),'config_catalog_identity_prefix'))
        for image,code in cases:
            with self.subTest(code=code),self.assertRaises(core.CatalogError if hasattr(core,'CatalogError') else policy.reader.CatalogError) as error:
                policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())
            self.assertEqual(error.exception.code,code)

    def test_late_failure_poison_after_name_and_no_refund(self):
        decoders=[];init=core._ConfigContentDecoder.__init__;parsed=[];project=parser.project_catalog_identity_prefix
        def di(obj,*a,**kw):init(obj,*a,**kw);decoders.append(obj)
        def cp(data,**kw):parsed.append(True);return project(data,**kw)
        image=source(tail=(('late',b'bad-deflate',0),))
        with mock.patch.object(core._ConfigContentDecoder,'__init__',di),mock.patch.object(parser,'project_catalog_identity_prefix',cp):
            with self.assertRaises(policy.reader.CatalogError):
                policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(parsed,[True]);self.assertTrue(decoders[0].failed)
        self.assertGreaterEqual(decoders[0].budget.counts['output_bytes'],parser.IDENTITY_OUTPUT_RESERVATION+262144)

    def test_multiple_generic_names_not_owned_one_catalog(self):
        image=source(refs=(A,B),tail=((B,stored_literal(names.document(name='"Other"')),0),))
        with self.assertRaises(policy.ObservationFailure) as error:
            policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(error.exception.code,'config_catalog_owned_count')

    def test_complete_real_envelopes_without_raising_caps(self):
        result=envelope()
        self.assertLessEqual(result['projection'],policy.MAX_PROJECTION_BYTES)
        self.assertLessEqual(result['capture'],policy.MAX_CAPTURE_BYTES)
        self.assertLessEqual(result['report'],protocol.MAX_REPORT_BYTES)
        self.assertEqual(result,EXPECTED_ENVELOPE)
        value=fixture();self.assertEqual((len(value['stages']),len(value['snapshots']),len(value['comparisons']),len(value['cleanup'])),(13,11,5,4))

    def test_envelope_fields_and_diagnostic_majorants_cover_real_values(self):
        value=projection();bound=old_budget.projection_envelope()
        bound.update(recipe_id=policy.RECIPE_ID,recipe_sha256=policy.RECIPE_SHA256,
            catalog_name_count=1,catalog_name_validation='owned_declared_key_name_matched',
        catalog_identity_validation='owned_uuid_code_description_matched')
        self.assertEqual(set(value),set(bound))
        for key,item in value.items():
            if type(item) is int:self.assertLessEqual(len(str(item)),len(str(bound[key])))
            else:self.assertEqual(item,bound[key])
        for category,codes in policy.DIAGNOSTICS.items():
            self.assertTrue(category.isascii());self.assertLessEqual(len(category),128)
            for code in codes:
                self.assertTrue(code.isascii());self.assertLessEqual(len(code),128)
                self.assertLessEqual(len(protocol.encode({'schema':policy.CAPTURE_SCHEMA,
                    'status':'failed','category':category,'code':code})),policy.MAX_CAPTURE_BYTES)

    def test_every_failure_code_and_context_domain_fits_complete_envelope(self):
        wire=protocol.encode
        failures=[{'schema':policy.CAPTURE_SCHEMA,'status':'failed','category':category,'code':code}
            for category,codes in policy.DIAGNOSTICS.items() for code in codes]
        upper=len(wire({'schema':policy.CAPTURE_SCHEMA,'status':'failed',
            'category':max(policy.DIAGNOSTICS,key=len),
            'code':max((code for codes in policy.DIAGNOSTICS.values() for code in codes),key=len)}))
        self.assertEqual(upper,118)
        self.assertTrue({'config_catalog_identity_prefix','config_catalog_standard_mismatch'}
                        <= policy.DIAGNOSTICS['structural_rejection'])
        self.assertIn('config_catalog_identity_limits',policy.DIAGNOSTICS['resource_limit'])
        for failure in failures:
            self.assertLessEqual(len(wire(failure)),upper)
            # Same complete structural report envelope, substituting each actual
            # failure capture for the full12288-byte enclosing-cap allowance.
            self.assertLessEqual(envelope()['report']-policy.MAX_CAPTURE_BYTES+len(wire(failure)),
                                 protocol.MAX_REPORT_BYTES)
        domains=set(protocol.STAGES)|set(protocol.FAILURES)|set(protocol.COMMAND_STAGES)|set(policy.metadata.PHASES)|{policy.FAILURE_KIND,'enterprise_'+policy.OPERATION}
        for domain in (protocol.CONTEXT_SITES,protocol.BSL_PHASES,protocol.INVENTORY_REGIONS,
                       protocol.INVENTORY_REASONS,snapshots.ENTRY_CLASSES,snapshots.ENTRY_SHAPES):
            domains.update(domain)
        self.assertTrue(all(type(v) is str and v.isascii() and len(v)<=128 for v in domains))
        # Every new parser diagnostic is mapped to the fixed public vocabulary;
        # no raw numeric spelling or private parser exception is serialized.
        for code in parser.CatalogIdentityError.codes:
            image=source()
            with mock.patch.object(parser,'project_catalog_identity_prefix',
                    side_effect=parser.CatalogIdentityError(code)):
                with self.assertRaises(policy.reader.CatalogError) as error:
                    policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())
            public=policy.reader_failure(error.exception)
            self.assertIn(public.code,policy.DIAGNOSTICS[public.category])
            self.assertIn(public.code,('config_catalog_identity_limits','config_catalog_identity_prefix'))

    def test_recipe_literals_profile_and_old_lane_stay_independent(self):
        profile=core.ConfigCatalogIdentityProfile(policy.DECLARATIONS,'0',0)
        self.assertEqual(profile.recipe(),policy.RECIPE_DESCRIPTION)
        self.assertEqual(profile.recipe_sha256,policy.RECIPE_SHA256)
        self.assertEqual(policy.RECIPE_SHA256,'815804b8bc0fa5f743554dc2250c3be6eda4027e7df8a2003f47c32a94c9662d')
        self.assertEqual((policy.SCHEMA,policy.CAPTURE_SCHEMA,policy.LANE),
            (31,32,'owned_config_catalog_identity_binding_v1'))
        self.assertEqual(old.policy.RECIPE_SHA256,'af9381415545bae5adb0f8b06f81571806334212d98e944ab6987803360ca156')
        self.assertEqual((old.policy.SCHEMA,old.policy.CAPTURE_SCHEMA),(25,26))
        for key in ('catalog_name_projection','catalog_name_limits','catalog_name_reservation',
                    'catalog_name_binding','catalog_name_suffix','catalog_embedded_uuid'):
            self.assertNotIn(key,old.policy.RECIPE_DESCRIPTION)

    def test_source_inventory_is_new_and_previous_unmodified(self):
        self.assertEqual(inputs.inventory(config_catalog_identity_binding=True),policy.CATALOG_SOURCE_FILES)
        self.assertEqual(len(inputs.inventory(config_catalog_observation=True)),25)
        self.assertNotIn('yadinassi/storage/config_catalog_name.py',inputs.inventory(config_catalog_observation=True))
        for value in (1,None,'yes'):
            with self.assertRaises(policy.OracleError):inputs.inventory(config_catalog_identity_binding=value)
        with self.assertRaises(policy.OracleError):inputs.inventory(config_catalog_identity_binding=True,config_catalog_observation=True)

    def test_closed_projection_fields_and_report_binding(self):
        value=projection()
        for key in value:
            changed=dict(value);changed.pop(key)
            with self.assertRaises(policy.OracleError):policy.validate_projection(changed)
        for key,bad in (('catalog_name_count',True),('catalog_name_count',2),
                        ('catalog_name_validation','embedded_uuid_matched'),('private_names',((A,'NativeOracleItems',2,1,0),))):
            changed=dict(value);changed[key]=bad
            with self.assertRaises(policy.OracleError):policy.validate_projection(changed)
        for key,bad in (('identity_manifest_sha256','bad'),('nonce','f'*32),('source_manifest_sha256','f'*64)):
            report=fixture();report['config_catalog_identity_binding'][key]=bad
            with self.assertRaises(policy.OracleError):policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity())




class CatalogIdentityManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.expected=self.root/'expected';self.actual=self.root/'actual'
        import inject_metadata
        self.inject=inject_metadata
        self.xml=(f'<MetaDataObject xmlns="{inject_metadata.NS}" version="{inject_metadata.FORMAT}">'
            f'<Catalog uuid="{A}"><Properties><Name>NativeOracleItems</Name><CodeLength>2</CodeLength><CodeType>String</CodeType><DescriptionLength>0</DescriptionLength></Properties></Catalog></MetaDataObject>')
        for directory in (self.expected,self.actual):
            (directory/'Catalogs').mkdir(parents=True)
            (directory/'Catalogs/NativeOracleItems.xml').write_text(self.xml,encoding='utf-8')

    def build(self):return policy.build_identity_manifest(self.expected,self.actual,nonce=NONCE,version=1)

    def test_fixture_resolves_temp_parent_but_manifest_rejects_alias(self):
        # Model a system temporary directory reached through a symlink, as on
        # macOS. Resolve only the test-owned root; do not weaken reader policy.
        real=self.root/'real';real.mkdir()
        alias=self.root/'alias'
        try:
            alias.symlink_to(real,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest('directory symlink creation unavailable')
        temporary=mock.Mock();temporary.name=str(alias/'fixture')
        case=CatalogIdentityManifestTests('test_exact_independent_redump_manifest_and_whole_xml_binding')
        self.addCleanup(case.doCleanups)
        with mock.patch.object(tempfile,'TemporaryDirectory',return_value=temporary):
            case.setUp()
        self.assertEqual(case.root,real/'fixture')
        value=case.build()
        self.assertEqual((value.key,value.name,value.code_length,value.code_type,value.description_length),(A,'NativeOracleItems',2,1,0))
        for expected,actual in ((alias/'fixture/expected',case.actual),
                                (case.expected,alias/'fixture/actual')):
            with self.assertRaises(policy.ObservationFailure):
                policy.build_identity_manifest(expected,actual,nonce=NONCE,version=1)

    def test_exact_independent_redump_manifest_and_whole_xml_binding(self):
        value=self.build();self.assertEqual((value.key,value.name,value.code_length,value.code_type,value.description_length),(A,'NativeOracleItems',2,1,0))
        self.assertEqual(value.nonce,NONCE);self.assertTrue(protocol.digest(policy.manifest_digest(value)))
        self.assertNotEqual(value.expected_sources_sha256,value.catalog_sha256)
        for bad in (True,2,None):
            with self.assertRaises(policy.ObservationFailure):
                policy.build_identity_manifest(self.expected,self.actual,nonce=NONCE,version=bad)

    def test_wrong_key_name_namespace_and_duplicate_nodes_reject(self):
        path=self.actual/'Catalogs/NativeOracleItems.xml'
        for text in (self.xml.replace(A,B), self.xml.replace(f' uuid="{A}"', ''),
                     self.xml.replace(A, '00000000-0000-0000-0000-000000000000'),self.xml.replace('NativeOracleItems','Other'),
                     self.xml.replace(self.inject.NS,'urn:wrong'),
                     self.xml.replace('</Properties>','<Name>Other</Name></Properties>'),
                     self.xml.replace('</Catalog>','<Properties><Name>Other</Name></Properties></Catalog>')):
            path.write_text(text,encoding='utf-8')
            with self.assertRaises(policy.ObservationFailure):self.build()
        path.write_text(self.xml,encoding='utf-8')
        self.build()

    def test_each_xml_field_mismatch_and_malformed_expected_are_rejected(self):
        actual = self.actual/'Catalogs/NativeOracleItems.xml'
        expected = self.expected/'Catalogs/NativeOracleItems.xml'
        for tag, old_value, new_value in (('CodeLength','2','3'),
                ('CodeType','String','Number'), ('DescriptionLength','0','1')):
            changed=self.xml.replace(f'<{tag}>{old_value}</{tag}>',f'<{tag}>{new_value}</{tag}>')
            actual.write_text(changed,encoding='utf-8')
            with self.subTest(tag=tag), self.assertRaises(policy.ObservationFailure): self.build()
            actual.write_text(self.xml,encoding='utf-8')
        for tag, old_value in (('CodeLength','2'),('CodeType','String'),('DescriptionLength','0')):
            old=f'<{tag}>{old_value}</{tag}>'
            variants = ('', old+old, f'<{tag} extra="x">{old_value}</{tag}>',
                f'<{tag}><Nested/></{tag}>', f'<{tag} xmlns="urn:wrong">{old_value}</{tag}>',
                old+f'<{tag} xmlns="urn:wrong">{old_value}</{tag}>')
            invalid = ('2','', 'Unknown') if tag=='CodeType' else ('-1','01','2147483648',' 2','2 ','True')
            variants += tuple(f'<{tag}>{value}</{tag}>' for value in invalid)
            for replacement in variants:
                changed=self.xml.replace(old,replacement)
                # Canonically equal but malformed expected/actual must still fail.
                for path in (expected,actual): path.write_text(changed,encoding='utf-8')
                with self.subTest(tag=tag,replacement=replacement), self.assertRaises(policy.ObservationFailure): self.build()
            for path in (expected,actual): path.write_text(self.xml,encoding='utf-8')
        self.build()

    def test_changed_expected_source_after_read_is_rejected(self):
        original=self.inject._hashes;calls=[]
        def changed(path):
            value=original(path);calls.append(path)
            if len(calls)>1:value['extra']='f'*64
            return value
        with mock.patch.object(self.inject,'_hashes',side_effect=changed):
            with self.assertRaises(policy.ObservationFailure):self.build()

    def native_shell(self):
        import test_native_1c_db_oracle_stage as stages
        native=object.__new__(stages.stage.Native)
        native.root=self.root;native.counter=0;native.v1=self.expected;native.v2=self.root/'v2'
        native.nonce=NONCE;native.params_policy=policy;native.identity_manifest=None
        native.identity_baseline_verified=False;native.stage='seed_v1'
        native.batch=mock.Mock(side_effect=lambda *a,**kw:(self.root/'redump-001').mkdir())
        return native,stages.stage

    def test_manifest_only_after_verified_redump_and_rechecked_baseline(self):
        native,stage=self.native_shell();order=[];value=manifest()
        with mock.patch.object(stage,'verify_redump',side_effect=lambda *a,**kw:order.append('verified')),mock.patch.object(policy,'build_identity_manifest',side_effect=lambda *a,**kw:order.append('manifest') or value):
            native.redump(self.root/'seed',1,user=None)
            self.assertEqual(native.identity_manifest,value);self.assertFalse(native.identity_baseline_verified)
            native.stage='baseline';native.redump(self.root/'observer',1)
        self.assertEqual(order,['verified','manifest','verified','manifest'])
        self.assertEqual(native.batch.call_count,2);self.assertTrue(native.identity_baseline_verified)
        self.assertFalse((self.root/'redump-001').exists())
        for call in native.batch.call_args_list:self.assertEqual(call.args[1][0],'/DumpConfigToFiles')

    def test_failed_or_changed_redump_cannot_enable_reader(self):
        native,stage=self.native_shell()
        with mock.patch.object(stage,'verify_redump',side_effect=ValueError('private')),mock.patch.object(policy,'build_identity_manifest') as build:
            with self.assertRaises(policy.OracleError):native.redump(self.root/'seed',1)
        build.assert_not_called();self.assertIsNone(native.identity_manifest)
        native.stage='baseline';native.identity_manifest=manifest()
        with mock.patch.object(stage,'verify_redump'),mock.patch.object(policy,'build_identity_manifest',return_value=dataclasses.replace(manifest(),name='Different')):
            with self.assertRaises(policy.OracleError):native.redump(self.root/'observer',1)
        self.assertFalse(native.identity_baseline_verified)
        native.temporary_clone=mock.Mock()
        with self.assertRaises(policy.OracleError):native.observe_record_metadata('baseline')
        native.temporary_clone.assert_not_called()


if __name__=='__main__':unittest.main()
