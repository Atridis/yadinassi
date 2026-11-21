"""Source session scalar reads preserve laziness, actual caller and revocation."""
import unittest
from unittest.mock import patch
import test_python_direct_source_query as fixtures
from test_source_session_parameters import package
from yadinassi.configuration.configuration_source_runtime import SourceApplication,_SourceInterpreter
from yadinassi.runtime import Interpreter
from yadinassi.execution.direct.source import python_direct_source_sessions as bridge
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.errors import BSLError


class DirectSourceSessionSecurity(unittest.TestCase):
    boundary=fixtures.DirectSourceQueryTests.boundary

    def setUp(self):
        for name in ('_execute_program','call_routine'):
            poison=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            poison.start();self.addCleanup(poison.stop)

    def app(self,body=''):
        out=[];app=SourceApplication(package(body,kind='xs:boolean'),output=out.append)
        self.addCleanup(app.close)
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('VM program')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM routine')):
            app.start()
        caller=_SourceInterpreter(app,family_owner=app.interpreter);self.addCleanup(caller.close)
        caller._logical_side='server';caller._context_stack.append('server');self.addCleanup(caller._context_stack.pop)
        return app,caller,out

    def test_boolean_dot_index_and_lazy_initializer_without_vm(self):
        app,caller,out=self.app('If Names<>Undefined Then SessionParameters.State=True; EndIf;')
        with self.boundary(app,caller) as boundary:
            store=bridge.namespace(boundary,'sessionparameters')
            self.assertIs(bridge.get(boundary,store,'State'),True)
            bridge.resolve(boundary,store,'__setitem__')('State',False)
            self.assertIs(bridge.resolve(boundary,store,'__getitem__')('State'),False)

    def test_typed_property_byref_uses_canonical_writer(self):
        from yadinassi.configuration.configuration_source import import_source
        files={item.path:item.content for item in package('',kind='xs:boolean').files}
        files['Ext/SessionModule.bsl']=b'Procedure Change(V) V=False; EndProcedure Procedure SessionParametersSetting(Names) SessionParameters.State=True; Change(SessionParameters.State); Message(SessionParameters.State); EndProcedure'
        out=[];app=SourceApplication(import_source(files),output=out.append);self.addCleanup(app.close)
        app.start();self.assertEqual(out,['Нет'])

    def test_lazy_recursion_preserves_canonical_error(self):
        with self.assertRaisesRegex(BSLError,'recursive session parameter'):
            self.app('Message(SessionParameters.State);')

    def test_foreign_store_rejected_before_authorization_callback(self):
        app,caller,_=self.app();other,_,_=self.app()
        with self.boundary(app,caller) as boundary,patch.object(other.session_parameters,'_authorize',side_effect=AssertionError('foreign callback')):
            with self.assertRaises(BoundaryViolation):bridge.get(boundary,other.session_parameters,'State')

    def test_zero_parameter_lazy_handler_on_actual_server_context(self):
        from yadinassi.configuration.configuration_source import import_source
        from yadinassi.application.session_parameters import _UNSET
        config=package('',kind='xs:boolean')
        files={item.path:item.content for item in config.files}
        files['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting() SessionParameters.State=True; EndProcedure'
        app=SourceApplication(import_source(files));self.addCleanup(app.close)
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('VM program')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM routine')):
            app.start()
        caller=app._session_owner;caller._context_stack.append('server');self.addCleanup(caller._context_stack.pop)
        app.session_parameters._values['state']=_UNSET
        with self.boundary(app,caller) as boundary:
            self.assertIs(bridge.get(boundary,app.session_parameters,'State'),True)

    def test_class_hook_replacement_refused_before_callback(self):
        from yadinassi.application.session_parameters import BSLSessionParameters
        app,caller,_=self.app();effects=[]
        for method in ('read','_authorize'):
            with self.subTest(method=method),self.boundary(app,caller) as boundary:
                with patch.object(BSLSessionParameters,method,lambda *args:effects.append('callback')):
                    with self.assertRaises(BoundaryViolation):bridge.get(boundary,app.session_parameters,'State')
        self.assertEqual(effects,[])

    def test_initializer_hook_replacement_rejected_before_callback(self):
        app,caller,_=self.app();effects=[]
        with self.boundary(app,caller) as boundary:
            with patch.object(app,'initialize_session_parameters',lambda *args:effects.append('callback')):
                with self.assertRaises(BoundaryViolation):bridge.get(boundary,app.session_parameters,'State')
            with patch.object(SourceApplication,'initialize_session_parameters',lambda *args:effects.append('callback')):
                with self.assertRaises(BoundaryViolation):bridge.get(boundary,app.session_parameters,'State')
        self.assertEqual(effects,[])

    def test_index_call_contract_rejected_before_write(self):
        app,caller,_=self.app()
        with self.boundary(app,caller) as boundary:
            store=app.session_parameters
            with self.assertRaises(TypeError):bridge.resolve(boundary,store,'__getitem__',argument_count=2)
            with self.assertRaises(TypeError):bridge.resolve(boundary,store,'__setitem__',require_value=True,argument_count=2)
            bridge.set_member(boundary,store,'State')(False)
            self.assertIs(bridge.get(boundary,store,'State'),False)

    def test_saved_setter_rechecks_store_and_activation(self):
        app,caller,_=self.app();other,_,_=self.app()
        with self.boundary(app,caller) as boundary:
            store=app.session_parameters;setter=bridge.set_member(boundary,store,'State')
            app.session_parameters=other.session_parameters
            try:
                with self.assertRaises(BoundaryViolation):setter(True)
            finally:app.session_parameters=store
            setter(False);self.assertIs(bridge.get(boundary,store,'State'),False)
        with self.assertRaises(BoundaryViolation):setter(True)


if __name__=='__main__':unittest.main()
