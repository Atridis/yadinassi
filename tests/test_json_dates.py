"""Documented JSON date shapes and explicit local conversion boundaries.

Timezone/fraction/resource checks assert Yadinassi policy, not new native probes.
"""

from datetime import datetime, timedelta
from decimal import Decimal
import os
import unittest
from unittest.mock import patch

from yadinassi import json_dates, timezones
from yadinassi.dates import BSLDate, MAX_TICKS, TICKS_PER_SECOND, date
from yadinassi.json_dates import (
    BSLJSONDateFormat as F, BSLJSONDateWritingVariant as V,
    BSLJSONSerializerSettings, JSON_DATE_FORMATS, JSON_DATE_WRITING_VARIANTS,
    read_json_date, write_json_date,
)
from yadinassi.values import NULL


EPOCH = datetime(1970, 1, 1)


def seconds(*parts):
    delta = datetime(*parts) - EPOCH
    return delta.days * 86400 + delta.seconds


def fields(value):
    return (value.year, value.month, value.day, value.hour, value.minute, value.second)


class JSONDateTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {timezones.TIMEZONE_ENV: 'UTC'}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_enum_bilingual_case_insensitive_members(self):
        for enum, namespace in ((F, JSON_DATE_FORMATS), (V, JSON_DATE_WRITING_VARIANTS)):
            for item in enum:
                for alias in item.value:
                    self.assertIs(namespace.get_member(alias), item)
                    self.assertIs(namespace.get_member(alias.swapcase()), item)
                self.assertEqual(str(item), item.value[0])

    def test_enum_namespaces_are_closed_and_read_only(self):
        for namespace in (JSON_DATE_FORMATS, JSON_DATE_WRITING_VARIANTS):
            with self.assertRaises(ValueError): namespace.get_member('Missing')
            with self.assertRaises(ValueError): namespace.set_member('ISO', F.ISO)
            with self.assertRaises(ValueError): namespace.get_member('_enum')

    def test_serializer_default_settings(self):
        value = BSLJSONSerializerSettings()
        self.assertIs(value.date_serialization_format, F.ISO)
        self.assertIs(value.date_writing_variant, V.LOCAL_DATE)
        self.assertIs(value.serialize_arrays_as_objects, False)
        self.assertEqual(str(value), 'НастройкиСериализацииJSON')

    def test_serializer_mutable_bilingual_properties(self):
        value = BSLJSONSerializerSettings()
        for ru, en, first, second, attr in (
            ('ВариантЗаписиДаты', 'DateWritingVariant', V.UNIVERSAL_DATE,
             V.LOCAL_DATE_WITH_OFFSET, 'date_writing_variant'),
            ('СериализовыватьМассивыКакОбъекты', 'SerializeArraysAsObjects',
             True, False, 'serialize_arrays_as_objects'),
            ('ФорматСериализацииДат', 'DateSerializationFormat',
             F.MICROSOFT, F.JAVASCRIPT, 'date_serialization_format'),
        ):
            value.set_member(ru.upper(), first)
            self.assertIs(value.get_member(en.lower()), first)
            self.assertIs(getattr(value, attr), first)
            value.set_member(en.swapcase(), second)
            self.assertIs(value.get_member(ru.lower()), second)

    def test_serializer_invalid_assignment_is_atomic(self):
        value = BSLJSONSerializerSettings()
        for name in ('DateWritingVariant', 'SerializeArraysAsObjects', 'DateSerializationFormat'):
            previous = value.get_member(name)
            for bad in (None, NULL, 0, Decimal(1), 'ISO', [], object()):
                with self.subTest(name=name, bad=type(bad)), self.assertRaises(TypeError):
                    value.set_member(name, bad)
                self.assertIs(value.get_member(name), previous)
        with self.assertRaises(TypeError): value.set_member('DateWritingVariant', F.ISO)
        with self.assertRaises(TypeError): value.set_member('DateSerializationFormat', V.LOCAL_DATE)
        with self.assertRaises(TypeError): value.set_member('DateWritingVariant', True)
        with self.assertRaises(TypeError): value.set_member('DateSerializationFormat', False)

    def test_serializer_zero_argument_constructor_and_closed_surface(self):
        for args in ((None,), (F.ISO,), (V.LOCAL_DATE, False, F.ISO)):
            with self.assertRaises(TypeError): BSLJSONSerializerSettings(*args)
        value = BSLJSONSerializerSettings()
        for name in ('DateFormat', 'ФорматСериализацииДаты', '_property', 'date_serialization_format'):
            with self.assertRaises(ValueError): value.get_member(name)
            with self.assertRaises(ValueError): value.set_member(name, F.ISO)

    def test_iso_local_calendar_does_not_need_an_instant(self):
        os.environ[timezones.TIMEZONE_ENV] = 'Not/AZone'
        with patch.object(timezones, 'local_parts', side_effect=AssertionError('instant lookup')), \
                patch.object(json_dates.time, 'mktime', side_effect=AssertionError('host lookup')):
            for text, source in (('2024-02-29T12:34:56', date('20240229123456')),
                                 ('0001-01-01T00:00:00', BSLDate(0)),
                                 ('9999-12-31T23:59:59', BSLDate(MAX_TICKS))):
                self.assertEqual(read_json_date(text, F.ISO), source)
                self.assertEqual(write_json_date(source, F.ISO), text)
                self.assertEqual(write_json_date(source, F.ISO, None), text)

    def test_iso_explicit_z_and_positive_offset_normalize_to_local(self):
        os.environ[timezones.TIMEZONE_ENV] = 'Europe/Warsaw'
        expected = date('20240229133456')
        for text in ('2024-02-29T12:34:56Z', '2024-02-29T13:34:56+01:00',
                     '2024-02-29T18:19:56+05:45'):
            self.assertEqual(read_json_date(text, F.ISO), expected)

    def test_iso_negative_offset_and_calendar_rollover(self):
        self.assertEqual(read_json_date('2024-02-29T23:45:00-00:30', F.ISO), date('20240301001500'))
        self.assertEqual(read_json_date('2024-01-01T00:15:00+00:30', F.ISO), date('20231231234500'))
        for suffix in ('Z', '+00:00', '-00:00'):
            self.assertEqual(read_json_date('2024-02-29T12:34:56' + suffix, F.ISO), date('20240229123456'))

    def test_iso_rejects_invalid_lexical_forms_and_dates(self):
        for text in ('', '2024-02-29', '2024-02-29 12:34:56', '2024-02-29t12:34:56Z',
                     '2024-02-29T12:34:56z', '2024-02-29T12:34:56.000',
                     '2024-02-29T12:34:56.125Z', '2024-02-29T12:34:56+0100',
                     '2024-02-29T12:34:56+01:00:00', '2023-02-29T12:34:56',
                     '0000-01-01T00:00:00', '2024-13-01T00:00:00',
                     '2024-01-01T24:00:00', '2024-01-01T00:60:00',
                     '2024-01-01T00:00:60', '２０２４-01-01T00:00:00',
                     '2024-01-01T00:00:00\n', ' 2024-01-01T00:00:00'):
            with self.subTest(text=text), self.assertRaises(ValueError): read_json_date(text, F.ISO)

    def test_iso_offset_bounds(self):
        for suffix in ('+24:00', '-24:00', '+00:60', '+99:99'):
            with self.assertRaises(ValueError): read_json_date('2024-01-01T00:00:00' + suffix, F.ISO)
        self.assertEqual(read_json_date('2024-01-02T00:00:00+23:59', F.ISO), date('20240101000100'))

    def test_read_requires_bounded_exact_string(self):
        class Text(str):
            def __len__(self): raise AssertionError('host hook')
        for value in (None, NULL, True, 0, Decimal(0), [], object(), Text('new Date(0)')):
            with self.assertRaises(TypeError): read_json_date(value, F.JAVASCRIPT)
        with self.assertRaises(ValueError): read_json_date('9' * 10000, F.JAVASCRIPT)

    def test_read_and_write_require_date_format_enum(self):
        for format in (None, NULL, True, 0, 'ISO', V.LOCAL_DATE, object()):
            with self.assertRaises(TypeError): read_json_date('2024-02-29T12:34:56', format)
            with self.assertRaises(TypeError): write_json_date(date('20240229'), format)
        with self.assertRaises(TypeError): read_json_date('2024-02-29T12:34:56')
        with self.assertRaises(TypeError): write_json_date(date('20240229'))

    def test_write_exact_date_and_variant_types(self):
        class DateSubclass(BSLDate): pass
        for value in (None, NULL, True, 0, Decimal(0), '20240229', datetime(2024, 2, 29), DateSubclass(0)):
            with self.assertRaises(TypeError): write_json_date(value, F.ISO)
        for variant in (NULL, True, 0, 'LocalDate', F.ISO, object()):
            with self.assertRaises(TypeError): write_json_date(date('20240229'), F.ISO, variant)

    def test_fractional_and_opaque_boundary_dates_are_not_rounded(self):
        for value in (BSLDate(0, boundary=True), BSLDate(MAX_TICKS, boundary=True),
                      BSLDate(date('20240229').ticks + 1), BSLDate(date('20240229').ticks + 9999)):
            for format in F:
                with self.assertRaises(ValueError): write_json_date(value, format, V.UNIVERSAL_DATE)
        for text, format in (('new Date(1)', F.JAVASCRIPT), ('new Date(-1)', F.JAVASCRIPT),
                             ('/Date(999)/', F.MICROSOFT), ('/Date(-1001)/', F.MICROSOFT)):
            with self.assertRaisesRegex(ValueError, 'дробные'): read_json_date(text, format)

    def test_javascript_guide_wrapper_and_utc_to_local_example(self):
        os.environ[timezones.TIMEZONE_ENV] = 'Europe/Moscow'
        source = date('20140923133540')
        self.assertEqual(read_json_date('new Date(1411464940000)', F.JAVASCRIPT), source)
        self.assertEqual(write_json_date(source, F.JAVASCRIPT, V.UNIVERSAL_DATE), 'new Date(1411464940000)')

    def test_microsoft_optional_slash_escaping(self):
        for text in ('/Date(0)/', r'\/Date(0)\/', r'\/Date(0)/', r'/Date(0)\/'):
            self.assertEqual(read_json_date(text, F.MICROSOFT), date('19700101'))
        self.assertEqual(write_json_date(date('19700101'), F.MICROSOFT, V.UNIVERSAL_DATE), '/Date(0)/')

    def test_epoch_negative_milliseconds_are_not_truncated_towards_zero(self):
        for format, text in ((F.JAVASCRIPT, 'new Date(-1000)'), (F.MICROSOFT, '/Date(-1000)/')):
            source = date('19691231235959')
            self.assertEqual(read_json_date(text, format), source)
            self.assertEqual(write_json_date(source, format, V.UNIVERSAL_DATE), text)

    def test_epoch_utc_full_date_range_and_overflow(self):
        for format in (F.JAVASCRIPT, F.MICROSOFT):
            for source in (BSLDate(0), BSLDate(MAX_TICKS)):
                encoded = write_json_date(source, format, V.UNIVERSAL_DATE)
                self.assertEqual(read_json_date(encoded, format), source)
        for text in ('new Date(-62135596801000)', 'new Date(253402300800000)',
                     'new Date(999999999999999)', 'new Date(9999999999999999)'):
            with self.assertRaises(ValueError): read_json_date(text, F.JAVASCRIPT)

    def test_javascript_and_microsoft_are_data_never_expressions(self):
        for text in ('0', '1411464940000', 'Date(0)', 'new Date()', 'new Date(+0)',
                     'new Date(1e3)', 'new Date(0.0)', 'new Date( 0 )', 'new Date(０)',
                     'new Date(0);doSomething()', 'new Date(__import__("os"))',
                     'new Date(0)\n', 'new Date(0,1)', 'new Date(NaN)', 'New Date(0)'):
            with self.subTest(text=text), self.assertRaises(ValueError): read_json_date(text, F.JAVASCRIPT)
        for text in ('Date(0)', '/Date(0+0100)/', '/date(0)/', '/Date(0)/\n', 'new Date(0)'):
            with self.assertRaises(ValueError): read_json_date(text, F.MICROSOFT)

    def test_non_iso_requires_explicit_universal_variant(self):
        for format in (F.JAVASCRIPT, F.MICROSOFT):
            for variant in (None, V.LOCAL_DATE, V.LOCAL_DATE_WITH_OFFSET):
                with self.assertRaises(ValueError): write_json_date(date('20240229'), format, variant)
            with self.assertRaises(ValueError): write_json_date(date('20240229'), format)

    def test_warsaw_seasonal_offset_and_universal_output(self):
        os.environ[timezones.TIMEZONE_ENV] = 'Europe/Warsaw'
        for source, offset, utc in ((date('20240229123456'), '+01:00', '2024-02-29T11:34:56Z'),
                                    (date('20240701123456'), '+02:00', '2024-07-01T10:34:56Z')):
            self.assertEqual(write_json_date(source, F.ISO, V.LOCAL_DATE_WITH_OFFSET),
                             write_json_date(source, F.ISO) + offset)
            self.assertEqual(write_json_date(source, F.ISO, V.UNIVERSAL_DATE), utc)

    def test_non_hour_offsets_and_date_rollover(self):
        for zone, local, utc, offset in (
            ('Asia/Kathmandu', '20240301021500', '2024-02-29T20:30:00Z', '+05:45'),
            ('America/St_Johns', '20240229213000', '2024-03-01T01:00:00Z', '-03:30'),
            ('Australia/Lord_Howe', '20240701103000', '2024-07-01T00:00:00Z', '+10:30'),
        ):
            os.environ[timezones.TIMEZONE_ENV] = zone
            source = date(local)
            self.assertEqual(read_json_date(utc, F.ISO), source)
            self.assertEqual(write_json_date(source, F.ISO, V.UNIVERSAL_DATE), utc)
            self.assertTrue(write_json_date(source, F.ISO, V.LOCAL_DATE_WITH_OFFSET).endswith(offset))

    def test_configured_dst_gap_and_fold_are_explicitly_unsupported(self):
        os.environ[timezones.TIMEZONE_ENV] = 'Europe/Warsaw'
        for source in (date('20240331023000'), date('20241027023000')):
            for variant in (V.UNIVERSAL_DATE, V.LOCAL_DATE_WITH_OFFSET):
                with self.assertRaisesRegex(ValueError, 'неоднозначное|несуществующее'):
                    write_json_date(source, F.ISO, variant)
        # A known instant can always be converted into its local calendar fields.
        for text in ('2024-10-27T00:30:00Z', '2024-10-27T01:30:00Z'):
            self.assertEqual(read_json_date(text, F.ISO), date('20241027023000'))

    def test_configured_zone_does_not_use_host_or_mutate_timezone(self):
        os.environ['TZ'] = 'host-owned-value'
        os.environ[timezones.TIMEZONE_ENV] = 'Europe/Warsaw'
        expected_environment = dict(os.environ)
        with patch.object(json_dates.time, 'mktime', side_effect=AssertionError('host mktime')), \
                patch.object(json_dates.time, 'localtime', side_effect=AssertionError('host localtime')):
            self.assertEqual(write_json_date(date('20240229123456'), F.ISO, V.UNIVERSAL_DATE),
                             '2024-02-29T11:34:56Z')
            self.assertEqual(read_json_date('2024-02-29T11:34:56Z', F.ISO), date('20240229123456'))
        self.assertEqual(dict(os.environ), expected_environment)

    def test_invalid_configured_zone_fails_closed(self):
        for zone in ('', '../UTC', 'Not/AZone', 'utc'):
            os.environ[timezones.TIMEZONE_ENV] = zone
            with patch.object(json_dates.time, 'mktime', side_effect=AssertionError('host fallback')), \
                    patch.object(json_dates.time, 'localtime', side_effect=AssertionError('host fallback')):
                with self.assertRaises(timezones.TimezoneConfigurationError):
                    write_json_date(date('20240229'), F.ISO, V.UNIVERSAL_DATE)
                with self.assertRaises(timezones.TimezoneConfigurationError):
                    read_json_date('2024-02-29T00:00:00Z', F.ISO)

    def test_historical_offset_seconds_are_dropped_without_rounding(self):
        os.environ[timezones.TIMEZONE_ENV] = 'Europe/Warsaw'
        source = date('19000101123456')
        # Warsaw mean time was +01:24:00; Paris exposes a non-minute offset.
        self.assertEqual(write_json_date(source, F.ISO, V.LOCAL_DATE_WITH_OFFSET), '1900-01-01T12:34:56+01:24')
        os.environ[timezones.TIMEZONE_ENV] = 'Europe/Paris'
        self.assertEqual(write_json_date(source, F.ISO, V.LOCAL_DATE_WITH_OFFSET), '1900-01-01T12:34:56+00:09')
        self.assertEqual(write_json_date(source, F.ISO, V.UNIVERSAL_DATE), '1900-01-01T12:25:35Z')
        os.environ[timezones.TIMEZONE_ENV] = 'America/St_Johns'
        self.assertEqual(write_json_date(source, F.ISO, V.LOCAL_DATE_WITH_OFFSET), '1900-01-01T12:34:56-03:30')
        self.assertEqual(write_json_date(source, F.ISO, V.UNIVERSAL_DATE), '1900-01-01T16:05:48Z')

    def test_unset_zone_uses_host_conversion_without_mutation(self):
        del os.environ[timezones.TIMEZONE_ENV]
        os.environ['TZ'] = 'host-owned-value'
        expected_environment = dict(os.environ)
        offset = 2 * 3600 + 30 * 60 + 17
        def localtime(value): return fields(EPOCH + timedelta(seconds=value + offset)) + (0, 0, 0)
        def mktime(value): return float(seconds(*value[:6]) - offset)
        with patch.object(json_dates.time, 'localtime', side_effect=localtime) as local, \
                patch.object(json_dates.time, 'mktime', side_effect=mktime) as mk:
            source = date('20240229123456')
            self.assertEqual(write_json_date(source, F.ISO, V.LOCAL_DATE_WITH_OFFSET), '2024-02-29T12:34:56+02:30')
            self.assertEqual(write_json_date(source, F.ISO, V.UNIVERSAL_DATE), '2024-02-29T10:04:39Z')
            self.assertEqual(read_json_date('2024-02-29T10:04:39Z', F.ISO), source)
            self.assertTrue(local.called)
            self.assertTrue(mk.called)
        self.assertEqual(dict(os.environ), expected_environment)

    def test_host_dst_fold_is_rejected(self):
        del os.environ[timezones.TIMEZONE_ENV]
        transition = seconds(2024, 10, 27, 1)
        def localtime(value):
            offset = 7200 if value < transition else 3600
            return fields(EPOCH + timedelta(seconds=value + offset)) + (0, 0, int(value < transition))
        def mktime(value):
            return float(seconds(*value[:6]) - (7200 if value[-1] == 1 else 3600))
        with patch.object(json_dates.time, 'localtime', side_effect=localtime), \
                patch.object(json_dates.time, 'mktime', side_effect=mktime), \
                self.assertRaisesRegex(ValueError, 'неоднозначное'):
            write_json_date(date('20241027023000'), F.ISO, V.UNIVERSAL_DATE)

    def test_host_dst_gap_is_rejected(self):
        del os.environ[timezones.TIMEZONE_ENV]
        transition = seconds(2024, 3, 31, 1)
        def localtime(value):
            offset = 3600 if value < transition else 7200
            return fields(EPOCH + timedelta(seconds=value + offset)) + (0, 0, int(value >= transition))
        def mktime(value):
            return float(seconds(*value[:6]) - (7200 if value[-1] == 1 else 3600))
        with patch.object(json_dates.time, 'localtime', side_effect=localtime), \
                patch.object(json_dates.time, 'mktime', side_effect=mktime), \
                self.assertRaisesRegex(ValueError, 'несуществующее'):
            write_json_date(date('20240331023000'), F.ISO, V.UNIVERSAL_DATE)

    def test_host_date_limits_have_clear_errors(self):
        del os.environ[timezones.TIMEZONE_ENV]
        for error in (OverflowError('range'), OSError('host'), ValueError('unsupported')):
            with patch.object(json_dates.time, 'mktime', side_effect=error), \
                    self.assertRaisesRegex(ValueError, 'платформе'):
                write_json_date(BSLDate(0), F.ISO, V.UNIVERSAL_DATE)
            with patch.object(json_dates.time, 'localtime', side_effect=error), \
                    self.assertRaisesRegex(ValueError, 'платформе'):
                read_json_date('0001-01-01T00:00:00Z', F.ISO)

    def test_all_formats_roundtrip_ordinary_whole_seconds(self):
        for zone in ('UTC', 'Europe/Warsaw', 'Asia/Kathmandu', 'America/New_York'):
            os.environ[timezones.TIMEZONE_ENV] = zone
            for source in (date('19700102030405'), date('20000229123456'), date('20240701235959')):
                for format in F:
                    text = write_json_date(source, format, V.UNIVERSAL_DATE)
                    self.assertEqual(read_json_date(text, format), source)
                for variant in (V.LOCAL_DATE, V.LOCAL_DATE_WITH_OFFSET):
                    self.assertEqual(read_json_date(write_json_date(source, F.ISO, variant), F.ISO), source)

    def test_explicit_offset_and_local_overflow_do_not_wrap(self):
        for text in ('0001-01-01T00:00:00+00:01', '9999-12-31T23:59:59-00:01'):
            with self.assertRaises(ValueError): read_json_date(text, F.ISO)
        for zone, source, text in (('Etc/GMT-14', BSLDate(0), '9999-12-31T23:59:59Z'),
                                   ('Etc/GMT+12', BSLDate(MAX_TICKS), '0001-01-01T00:00:00Z')):
            os.environ[timezones.TIMEZONE_ENV] = zone
            with self.assertRaises(ValueError): write_json_date(source, F.ISO, V.UNIVERSAL_DATE)
            with self.assertRaises(ValueError): read_json_date(text, F.ISO)


if __name__ == '__main__':
    unittest.main()
