"""DefinedType indirection remains closed, bounded and schema-bound."""
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
import tempfile
import unittest
from test_source_constant_store import configuration
from test_source_session_parameters import declaration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_constants import source_constant_definitions
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore

BOOL='<v8:Type>xs:boolean</v8:Type>'
STRING='<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>64</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'


def alias(name):return '<v8:TypeSet>cfg:DefinedType.'+name+'</v8:TypeSet>'

def xml(name,body,family):
    return declaration(name,body).replace(b'SessionParameter',family.encode()).replace(b'xmlns:xs=',b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:xs=')


def package(types=None, constant=None, body='', extra=None):
    types={'Setting':BOOL} if types is None else types
    files={f.path:f.content for f in configuration().files}
    children=''.join('<DefinedType>'+n+'</DefinedType>' for n in types)+'<Constant>Choice</Constant>'
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',children.encode()+b'</ChildObjects>')
    files['Constants/Choice.xml']=xml('Choice',constant or alias('Setting'),'Constant')
    for name,kind in types.items():files['DefinedTypes/'+name+'.xml']=xml(name,kind,'DefinedType')
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    files.update(extra or {})
    return import_source(files)


class DefinedTypeConstantTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.path=Path(d.name)/'scratch.sqlite'

    def store(self,source=None):
        store=SourceConstantStore.create(self.path,source or package());self.addCleanup(store.close);return store

    def test_scalar_alias_identity_binding(self):
        defs,errors,_=source_constant_definitions(package());d=next(d for d in defs if d.name=='Choice')
        self.assertEqual(d.kind,'boolean');self.assertEqual(d.type_dependencies,((str(uuid5(NAMESPACE_URL,'Setting')),'Setting'),));self.assertNotIn('choice',errors)

    def test_direct_get_set(self):
        store=self.store();store.set('Choice',True);self.assertIs(store.get('Choice'),True)
        with self.assertRaises(TypeError):store.set('Choice','true')

    def test_qualified_string_no_implicit_default(self):
        store=self.store(package({'Setting':STRING}))
        with self.assertRaisesRegex(ValueError,'uninitialized'):store.get('Choice')
        store.set('Choice','abc');self.assertEqual(store.get('Choice'),'abc')
        with self.assertRaises(ValueError):store.set('Choice','x'*65)

    def test_composite_alias(self):
        store=self.store(package({'Setting':BOOL+STRING}))
        for value in (True,'text',None):store.set('Choice',value);self.assertEqual(store.get('Choice'),value)

    def test_chained_alias(self):
        _,errors,_=source_constant_definitions(package({'Setting':alias('Leaf'),'Leaf':BOOL}))
        self.assertIn('nested DefinedType unsupported',errors['choice'])

    def test_cycle_is_named_failure(self):
        defs,errors,_=source_constant_definitions(package({'Setting':alias('Leaf'),'Leaf':alias('Setting')}))
        self.assertIn('nested DefinedType unsupported',errors['choice']);self.assertIn('Text',[d.name for d in defs])

    def test_excessive_chain(self):
        types={'Setting':alias('D0')};types.update({'D'+str(i):alias('D'+str(i+1)) for i in range(16)});types['D16']=BOOL
        _,errors,_=source_constant_definitions(package(types));self.assertIn('nested DefinedType unsupported',errors['choice'])

    def test_unknown_defined_type(self):
        _,errors,_=source_constant_definitions(package(constant=alias('Absent')));self.assertIn('unknown DefinedType',errors['choice'])

    def test_mixed_alias_with_scalar_refused(self):
        _,errors,_=source_constant_definitions(package(constant=alias('Setting')+BOOL));self.assertIn('mixed',errors['choice'])

    def test_qualifier_override_refused(self):
        _,errors,_=source_constant_definitions(package(constant=alias('Setting')+'<v8:StringQualifiers/>'));self.assertIn('mixed',errors['choice'])

    def test_wrong_namespace_refused(self):
        _,errors,_=source_constant_definitions(package(constant='<v8:TypeSet>xs:DefinedType.Setting</v8:TypeSet>'));self.assertIn('unsupported source type set',errors['choice'])

    def test_unsupported_underlying_type_stays_unsupported(self):
        defs,errors,_=source_constant_definitions(package({'Setting':'<v8:Type>cfg:CatalogRef.Items</v8:Type>'}))
        self.assertIn('choice',errors);self.assertNotIn('Choice',[d.name for d in defs])

    def test_bsl_manager_set_and_query(self):
        source=package(body='S=Constants.CreateSet("Choice"); S.Choice=True; S.Write(); M=Constants.Choice.CreateValueManager(); M.Read(); Message(M.Value); Q=New Query("SELECT Choice AS X FROM Constants"); R=Q.Execute().Select(); R.Next(); Message(R.X);')
        out=[];app=SourceApplication(source,scratch_database=self.path,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['Да','Да'])

    def test_reopen(self):
        store=self.store();store.set('Choice',True);store.close();store=SourceConstantStore.reopen(self.path,package());self.addCleanup(store.close);self.assertIs(store.get('Choice'),True)

    def test_update_preserves_alias_value(self):
        store=self.store();store.set('Choice',True);store.close();new=package(body='Message("new");');SourceConstantStore.update_source(self.path,new)
        store=SourceConstantStore.reopen(self.path,new);self.addCleanup(store.close);self.assertIs(store.get('Choice'),True)

    def test_underlying_type_update_refused_unchanged(self):
        store=self.store();store.set('Choice',True);store.close();before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,package({'Setting':STRING}))
        self.assertEqual(self.path.read_bytes(),before)

    def test_alias_reidentity_update_refused_unchanged(self):
        store=self.store();store.set('Choice',True);store.close();before=self.path.read_bytes()
        changed=xml('Setting',BOOL,'DefinedType').replace(str(uuid5(NAMESPACE_URL,'Setting')).encode(),str(uuid5(NAMESPACE_URL,'different')).encode())
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,package(extra={'DefinedTypes/Setting.xml':changed}))
        self.assertEqual(self.path.read_bytes(),before)

    def test_alias_to_direct_type_update_refused(self):
        store=self.store();store.close()
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,package(constant=BOOL))

    def test_unused_unsupported_defined_type_does_not_block(self):
        store=self.store(package({'Setting':BOOL,'Other':alias('Missing')}));store.set('Choice',True);self.assertIs(store.get('Choice'),True)

    def test_transaction_rollback(self):
        store=self.store();store.set('Choice',True);store.begin_transaction();store.set('Choice',False);store.rollback_transaction();self.assertIs(store.get('Choice'),True)

    def test_uuid_alias(self):
        from yadinassi.unique_identifiers import BSLUUID
        store=self.store(package({'Setting':'<v8:Type>v8:UUID</v8:Type>'}));v=BSLUUID('01234567-89ab-cdef-0123-456789abcdef');store.set('Choice',v);self.assertEqual(store.get('Choice').text,v.text)

    def test_storage_alias(self):
        from yadinassi.value_storage import BSLValueStorage
        store=self.store(package({'Setting':'<v8:Type>v8:ValueStorage</v8:Type>'}));store.set('Choice',BSLValueStorage('text'));self.assertEqual(store.get('Choice').get(),'text')

    def test_enum_alias_uses_application_namespace(self):
        from test_source_enum_constants import package as enums
        files={f.path:f.content for f in enums().files}
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<DefinedType>Setting</DefinedType></ChildObjects>')
        files['Constants/Choice.xml']=xml('Choice',alias('Setting'),'Constant')
        files['DefinedTypes/Setting.xml']=xml('Setting','<v8:Type>cfg:EnumRef.State</v8:Type>','DefinedType')
        source=import_source(files);app=SourceApplication(source,scratch_database=self.path);self.addCleanup(app.close)
        ref=app.enumerations.get_member('State')._values[0];app.constant_store.set('Choice',ref);self.assertIs(app.constant_store.get('Choice'),ref)
