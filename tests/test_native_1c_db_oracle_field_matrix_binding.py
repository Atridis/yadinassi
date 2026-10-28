"""Synthetic fixed matrix proof only; never native compatibility evidence."""
import copy
import dataclasses
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import config_catalog_field_matrix as policy
import config_catalog_name as parser
import config_framing_reader as core
import protocol
import test_native_1c_db_oracle_catalog_identity_binding as previous
from test_native_1c_db_oracle_catalog_reference_reader import A,B,entries,stored_literal,content_source
C='44444444-4444-4444-8444-444444444444'
NONCE=previous.NONCE
KEYS=(A,B,C)
names=previous.names


def identity():
    value=previous.identity();value['sources']={p:'c'*64 for p in policy.CATALOG_SOURCE_FILES};return value


def manifest():
    return policy._MatrixManifest(NONCE,'a'*64,tuple(
        policy._IdentityManifest(NONCE,'a'*64,'b'*64,key,*fields)
        for key,fields in zip(KEYS,policy.MATRIX)))


def source():
    payloads=[stored_literal(names.document(name='"'+name+'"',code=str(code),kind=str(kind),
        description=str(description),metadata_uuid=key))
        for key,(name,code,kind,description) in zip(KEYS,policy.MATRIX)]
    return content_source(entries(refs=KEYS,payload=payloads[0],tail=tuple(
        (key,payload,0) for key,payload in zip(KEYS[1:],payloads[1:]))))


def private():
    image=source();return policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())


def projection():return policy.compare_private(private(),manifest(),nonce=NONCE)


def evidence():
    value=previous.old.previous.evidence();value.update(reader=private(),identity_manifest=manifest());return value


def fixture():
    value=previous.old.fixture();del value['config_catalog_observation']
    value.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=identity(),
        config_catalog_field_matrix=None,reader_validation=policy.VERDICT,observation_validation=policy.VERDICT)
    value['config_catalog_field_matrix']=policy.bind_capture(evidence(),value)
    return value


class MatrixBindingTests(unittest.TestCase):
    def test_complete_report_and_no_private_values(self):
        report=fixture()
        policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity())
        report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
        policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity(),final=True)
        raw=protocol.encode(report)
        for secret in (*KEYS,*(item[0] for item in policy.MATRIX)):
            self.assertNotIn(secret.encode(),raw)
        self.assertEqual(report['native_compatibility'],'not_claimed')

    def test_all_three_fields_and_uuid_are_compared_independently(self):
        actual=private()
        for index in range(3):
            for field,value in (('metadata_uuid','ffffffff-ffff-4fff-8fff-ffffffffffff'),
                                ('name','Changed'),('code_length',3),('code_type',9),('description_length',5)):
                changed=list(actual.names);key,fields=changed[index]
                changed[index]=(key,dataclasses.replace(fields,**{field:value}))
                with self.subTest(index=index,field=field), self.assertRaises(policy.ObservationFailure):
                    policy.compare_private(dataclasses.replace(actual,names=tuple(changed)),manifest(),nonce=NONCE)

    def test_exact_bijection_and_old_one_fixture_rejected(self):
        actual=private()
        for rows in (actual.names[:1],actual.names[:2],actual.names+actual.names[:1],
                     (actual.names[0],actual.names[1],actual.names[1])):
            with self.assertRaises(policy.ObservationFailure):
                policy.compare_private(dataclasses.replace(actual,names=rows),manifest(),nonce=NONCE)
        with self.assertRaises(policy.ObservationFailure):
            image=previous.source();policy.read_owned_projection(image.read_at,image.size,limits=policy.reader.CatalogLimits())
        for rows in (actual.names[::-1],actual.names[1:]+actual.names[:1]):
            self.assertEqual(policy.compare_private(dataclasses.replace(actual,names=rows),manifest(),nonce=NONCE),projection())

    def test_fixed_manifest_profiles_nonce_and_unique_uuid(self):
        value=manifest()
        for index in range(3):
            for field,replacement in (('name','Different'),('code_length',3),('code_type',True),
                                      ('description_length',0 if index else 16),('expected_sources_sha256','d'*64)):
                items=list(value.catalogs);items[index]=dataclasses.replace(items[index],**{field:replacement})
                with self.subTest(index=index,field=field), self.assertRaises(policy.ObservationFailure):
                    policy.validate_manifest(dataclasses.replace(value,catalogs=tuple(items)),nonce=NONCE)
        with self.assertRaises(policy.ObservationFailure):policy.validate_manifest(value,nonce='0'*32)

    def test_one_cumulative_reader_and_expectation_free_parser(self):
        budgets=[];calls=[];init=core.CatalogReader.__init__;project=parser.project_catalog_identity_prefix
        def create(obj,*args,**kwargs):init(obj,*args,**kwargs);budgets.append(obj._budget)
        def parse(data,**kwargs):calls.append(kwargs.copy());return project(data,**kwargs)
        with mock.patch.object(core.CatalogReader,'__init__',create),mock.patch.object(parser,'project_catalog_identity_prefix',parse):
            actual=private()
        self.assertEqual(len(budgets),1);self.assertEqual(len(calls),3)
        for kwargs in calls:
            self.assertEqual(set(kwargs),{'budget','limits'});self.assertIs(kwargs['budget'],budgets[0])
        self.assertEqual(actual.projection['completed_chain_count'],5)

    def test_old_lane_and_reader_recipe_stay_separate(self):
        self.assertEqual(policy.READER_RECIPE_SHA256,previous.policy.RECIPE_SHA256)
        self.assertNotEqual(policy.RECIPE_SHA256,previous.policy.RECIPE_SHA256)
        with self.assertRaises(protocol.OracleError):
            previous.policy.validate_projection(projection())
        with self.assertRaises(protocol.OracleError):
            policy.validate_report(protocol.encode(previous.fixture()),nonce=NONCE,provenance=previous.identity())

    def test_mismatched_reader_recipe_cannot_be_relabelled(self):
        observe=core.observe_config_catalog_identity
        for changes in ({'recipe_id':'wrong'}, {'recipe_sha256':'0'*64}):
            def altered(*args,**kwargs):return dataclasses.replace(observe(*args,**kwargs),**changes)
            with mock.patch.object(core,'observe_config_catalog_identity',altered):
                with self.assertRaises(protocol.OracleError):private()


class MatrixXMLManifestTests(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile
        import inject_metadata
        self.metadata=inject_metadata
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();source=self.root/'native';source.mkdir()
        shutil.copyfile(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml',source/'Configuration.xml')
        (source/'ConfigDumpInfo.xml').write_text('synthetic bookkeeping',encoding='utf-8')
        self.expected=self.root/'expected';self.actual=self.root/'actual'
        inject_metadata.inject(source,self.expected,nonce=NONCE,
            evidence=Path('/tmp/onec-db-oracle/evidence'),catalog_field_matrix=True)
        shutil.copytree(self.expected,self.actual)

    def build(self):return policy.build_identity_manifest(self.expected,self.actual,nonce=NONCE,version=1)

    def test_three_canonical_private_xml_facts_bound(self):
        value=self.build()
        self.assertEqual(tuple((item.name,item.code_length,item.code_type,item.description_length)
            for item in value.catalogs),policy.MATRIX)
        self.assertEqual(len({item.key for item in value.catalogs}),3)
        self.assertEqual(len(policy.manifest_digest(value)),64)
        self.assertNotIn('catalogs',projection())

    def test_each_variant_mismatch_or_missing_rejects_entire_manifest(self):
        for name,*_ in policy.MATRIX:
            path=self.actual/f'Catalogs/{name}.xml';raw=path.read_bytes()
            for value in (None, raw.replace(b'<CodeLength>2</CodeLength>',b'<CodeLength>3</CodeLength>'),
                          raw.replace(b'<CodeType>String</CodeType>',b'<CodeType>Number</CodeType>')
                          if b'<CodeType>String</CodeType>' in raw else raw.replace(b'<CodeType>Number</CodeType>',b'<CodeType>String</CodeType>')):
                if value is None:path.unlink()
                else:path.write_bytes(value)
                with self.subTest(name=name),self.assertRaises(policy.ObservationFailure):self.build()
                path.write_bytes(raw)

    def test_injected_expected_is_not_an_unchecked_comparison_oracle(self):
        # Equal altered XML in both trees still fails the fixed reviewed profile.
        for tree in (self.expected,self.actual):
            path=tree/'Catalogs/NativeOracleNumberDescription.xml'
            path.write_bytes(path.read_bytes().replace(b'<DescriptionLength>16</DescriptionLength>',b'<DescriptionLength>17</DescriptionLength>'))
        with self.assertRaises(policy.ObservationFailure):self.build()

    def test_all_version_and_nonce_types_fail_closed(self):
        for version in (0,2,True,'1',None):
            with self.assertRaises(policy.ObservationFailure):
                policy.build_identity_manifest(self.expected,self.actual,nonce=NONCE,version=version)
        for nonce in (None,True,'X'*32,'0'*31):
            with self.assertRaises(policy.ObservationFailure):
                policy.build_identity_manifest(self.expected,self.actual,nonce=nonce,version=1)

    def test_actual_source_tree_mutation_during_read_rejects(self):
        read_xml=self.metadata.read_xml;count=0
        def changed(path):
            nonlocal count
            result=read_xml(path);count+=1
            if count==1:
                (self.actual/'ConfigDumpInfo.xml').write_text('changed bookkeeping',encoding='utf-8')
            return result
        with mock.patch.object(self.metadata,'read_xml',side_effect=changed):
            with self.assertRaises(policy.ObservationFailure):self.build()
