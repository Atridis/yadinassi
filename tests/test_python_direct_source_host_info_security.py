"""Source target identity and scratch-session authority cannot be retargeted."""
import unittest
from unittest.mock import patch
import test_python_direct_source_query as fixtures
from yadinassi import python_direct_source_host_info as bridge
from yadinassi.source_system_info import SourceSystemInfo
from yadinassi.source_host_session import SourceSessionCall
from yadinassi.values import HostFunction
from yadinassi.experimental_naked_boundaries import BoundaryViolation


class DirectHostInfoSecurity(unittest.TestCase):
    app=fixtures.DirectSourceQueryTests.app
    boundary=fixtures.DirectSourceQueryTests.boundary

    def test_system_info_no_native_target_is_not_fabricated(self):
        app,caller=self.app()
        with self.boundary(app,caller) as boundary:
            value=bridge.resolve_constructor(boundary,'SystemInfo',argument_count=0)()
            self.assertIsNone(bridge.get(boundary,value,'CompatibilityTarget'))
            with self.assertRaisesRegex(ValueError,'explicit'):bridge.get(boundary,value,'AppVersion')

    def test_constructor_registration_rechecked_after_bind(self):
        app,caller=self.app();effects=[]
        with self.boundary(app,caller) as boundary:
            bound=bridge.resolve_constructor(boundary,'SystemInfo')
            old=caller.types['systeminfo'];caller.types['systeminfo']=HostFunction('SystemInfo',lambda:effects.append('called'))
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:caller.types['systeminfo']=old
        self.assertEqual(effects,[])

    def test_other_constructor_alias_and_background_identity_rechecked(self):
        app,caller=self.app(scratch=True)
        with self.boundary(app,caller) as boundary:
            bound=bridge.resolve_constructor(boundary,'SystemInfo')
            original=caller.types['системнаяинформация'];caller.types['системнаяинформация']=HostFunction('bad',lambda:None)
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:caller.types['системнаяинформация']=original
            current=bridge.captured(boundary,caller.functions['getcurrentinfobasesession'])
            app.host_session._background_job=object()
            try:
                with self.assertRaises(BoundaryViolation):current()
            finally:app.host_session._background_job=None

    def test_constructor_class_and_initializer_replacement_before_callback(self):
        from yadinassi import source_system_info
        app,caller=self.app();effects=[]
        with self.boundary(app,caller) as boundary:
            bound=bridge.resolve_constructor(boundary,'SystemInfo')
            with patch.object(SourceSystemInfo,'__init__',lambda *args:effects.append('init')):
                with self.assertRaises(BoundaryViolation):bound()
            with patch.object(source_system_info,'SourceSystemInfo',lambda *args:effects.append('class')):
                with self.assertRaises(BoundaryViolation):bound()
        self.assertEqual(effects,[])

    def test_forged_and_retargeted_session_markers_denied(self):
        app,caller=self.app(scratch=True);other,_=self.app(scratch=True)
        with self.boundary(app,caller) as boundary:
            forged=HostFunction('Get',SourceSessionCall(SourceSystemInfo(app),True))
            with self.assertRaises(BoundaryViolation):bridge.captured(boundary,forged)
            function=HostFunction('Get',SourceSessionCall(app.host_session,True));bound=bridge.captured(boundary,function)
            function.function.session=other.host_session
            with patch.object(other.host_session,'authorize',side_effect=AssertionError('foreign callback')):
                with self.assertRaises(BoundaryViolation):bound()

    def test_zero_arity_lifetime_and_fake_store(self):
        app,caller=self.app(scratch=True)
        with self.boundary(app,caller) as boundary:
            function=caller.functions['getcurrentinfobasesession']
            with self.assertRaises(TypeError):bridge.captured(boundary,function,argument_count=1)
            bound=bridge.captured(boundary,function,argument_count=0);self.assertIs(bound(),app.host_session)
            store=app.constant_store;app.constant_store=object()
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:app.constant_store=store
        with self.assertRaises(BoundaryViolation):bound()


if __name__=='__main__':unittest.main()
