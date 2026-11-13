"""Application-global client exports keep owned live slots and side limits."""
import unittest
from test_configuration_source_runtime import source
from test_source_server_call import module
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


def configuration(app, helper, *, global_module=False, server=False):
    files=module('Helpers',helper,client=not server,server=server,
                 server_call=server,global_module=global_module)
    files['CommonModules/Helpers.xml']=files['CommonModules/Helpers.xml'].replace(
        b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000000002">')
    return source(app.encode(),files)


class SourceApplicationExportsTests(unittest.TestCase):
    def run_app(self, app, helper, **kwargs):
        output=[]
        instance=SourceApplication(configuration(app,helper,**kwargs),output=output.append)
        self.addCleanup(instance.close)
        instance.start()
        return instance,output

    def test_exported_function_from_client_common(self):
        _,out=self.run_app('Procedure OnStart() Message(Helpers.Run()); EndProcedure\nFunction Answer() Export Return 42; EndFunction',
                          'Function Run() Export Return Answer(); EndFunction')
        self.assertEqual(out,['42'])

    def test_private_application_routine_not_exposed(self):
        with self.assertRaises(BSLError):
            self.run_app('Procedure OnStart() Helpers.Run(); EndProcedure\nFunction Answer() Return 42; EndFunction',
                         'Procedure Run() Export Answer(); EndProcedure')

    def test_shared_scalar_assignment(self):
        _,out=self.run_app('Var Shared Export;\nProcedure OnStart() Shared=1; Helpers.Run(); Message(Shared); EndProcedure',
                          'Procedure Run() Export Shared=Shared+2; EndProcedure')
        self.assertEqual(out,['3'])

    def test_shared_collection_mutation(self):
        _,out=self.run_app('Var Shared Export;\nProcedure OnStart() Shared=New Array; Helpers.Run(); Message(Shared.Count()); EndProcedure',
                          'Procedure Run() Export Shared.Add(1); EndProcedure')
        self.assertEqual(out,['1'])

    def test_private_variable_not_exposed(self):
        with self.assertRaises(BSLError):
            self.run_app('Var Shared;\nProcedure OnStart() Shared=1; Helpers.Run(); EndProcedure',
                         'Procedure Run() Export Message(Shared); EndProcedure')

    def test_explicit_local_shadows_global(self):
        _,out=self.run_app('Var Shared Export;\nProcedure OnStart() Shared=1; Helpers.Run(); Message(Shared); EndProcedure',
                          'Procedure Run() Export Var Shared; Shared=9; Message(Shared); EndProcedure')
        self.assertEqual(out,['9','1'])

    def test_parameter_shadows_global(self):
        _,out=self.run_app('Var Shared Export;\nProcedure OnStart() Shared=1; Helpers.Run(9); Message(Shared); EndProcedure',
                          'Procedure Run(Val Shared) Export Shared=10; Message(Shared); EndProcedure')
        self.assertEqual(out,['10','1'])

    def test_byref_mutates_same_global_slot(self):
        _,out=self.run_app('Var Shared Export;\nProcedure OnStart() Shared=1; Helpers.Run(); Message(Shared); EndProcedure',
                          'Procedure Run() Export Change(Shared); EndProcedure\nProcedure Change(X) X=7; EndProcedure')
        self.assertEqual(out,['7'])

    def test_exported_procedure_byref(self):
        _,out=self.run_app('Procedure OnStart() Message(Helpers.Run()); EndProcedure\nProcedure Change(X) Export X=8; EndProcedure',
                          'Function Run() Export X=1; Change(X); Return X; EndFunction')
        self.assertEqual(out,['8'])

    def test_optional_exported_call(self):
        _,out=self.run_app('Procedure OnStart() Message(Helpers.Run()); EndProcedure\nFunction Answer(Val X=4,Val Y=5) Export Return X+Y; EndFunction',
                          'Function Run() Export Return Answer(,7); EndFunction')
        self.assertEqual(out,['11'])

    def test_module_local_routine_precedes_application(self):
        _,out=self.run_app('Procedure OnStart() Message(Helpers.Run()); EndProcedure\nFunction Answer() Export Return 42; EndFunction',
                          'Function Run() Export Return Answer(); EndFunction\nFunction Answer() Return 8; EndFunction')
        self.assertEqual(out,['8'])

    def test_server_cannot_call_application_export(self):
        with self.assertRaises(BSLError):
            self.run_app('Procedure OnStart() Helpers.Run(); EndProcedure\nFunction Answer() Export Return 42; EndFunction',
                         'Procedure Run() Export Answer(); EndProcedure',server=True)

    def test_server_cannot_read_application_variable(self):
        with self.assertRaises(BSLError):
            self.run_app('Var Shared Export;\nProcedure OnStart() Shared=42; Helpers.Run(); EndProcedure',
                         'Procedure Run() Export Message(Shared); EndProcedure',server=True)

    def test_global_common_cannot_read_application_variable(self):
        with self.assertRaises(BSLError):
            self.run_app('Var Shared Export;\nProcedure OnStart() Shared=42; Run(); EndProcedure',
                         'Procedure Run() Export Message(Shared); EndProcedure',global_module=True)

    def test_global_common_cannot_call_application_export(self):
        with self.assertRaises(BSLError):
            self.run_app('Procedure OnStart() Run(); EndProcedure\nFunction Answer() Export Return 42; EndFunction',
                         'Procedure Run() Export Answer(); EndProcedure',global_module=True)

    def test_nested_application_call_restores_active_startup_locals(self):
        _,out=self.run_app('Procedure OnStart() X=3; Helpers.Run(); Message(X); EndProcedure\nProcedure Answer() Export X=9; Message(X); EndProcedure',
                          'Procedure Run() Export Answer(); EndProcedure')
        self.assertEqual(out,['9','3'])

    def test_eval_and_execute_share_slot(self):
        _,out=self.run_app('Var Shared Export;\nProcedure OnStart() Shared=2; Helpers.Run(); Message(Shared); EndProcedure',
                          'Procedure Run() Export Execute "Shared=Shared+3;"; Message(Eval("Shared")); EndProcedure')
        self.assertEqual(out,['5','5'])

    def test_isolated_applications(self):
        code='Var Shared Export;\nProcedure OnStart() Shared=1; Helpers.Run(); Message(Shared); EndProcedure'
        helper='Procedure Run() Export Shared=Shared+1; EndProcedure'
        _,a=self.run_app(code,helper);_,b=self.run_app(code,helper)
        self.assertEqual(a,['2']);self.assertEqual(b,['2'])

    def test_retained_reference_rejects_closed_application(self):
        from yadinassi.source_application_exports import variable
        app,_=self.run_app('Var Shared Export;\nProcedure OnStart() Helpers.Run(); EndProcedure',
                          'Procedure Run() Export EndProcedure')
        child=app._instances[('helpers','client',False)]
        ref=variable(child,'Shared');app.close()
        with self.assertRaisesRegex(ValueError,'not running'):ref.get()
        with self.assertRaisesRegex(ValueError,'not running'):ref.set(1)

    def form_controller(self, app_code, form_code):
        from test_source_forms import files
        from yadinassi.configuration_source import import_source
        from yadinassi.source_forms import SourceFormController
        mapping=files(form_code.encode())
        mapping['Ext/ManagedApplicationModule.bsl']=app_code.encode()
        app=SourceApplication(import_source(mapping))
        self.addCleanup(app.close);app.start()
        return app,SourceFormController(app,'CommonForm.Main')

    def form_command(self, controller):
        from test_source_forms import request
        self.assertIsNone(controller.exchange(request())['result']['error'])
        result=controller.exchange(request('event',event='command',revision=controller.client.session.revision,control='GoButton'))['result']
        self.assertIsNone(result['error'])

    def test_form_client_calls_export_and_mutates_global(self):
        app,controller=self.form_controller('Var Shared Export;\nProcedure OnStart() Shared=1; EndProcedure\nFunction Answer() Export Return "ready"; EndFunction',
            '&AtServer\nProcedure Created(Cancel,StandardProcessing) Greeting="created"; EndProcedure\n&AtClient\nProcedure Go(Command) Shared=Shared+1; Greeting=Answer(); EndProcedure')
        self.form_command(controller)
        self.assertEqual(app.interpreter.variables['shared'],2)
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'ready')

    def test_form_attribute_shadows_export(self):
        app,controller=self.form_controller('Var Greeting Export;\nProcedure OnStart() Greeting="application"; EndProcedure',
            '&AtServer\nProcedure Created(Cancel,StandardProcessing) Greeting="form"; EndProcedure\n&AtClient\nProcedure Go(Command) Greeting=Greeting+" changed"; EndProcedure')
        self.form_command(controller)
        self.assertEqual(app.interpreter.variables['greeting'],'application')
        self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'form changed')

    def test_form_server_cannot_read_application(self):
        from test_source_forms import request
        app,controller=self.form_controller('Var Shared Export;\nProcedure OnStart() Shared="secret"; EndProcedure',
            '&AtServer\nProcedure Created(Cancel,StandardProcessing) Greeting=Shared; EndProcedure\n&AtClient\nProcedure Go(Command) EndProcedure')
        self.assertIsNotNone(controller.exchange(request())['result']['error'])

    def test_server_copyback_preserves_global_slot(self):
        from yadinassi.configuration_source import import_source
        cfg=configuration('Var Shared Export;\nProcedure OnStart() Shared=1; Helpers.Run(); Message(Shared); EndProcedure',
            'Procedure Run() Export API.Change(Shared); EndProcedure')
        files={item.path:item.content for item in cfg.files}
        extra=module('API','Procedure Change(X) Export X=7; EndProcedure')
        extra['CommonModules/API.xml']=extra['CommonModules/API.xml'].replace(b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000000003">')
        files.update(extra)
        out=[];app=SourceApplication(import_source(files),output=out.append)
        self.addCleanup(app.close);app.start()
        self.assertEqual(out,['7'])
