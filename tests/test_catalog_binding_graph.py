"""Finite three-table resource graph mechanics on invented bytes only."""
from copy import copy
from dataclasses import replace
import unittest
from test_filedb_catalog import Source, descriptor
import test_config_catalog_binding as compiler_tests
c = compiler_tests.catalog


def source(*, config='CONFIG', params='PARAMS', shared_page=False):
    s = Source(page_count=24)
    s.ready({2:descriptor(config, fields='', files=(5,6,0)),
             3:descriptor(params, fields='', files=(7,8,0)),
             4:descriptor('_Reference19', fields='', files=(9,10,0))})
    for page in range(5,11):
        s.page(page)[:24] = b'\x1c\xfd' + bytes(14) + (1 if shared_page and page in (5,7) else 0).to_bytes(8,'little')
        s.page(page)[24:28] = (12).to_bytes(4,'little')
    return s


def graph(s=None):
    s = source() if s is None else s
    reader = c.CatalogReader(s.read_at,s.size)
    cat = reader.read_catalog()
    return s,reader,cat,c._CatalogBindingGraph(reader,cat)


def finish(g,role,binding=None):
    with g.stage(role,binding=binding) as h:
        d=h._open_table_data(h.table)
        if role!='records':h._open_table_blob(h.table)
        return d,h


class BindingGraphTests(unittest.TestCase):
    def test_three_ordered_roles_one_source_budget_and_revoked_views(self):
        s,r,cat,g=graph(); before=r.usage
        d,h=finish(g,'config')
        finish(g,'params')
        binding,_=compiler_tests.CatalogBindingTests().compile()
        finish(g,'records',binding)
        self.assertEqual(g._next,3);self.assertFalse(g.failed)
        self.assertGreater(r.usage.output_bytes,before.output_bytes)
        self.assertEqual(len({id(x) for x in g._tables}),3)
        with self.assertRaises(ValueError):finish(g,'records',binding)
        self.assertTrue(g.failed);self.assertFalse(s.closed)

    def test_stale_handle_rejection_poison_even_when_caught(self):
        _,r,cat,g=graph();d,h=finish(g,'config')
        with self.assertRaises(ValueError):d.read_range(0,0)
        self.assertTrue(g.failed)
        with self.assertRaises(ValueError):finish(g,'params')

    def test_legacy_unchanged_when_no_graph_and_sealed_after_graph(self):
        s=source();r=c.CatalogReader(s.read_at,s.size);cat=r.read_catalog()
        r._open_table_data(cat.tables[0]);r._open_table_blob(cat.tables[0])
        with self.assertRaises(ValueError):r._open_table_data(cat.tables[1])
        with self.assertRaises(ValueError):c._CatalogBindingGraph(r,cat)
        _,r,cat,g=graph()
        with self.assertRaises(ValueError):r._open_table_data(cat.tables[0])
        with self.assertRaises(ValueError):r._open_table_blob(cat.tables[0])
        with self.assertRaises(ValueError):c._CatalogBindingGraph(r,cat)

    def test_catalog_identity_not_structural_equality(self):
        s=source();r=c.CatalogReader(s.read_at,s.size);cat=r.read_catalog()
        with self.assertRaises(ValueError):c._CatalogBindingGraph(r,replace(cat))
        self.assertFalse(r._table_opened)

    def test_wrong_order_and_missing_stage_completion_poison(self):
        for mode in ('order','missing','partial','decode'):
            with self.subTest(mode=mode):
                _,r,cat,g=graph()
                with self.assertRaises((ValueError,RuntimeError)):
                    with g.stage('params' if mode=='order' else 'config') as h:
                        if mode in ('partial','decode'):h._open_table_data(h.table)
                        if mode=='decode':
                            h._open_table_blob(h.table)
                            raise RuntimeError('synthetic decoding failure after successful opens')
                self.assertTrue(g.failed)
                with self.assertRaises(ValueError):finish(g,'config')

    def test_forged_and_cross_handle_tables_poison(self):
        for mode in ('copy_handle','copy_table','other_table','duplicate_data','early_blob'):
            with self.subTest(mode=mode):
                _,r,cat,g=graph()
                with self.assertRaises(ValueError):
                    with g.stage('config') as h:
                        if mode=='copy_handle':copy(h)._open_table_data(h.table)
                        elif mode=='copy_table':h._open_table_data(replace(h.table))
                        elif mode=='other_table':h._open_table_data(cat.tables[1])
                        elif mode=='early_blob':h._open_table_blob(h.table)
                        else:
                            h._open_table_data(h.table);h._open_table_data(h.table)
                self.assertTrue(g.failed)

    def test_cross_table_physical_page_sharing_rejected(self):
        _,r,cat,g=graph(source(shared_page=True));finish(g,'config')
        with self.assertRaises(c.UnsupportedSharing):finish(g,'params')
        self.assertTrue(g.failed)

    def test_copied_graph_rejected_and_no_alternate_session(self):
        _,r,cat,g=graph()
        with self.assertRaises(ValueError):finish(copy(g),'config')
        self.assertEqual(g._next,0)
        finish(g,'config')

    def test_stage_can_not_be_nested_and_read_error_poison(self):
        _,r,cat,g=graph()
        with self.assertRaises(ValueError):
            with g.stage('config'):
                with g.stage('params'):pass
        self.assertTrue(g.failed)
        _,r,cat,g=graph()
        with self.assertRaises(c.InvalidStructure):
            with g.stage('config') as h:
                d=h._open_table_data(h.table);d._validate_range(0,1)
        self.assertTrue(g.failed)

    def test_missing_or_ambiguous_role_does_not_read_data(self):
        for s in (source(config='OTHER'),source(params='config')):
            _,r,cat,g=graph(s);before=len(s.calls)
            with self.assertRaises(c.UnsupportedLayout):finish(g,'config')
            self.assertEqual(len(s.calls),before)
            self.assertTrue(g.failed)
