from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch
from hashlib import sha256
from yadinassi import form_event_simulation as sim
from yadinassi import form_module_analysis as analysis
import test_form_draft_session as draftfixture
import test_verified_form_draft_session as verifiedfixture

class ScalarSourceUnitTests(TestCase):
    def test_fresh_verified_sessions_do_not_reparse_or_reparse_xml(self):
        f=verifiedfixture.VerifiedFormDraftSessionTests();f.setUp();self.addCleanup(f.doCleanups)
        first=f.make();first.change_description(' First ',revision=0)
        with patch.object(analysis,'_parse',side_effect=AssertionError('parse')),patch.object(analysis,'_metadata',side_effect=AssertionError('XML')),patch.object(sim,'_parse',side_effect=AssertionError('second parse')):
            second=f.make();second.change_description(' Second ',revision=0);second.prepare_save(revision=1)
        self.assertEqual(dict(first.snapshot().values)['Description'],'First')
        self.assertEqual(dict(second.snapshot().values)['Description'],'Second')
    def test_binding_is_primitive_snapshot_not_same_object_alias(self):
        session=draftfixture.FormDraftSessionTests().make();unit=session._direct_scalar_source
        original=session._binding
        self.assertIsNot(unit.analysis.binding,original)
        before=unit.key
        object.__setattr__(original,'configuration_generation',original.configuration_generation+1)
        session.change_description(' Changed ',revision=0)
        self.assertIsNot(session._direct_scalar_source,unit)
        self.assertEqual(unit.key,before)
        self.assertNotEqual(unit.analysis.binding.configuration_generation,original.configuration_generation)
    def test_forged_uuid_payload_never_runs_equality_or_bool(self):
        session=draftfixture.FormDraftSessionTests().make()
        class Host:
            def __bool__(self):raise AssertionError('bool')
            def __eq__(self,other):raise AssertionError('eq')
            def __hash__(self):raise AssertionError('hash')
        object.__setattr__(session._binding.database_id,'int',Host())
        with self.assertRaises(analysis.FormModuleAnalysisError):session.prepare_save(revision=0)
    def test_source_and_xml_drift_rejected_after_warm_hit(self):
        for field,digest in (('_source','source_sha256'),('_catalog_xml','catalog_sha256'),('_form_xml','form_sha256'),('_definition_xml','definition_sha256')):
            with self.subTest(field=field):
                session=draftfixture.FormDraftSessionTests().make();before=session.snapshot()
                setattr(session,field,b'invalid source or XML')
                session._binding=replace(session._binding,**{digest:sha256(getattr(session,field)).hexdigest()})
                with self.assertRaises(analysis.FormModuleAnalysisError):session.change_description('Bad',revision=0)
                self.assertIs(session.snapshot(),before)
    def test_limits_and_profile_are_part_of_pure_unit_key(self):
        session=draftfixture.FormDraftSessionTests().make();first=session._direct_scalar_source
        with patch.object(analysis,'MAX_AST_NODES',1):
            with self.assertRaises(analysis.FormModuleAnalysisError):session.prepare_save(revision=0)
        self.assertIs(session._direct_scalar_source,first)
        with patch.object(analysis,'PROFILE','changed-test-profile'):
            session.prepare_save(revision=0)
            self.assertIsNot(session._direct_scalar_source,first)
    def test_public_analysis_does_not_return_program(self):
        session=draftfixture.FormDraftSessionTests().make()
        admitted=sim._admit(session._source,session._binding,session._catalog_xml,session._form_xml,session._definition_xml)
        self.assertIs(type(admitted),analysis.FormModuleAnalysis)
        self.assertFalse(hasattr(admitted,'program'))
