"""Authenticated Date/parser observations, with explicit unsupported-policy controls."""
from decimal import Decimal, localcontext, ROUND_DOWN
import hashlib
import json
from pathlib import Path
import unittest

from yadinassi import Interpreter
from yadinassi.dates import BSLDate, date, UnsupportedDateRange
from yadinassi.formatting import format_value
from yadinassi.values import to_string

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/format_dates'
ARCHIVES = {
    'original40': ('5482cefd7c689ab05e04410ea3a701391f350a659dfe8767e118b3c771b678aa', '186c4441a7ce4c3fb70ccd9f4304be7af1bef5d5cb2797eb91b17500881658b8', {35,36}),
    'supplement56': ('7290d1cd2cb6b9f3c77679d8e62a920b87c91417a8569502afe314abb09fa4fb', 'fe558102e1e7f6cf879243b10ec377906d908a784fe2ed497c19826a4359fa8f', {35,36}),
    'parser28': ('606d4932ec82cc57b2465d4a3d344a8dfec776cbc0b5c2ca34e3a1e50a4ef9a9', '565011c01ba0bd70060d2307ce62e3c179886557802551aea35641f988db7b4a', {27}),
}

def output(source):
    lines = []
    Interpreter(lines.append).execute(source.decode())
    return lines


class FormatDatesRuntimeTests(unittest.TestCase):
    def test_all_archived_observations_replayed_with_explicit_policy_controls(self):
        for name, (source_hash, capture_hash, controls) in ARCHIVES.items():
            with self.subTest(archive=name):
                source=(FIXTURE/(name+'.bsl')).read_bytes();raw=(FIXTURE/(name+'.out')).read_bytes()
                self.assertEqual(hashlib.sha256(source).hexdigest(), source_hash)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), capture_hash)
                expected=raw.decode().splitlines();actual=output(source)
                self.assertEqual(len(actual),len(expected))
                self.assertEqual(actual[:2],expected[:2])
                for case,(got,want) in enumerate(zip(actual[2:],expected[2:]),1):
                    if case in controls:
                        self.assertIn('[ok|',want)
                        self.assertEqual(got,f'FD-{case:02}: [action-error]')
                    else:self.assertEqual(got,want,(name,case))

    def test_final_supported56_is_explicit_projection_of_immutable_observations(self):
        mapping=json.loads((FIXTURE/'supported56-mapping.json').read_text())
        source=(FIXTURE/'supported56.bsl').read_bytes()
        self.assertEqual(source,(ROOT/'integrational_tests/measurements/format_dates.bsl').read_bytes())
        self.assertEqual(hashlib.sha256(source).hexdigest(),mapping['source_sha256'])
        self.assertEqual(len(mapping['cases']),56)
        result=output(source);self.assertEqual(len(result),58)
        for case,entry in enumerate(mapping['cases'],1):
            self.assertEqual(entry['case'],case)
            archive=entry['archive'];archived=(FIXTURE/(archive+'.bsl')).read_bytes();captured=(FIXTURE/(archive+'.out')).read_bytes()
            self.assertEqual(hashlib.sha256(archived).hexdigest(),entry['source_sha256'])
            self.assertEqual(hashlib.sha256(captured).hexdigest(),entry['capture_sha256'])
            self.assertNotIn(entry['archive_case'],ARCHIVES[archive][2])
            native=captured.decode().splitlines()[entry['archive_case']+1].split(': ',1)[1]
            self.assertEqual(result[case+1],f'FD-{case:02}: '+native)
        self.assertEqual((mapping['max_encoded_bytes'],mapping['cap']),(8170,8192))

    def test_family_specific_case_and_duplicate_selection(self):
        number=Decimal('1.234')
        self.assertEqual(format_value(number,'nfd=1'),'1,234')
        self.assertEqual(format_value(number,'NFD=1;NFD=2'),'1,23')
        self.assertEqual(format_value(number,'NFD=2;NFD=1'),'1,2')
        value=date('20260102030405')
        self.assertEqual(format_value(value,'DF=yyyy;DF=MM'),'2026')
        self.assertEqual(format_value(value,'DF=MM;DF=yyyy'),'01')
        for mask in ('DF=yyyy;ДФ=MM','ДФ=MM;DF=yyyy'):
            self.assertEqual(format_value(value,mask),'01')
        for mask in ("DE='A';ДП='B'","ДП='B';DE='A'"):
            self.assertEqual(format_value(BSLDate(0),mask),'B')

    def test_empty_date_and_known_boundaries(self):
        empty=BSLDate(0)
        self.assertEqual(format_value(empty),'')
        self.assertEqual(format_value(empty,"DE=''"),'01.01.0001 0:00:00')
        self.assertEqual(format_value(empty,"DE='';DF='yyyy-MM-dd HH:mm:ss'"),'0001-01-01 00:00:00')
        self.assertEqual(format_value(BSLDate(10000),"DE='EMPTY'"),'01.01.0001 0:00:01')
        self.assertEqual(format_value(date('99991231235959'),"DF='yyyy-MM-dd HH:mm:ss'"),'9999-12-31 23:59:59')
        with self.assertRaises(UnsupportedDateRange):format_value(BSLDate(0,boundary=True))
        self.assertEqual(to_string(empty),'01.01.0001 0:00:00')

    def test_token_and_literal_scanner_local_properties(self):
        value=date('20260102030405')
        self.assertEqual(format_value(value,"DF='d dd M MM yy yyyy H HH m mm s ss'"),'2 02 1 01 26 2026 3 03 4 04 5 05')
        self.assertEqual(format_value(value,'DF="yyyy \'year\' MM"'),'2026 year 01')
        self.assertEqual(format_value(value,'DF="yyyy\'\'MM"'),'202601')
        self.assertEqual(format_value(value,'DF="yyyy\';\'MM"'),'2026;01')
        self.assertEqual(format_value(value,'DF=yyyy-MM-dd HH:mm:ss'),to_string(value))
        self.assertEqual(format_value(value,"DF='yyyy-MM-dd HH:mm:ss'"),'2026-01-02 03:04:05')

    def test_unsupported_families_and_malformed_masks_stay_explicit(self):
        value=date('20260102030405')
        for mask in ('DF=MMMM','DF=ddd','DF=hh tt',"DF='hh tt'",'DF=q','DF=yyy','DF=',
                     'DLF=D','L=en',"DF=\"yyyy 'bad\"",'NF=N','nd=2','BF=No'):
            with self.subTest(mask=mask),self.assertRaises(ValueError):format_value(value,mask)
        self.assertEqual(format_value(Decimal('1234.5'),'NFD=1;NG=0;l=en'),'1234,5')

    def test_resource_boundaries_and_numeric_context_preserved(self):
        value=date('20260102030405')
        with self.assertRaises(ValueError):format_value(date('20261030123456'),"DF='"+'d/'*2000+"'")
        with self.assertRaises(ValueError):format_value(BSLDate(0),'DE='+'😀'*2049)
        with localcontext() as ctx:
            ctx.prec=1;ctx.rounding=ROUND_DOWN
            for sig in ctx.traps:ctx.traps[sig]=True
            ctx.clear_flags();before=ctx.copy()
            self.assertEqual(format_value(value,"DF='yyyy-MM-dd HH:mm:ss'"),'2026-01-02 03:04:05')
            self.assertEqual(dict(ctx.flags),dict(before.flags))
            self.assertEqual(dict(ctx.traps),dict(before.traps))

if __name__=='__main__':unittest.main()
