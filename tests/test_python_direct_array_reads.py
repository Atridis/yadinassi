"""Existing native Array proofs also establish live dictionary key presence."""
from decimal import Decimal
import unittest
from contextlib import closing

from yadinassi import Interpreter


class ArrayDefiniteReadTests(unittest.TestCase):
    def paired(self, source, install=None):
        # Product observations, not a comparison of an inactive optimizer hook.
        with closing(Interpreter()) as vm:
            if install:install(vm)
            error=None
            try:vm.execute(source)
            except Exception as exc:error=(type(exc).__name__,str(exc))
            return ({k:v for k,v in vm.variables.items() if k!='host'},error)

    def test_proven_array_loop_reads_and_counter_use_live_subscripts(self):
        source='a=New Array;For i=0 To 9 Do a.Add(i);EndDo;s=0;For j=0 To a.Count()-1 Do s=s+a.Get(j);EndDo;'
        self.assertEqual(self.paired(source)[0]['s'],45)

    def test_aliases_and_clear_keep_native_effects(self):
        values,error=self.paired('a=New Array;a.Add(3);b=a;s=b.Get(0);b.Clear();r=a.Count();')
        self.assertIsNone(error);self.assertEqual(values['s'],3);self.assertEqual(values['r'],0)

    def test_callback_rebind_after_receiver_read_uses_captured_array(self):
        def install(vm):
            def change():vm.variables['a']=Decimal(99);return Decimal(7)
            vm.register_function('Change',change)
        values,error=self.paired('a=New Array;b=a;a.Add(Change());r=b.Get(0);',install)
        self.assertIsNone(error);self.assertEqual(values['a'],99);self.assertEqual(values['r'],7)

    def test_callback_delete_keeps_missing_name_error(self):
        def install(vm):vm.register_function('Drop',lambda:vm.variables.pop('a'))
        values,error=self.paired('a=New Array;a.Add(1);Drop();r=a.Count();',install)
        self.assertNotIn('r',values);self.assertIn('не определена',error[1])

    def test_callback_counter_update_stays_live(self):
        def install(vm):vm.register_function('Change',lambda:vm.variables.__setitem__('i',Decimal(5)))
        values,error=self.paired('a=New Array;For i=0 To 5 Do a.Add(i);Change();EndDo;r=a.Count();',install)
        self.assertIsNone(error);self.assertEqual(values['r'],1);self.assertEqual(values['i'],6)

    def test_zero_iterations_do_not_define_body_names(self):
        values,error=self.paired('a=New Array;For i=2 To 1 Do b=a;EndDo;r=b;')
        self.assertNotIn('b',values);self.assertIn('не определена',error[1])

    def test_byref_call_invalidates_previous_array_facts(self):
        values,error=self.paired('Procedure Change(a) a=7;EndProcedure a=New Array;Change(a);r=a;')
        self.assertIsNone(error);self.assertEqual(values['r'],7)

    def test_bounds_failure_preserves_partial_live_state(self):
        values,error=self.paired('a=New Array;a.Add(1);s=0;For i=0 To 2 Do s=s+a.Get(i);EndDo;')
        self.assertEqual(values['s'],1);self.assertEqual(values['i'],1);self.assertIsNotNone(error)
