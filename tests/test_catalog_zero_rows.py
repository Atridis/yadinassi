"""Public zero-Code physical/UUID reads of invented bytes, not native acceptance."""
from dataclasses import asdict, replace
from decimal import Decimal
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from uuid import UUID

import test_native_catalog_zero_code_physical as fixture

# Independent runtime import: the oracle adapter supplies no new reader behavior.
package = types.ModuleType('zero_public_storage')
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'yadinassi/storage')]
sys.modules[package.__name__] = package
entry = importlib.import_module(package.__name__ + '.catalog_reader')
codec = importlib.import_module(package.__name__ + '.catalog_reference_uuid')
c = entry.catalog_module
PHYSICAL = bytes.fromhex('8899aabbccddeeff4677445500112233')
EXPECTED = UUID('00112233-4455-4677-8899-aabbccddeeff')


def source(description=8, payload=32, *, varied=False, rows=1, **kwargs):
    if not varied:
        value = fixture.source(description, payload, rows=rows, **kwargs)
    else:
        cf = fixture.fixture.config_fixture
        keys = ('12345678-1234-4567-89ab-123456789abc', *cf.KEYS[1:])
        attrs = ('abcdef01-1234-4567-89ab-123456789abc', 'abcdef02-1234-4567-89ab-123456789abc')
        matrix = list(cf.policy.MATRIX)
        matrix[0] = ('DifferentInventory', *matrix[0][1:])
        original = cf.constructed.attribute
        original_entries = cf.entries
        def entries(**options):
            result = original_entries(**options)
            _, data, marker = result[0]
            result[0] = (keys[0].upper(), data, marker)
            return result
        def attribute(identifier, name, pattern):
            if identifier.startswith('aaaaaaaa'):
                identifier, name = attrs[0], '"Narrative"'
            elif identifier.startswith('bbbbbbbb'):
                identifier, name = attrs[1], '"Total"'
            return original(identifier, name, pattern)
        with mock.patch.object(cf, 'KEYS', keys), mock.patch.object(cf.policy, 'MATRIX', tuple(matrix)), \
             mock.patch.object(cf.constructed, 'attribute', side_effect=attribute), \
             mock.patch.object(cf, 'entries', side_effect=entries):
            value = fixture.source(description, payload, rows=rows, **kwargs)
        # Independently rebuild DBNames and physical descriptors with different IDs.
        content = ('\ufeff{0,{3,{' + keys[0] + ',"Reference",873},{' + attrs[0] +
                   ',"Fld",914},{' + attrs[1] + ',"Fld",502}}}').encode()
        params = fixture.fixture.params_fixture.source(content)
        for old, new in ((5, 30), (8, 31), (9, 34), (10, 32), (11, 33)):
            value.page(new)[:] = params.page(old)
        value.page(30)[24:28] = fixture.fixture.u32(32)
        value.page(31)[24:28] = fixture.fixture.u32(33)
        value.page(32)[1:5] = fixture.fixture.u32(0)
        fields = [('_IDRREF','B',0,16,0,'CS'), ('_VERSION','RV',0,0,0,'CS'),
                  ('_MARKED','L',0,0,0,'CS'), ('_PREDEFINEDID','B',0,16,0,'CS')]
        if description:
            fields.append(('_DESCRIPTION','NVC',0,description,0,'CI'))
        fields += [('_FLD914','NVC',0,payload,0,'CI'), ('_FLD502','N',0,9,2,'CS')]
        descriptor = fixture.serialize(('_Reference873',0,('Fields',*fields),('Indexes',),
                                         ('Recordlock','0'),('Files',40,41,42))).encode()
        value.chain(tuple(range(14,14+(len(descriptor)+249)//250)),descriptor)
    size = 50 + (2 + 2*description if description else 0) + 2 + 2*payload + 5
    if rows:
        value.page(43)[size+17:size+33] = PHYSICAL
    return value


class ZeroPublicRowsTests(unittest.TestCase):
    def read(self, value=None, *, raw=False, name='NativeOracleItems', **kwargs):
        value = source() if value is None else value
        return (entry.read_catalog_binding if raw else entry.read_catalog_rows)(
            value.read_at, value.size, catalog_name=name, **kwargs)

    def test_four_measured_shapes_both_public_routes_without_code(self):
        for description in (0, 8):
            for payload in (32, 64):
                with self.subTest(description=description, payload=payload):
                    a, b = source(description,payload), source(description,payload)
                    raw, typed = self.read(a,raw=True), self.read(b)
                    self.assertEqual(asdict(raw.records), asdict(typed.records))
                    self.assertEqual(raw.binding, typed.binding)
                    self.assertEqual(a.calls, b.calls)
                    self.assertEqual(typed.binding.code_length, 0)
                    self.assertEqual(typed.binding.code_type, 1)
                    self.assertEqual(len(typed.binding.placements), 6+bool(description))
                    fields = typed.records.rows[0].fields
                    self.assertNotIn('_CODE', [f.declaration.name for f in fields])
                    self.assertEqual([f.value for f in fields[-2:]], ['alpha', Decimal('1.25')])
                    self.assertEqual(fields[-2].offset, 50 if description == 0 else 68)
                    self.assertEqual(typed.rows[0].reference_uuid, EXPECTED)
                    self.assertIs(typed.rows[0].physical_record, typed.records.rows[0])
                    self.assertFalse(hasattr(typed.rows[0], 'code'))
                    self.assertFalse(hasattr(typed, 'native_acceptance'))
                    if description:self.assertEqual(fields[4].value,'X')

    def test_identifiers_names_and_physical_ids_are_dynamic(self):
        for description, payload in ((0,32),(8,64)):
            value = source(description,payload,varied=True)
            result = self.read(value,name='DifferentInventory')
            raw = self.read(source(description,payload,varied=True),raw=True,name='DifferentInventory')
            self.assertEqual(asdict(raw.records),asdict(result.records))
            self.assertEqual(raw.binding,result.binding)
            self.assertEqual(result.identity.metadata_uuid,'12345678-1234-4567-89ab-123456789abc')
            self.assertEqual(result.binding.table_name,'_Reference873')
            self.assertEqual([(a.name,a.physical_name) for a in result.binding.attributes],
                             [('Narrative','_FLD914'),('Total','_FLD502')])
            self.assertEqual(result.rows[0].reference_uuid,EXPECTED)
            self.assertNotEqual(result.rows[0].reference_uuid,UUID(result.identity.metadata_uuid))
            self.assertEqual(result.records.rows[0].fields[-2].value,'alpha')
            self.assertEqual(result.records.rows[0].fields[-1].value,Decimal('1.25'))
            with self.assertRaises(c.UnsupportedLayout):self.read(value)

    def test_complete_single_graph_and_failure_poison(self):
        readers, graphs = [], []
        ri, gi = c.CatalogReader.__init__, c._CatalogBindingGraph.__init__
        def reader(obj,*a,**k):ri(obj,*a,**k);readers.append(obj)
        def graph(obj,*a,**k):gi(obj,*a,**k);graphs.append(obj)
        with mock.patch.object(c.CatalogReader,'__init__',reader), mock.patch.object(c._CatalogBindingGraph,'__init__',graph):
            result = self.read()
            with self.assertRaises(c.CatalogError):self.read(source(17))
        self.assertEqual(len(readers),2);self.assertEqual(len(graphs),2)
        self.assertFalse(graphs[0].failed);self.assertEqual(graphs[0]._next,3)
        self.assertEqual(result.usage,readers[0].usage)
        self.assertTrue(graphs[1].failed)
        for graph in graphs:
            with self.assertRaises(ValueError):
                with graph.stage('config'):pass

    def test_raw_route_has_no_uuid_conversion_and_baseline_stays_empty(self):
        with mock.patch.object(entry,'_project_rows',side_effect=AssertionError('raw route')):
            self.assertEqual(self.read(raw=True).records.rows[0].fields[0].value,PHYSICAL)
        for desc in (0,8):
            with mock.patch.object(codec,'decode_catalog_reference_uuid',side_effect=AssertionError('no row')):
                result=self.read(source(desc,rows=0))
            self.assertEqual(result.rows,());self.assertEqual(result.records.rows,())

    def test_unmeasured_qualifiers_and_numeric_zero_rejected(self):
        for kwargs in ({'description':1},{'description':17},{'payload':31},{'payload':65},{'kind':0}):
            with self.subTest(kwargs=kwargs),self.assertRaises(c.UnsupportedLayout):self.read(source(**kwargs))

    def test_physical_extra_code_misordered_description_and_multiple_rows(self):
        edits = (lambda ds:ds[:4]+[('_CODE','NVC',0,0,0,'CI')]+ds[4:],
                 lambda ds:ds[:4]+list(reversed(ds[4:])),
                 lambda ds:ds[:4]+[('_DESCRIPTION','NVC',0,17,0,'CI')]+ds[5:])
        for edit in edits:
            with self.assertRaises(c.CatalogError):self.read(source(edit=edit))
        self.assertEqual(len(self.read(source(rows=2)).rows), 2)

    def test_same_lifetime_cumulative_budget_exact_and_one_less(self):
        usage=self.read().usage
        for field in ('page_reads','read_bytes','bytes_processed','output_bytes','tokens'):
            amount=getattr(usage,field)
            limits=replace(c.CatalogLimits(),**{'max_'+field:amount})
            self.assertEqual(self.read(limits=limits).usage,usage)
            with self.assertRaises(c.ResourceLimit):self.read(limits=replace(limits,**{'max_'+field:amount-1}))

    def test_forged_zero_projection_shape_fails_before_codec(self):
        original=entry._project_rows
        for mode in ('numeric','description','missing','duplicate','extra'):
            def forged(graph,identity,binding,records):
                if mode=='numeric':binding=replace(binding,code_type=0);identity=replace(identity,code_type=0)
                elif mode=='description':binding=replace(binding,description_length=17);identity=replace(identity,description_length=17)
                elif mode=='missing':binding=replace(binding,placements=binding.placements[:-1])
                elif mode=='duplicate':binding=replace(binding,placements=(binding.placements[0],)*len(binding.placements))
                else:binding=replace(binding,placements=binding.placements+(binding.placements[-1],))
                return original(graph,identity,binding,records)
            with mock.patch.object(entry,'_project_rows',side_effect=forged), \
                 mock.patch.object(codec,'decode_catalog_reference_uuid') as called, self.assertRaises(c.InvalidStructure):
                self.read()
            called.assert_not_called()

    def test_short_callback_and_page_alias_fail_closed(self):
        value=source();original=value.read_at
        def short(offset,length):
            data=original(offset,length)
            return data[:-1] if offset==43*fixture.fixture.P else data
        with self.assertRaises(c.CatalogError):entry.read_catalog_rows(short,value.size,catalog_name='NativeOracleItems')
        value=source();value.page(40)[24:28]=fixture.fixture.u32(32)
        with self.assertRaises(c.CatalogError):self.read(value)

if __name__=='__main__':unittest.main()
