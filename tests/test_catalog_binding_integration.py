"""Invented CONFIG/PARAMS/row bytes on one graph; not native compatibility."""
import importlib
import sys
import unittest
from unittest import mock
import test_native_1c_db_oracle_catalog_attribute_binding as config_fixture
import test_native_1c_db_oracle_extraction as params_fixture
from test_filedb_records import serialize, row
from test_filedb_catalog import P, u32
import config_framing_reader as config
import filedb_catalog as c
import params_extraction

ap = config.load_catalog_attribute_projector()
pkg = ap.__package__
sys.modules[pkg+'.filedb_catalog'] = c
def load(name):
    spec=importlib.util.spec_from_file_location(pkg+'.'+name, config_fixture.matrix.ROOT/'yadinassi/storage'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module

dbnames=load('filedb_dbnames')
binding=load('config_catalog_binding')
load('filedb_records')
records=load('config_catalog_records')
named = params_extraction.load_reader(config_fixture.matrix.ROOT/'yadinassi/storage/filedb_named_file.py')


def source():
    value = config_fixture.source()
    value.page_count=64;value.size=64*P;value.page(0)[12:16]=u32(64)
    cuuid=config_fixture.KEYS[0]
    content=('\ufeff{0,{3,{'+cuuid+',"Reference",19},'
        '{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,"Fld",62},'
        '{bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb,"Fld",741}}}').encode()
    params=params_fixture.source(content)
    for old,new in ((5,30),(8,31),(9,34),(10,32),(11,33)):
        value.page(new)[:]=params.page(old)
    value.page(30)[24:28]=u32(32);value.page(31)[24:28]=u32(33)
    # Public coordinator selects the closed marker-one recipe: an all-active
    # PARAMS image has a zero reserved head. The original extraction fixture
    # retains opaque R padding to test the unchanged strict/default recipe.
    value.page(32)[1:5]=u32(0)
    declarations=(('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
        ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'),
        ('_CODE','NVC',0,2,0,'CI'),('_FLD62','NVC',0,32,0,'CI'),('_FLD741','N',0,9,2,'CS'))
    descriptions=((10,('PARAMS',0,('Fields',*params_fixture.policy.DECLARATIONS),('Indexes',),('Recordlock','0'),('Files',30,31,34))),
                  (14,('_Reference19',0,('Fields',*declarations),('Indexes',),('Recordlock','0'),('Files',40,41,42))))
    value.catalog((2,10,14))
    for block,desc in descriptions:
        encoded=serialize(desc).encode();value.chain(tuple(range(block,block+(len(encoded)+249)//250)),encoded)
    data=b'\x01'+b'R'*126+row()
    value.page(40)[:24]=b'\x1c\xfd'+bytes(14)+len(data).to_bytes(8,'little')
    value.page(40)[24:28]=u32(43);value.page(43)[:len(data)]=data
    return value


def compile_on_graph(value):
    reader=c.CatalogReader(value.read_at,value.size);catalog=reader.read_catalog()
    graph=c._CatalogBindingGraph(reader,catalog)
    with graph.stage('config') as h:
        observation=config._observe_catalog_attributes_from_graph(h,
            profile=config.ConfigCatalogAttributeProfile(config_fixture.policy.DECLARATIONS,'0',0))
    with graph.stage('params') as h:
        extracted=named._read_dbnames_from_catalog(reader,catalog,
            profile=named.DBNamesProfile(params_fixture.policy.DECLARATIONS,'0',0),_binding_handle=h)
        pp=dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
        pl=dbnames.DBNamesParseLimits()
        reservation=dbnames.reserve_dbnames_parse(extracted.data,profile=pp,limits=pl)
        reader._budget.charge('output_bytes',reservation.output_bytes)
        reader._budget.charge('bytes_processed',reservation.bytes_processed)
        parsed=dbnames.parse_dbnames(extracted.data,profile=pp,limits=pl)
        matches=[x for x in observation.private_fields if x[1].metadata_uuid==config_fixture.KEYS[0]]
        assert len(matches)==1
        key,identity,attributes=matches[0]
        compiled=binding.compile_catalog_binding(identity,attributes,parsed,
            profile=binding.CatalogBindingProfile(binding.PROFILE_IDENTIFIER),budget=reader._budget)
    return reader,catalog,graph,compiled


class BindingIntegrationTests(unittest.TestCase):
    def test_independent_bytes_compile_on_one_reader(self):
        value=source();readers=[];original=c.CatalogReader.__init__
        def init(obj,*a,**kw):original(obj,*a,**kw);readers.append(obj)
        with mock.patch.object(c.CatalogReader,'__init__',init):
            reader,catalog,graph,compiled=compile_on_graph(value)
        self.assertEqual(readers,[reader]);self.assertEqual(graph._next,2)
        self.assertEqual(compiled.table_name,'_Reference19')
        self.assertEqual([a.physical_name for a in compiled.attributes],['_FLD62','_FLD741'])
        self.assertEqual(compiled.record_size,127)
        self.assertEqual(compiled.declarations,tuple(x.raw for x in catalog.tables[2].fields))
        self.assertGreater(reader.usage.bytes_processed,0)
        before=reader.usage.bytes_processed
        with graph.stage('records',binding=compiled) as h:
            actual=records.read_bound_catalog_records(reader,catalog,compiled,handle=h)
        self.assertEqual(graph._next,3)
        self.assertEqual(len(actual.rows),1)
        self.assertEqual([x.value for x in actual.rows[0].fields][4:],['K1','alpha',records.Decimal('1.25')])
        self.assertGreater(reader.usage.bytes_processed,before)

    def test_config_late_failure_poison_prevents_params(self):
        value=source();reader=c.CatalogReader(value.read_at,value.size);catalog=reader.read_catalog()
        graph=c._CatalogBindingGraph(reader,catalog)
        with self.assertRaises(RuntimeError):
            with graph.stage('config') as h:
                config._observe_catalog_attributes_from_graph(h,
                    profile=config.ConfigCatalogAttributeProfile(config_fixture.policy.DECLARATIONS,'0',0))
                raise RuntimeError('synthetic late validation failure')
        before=len(value.calls)
        with self.assertRaises(ValueError):
            with graph.stage('params'):pass
        self.assertEqual(len(value.calls),before)

    def test_caught_config_decode_error_still_poisoned(self):
        value=source();reader=c.CatalogReader(value.read_at,value.size);catalog=reader.read_catalog()
        graph=c._CatalogBindingGraph(reader,catalog)
        with self.assertRaises(ValueError):
            with graph.stage('config') as h:
                with mock.patch.object(config._ConfigContentDecoder,'decode',side_effect=RuntimeError('synthetic')):
                    try:
                        config._observe_catalog_attributes_from_graph(h,
                            profile=config.ConfigCatalogAttributeProfile(config_fixture.policy.DECLARATIONS,'0',0))
                    except RuntimeError:pass
        self.assertTrue(graph.failed);self.assertEqual(graph._next,0)

    def test_caught_params_inflate_error_still_poisoned(self):
        value=source();reader=c.CatalogReader(value.read_at,value.size);catalog=reader.read_catalog()
        graph=c._CatalogBindingGraph(reader,catalog)
        with graph.stage('config') as h:
            config._observe_catalog_attributes_from_graph(h,
                profile=config.ConfigCatalogAttributeProfile(config_fixture.policy.DECLARATIONS,'0',0))
        with self.assertRaises(ValueError):
            with graph.stage('params') as h:
                with mock.patch.object(named,'_inflate_raw',side_effect=RuntimeError('synthetic')):
                    try:
                        named._read_dbnames_from_catalog(reader,catalog,
                            profile=named.DBNamesProfile(params_fixture.policy.DECLARATIONS,'0',0),_binding_handle=h)
                    except RuntimeError:pass
        self.assertTrue(graph.failed);self.assertEqual(graph._next,1)
