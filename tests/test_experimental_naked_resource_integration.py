import os
import unittest
from unittest.mock import patch
from yadinassi import values
from yadinassi.experimental_naked_collections import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext


class ResourceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_constructor_failure_is_catchable_before_assignment(self):
        with patch.object(values,'_MAX_ARRAY_CONSTRUCTION',4):
            result=prepare('r=0;Try a=New Array(5);Except r=1;EndTry;',repairs=('resource_bounds','error_boundaries')).run()
        self.assertEqual(result['r'],1)
        self.assertNotIn('a',result)

    def test_empty_array_static_proof_preserves_live_limits(self):
        program=prepare('a=New Array;',repairs=('resource_bounds',))
        with patch.object(values,'_MAX_ARRAY_CONSTRUCTION',0):
            self.assertEqual(program.run()['a'],[])
        with patch.object(values,'_MAX_ARRAY_DIMENSIONS',0):
            with self.assertRaises(ValueError):program.run()

    def test_insert_effect_order_and_no_partial_mutation(self):
        effects=[]
        ctx=BoundaryContext(services={'effect':lambda:effects.append('value') or 9})
        program=prepare('a=New Array;a.Add(1);Try a.Insert(5,Effect());Except r=1;EndTry;',repairs=('resource_bounds','service_boundaries','error_boundaries'))
        with patch.object(values,'_MAX_INSERT_GROWTH',4):
            result=program.run(context=ctx)
        self.assertEqual(result['r'],1)
        self.assertEqual(result['a'],[1])
        self.assertEqual(effects,['value'])

    def test_extracted_insert_uses_same_resource_limit(self):
        program=prepare('a=New Array;f=a.Insert;Try f(5,9);Except r=1;EndTry;',repairs=('resource_bounds','method_values','service_boundaries','error_boundaries'))
        with patch.object(values,'_MAX_INSERT_GROWTH',4):
            result=program.run(context=BoundaryContext())
        self.assertEqual(result['r'],1)
        self.assertEqual(result['a'],[])

    def test_huge_bad_index_diagnostic_does_not_expand_integer(self):
        from decimal import Decimal
        from yadinassi import experimental_naked_collections as module
        # Reproduced before this fix: formatting the error called int(1e1000000).
        with patch.object(module,'int',side_effect=AssertionError('integer expansion'),create=True):
            with self.assertRaises(IndexError):
                module._checked_array_index([],Decimal('1e1000000'))

    def test_trusted_local_constructor_does_not_adopt_artificial_cap(self):
        with patch.object(values,'_MAX_ARRAY_CONSTRUCTION',4):
            result=prepare('a=New Array(5);',repairs=('constructor_bounds',)).run()
        self.assertEqual(result['a'],[None]*5)

    def test_trusted_local_insert_does_not_adopt_artificial_growth_cap(self):
        with patch.object(values,'_MAX_INSERT_GROWTH',4):
            result=prepare('a=New Array;a.Insert(5,9);',repairs=('constructor_bounds','array_insert_shape')).run()
        self.assertEqual(result['a'],[None]*5+[9])
