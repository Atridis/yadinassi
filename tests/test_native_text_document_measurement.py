"""Instrumentation controls only; never expected native TextDocument behavior."""
from decimal import Decimal as D
from pathlib import Path
import hashlib
import os
import re
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.values import BSLObject, HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '16bd5c91f17225906ef9e9e579371b8884eff74dafd67167b06e5a2dda2e55d5'
HELPERS_SHA = 'a33ebfaedf963fd19251e2898c7d0034ee11d8e673ba5fc6f0141641a1e4a086'
CALLS_SHA = '682cbf0abd63990df8ab4a3a6cb0cf73b7f3439ce1afe3bb9c03d506dcf4e09e'
HELPER_START = '// Begin bounded TextDocument helpers (measurement only; no native answers).\n'
HELPER_END = '// End bounded TextDocument helpers.\n\n'
CALL_START = '// Begin bounded TextDocument observations (measurement only; no native answers).\n'
CALL_END = '// End bounded TextDocument observations.\n'


def source_bytes():
    raw = (ROOT / 'integrational_tests/tests/values.bsl').read_bytes()
    # Offline fixture checkout normalization only; production remains LF strict.
    return raw.replace(b'\r\n', b'\n') if os.name == 'nt' else raw


def fragments():
    text = source_bytes().decode('utf-8')
    helpers = HELPER_START + text.split(HELPER_START)[1].split(HELPER_END)[0] + HELPER_END
    calls = CALL_START + text.split(CALL_START)[1].split(CALL_END)[0] + CALL_END
    return helpers, calls


def records():
    result = []
    for line in fragments()[1].splitlines():
        if line.startswith('НаблюдатьТекстовыйДокумент('):
            parts = re.findall(r'"((?:[^"]|"")*)"', line)
            assert len(parts) == 4
            result.append(tuple(part.replace('""', '"') for part in parts))
    return result

def quote(s): return '"'+s.replace('"','""')+'"'

class InstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.out=[]
        self.vm=Interpreter(self.out.append)
        self.helpers = fragments()[0]
        self.vm.execute(self.helpers)

    def observe(self,label,setup='Документ = Неопределено;',action='Ответ = Неопределено;',readback='Пост = "none";'):
        self.vm.execute('НаблюдатьТекстовыйДокумент('+', '.join(map(quote,(label,setup,action,readback)))+');')

    def test_matrix_is_input_only_parses_and_is_bounded(self):
        calls = fragments()[1]
        rows = records()
        self.assertEqual(len(rows), 44)
        self.assertEqual(len({row[0] for row in rows}), 44)
        parse(self.helpers + calls)
        for label, setup, action, readback in rows:
            for code in (setup, action, readback):
                parse(code)
                for forbidden in ('Сообщить', 'ОписаниеОшибки', 'ЗначениеВСтрокуВнутр',
                                  '.Read(', '.Write(', '.Прочитать(', '.Записать('):
                    self.assertNotIn(forbidden, code)
            self.assertLess(len(label), 40)
        self.vm.execute(calls)
        self.assertEqual(len(self.out), 44)

    def test_utf16_encoding_is_lossless_not_normalized(self):
        for s,expected in [('', '0:'), ('A', '1:0041'), ('A\r\nБ😀', '6:0041000d000a0411d83dde00'),('é','2:00650301')]:
            self.vm.variables['probe']=s
            self.assertEqual(self.vm.execute('КодыТекстовогоДокумента(probe)'),expected)
        self.vm.variables['probe']='x'*65
        with self.assertRaises(BSLError):self.vm.execute('КодыТекстовогоДокумента(probe)')

    def test_result_tags_do_not_conflate_empty_undefined_number_or_boolean(self):
        for value,expected in [(None,'U'), ('','S0:'), ('1','S1:0031'), (D(1),'N1')]:
            self.vm.variables['probe']=value
            self.assertEqual(self.vm.execute('ОтветТекстовогоДокумента(probe)'),expected)
        for value in [True, D(9),D('0.5')]:
            self.vm.variables['probe']=value
            with self.assertRaises(BSLError):self.vm.execute('ОтветТекстовогоДокумента(probe)')

    def test_stage_statuses_and_next_record_survive(self):
        bad='ВызватьИсключение "synthetic";'
        self.observe('setup',setup=bad)
        self.observe('action',action=bad)
        self.observe('readback',readback=bad)
        self.observe('both',action=bad,readback=bad)
        self.observe('next',action='Ответ = "A";')
        self.assertEqual(self.out,['textdoc.setup: [setup-error]',
           'textdoc.action: [action-error|R=U|none]',
           'textdoc.readback: [readback-error|ok]',
           'textdoc.both: [readback-error|action-error]',
           'textdoc.next: [ok|R=S1:0041|none]'])

    def test_snapshot_readers_are_independent_and_partial_mutation_is_visible(self):
        # Fake methods deliberately inconsistent: these are harness controls,
        # not a TextDocument model or proposed native semantic expectations.
        class Witness(BSLObject):
            def __init__(self):self.text='before'; self.calls=[]
            def get_member(self,name):
                def count():self.calls.append('count'); return D(2)
                def text():self.calls.append('text'); return self.text
                def line(i):
                    self.calls.append(('line',i))
                    if i==D(1):raise ValueError('synthetic')
                    return 'Q'
                return HostFunction(name, {'количествострок':count,'получитьтекст':text,'получитьстроку':line}[name.casefold()])
        w=Witness()
        self.vm.register_function('GetWitness',lambda:w)
        def mutate():w.text='X'; raise ValueError('synthetic')
        self.vm.register_function('MutateWitness',mutate)
        self.observe('partial',setup='Документ = GetWitness();',action='MutateWitness();',readback='Пост = СнимокТекстовогоДокумента(Документ);')
        self.assertEqual(self.out,['textdoc.partial: [action-error|R=U|C=2|T=1:0058|L=1=line-error,2=1:0051]'])
        self.assertEqual(w.calls,['count','text',('line',D(1)),('line',D(2))])

    def test_record_size_failure_is_explicit_not_truncated(self):
        self.observe('long',readback='Пост = '+quote('x'*1024)+';')
        self.assertEqual(self.out,['textdoc.long: [readback-error|ok]'])



class TextDocumentSourceContracts(unittest.TestCase):
    def test_exact_current_source_blocks_and_counts(self):
        import test_native_1c_full_stage as f
        from scripts.native_historical_replay import without_text_document_probes, without_uuid_probes
        raw = source_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA)
        helpers, calls = fragments()
        self.assertEqual(hashlib.sha256(helpers.encode()).hexdigest(), HELPERS_SHA)
        self.assertEqual(hashlib.sha256(calls.encode()).hexdigest(), CALLS_SHA)
        self.assertEqual(len(raw.splitlines()), 1225)
        self.assertEqual(f.suite.CLIENT_VALUES_MESSAGE_COUNT, 534)
        self.assertEqual(f.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, 1021)
        previous = without_text_document_probes(raw.decode())
        self.assertEqual(hashlib.sha256(previous.encode()).hexdigest(),
                         '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c')
        from scripts.native_historical_replay import without_nstr_probes
        self.assertLess(len(without_nstr_probes(raw.decode()).encode()) - len(previous.encode()), 22000)
        self.assertEqual(hashlib.sha256(without_uuid_probes(raw.decode()).encode()).hexdigest(),
                         'dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12')

    def test_empty_trailing_breaks_and_aliases_are_separate_observations(self):
        rows = {label: (setup, action, readback) for label, setup, action, readback in records()}
        for label in ('set.empty', 'set.lf', 'set.cr', 'set.crlf', 'set.trailing.lf',
                      'set.trailing.cr', 'set.trailing.crlf', 'set.only.breaks', 'set.unicode',
                      'add.after.trailing.crlf', 'get.empty.one', 'delete.only', 'clear.empty'):
            self.assertIn(label, rows)
        for name in ('SetText', 'GetText', 'GetLine', 'LineCount', 'AddLine',
                     'InsertLine', 'ReplaceLine', 'DeleteLine', 'Clear'):
            self.assertIn('.' + name + '(', fragments()[1])
        for family in ('get', 'insert', 'replace', 'delete'):
            self.assertIn('(0', rows[family + '.zero'][1])
            self.assertIn('КоличествоСтрок() + ', rows[family + '.past'][1])
        self.assertEqual(rows['type.ru'][0], 'Документ = Неопределено;')
        self.assertEqual(rows['type.en'][0], 'Документ = Неопределено;')

    def test_live_adapter_preserves_every_probe_and_rejects_old_and_changed_source(self):
        import test_native_1c_full_stage as f
        from scripts.native_historical_replay import without_text_document_probes, without_uuid_probes
        raw = source_bytes()
        template = (ROOT / f.suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt': template = template.replace(b'\r\n', b'\n')
        module = f.suite.client_values_module(raw, template)
        self.assertIn(fragments()[1].encode(), module)
        for label, setup, action, readback in records():
            for code in (setup, action, readback):
                self.assertIn(quote(code).encode(), module)
        for changed in (raw + b'\n', raw.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + raw,
                        without_text_document_probes(raw.decode()).encode(),
                        without_uuid_probes(raw.decode()).encode()):
            with self.subTest(sha=hashlib.sha256(changed).hexdigest()):
                with self.assertRaises(f.suite.FullError):
                    f.suite.client_values_module(changed, template)
                with self.assertRaises(ValueError):
                    without_text_document_probes(changed.decode())

    def test_exact_441_and_402_adapters_are_separate_from_current_534(self):
        import test_native_1c_full_stage as f
        from test_native_async_fixture import (historical_text_document_values_module,
                                              historical_uuid_values_module,
                                              without_text_document_measurement)
        raw = source_bytes()
        template = (ROOT / f.suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt': template = template.replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(historical_text_document_values_module(raw, template)).hexdigest(),
                         '433a2db811bab637ab666e5a0cbdeb9eeeffd158534b223dfa34f0389b9cc282')
        self.assertEqual(hashlib.sha256(historical_uuid_values_module(raw, template)).hexdigest(),
                         '814858ce2af10afc86882ec719a19f41589effabb71b83882d94d6077d90e824')
        for host, name in ((True, 'scripts/native_1c_full_host.py'),
                           (False, 'scripts/native_1c_bootstrap/full_suite.py')):
            source = (ROOT / name).read_text(encoding='utf-8')
            without_text_document_measurement(source, host=host)
            with self.assertRaises(AssertionError):
                without_text_document_measurement(source + '\n', host=host)

    def test_caps_and_historical_fixtures_remain_unextended(self):
        import test_native_1c_full_stage as f
        self.assertEqual((f.suite.MAX_STAGE_REPORT, f.suite.MAX_REPORT,
                          f.suite.MAX_OUTPUT, f.suite.MAX_TOTAL,
                          f.suite.MAX_TRANSPORT, f.suite.MAX_RESULT),
                         (8192, 32768, 1048576, 2097152, 3145728, 2097152))
        # Even the worst admitted projection payload across all new records
        # remains a small fraction of the unchanged one-megabyte output budget.
        self.assertLess(44 * (1024 + 64), f.suite.MAX_OUTPUT // 16)


if __name__ == '__main__': unittest.main()
