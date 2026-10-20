"""ValueList probe integrity, not an implementation or oracle for native 1C.

Host objects below deliberately exercise both accepted and rejected branches.
Their behavior and SYNTHETIC codec strings are never written as native goldens.
The unchanged complete-output comparators remain the owner-evidence gate.
"""
from contextlib import ExitStack
from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, ast, runtime, serialization, type_values
from yadinassi.parser import parse
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.values import BSLArray, BSLFixedArray, BSLObject, HostFunction, equal


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/collections.bsl'
HELPERS = ('// Начало компактных проб списка значений.\n',
           '// Конец компактных проб списка значений.\n\n')
BODY = ('// Начало наблюдений списка значений.\n',
        '// Конец наблюдений списка значений.\n')
FINAL = 'table.list.checkpoint.complete: [ok]'


def source():
    return SOURCE.read_text(encoding='utf-8-sig')


def section(markers):
    return source().split(markers[0], 1)[1].split(markers[1], 1)[0]


def without_list_probe(text):
    """Historical-source integrity only; never used by a native comparator."""
    for start, end in (HELPERS, BODY):
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


def observations():
    return [node.expression for node in parse(section(BODY))
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьТаблицы']


def blob_hash(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def array(values):
    result = BSLArray()
    result.items = list(values)
    return result


class _SyntheticType:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __deepcopy__(self, memo):
        return self


LIST_TYPE = _SyntheticType('СписокЗначений')
ITEM_TYPE = _SyntheticType('ЭлементСпискаЗначений')


ALIASES = {
    'добавить': 'add', 'вставить': 'insert', 'получить': 'get',
    'количество': 'count', 'удалить': 'delete', 'очистить': 'clear',
    'сдвинуть': 'move', 'индекс': 'indexof', 'найтипозначению': 'findbyvalue',
    'найтипоидентификатору': 'findbyid', 'получитьидентификатор': 'getid',
    'загрузитьзначения': 'loadvalues', 'выгрузитьзначения': 'unloadvalues',
    'скопировать': 'copy', 'заполнитьпометки': 'fillchecks',
    'значение': 'value', 'представление': 'presentation', 'пометка': 'check',
    'типзначения': 'valuetype', 'доступныезначения': 'availablevalues',
}


def canonical(name):
    return ALIASES.get(name.casefold(), name.casefold())


class _Item(BSLObject):
    def __init__(self, host, owner=None, identifier=Decimal(0),
                 value=None, presentation='', check=False):
        self.host, self.owner, self.identifier = host, owner, identifier
        self.fields = dict(value=value, presentation=presentation, check=check)

    def __str__(self):
        return 'SYNTHETIC item'

    def get_member(self, name):
        key = canonical(name)
        self.host.events.append(('item.read.' + key, ()))
        if self.host.broken_property == key:
            raise ValueError('synthetic property read failure')
        if key in self.fields:
            return self.fields[key]
        return super().get_member(name)

    def set_member(self, name, value):
        key = canonical(name)
        self.host.events.append(('item.write.' + key, (value,)))
        if key not in self.fields:
            return super().set_member(name, value)
        self.fields[key] = value
        self.host.after('item.write.' + key, (value,))

    def get_method(self, name):
        key = canonical(name)
        if key == 'getid':
            def invoke():
                self.host.events.append(('getid', ()))
                if self.host.broken_id:
                    raise ValueError('synthetic ID failure')
                return self.identifier
            return HostFunction(name, invoke)
        return super().get_method(name)


class _List(BSLObject):
    """Permissive disposable host surface; its policies are not native claims."""
    def __init__(self, host, *args):
        self.host, self.items, self.next_id = host, [], 0
        host.events.append(('constructor.list', args))

    def __str__(self):
        return 'SYNTHETIC list'

    def __iter__(self):
        self.host.events.append(('iterate', ()))
        if self.host.broken_iteration:
            raise ValueError('synthetic iterator failure')
        return iter(self.items)

    def get(self, index):
        return self.invoke('get', index)

    def set(self, index, value):
        self.host.events.append(('index.write', (index, value)))
        raise ValueError('synthetic indexed write rejection')

    def get_member(self, name):
        key = canonical(name)
        if key == 'valuetype':
            return BSLTypeDescription()
        if key == 'availablevalues':
            return False
        return super().get_member(name)

    def get_method(self, name):
        key = canonical(name)
        methods = {'add', 'insert', 'get', 'count', 'delete', 'clear', 'move',
                   'indexof', 'getid', 'findbyid', 'findbyvalue', 'loadvalues',
                   'unloadvalues', 'copy', 'fillchecks'}
        if key not in methods:
            return super().get_method(name)
        return HostFunction(name, lambda *args: self.invoke(key, *args),
                            returns_value=key not in {
                                'delete', 'clear', 'move', 'loadvalues', 'fillchecks'})

    def position(self, value):
        if isinstance(value, _Item):
            return self.items.index(value)
        if type(value) is not Decimal:
            raise TypeError('synthetic index type')
        position = int(value)
        if not 0 <= position < len(self.items):
            raise IndexError('synthetic index bounds')
        return position

    def add_item(self, args, position=None):
        # Explicit argument defaults, without guessing native coercions.
        value = args[0] if args else None
        presentation = args[1] if len(args) > 1 else ''
        check = args[2] if len(args) > 2 else False
        item = _Item(self.host, self, Decimal(self.next_id), value, presentation, check)
        self.next_id += 1
        self.items.insert(len(self.items) if position is None else position, item)
        return item

    def invoke(self, key, *args):
        self.host.events.append((key, args))
        if key == 'add':
            result = self.add_item(args)
        elif key == 'insert':
            position, *values = args
            if type(position) is not Decimal:
                raise TypeError('synthetic insert type')
            result = self.add_item(values, max(0, min(int(position), len(self.items))))
        elif key == 'get':
            if self.host.broken_get:
                raise ValueError('synthetic get failure')
            result = self.items[self.position(args[0])]
        elif key == 'count':
            if self.host.broken_count:
                raise ValueError('synthetic count failure')
            result = Decimal(len(self.items))
        elif key == 'delete':
            self.items.pop(self.position(args[0]))
            result = None
        elif key == 'clear':
            self.items.clear()
            result = None
        elif key == 'move':
            position = self.position(args[0])
            if type(args[1]) is not Decimal:
                raise TypeError('synthetic offset type')
            item = self.items.pop(position)
            destination = max(0, min(position + int(args[1]), len(self.items)))
            self.items.insert(destination, item)
            result = None
        elif key == 'indexof':
            result = Decimal(next((i for i, item in enumerate(self.items)
                                   if item is args[0]), -1))
        elif key == 'findbyvalue':
            result = next((item for item in self.items
                           if equal(item.fields['value'], args[0])), None)
        elif key == 'findbyid':
            result = next((item for item in self.items
                           if equal(item.identifier, args[0])), None)
        elif key == 'loadvalues':
            if not isinstance(args[0], (BSLArray, BSLFixedArray)):
                raise TypeError('synthetic load source type')
            self.items.clear()
            for value in args[0]:
                self.add_item((value,))
            result = None
        elif key == 'unloadvalues':
            result = array(item.fields['value'] for item in self.items)
        elif key == 'copy':
            result = _List(self.host)
            for item in self.items:
                result.add_item(tuple(item.fields[key] for key in ('value', 'presentation', 'check')))
        elif key == 'fillchecks':
            for item in self.items:
                item.fields['check'] = args[0]
            result = None
        else:
            raise AssertionError(key)
        self.host.after(key, args)
        return result


class Host:
    def __init__(self):
        self.events, self.output, self.streams = [], [], {}
        self.command_events = []
        self.broken_property = None
        self.broken_iteration = self.broken_count = self.broken_id = self.broken_get = False
        self.broken_type_codec = False
        self.item_reads_undefined = False
        self.fail_after = None
        self.vm = Interpreter(output=self.output.append)
        self.vm.register_type('СписокЗначений', lambda *args: _List(self, *args), 'ValueList')
        self.vm.register_type('ЭлементСпискаЗначений', self.construct_item, 'ValueListItem')
        self.vm.register_function('Тип', self.type_by_name, 'Type')
        self.vm.register_function('ТипЗнч', self.type_of, 'TypeOf')
        self.vm.register_function('ЗначениеВСтрокуВнутр', self.write, 'ValueToStringInternal')
        self.vm.register_function('ЗначениеИзСтрокиВнутр', self.read, 'ValueFromStringInternal')
        self.vm.execute(source().split('#Область МассивыИСтруктуры', 1)[0])

    def __deepcopy__(self, memo):
        return self

    def construct_item(self, *args):
        self.events.append(('constructor.item', args))
        return _Item(self)

    def type_by_name(self, value):
        if type(value) is str:
            if value.casefold() in {'списокзначений', 'valuelist'}:
                return LIST_TYPE
            if value.casefold() in {'элементсписказначений', 'valuelistitem'}:
                return ITEM_TYPE
        return type_values.type_by_name(value)

    def type_of(self, value):
        if type(value) is _List:
            return LIST_TYPE
        if type(value) is _Item:
            return ITEM_TYPE
        if type(value) is _SyntheticType:
            return type_values.type_by_name('Type')
        return type_values.type_of(value)

    def after(self, method, args):
        if self.fail_after and self.fail_after(method, args):
            raise ValueError('synthetic failure after mutation')

    def write(self, value):
        if type(value) is _SyntheticType:
            if self.broken_type_codec:
                raise ValueError('synthetic type codec failure')
            text = 'SYNTHETIC-TYPE:' + value.name
        elif type(value) in {_List, _Item}:
            self.events.append(('codec.write.list' if type(value) is _List else 'codec.write.item', ()))
            rows = value.items if type(value) is _List else [value]
            projected = array(array([row.identifier, row.fields['value'],
                                     row.fields['presentation'], row.fields['check']])
                              for row in rows)
            text = ('SYNTHETIC-LIST:' if type(value) is _List else 'SYNTHETIC-ITEM:')
            text += serialization.value_to_string_internal(projected)
        else:
            return serialization.value_to_string_internal(value)
        self.streams[text] = deepcopy(value)
        return text

    def read(self, value):
        if value in self.streams:
            if value.startswith('SYNTHETIC-ITEM:') and self.item_reads_undefined:
                return None
            return deepcopy(self.streams[value])
        return serialization.value_from_string_internal(value)

    def __enter__(self):
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(runtime, '_COLLECTIONS',
                                             runtime._COLLECTIONS + (_List,)))
        original_receiver = self.vm.known_table_receiver
        original_optional = self.vm.table_optional_arguments

        def known_receiver(node):
            node = self.vm.ungroup(node)
            if isinstance(node, ast.Name):
                value = self.vm.visit_Name(node)
                if type(value) is _List:
                    return value
            return original_receiver(node)

        def optional(receiver, name):
            if type(receiver) is _List:
                key = canonical(name)
                if key == 'add':
                    return frozenset(range(3))
                if key == 'insert':
                    return frozenset(range(1, 4))
            return original_optional(receiver, name)

        self.stack.enter_context(patch.object(self.vm, 'known_table_receiver', known_receiver))
        self.stack.enter_context(patch.object(self.vm, 'table_optional_arguments', optional))
        original_execute = self.vm.visit_Execute

        def execute(node):
            # The probe passes a local fixed string. Isolate target events from
            # setup and snapshot calls, so those cannot give false coverage.
            command = self.vm.visit(node.expression)
            first = len(self.events)
            try:
                return original_execute(node)
            finally:
                self.command_events.append((command, self.events[first:]))

        self.stack.enter_context(patch.object(self.vm, 'visit_Execute', execute))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    def observe(self, label, expression):
        self.events.clear()
        self.command_events.clear()
        self.output.clear()
        escaped = expression.replace('"', '""')
        self.vm.execute('НаблюдатьТаблицы("' + label + '", "' + escaped + '")')
        return self.output[0]


class ValueListCheckpointTests(unittest.TestCase):
    def test_original_source_all_goldens_and_environment_are_unchanged(self):
        restored = ('\ufeff' + without_list_probe(source())).encode()
        self.assertEqual(blob_hash(restored), '92ba44889c221de39f8b3ae578f0c1408ccbf0ae')
        hashes = {
            'collections': 'c3e5ae6e3211b2fb85ba3614cadb764475315ce8',
            'dates': '05d23c46540b301820f2ac81c8a67fc0e1273dc8',
            'functions': '6df192ac9d10c07755948d7c14cfed9e2311c65f',
            'numbers': 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13',
            'strings': 'a1ecb5458c3eb10b0df52cd9ae241994a2e4f462',
            'values': '016f30d6f3bdb1a814e86a70e3bcf424383a0d27',
        }
        for name, expected in hashes.items():
            data = (ROOT / f'integrational_tests/output/{name}.out').read_bytes()
            self.assertEqual(blob_hash(data.replace(b'\r\n', b'\n')), expected)
        self.assertEqual((ROOT / 'integrational_tests/meta.md').read_text(encoding='utf-8'),
                         '1c-version: 8.3.27.2342\nos: Windows\ninfobase-mode: файловая база\n'
                         'infobase-locale: русский (Россия)\nsession-locale: русский (Россия)\n'
                         'compatibility-mode: НеУказан\n')

    def test_fixed_unique_bounded_observations_and_full_source_parse(self):
        calls = observations()
        self.assertEqual(len(calls), 36)
        labels = []
        for call in calls:
            self.assertEqual(len(call.arguments), 2)
            self.assertTrue(all(isinstance(arg, ast.Literal) and type(arg.value) is str
                                for arg in call.arguments))
            label, expression = (arg.value for arg in call.arguments)
            self.assertRegex(label, r'^list\.[a-z.-]+$')
            self.assertLess(len(expression), 500)
            self.assertNotRegex(expression, r'[\r\n]')
            parse('Result = ' + expression + ';')
            labels.append(label)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(source().count(FINAL), 1)
        self.assertIn('Сообщить("' + FINAL + '");', section(BODY))
        started = False
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            elif not isinstance(node, ast.Var):
                started = True

    def test_every_observation_reaches_targets_and_has_serializable_result(self):
        expected = {
            'identity': ('get', 'iterate'),
            'constructor.list': ('constructor.list',),
            'constructor.item': ('constructor.item',),
            'add.defaults': ('add',), 'add.explicit': ('add',),
            'add.omitted': ('add', 'insert'), 'add.invalid': ('add',),
            'insert.boundaries': ('insert',), 'insert.coercion': ('insert',),
            'get.access': ('get',), 'get.boundaries': ('get',),
            'index.write': ('index.write',),
            'fields.aliases': ('item.write.value', 'item.write.presentation', 'item.write.check'),
            'fields.presentation': ('item.write.presentation',),
            'fields.check': ('item.write.check',), 'fill-checks': ('fillchecks',),
            'find.values': ('findbyvalue',), 'indexof': ('indexof',),
            'delete.index': ('delete',), 'delete.item': ('delete',),
            'clear': ('clear',), 'move.index': ('move',), 'move.item': ('move',),
            'move.invalid': ('move',), 'id.lifecycle': ('getid', 'findbyid', 'move'),
            'id.find': ('getid', 'findbyid'),
            'detached.delete': ('delete', 'getid', 'findbyid'),
            'detached.clear': ('clear', 'getid', 'findbyid'),
            'copy': ('copy',), 'load': ('loadvalues',),
            'load.invalid': ('loadvalues',), 'unload': ('unloadvalues',),
            'codec.empty': ('codec.write.list',), 'codec.populated': ('codec.write.list',),
            'codec.item': ('codec.write.item',), 'codec.history': ('delete', 'move', 'codec.write.list'),
        }
        self.assertEqual(set(expected), {call.arguments[0].value[5:] for call in observations()})
        with Host() as host:
            for call in observations():
                label, expression = (arg.value for arg in call.arguments)
                with self.subTest(label=label):
                    output = host.observe(label, expression)
                    self.assertEqual(len(host.output), 1)
                    self.assertNotEqual(output, 'table.' + label + ': [error]')
                    self.assertNotIn('[serialize-error]', output)
                    self.assertNotIn('[result-error]', output)
                    targets = [name for name, args in host.events]
                    for target in expected[label[5:]]:
                        self.assertIn(target, targets)
                    for command, events in host.command_events:
                        first = parse(command)[0]
                        if isinstance(first, ast.Assign):
                            if isinstance(first.target, ast.Attribute):
                                target = 'item.write.' + canonical(first.target.name)
                            elif isinstance(first.target, ast.Index):
                                target = 'index.write'
                            else:
                                value = first.value
                                if isinstance(value, ast.New):
                                    if value.name.casefold() in {'valuelistitem', 'элементсписказначений'}:
                                        target = 'constructor.item'
                                    elif value.name.casefold() in {'valuelist', 'списокзначений'}:
                                        target = 'constructor.list'
                                    else:
                                        # A Structure wrapping separately observed IDs.
                                        calls = [arg for arg in value.arguments
                                                 if isinstance(arg, ast.Call)
                                                 and isinstance(arg.callee, ast.Attribute)]
                                        self.assertTrue(calls, command)
                                        for nested in calls:
                                            self.assertIn(canonical(nested.callee.name),
                                                          [name for name, args in events], command)
                                        continue
                                elif isinstance(value, ast.Index):
                                    target = 'get'
                                else:
                                    self.assertIsInstance(value, ast.Call, command)
                                    target = canonical(value.callee.name)
                        else:
                            self.assertIsInstance(first, ast.ExpressionStatement, command)
                            target = canonical(first.expression.callee.name)
                        self.assertIn(target, [name for name, args in events], command)
                    if label == 'list.add.omitted':
                        self.assertIn(('add', (Decimal(10), None, True)), host.events)
                        self.assertIn(('insert', (Decimal(0), None, 'missing', True)), host.events)

    def test_ordered_labels_and_completion_in_synthetic_execution(self):
        with Host() as host:
            host.vm.execute(section(BODY))
            self.assertEqual([message.split(':', 1)[0] for message in host.output],
                             ['table.' + call.arguments[0].value for call in observations()]
                             + ['table.list.checkpoint.complete'])
            self.assertEqual(host.output[-1], FINAL)

    def test_mutation_before_failure_survives_in_status_and_state(self):
        cases = [('Список.Add(99);', 'add', Decimal(3)),
                 ('Список.Insert(0, 99);', 'insert', Decimal(3)),
                 ('Список.Delete(0);', 'delete', Decimal(1)),
                 ('Список.Clear();', 'clear', Decimal(0)),
                 ('Список.Move(0, 1);', 'move', Decimal(2))]
        for command, target, count in cases:
            with self.subTest(target=target), Host() as host:
                host.fail_after = lambda method, args: (method == target
                    and (target != 'add' or args[0] == Decimal(99)))
                result = host.vm.execute('ДействиеСпискаПробы("' + command + '")')
                self.assertEqual(result.get('Status'), 'error')
                self.assertEqual(result.get('After').get('Count'), count)
                if target == 'move':
                    self.assertEqual(result.get('After').get('Items').items[0].items[0], Decimal(20))

    def test_snapshot_count_iteration_property_and_id_fail_independently(self):
        for broken, expected in [('broken_count', 'Count={"S","[error]"}'),
                                 ('broken_iteration', '[iteration-error]'),
                                 ('broken_property', '[presentation-error]'),
                                 ('broken_id', 'Count={"N",3}')]:
            with self.subTest(observer=broken), Host() as host:
                setattr(host, broken, 'presentation' if broken == 'broken_property' else True)
                output = host.observe('list.instrumented', 'ДействиеСпискаПробы("Список.Add(99);")')
                self.assertIn(expected, output)
                self.assertIn('Status={"S","ok"}', output)
                self.assertNotIn('[serialize-error]', output)
                self.assertIn(('add', (Decimal(99),)), host.events)

    def test_generic_actions_do_not_depend_on_get_for_setup(self):
        with Host() as host:
            host.broken_get = True
            output = host.observe('list.instrumented', 'ДействиеСпискаПробы("Список.Add(99);")')
            self.assertIn('Status={"S","ok"}', output)
            self.assertIn('Count={"N",3}', output)
            self.assertNotIn('get', [name for name, args in host.events])

    def test_detached_writes_keep_each_status_and_partial_fields(self):
        with Host() as host:
            host.fail_after = lambda name, args: name == 'item.write.value'
            result = host.vm.execute('СвязиСпискаПробы("delete")')
            status = result.get('WriteStatus')
            self.assertEqual(status.get('Value'), 'error')
            self.assertEqual(status.get('Presentation'), 'ok')
            self.assertEqual(status.get('Check'), 'ok')
            self.assertEqual(result.get('Written').items, [Decimal(99), 'detached', False])

    def test_id_failure_does_not_hide_lifecycle_or_codec_fields(self):
        with Host() as host:
            host.broken_id = True
            result = host.vm.execute('СвязиСпискаПробы("delete")')
            self.assertEqual(result.get('BeforeID'), '[error]')
            self.assertEqual(result.get('AfterID'), '[error]')
            self.assertEqual(result.get('Status'), 'ok')
            self.assertEqual(result.get('After').get('Count'), Decimal(2))
            output = host.observe('list.instrumented', 'КодекСпискаПробы("history")')
            self.assertIn('Write={"S","SYNTHETIC-LIST:', output)
            self.assertIn('ReadWrite={"S","same-as-Write"}', output)
            self.assertIn('ReadIDs=', output)
            self.assertNotIn('[serialize-error]', output)

    def test_codec_type_failure_does_not_hide_value_write_or_inverse(self):
        with Host() as host:
            host.broken_type_codec = True
            host.broken_iteration = True
            output = host.observe('list.instrumented', 'КодекСпискаПробы("base")')
            self.assertIn('TypeWrite={"S","[error]"}', output)
            self.assertIn('Write={"S","SYNTHETIC-LIST:', output)
            self.assertIn('ReadWrite={"S","same-as-Write"}', output)
            self.assertIn('[iteration-error]', output)
            self.assertNotIn('[serialize-error]', output)

    def test_successful_item_read_as_undefined_is_projected_as_undefined(self):
        with Host() as host:
            host.item_reads_undefined = True
            output = host.observe('list.instrumented', 'КодекСпискаПробы("item")')
            self.assertIn('ReadView={"U"}', output)
            self.assertNotIn('ReadView={"S","[error]"}', output)
            self.assertNotIn('[serialize-error]', output)


if __name__ == '__main__':
    unittest.main()
