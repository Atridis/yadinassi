"""Finite diagnostics cover source-backed runtime raises, not inferred native causes."""
import ast
from pathlib import Path
import unittest
from unittest import mock
import test_native_catalog_description_physical as fixture
import catalog_binding_reader as loader
import catalog_description_physical as adapter
import catalog_description_rows as policy
import inputs

ROOT=Path(__file__).resolve().parents[1]
CLASSES={name:getattr(loader.catalog_module,name) for name in (
    'UnsupportedLayout','InvalidStructure','ResourceLimit','UnsupportedSharing',
    'SourceIOError','ChangedDuringRead','NotRegularFile')}
CATEGORIES=dict(UnsupportedLayout='unsupported_layout',InvalidStructure='structural_rejection',
    ResourceLimit='resource_limit',UnsupportedSharing='unsupported_sharing_policy',
    SourceIOError='io_or_change',ChangedDuringRead='io_or_change',NotRegularFile='io_or_change')
SOURCES=tuple(name for name in inputs.CATALOG_DESCRIPTION_ROWS_SOURCE_FILES
    if name.startswith('yadinassi/storage/') or name.endswith('/catalog_binding_reader.py'))


def source_raises():
    literals=set();dynamic=[]
    for name in SOURCES:
        tree=ast.parse((ROOT/name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node,ast.Raise) or not isinstance(node.exc,ast.Call):continue
            function=node.exc.func
            kind=function.id if isinstance(function,ast.Name) else function.attr if isinstance(function,ast.Attribute) else None
            if kind not in CLASSES:continue
            value=node.exc.args[0]
            if isinstance(value,ast.Constant) and type(value.value) is str:literals.add((kind,value.value))
            else:dynamic.append((name,kind,ast.unparse(value)))
    return literals,dynamic


class DiagnosticCoverageTests(unittest.TestCase):
    def assert_classified(self,kind,code):
        error=CLASSES[kind](code)
        value=policy.diagnostic_for(error,snapshot='applied',phase='public_reader')
        self.assertEqual((value['category'],value['code']),(CATEGORIES[kind],code),(kind,code))

    def test_every_storage_literal_raise_in_loaded_runtime_sources_is_classified(self):
        literals,_=source_raises()
        self.assertGreater(len(literals),100)
        for kind,code in sorted(literals):
            with self.subTest(kind=kind,code=code):self.assert_classified(kind,code)

    def test_dynamic_families_are_closed_source_enumerations_not_prefix_acceptance(self):
        _,dynamic=source_raises()
        expected={
            ('yadinassi/storage/filedb_catalog.py','ResourceLimit','name'),
            ('yadinassi/storage/filedb_named_file.py','ResourceLimit',"'transport_' + name"),
            ('yadinassi/storage/filedb_records.py','UnsupportedLayout',"'format_' + discriminator"),
            ('yadinassi/storage/config_catalog_records.py','UnsupportedLayout',"'format_' + discriminator"),
            ('yadinassi/storage/config_catalog_transport.py','ResourceLimit',"'config_projection_' + error.code"),
            ('yadinassi/storage/config_catalog_transport.py','ResourceLimit',"'config_catalog_identity_limits' if identity else 'config_catalog_standard_limits' if standard else 'config_catalog_name_limits'"),
            ('yadinassi/storage/config_catalog_transport.py','InvalidStructure',"'config_catalog_identity_prefix' if identity else 'config_catalog_standard_prefix' if standard else 'config_catalog_name_prefix'"),
        }
        self.assertEqual(set(dynamic),expected)
        source=ast.parse((ROOT/'yadinassi/storage/filedb_catalog.py').read_text(encoding='utf-8'))
        usage=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='CatalogUsage')
        budget=[n.target.id for n in usage.body if isinstance(n,ast.AnnAssign)]
        named=ast.parse((ROOT/'yadinassi/storage/filedb_named_file.py').read_text(encoding='utf-8'))
        cls=next(n for n in named.body if isinstance(n,ast.ClassDef) and n.name=='_TransportBudget')
        assignments=[n for n in ast.walk(cls) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Dict)
            and any(isinstance(t,ast.Attribute) and t.attr=='counts' for t in n.targets)]
        self.assertEqual(len(assignments),1)
        transport=[n.value for n in assignments[0].value.keys]
        self.assertEqual(set(transport),{'blob_bytes','inflate_input_bytes','plain_bytes','blob_visits','inflate_calls'})
        for code in budget+['transport_'+n for n in transport]+['config_projection_'+n for n in ('input_bytes','prefix_bytes','output_bytes')]+['config_catalog_identity_limits']:
            self.assert_classified('ResourceLimit',code)
        records=ast.parse((ROOT/'yadinassi/storage/filedb_records.py').read_text(encoding='utf-8'))
        discriminator=next(n for n in records.body if isinstance(n,ast.FunctionDef) and n.name=='format_discriminator')
        def return_values(node):
            if isinstance(node,ast.Constant) and type(node.value) is str:return {node.value}
            self.assertIsInstance(node,ast.IfExp)
            return return_values(node.body)|return_values(node.orelse)
        format_values=set().union(*(return_values(node.value) for node in ast.walk(discriminator) if isinstance(node,ast.Return)))
        self.assertIn('integer_zero',format_values)
        bound_source=(ROOT/'yadinassi/storage/config_catalog_records.py').read_text(encoding='utf-8')
        self.assertIn("discriminator != 'integer_zero'",bound_source)
        for code in format_values-{'integer_zero'}:self.assert_classified('UnsupportedLayout','format_'+code)
        projection_source=(ROOT/'yadinassi/storage/config_catalog_transport.py').read_text(encoding='utf-8')
        self.assertIn("if error.code in ('input_bytes', 'prefix_bytes', 'output_bytes'):",projection_source)
        # The typed binding entrypoint fixes identity=True. Do not pretend
        # its unused standard/name alternatives are reachable on this route.
        config=ast.parse(projection_source)
        entry=next(n for n in config.body if isinstance(n,ast.FunctionDef) and n.name=='_observe_catalog_attributes_from_graph')
        calls=[n for n in ast.walk(entry) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_observe_catalog_prefix']
        self.assertEqual(len(calls),1)
        selected={k.arg:k.value.value for k in calls[0].keywords if k.arg in ('identity','standard','attributes') and isinstance(k.value,ast.Constant)}
        self.assertEqual(selected,{'identity':True,'standard':True,'attributes':True})
        self.assert_classified('InvalidStructure','config_catalog_identity_prefix')
        for cls,code in ((CLASSES['ResourceLimit'],'transport_PRIVATE'),(CLASSES['UnsupportedLayout'],'format_PRIVATE'),(CLASSES['ResourceLimit'],'config_projection_PRIVATE')):
            self.assertEqual(policy.diagnostic_for(cls(code),snapshot='applied',phase='public_reader')['category'],'unclassified')

    def test_actual_payload64_reader_missing_table_failure_has_same_class_and_finite_code(self):
        modules=loader._load_storage(project_rows=True)
        self.assertIs(policy._catalog_errors,loader.catalog_module)
        for module in modules.values():
            if hasattr(module,'UnsupportedLayout'):self.assertIs(module.UnsupportedLayout,loader.catalog_module.UnsupportedLayout)
        value=fixture.source(8,'Я ',64);raw=value.full_bytes()
        observed,_=adapter.read_description_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        self.assertEqual(observed.attributes.attributes[0].qualifiers[0],64)
        for before,after in ((b'_Reference19',b'_Reference20'),(b'PARAMS',b'PARAXS')):
            mutated=raw.replace(before,after);self.assertNotEqual(mutated,raw)
            with self.assertRaises(loader.catalog_module.UnsupportedLayout) as caught:
                adapter.read_description_rows(lambda offset,size:mutated[offset:offset+size],len(mutated),catalog_name='NativeOracleItems')
            self.assertIs(type(caught.exception),loader.catalog_module.UnsupportedLayout)
            self.assertEqual(caught.exception.code,'binding_table_count')
            self.assertEqual(policy.diagnostic_for(caught.exception,snapshot='applied',phase='public_reader')['code'],'binding_table_count')

    def test_loader_valueerror_discriminates_type_without_inspecting_message(self):
        source=(ROOT/'scripts/native_1c_db_oracle/catalog_binding_reader.py').read_text(encoding='utf-8')
        self.assertIn("raise ValueError('catalog binding cached sibling mismatch')",source)
        error=ValueError('PRIVATE SOURCE PATH')
        value=fixture.source(8,'Я ',64)
        result=loader.read_catalog_rows(value.read_at,value.size,catalog_name='NativeOracleItems')
        with mock.patch.object(loader,'_load_storage',side_effect=error),self.assertRaises(ValueError) as caught:
            loader._raw_rows_view(result)
        self.assertIs(caught.exception,error)
        self.assertEqual(policy.diagnostic_for(error,snapshot='applied',phase='public_reader'),
            dict(snapshot='applied',phase='public_reader',category='builtin',code='value_error'))
