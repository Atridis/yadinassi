"""Real document write and independent client/server table replicas."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from yadinassi.configuration_document_profile import import_document_forms_configuration
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.configuration_document import DocumentObjectSession
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.form_replication import ReplicatedFormSession

EXAMPLE=Path(__file__).resolve().parents[1]/'examples/configuration-document-forms'


class DocumentFormReplicaTests(unittest.TestCase):
    def setUp(self):
        self.files={p.relative_to(EXAMPLE).as_posix():p.read_bytes() for p in EXAMPLE.rglob('*') if p.is_file()}
        config=import_document_forms_configuration(self.files)
        self.schema=config.documents[0]
        self.definition=load_configuration_forms(self.files,document_schemas=config.documents).resolve('Document.Orders.Form.Card')
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'document.sqlite'
        SQLiteCatalogBackend.create_document_forms(self.path,self.files).close()
        self.context=SQLiteDBContext(self.path);self.addCleanup(self.context.close)

    def pair(self,key=None):
        owned=DocumentObjectSession(self.context,self.schema,self.files,key)
        server=self.definition.create_server(database_context=self.context,object_session=owned)
        self.addCleanup(server.session.interpreter.close)
        package=self.definition.client_package()
        client=ReplicatedFormSession(package.source,server.exchange,handlers=package.handlers,bindings=package.bindings)
        self.addCleanup(client.interpreter.close);client.open()
        return client,server,owned

    def command(self,client,name):
        return client.dispatch('command',revision=client.revision,control=name+'Button')

    def grid(self,client):return next(iter(client.form._tables.values()))

    def edit(self,client,row,column,value):
        return client.dispatch('cell',revision=client.revision,control='LinesTable',row=row,column=column,value=value)

    def test_add_edit_write_and_authoritative_reopen(self):
        client,server,owned=self.pair();self.command(client,'NewLine')
        self.edit(client,1,'Label','Actual row');self.edit(client,1,'Quantity',Decimal('2.50'))
        self.command(client,'Write')
        self.assertEqual(client.form._data['status'],'saved')
        self.assertFalse(client.form._data['dirty'])
        reopened,_,other=self.pair(owned.object._key)
        self.assertEqual(self.grid(reopened)._snapshot().rows,((1,('Actual row',Decimal('2.50'),False)),))
        self.assertEqual(other.image(),owned.image())
        self.assertTrue(owned.image().values[0][1])

    def test_delete_selected_write_and_nonreused_replica_identity(self):
        client,_,owned=self.pair()
        self.command(client,'NewLine');self.command(client,'NewLine')
        client.dispatch('select',revision=client.revision,control='LinesTable',row=1)
        self.command(client,'DeleteSelected');self.command(client,'Write')
        self.assertEqual(self.grid(client)._snapshot().rows[0][0],2)
        self.assertEqual(len(owned.image().sections[0][1]),1)
        self.command(client,'NewLine');self.assertEqual(self.grid(client)._snapshot().rows[-1][0],3)

    def test_other_dirty_form_not_overwritten_and_close_is_independent(self):
        first,_,_=self.pair();other,_,_=self.pair()
        self.command(other,'NewLine');self.edit(other,1,'Label','Other draft')
        self.command(first,'NewLine');self.command(first,'Write')
        first.dispatch('close',revision=first.revision)
        self.assertTrue(first.closed);self.assertFalse(other.closed)
        self.assertEqual(self.grid(other)._snapshot().rows[0][1][0],'Other draft')
        self.assertTrue(other.form._data['dirty'])

    def test_dirty_close_refused_then_write_allows_close(self):
        client,_,_=self.pair();self.command(client,'NewLine')
        client.dispatch('close',revision=client.revision);self.assertFalse(client.closed)
        self.command(client,'Write');client.dispatch('close',revision=client.revision)
        self.assertTrue(client.closed)

    def test_stale_revision_and_deleted_row_cannot_edit_another_row(self):
        client,_,_=self.pair();self.command(client,'NewLine');old=client.revision
        self.command(client,'NewLine')
        with self.assertRaises(ValueError):
            client.dispatch('cell',revision=old,control='LinesTable',row=1,column='Label',value='stale')
        client.dispatch('select',revision=client.revision,control='LinesTable',row=1)
        self.command(client,'DeleteSelected')
        with self.assertRaises(ValueError):self.edit(client,1,'Label','deleted')
        self.assertEqual(self.grid(client)._snapshot().rows[0][1][0],'New line')

    def test_deletion_mark_is_persisted_without_posting(self):
        client,_,owned=self.pair()
        client.dispatch('change',revision=client.revision,control='DeletionInput',value=True)
        self.command(client,'Write')
        self.assertTrue(dict(owned.image().values)['DeletionMark'])
        self.assertFalse(owned.object.get_member('Posted'))

    def test_reopened_rows_available_before_oncreate(self):
        client,_,owned=self.pair();self.command(client,'NewLine');self.command(client,'Write')
        reopened,server,_=self.pair(owned.object._key)
        self.assertEqual(len(self.grid(reopened)._rows),1)
        self.assertEqual(len(next(iter(server.session.form._tables.values()))._rows),1)
        self.assertFalse(reopened.form._data['dirty'])
        self.assertEqual(reopened.form._data['status'],'Rows loaded: 1')

    def test_profile_rejects_declaration_and_column_overflow(self):
        from dataclasses import replace
        from yadinassi.configuration_forms import _definition
        schema=replace(self.schema,tabular_sections=self.schema.tabular_sections*5)
        prefix='Documents/Orders/Forms/Card/Ext/Form'
        with self.assertRaises(ValueError):
            _definition('Document.Orders.Form.Card',self.definition.identity,self.files[prefix+'.xml'],self.files[prefix+'/Module.bsl'],document_schema=schema)
        section=self.schema.tabular_sections[0]
        fields=tuple(replace(section.fields[0],name='Field'+str(i)) for i in range(9))
        schema=replace(self.schema,tabular_sections=(replace(section,fields=fields),))
        with self.assertRaises(ValueError):
            _definition('Document.Orders.Form.Card',self.definition.identity,self.files[prefix+'.xml'],self.files[prefix+'/Module.bsl'],document_schema=schema)
