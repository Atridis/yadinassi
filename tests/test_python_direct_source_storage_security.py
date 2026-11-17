"""Admission and delayed capability revocation for finite source bridges."""
import unittest
import test_python_direct_source_query as fixtures
from yadinassi import python_direct_source_storage as storage
from yadinassi import python_direct_source_query as query
from yadinassi.values import HostFunction
from yadinassi.source_constants_runtime import SourceConstants, ConstantCall
from yadinassi.experimental_naked_boundaries import BoundaryViolation


class SourceBridgeSecurityTests(unittest.TestCase):
    app=fixtures.DirectSourceQueryTests.app
    boundary=fixtures.DirectSourceQueryTests.boundary

    def test_query_registry_replacement_after_binding_refused(self):
        app,owner=self.app()
        with self.boundary(app,owner) as boundary:
            bound=query.resolve_constructor(boundary,'Query',argument_count=1)
            effects=[]
            def argument():
                owner.types['query']=HostFunction('Query',lambda *args:effects.append('replacement'))
                return 'SELECT Text FROM Constants'
            with self.assertRaises(BoundaryViolation):bound(argument())
            self.assertEqual(effects,[])

    def test_captured_marker_owner_checked_before_authorize(self):
        app,owner=self.app(scratch=True);effects=[]
        class Foreign:
            def _store(self,caller):effects.append('foreign callback')
        marker=ConstantCall(Foreign(),'Text',False)
        with self.boundary(app,owner) as boundary:
            with self.assertRaises(BoundaryViolation):
                storage.captured(boundary,HostFunction('Get',marker.descriptor()))
        self.assertEqual(effects,[])

    def test_argument_cannot_retarget_admitted_constant_marker(self):
        app,owner=self.app(scratch=True);effects=[]
        marker=ConstantCall(SourceConstants(app),'Text',True)
        class Foreign:
            def _store(self,caller):effects.append('foreign callback')
        with self.boundary(app,owner) as boundary:
            bound=storage.captured(boundary,HostFunction('Set',marker.descriptor(),returns_value=False),argument_count=1)
            def argument():
                marker.owner=Foreign()
                return 'must not write'
            with self.assertRaisesRegex(BoundaryViolation,'operation changed'):bound(argument())
        self.assertEqual(effects,[])
        with self.assertRaisesRegex(ValueError,'uninitialized constant'):app.constant_store.get('Text')

    def test_query_array_indexing_uses_canonical_protocol(self):
        from decimal import Decimal
        from yadinassi.values import BSLArray, BSLFixedArray
        app,owner=self.app()
        with self.boundary(app,owner) as boundary:
            array=BSLArray();array.get_method('Add')('first')
            read=query.resolve_member(boundary,array,'__getitem__')
            self.assertEqual(read(Decimal(0)),'first')
            query.resolve_member(boundary,array,'__setitem__')(Decimal(0),'second')
            self.assertEqual(read(Decimal(0)),'second')
            fixed=BSLFixedArray(array)
            self.assertEqual(query.resolve_member(boundary,fixed,'__getitem__')(Decimal(0)),'second')

    def test_finite_driver_closes_unexpected_suspension(self):
        events=[]
        def suspended():
            try:yield 'not integrated'
            finally:events.append('closed')
        with self.assertRaisesRegex(BoundaryViolation,'suspension'):storage.finish(suspended())
        self.assertEqual(events,['closed'])


if __name__=='__main__':unittest.main()
