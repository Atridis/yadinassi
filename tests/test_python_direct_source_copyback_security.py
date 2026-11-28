"""Copy-out is withheld until the complete server packet is admitted."""
import unittest
from decimal import Decimal
import test_source_server_call as existing
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

DENIED=(BSLError,BoundaryViolation,ValueError,TypeError)


class SourceCopybackSecurity(unittest.TestCase):
    def app(self,body,output=lambda _:None, *, allow_extensions=False):
        app=SourceApplication(existing.configuration('',body),output=output, allow_extensions=allow_extensions)
        self.addCleanup(app.close);app.start();return app

    def test_origin_revocation_or_close_withholds_copyout(self):
        for operation in ('plan','registry','close'):
            with self.subTest(operation=operation):
                holder={}
                def revoke(_):
                    app=holder['app']
                    if operation=='close':app.close();return
                    owner=next(owner for key,owner in app._instances.items() if key[0]=='serverapi')
                    if operation=='plan':owner._direct_source_plans={}
                    else:owner.server_routines={}
                app=self.app('Procedure Change(A,B) Export A=7;B=8;Message("revoke");EndProcedure',revoke)
                holder['app']=app;vm=app.interpreter;slots=vm.variables
                with self.assertRaises(DENIED):vm.execute('A=1;B=2;ServerAPI.Change(A,B);')
                self.assertEqual((slots['a'],slots['b']),(Decimal(1),Decimal(2)))

    def test_invalid_later_output_withholds_earlier_output(self):
        for statement in ('B=Metadata;', 'B=New Array;B.Add(B);'):
            with self.subTest(statement=statement):
                app=self.app('Procedure Change(A,B) Export A=7;'+statement+'EndProcedure')
                with self.assertRaises(DENIED):app.interpreter.execute('A=1;B=2;ServerAPI.Change(A,B);')
                self.assertEqual((app.interpreter.variables['a'],app.interpreter.variables['b']),
                                 (Decimal(1),Decimal(2)))

    def test_member_and_index_denied_before_earlier_effects(self):
        for argument in ('S.X','A[0]'):
            with self.subTest(argument=argument):
                app=self.app('Procedure Change(Val First,Second) Export EndProcedure', allow_extensions=True);effects=[]
                app.interpreter.register_function('Touch',lambda:effects.append('arg') or Decimal(1))
                with self.assertRaises(DENIED):
                    app.interpreter.execute('S=New Structure("X",1);A=New Array;A.Add(1);ServerAPI.Change(Touch(),'+argument+');')
                self.assertEqual(effects,[])

    def test_fragment_copyback_and_early_shape_denial(self):
        app=self.app('Function Change(X,Val Y) Export X=X+1;Return X;EndFunction', allow_extensions=True)
        vm=app.interpreter
        vm.execute('X=1;Execute("ServerAPI.Change(X,0);");Y=Eval("ServerAPI.Change(X,0)");')
        self.assertEqual((vm.variables['x'],vm.variables['y']),(Decimal(3),Decimal(3)))
        effects=[];vm.register_function('Touch',lambda:effects.append('arg') or Decimal(1))
        for expression in ('Execute("ServerAPI.Change(Touch(),Touch());");',
                           'Eval("ServerAPI.Change(Touch(),Touch())");'):
            with self.subTest(expression=expression),self.assertRaises(DENIED):vm.execute(expression)
        self.assertEqual(effects,[])
