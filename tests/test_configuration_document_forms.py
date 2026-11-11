"""Closed document compiler and typed table projections; no native claims."""
from dataclasses import replace
from decimal import Decimal
import unittest
from uuid import uuid4
from document_form_fixture import sources
from yadinassi.configuration_document_profile import import_document_forms_configuration
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.configuration_document import DocumentImage, DocumentRowImage
from yadinassi.form_program import compile_form_module


class DocumentFormCompilerTests(unittest.TestCase):
    def definition(self,files=None):
        files=sources() if files is None else files
        imported=import_document_forms_configuration(files)
        return load_configuration_forms(files,document_schemas=imported.documents).resolve('Document.Orders.Form.Card')

    def test_profile_is_explicit_source_bound(self):
        files=sources();first=import_document_forms_configuration(files)
        self.assertEqual(len(first.activation_issues),1)
        files['Documents/Orders/Forms/Card/Ext/Form/Module.bsl']+=b'\n// changed\n'
        self.assertNotEqual(first.activation_issues,import_document_forms_configuration(files).activation_issues)

    def test_typed_header_and_section(self):
        d=self.definition();self.assertIsNone(d.catalog_schema)
        self.assertEqual(tuple(k for k,v in d.object_fields),('Number','Date','DeletionMark'))
        self.assertEqual(d.object_sections,(('Lines','ObjectField4'),))
        self.assertEqual(d.tables[0].columns[0].name,'Flag')
        server=d.create_server();self.addCleanup(server.session.interpreter.close)
        self.assertIn('linestable',server.session.form.items._values)

    def test_object_module_not_silently_skipped(self):
        files=sources();files['Documents/Orders/Ext/ObjectModule.bsl']=b'// unsupported even empty behavior'
        with self.assertRaises(ValueError):self.definition(files)

    def test_posting_rejected(self):
        files=sources();files['Documents/Orders.xml']=files['Documents/Orders.xml'].replace(b'<Posting>Deny</Posting>',b'<Posting>Allow</Posting>')
        with self.assertRaises(ValueError):self.definition(files)

    def test_wrong_owner_rejected(self):
        files=sources();p='Documents/Orders/Forms/Card/Ext/Form.xml';files[p]=files[p].replace(b'DocumentObject.Orders',b'CatalogObject.Orders')
        with self.assertRaises(ValueError):self.definition(files)

    def test_document_beforewrite_event_is_not_object_event(self):
        files=sources();p='Documents/Orders/Forms/Card/Ext/Form.xml';files[p]=files[p].replace(b'</Form>',b'<Events><Event name="BeforeWriteAtServer">SaveAtServer</Event></Events></Form>')
        with self.assertRaises(ValueError):self.definition(files)

    def test_section_method_lowering_only_declared(self):
        compile_form_module('&AtServer\nProcedure P() R=Object.Lines.Add(); R.Flag=True; EndProcedure',object_fields=('Number','Lines'),object_sections=('Lines',))
        with self.assertRaises(ValueError):compile_form_module('&AtServer\nProcedure P() Object.Number.Clear(); EndProcedure',object_fields=('Number',))
        with self.assertRaises(ValueError):compile_form_module('&AtServerNoContext\nProcedure P() Object.Lines.Add(); EndProcedure',object_fields=('Lines',),object_sections=('Lines',))

    def test_complete_projection_and_host_only_row_identity(self):
        d=self.definition();server=d.create_server();session=server.session;self.addCleanup(session.interpreter.close)
        values=tuple((f,session.form._data[s.casefold()]) for f,s in d.object_fields)
        uid=uuid4();image=DocumentImage(values,(('Lines',(DocumentRowImage(uid,(('Flag',True),)),)),))
        d._install_document_image(session,image)
        table=session.form._tables['objectfield4']
        self.assertEqual(table._snapshot().rows,((1,(True,)),))
        self.assertEqual(session._document_row_ids,{('objectfield4',1):uid})

    def test_overflow_rejected_not_truncated(self):
        d=self.definition();server=d.create_server();session=server.session;self.addCleanup(session.interpreter.close)
        values=tuple((f,session.form._data[s.casefold()]) for f,s in d.object_fields)
        image=DocumentImage(values,(('Lines',tuple(DocumentRowImage(None,(('Flag',False),)) for _ in range(33))),))
        with self.assertRaises(ValueError):d._install_document_image(session,image)
        self.assertEqual(session.form._tables['objectfield4']._snapshot().rows,())

    def test_unknown_dotted_xml_path_rejected(self):
        files=sources();p='Documents/Orders/Forms/Card/Ext/Form.xml';files[p]=files[p].replace(b'Object.Lines',b'Object.Lines.Secret')
        with self.assertRaises(ValueError):self.definition(files)

    def test_save_preflight_preserves_noninitial_row_identity_and_selection(self):
        from types import SimpleNamespace
        from yadinassi.configuration_document import DocumentSaveResult
        from test_form_tables import active
        d=self.definition();server=d.create_server();session=server.session
        self.addCleanup(session.interpreter.close)
        session.open()
        with active(session):
            table=session.form._tables['objectfield4']
            first=table.add();table.delete(first)
            second=table.add();second.set_member('Flag',True)
            session.form.items._values['linestable'].current_row=second._row_id
            def save(image,validate_result):
                # Isolate projection validation; this is not persistence evidence.
                result=DocumentSaveResult('saved',image=image)
                validate_result(result)
                return result
            owned=SimpleNamespace(pending_commit=False,pending_refresh=False,save=save)
            self.assertEqual(d._write_document(session,owned),'saved')
            self.assertEqual(table._snapshot().rows,((2,(True,)),))
            self.assertEqual(session.form.items._values['linestable'].current_row,2)
