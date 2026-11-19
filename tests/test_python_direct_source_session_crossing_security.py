"""Session crossing authorization is never inferred from logical-side labels."""
import unittest
from unittest.mock import patch
import test_python_direct_source_session_crossing as basic
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class SourceSessionCrossingSecurity(unittest.TestCase):
    setUp=basic.SourceSessionCrossingTests.setUp
    app=basic.SourceSessionCrossingTests.app

    def test_fresh_activation_preserves_client_frame_and_revokes_on_return(self):
        from yadinassi.execution.direct.source.python_direct_source_server import _ACTIVE,check_activation
        app,_=self.app();owner=app._session_owner;seen=[]
        def capture(text):
            fresh=_ACTIVE.get()[-1][0]
            seen.append(fresh)
            self.assertIsNot(fresh,owner);self.assertEqual(fresh.execution_context,'server')
            # Execution side is the shared scheduler's active frame, not a
            # per-interpreter label. The original client frame remains below it.
            self.assertEqual(owner._context_stack,['client','server'])
            self.assertFalse(fresh._transaction_activation_allowed)
            self.assertFalse(fresh._application_exports_enabled)
        owner.output=capture
        owner.execute('&AtServer\nFunction Read() Message("server");A=New Array;A.Add(1);Return A;EndFunction')
        first=owner.execute('Read();');second=owner.execute('Read();')
        self.assertEqual(first,second);self.assertIsNot(first,second)
        self.assertEqual(owner.variables,{});self.assertEqual(_ACTIVE.get(),())
        self.assertEqual(owner._context_stack,['client']);self.assertEqual(owner.execution_context,'client')
        for fresh in seen:
            self.assertTrue(fresh._family_released)
            with self.assertRaises(BoundaryViolation):check_activation(fresh)

    def test_origin_revocation_during_body_denies_result(self):
        for change in ('session','instance','source','plans'):
            with self.subTest(change=change):
                app,_=self.app();owner=app._session_owner
                def revoke(text):
                    if change=='session':app._session_owner=app.interpreter
                    elif change=='instance':app._instances['<session>']=app.interpreter
                    elif change=='source':app.files['Ext/SessionModule.bsl']=b'// changed'
                    else:owner._direct_source_plans={}
                owner.output=revoke
                owner.execute('&AtServer\nFunction Read() Message("revoke");Return 7;EndFunction')
                with self.assertRaises(basic.DENIED):owner.execute('Read();')
                self.assertEqual(owner.execution_context,'client')

    def test_root_and_foreign_owner_do_not_gain_session_entry(self):
        app,_=self.app();owner=app._session_owner
        owner.execute('&AtServer\nFunction Read() Return 7;EndFunction')
        with self.assertRaises(basic.DENIED):app.interpreter.execute('Read();')
        other,_=self.app();other._session_owner=owner
        with self.assertRaises(basic.DENIED):other.interpreter.execute('Read();')
        self.assertEqual(owner.execution_context,'client')

    def test_errors_and_untransferable_result_restore_side(self):
        app,_=self.app();owner=app._session_owner
        owner.execute('&AtServer\nFunction Bad() Return SessionParameters;EndFunction\n&AtServer\nProcedure Throw() Raise "stop";EndProcedure')
        for call in ('Bad();','Throw();'):
            with self.assertRaises(basic.DENIED):owner.execute(call)
            self.assertEqual(owner.execution_context,'client');self.assertEqual(owner._module_context_stack,[True])

    def test_real_transaction_gates_at_caller_and_server(self):
        import tempfile
        from pathlib import Path
        from yadinassi.configuration.configuration_source_runtime import SourceApplication
        from yadinassi.configuration.configuration_source import import_source
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        mapping={f.path:f.content for f in basic.package('',kind='xs:boolean').files}
        mapping['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting() SessionParameters.State=True;EndProcedure'
        app=SourceApplication(import_source(mapping),scratch_database=Path(directory.name)/'scratch.sqlite',output=lambda _:None)
        self.addCleanup(app.close);app.start();owner=app._session_owner
        owner.execute('&AtServer\nProcedure Begin() BeginTransaction();EndProcedure\n&AtServer\nFunction Read() Return 1;EndFunction')
        with self.assertRaises(basic.DENIED):owner.execute('Begin();')
        self.assertFalse(app.constant_store.transaction_active)
        app.constant_store.begin_transaction()
        with self.assertRaises(basic.DENIED):owner.execute('Read();')
        self.assertFalse(app.constant_store.transaction_active)
        self.assertEqual(owner.execution_context,'client')

    def test_session_registry_denied_before_lookup_callback(self):
        app,_=self.app();owner=app._session_owner;effects=[]
        owner.execute('&AtServer\nFunction Read() Return 7;EndFunction')
        original=owner.server_routines
        class Poison(dict):
            def get(self,*args):effects.append('get');raise AssertionError('get callback')
            def items(self):effects.append('items');raise AssertionError('items callback')
        owner.server_routines=Poison(original)
        try:
            with self.assertRaises(BoundaryViolation):owner.execute('Read();')
        finally:owner.server_routines=original
        self.assertEqual(effects,[])
