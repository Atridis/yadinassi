"""Exact readonly common-module metadata, not general reflection or transport."""
import contextvars
from decimal import Decimal
import threading
import unittest
from unittest.mock import patch
from contextlib import contextmanager
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.python_direct_configuration import ConfigurationBoundary
from yadinassi.python_direct_configuration_commands import _Scope
from yadinassi import python_direct_configuration_metadata as readers
from configuration_runtime_fixture import CLIENT,module_files


class DirectConfigurationMetadataTests(unittest.TestCase):
    def app(self):
        app=ConfigurationApplication.from_files(module_files([CLIENT,('Другой','Function F() Export Return 1;EndFunction',{})]),output=lambda value:None)
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    @contextmanager
    def context(self,app):
        scope=_Scope(app);scope.enter()
        try:
            context=ConfigurationBoundary(app,app.interpreter);context.enter()
            yield scope,context
        finally:scope.leave()

    def test_scalar_metadata_matches_canonical_public_objects(self):
        from yadinassi.metadata import BSLCommonModuleMetadataCollection
        app=self.app();oracle=BSLCommonModuleMetadataCollection(app.configuration.common_modules)
        self.assertEqual(app.execute('Metadata.CommonModules.Count()'),oracle.count())
        for index,definition in enumerate(app.configuration.common_modules):
            item=oracle.get(Decimal(index))
            for path in (f'Metadata.CommonModules.Get({index})',f'Metadata.CommonModules[{index}]',
                         f'Metadata.CommonModules.Find("{definition.name.upper()}")',f'Metadata.CommonModules["{definition.name}"]',
                         f'Метаданные.ОбщиеМодули.{definition.name}'):
                for name in ('Name','Global','ClientManagedApplication','Server','ServerCall','Privileged','Synonym','Comment'):
                    self.assertEqual(app.execute(path+'.'+name),item.get_member(name))
                self.assertEqual(app.execute(path+'.FullName()'),item.full_name())
        self.assertEqual(app.execute('Метаданные.ОбщиеМодули.Количество()'),Decimal(2))

    def test_only_scalar_results_can_leave_reader_graph(self):
        app=self.app()
        for text in ('M=Metadata;','M=Metadata.CommonModules;','M=Metadata.CommonModules.Tools;',
                     'Message(Metadata.CommonModules.Find("Tools"));',
                     'Tools.Double(Metadata.CommonModules.Tools);','Metadata.Catalogs.Count();',
                     'Metadata.CommonModules.Tools._definition;', 'Metadata.CommonModules.Tools.Source;',
                     'Metadata.CommonModules.Contains(Metadata.CommonModules.Tools);'):
            with self.subTest(text=text),self.assertRaises(PythonDirectUnsupported):app.execute(text)
        self.assertNotIn('m',app.interpreter.variables)

    def test_missing_names_and_bad_indices_are_ordinary_errors(self):
        app=self.app()
        for expression in ('Metadata.CommonModules["missing"].Name','Metadata.CommonModules[99].Name',
                           'Metadata.CommonModules.Find("missing").Name','Metadata.CommonModules.Get("Tools").Name',
                           'Metadata.CommonModules[-1].Name','Metadata.CommonModules[0.5].Name'):
            app.execute('Caught=False;Try X='+expression+';Except Caught=True;EndTry;')
            self.assertIs(app.interpreter.variables['caught'],True)

    def test_tokens_forged_stale_or_from_other_scope_are_not_receivers(self):
        app=self.app();other=self.app()
        with self.context(app) as (scope,context):
            token=context.external_get('Metadata')
            forged=object.__new__(readers._TOKEN_TYPE)
            with self.assertRaises(BoundaryViolation):context.get_member(forged,'CommonModules')
            collection=context.get_member(token,'CommonModules')
            count=context.resolve_member(collection,'Count')
            self.assertEqual(count(),Decimal(2))
        with self.assertRaises(BoundaryViolation):count()
        with self.context(other) as (_,context):
            with self.assertRaises(BoundaryViolation):context.get_member(token,'CommonModules')
        # Token has no source, owner or payload slots; no app retention path.
        self.assertFalse(hasattr(token,'__dict__'))
        self.assertFalse(hasattr(token,'scope'))

    def test_context_thread_and_revocation_checked_before_reads(self):
        app=self.app()
        with self.context(app) as (_,context):
            root=context.external_get('metadata');collection=context.get_member(root,'CommonModules')
            count=context.resolve_member(collection,'Count')
            for foreign in (contextvars.Context(),contextvars.copy_context()):
                with self.assertRaises(BoundaryViolation):foreign.run(count)
            errors=[]
            def worker():
                try:count()
                except BaseException as error:errors.append(type(error))
            thread=threading.Thread(target=worker);thread.start();thread.join()
            self.assertEqual(errors,[BoundaryViolation]);self.assertEqual(count(),Decimal(2))
            app.close(force=True)
            with self.assertRaises(BoundaryViolation):count()

    def test_mutated_definition_does_not_publish_stale_scalar(self):
        app=self.app();definition=app.configuration.common_modules[0]
        with self.context(app) as (_,context):
            collection=context.get_member(context.external_get('metadata'),'CommonModules')
            item=context.resolve_member(collection,'Find')('Tools')
            object.__setattr__(definition,'name','private-replacement')
            try:
                with self.assertRaises(BoundaryViolation):context.get_member(item,'Name')
            finally:object.__setattr__(definition,'name','Tools')

    def test_no_receiver_hooks_or_public_type_rebinding(self):
        app=self.app();events=[]
        class Host:
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
        with self.context(app) as (scope,context):
            with self.assertRaises(BoundaryViolation):scope.metadata.record(context,Host())
            with patch.object(readers,'_Reader',Host):
                token=context.external_get('metadata')
                self.assertTrue(readers.is_reader(token))
            collection=context.get_member(token,'CommonModules')
            with patch.object(readers._TOKEN_TYPE,'__getattribute__',lambda *a:events.append('attribute')):
                self.assertEqual(context.resolve_member(collection,'Count')(),Decimal(2))
        self.assertEqual(events,[])

    def test_definition_descriptor_override_and_forged_definition_fail_closed(self):
        from yadinassi.configuration_modules import CommonModuleDefinition
        app=self.app();events=[]
        with patch.object(CommonModuleDefinition,'__getattribute__',lambda *a:events.append('attribute')):
            with self.assertRaises(BoundaryViolation):app.execute('Metadata.CommonModules.Count();')
        self.assertEqual(events,[])
        with self.context(app) as (scope,context):
            token=context.external_get('metadata')
            original=app.configuration.common_modules
            object.__setattr__(app.configuration,'common_modules',tuple(reversed(original)))
            try:
                with self.assertRaises(BoundaryViolation):context.get_member(token,'CommonModules')
            finally:object.__setattr__(app.configuration,'common_modules',original)

    def test_reader_truth_and_comparison_hooks_never_run(self):
        app=self.app();events=[]
        def forbidden(*args):events.append('hook');raise AssertionError('token hook')
        with patch.object(readers._TOKEN_TYPE,'__bool__',forbidden,create=True),patch.object(readers._TOKEN_TYPE,'__eq__',forbidden):
            self.assertEqual(app.execute('Metadata.CommonModules.Find("Tools").Name'),'Tools')
            app.execute('Try X=Metadata.CommonModules.Find("missing").Name;Except X="missing";EndTry;')
        self.assertEqual(events,[]);self.assertEqual(app.interpreter.variables['x'],'missing')

    def test_readonly_and_private_branches_reject_before_effects(self):
        from yadinassi.errors import BSLError
        app=self.app();seen=[];app.interpreter.output=seen.append
        for text in ('Message("before"); Metadata.CommonModules.Tools.Name="changed";',
                     'Message("before"); Try X=1; Except X=Metadata.CommonModules.Tools.Source; EndTry;'):
            with self.subTest(text=text),self.assertRaises((BSLError,PythonDirectUnsupported)):
                app.execute(text)
        self.assertEqual(seen,[])
        self.assertEqual(app.execute('Metadata.CommonModules.Tools.Name'),'Tools')

    def test_admission_descriptor_override_never_runs_host_hook(self):
        from yadinassi.configuration_modules import CommonModuleDefinition
        app=self.app();seen=[]
        def forbidden(value):seen.append('hook');raise AssertionError('host property')
        original=vars(CommonModuleDefinition)['return_values_reuse']
        with patch.object(CommonModuleDefinition,'return_values_reuse',property(forbidden)):
            with self.assertRaises(BoundaryViolation):app.execute('Metadata.CommonModules.Count();')
        def output(value):
            setattr(CommonModuleDefinition,'return_values_reuse',property(forbidden))
        app.interpreter.output=output
        try:
            with self.assertRaises(BoundaryViolation):
                app.execute('Message("mutate"); X=Metadata.CommonModules.Tools.Name;')
        finally:setattr(CommonModuleDefinition,'return_values_reuse',original)
        self.assertEqual(seen,[])
