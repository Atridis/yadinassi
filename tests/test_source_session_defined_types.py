"""Source startup aliases resolve metadata only, not host authority or defaults."""
import unittest
from uuid import NAMESPACE_URL, uuid5
from test_source_session_parameters import package
from test_source_defined_type_constants import alias, xml, BOOL, STRING
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.configuration_source_session import source_session_definitions
from yadinassi.errors import BSLError


def configuration(types=None, declaration=None, body=''):
    types = {'Root': alias('Leaf'), 'Leaf': BOOL} if types is None else types
    files = {f.path: f.content for f in package(body).files}
    children = ''.join('<DefinedType>'+name+'</DefinedType>' for name in types)
    files['Configuration.xml'] = files['Configuration.xml'].replace(
        b'</Configuration>', b'<ChildObjects>'+children.encode()+b'</ChildObjects></Configuration>')
    files['SessionParameters/State.xml'] = xml('State', declaration or alias('Root'), 'SessionParameter')
    for name, content in types.items():
        files['DefinedTypes/'+name+'.xml'] = xml(name, content, 'DefinedType')
    return import_source(files)


class SourceSessionDefinedTypeTests(unittest.TestCase):
    def start(self, **kwargs):
        output=[]
        app=SourceApplication(configuration(**kwargs), output=output.append)
        self.addCleanup(app.close)
        app.start()
        return app, output

    def test_chain_startup_and_parameter_identity(self):
        source=configuration(body='SessionParameters.State=True; Message(SessionParameters.State);')
        defs, errors=source_session_definitions(source)
        self.assertFalse(errors)
        self.assertEqual(defs[0].identity, uuid5(NAMESPACE_URL,'State'))
        self.assertEqual(defs[0].name,'State')
        _, output=self.start(body='SessionParameters.State=True; Message(SessionParameters.State);')
        self.assertEqual(output,['Да'])

    def test_immutable_union_and_metadata(self):
        app, _=self.start(types={'Root':alias('Leaf'),'Leaf':BOOL+'<v8:Type>v8:UUID</v8:Type>'},
            body='SessionParameters.State=New UUID; SessionParameters.State=True;')
        self.assertIs(app.session_parameters._values['state'],True)
        with self.assertRaisesRegex(ValueError,'unsupported metadata field type'):
            app.session_parameters.metadata.get_member('State').get_member('Type')

    def test_qualifiers_and_atomic_rejected_assignment(self):
        app, _=self.start(types={'Root':alias('Leaf'),'Leaf':STRING},
            body='SessionParameters.State="ok"; Try SessionParameters.State=1; Except EndTry;')
        self.assertEqual(app.session_parameters._values['state'],'ok')
        defs,_=source_session_definitions(configuration(types={'Root':alias('Leaf'),'Leaf':STRING}))
        self.assertEqual(defs[0].kind,'string')
        self.assertIn(64,defs[0].qualifiers)

    def test_immutable_value_retains_validation(self):
        with self.assertRaisesRegex(BSLError,'mutable or unsupported'):
            self.start(types={'Root':'<v8:Type>v8:FixedArray</v8:Type>'},
                body='A=New Array; A.Add(New Map); SessionParameters.State=New FixedArray(A);')

    def test_no_default_invented(self):
        with self.assertRaisesRegex(BSLError,'not set|recursive'):
            self.start(body='Message(SessionParameters.State);')

    def test_lazy_initializer_works(self):
        _, out=self.start(body='If Names=Undefined Then Message(SessionParameters.State); Else SessionParameters.State=True; EndIf;')
        self.assertEqual(out,['Да'])

    def test_unknown_and_cycle_are_named_lazy_failures(self):
        for types, reason in (({'Root':alias('Missing')},'unknown DefinedType'),
                              ({'Root':alias('Leaf'),'Leaf':alias('rOoT')},'DefinedType cycle')):
            with self.subTest(reason=reason):
                app,_=self.start(types=types)
                self.assertIn(reason,app.session_parameters._unsupported['state'])
                with self.assertRaisesRegex(BSLError,'unsupported session parameter type'):
                    self.start(types=types,body='SessionParameters.State=True;')

    def test_unused_unsupported_alias_does_not_block_valid_session(self):
        app,_=self.start(types={'Root':BOOL,'Other':alias('Missing')},body='SessionParameters.State=True;')
        self.assertIs(app.session_parameters._values['state'],True)

    def test_mixed_alias_never_drops_unknown_branch(self):
        for content in (alias('Root')+BOOL, alias('Root')+'<v8:StringQualifiers/>'):
            app,_=self.start(declaration=content)
            self.assertIn('mixed',app.session_parameters._unsupported['state'])

    def test_unsupported_leaf_does_not_grant_object_access(self):
        for content in ('<v8:Type>cfg:CatalogRef.Items</v8:Type>',
                        BOOL+'<v8:Type>v8:FutureType</v8:Type>'):
            app,_=self.start(types={'Root':content})
            self.assertIn('state',app.session_parameters._unsupported)

    def test_chain_bound_exactly_sixteen(self):
        types={'D'+str(i):alias('D'+str(i+1)) for i in range(15)}
        types['D15']=BOOL
        app,_=self.start(types=types,declaration=alias('D0'),body='SessionParameters.State=True;')
        self.assertIs(app.session_parameters._values['state'],True)
        types['D15']=alias('D16');types['D16']=BOOL
        app,_=self.start(types=types,declaration=alias('D0'))
        self.assertIn('chain exceeds 16',app.session_parameters._unsupported['state'])

    def test_qname_scope_is_resolved_at_each_declaration(self):
        files={f.path:f.content for f in configuration().files}
        files['DefinedTypes/Root.xml']=files['DefinedTypes/Root.xml'].replace(b'xmlns:cfg=',b'xmlns:other=').replace(b'cfg:DefinedType.Leaf',b'other:DefinedType.Leaf')
        defs, errors=source_session_definitions(import_source(files))
        self.assertFalse(errors);self.assertEqual(defs[0].kind,'boolean')

    def test_shared_chain_binds_catalog_and_document_field_identities(self):
        from test_source_catalog_definitions import attribute
        from test_source_document_records import package as documents
        from yadinassi.source_catalog_definitions import source_catalog_definitions
        from yadinassi.source_document_definitions import source_document_definitions
        files={f.path:f.content for f in documents(children=attribute(kind=alias('Root'))).files}
        files['Catalogs/Items.xml']=files['Catalogs/Items.xml'].replace(b'</ChildObjects>',attribute(kind=alias('Root')).encode()+b'</ChildObjects>')
        for path in ('Catalogs/Items.xml','Documents/Invoice.xml'):
            files[path]=files[path].replace(b'xmlns:xs=',b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:xs=')
        definitions={f.path:f.content for f in configuration().files}
        files['Configuration.xml']=definitions['Configuration.xml']
        for path in ('DefinedTypes/Root.xml','DefinedTypes/Leaf.xml'):
            files[path]=definitions[path]
        source=import_source(files)
        expected=tuple((str(uuid5(NAMESPACE_URL,n)),n) for n in ('Root','Leaf'))
        for parser, name in ((source_catalog_definitions,'items'),(source_document_definitions,'invoice')):
            defs,errors=parser(source)
            self.assertFalse(errors)
            field=next(f for f in defs[name].fields if f.name=='Flag')
            self.assertEqual(field.kind,'boolean')
            self.assertEqual(field.type_dependencies,expected)

    def test_client_and_foreign_family_remain_forbidden(self):
        first,_=self.start(body='SessionParameters.State=True;')
        second,_=self.start()
        second._session_owner.variables['foreign']=first.session_parameters
        with self.assertRaisesRegex(BSLError,'another or closed'):
            second._session_owner.execute('Foreign.State')
        with self.assertRaisesRegex(BSLError,'server application context'):
            first.interpreter.execute('SessionParameters.State')

if __name__ == '__main__':
    unittest.main()
