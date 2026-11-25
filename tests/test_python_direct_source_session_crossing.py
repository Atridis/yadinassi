"""Session-owned zero-argument host crossings keep the actual caller side."""
import unittest
from unittest.mock import patch
import test_source_session_types as existing
from test_source_session_parameters import package
from yadinassi.configuration.configuration_source import import_source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.application.session_parameters import _UNSET
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

DENIED=(BSLError,BoundaryViolation,ValueError,TypeError)

class SourceSessionCrossingTests(unittest.TestCase):
    def app(self):
        mapping={f.path:f.content for f in package('',kind='xs:boolean').files}
        mapping['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting() SessionParameters.State=True;EndProcedure'
        output=[];app=SourceApplication(import_source(mapping),output=output.append);self.addCleanup(app.close);app.start();return app,output
    def test_original_zero_parameter_lazy_uuid(self):
        original=existing.SourceSessionTypesTests();self.addCleanup(original.doCleanups)
        original.test_zero_parameter_lazy_handler()
    def test_lazy_zero_parameter_from_existing_qualified_server_crossing(self):
        from test_source_server_call import module
        mapping={f.path:f.content for f in package('',kind='xs:boolean').files}
        mapping['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting() SessionParameters.State=True;EndProcedure'
        extra=module('ServerAPI','Function Read() Export Return SessionParameters.State;EndFunction')
        extra['CommonModules/ServerAPI.xml']=extra['CommonModules/ServerAPI.xml'].replace(
            b'<CommonModule>',b'<CommonModule uuid="00000000-0000-0000-0000-000000000032">')
        mapping.update(extra);output=[]
        app=SourceApplication(import_source(mapping),output=output.append)
        self.addCleanup(app.close);app.start();app.session_parameters._values['state']=_UNSET
        app.interpreter.execute('Message(ServerAPI.Read());')
        self.assertEqual(output,['Да']);self.assertIs(app.session_parameters._values['state'],True)
        self.assertEqual(app._session_owner.execution_context,'client')
    def test_private_nested_routine_and_actual_side_restore(self):
        app,out=self.app();owner=app._session_owner
        owner.execute('&AtServer\nFunction Read() Return Inner();EndFunction\n&AtServer\nFunction Inner() Return SessionParameters.State;EndFunction\nMessage(Read());')
        self.assertEqual(out,['Да']);self.assertEqual(owner.execution_context,'client')
        with self.assertRaises(DENIED):owner.execute('SessionParameters.State;')
        self.assertEqual(owner.execution_context,'client')
    def test_safe_mode_and_transaction_gates(self):
        from yadinassi.db import database_transactions
        app,out=self.app();owner=app._session_owner
        owner.execute('&AtServer\nProcedure Read() Message("bad");EndProcedure')
        with self.assertRaises(DENIED):owner.execute('SetSafeMode(True);Read();')
        with patch.object(database_transactions,'forbid_transfer',side_effect=ValueError('transaction crossing denied')):
            with self.assertRaises(DENIED):owner.execute('Read();')
        self.assertEqual(out,[]);self.assertEqual(owner.execution_context,'client')
    def test_nonzero_parameters_denied_before_argument_effects(self):
        app,out=self.app();owner=app._session_owner
        owner.execute('&AtServer\nProcedure Read(Val X) Message("bad");EndProcedure')
        with self.assertRaises(DENIED):owner.execute('Read(Message("arg"));')
        self.assertEqual(out,[])
    def test_module_state_is_not_inherited(self):
        app,out=self.app();owner=app._session_owner
        owner.execute('&AtServer\nVar Saved;\n&AtServer\nProcedure Read() Message("bad");EndProcedure')
        with self.assertRaises(DENIED):owner.execute('Read();')
        self.assertEqual(out,[])
