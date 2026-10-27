"""Independent codec measurement instrumentation; no native codec answers."""
import hashlib
import os
from pathlib import Path
import re
import unittest

from scripts.native_historical_replay import TEXT_DOCUMENT_PROBE_BLOCKS, without_text_document_probes
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
import test_native_1c_full_stage as fixtures

ROOT = Path(__file__).resolve().parents[1]
V2_SHA = '50aa6ea564cb9c7c54ea9eb9c99473e3dd4536fabf906ddfa256bb386e08f995'
V3_SHA = '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c'
BLOCKS = (
    ('// Begin bounded UUID codec helpers (candidate; not native evidence).\n', '// End bounded UUID codec helpers.\n\n'),
    ('// Begin bounded UUID codec observations (candidate; not native evidence).\n', '// End bounded UUID codec observations.\n'),
)

def without_codec_blocks(text):
    # Exact test-only inverse to the frozen v2 observation source, not admission.
    if any(boundary in text for pair in TEXT_DOCUMENT_PROBE_BLOCKS for boundary in pair):
        text = without_text_document_probes(text)
    if hashlib.sha256(text.encode()).hexdigest() != V3_SHA:
        raise ValueError('UUID codec candidate source changed')
    for start, end in BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('UUID codec boundaries changed')
        before, tail = text.split(start, 1)
        _, after = tail.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode()).hexdigest() != V2_SHA:
        raise ValueError('UUID codec prior source changed')
    return text

class UUIDCodecMeasurementContract(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT/'integrational_tests/tests/values.bsl').read_bytes()
        self.template = (ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt':
            self.raw = self.raw.replace(b'\r\n', b'\n')
            self.template = self.template.replace(b'\r\n', b'\n')
        self.source = self.raw.decode()
        self.helpers = self.source.split(BLOCKS[0][0])[1].split(BLOCKS[0][1])[0]
        self.block = self.source.split(BLOCKS[1][0])[1]
        self.calls = []
        for line in self.block.splitlines():
            if line.startswith('НаблюдатьКодекUUID('):
                parts = re.findall(r'"((?:[^"]|"")*)"', line)
                self.assertEqual(len(parts), 4)
                self.calls.append(tuple(x.replace('""', '"') for x in parts))

    def test_exact_nine_records_preserve_frozen_v2_and_fresh_count(self):
        previous = without_codec_blocks(self.source)
        self.assertLess(len(without_text_document_probes(self.source).encode()) - len(previous.encode()), 8000)
        self.assertEqual(len(self.calls), 9)
        self.assertEqual({x[0] for x in self.calls}, {
            'internal.fixed', 'internal.zero', 'internal.type',
            'internal.roundtrip.fixed', 'internal.roundtrip.zero',
            'xml.fixed', 'xml.zero', 'xml.roundtrip.fixed', 'xml.roundtrip.zero'})
        self.assertEqual(fixtures.suite.CLIENT_VALUES_MESSAGE_COUNT, 534)
        self.assertEqual(fixtures.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, 946)
        self.assertEqual(hashlib.sha256(without_text_document_probes(self.source).encode()).hexdigest(), V3_SHA)
        with self.assertRaises(fixtures.suite.FullError):
            fixtures.suite.client_values_module(previous.encode(), self.template)

    def test_all_fixed_dynamic_stages_parse_and_verify_input_before_encoding(self):
        parse(self.source)
        for label, setup, encode, decode in self.calls:
            with self.subTest(label=label):
                for code in (setup, encode, decode):
                    parse(code)
                    self.assertNotIn('УникальныйИдентификатор()', code)
                    self.assertNotIn('Сообщить', code)
                fixed = ('00000000-0000-0000-0000-000000000000' if label.endswith('.zero')
                         else '01234567-89ab-4cde-8f01-23456789abcd')
                self.assertIn(f'Новый УникальныйИдентификатор("{fixed}")', setup)
                self.assertIn(f'НРег(Строка(Значение)) <> "{fixed}"', setup)
                self.assertIn('ВызватьИсключение "uuid-fixed-input"', setup)
                self.assertNotIn('Тип("UUID")', setup + encode + decode)
                if label == 'internal.type':
                    self.assertEqual(encode, 'Текст = ЗначениеВСтрокуВнутр(ТипЗнч(Значение));')
                if '.roundtrip.' in label:
                    self.assertIn('Строка(ТипЗнч(Прочитано))', decode)
                    self.assertIn('Строка(Прочитано = Значение)', decode)
                    self.assertNotIn('Строка(Прочитано);', decode)
                else:
                    self.assertEqual(decode, 'Результат = Текст;')

    def vm(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute(BLOCKS[0][0] + self.helpers + BLOCKS[0][1])
        return vm, output

    def observe(self, vm, label, setup, encode, decode):
        args = ', '.join('"' + x.replace('"', '""') + '"' for x in (label, setup, encode, decode))
        vm.execute('НаблюдатьКодекUUID(' + args + ');')

    def test_setup_encoder_decoder_failures_are_distinct_and_next_record_survives(self):
        vm, out = self.vm()
        fail = 'ВызватьИсключение "synthetic";'
        for label, stages in [('setup', (fail, 'Текст = "ok";', 'Результат = Текст;')),
                              ('encode', ('Значение = 1;', fail, 'Результат = Текст;')),
                              ('decode', ('Значение = 1;', 'Текст = "ok";', fail))]:
            self.observe(vm, label, *stages)
        self.observe(vm, 'next', 'Значение = 1;', 'Текст = "bounded";', 'Результат = Текст;')
        self.assertEqual(out, ['uuid.codec.setup: [setup-error]', 'uuid.codec.encode: [encode-error]',
                               'uuid.codec.decode: [decode-error]', 'uuid.codec.next: [bounded]'])

    def test_256_character_bound_rejects_not_truncates_and_blocks_decoder(self):
        vm, out = self.vm()
        self.observe(vm, 'limit', 'Значение = 1;', 'Текст = "'+'a'*256+'";', 'Результат = Текст;')
        self.assertEqual(out.pop(), 'uuid.codec.limit: ['+'a'*256+']')
        self.observe(vm, 'oversized', 'Значение = 1;', 'Текст = "'+'b'*257+'";',
                     'ВызватьИсключение "decoder-must-not-run";')
        self.assertEqual(out.pop(), 'uuid.codec.oversized: [encode-error]')
        self.observe(vm, 'wrongtype', 'Значение = 1;', 'Текст = 17;', 'Результат = Текст;')
        self.assertEqual(out.pop(), 'uuid.codec.wrongtype: [encode-error]')
        self.observe(vm, 'projection', 'Значение = 1;', 'Текст = "ok";', 'Результат = "'+'x'*257+'";')
        self.assertEqual(out.pop(), 'uuid.codec.projection: [decode-error]')
        self.assertNotIn('Лев(', self.helpers)
        self.assertNotIn('Сред(', self.helpers)

    def test_complete_adapter_preserves_codec_body_and_stage_boundaries(self):
        module = fixtures.suite.client_values_module(self.raw, self.template).decode('utf-8-sig')
        self.assertIn(BLOCKS[1][0] + self.block, module)
        self.assertEqual(self.helpers.count('Выполнить('), 3)
        for status in ('setup-error', 'encode-error', 'decode-error'):
            self.assertEqual(module.count('uuid.codec." + Метка + ": [' + status + ']'), 1)

    def test_exact_v2_inverse_rejects_crlf_bom_and_tamper(self):
        for raw in (self.raw.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf'+self.raw, self.raw+b'\n'):
            with self.assertRaises(ValueError):
                without_codec_blocks(raw.decode())
            with self.assertRaises(fixtures.suite.FullError):
                fixtures.suite.client_values_module(raw, self.template)

    def test_production_transport_caps_are_unchanged(self):
        self.assertEqual((fixtures.suite.MAX_STAGE_REPORT, fixtures.suite.MAX_REPORT,
                          fixtures.suite.MAX_OUTPUT, fixtures.suite.MAX_TOTAL,
                          fixtures.suite.MAX_TRANSPORT, fixtures.suite.MAX_RESULT),
                         (8192, 32768, 1048576, 2097152, 3145728, 2097152))
