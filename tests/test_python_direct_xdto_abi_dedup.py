"""ABI dedup retains all requirements and revalidates mutable classes."""
import unittest
from unittest.mock import patch
from yadinassi.execution.direct.source import python_direct_source_xdto as shared
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class XDTOABIDedupTests(unittest.TestCase):
    def test_exact_requirement_union_and_module_checks_preserved(self):
        def key(entry):
            cls,mro,fields=entry
            return id(cls),id(mro),tuple((name,id(value)) for name,value in fields)
        before=[entry for _,_,classes,_ in shared._ABI for entry in classes]
        after=[entry for _,_,classes,_ in shared._HOOK_ABI for entry in classes]
        self.assertEqual(set(map(key,before)),set(map(key,after)))
        self.assertEqual(len(after),len(set(map(key,before))))
        self.assertLess(len(after),len(before))
        for old,new in zip(shared._ABI,shared._HOOK_ABI):
            for index in (0,1,3):self.assertIs(old[index],new[index])

    def test_conflicting_requirements_are_not_merged(self):
        class C:pass
        marker=object();one=(C,C.__mro__,(('field',object()),))
        other=(C,C.__mro__,(('field',object()),))
        different_mro=(C,tuple(list(C.__mro__)),one[2])
        different_fields=(C,C.__mro__,one[2]+(('extra',object()),))
        result=shared._unique_class_requirements(((marker,(),(one,one,other,different_mro,different_fields),()),))
        self.assertEqual(len(result[0][2]),4)
        self.assertIs(result[0][2][0][2],one[2])
        self.assertIs(result[0][2][1][2],other[2])

    def test_every_retained_class_still_checked_after_warm_success(self):
        shared._hooks()
        for _,_,classes,_ in shared._HOOK_ABI:
            for cls,_,_ in classes:
                if cls is object:continue  # Immutable built-in; union coverage above still includes it.
                with self.subTest(cls=cls.__name__):
                    with patch.object(cls,'_audit_added_field',object(),create=True):
                        with self.assertRaises(BoundaryViolation):shared._hooks()
                    shared._hooks()
