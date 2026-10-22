"""ValueListItem references: genuine Linux checkpoint plus local boundary tests.

The twenty literal records below are transcribed unchanged from collections.out
in https://github.com/Atridis/yadinassi/actions/runs/39613596830.
PR head: da45d5a2d32226fca8cce82e9ebd018567701e40.
Synthetic merge: 37629ede2efec05b759db69b8f804bf179396253.
Tree: e5edf610125fd16f9c9e23afb0349f100846a828.
Complete artifact SHA256:
6b12b688fd53914e285b5376e9d0370dd5557013de4d8c7d0fa727264a24f22d.
Source SHA256 is checked below. These are not generated interpreter expectations
and are not Windows observations. Root / &НаКлиенте parity and defensive host,
released-owner and standalone-decoded boundaries are LOCAL tests, not additional
native client or native lifetime evidence.
"""
from scripts.native_historical_replay import without_descriptor_map_probes
from decimal import Decimal as D
import gc
import hashlib
from pathlib import Path
import unittest

from tests.native_observations import extract_payload, read_observation
from yadinassi import BSLError, Interpreter, serialization
from yadinassi.structures import BSLStructure
from yadinassi.value_lists import BSLValueList, BSLValueListItem
from yadinassi.values import BSLArray

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "f8a5be47e937e39500c51a2b9c8fdaaf4becd68aa908cf7e99abe068a6c8cd4a"
CASES = (
    "value-ru", "value-en", "presentation-ru", "presentation-en", "check-ru",
    "check-en", "value-val", "presentation-val", "check-val", "live",
    "same-nested", "write-throw", "coercions", "invalid-write", "receiver-once",
    "reorder-delete", "cache", "missing-property", "invalid-receiver", "function-result",
)
NATIVE_RECORDS = r"""
table.list.reference.value-ru: [
  Status={"S","ok"}
  Log=[{"S","entered"}; {"N",11}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",11}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.value-en: [
  Status={"S","ok"}
  Log=[{"S","entered"}; {"N",12}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",12}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.presentation-ru: [
  Status={"S","ok"}
  Log=[{"S","entered"}; {"S","new-ru"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","new-ru"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.presentation-en: [
  Status={"S","ok"}
  Log=[{"S","entered"}; {"S","new-en"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","new-en"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.check-ru: [
  Status={"S","ok"}
  Log=[{"S","entered"}; {"B",1}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","old"}
  Check={"B",1}
  ID={"N",0}
]
table.list.reference.check-en: [
  Status={"S","ok"}
  Log=[{"S","entered"}; {"B",1}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","old"}
  Check={"B",1}
  ID={"N",0}
]
table.list.reference.value-val: [
  Status={"S","ok"}
  Log=[{"S","entered-val"}; {"N",13}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.presentation-val: [
  Status={"S","ok"}
  Log=[{"S","entered-val"}; {"S","val"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.check-val: [
  Status={"S","ok"}
  Log=[{"S","entered-val"}; {"B",1}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.live: [
  Status={"S","ok"}
  Log=[{"N",21}]
  Result={"N",22}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",22}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.same-nested: [
  Status={"S","ok"}
  Log=[{"N",31}; {"S","entered"}; {"N",32}; {"N",32}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",32}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.write-throw: [
  Status={"S","error"}
  Log=[{"S","written"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",41}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.coercions: [
  Status={"S","ok"}
  Log=[{"S","entered"}; {"S","123"}; {"S","conversion-ok"}; {"S","entered"}; {"S",""}; {"S","conversion-ok"}; {"S","entered"}; {"B",1}; {"S","conversion-ok"}; {"S","entered"}; {"B",0}; {"S","conversion-ok"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S",""}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.invalid-write: [
  Status={"S","error"}
  Log=[{"S","entered"}; {"N",42}; {"S","entered"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",42}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.receiver-once: [
  Status={"S","ok"}
  Log=[{"S","receiver"}; {"S","index"}; {"S","entered"}; {"N",52}; {"S","receiver"}; {"S","index"}; {"S","entered"}; {"S","once"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",52}
  Presentation={"S","once"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.reorder-delete: [
  Status={"S","ok"}
  Log=[{"N",61}; {"N",0}; {"N",62}; {"N",-1}]
  Result={"U"}
  Count={"N",1}
  Second={"N",20}
  Identity={"B",0}
  Value={"N",62}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",-1}
]
table.list.reference.cache: [
  Status={"S","ok"}
  Log=[{"S","old; second"}; {"S","entered"}; {"S","fresh"}; {"S","old; second"}; {"S","fresh"}; {"S","fresh; second"}]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","fresh"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.missing-property: [
  Status={"S","error"}
  Log=[]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.invalid-receiver: [
  Status={"S","error"}
  Log=[]
  Result={"U"}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",10}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
table.list.reference.function-result: [
  Status={"S","ok"}
  Log=[{"N",71}]
  Result={"N",71}
  Count={"N",2}
  Second={"N",20}
  Identity={"B",1}
  Value={"N",71}
  Presentation={"S","old"}
  Check={"B",0}
  ID={"N",0}
]
"""


def plain(value):
    if type(value) is BSLArray:
        return [plain(item) for item in value.items]
    if type(value) is BSLStructure:
        return {pair.key: plain(pair.value) for pair in value}
    return value


class NativeValueListReferenceTests(unittest.TestCase):
    def test_actual_bsl_helpers_match_all_twenty_native_records(self):
        source_bytes = without_descriptor_map_probes((ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8')).encode('utf-8')
        self.assertEqual(hashlib.sha256(source_bytes.replace(b'\r\n', b'\n')).hexdigest(),
                         SOURCE_SHA256)
        source = source_bytes.decode('utf-8-sig')
        vm = Interpreter(native_target='linux-8.3.27.1508')
        vm.execute(source.split('#Область МассивыИСтруктуры', 1)[0])
        self.assertEqual(NATIVE_RECORDS.count('table.list.reference.'), len(CASES))
        for name in CASES:
            with self.subTest(case=name):
                expected = plain(read_observation(extract_payload(
                    NATIVE_RECORDS, 'table.list.reference.' + name), compact=True))
                actual = plain(vm.execute('ПробаСсылкиСписка("' + name + '")'))
                self.assertEqual(actual, expected)


class ValueListReferenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.execute('owner = New ValueList; item = owner.Add(10, "old", False); '
                        'other = owner.Add(20, "second", False);')

    def test_bilingual_fields_and_val_isolation(self):
        self.vm.execute('Procedure SetField(x, Val n) x = n; EndProcedure '
                        'Procedure SetValue(Val x, Val n) x = n; EndProcedure')
        for fields, value, expected in ((('Значение', 'Value'), '11', D(11)),
                                        (('Представление', 'Presentation'), '"new"', 'new'),
                                        (('Пометка', 'Check'), 'True', True)):
            for field in fields:
                with self.subTest(field=field):
                    self.vm.execute(f'SetField(item.{field}, {value});')
                    self.assertEqual(self.vm.execute('item.' + field), expected)
                    self.vm.execute(f'SetValue(item.{field}, Undefined);')
                    self.assertEqual(self.vm.execute('item.' + field), expected)

    def test_live_aliases_nested_same_field_and_function_result(self):
        self.vm.execute('''
            Procedure Inner(x) x = x + 1; EndProcedure
            Function Change(a, b, Val original)
                a = 31; Message(b); Inner(b); Message(a);
                original.Value = 33; Return a;
            EndFunction
            result = Change(item.Значение, item.Value, item);
        ''')
        self.assertEqual(self.output, ['31', '32'])
        self.assertEqual(self.vm.execute('result'), D(33))
        self.assertEqual(self.vm.execute('item.Value'), D(33))
        self.vm.execute('result = 99;')
        self.assertEqual(self.vm.execute('item.Value'), D(33))

    def test_exception_preserves_writes_and_restores_binding_frame(self):
        self.vm.execute('''
            Procedure Fail(x) x = 41; Raise "expected"; EndProcedure
            x = 100;
            Try Fail(item.Value); Except Message(item.Value); EndTry;
        ''')
        self.assertEqual(self.output, ['41'])
        self.assertEqual(self.vm.execute('x'), D(100))
        self.assertIsNone(self.vm.locals)
        self.vm.execute('x = 101;')
        self.assertEqual(self.vm.execute('item.Value'), D(41))

    def test_converted_getter_is_observable_immediately_and_bad_write_is_partial(self):
        self.vm.execute('''
            Procedure Convert(p, c)
                p = 123; Message(TypeOf(p) = Type("String")); Message(p);
                p = Undefined; Message(p = "");
                c = 1; Message(TypeOf(c) = Type("Boolean")); Message(c);
                c = 0; Message(c);
                p = "committed";
                c = New Array;
                Message("unreachable");
            EndProcedure
            Try Convert(item.Presentation, item.Check); Except Message("caught"); EndTry;
        ''')
        self.assertEqual(self.output, ['Да', '123', 'Да', 'Да', 'Да', 'Нет', 'caught'])
        self.assertEqual(self.vm.execute('item.Presentation'), 'committed')
        self.assertIs(self.vm.execute('item.Check'), False)

    def test_receiver_and_index_are_bound_once_before_routine_entry(self):
        self.vm.execute('''
            Function Receiver(Val list) Message("receiver"); Return list; EndFunction
            Function Index() Message("index"); Return 0; EndFunction
            Procedure Change(x)
                Message("entered"); x = 51; Message(x); x = 52;
            EndProcedure
            Change(Receiver(owner)[Index()].Value);
            Change(Receiver(owner).Get(Index()).Value);
        ''')
        self.assertEqual(self.output, ['receiver', 'index', 'entered', '51'] * 2)
        self.assertEqual(self.vm.execute('item.Value'), D(52))
        self.assertEqual(self.vm.execute('other.Value'), D(20))

    def test_reorder_and_delete_keep_original_item_reference_with_owner_alive(self):
        self.vm.execute('''
            Procedure Change(x, Val list, Val target)
                list.Move(target, 1); x = 61; Message(target.Value);
                Message(list[1].Value); list.Delete(target);
                x = 62; Message(target.Value); Message(target.GetID());
            EndProcedure
            Change(item.Value, owner, item);
        ''')
        self.assertEqual(self.output, ['61', '61', '62', '-1'])
        self.assertEqual(self.vm.execute('owner.Count()'), D(1))
        self.assertEqual(self.vm.execute('owner[0].Value'), D(20))

    def test_presentation_reference_preserves_warmed_list_cache(self):
        self.vm.execute('''
            Procedure Change(x) x = "fresh"; Message(x); EndProcedure
            Message(String(owner)); Change(item.Presentation);
            Message(String(owner)); Message(String(item));
            copy = owner.Copy(); Message(String(copy));
        ''')
        self.assertEqual(self.output, ['old; second', 'fresh', 'old; second',
                                       'fresh', 'fresh; second'])

    def test_bad_reference_fails_before_later_argument_or_routine_body(self):
        self.vm.execute('''
            Function Later() Message("later"); Return 1; EndFunction
            Procedure Change(x, Val y) Message("entered"); x = y; EndProcedure
        ''')
        for expression in ('item.NoSuchField', 'owner.Get(99).Value',
                           'item.Picture', 'item._owner_ref', 'owner.ValueType'):
            with self.subTest(expression=expression):
                with self.assertRaises(BSLError):
                    self.vm.execute(f'Change({expression}, Later());')
                self.assertEqual(self.output, [])
        self.assertEqual(self.vm.execute('item.Value'), D(10))

    def test_root_and_client_local_parity_not_native_client_evidence(self):
        for directive in ('', '&НаКлиенте\n'):
            output = []
            vm = Interpreter(output.append)
            vm.execute(directive + '''
                Procedure Change(x) x = 17; Message(x); EndProcedure
                owner = New ValueList; item = owner.Add(10);
                Change(item.Value); Message(item.Value);
            ''')
            self.assertEqual(output, ['17', '17'])


class ValueListReferenceBoundaryTests(unittest.TestCase):
    """Defensive Yadinassi scope, explicitly not extra native observations."""
    def test_released_owner_and_standalone_decoded_references_are_bounded(self):
        owner = BSLValueList()
        item = owner.add(D(10), 'old', False)
        decoded = serialization.value_from_string_internal(
            serialization.value_to_string_internal(item))
        del owner
        gc.collect()
        self.assertIsNone(item._owner_ref())
        for target in (item, decoded):
            for field in ('Value', 'Presentation', 'Check'):
                with self.subTest(target=type(target), field=field):
                    output = []
                    vm = Interpreter(output.append)
                    vm.variables['item'] = target
                    vm.execute('Procedure Change(x) Message("entered"); x = 1; EndProcedure')
                    with self.assertRaises(BSLError):
                        vm.execute(f'Change(item.{field});')
                    self.assertEqual(output, [])

    def test_reference_does_not_extend_owner_lifetime_and_rechecks_each_access(self):
        for operation in ('Message(x);', 'x = 99;'):
            with self.subTest(operation=operation):
                output = []
                vm = Interpreter(output.append)
                vm.execute('owner = New ValueList; item = owner.Add(10);')
                item = vm.variables['item']

                def release_owner():
                    vm.variables.pop('owner')
                    gc.collect()

                vm.register_function('ReleaseOwner', release_owner, returns_value=False)
                vm.execute('Procedure Change(x) Message("entered"); ReleaseOwner(); '
                           + operation + ' EndProcedure')
                with self.assertRaises(BSLError):
                    vm.execute('Change(item.Value);')
                self.assertEqual(output, ['entered'])
                self.assertIsNone(item._owner_ref())
                self.assertEqual(item.value, D(10))
                self.assertIsNone(vm.locals)

    def test_arbitrary_host_objects_and_item_subclasses_cannot_supply_member_hooks(self):
        class Host:
            def __getattr__(self, name):
                raise AssertionError('host getter invoked')
            def __setattr__(self, name, value):
                raise AssertionError('host setter invoked')

        class ItemSubclass(BSLValueListItem):
            @property
            def Value(self):
                raise AssertionError('subclass getter invoked')

            @Value.setter
            def Value(self, value):
                raise AssertionError('subclass setter invoked')

        subclass = object.__new__(ItemSubclass)
        for target in (Host(), subclass):
            output = []
            vm = Interpreter(output.append)
            vm.variables['item'] = target
            vm.execute('Procedure Change(x) Message("entered"); x = 1; EndProcedure')
            with self.assertRaises(BSLError):
                vm.execute('Change(item.Value);')
            self.assertEqual(output, [])


if __name__ == '__main__':
    unittest.main()
