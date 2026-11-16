"""Owner-local source code reuse never caches event state or source authority."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch
import test_main_demo_host as hostfixture
import test_verified_form_draft_session as scalarfixture
import test_product_form_events as productfixture
from yadinassi import python_direct_form_events as direct
from yadinassi.catalog_backend import BackendError

class PreparedFormEventsTests(TestCase):
    def test_actual_kind_editor_reuses_across_fresh_source_drafts(self):
        f=hostfixture.MainDemoHostTests();f.setUp();self.addCleanup(f.doCleanups)
        kind=next(c for c in f.config.catalogs if c.name=='ВидыНоменклатуры')
        owner=f.host.owner;owner.select(str(kind.identity));owner.open()
        with patch.object(direct,'prepare',wraps=direct.prepare) as compile:
            owner.editor.change('InputData1','  First kind  ')
            owner.editor.change('InputData1','  Second kind  ')
            owner.event('command',control='SaveButton')
        self.assertEqual(compile.call_count,1)
        self.assertEqual(owner.editor.snapshot()['saveState'],'saved')
        self.assertEqual(owner.editor.object.get_member('Description'),'Second kind')
    def test_new_verified_sessions_reuse_code_but_recheck_current_source(self):
        f=scalarfixture.VerifiedFormDraftSessionTests();f.setUp();self.addCleanup(f.doCleanups)
        first=f.make();first.change_description(' First ',revision=0)
        plan=f.backend._direct_event_plan
        second=f.make()
        with patch.object(direct,'prepare',side_effect=AssertionError('recompile')):
            second.change_description(' Second ',revision=0)
        self.assertIs(f.backend._direct_event_plan,plan)
        self.assertEqual(dict(first.snapshot().values)['Description'],'First')
        before=second.snapshot()
        f.change_source(scalarfixture.PATHS['module_path'],scalarfixture.SOURCE+b'\n')
        with self.assertRaises(BackendError):second.change_description('bad',revision=1)
        self.assertIs(second.snapshot(),before)
    def test_closed_owner_cannot_use_warm_code(self):
        f=scalarfixture.VerifiedFormDraftSessionTests();f.setUp();self.addCleanup(f.doCleanups)
        session=f.make();session.change_description(' Good ',revision=0);before=session.snapshot()
        f.backend.close()
        with self.assertRaises(BackendError):session.prepare_save(revision=1)
        self.assertIs(session.snapshot(),before)
    def test_product_event_and_object_code_reused_with_fresh_cancellation(self):
        f=productfixture.ProductFormEventTests();f.setUp();self.addCleanup(f.doCleanups)
        import yadinassi.python_direct_catalog_preparation as object_direct
        with patch.object(direct,'prepare',wraps=direct.prepare) as event_compile,patch.object(object_direct,'prepare',wraps=object_direct.prepare) as object_compile:
            self.assertFalse(f.run_event('BeforeWriteAtServer').cancel)
            self.assertFalse(f.run_event('BeforeWriteAtServer').cancel)
            f.card.get_member('Склады').clear()
            refused=f.run_event('BeforeWriteAtServer')
            self.assertTrue(refused.cancel);self.assertTrue(refused.messages)
        self.assertEqual(event_compile.call_count,1);self.assertEqual(object_compile.call_count,1)
        self.assertTrue(f.card.is_new())
    def test_schema_and_profile_change_do_not_reuse_plan(self):
        f=productfixture.ProductFormEventTests();f.setUp();self.addCleanup(f.doCleanups)
        f.run_event('DescriptionOnChange');manager=f.card._manager;first=manager._direct_event_plan
        old=manager._schema
        try:
            manager._schema=replace(old,description_length=old.description_length+1)
            f.run_event('DescriptionOnChange')
            self.assertIsNot(manager._direct_event_plan,first)
        finally:manager._schema=old
        with patch.object(direct,'REPAIRS',direct.REPAIRS+('authority_checkpoints',)):
            f.run_event('DescriptionOnChange')
            self.assertIsNot(manager._direct_event_plan,first)

    def test_failure_after_private_setter_does_not_adopt_or_replay(self):
        f=scalarfixture.VerifiedFormDraftSessionTests();f.setUp();self.addCleanup(f.doCleanups)
        session=f.make();session.change_description(' Good ',revision=0);before=session.snapshot()
        original=direct.ScalarEventBoundary.resolve_set_member;effects=[]
        def bind(context,value,name):
            setter=original(context,value,name)
            def fail(new):
                setter(new);effects.append(new);raise ValueError('after private setter')
            return fail
        with patch.object(direct.ScalarEventBoundary,'resolve_set_member',bind):
            with self.assertRaises(Exception):session.change_description(' Changed ',revision=1)
        self.assertEqual(effects,['Changed']);self.assertIs(session.snapshot(),before)
        self.assertEqual(dict(session.change_description(' Later ',revision=1).values)['Description'],'Later')
