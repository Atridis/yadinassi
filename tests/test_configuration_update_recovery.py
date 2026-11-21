"""Mixed-source profile and maintenance recovery, using disposable owned SQLite."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi.db.catalog.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
from yadinassi.db.document.document_backend import DocumentDraft, DocumentKey
from yadinassi.db.registers.register_backend import RegisterDraft, RegisterKey, RegisterSetDraft
from yadinassi.db.transaction_backend import TransactionRequest
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.db.sqlite.sqlite_migration_plan import prepare as prepare_profile, apply as apply_profile
from yadinassi.db.sqlite.sqlite_configuration_update import prepare, apply, resolve
from test_configuration_evolution import append_field
from test_periodic_information_registers import periodic_files
from test_document_configuration_xml import document_files
from test_catalog_commit_cleanup_recovery import FaultConnection
from configuration_runtime_fixture import module_files, CLIENT


def mixed_files():
    files=periodic_files()
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Document>Orders</Document><CommonModule>Tools</CommonModule></ChildObjects>')
    files['Documents/Orders.xml']=document_files(fields=False,auto='false')['Documents/Orders.xml']
    files.update({p:v for p,v in module_files([CLIENT]).items() if p.startswith('CommonModules/')})
    files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(b'<Hierarchical>false</Hierarchical>',b'<Hierarchical>true</Hierarchical><HierarchyType>HierarchyFoldersAndItems</HierarchyType>')
    return files


class ConfigurationUpdateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'mixed.sqlite';self.files=mixed_files()
        self.source=import_configuration(self.files,numbering_policy='decimal_v1',module_runtime=MODULE_RUNTIME)
        self.target=import_configuration(append_field(self.files),numbering_policy='decimal_v1',module_runtime=MODULE_RUNTIME)
        backend=SQLiteCatalogBackend.create(self.path,self.source);backend.close()
        apply_profile(self.path,prepare_profile(self.path,maintenance=True),maintenance=True)
        self.backend=SQLiteCatalogBackend(self.path);self.addCleanup(lambda:self.backend.close())

    def cat(self,code='cat'):
        return CatalogDraft(CatalogKey(self.backend.database_id,self.source.catalogs[0].identity,uuid4()),code,'',False,())

    def doc(self,number='doc'):
        return DocumentDraft(DocumentKey(self.backend.database_id,self.source.documents[0].identity,uuid4()),number,datetime(2026,1,1),False,())

    def reg(self,item='old'):
        return RegisterDraft(RegisterKey(self.backend.database_id,self.source.information_registers[0].identity,(datetime(2026,1,1),item,'region')),(Decimal('2.50'),True))

    def evolve(self):
        self.backend.close();plan=prepare(self.path,self.target,maintenance=True)
        apply(self.path,plan,maintenance=True);self.backend=SQLiteCatalogBackend(self.path)
        return plan

    def assert_document(self,draft,revision):
        with closing(self.backend.begin_document_read()) as reader:
            record=reader.read_document(draft.key)
        self.assertEqual((record.number,record.date,record.values),
                         (draft.number,draft.date,draft.values))
        self.assertEqual(record.revision.token,revision.token)
        self.assertEqual(record.revision.configuration_generation,2)

    def assert_register(self,draft,revision):
        with closing(self.backend.begin_register_read()) as reader:
            record=reader.read_record(draft.key)
        self.assertEqual(record.values,draft.values)
        self.assertEqual(record.revision.token,revision.token)
        self.assertEqual(record.revision.configuration_generation,2)

    def assert_catalog(self,draft,revision,values):
        with closing(self.backend.begin_read()) as reader:
            record=reader.read_catalog(draft.key)
        self.assertEqual((record.code,record.values),(draft.code,values))
        self.assertEqual(record.revision.token,revision.token)
        self.assertEqual(record.revision.configuration_generation,2)

    def test_document_data_survives_generation_change(self):
        draft=self.doc()
        with closing(self.backend.begin_document_write(uuid4())) as view:
            view.create(draft);outcome=view.commit()
        self.evolve()
        self.assertEqual(outcome.revision.configuration_generation,1)
        self.assert_document(draft,outcome.revision)

    def test_register_data_survives_generation_change(self):
        draft=self.reg()
        with closing(self.backend.begin_register_write(uuid4())) as view:
            view.write(draft);outcome=view.commit()
        self.evolve()
        self.assert_register(draft,outcome.revision)

    def test_register_set_survives_generation_change(self):
        schema=self.source.information_registers[0]
        with closing(self.backend.begin_register_read()) as view:
            _,snapshot=view.read_set(schema.identity)
        draft=self.reg()
        request=RegisterSetDraft(schema.identity,(),(draft,),True,snapshot)
        with closing(self.backend.begin_register_write(uuid4())) as view:
            view.write_set(request);view.commit()
        self.evolve()
        with closing(self.backend.begin_register_read()) as view:
            rows,_=view.read_set(schema.identity)
        self.assertEqual([(record.key,record.values) for record in rows],[(draft.key,draft.values)])
        self.assertEqual(rows[0].revision.configuration_generation,2)

    def test_mixed_unit_records_survive_generation_change(self):
        catalog,document,register=self.cat(),self.doc(),self.reg()
        requests=(TransactionRequest('catalog_create',catalog),TransactionRequest('document_create',document),TransactionRequest('register_write',register))
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            for request in requests:tx.stage(request)
            outcomes=tx.commit()
        self.assertTrue(all(x.result.revision.configuration_generation==1 for x in outcomes))
        self.evolve()
        self.assert_catalog(catalog,outcomes[0].result.revision,(False,))
        self.assert_document(document,outcomes[1].result.revision)
        self.assert_register(register,outcomes[2].result.revision)

    def test_new_mixed_unit_uses_only_current_generation(self):
        self.evolve()
        catalog,document,register=replace(self.cat(),values=(True,)),self.doc(),self.reg()
        requests=(TransactionRequest('catalog_create',catalog),TransactionRequest('document_create',document),TransactionRequest('register_write',register))
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            for request in requests:tx.stage(request)
            result=tx.commit()
        self.assertTrue(all(x.result.revision.configuration_generation==2 for x in result))
        self.assert_catalog(catalog,result[0].result.revision,(True,))
        self.assert_document(document,result[1].result.revision)
        self.assert_register(register,result[2].result.revision)

    def test_profile_sources_mappings_and_unchanged_tables_preserved(self):
        self.assertEqual(self.backend.storage_version,10)
        old_tables=dict(self.backend._layout._tables);old_fields=dict(self.backend._layout._fields)
        old_documents=self.backend._document_schemas;old_registers=self.backend._register_schemas
        unchanged=('document_schema','information_register_schema','catalog_hierarchy','transaction_profile','transaction_migration')
        with closing(self.backend._connect()) as db:
            rows={n:db.execute('SELECT * FROM '+n).fetchall() for n in unchanged}
        self.evolve()
        self.assertEqual(self.backend.storage_version,10)
        self.assertEqual(self.backend._document_schemas,old_documents);self.assertEqual(self.backend._register_schemas,old_registers)
        self.assertEqual(self.backend._layout._tables,old_tables)
        self.assertTrue(old_fields.items()<=self.backend._layout._fields.items())
        for p,v in self.files.items():
            if p!='Catalogs/Categories.xml':self.assertEqual(self.backend.export_configuration()[p],v)
        with closing(self.backend._connect()) as db:
            for n in unchanged:self.assertEqual(db.execute('SELECT * FROM '+n).fetchall(),rows[n])

    def test_lost_commit_acknowledgement_resolves_without_replay(self):
        self.backend.close();plan=prepare(self.path,self.target,maintenance=True)
        import yadinassi.db.sqlite.sqlite_migration_plan as migration
        original=migration._open
        def faulty(path,*,readonly):
            connection=original(path,readonly=readonly)
            return connection if readonly else FaultConnection(connection,commit_fault='after')
        with patch.object(migration,'_open',side_effect=faulty),self.assertRaisesRegex(BackendError,'uncertain_commit'):
            apply(self.path,plan,maintenance=True)
        for _ in range(2):self.assertEqual(resolve(self.path,plan,maintenance=True),'committed')

    def test_commit_failure_before_effect_resolves_not_committed(self):
        self.backend.close();plan=prepare(self.path,self.target,maintenance=True);before=self.path.read_bytes()
        import yadinassi.db.sqlite.sqlite_migration_plan as migration
        original=migration._open
        with patch.object(migration,'_open',side_effect=lambda p,readonly:original(p,readonly=True) if readonly else FaultConnection(original(p,readonly=False),commit_fault='before')):
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):apply(self.path,plan,maintenance=True)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'not_committed')
        self.assertEqual(self.path.read_bytes(),before)

    def test_changed_source_rejected_before_mutation(self):
        self.backend.close();plan=prepare(self.path,self.target,maintenance=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE configuration_file SET content=? WHERE path='Catalogs/Products/Ext/ObjectModule.bsl'",(b'// altered',));db.commit()
        before=self.path.read_bytes()
        with self.assertRaises(BackendError):apply(self.path,plan,maintenance=True)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'uncertain')

    def test_history_tampering_refuses_admission(self):
        self.evolve();self.backend.close()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE configuration_update SET source_generation=target_generation");db.commit()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)

    def test_target_digest_tampering_refuses_admission(self):
        self.evolve();self.backend.close()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE configuration_update SET target_hash=?",('0'*64,))
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)

    def test_retained_plan_roundtrip_resolves_after_reopen(self):
        from yadinassi.db.sqlite.sqlite_configuration_update import dump_plan,load_plan
        self.backend.close();plan=prepare(self.path,self.target,maintenance=True)
        persisted=dump_plan(plan);self.assertEqual(load_plan(persisted),plan)
        apply(self.path,load_plan(persisted),maintenance=True)
        self.assertEqual(resolve(self.path,load_plan(persisted),maintenance=True),'committed')

    def test_retained_plan_rejects_changed_source_and_diff(self):
        import json
        from yadinassi.db.sqlite.sqlite_configuration_update import dump_plan,load_plan
        self.backend.close();plan=prepare(self.path,self.target,maintenance=True)
        raw=dump_plan(plan)
        for key,value in (('source_hash','0'*64),('source_generation',True),('added_catalogs',[str(uuid4())]),('table_mapping',[])):
            altered=json.loads(raw);altered[key]=value
            with self.subTest(key=key),self.assertRaises(BackendError):load_plan(json.dumps(altered))
        with self.assertRaises(BackendError):load_plan(raw[:-1]+',"schema":"configuration_update_plan_v1"}')

    def test_backfill_target_budget_failure_rolls_back_before_commit(self):
        # Small patched bound retains realistic old source admission while the
        # DateTime defaults push the target source over its scalar scan budget.
        for i in range(100):
            view=self.backend.begin_write(uuid4());view.create(self.cat(str(i)));view.commit()
        self.backend.close()
        files=dict(self.files)
        field=('<Attribute uuid="'+str(uuid4())+'"><Properties><Name>ExtraDate</Name><Type>'
               '<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>'
               '</Type></Properties></Attribute>').encode()
        files['Catalogs/Categories.xml']=files['Catalogs/Categories.xml'].replace(b'</ChildObjects>',field+b'</ChildObjects>')
        target=import_configuration(files,numbering_policy='decimal_v1',module_runtime=MODULE_RUNTIME)
        with patch('yadinassi.db.sqlite.sqlite_catalog._MAX_CONFIG_BYTES',8000):
            plan=prepare(self.path,target,maintenance=True);before=self.path.read_bytes()
            with self.assertRaisesRegex(BackendError,'unsupported'):apply(self.path,plan,maintenance=True)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'not_committed')

    def test_writer_page_cap_refuses_before_commit(self):
        self.backend.close();plan=prepare(self.path,self.target,maintenance=True);before=self.path.read_bytes()
        with patch('yadinassi.db.sqlite.sqlite_catalog._MAX_DATABASE_BYTES',len(before)):
            with self.assertRaises(BackendError):apply(self.path,plan,maintenance=True)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'not_committed')

    def test_retained_base_profile_matrix(self):
        from sqlite_catalog_fixture import configuration_files
        from catalog_sections_fixture import configuration_files_with_sections
        from test_configuration_numbering_import import numbered_files
        from test_information_registers import register_files
        from test_catalog_hierarchy import hierarchy_files
        factories=((2,configuration_files),(3,configuration_files_with_sections),(4,numbered_files),
                   (7,lambda:document_files(fields=False)),(8,register_files),(9,periodic_files),(10,hierarchy_files))
        for expected,factory in factories:
            with self.subTest(profile=expected):
                path=Path(self.temp.name)/('profile'+str(expected)+'.sqlite');files=factory()
                config=import_configuration(files,numbering_policy='decimal_v1')
                backend=SQLiteCatalogBackend.create(path,config);backend.close()
                apply_profile(path,prepare_profile(path,maintenance=True),maintenance=True)
                target=import_configuration(append_field(files),numbering_policy='decimal_v1')
                plan=prepare(path,target,maintenance=True);apply(path,plan,maintenance=True)
                backend=SQLiteCatalogBackend(path)
                try:self.assertEqual((backend.format_version,backend.storage_version),(12,expected))
                finally:backend.close()

    def test_new_catalog_is_immediately_readable_and_writable(self):
        files=dict(self.files);old=self.source.catalogs[0]
        identity=uuid4()
        files['Catalogs/Extra.xml']=files['Catalogs/Categories.xml'].replace(str(old.identity).encode(),str(identity).encode()).replace(b'Categories',b'Extra')
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Catalog>Extra</Catalog></ChildObjects>')
        target=import_configuration(files,numbering_policy='decimal_v1',module_runtime=MODULE_RUNTIME)
        self.backend.close();plan=prepare(self.path,target,maintenance=True);apply(self.path,plan,maintenance=True)
        self.backend=SQLiteCatalogBackend(self.path)
        draft=CatalogDraft(CatalogKey(self.backend.database_id,identity,uuid4()),'new','',False,())
        tx=self.backend.begin_write(uuid4());tx.create(draft);tx.commit()
        view=self.backend.begin_read()
        try:self.assertEqual(view.read_catalog(draft.key).code,'new')
        finally:view.close()
