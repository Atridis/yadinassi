"""Live behavior migrated from retired compiled-engine tests.

No legacy oracle or fallback. Unsupported live behavior must fail normally.
Engine flags, registry layouts, tier counters and old node-visitor ABI are retired.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.errors import BSLRuntimeError

class SnapshotContractTests(unittest.TestCase):
    def test_retained_routine_version_survives_unrelated_repl(self):
        vm=Interpreter(execution_backend='python-direct');p=parse('Function F() Return 1; EndFunction')
        vm.execute_program(p);p[0].body[0].value.value=Decimal(2)
        vm.execute('x=0;');vm.execute('r=F();')
        self.assertEqual(vm.variables['r'],Decimal(1))
        vm.execute_program(p);vm.execute('r=F();')
        self.assertEqual(vm.variables['r'],Decimal(2))
        vm.execute('Function F() Return 3; EndFunction');vm.execute('r=F();')
        self.assertEqual(vm.variables['r'],Decimal(3))

    def test_explicit_unit_execution_prepares_new_version(self):
        vm=Interpreter(execution_backend='python-direct');p=parse('r=1;')
        vm.execute_program(p);p[0].value.value=Decimal(2)
        vm.execute_program(p)
        self.assertEqual(vm.variables['r'],Decimal(2))

    def test_reentrant_readmission_cannot_replace_active_version(self):
        out=[];vm=Interpreter(execution_backend='python-direct',output=out.append)
        p=parse('Function F() Return 1; EndFunction Procedure A() Host();Message(F()); EndProcedure A();')
        def host():
            p[0].body[0].value.value=Decimal(2)
            vm.execute_program([p[0]])
        vm.register_function('Host',host,returns_value=False)
        vm.execute_program(p);self.assertEqual(out,['1'])
        vm.execute('r=F();');self.assertEqual(vm.variables['r'],Decimal(1))
        vm.execute_program([p[0]]);vm.execute('r=F();');self.assertEqual(vm.variables['r'],Decimal(2))

    def test_live_byref_and_dynamic_code(self):
        vm=Interpreter(execution_backend='python-direct')
        vm.execute('Procedure Inc(x) x=x+1; EndProcedure a=1;b=0;Inc(a);Execute("b=3;");r=Eval("a+b");')
        self.assertEqual(vm.variables['a'],Decimal(2));self.assertEqual(vm.variables['r'],Decimal(5))

class SnapshotLiveFormTests(unittest.TestCase):
    def test_live_form_values_items_and_handler_binding_do_not_recompile_client(self):
        from test_form_runtime import SOURCE, make
        from yadinassi.execution_policy import execution_backend_policy
        source=SOURCE.replace('ThisObject.Dynamic = "command";', 'Rebind();')+'''
&AtServer
Procedure Rebind()
 Items.NameField.SetAction("OnChange", "ChangedAgain");
 Added = Items.Add("SecondField", Type("FormField"));
 Added.DataPath = "Name";
EndProcedure
&AtClient
Procedure ChangedAgain(Element)
 ThisObject.Dynamic = "again:" + ThisObject.Name;
EndProcedure
'''
        with execution_backend_policy('python-direct'):
            session=make(source);session.open()
            vm=session.interpreter
            first=session.dispatch('change',revision=1,control='NameField',value='Ada')
            self.assertEqual(dict(first.attributes)['Name'],'Ada')
            self.assertEqual(dict(first.attributes)['Dynamic'],'changed')
            session.dispatch('command',revision=2,control='ApplyButton')
            second=session.dispatch('change',revision=3,control='NameField',value='Bob')
            self.assertEqual(dict(second.attributes)['Dynamic'],'again:Bob')
            self.assertIn('secondfield',session.form.items._values)
            third=session.dispatch('change',revision=4,control='SecondField',value='Carol')
            self.assertEqual(dict(third.attributes)['Name'],'Carol')

    def test_handler_authority_and_explicit_release_remain_enforced(self):
        from test_form_runtime import make
        from yadinassi.execution_policy import execution_backend_policy
        with execution_backend_policy('python-direct'):
            session=make();session.open()
            field=session.form.items._values['namefield']
            with self.assertRaises(ValueError):field.set_action('OnChange','ApplyCommand')
            self.assertEqual(field.action,'Changed')
            with self.assertRaises(ValueError):session.dispatch('ApplyCommand',revision=1)
            result=session.dispatch('change',revision=1,control='NameField',value='live')
            self.assertEqual(dict(result.attributes)['Dynamic'],'changed')

    def test_existing_server_handler_cannot_be_bound_as_client_event(self):
        from test_form_runtime import SOURCE,make
        from yadinassi.execution_policy import execution_backend_policy
        source=SOURCE.replace('ThisObject.Dynamic = "command";','BadBind();')+'''
&AtServer
Procedure BadBind()
 Items.NameField.SetAction("OnChange", "Create");
EndProcedure
'''
        with execution_backend_policy('python-direct'):
            session=make(source);session.open()
            with self.assertRaisesRegex(Exception,'обработчик отсутствует или имеет неподдерживаемую сигнатуру'):
                session.dispatch('command',revision=1,control='ApplyButton')
            self.assertEqual(session.form.items._values['namefield'].action,'Changed')
            result=session.dispatch('change',revision=2,control='NameField',value='still-live')
            self.assertEqual(dict(result.attributes)['Dynamic'],'changed')
