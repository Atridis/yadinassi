"""Closed source-only inventory form/report grant; not native UI parity."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
import unittest
from uuid import UUID, uuid5

from yadinassi.configuration_inventory_application import (
    PROFILE, FORMAT_VERSION, NAMESPACE, InventoryApplicationConfiguration,
    InventoryCommandGrant, InventoryReportGrant, import_inventory_application,
    canonical, validated_core)
from yadinassi.configuration_accumulation_references import (
    import_inventory_configuration, PROFILE as CORE_PROFILE)
from yadinassi.configuration_accumulation import import_accumulation_configuration
from yadinassi.configuration_xml import import_configuration
from yadinassi.configuration_forms import load_configuration_forms
from inventory_application_fixture import (source, ROOT, MANIFEST, DOC, DOC_FORM,
    DOC_MODULE, CATALOG, CATALOG_FORM)


class InventoryApplicationSourceTests(unittest.TestCase):
    def load(self, files=None):
        return import_inventory_application(source() if files is None else files, inventory_runtime=PROFILE)

    def changed(self, path, old, new):
        files=source();self.assertIn(old,files[path]);files[path]=files[path].replace(old,new);return files

    def refused(self, files):
        with self.assertRaises(ValueError):self.load(files)

    def forms(self, config):
        return load_configuration_forms(dict(config.files),catalog_schemas=config.catalogs,
            document_schemas=config.documents,reference_catalogs=config.catalogs,posting_application=True)

    def test_explicit_distinct_grant_required(self):
        for profile in (None,CORE_PROFILE,'accumulation-balance-scalar-v1','document-recorder-forms-v1',True):
            with self.subTest(profile=profile),self.assertRaises(ValueError):
                import_inventory_application(source(),inventory_runtime=profile)

    def test_full_original_source_and_digest_retained(self):
        files=source();config=self.load(files)
        self.assertIs(type(config),InventoryApplicationConfiguration)
        self.assertEqual(dict(config.files),files);self.assertEqual(config.profile,PROFILE)
        digest=sha256(b''.join(p.encode()+b'\0'+sha256(raw).digest() for p,raw in sorted(files.items()))).hexdigest()
        self.assertEqual(config.source_digest,digest)
        self.assertNotEqual(digest,config.core_projection_digest)
        self.assertEqual(FORMAT_VERSION,15)

    def test_validated_projection_preserves_exact_core_schemas_and_handler_bytes(self):
        config=self.load();core=validated_core(config)
        original=ROOT/'examples/inventory_reference/source'
        baseline=import_inventory_configuration({p.relative_to(original).as_posix():p.read_bytes()
            for p in original.rglob('*') if p.is_file()},inventory_runtime=CORE_PROFILE)
        for name in ('identity','name','catalogs','documents','registers','handlers'):
            self.assertEqual(getattr(config,name),getattr(baseline,name),name)
            self.assertEqual(getattr(core,name),getattr(config,name),name)
        self.assertEqual(core.source_digest,config.core_projection_digest)
        self.assertNotIn(MANIFEST,dict(core.files));self.assertIn(MANIFEST,dict(config.files))
        for identity,path,digest in core.handlers:
            self.assertEqual(dict(core.files)[path],dict(config.files)[path])
            self.assertEqual(sha256(dict(config.files)[path]).hexdigest(),digest)

    def test_old_core15_importer_refuses_full_forms(self):
        with self.assertRaises(ValueError):import_inventory_configuration(source(),inventory_runtime=CORE_PROFILE)

    def test_old_scalar14_importer_refuses_full_forms(self):
        with self.assertRaises(ValueError):import_accumulation_configuration(source(),accumulation_runtime='accumulation-balance-scalar-v1')

    def test_default_import_does_not_admit_new_grant(self):
        with self.assertRaises(ValueError):import_configuration(source())

    def test_canonical_is_full_exact_reimport(self):
        config=self.load();self.assertEqual(canonical(config),config)
        self.assertIsNot(canonical(config),config)

    def test_canonical_refuses_core_projection_type(self):
        with self.assertRaises(ValueError):canonical(validated_core(self.load()))

    def test_canonical_refuses_wrong_profile_or_digest(self):
        config=self.load()
        for kwargs in ({'profile':CORE_PROFILE},{'source_digest':'0'*64},{'core_projection_digest':'0'*64}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):canonical(replace(config,**kwargs))

    def test_canonical_refuses_changed_catalog_document_register_and_handler(self):
        config=self.load()
        for key in ('catalogs','documents','registers','handlers','commands','reports'):
            with self.subTest(key=key),self.assertRaises(ValueError):canonical(replace(config,**{key:()}))

    def test_canonical_refuses_duplicate_or_mutable_source_envelope(self):
        config=self.load()
        for files in (list(config.files),config.files+(config.files[0],),tuple((p,bytearray(raw)) for p,raw in config.files)):
            with self.subTest(kind=type(files)),self.assertRaises(ValueError):canonical(replace(config,files=files))

    def test_canonical_refuses_numeric_type_coercion_in_commands(self):
        config=self.load();command=config.commands[0]
        changed=replace(command,command_id=float(command.command_id))
        with self.assertRaises(ValueError):canonical(replace(config,commands=(changed,)+config.commands[1:]))

    def test_validated_core_checks_full_manifest_before_projection(self):
        config=self.load();files=dict(config.files);files[MANIFEST]=files[MANIFEST].replace(b'mode="Post"',b'mode="Write"')
        with self.assertRaises(ValueError):validated_core(replace(config,files=tuple(sorted(files.items()))))

    def test_grants_are_immutable_and_source_is_detached(self):
        files=source();config=self.load(files);files[MANIFEST]=b'changed'
        self.assertNotEqual(dict(config.files)[MANIFEST],files[MANIFEST])
        for value,field in ((config,'profile'),(config.commands[0],'mode'),(config.reports[0],'view')):
            with self.subTest(field=field),self.assertRaises(FrozenInstanceError):setattr(value,field,'changed')
        self.assertIs(type(config.commands[0]),InventoryCommandGrant)
        self.assertIs(type(config.reports[0]),InventoryReportGrant)

    def test_commands_bind_only_document_forms_exact_ids_and_modes(self):
        commands=self.load().commands
        self.assertEqual(len(commands),6)
        for form in ('Document.Receipt.Form.Card','Document.Issue.Form.Card'):
            self.assertEqual([(g.command,g.command_id,g.mode) for g in commands if g.form==form],
                [('Write',3,'Write'),('Post',4,'Post'),('UndoPosting',5,'UndoPosting')])
        self.assertTrue(all(g.form.startswith('Document.') for g in commands))

    def test_reports_bind_exact_uuid_name_and_closed_views(self):
        config=self.load();register=config.registers[0]
        self.assertEqual([(r.name,r.register,r.register_id,r.view) for r in config.reports],
            [('Stock'+view,register.name,register.identity,view) for view in ('Movements','Balance','Turnovers')]
            + [('StockStatement',register.name,register.identity,'BalanceAndTurnovers')])

    def test_missing_manifest_refused(self):
        files=source();del files[MANIFEST];self.refused(files)

    def test_missing_form_or_handler_source_refused(self):
        for path in (DOC_FORM,DOC_MODULE,'Documents/Receipt/Ext/ObjectModule.bsl'):
            with self.subTest(path=path):
                files=source();del files[path];self.refused(files)

    def test_wrong_manifest_namespace_and_version_refused(self):
        for old,new in ((b'inventory-application:1',b'inventory-application:2'),(b'version="1"',b'version="2"')):
            with self.subTest(old=old):self.refused(self.changed(MANIFEST,old,new))

    def test_unknown_manifest_attributes_nodes_and_text_refused(self):
        for old,new in ((b'version="1"',b'version="1" extra="x"'),(b'<Forms>',b'<Forms extra="x">'),
                        (b'<Reports>',b'<Reports>unexpected'),(b'</Reports>',b'<Unknown/></Reports>')):
            with self.subTest(old=old):self.refused(self.changed(MANIFEST,old,new))

    def test_manifest_container_order_and_duplicates_refused(self):
        files=source();raw=files[MANIFEST]
        start=raw.index(b'<Forms>');end=raw.index(b'</Forms>')+len(b'</Forms>')
        forms=raw[start:end];remainder=raw[end:raw.index(b'</InventoryApplication>')]
        files[MANIFEST]=raw[:start]+remainder+forms+b'</InventoryApplication>'
        self.refused(files)
        self.refused(self.changed(MANIFEST,b'</Forms>',b'</Forms><Forms/>'))

    def test_all_forms_require_manifest_binding(self):
        files=self.changed(MANIFEST,b'<CatalogForm name="Catalog.Products.Form.Card"/>',b'')
        self.refused(files)

    def test_unknown_or_case_changed_manifest_form_refused(self):
        for value in (b'Catalog.Unknown.Form.Card',b'catalog.Products.Form.Card'):
            with self.subTest(value=value):self.refused(self.changed(MANIFEST,b'Catalog.Products.Form.Card',value))

    def test_duplicate_manifest_form_refused(self):
        item=b'<CatalogForm name="Catalog.Products.Form.Card"/>'
        self.refused(self.changed(MANIFEST,item,item+item))

    def test_catalog_cannot_receive_posting_commands(self):
        self.refused(self.changed(MANIFEST,b'<CatalogForm name="Catalog.Products.Form.Card"/>',
            b'<CatalogForm name="Catalog.Products.Form.Card"><Command name="Save" id="1" mode="Write"/></CatalogForm>'))

    def test_catalog_cannot_be_declared_as_document_grant(self):
        self.refused(self.changed(MANIFEST,b'<CatalogForm name="Catalog.Products.Form.Card"/>',
            b'<DocumentForm name="Catalog.Products.Form.Card"/>'))

    def test_document_cannot_be_declared_as_catalog_grant(self):
        files=source();files[MANIFEST]=files[MANIFEST].replace(b'DocumentForm',b'CatalogForm');self.refused(files)

    def test_unknown_command_name_id_mode_and_extra_attribute_refused(self):
        for old,new in ((b'name="Post" id="4"',b'name="Other" id="4"'),(b'id="4"',b'id="99"'),
                        (b'mode="Post"',b'mode="write"'),(b'mode="Post"',b'mode="Post" sql="x"')):
            with self.subTest(old=old):self.refused(self.changed(MANIFEST,old,new))

    def test_duplicate_or_missing_modes_refused(self):
        self.refused(self.changed(MANIFEST,b'mode="Post"',b'mode="Write"'))
        self.refused(self.changed(MANIFEST,b'<Command name="Post" id="4" mode="Post"/>',b''))

    def test_nonempty_command_handler_refused(self):
        self.refused(self.changed(DOC_MODULE,b'Procedure PostCommand(Command)\n',b'Procedure PostCommand(Command)\n Message("not empty");\n'))

    def test_wrong_command_handler_arity_and_default_refused(self):
        for parameters in (b'()',b'(Command, Other)',b'(Command = Undefined)'):
            with self.subTest(parameters=parameters):
                self.refused(self.changed(DOC_MODULE,b'Procedure PostCommand(Command)',b'Procedure PostCommand'+parameters))

    def test_extra_executable_or_foreign_manifest_refused(self):
        for path in ('Ext/ManagedApplicationModule.bsl','CommonModules/Shared/Ext/Module.bsl','PostingApplication.xml'):
            with self.subTest(path=path):
                files=source();files[path]=b'// no additional grant';self.refused(files)

    def test_extra_metadata_families_refused(self):
        for kind in ('CommonForm','CommonModule','Enum','InformationRegister'):
            with self.subTest(kind=kind):self.refused(self.changed('Configuration.xml',b'</ChildObjects>',('<'+kind+'>Extra</'+kind+'></ChildObjects>').encode()))

    def test_default_forms_required_exact_and_declared(self):
        self.refused(self.changed(CATALOG,b'<DefaultObjectForm>Catalog.Products.Form.Card</DefaultObjectForm>',b''))
        self.refused(self.changed(DOC,b'Document.Receipt.Form.Card',b'Document.Issue.Form.Card'))

    def test_duplicate_form_declaration_refused(self):
        self.refused(self.changed(DOC,b'<Form>Card</Form>',b'<Form>Card</Form><Form>Card</Form>'))

    def test_unknown_owner_child_refused(self):
        self.refused(self.changed(CATALOG,b'<Form>Card</Form>',b'<Form>Card</Form><Command>Other</Command>'))

    def test_form_object_owner_type_must_match(self):
        self.refused(self.changed(DOC_FORM,b'cfg:DocumentObject.Receipt',b'cfg:DocumentObject.Issue'))

    def test_posted_is_authoritative_readonly_label(self):
        files=source();files[DOC_FORM]=files[DOC_FORM].replace(b'<LabelField name="PostedLabel"',b'<InputField name="PostedLabel"').replace(b'Object.Posted</DataPath></LabelField>',b'Object.Posted</DataPath></InputField>')
        self.refused(files)

    def test_catalog_does_not_receive_posted_or_posting_sync_projection(self):
        forms=self.forms(self.load())
        for name in ('Catalog.Products.Form.Card','Catalog.Warehouses.Form.Card'):
            form=forms.resolve(name);self.assertFalse(form.posting_application)
            self.assertNotIn('Posted',dict(form.object_fields))
            self.assertNotIn('yadinassipostingsync',{getattr(r,'name','').casefold() for r in form.program.server.program()})
        for name in ('Document.Receipt.Form.Card','Document.Issue.Form.Card'):
            form=forms.resolve(name);self.assertTrue(form.posting_application)
            self.assertIn('Posted',dict(form.object_fields))

    def test_reference_fields_and_section_targets_remain_exact(self):
        config=self.load();forms=self.forms(config)
        targets={c.name:c.identity for c in config.catalogs}
        for schema in config.documents:
            self.assertEqual(schema.fields[0].target_catalog_id,targets['Warehouses'])
            product=next(f for f in schema.tabular_sections[0].fields if f.name=='Product')
            self.assertEqual(product.target_catalog_id,targets['Products'])
            form=forms.resolve('Document.'+schema.name+'.Form.Card')
            self.assertEqual(len(form.reference_slots),2)

    def test_report_wrong_name_uuid_view_or_unknown_attributes_refused(self):
        for old,new in ((b'register="Stock"',b'register="stock"'),
                        (b'registerId="9ea1e3ef-4d1e-5933-b5ff-923cb2084491"',b'registerId="00000000-0000-0000-0000-000000000001"'),
                        (b'view="Balance"',b'view="SQL"'),(b'view="Balance"',b'view="Balance" query="SELECT"')):
            with self.subTest(old=old):self.refused(self.changed(MANIFEST,old,new))

    def test_report_names_are_bounded_identifiers(self):
        for name in (b'',b'not a name',b'x'*129):
            with self.subTest(name=name):self.refused(self.changed(MANIFEST,b'name="StockMovements"',b'name="'+name+b'"'))

    def test_duplicate_report_name_and_register_view_refused(self):
        self.refused(self.changed(MANIFEST,b'name="StockBalance"',b'name="stockmovements"'))
        self.refused(self.changed(MANIFEST,b'view="Turnovers"',b'view="Balance"'))

    def test_report_body_or_text_refused(self):
        self.refused(self.changed(MANIFEST,b'view="Balance"/>',b'view="Balance"><Query/></Report>'))
        self.refused(self.changed(MANIFEST,b'<Reports>',b'<Reports>SELECT'))

    def test_duplicate_form_uuid_with_core_field_refused(self):
        files=source();path='Catalogs/Products/Forms/Card.xml'
        from xml.etree import ElementTree as ET
        root=ET.fromstring(files[path]);old=next(iter(root)).get('uuid')
        files[path]=files[path].replace(old.encode(),b'c4fa483c-9dd8-5733-8057-4df45cc4af7e')
        self.refused(files)

    def test_generated_core_identity_cannot_be_reused_by_form(self):
        files=source();path='Catalogs/Products/Forms/Card.xml'
        from xml.etree import ElementTree as ET
        form_id=next(iter(ET.fromstring(files[path]))).get('uuid')
        entries=[]
        for index,category in enumerate(('Object','Ref','Selection','List','Manager')):
            first=form_id if index==0 else str(uuid5(UUID(form_id),'type'+category))
            second=str(uuid5(UUID(form_id),'value'+category))
            entries.append(f'<xr:GeneratedType name="Catalog{category}.Products" category="{category}"><xr:TypeId>{first}</xr:TypeId><xr:ValueId>{second}</xr:ValueId></xr:GeneratedType>')
        files[CATALOG]=files[CATALOG].replace(b'<Properties>',('<InternalInfo xmlns:xr="http://v8.1c.ru/8.3/xcf/readable">'+''.join(entries)+'</InternalInfo><Properties>').encode(),1)
        self.refused(files)

    def test_tampered_handler_digest_is_not_accepted_by_canonical(self):
        config=self.load();identity,path,digest=config.handlers[0]
        with self.assertRaises(ValueError):canonical(replace(config,handlers=((identity,path,'0'*64),)+config.handlers[1:]))

    def test_comment_only_form_change_is_still_part_of_full_binding(self):
        first=self.load();second=self.load(self.changed(DOC_MODULE,b'&AtServer',b'// retained form bytes\n&AtServer'))
        self.assertNotEqual(first.source_digest,second.source_digest)
        self.assertEqual(first.core_projection_digest,second.core_projection_digest)

    def test_no_runtime_dependency_on_demo_names(self):
        replacements=((b'Products',b'Materials'),(b'Warehouses',b'Locations'),(b'Receipt',b'Arrival'),(b'Issue',b'Dispatch'),(b'Stock',b'Inventory'))
        files={}
        for path,raw in source().items():
            for old,new in replacements:path=path.replace(old.decode(),new.decode());raw=raw.replace(old,new)
            files[path]=raw.replace(b'AccumulationRecordType.Arrival',b'AccumulationRecordType.Receipt')
        config=self.load(files)
        self.assertEqual({c.name for c in config.catalogs},{'Materials','Locations'})
        self.assertEqual({d.name for d in config.documents},{'Arrival','Dispatch'})
        self.assertEqual({r.register for r in config.reports},{'Inventory'})

    def test_old_posting13_document_only_behavior_is_unchanged(self):
        from posting_application_fixture import source as old_source
        from yadinassi.configuration_posting_application import import_posting_application, PROFILE as OLD_PROFILE
        config=import_posting_application(old_source(),posting_runtime=OLD_PROFILE)
        forms=load_configuration_forms(dict(config.files),document_schemas=config.documents,posting_application=True)
        self.assertTrue(all(d.posting_application for d in forms.forms.values()))
        self.assertEqual(len(config.commands),3)
