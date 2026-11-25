"""UUID construction inside configured source, without new service/transfer grants."""
import unittest
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.execution.direct.python_direct_configuration import ConfigurationBoundary
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.unique_identifiers import BSLUUID
from yadinassi.types.values import HostFunction
from configuration_runtime_fixture import module_files

TEXT='01234567-89ab-cdef-0123-456789abcdef'

class ConfigurationUUIDTests(unittest.TestCase):
    def app(self, source, output=None):
        app=ConfigurationApplication.from_files(module_files([('Tools',source,{})]),output=output or (lambda value:None))
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    def test_aliases_in_real_common_module_no_legacy(self):
        source=f'Function F() Export A=New UUID("{TEXT}");B=Новый УникальныйИдентификатор("{TEXT.upper()}");Return A=B;EndFunction'
        app=self.app(source)
        self.assertIs(app.execute('Tools.F()'),True)

    def test_default_constructor_and_invalid_input(self):
        app=self.app('Function F() Export Return New UUID<>New UUID;EndFunction Function Bad() Export C=0;Try A=New UUID(7);Except C=C+1;EndTry;Try A=New UUID("bad");Except C=C+1;EndTry;Try A=New UUID("a","b");Except C=C+1;EndTry;Return C;EndFunction')
        self.assertIs(app.execute('Tools.F()'),True)
        self.assertEqual(app.execute('Tools.Bad()'),3)

    def test_unused_uuid_routine_does_not_block_start(self):
        app=self.app('Function Unused() Export Return New UUID;EndFunction Function F() Export Return 42;EndFunction')
        self.assertEqual(app.execute('Tools.F()'),42)

    def test_no_uuid_transfer_or_member_grant(self):
        app=self.app('Function F() Export Return New UUID;EndFunction')
        with self.assertRaises(BoundaryViolation):app.execute('Tools.F()')
        self.assertNotIn('x',app.interpreter.variables)

    def test_replaced_factory_rejected_before_argument_effect(self):
        source=f'Function Argument() Message("argument");Return "{TEXT}";EndFunction Function F() Export Return New UUID(Argument())=New UUID;EndFunction'
        out=[];app=self.app(source,out.append)
        owner=app._modules['tools','client'].interpreter
        effects=[];owner.types['uuid']=HostFunction('UUID',lambda *args:effects.append('constructor'))
        with self.assertRaises(BoundaryViolation):app.execute('Tools.F()')
        self.assertEqual(out,[]);self.assertEqual(effects,[])

    def test_bound_constructor_checks_live_owner_and_wrapper(self):
        app=self.app('Function F() Export Return 1;EndFunction')
        ctx=ConfigurationBoundary(app,app.interpreter);ctx.enter();self.addCleanup(ctx.leave)
        call=ctx.resolve_service('new:uuid')
        factory=app.interpreter.types['uuid'];events=[]
        factory.function=lambda *args:events.append('replacement')
        with self.assertRaises(BoundaryViolation):call(TEXT)
        self.assertEqual(events,[])
        factory.function=BSLUUID
        call=ctx.resolve_service('new:uuid')
        app.interpreter.types['uuid']=HostFunction('UUID',lambda *args:events.append('registry replacement'))
        with self.assertRaises(BoundaryViolation):call(TEXT)
        self.assertEqual(events,[])
        app.interpreter.types['uuid']=factory
        call=ctx.resolve_service('new:уникальныйидентификатор')
        app.close(force=True)
        with self.assertRaisesRegex(ValueError,'not active'):call(TEXT)
