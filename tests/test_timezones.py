"""Deterministic timezone contracts, not additional native 1C measurements.

Warsaw is the CLDR world-default mapping for the owner's Windows timezone.
Seasonal, historical, foreign-zone and defensive cases below are standalone
implementation policies; the native February 2024 probe is separate evidence.
"""

from datetime import datetime
from decimal import Decimal
from importlib import resources
from io import BytesIO
import os
from pathlib import Path
from struct import error as StructError
import tempfile
import unittest
from unittest.mock import Mock, patch
import zoneinfo

import tzdata

from yadinassi import timezones
from yadinassi.timezones import (
    MAX_ZONE_NAME_LENGTH, TIMEZONE_ENV, TimezoneConfigurationError, local_parts,
)


UNIX_EPOCH = datetime(1970, 1, 1)
MIN_SECONDS = -62135596800
MAX_SECONDS = 253402300799


def unix_seconds(*parts):
    difference = datetime(*parts) - UNIX_EPOCH
    return difference.days * 86400 + difference.seconds


class TimezoneTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        timezones._load_zone.cache_clear()
        self.addCleanup(timezones._load_zone.cache_clear)
        timezones._zone_names.cache_clear()
        self.addCleanup(timezones._zone_names.cache_clear)

    def test_pinned_database_version(self):
        self.assertEqual(tzdata.__version__, '2026.5')
        self.assertEqual(tzdata.IANA_VERSION, '2026e')

    def test_unset_uses_exact_host_sample_without_opening_resources(self):
        fields = (2024, 2, 29, 18, 19, 56, 3, 60, -1)
        with patch.object(timezones.time, 'localtime', return_value=fields) as convert, \
                patch.object(timezones.resources, 'files', side_effect=AssertionError('resource used')):
            self.assertEqual(local_parts(1709210096), fields[:6])
        convert.assert_called_once_with(1709210096)
        self.assertEqual(timezones._load_zone.cache_info().currsize, 0)

    def test_unset_preserves_host_timezone_and_conversion_exceptions(self):
        os.environ['TZ'] = 'host-owned-value'
        for error in (OSError('host failed'), ValueError('bad date'), OverflowError('too large')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(timezones.time, 'localtime', side_effect=error), \
                    self.assertRaises(type(error)) as caught:
                local_parts(0)
            self.assertIs(caught.exception, error)
        self.assertEqual(os.environ, {'TZ': 'host-owned-value'})

    def test_unset_leaves_platform_range_decisions_to_host(self):
        for seconds, fields in ((MIN_SECONDS - 1, (1, 1, 1, 0, 59, 59)),
                                (MAX_SECONDS + 1, (9999, 12, 31, 23, 0, 0)),
                                (10 ** 100, (9999, 12, 31, 23, 59, 59))):
            with self.subTest(seconds=seconds), \
                    patch.object(timezones.time, 'localtime', return_value=fields) as convert:
                self.assertEqual(local_parts(seconds), fields)
            convert.assert_called_once_with(seconds)

    def test_explicit_warsaw_uses_offset_of_converted_season(self):
        os.environ[TIMEZONE_ENV] = 'Europe/Warsaw'
        cases = (((2024, 2, 29, 12, 34, 56), (2024, 2, 29, 13, 34, 56)),
                 ((2024, 7, 1, 12, 34, 56), (2024, 7, 1, 14, 34, 56)),
                 ((2024, 2, 29, 12, 34, 56), (2024, 2, 29, 13, 34, 56)))
        with patch.object(timezones.time, 'localtime', side_effect=AssertionError('host used')), \
                patch.object(timezones.time, 'gmtime', side_effect=AssertionError('C calendar used')), \
                patch.object(timezones.time, 'time', side_effect=AssertionError('today used')), \
                patch.object(timezones.time, 'time_ns', side_effect=AssertionError('today used')):
            for instant, expected in cases:
                self.assertEqual(local_parts(unix_seconds(*instant)), expected)

    def test_warsaw_spring_gap_and_autumn_fold(self):
        os.environ[TIMEZONE_ENV] = 'Europe/Warsaw'
        cases = (((2024, 3, 31, 0, 59, 59), (2024, 3, 31, 1, 59, 59)),
                 ((2024, 3, 31, 1, 0, 0), (2024, 3, 31, 3, 0, 0)),
                 ((2024, 10, 27, 0, 59, 59), (2024, 10, 27, 2, 59, 59)),
                 ((2024, 10, 27, 1, 0, 0), (2024, 10, 27, 2, 0, 0)))
        for instant, expected in cases:
            with self.subTest(instant=instant):
                self.assertEqual(local_parts(unix_seconds(*instant)), expected)

    def test_other_offsets_calendar_rollovers_and_non_hour_dst(self):
        cases = (('Asia/Kathmandu', (2024, 2, 29, 20, 30, 0), (2024, 3, 1, 2, 15, 0)),
                 ('America/St_Johns', (2024, 3, 1, 1, 0, 0), (2024, 2, 29, 21, 30, 0)),
                 ('Australia/Lord_Howe', (2024, 1, 1, 0, 0, 0), (2024, 1, 1, 11, 0, 0)),
                 ('Australia/Lord_Howe', (2024, 7, 1, 0, 0, 0), (2024, 7, 1, 10, 30, 0)),
                 ('Etc/GMT-14', (2023, 12, 31, 12, 0, 0), (2024, 1, 1, 2, 0, 0)),
                 ('Etc/GMT+12', (2024, 1, 1, 0, 0, 0), (2023, 12, 31, 12, 0, 0)))
        for name, instant, expected in cases:
            with self.subTest(zone=name, instant=instant):
                os.environ[TIMEZONE_ENV] = name
                self.assertEqual(local_parts(unix_seconds(*instant)), expected)

    def test_utc_leap_days_pre_epoch_and_full_range(self):
        os.environ[TIMEZONE_ENV] = 'UTC'
        for parts in ((1, 1, 1, 0, 0, 0), (4, 2, 29, 0, 0, 0),
                      (1600, 2, 29, 23, 59, 59), (1900, 3, 1, 0, 0, 0),
                      (1969, 12, 31, 23, 59, 59), (1970, 1, 1, 0, 0, 0),
                      (2000, 2, 29, 12, 34, 56), (2400, 2, 29, 12, 34, 56),
                      (9999, 12, 31, 23, 59, 59)):
            with self.subTest(parts=parts):
                actual = local_parts(unix_seconds(*parts))
                self.assertIs(type(actual), tuple)
                self.assertEqual(actual, parts)
                self.assertTrue(all(type(value) is int for value in actual))

    def test_explicit_range_is_checked_before_resource_lookup(self):
        os.environ[TIMEZONE_ENV] = 'UTC'
        with patch.object(timezones.resources, 'files', side_effect=AssertionError('resource used')):
            for seconds in (MIN_SECONDS - 1, MAX_SECONDS + 1, -(10 ** 100000), 10 ** 100000):
                with self.assertRaises(OverflowError):
                    local_parts(seconds)

    def test_local_overflow_after_offset_is_a_range_error(self):
        for name, seconds in (('Etc/GMT+12', MIN_SECONDS), ('Etc/GMT-14', MAX_SECONDS)):
            os.environ[TIMEZONE_ENV] = name
            with self.subTest(zone=name), self.assertRaises(OverflowError):
                local_parts(seconds)

    def test_only_exact_integer_seconds_without_host_conversion_hooks(self):
        class Hostile:
            def __int__(self):
                raise AssertionError('int hook')

            def __index__(self):
                raise AssertionError('index hook')

            def __float__(self):
                raise AssertionError('float hook')

            def __str__(self):
                raise AssertionError('str hook')

        class IntSubclass(int):
            def __le__(self, other):
                raise AssertionError('comparison hook')

        for name in (None, 'UTC'):
            if name is not None:
                os.environ[TIMEZONE_ENV] = name
            for value in (None, True, False, '0', 0.0, float('inf'), float('nan'),
                          Decimal(0), Decimal('NaN'), [], {}, Hostile(), IntSubclass(0)):
                with self.subTest(zone=name, kind=type(value).__name__), \
                        patch.object(timezones.time, 'localtime', side_effect=AssertionError('host used')), \
                        patch.object(timezones.resources, 'files', side_effect=AssertionError('resource used')), \
                        self.assertRaises(TypeError):
                    local_parts(value)

    def test_empty_absolute_traversal_and_malformed_keys_never_reach_resources(self):
        bad_names = ('', '.', '..', '/UTC', '//UTC', 'Europe/', '/Europe/Warsaw',
                     'Europe//Warsaw', 'Europe/./Warsaw', 'Europe/../UTC', '../UTC',
                     r'Europe\Warsaw', r'C:\Windows\UTC', 'C:/UTC', ' UTC', 'UTC ',
                     'UTC\n', 'UTC\x00', 'Еurope/Warsaw', 'Europe/Warsaw.py',
                     'zone.tab', 'Europe/*', 'Europe/%2e%2e/UTC', 'UTC?x=1',
                     'UTC#x', 'UTC=1', 'A' * (MAX_ZONE_NAME_LENGTH + 1),
                     ('A/' * MAX_ZONE_NAME_LENGTH) + 'UTC')
        with patch.object(timezones.resources, 'files', side_effect=AssertionError('resource used')), \
                patch.object(timezones.time, 'localtime', side_effect=AssertionError('fallback used')):
            for name in bad_names:
                with self.subTest(name=name), \
                        patch.object(timezones.os, 'environ', {TIMEZONE_ENV: name}), \
                        self.assertRaisesRegex(TimezoneConfigurationError, TIMEZONE_ENV):
                    local_parts(0)
        self.assertEqual(timezones._load_zone.cache_info().currsize, 0)

    def test_zone_name_exact_type_guard_avoids_hostile_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('str hook')

            def __hash__(self):
                raise AssertionError('hash hook')

        class HostileStr(str):
            def __len__(self):
                raise AssertionError('len hook')

            def __hash__(self):
                raise AssertionError('hash hook')

        for value in (Hostile(), HostileStr('UTC'), b'UTC', 0, []):
            with self.subTest(kind=type(value).__name__), \
                    patch.object(timezones.os, 'environ', {TIMEZONE_ENV: value}), \
                    patch.object(timezones.resources, 'files', side_effect=AssertionError('resource used')), \
                    self.assertRaises(TimezoneConfigurationError):
                local_parts(0)

    def test_invalid_explicit_zone_never_silently_falls_back(self):
        for name in ('Mars/Olympus_Mons', 'Europe/warsaw', 'Central European Standard Time'):
            os.environ[TIMEZONE_ENV] = name
            with self.subTest(zone=name), \
                    patch.object(timezones.time, 'localtime', side_effect=AssertionError('fallback used')), \
                    self.assertRaises(TimezoneConfigurationError):
                local_parts(0)

    def test_setting_is_reread_between_calls_and_removal_restores_host(self):
        expected = [('UTC', (1970, 1, 1, 0, 0, 0)),
                    ('Asia/Kathmandu', (1970, 1, 1, 5, 30, 0)),
                    ('Europe/Warsaw', (1970, 1, 1, 1, 0, 0)),
                    ('UTC', (1970, 1, 1, 0, 0, 0))]
        for name, fields in expected:
            os.environ[TIMEZONE_ENV] = name
            self.assertEqual(local_parts(0), fields)
        os.environ[TIMEZONE_ENV] = 'Invalid/Zone'
        with self.assertRaises(TimezoneConfigurationError):
            local_parts(0)
        os.environ[TIMEZONE_ENV] = 'Europe/Warsaw'
        self.assertEqual(local_parts(0), (1970, 1, 1, 1, 0, 0))
        del os.environ[TIMEZONE_ENV]
        with patch.object(timezones.time, 'localtime', return_value=(2000, 1, 1, 0, 0, 0)) as host:
            self.assertEqual(local_parts(0), (2000, 1, 1, 0, 0, 0))
        host.assert_called_once_with(0)

    def test_process_timezone_environment_and_settings_are_not_changed(self):
        os.environ.update({TIMEZONE_ENV: 'Europe/Warsaw', 'TZ': 'Pacific/Honolulu',
                           'PYTHONTZPATH': '/untrusted/zoneinfo'})
        before = dict(os.environ)
        with patch.object(timezones.time, 'tzset', create=True,
                          side_effect=AssertionError('process timezone changed')):
            self.assertEqual(local_parts(0), (1970, 1, 1, 1, 0, 0))
        self.assertEqual(dict(os.environ), before)

    def test_resource_api_receives_package_and_validated_path_components(self):
        os.environ[TIMEZONE_ENV] = 'Europe/Warsaw'
        timezones._zone_names()
        root = Mock()
        stream = BytesIO(resources.files(tzdata).joinpath('zoneinfo', 'Europe', 'Warsaw').read_bytes())
        root.joinpath.return_value.open.return_value = stream
        with patch.object(timezones.resources, 'files', return_value=root) as files:
            self.assertEqual(local_parts(0), (1970, 1, 1, 1, 0, 0))
        files.assert_called_once_with(tzdata)
        root.joinpath.assert_called_once_with('zoneinfo', 'Europe', 'Warsaw')
        root.joinpath.return_value.open.assert_called_once_with('rb')
        self.assertTrue(stream.closed)

    def test_resource_failures_are_explicit_and_not_cached(self):
        os.environ[TIMEZONE_ENV] = 'UTC'
        timezones._zone_names()
        failures = (FileNotFoundError('absent'), PermissionError('unreadable'),
                    IsADirectoryError('directory'), OSError('resource failed'),
                    ValueError('bad resource'), EOFError('truncated'), StructError('bad TZif'))
        for stage in ('files', 'joinpath', 'open'):
            for failure in failures:
                root = Mock()
                if stage == 'joinpath':
                    root.joinpath.side_effect = failure
                elif stage == 'open':
                    root.joinpath.return_value.open.side_effect = failure
                with self.subTest(stage=stage, failure=type(failure).__name__), \
                        patch.object(timezones.resources, 'files',
                                     side_effect=failure if stage == 'files' else None,
                                     return_value=root), \
                        self.assertRaises(TimezoneConfigurationError) as caught:
                    local_parts(0)
                self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual(timezones._load_zone.cache_info().currsize, 0)
        # A later successful resource read recovers; failures do not poison it.
        self.assertEqual(local_parts(0), (1970, 1, 1, 0, 0, 0))

    def test_malformed_tzif_is_closed_and_becomes_configuration_error(self):
        os.environ[TIMEZONE_ENV] = 'UTC'
        timezones._zone_names()
        for raw in (b'', b'not TZif', b'TZif', b'TZif2' + bytes(100)):
            root = Mock()
            stream = BytesIO(raw)
            root.joinpath.return_value.open.return_value = stream
            with self.subTest(data=raw), patch.object(timezones.resources, 'files', return_value=root), \
                    self.assertRaises(TimezoneConfigurationError):
                local_parts(0)
            self.assertTrue(stream.closed)

    def test_tzpath_data_cannot_override_bundled_database(self):
        os.environ[TIMEZONE_ENV] = 'Europe/Warsaw'
        original_path = zoneinfo.TZPATH
        self.addCleanup(zoneinfo.reset_tzpath, original_path)
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory, 'Europe', 'Warsaw')
            fake.parent.mkdir()
            fake.write_bytes(resources.files(tzdata).joinpath('zoneinfo', 'UTC').read_bytes())
            zoneinfo.reset_tzpath([directory])
            # Confirm the ambient search path now resolves Warsaw incorrectly.
            ambient = zoneinfo.ZoneInfo.no_cache('Europe/Warsaw')
            self.assertEqual(datetime(2024, 2, 29, tzinfo=ambient).utcoffset().total_seconds(), 0)
            self.assertEqual(local_parts(unix_seconds(2024, 2, 29, 12, 34, 56)),
                             (2024, 2, 29, 13, 34, 56))

    def test_empty_tzpath_and_unusable_zoneinfo_constructor_do_not_matter(self):
        os.environ[TIMEZONE_ENV] = 'Europe/Warsaw'
        original_path = zoneinfo.TZPATH
        self.addCleanup(zoneinfo.reset_tzpath, original_path)
        zoneinfo.reset_tzpath([])
        factory = Mock(side_effect=AssertionError('ambient ZoneInfo constructor used'))
        factory.from_file = zoneinfo.ZoneInfo.from_file
        with patch.object(timezones, 'ZoneInfo', factory):
            self.assertEqual(local_parts(unix_seconds(2024, 7, 1, 12, 0, 0)),
                             (2024, 7, 1, 14, 0, 0))
        factory.assert_not_called()

    def test_zone_cache_is_bounded_and_does_not_cache_instants(self):
        names = [f'Etc/GMT+{offset}' for offset in range(13)]
        names += [f'Etc/GMT-{offset}' for offset in range(1, 5)]
        timezones._zone_names()
        with patch.object(timezones.resources, 'files', wraps=resources.files) as files:
            for name in names:
                os.environ[TIMEZONE_ENV] = name
                local_parts(0)
            self.assertEqual(files.call_count, 17)
            self.assertEqual(timezones._load_zone.cache_info().maxsize, 16)
            self.assertEqual(timezones._load_zone.cache_info().currsize, 16)
            os.environ[TIMEZONE_ENV] = names[-1]
            first, next_second = local_parts(0), local_parts(1)
            self.assertNotEqual(first, next_second)
            self.assertEqual(files.call_count, 17)
            os.environ[TIMEZONE_ENV] = names[0]
            local_parts(0)
            self.assertEqual(files.call_count, 18)

    def test_case_insensitive_resources_cannot_accept_inexact_zone_names(self):
        actual_root = resources.files(tzdata)
        names = actual_root.joinpath('zones').read_text(encoding='ascii').splitlines()
        casefolded = {name.casefold(): name for name in names}
        opened_zones = []

        def case_insensitive_path(*parts):
            if parts == ('zones',):
                return actual_root.joinpath('zones')
            self.assertEqual(parts[0], 'zoneinfo')
            requested = '/'.join(parts[1:])
            opened_zones.append(requested)
            canonical = casefolded[requested.casefold()]
            return actual_root.joinpath('zoneinfo', *canonical.split('/'))

        root = Mock()
        root.joinpath.side_effect = case_insensitive_path
        with patch.object(timezones.resources, 'files', return_value=root):
            # The fake resource provider really resolves case variants, as a
            # default Windows/macOS filesystem would without the catalogue.
            self.assertEqual(case_insensitive_path('zoneinfo', 'Europe', 'warsaw').read_bytes(),
                             actual_root.joinpath('zoneinfo', 'Europe', 'Warsaw').read_bytes())
            opened_zones.clear()
            for name in ('Europe/warsaw', 'europe/Warsaw', 'EUROPE/WARSAW', 'utc'):
                os.environ[TIMEZONE_ENV] = name
                with self.subTest(zone=name), self.assertRaises(TimezoneConfigurationError):
                    local_parts(0)
            self.assertEqual(opened_zones, [])
            os.environ[TIMEZONE_ENV] = 'Europe/Warsaw'
            self.assertEqual(local_parts(0), (1970, 1, 1, 1, 0, 0))
            self.assertEqual(opened_zones, ['Europe/Warsaw'])
            # A prior successful cached canonical lookup cannot admit variants.
            os.environ[TIMEZONE_ENV] = 'Europe/warsaw'
            with self.assertRaises(TimezoneConfigurationError):
                local_parts(0)
            self.assertEqual(opened_zones, ['Europe/Warsaw'])

    def test_catalogue_is_bounded_immutable_and_cached_once(self):
        raw = resources.files(tzdata).joinpath('zones').read_bytes()
        reads = []

        class TrackedStream(BytesIO):
            def read(self, size=-1):
                reads.append(size)
                return super().read(size)

        stream = TrackedStream(raw)
        root = Mock()
        root.joinpath.return_value.open.return_value = stream
        with patch.object(timezones.resources, 'files', return_value=root) as files:
            first = timezones._zone_names()
            self.assertIs(timezones._zone_names(), first)
        self.assertIs(type(first), frozenset)
        self.assertIn('Europe/Warsaw', first)
        self.assertNotIn('Europe/warsaw', first)
        self.assertEqual(reads, [timezones._MAX_ZONE_CATALOG_BYTES + 1])
        self.assertTrue(stream.closed)
        files.assert_called_once_with(tzdata)
        root.joinpath.assert_called_once_with('zones')
        self.assertEqual(timezones._zone_names.cache_info().maxsize, 1)
        self.assertEqual(timezones._zone_names.cache_info().currsize, 1)

    def test_catalogue_errors_never_open_zone_bytes_or_cache_failure(self):
        os.environ[TIMEZONE_ENV] = 'UTC'
        invalid_catalogues = (b'', b'UTC\nUTC\n', b'../UTC\n', b'\xff\n', b'UTC\n\n',
                              b'A' * (MAX_ZONE_NAME_LENGTH + 1),
                              b'A' * (timezones._MAX_ZONE_CATALOG_BYTES + 1),
                              b'UTC\n' * (timezones._MAX_ZONE_CATALOG_ENTRIES + 1))
        for raw in invalid_catalogues:
            root = Mock()
            stream = BytesIO(raw)
            root.joinpath.return_value.open.return_value = stream
            with self.subTest(length=len(raw)), \
                    patch.object(timezones.resources, 'files', return_value=root), \
                    patch.object(timezones, '_load_zone', side_effect=AssertionError('zone opened')), \
                    self.assertRaisesRegex(TimezoneConfigurationError, 'каталог'):
                local_parts(0)
            self.assertTrue(stream.closed)
            self.assertEqual(timezones._zone_names.cache_info().currsize, 0)
        for failure in (OSError('catalogue absent'), PermissionError('unreadable')):
            with patch.object(timezones.resources, 'files', side_effect=failure), \
                    self.assertRaisesRegex(TimezoneConfigurationError, 'каталог') as caught:
                local_parts(0)
            self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual(timezones._zone_names.cache_info().currsize, 0)
        self.assertEqual(local_parts(0), (1970, 1, 1, 0, 0, 0))


if __name__ == '__main__':
    unittest.main()
