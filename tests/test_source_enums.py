"""Source enum declarations preserve identity and isolate unsupported objects."""
import unittest
from uuid import uuid5, NAMESPACE_URL
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_enums import source_enum_definitions


def identity(name):
    return str(uuid5(NAMESPACE_URL, 'source-enum/' + name))


def value(name, uid=None, properties=''):
    return ('<EnumValue uuid="' + (uid or identity(name)) + '"><Properties><Name>' + name
            + '</Name>' + properties + '</Properties></EnumValue>')


def xml(family, name, children='', properties=''):
    return ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core">'
            '<' + family + ' uuid="' + identity(family + name) + '"><Properties><Name>' + name
            + '</Name>' + properties + '</Properties><ChildObjects>' + children + '</ChildObjects></'
            + family + '></MetaDataObject>').encode()


def package(enums=None):
    enums = {'State': xml('Enum', 'State', value('Active') + value('Inactive'))} if enums is None else enums
    files = {'Configuration.xml': xml('Configuration', 'Demo', ''.join('<Enum>' + n + '</Enum>' for n in enums))}
    files.update({'Enums/' + name + '.xml': raw for name, raw in enums.items()})
    return import_source(files)


class SourceEnumTests(unittest.TestCase):
    def test_actual_identities_and_declared_value_order(self):
        definitions, errors, names = source_enum_definitions(package())
        self.assertEqual(names, ('State',)); self.assertEqual(errors, {})
        definition = definitions[0]
        self.assertEqual(str(definition.identity), identity('EnumState'))
        self.assertEqual([v.name for v in definition.values], ['Active', 'Inactive'])
        self.assertEqual([str(v.identity) for v in definition.values], [identity('Active'), identity('Inactive')])

    def test_declared_enum_order(self):
        definitions, _, names = source_enum_definitions(package({n: xml('Enum', n) for n in ('Z', 'A')}))
        self.assertEqual(names, ('Z', 'A'))
        self.assertEqual(tuple(d.name for d in definitions), names)

    def test_real_synonyms_and_comments(self):
        description = '<Synonym><v8:item><v8:lang>en</v8:lang><v8:content>Enabled</v8:content></v8:item></Synonym><Comment>note</Comment>'
        definitions, errors, _ = source_enum_definitions(package({'State': xml('Enum', 'State', value('Active', properties=description), description)}))
        self.assertFalse(errors)
        for obj in (definitions[0], definitions[0].values[0]):
            self.assertEqual(obj.synonyms, (('en', 'Enabled'),)); self.assertEqual(obj.comment, 'note')

    def test_extra_source_presentation_properties_do_not_block_values(self):
        raw = xml('Enum', 'State', value('Active') + '<Form>MainForm</Form>', '<UseStandardCommands>true</UseStandardCommands><DefaultListForm>Enum.State.Form.MainForm</DefaultListForm>')
        raw = raw.replace(b'<Properties>', b'<InternalInfo><FutureType>preserved</FutureType></InternalInfo><Properties>', 1)
        definitions, errors, _ = source_enum_definitions(package({'State': raw}))
        self.assertFalse(errors); self.assertEqual(definitions[0].values[0].name, 'Active')

    def test_unknown_child_is_local_error(self):
        definitions, errors, names = source_enum_definitions(package({'Bad': xml('Enum', 'Bad', '<FutureChild/>'), 'Good': xml('Enum', 'Good')}))
        self.assertEqual([d.name for d in definitions], ['Good'])
        self.assertIn('bad', errors); self.assertEqual(names, ('Bad', 'Good'))

    def test_missing_uuid_is_not_synthesized(self):
        definitions, errors, _ = source_enum_definitions(package({'State': xml('Enum', 'State', value('Active').replace(' uuid="' + identity('Active') + '"', ''))}))
        self.assertEqual(definitions, ()); self.assertIn('state', errors)

    def test_duplicate_value_name_is_local_error(self):
        definitions, errors, _ = source_enum_definitions(package({'State': xml('Enum', 'State', value('Active') + value('ACTIVE'))}))
        self.assertFalse(definitions); self.assertIn('inventory', errors['state'])

    def test_duplicate_value_uuid_rejects_both_enums(self):
        definitions, errors, _ = source_enum_definitions(package({n: xml('Enum', n, value('Active')) for n in ('First', 'Second')}))
        self.assertFalse(definitions); self.assertEqual(set(errors), {'first', 'second'})

    def test_value_uuid_cannot_alias_metadata_identity(self):
        definitions, errors, _ = source_enum_definitions(package({'State': xml('Enum', 'State', value('Active', identity('ConfigurationDemo')))}))
        self.assertFalse(definitions); self.assertIn('UUID', errors['state'])

    def test_bad_synonyms_are_explicit(self):
        definitions, errors, _ = source_enum_definitions(package({'State': xml('Enum', 'State', properties='<Synonym><v8:item/></Synonym>')}))
        self.assertFalse(definitions); self.assertIn('synonym', errors['state'])

    def test_empty_enum_is_actual_empty_declaration(self):
        definitions, errors, _ = source_enum_definitions(package({'Empty': xml('Enum', 'Empty')}))
        self.assertFalse(errors); self.assertEqual(definitions[0].values, ())

    def test_value_count_bounded(self):
        definitions, errors, _ = source_enum_definitions(package({'Many': xml('Enum', 'Many', ''.join(value('V'+str(i)) for i in range(513)))}))
        self.assertFalse(definitions); self.assertIn('inventory', errors['many'])

    def test_admitted_source_required(self):
        with self.assertRaises(TypeError): source_enum_definitions({})
