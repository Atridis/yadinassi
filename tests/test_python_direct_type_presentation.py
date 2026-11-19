"""Only definition-time canonical Type singletons receive their fixed display label."""
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.values import BSLType, _DIRECT_TYPE_PRESENTATIONS
from yadinassi.execution.codegen.experimental_naked_scalar_semantics import presentation, concatenate, typed_find
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation


class TypePresentationTests(unittest.TestCase):
    def test_all_defined_singletons_match_canonical_display(self):
        for member,name,error in _DIRECT_TYPE_PRESENTATIONS:
            if error is not None:
                with self.assertRaises(ValueError) as caught:presentation(member)
                self.assertEqual(str(caught.exception),error)
                with self.assertRaises(ValueError) as caught:str(member)
                self.assertEqual(str(caught.exception),error)
                continue
            self.assertEqual(str(member),name)
            self.assertEqual(presentation(member),name)
            self.assertEqual(concatenate('type:',member),'type:'+name)

    def test_runtime_display_and_operand_order_match_reference(self):
        for backend in ('python-direct','compiled-strict'):
            output=[];events=[];vm=Interpreter(output=output.append,execution_backend=backend)
            self.addCleanup(vm.close)
            vm.register_function('Left',lambda:events.append('left') or 'Тип: ')
            vm.register_function('Right',lambda:events.append('right') or BSLType.MAP)
            vm.execute('Message(Type("Number"));Message(String(Type("Type")));'
                       'Message(Left()+Right());')
            self.assertEqual(output,['Число','Тип','Тип: Соответствие'])
            self.assertEqual(events,['left','right'])

    def test_enum_value_name_str_and_class_hooks_are_not_dispatched(self):
        def hostile(*args):raise AssertionError('enum hook')
        with patch.object(BSLType,'value',property(hostile),create=True),\
             patch.object(BSLType,'name',property(hostile),create=True),\
             patch.object(BSLType,'__str__',hostile),\
             patch.object(BSLType,'__getattribute__',hostile),\
             patch.object(BSLType,'__hash__',hostile),\
             patch.object(BSLType,'__eq__',hostile):
            for member,name,error in _DIRECT_TYPE_PRESENTATIONS:
                if error is None:self.assertEqual(presentation(member),name)
                else:
                    with self.assertRaises(ValueError) as caught:presentation(member)
                    self.assertEqual(str(caught.exception),error)

    def test_forged_members_and_foreign_spoofs_are_rejected(self):
        forged=object.__new__(BSLType)
        object.__setattr__(forged,'_name_','NUMBER');object.__setattr__(forged,'_value_','Число')
        class Foreign:
            @property
            def __class__(self):return BSLType
            def __str__(self):raise AssertionError('host str')
        for value in (forged,Foreign()):
            with self.assertRaises(BoundaryViolation):presentation(value)
        with patch('yadinassi.types.values.BSLType',Foreign):
            self.assertEqual(presentation(BSLType.NUMBER),'Число')
            with self.assertRaises(BoundaryViolation):presentation(Foreign())

    def test_presentation_grants_no_members_or_find_key_capability(self):
        boundary=BoundaryContext();boundary.start();value=BSLType.NUMBER
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'value')
        with self.assertRaises(BoundaryViolation):typed_find([value],value)
        boundary.revoke()
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'value')

    def test_owner_close_during_operand_prevents_result_publication(self):
        output=[];vm=Interpreter(output=output.append);self.addCleanup(vm.close)
        def close():vm.close();return BSLType.NUMBER
        vm.register_function('CloseOwner',close)
        with self.assertRaises(BoundaryViolation):vm.execute('Message("type:"+CloseOwner());')
        self.assertEqual(output,[])

    def test_unmeasured_presentations_remain_catchable_without_publication(self):
        for member,label,error in _DIRECT_TYPE_PRESENTATIONS:
            if error is None:continue
            for backend in ('python-direct','compiled-strict'):
                output=[];vm=Interpreter(output=output.append,execution_backend=backend)
                self.addCleanup(vm.close);vm.variables['t']=member
                vm.execute('saved="old";caught=False;Try saved="type:"+t;'
                           'Except caught=True;EndTry;')
                self.assertTrue(vm.variables['caught'])
                self.assertEqual(vm.variables['saved'],'old')
                self.assertEqual(output,[])

    def test_late_value_and_str_replacement_do_not_change_direct_snapshot(self):
        output=[];vm=Interpreter(output=output.append);self.addCleanup(vm.close)
        vm.variables['t']=BSLType.NUMBER
        with patch.object(BSLType.NUMBER,'_value_','host replacement'),\
             patch.object(BSLType,'__str__',lambda self:'host replacement'):
            vm.execute('Message("type:"+t);')
        self.assertEqual(output,['type:Число'])
