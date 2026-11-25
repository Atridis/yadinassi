"""Direct helpers checked against actual VM / canonical collection semantics."""
import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.types.values import BSLArray,HostFunction
from yadinassi.collections.structures import BSLStructure
from yadinassi.execution.codegen.direct_structure import *
from yadinassi.execution.codegen.direct_structure import _DirectStructure
from yadinassi.execution.codegen.direct_scalar_semantics import typed_find

def vm_values(source,*names):
    vm=Interpreter();vm.execute(source)
    return tuple(vm.variables[name] for name in names)


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
