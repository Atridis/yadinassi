"""Explicit additive source update preserves values atomically; never executes BSL."""
from contextlib import closing, redirect_stdout, redirect_stderr
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_source_storage_values import package, UUID
from test_source_session_parameters import declaration
from yadinassi.configuration_source import import_source, source_digest, save_source_archive
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.value_storage import BSLValueStorage
from yadinassi.cli import main


def changed(source, replacements=None, remove=()):
    files={item.path:item.content for item in source.files if item.path not in remove}
    files.update(replacements or {})
    return import_source(files)


def add_constant(source,name='NewFlag',kind='xs:boolean'):
    xml=declaration(name,'<v8:Type>'+kind+'</v8:Type>').replace(b'SessionParameter',b'Constant')
    config=next(item.content for item in source.files if item.path=='Configuration.xml')
    config=config.replace(b'</ChildObjects>',('<Constant>'+name+'</Constant></ChildObjects>').encode())
    return changed(source,{'Configuration.xml':config,'Constants/'+name+'.xml':xml})


class SourceScratchUpdateTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/'scratch.sqlite';self.source=package()

    def create(self):
        with closing(SourceConstantStore.create(self.path,self.source)) as store:
            store.set('Flag',True);store.set('Text','saved');store.set('Identifier',BSLUUID(UUID));store.set('Storage',BSLValueStorage('settings'))

    def reopened(self,source):
        store=SourceConstantStore.reopen(self.path,source);self.addCleanup(store.close);return store

    def new_source(self):
        return changed(self.source,{'Ext/SessionModule.bsl':b'not valid BSL: should not execute or compile during source update!'})

    def test_bsl_change_preserves_all_values_and_new_source(self):
        self.create();new=self.new_source();result=SourceConstantStore.update_source(self.path,new)
        self.assertEqual(result['preserved_values'],4);self.assertEqual(result['added_constants'],0)
        store=self.reopened(new)
        self.assertTrue(store.get('Flag'));self.assertEqual(store.get('Text'),'saved')
        self.assertEqual(store.get('Identifier').text,UUID);self.assertEqual(store.get('Storage').get(),'settings')
        self.assertEqual(SourceConstantStore.load_source(self.path),new)

    def test_old_source_binding_no_longer_opens(self):
        self.create();SourceConstantStore.update_source(self.path,self.new_source())
        with self.assertRaisesRegex(ValueError,'binding'):SourceConstantStore.reopen(self.path,self.source)

    def test_additive_constant_is_uninitialized_not_guessed(self):
        self.create();new=add_constant(self.source)
        result=SourceConstantStore.update_source(self.path,new)
        self.assertEqual(result['added_constants'],1);store=self.reopened(new)
        self.assertTrue(store.get('Flag'))
        with self.assertRaisesRegex(ValueError,'uninitialized'):store.get('NewFlag')
        store.set('NewFlag',False);self.assertFalse(store.get('NewFlag'))

    def test_new_known_measured_string_default_only(self):
        self.create();new=add_constant(self.source,'NewText')
        # Build exact one-type declaration, not a composite envelope.
        xml=declaration('NewText','<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>64</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>').replace(b'SessionParameter',b'Constant')
        new=changed(new,{'Constants/NewText.xml':xml});SourceConstantStore.update_source(self.path,new)
        self.assertEqual(self.reopened(new).get('NewText'),'')

    def test_add_unsupported_declaration_does_not_activate_service(self):
        self.create();new=add_constant(self.source,'NewUnsupported','v8:AnyRef');SourceConstantStore.update_source(self.path,new)
        with self.assertRaisesRegex(ValueError,'unsupported'):self.reopened(new).get('NewUnsupported')

    def test_remove_constant_refused_even_without_value(self):
        self.create();files={x.path:x.content for x in self.source.files};files['Configuration.xml']=files['Configuration.xml'].replace(b'<Constant>Date</Constant>',b'');del files['Constants/Date.xml'];new=import_source(files)
        with self.assertRaisesRegex(ValueError,'remove'):SourceConstantStore.update_source(self.path,new)
        self.assertEqual(self.reopened(self.source).get('Text'),'saved')

    def test_type_change_refused_preserves_values(self):
        self.create();xml=declaration('Flag','<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>6</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>').replace(b'SessionParameter',b'Constant')
        with self.assertRaisesRegex(ValueError,'type/qualifier'):SourceConstantStore.update_source(self.path,changed(self.source,{'Constants/Flag.xml':xml}))
        self.assertTrue(self.reopened(self.source).get('Flag'))

    def test_qualifier_widening_is_also_refused(self):
        self.create();xml=next(x.content for x in self.source.files if x.path=='Constants/Text.xml').replace(b'<v8:Length>16</v8:Length>',b'<v8:Length>32</v8:Length>')
        with self.assertRaisesRegex(ValueError,'type/qualifier'):SourceConstantStore.update_source(self.path,changed(self.source,{'Constants/Text.xml':xml}))

    def test_constant_identity_replacement_refused(self):
        self.create();xml=next(x.content for x in self.source.files if x.path=='Constants/Flag.xml');import re
        xml=re.sub(b'uuid="[^"]+"',b'uuid="11111111-2222-3333-4444-555555555555"',xml,count=1)
        with self.assertRaisesRegex(ValueError,'replace'):SourceConstantStore.update_source(self.path,changed(self.source,{'Constants/Flag.xml':xml}))

    def test_configuration_identity_refused(self):
        self.create();config=next(x.content for x in self.source.files if x.path=='Configuration.xml');import re
        config=re.sub(b'uuid="[^"]+"',b'uuid="11111111-2222-3333-4444-555555555555"',config,count=1)
        with self.assertRaisesRegex(ValueError,'configuration identity'):SourceConstantStore.update_source(self.path,changed(self.source,{'Configuration.xml':config}))

    def test_unsupported_existing_declaration_change_refused(self):
        self.create();xml=next(x.content for x in self.source.files if x.path=='Constants/Unsupported.xml').replace(b'<Comment/>',b'<Comment>change</Comment>')
        with self.assertRaisesRegex(ValueError,'unsupported constant declaration'):SourceConstantStore.update_source(self.path,changed(self.source,{'Constants/Unsupported.xml':xml}))

    def test_policy_changes_preserve_value_but_restrict_new_writes(self):
        self.create();xml=next(x.content for x in self.source.files if x.path=='Constants/Text.xml').replace(b'<DataHistory>DontUse</DataHistory>',b'<DataHistory>Use</DataHistory>');new=changed(self.source,{'Constants/Text.xml':xml})
        SourceConstantStore.update_source(self.path,new);store=self.reopened(new);self.assertEqual(store.get('Text'),'saved')
        with self.assertRaisesRegex(ValueError,'history'):store.set('Text','new')

    def test_injected_failure_after_replacement_rolls_back_source_and_values(self):
        self.create();new=add_constant(self.new_source())
        import yadinassi.source_constant_store as module
        original=module._verify_source
        def verify(connection,source):
            if source_digest(source)==source_digest(new):raise ValueError('injected final verification failure')
            return original(connection,source)
        with patch.object(module,'_verify_source',side_effect=verify):
            with self.assertRaisesRegex(ValueError,'injected'):SourceConstantStore.update_source(self.path,new)
        self.assertEqual(SourceConstantStore.load_source(self.path),self.source)
        self.assertEqual(self.reopened(self.source).get('Storage').get(),'settings')

    def test_foreign_database_untouched(self):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('CREATE TABLE user_data(v TEXT)')
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,self.new_source())
        self.assertEqual(before,self.path.read_bytes())

    def test_missing_database_not_created(self):
        with self.assertRaises(OSError):SourceConstantStore.update_source(self.path,self.new_source())
        self.assertFalse(self.path.exists())

    def test_corrupt_existing_value_refused_before_update(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE constant_value SET value_json='bad'")
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,self.new_source())
        self.assertEqual(before,self.path.read_bytes())

    def test_sidecar_refused_without_recovery(self):
        self.create();journal=Path(str(self.path)+'-journal');journal.write_bytes(b'owner journal');before=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'clean-close'):SourceConstantStore.update_source(self.path,self.new_source())
        self.assertEqual(before,self.path.read_bytes());self.assertEqual(journal.read_bytes(),b'owner journal')

    def test_open_old_handle_retires_after_update(self):
        self.create();old=self.reopened(self.source);SourceConstantStore.update_source(self.path,self.new_source())
        with self.assertRaisesRegex(ValueError,'binding'):old.get('Text')

    def test_cli_update_no_startup_or_code_execution(self):
        self.create();archive=self.path.with_suffix('.zip');save_source_archive(archive,self.new_source());out=io.StringIO()
        with patch('yadinassi.configuration_source_runtime.SourceApplication.start',side_effect=AssertionError('never execute')),redirect_stdout(out):
            self.assertEqual(main(['--configuration-source',str(archive),'--update-source-scratch-db',str(self.path)]),0)
        self.assertIn('Код не запускался',out.getvalue());self.assertEqual(self.reopened(self.new_source()).get('Text'),'saved')

    def test_cli_requires_new_source_and_separate_execution(self):
        for args in (['--update-source-scratch-db',str(self.path)],['--configuration-source','unused','--update-source-scratch-db',str(self.path),'--run-startup'],['--configuration-source','unused','--update-source-scratch-db',str(self.path),'--save-source','unused.zip']):
            with self.subTest(args=args),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(args)

    def test_update_does_not_create_temporary_user_files(self):
        self.create();SourceConstantStore.update_source(self.path,self.new_source())
        self.assertEqual([x.name for x in self.path.parent.iterdir()],['scratch.sqlite'])

    def test_repeated_compatible_update_preserves_values(self):
        self.create();first=self.new_source();second=changed(first,{'Resources/data.bin':b'new bytes'})
        SourceConstantStore.update_source(self.path,first);SourceConstantStore.update_source(self.path,second)
        self.assertEqual(self.reopened(second).get('Text'),'saved')

    def test_intervening_valid_write_is_preserved_under_reservation(self):
        self.create();new=self.new_source();original=SourceConstantStore.reopen
        def reopen(path,source):
            result=original(path,source)
            with closing(sqlite3.connect(path)) as db,db:
                db.execute("UPDATE constant_value SET value_json=? WHERE identity=(SELECT identity FROM constant_schema WHERE name='Text')",('["string","latest"]',))
            return result
        with patch.object(SourceConstantStore,'reopen',side_effect=reopen):
            SourceConstantStore.update_source(self.path,new)
        self.assertEqual(self.reopened(new).get('Text'),'latest')

    def test_intervening_corruption_refuses_source_replacement(self):
        self.create();new=self.new_source();original=SourceConstantStore.reopen
        def reopen(path,source):
            result=original(path,source)
            with closing(sqlite3.connect(path)) as db,db:db.execute("UPDATE constant_value SET value_json='bad'")
            return result
        with patch.object(SourceConstantStore,'reopen',side_effect=reopen):
            with self.assertRaisesRegex(ValueError,'integrity'):SourceConstantStore.update_source(self.path,new)
        self.assertEqual(SourceConstantStore.load_source(self.path),self.source)
