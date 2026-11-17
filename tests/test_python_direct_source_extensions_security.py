"""Read-only extension calls retain actual owner and delayed-call checks."""
import unittest
from unittest.mock import patch
import test_python_direct_source_query as fixtures
from yadinassi import python_direct_source_extensions as bridge
from yadinassi.source_extensions import SourceExtensions
from yadinassi.experimental_naked_boundaries import BoundaryViolation


class DirectSourceExtensionSecurity(unittest.TestCase):
    app=fixtures.DirectSourceQueryTests.app
    boundary=fixtures.DirectSourceQueryTests.boundary

    def test_marker_cannot_use_stateless_sources_as_manager(self):
        from yadinassi.source_extensions import SourceExtensionSources,ExtensionCall
        from yadinassi.values import HostFunction
        app,caller=self.app();effects=[]
        namespace=SourceExtensionSources()
        namespace.read=lambda *args:effects.append('callback')
        with self.boundary(app,caller) as boundary:
            with self.assertRaises(BoundaryViolation):
                bridge.captured(boundary,HostFunction('Get',ExtensionCall(namespace,'get')))
        self.assertEqual(effects,[])

    def test_preflight_does_not_query_database_and_call_queries_once(self):
        app,caller=self.app(scratch=True)
        with self.boundary(app,caller) as boundary,patch.object(app.constant_store,'require_empty_extension_registry',wraps=app.constant_store.require_empty_extension_registry) as query:
            bound=bridge.resolve(boundary,app.extensions,'Get',argument_count=2)
            self.assertEqual(query.call_count,0)
            current,omissions=bound.prepare_omissions(bound,{0,1},2)
            self.assertIs(current,bound);self.assertEqual(omissions,{0:None,1:None})
            self.assertEqual(len(bound(None,None).items),0)
            self.assertEqual(query.call_count,1)

    def test_saved_marker_retarget_rejected_before_foreign_read(self):
        app,caller=self.app(scratch=True);other,_=self.app(scratch=True)
        with self.boundary(app,caller) as boundary:
            function=bridge.get(boundary,app.extensions,'Get');bound=bridge.captured(boundary,function)
            function.function.manager=other.extensions
            with patch.object(other.extensions,'read',side_effect=AssertionError('foreign read')):
                with self.assertRaises(BoundaryViolation):bound()

    def test_foreign_owner_and_class_hook_rejected_before_callbacks(self):
        app,caller=self.app(scratch=True);other,_=self.app(scratch=True)
        with self.boundary(app,caller) as boundary:
            with patch.object(other.extensions,'get_member',side_effect=AssertionError('foreign callback')):
                with self.assertRaises(BoundaryViolation):bridge.get(boundary,other.extensions,'Get')
            with patch.object(SourceExtensions,'read',side_effect=AssertionError('class callback')):
                with self.assertRaises(BoundaryViolation):bridge.resolve(boundary,app.extensions,'Get')

    def test_fake_scratch_store_rejected_without_callback(self):
        app,caller=self.app(scratch=True);effects=[]
        class Fake:
            def require_empty_extension_registry(self):effects.append('database')
        with self.boundary(app,caller) as boundary:
            bound=bridge.resolve(boundary,app.extensions,'Get')
            original=app.constant_store;app.constant_store=Fake()
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:app.constant_store=original
        self.assertEqual(effects,[])

    def test_saved_call_revoked_after_activation(self):
        app,caller=self.app(scratch=True)
        with self.boundary(app,caller) as boundary:
            bound=bridge.resolve(boundary,app.extensions,'GetSessionApplicationIssuesInformation',argument_count=0)
            with self.assertRaises(TypeError):bridge.resolve(boundary,app.extensions,'GetSessionApplicationIssuesInformation',argument_count=1)
        with self.assertRaises(BoundaryViolation):bound()


if __name__=='__main__':unittest.main()
