import unittest
from types import SimpleNamespace
from yadinassi.python_direct_database import CatalogBoundary, _DETACHED_TYPE_IDS
from yadinassi.values import BSLArray
from yadinassi.value_tables import BSLValueTableRow, BSLCollectionIndexes
from yadinassi.value_lists import BSLValueListItem
from yadinassi.queries import BSLQuery
from yadinassi.experimental_naked_boundaries import BoundaryViolation

class DetachedDispatchTests(unittest.TestCase):
    def test_exact_detached_type_still_checks_current_boundary(self):
        calls=[]
        boundary=SimpleNamespace(vm=SimpleNamespace(_catalogs=object()),_check=lambda:calls.append(1))
        CatalogBoundary._catalog_owner(boundary,BSLArray())
        self.assertEqual(calls,[1])
        def closed():raise BoundaryViolation('closed')
        boundary._check=closed
        with self.assertRaisesRegex(BoundaryViolation,'closed'):
            CatalogBoundary._catalog_owner(boundary,BSLArray())

    def test_subclasses_and_owner_bearing_children_not_in_fast_path(self):
        class Child(BSLArray):pass
        boundary=SimpleNamespace(vm=SimpleNamespace(_catalogs=object()),_check=lambda:None)
        with self.assertRaises(BoundaryViolation):CatalogBoundary._catalog_owner(boundary,Child())
        for cls in (Child,BSLValueTableRow,BSLCollectionIndexes,BSLValueListItem,BSLQuery):
            self.assertNotIn(id(cls),_DETACHED_TYPE_IDS)
