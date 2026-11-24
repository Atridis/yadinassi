"""Direct helpers checked against actual VM / canonical collection semantics."""
import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.types.values import BSLArray,HostFunction
from yadinassi.collections.structures import BSLStructure
from yadinassi.execution.codegen.experimental_naked_structure import *
from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
from yadinassi.execution.codegen.experimental_naked_array_methods import array_method_value
from yadinassi.execution.codegen.experimental_naked_collections import _checked_array_index,_array_insert_shape
from yadinassi.execution.codegen.experimental_naked_scalar_semantics import typed_find

def vm_values(source,*names):
    vm=Interpreter();vm.execute(source)
    return tuple(vm.variables[name] for name in names)

def method(array,name):
    def delete(a,index):del a[_checked_array_index(a,index)]
    return array_method_value(array,name,insert=_array_insert_shape,find=typed_find,delete=delete)

class StructureDirectTests(unittest.TestCase):
    def test_casefold(self):
        s=new_structure('Name',D(1));structure_set(s,'NAME',D(3))
        self.assertEqual(structure_get(s,'name'),vm_values('s=New Structure("Name",1);s.NAME=3;result=s.name;','result')[0])
    def test_duplicate_and_spelling(self):
        s=new_structure('Name,name',D(1),D(2));self.assertEqual((len(s),list(s.items())),(1,[('name',D(2))]))
    def test_assignment_preserves_spelling(self):
        s=new_structure('Name',D(1));s['NAME']=D(3);self.assertEqual(list(s.items()),[('Name',D(3))])
    def test_insert_respells(self):
        s=new_structure('Name',D(1));s.insert('nAmE',D(3));self.assertEqual(list(s.items()),[('nAmE',D(3))])
    def test_property_spaces_and_output(self):
        values=[]
        class Ref:
            def set(self,value):values.append(value)
        s=new_structure('Name',D(7));self.assertTrue(structure_property(s,' NAME ',Ref()));self.assertEqual(values,[7])
        self.assertFalse(structure_property(s,'missing',Ref()));self.assertEqual(values,[7,None])
    def test_invalid_keys_match_canonical(self):
        for name in (' Name ','\tName\t','bad-key',D(1)):
            errors=[]
            for action in (lambda:BSLStructure('Name',D(7)).get(name),lambda:structure_get(new_structure('Name',D(7)),name)):
                try:action()
                except Exception as error:errors.append((type(error),str(error)))
            self.assertEqual(len(errors),2);self.assertEqual(*errors)
    def test_unicode_casefold(self):
        s=new_structure('ß',D(1));s.insert('SS',D(2));self.assertEqual((len(s),s['ß'],list(s.items())),(1,2,[('SS',D(2))]))
    def test_count_property_distinct(self):
        s=new_structure('Count',D(7));self.assertEqual(s['count']+len(s),vm_values('s=New Structure("Count",7);result=s.Count+s.Count();','result')[0])
    def test_composition_change_rejected_but_value_updates_live(self):
        s=new_structure('a,b',D(1),D(2));it=s.items();self.assertEqual(next(it),('a',D(1)));s['b']=D(9);self.assertEqual(next(it),('b',D(9)))
        it=s.items();next(it);structure_delete(s,'b');s.insert('c',D(3))
        with self.assertRaisesRegex(ValueError,'Изменение состава структуры'):next(it)
    def test_known_keys_and_mapping_references_preserve_rules(self):
        s=new_structure('Name',D(1));structure_set_known(s,'name','NAME',D(3));self.assertEqual(structure_get_known(s,'name','Name'),3)
        self.assertIn('NAME',s);self.assertEqual(s.get('NAME'),3)
        with self.assertRaises(ValueError):s['missing']=D(7)
        self.assertIsNone(s.get('missing'));s.clear();self.assertEqual(len(s),0)

class ArrayMethodValueTests(unittest.TestCase):
    def test_count_method(self):
        a=[];f=method(a,'Count');a.append(D(1));self.assertIs(type(f),HostFunction);self.assertEqual(f(),1)
    def test_add_default_and_mutation(self):
        a=[];f=method(a,'Add');f();f(D(7));self.assertEqual(a,[None,D(7)])
    def test_receiver_bound_before_reassignment(self):
        a=[D(7)];f=method(a,'Count');a=[];self.assertEqual(f(),vm_values('a=New Array;a.Add(7);f=a.Count;a=New Array;result=f();','result')[0])
    def test_extraction_identity_and_alias(self):
        a=[];f=method(a,'Count');g=method(a,'Count');alias=f;self.assertIsNot(f,g);self.assertIs(alias,f)
    def test_escaped_method_in_array(self):
        a=[];box=[method(a,'Add')];box[0](D(9));self.assertEqual(a,[D(9)])
    def test_get_set_insert_delete_find(self):
        a=[True,D(1)];self.assertEqual(method(a,'Find')(D(1)),1);self.assertEqual(method(a,'Get')(D(1)),1)
        method(a,'Set')(D(1),D(9));method(a,'Insert')(D(4),D(7));self.assertEqual(a,[True,D(9),None,None,D(7)])
        method(a,'Delete')(D(0));self.assertEqual(len(a),4)
    def test_aliases_and_empty_ubound(self):
        a=[];self.assertEqual(method(a,'ВГраница')(),-1);method(a,'Добавить')(D(7));self.assertEqual(method(a,'Количество')(),1);method(a,'Очистить')();self.assertEqual(a,[])
    def test_missing_method_and_nonarray_not_adopted(self):
        with self.assertRaises(ValueError):method([],'unknown')
        with self.assertRaises(TypeError):method({},'Count')
    def test_arity_errors_match_canonical(self):
        for name,args in (('Count',(D(1),)),('Add',(D(1),D(2))),('Get',()),('Set',(D(1),)),('Insert',()),('Find',())):
            errors=[]
            for function in (BSLArray().get_member(name),method([],name)):
                try:function(*args)
                except Exception as error:errors.append((type(error),str(error)))
            self.assertEqual(len(errors),2);self.assertEqual(*errors)
