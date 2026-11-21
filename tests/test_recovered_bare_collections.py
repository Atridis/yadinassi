import unittest
from unittest.mock import patch
from yadinassi.execution.codegen.native_bare_collections import (
    BareArray, BareMap, BareMapEntry, BareStructure, BareValueList, BareValueListItem,
)

class RecoveredBareCollections(unittest.TestCase):
    def test_map_is_raw_dict_and_iterates_light_pairs(self):
        value=BareMap();value.insert('x',3);value.set(4,None)
        self.assertEqual(dict(value),{'x':3,4:None})
        self.assertEqual(list(value),[BareMapEntry('x',3),BareMapEntry(4,None)])
        self.assertEqual(next(iter(value)).get_member('key'),'x')
        self.assertIsNone(value.delete('absent'));value.delete('x')
        self.assertEqual(value.count(),1);self.assertIs(type(value.count()),int)
        self.assertEqual(dict(value.copy()),dict(value))
        with self.assertRaises(TypeError):value.insert([],3)
    def test_structure_has_single_canonical_dictionary(self):
        value=BareStructure(' Name,NUMBER ',3,4)
        self.assertEqual(dict(value),{'name':3,'number':4})
        self.assertIs(BareStructure.get_member,dict.__getitem__)
        self.assertIs(BareStructure.set_member,dict.__setitem__)
        value.set_member('name',8);value.insert('Extra',None)
        self.assertEqual(value.get('NAME'),8);self.assertTrue(value.property('EXTRA'))
        self.assertEqual(list(value),[BareMapEntry('name',8),BareMapEntry('number',4),BareMapEntry('extra',None)])
        copy=value.copy();copy.delete('NAME');self.assertTrue(value.property('Name'))
        with self.assertRaises(KeyError):value.get_member('missing')
        with self.assertRaises(NotImplementedError):value.property('name',[])
    def test_value_list_record_operations(self):
        value=BareValueList();a=value.add(3,'three');b=value.insert(0,1,'one')
        self.assertIs(type(a),BareValueListItem);self.assertEqual(list(a),[3,'three',False,None])
        self.assertIs(value.get(0),b);self.assertIs(value.find_by_value(3),a)
        a.set_member('check',True);self.assertTrue(a.get_member('check'))
        value.fill_checks(False);self.assertFalse(a[2])
        copy=value.copy();self.assertEqual(copy,value);self.assertIsNot(copy[0],value[0])
        value.move(0,1);self.assertEqual([x[0] for x in value],[3,1])
        value.sort_by_value();value.delete(-1);self.assertEqual([x[0] for x in value],[1])
        self.assertIs(type(value.count()),int)
        with self.assertRaises(NotImplementedError):value.find_by_id(0)
        with self.assertRaises(NotImplementedError):a.get_id()
    def test_unload_returns_one_new_array_storage_with_shared_payloads(self):
        payload=[];value=BareValueList();value.add(payload);value.add(None)
        with patch.object(BareArray,'__init__',side_effect=AssertionError('unneeded empty storage')):
            result=value.unload_values()
        self.assertIs(type(result),BareArray);self.assertIs(type(result._data),list)
        self.assertEqual(len(result),2);self.assertIs(result[0],payload);self.assertIsNone(result[1])
        result.add(3);self.assertEqual(value.count(),2)
        fresh=value.unload_values();self.assertIsNot(fresh._data,result._data)
    def test_load_and_empty_unload(self):
        value=BareValueList();value.load_values([5,2]);value.sort_by_value(True)
        self.assertEqual(list(value.unload_values()),[5,2])
        value.clear();self.assertEqual(list(value.unload_values()),[])

if __name__=='__main__':unittest.main()
