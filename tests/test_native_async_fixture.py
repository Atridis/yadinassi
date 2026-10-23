"""Offline source contracts only; no claim of native BSL compilation/execution."""
import ast
import hashlib
import json
import re
from pathlib import Path

import unittest

REPOSITORY = Path(__file__).resolve().parents[1]
SNIPPET = REPOSITORY / 'scripts' / 'native_1c_bootstrap' / 'full_suite.py'
# Independent frozen inventory/DAG, not derived from the implementation's constants.
FROZEN_SPEC = {'slots': [4, 3, 5, 3, 4, 7, 3, 3],
 'cases': [{'id': 0,
            'required': [10, 11, 12, 13, 14, 15, 16, 17, 18],
            'edges': [[10, 11],
                      [11, 12],
                      [10, 13],
                      [13, 14],
                      [12, 14],
                      [14, 15],
                      [15, 16],
                      [16, 17],
                      [17, 18]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 1,
            'required': [10, 11, 12, 13, 14, 15, 16, 17, 25, 26],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 25],
                      [25, 26],
                      [26, 13],
                      [13, 14],
                      [14, 17],
                      [10, 15],
                      [15, 16],
                      [16, 17]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 2,
            'required': [10,
                         11,
                         12,
                         13,
                         14,
                         15,
                         16,
                         17,
                         18,
                         19,
                         20,
                         21,
                         22,
                         23,
                         24,
                         25,
                         26,
                         27,
                         28],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 25],
                      [25, 26],
                      [26, 13],
                      [13, 14],
                      [14, 22],
                      [10, 15],
                      [15, 16],
                      [16, 17],
                      [17, 18],
                      [18, 27],
                      [27, 28],
                      [28, 19],
                      [19, 20],
                      [20, 23],
                      [16, 21],
                      [21, 22],
                      [22, 23],
                      [23, 24]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 3,
            'required': [10, 13, 16],
            'edges': [[10, 11],
                      [10, 12],
                      [11, 13],
                      [12, 13],
                      [13, 14],
                      [13, 15],
                      [14, 16],
                      [15, 16],
                      [16, 17],
                      [16, 18]],
            'choices': [[11, 12], [14, 15], [17, 18]],
            'error_slot_phases': [[0, 3], [1, 4], [2, 5]]},
           {'id': 4,
            'required': [10, 11, 12, 13, 14, 15, 16, 19],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 13],
                      [11, 14],
                      [14, 16],
                      [10, 15],
                      [15, 16],
                      [16, 17],
                      [16, 18],
                      [17, 19],
                      [18, 19],
                      [13, 19]],
            'choices': [[17, 18]],
            'error_slot_phases': []},
           {'id': 5,
            'required': [10, 11, 12, 13, 14, 15, 16],
            'edges': [[10, 11], [11, 12], [12, 13], [13, 14], [14, 16], [10, 15], [15, 16]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 6,
            'required': [10, 11, 12],
            'edges': [[10, 11],
                      [11, 12],
                      [10, 13],
                      [12, 14],
                      [13, 15],
                      [15, 16],
                      [15, 17],
                      [12, 16],
                      [12, 17],
                      [16, 18],
                      [17, 18],
                      [18, 19],
                      [18, 20],
                      [12, 19],
                      [12, 20]],
            'choices': [[13, 14], [16, 17], [19, 20]],
            'error_slot_phases': [[0, 0], [1, 1], [2, 2]]},
           {'id': 7,
            'required': [10, 11, 12, 13, 14, 15, 16, 17, 18],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 13],
                      [13, 14],
                      [14, 15],
                      [15, 16],
                      [16, 17],
                      [17, 18]],
            'choices': [],
            'error_slot_phases': [[2, 6]]}]}


def literal_sources():
    tree = ast.parse(SNIPPET.read_text(encoding='utf-8'))
    names = ('ASYNC_TEMPLATE', 'ASYNC_CASE_SOURCES', 'ASYNC_FIXTURE_SHA256')
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    assert target.id not in result
                    result[target.id] = ast.literal_eval(node.value)
    assert set(result) == set(names)
    return result


def make_fixture():
    sources = literal_sources()
    # Test the repository generator definition in an isolated namespace. This is
    # offline test code only: production host extraction must not execute staged
    # code, and the independent host protocol tests cover that boundary.
    namespace = dict(sources)
    import json
    namespace.update(hashlib=hashlib, json=json)
    class FullError(Exception):
        pass
    namespace['FullError'] = FullError
    namespace['generated_module'] = lambda raw: raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8-sig')
    tree = ast.parse(SNIPPET.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'async_client_module')
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SNIPPET), 'exec'), namespace)
    return namespace


def routine(source, name):
    # BSL mixed-case routine declarations, deliberately no BSL execution here.
    pattern = (r'(?im)^\s*(?:Асинх\s+|Async\s+)?(?:Процедура|Функция|Procedure|Function)\s+'
               + re.escape(name) + r'\([^\n]*\)\s*\n(.*?)^\s*(?:КонецПроцедуры|КонецФункции|EndProcedure|EndFunction)\s*$')
    match = re.search(pattern, source, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)
    assert match, name
    return match.group(1)




def without_error_payload_sentinels(source):
    # Exact inverse of the twelve transport-only sentinels, not semantic Null.
    assert source.count('АсинхПара(0, Неопределено)') == 11
    assert source.count('АсинхПара(1, Неопределено)') == 1
    assert not re.search(r'АсинхПара\([01], Null\)', source)
    return re.sub(r'АсинхПара\(([01]), Неопределено\)',
                  r'АсинхПара(\1, Null)', source)


def without_local_request_key(template):
    start = template.index('Function AsyncReadRequest(ЭтапВхода)\n')
    end = template.index('EndFunction', start) + len('EndFunction')
    body = template[start:end]
    declaration = '    Var AsyncRequestKey;\n'
    assert body.count(declaration) == 1
    assert not re.search(r'\bKey\b', body)
    body = body.replace(declaration, '')
    body, count = re.subn(r'\bAsyncRequestKey\b', 'Key', body)
    assert count == 8
    return template[:start] + body + template[end:]


def without_ru_request_end_token(template):
    template = without_error_payload_sentinels(template)
    current = '    AsyncRequestEndToken = ТипЗначенияJSON.КонецОбъекта;\n'
    previous = '    AsyncRequestEndToken = JSONValueType.ObjectEnd;\n'
    assert template.count(current) == 1
    assert previous not in template
    return template.replace(current, previous)


def without_inline_request_end(template):
    template = without_ru_request_end_token(template)
    # Restore the exact previous helper boundary, not just equivalent operations.
    declaration = '    Var AsyncRequestKey, AsyncRequestEndToken;\n'
    assert template.count(declaration) == 1
    template = template.replace(declaration, '    Var AsyncRequestKey;\n')
    inline = ('    AsyncRequestEndToken = JSONValueType.ObjectEnd;\n'
              '    ЭтапВхода = "request_end_read";\n'
              '    If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;\n'
              '    ЭтапВхода = "request_end_token";\n'
              '    If Reader.CurrentValueType <> AsyncRequestEndToken Then Raise "ASYNC-REQUEST"; EndIf;\n')
    assert template.count(inline) == 1
    template = template.replace(inline,
        '    AsyncExpectRequestEnd(Reader, JSONValueType.ObjectEnd, ЭтапВхода);\n')
    assert 'AsyncRequestEndToken' not in template
    helper = ('&AtClient\nProcedure AsyncExpectRequestEnd(Reader, Val Token, ЭтапВхода)\n'
              '    ЭтапВхода = "request_end_read";\n'
              '    If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;\n'
              '    ЭтапВхода = "request_end_token";\n'
              '    If Reader.CurrentValueType <> Token Then Raise "ASYNC-REQUEST"; EndIf;\n'
              'EndProcedure\n\n')
    insertion = '&AtClient\nFunction AsyncReadRequest(ЭтапВхода)\n'
    assert template.count(insertion) == 1
    assert 'Procedure AsyncExpectRequestEnd' not in template
    return template.replace(insertion, helper + insertion)


def without_request_end_diagnostic(template):
    helper = ('&AtClient\nProcedure AsyncExpectRequestEnd(Reader, Val Token, ЭтапВхода)\n'
              '    ЭтапВхода = "request_end_read";\n'
              '    If Not Reader.Read() Then Raise "ASYNC-REQUEST"; EndIf;\n'
              '    ЭтапВхода = "request_end_token";\n'
              '    If Reader.CurrentValueType <> Token Then Raise "ASYNC-REQUEST"; EndIf;\n'
              'EndProcedure\n\n')
    assert template.count(helper) == 1
    template = template.replace(helper, '')
    template = template.replace('ЭтапВхода = "request_end_call";',
                                'ЭтапВхода = "request_end";')
    template = template.replace(
        'AsyncExpectRequestEnd(Reader, JSONValueType.ObjectEnd, ЭтапВхода);',
        'AsyncExpectToken(Reader, JSONValueType.ObjectEnd);')
    for label in ('trailing', 'close'):
        addition = f'    ЭтапВхода = "request_end_{label}";\n'
        assert template.count(addition) == 1
        template = template.replace(addition, '')
    return template


def without_request_site_diagnostic(template):
    start = template.index('&AtClient\nProcedure AsyncExpectRequestKey')
    end = template.index('&AtClient\nFunction AsyncReadRequest', start)
    template = template[:start] + template[end:]
    template = template.replace(
        'AsyncExpectRequestKey(Reader, JSONValueType.PropertyName, ЭтапВхода, Index);',
        'AsyncExpectToken(Reader, JSONValueType.PropertyName);')
    for name in ('current', 'property'):
        addition = (f'        If Index = 1 Then\n'
                    f'            ЭтапВхода = "request_key_{name}_first";\n'
                    f'        Else\n'
                    f'            ЭтапВхода = "request_key_{name}_later";\n'
                    f'        EndIf;\n')
        assert template.count(addition) == 1
        template = template.replace(addition, '')
    return template.replace('ЭтапВхода = "request_key_call";',
                            'ЭтапВхода = "request_key";')


class AsyncFixtureSourcesTest(unittest.TestCase):
    def test_error_payload_change_restores_exact_reviewed_production_sources(self):
        from test_native_async_protocol import full
        fixture = literal_sources()
        previous_aggregate = 'dc3cd3368ef737d4566eec13e9a4103f5fc26ff3c44ba4fc3d06bcd2adba3705'
        previous_identity = {'template': 'c60b81e77e69f20ce3bd3ee36ea0d7e44f5bea38639d8ded7e32fab74a9846b6', 'modules': ['80a842b78f20c6a52d7f68f9a8a0a52bde8316a497bc2033c68af4474fcc6c8a', 'd0820a1eed7a700916f6d070e27b19df2b85ba0386273f99d88784a79c7d8fb2', 'ae10664360da0c5242cfd77d1be01ee0fd9c74514598fec1c436635b2e8c3490', '52f4ef3fa979630bc0be401ddfe508a89ed7c1713a1d3b632c5f6f86d7528167', '49aaf7135bf9cf3a25e0c640e6b68936b2a7e1f7c126a0a25259a83e41e996a4', 'da305166b522673f1333c7cfdd375c7857d0cf4959f3c198758f4d82e69dad36', 'd6f5e0f89bbb8972386401504b1b0f9d74d7c5f7e583c391eb1c7e425c370046', '5ff92eac867884b73410f9312ade405cf44ed8b62ce019e53275bd53adaeff8b']}
        source = without_error_payload_sentinels(SNIPPET.read_text(encoding='utf-8'))
        current_pin = 'ASYNC_FIXTURE_SHA256 = ' + repr(fixture['ASYNC_FIXTURE_SHA256'])
        self.assertEqual(source.count(current_pin), 1)
        source = source.replace(current_pin, 'ASYNC_FIXTURE_SHA256 = ' + repr(previous_aggregate))
        # Published a61f376 / tree b555f4f, plus exact main 0dbb938 changes.
        # Only the audited ordinary object witness, bool transport and legacy
        # adapter inverse differ from that historical production-source pin.
        self.assertEqual(hashlib.sha256(source.encode('utf-8')).hexdigest(),
                         'ea93b15df0cb9fd312534ffe0b28acb111a0f97a8f02431205e597d8f858f940')
        # Host footprint also includes reviewed same-run Async comparator wiring;
        # the native source and literal fixture pins above remain unchanged.
        host = (REPOSITORY / 'scripts' / 'native_1c_full_host.py').read_text(encoding='utf-8')
        self.assertEqual(host.count(fixture['ASYNC_FIXTURE_SHA256']), 1)
        host = host.replace(fixture['ASYNC_FIXTURE_SHA256'], previous_aggregate)
        current_identity = 'ASYNC_EXPECTED_IDENTITY = ' + repr(full.ASYNC_EXPECTED_IDENTITY)
        self.assertEqual(host.count(current_identity), 1)
        host = host.replace(current_identity, 'ASYNC_EXPECTED_IDENTITY = ' + repr(previous_identity))
        self.assertEqual(hashlib.sha256(host.encode('utf-8')).hexdigest(),
                         'a95ce9e74726d88b9d5467ef91e1b6d4bb4ffb57d826cddc01ffc94c8480b144')
        self.assertEqual(hashlib.sha256(json.dumps(fixture['ASYNC_CASE_SOURCES'], ensure_ascii=False,
                         separators=(',', ':')).encode('utf-8')).hexdigest(),
                         '09edb17d68c0ff7a5462498b132afa5c2b202912abdcb48e33ae1c676a39c075')
        self.assertEqual(fixture['ASYNC_FIXTURE_SHA256'], '83a6e22dbb4788498985e51e06ea610d2a9bc95702852da396cb6d7779bf1c5a')
        self.assertEqual(full.ASYNC_EXPECTED_IDENTITY, {'template': '4177f7bc3e4690e6a67e48af06db4dba78405bb76f16151867fd006c35ba713f', 'modules': ['9c35b55df6f304166f83535490b7cffe51f0bac3383663fa4d2c201dfd4f3317', '2f1521d54fef7ecd73f8dce7f36f983111ff2fdb98112a89bd47f01988072676', '6e1a01c33d77681426c6d3f0c0d648fde353514edad381ba2c6bd2b586284959', 'a3959ce4beb9fe01cc1d3f3416bdb2ac7ef56ecb9cdcce11c0b41d96f347bc78', 'a5a2d09e4a7be7749121b0a26c30670bcd122d76ae81e6b5158fdb9de7ff2b1b', '761b8ed069ac9451cd9eb918c5e7e7d6d84a9d380155bc56b36ffd05717d76f6', '395dfd07a0171d361fd5c029e6a2400ef8d72097f506e073c75fedb1bc3105f4', '3ac1cd874da474e939006034f5a7216e7d2a26e9f9a9fb87f0c0813b1968a45a']})

    def test_marker_validation_diagnostics_preserve_previous_native_fixture_bytes(self):
        fixture = literal_sources()
        # Pinned from head 7af481f/tree 6ebcb7a before the Python-only
        # diagnostic change, not recomputed from the new implementation.
        self.assertEqual(hashlib.sha256(without_error_payload_sentinels(fixture['ASYNC_TEMPLATE']).encode('utf-8')).hexdigest(),
                         'c60b81e77e69f20ce3bd3ee36ea0d7e44f5bea38639d8ded7e32fab74a9846b6')
        self.assertEqual(hashlib.sha256(json.dumps(fixture['ASYNC_CASE_SOURCES'], ensure_ascii=False,
                         separators=(',', ':')).encode('utf-8')).hexdigest(),
                         '09edb17d68c0ff7a5462498b132afa5c2b202912abdcb48e33ae1c676a39c075')
        self.assertEqual(hashlib.sha256(json.dumps(
            [without_error_payload_sentinels(fixture['ASYNC_TEMPLATE']), fixture['ASYNC_CASE_SOURCES']],
            ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest(),
            'dc3cd3368ef737d4566eec13e9a4103f5fc26ff3c44ba4fc3d06bcd2adba3705')
        source = SNIPPET.read_text(encoding='utf-8')
        functions = [node for node in ast.parse(source).body
                     if isinstance(node, ast.FunctionDef) and node.name == 'async_client_module']
        self.assertEqual(len(functions), 1)
        self.assertEqual(hashlib.sha256(ast.get_source_segment(source, functions[0]).encode('utf-8')).hexdigest(),
                         '41e7ce33d37ca353bb32eeb5385f43f9827607c8421f6b9a886972257da8fa6b')
        request = "expected = {'schema':1,'version':1,'nonce':nonce,'entered':str(entered),'completed':str(completed)}"
        self.assertEqual(source.count(request), 1)

    def test_russian_end_token_expression_is_the_only_template_change(self):
        fixture = literal_sources()
        restored = without_ru_request_end_token(fixture['ASYNC_TEMPLATE'])
        self.assertEqual(hashlib.sha256(restored.encode('utf-8')).hexdigest(),
                         '19e6444a1856d5f4b8769a80f9ed97df0a042559e8255849635dff083dc8aba4')
        self.assertEqual(hashlib.sha256(json.dumps(
            [restored, fixture['ASYNC_CASE_SOURCES']], ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')).hexdigest(),
            '6ecaab71ff8e580a26da2a30d3fb35e9aea4a37d2bd690008e42fa8e806532bb')

    def test_marker_diagnostics_and_russian_end_token_have_reviewed_source_pins(self):
        from test_native_async_protocol import full
        fixture = literal_sources()
        # Normalize only the pre-existing end-token/pin delta; these exact
        # source hashes additionally pin the reviewed Python-only diagnostic and
        # exact main 0dbb938 ordinary object witness/adapter integration.
        previous_aggregate = '6ecaab71ff8e580a26da2a30d3fb35e9aea4a37d2bd690008e42fa8e806532bb'
        previous_identity = {'template': '19e6444a1856d5f4b8769a80f9ed97df0a042559e8255849635dff083dc8aba4', 'modules': ['b72afebe539cd97cd3eebc28c2aaf6866375609f3bb15f6433c69fb2dd5f99f7', '8df02833ca425b23f81c8b318f0af6ac05605d39f4c008b7e753206ed1c5374b', 'bff8fc309d743edd5e2aad989acc69d9fc142cab4f6cb11164edc73a9b6ead57', '311e8e0483ebbb69f34beb1c71d44ce61a56caf362d180c13e1f744ceb5a7aa6', '0f60e947518b7140f56973fccb631e167309ca36d2da10ce41355e9bdf41be61', 'a2b82d56e4f705b0bef66955b35d279a788da1cf2295f28af278d4a381a5f755', '9dd42db7bca81ed3e36ae12602693f8f5e5efcaf71e37a77e5a6e582b03355f9', '028492c644622ed2e8e79d9b65d8f6b8566b2a4e202088272ff0c391e2203df8']}
        source = without_ru_request_end_token(SNIPPET.read_text(encoding='utf-8'))
        current_pin = 'ASYNC_FIXTURE_SHA256 = ' + repr(fixture['ASYNC_FIXTURE_SHA256'])
        self.assertEqual(source.count(current_pin), 1)
        source = source.replace(current_pin, 'ASYNC_FIXTURE_SHA256 = ' + repr(previous_aggregate))
        self.assertEqual(hashlib.sha256(source.encode('utf-8')).hexdigest(),
                         '048f5e2efa484811e3448e0f4334a679991bb0c464da3125ec0abf36cfd93e3d')
        # Host footprint also includes reviewed same-run Async comparator wiring;
        # the native source and literal fixture pins above remain unchanged.
        host = (REPOSITORY / 'scripts' / 'native_1c_full_host.py').read_text(encoding='utf-8')
        self.assertEqual(host.count(fixture['ASYNC_FIXTURE_SHA256']), 1)
        host = host.replace(fixture['ASYNC_FIXTURE_SHA256'], previous_aggregate)
        current_identity = 'ASYNC_EXPECTED_IDENTITY = ' + repr(full.ASYNC_EXPECTED_IDENTITY)
        self.assertEqual(host.count(current_identity), 1)
        host = host.replace(current_identity, 'ASYNC_EXPECTED_IDENTITY = ' + repr(previous_identity))
        self.assertEqual(hashlib.sha256(host.encode('utf-8')).hexdigest(),
                         'ee7cfa1b7f0a082d1b91ab38f805c332d97a0933b0dd8bb9e0d8199cd522acff')

    def test_inline_end_operations_are_the_only_template_change(self):
        fixture = make_fixture()
        restored = without_inline_request_end(fixture['ASYNC_TEMPLATE'])
        self.assertEqual(hashlib.sha256(restored.encode('utf-8')).hexdigest(),
                         'cdef1ae4d6fc78de8e14e81e87dd67795c0c2c8f20ecb72aefabf338f48bdb89')
        self.assertEqual(hashlib.sha256(json.dumps(
            [restored, fixture['ASYNC_CASE_SOURCES']], ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')).hexdigest(),
            'd3d3708f0ab82393a689319f1ce1f2b33f6f612da50524055444c3628b084f5f')

    def test_end_diagnostics_are_the_only_template_change(self):
        fixture = make_fixture()
        restored = without_request_end_diagnostic(without_inline_request_end(fixture['ASYNC_TEMPLATE']))
        # Exact inverse binds all reader operations, remaining routines and cases
        # to the reviewed local-key template, independently of the new pins.
        self.assertEqual(hashlib.sha256(restored.encode('utf-8')).hexdigest(),
                         'd53ce9873242502e179caaca49adff04a986a58865a1fdaca32f3e1d9cb854e2')
        self.assertEqual(hashlib.sha256(json.dumps(
            [restored, fixture['ASYNC_CASE_SOURCES']], ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')).hexdigest(),
            '3d789ced862ca647626a2106b21c2a27f15622cc918b0c3edff80f89c4f6b444')

    def test_local_request_key_is_the_only_template_change(self):
        fixture = make_fixture()
        template = without_request_end_diagnostic(without_inline_request_end(fixture['ASYNC_TEMPLATE']))
        body = routine(template, 'AsyncReadRequest')
        self.assertTrue(body.startswith('    Var AsyncRequestKey;\n'))
        self.assertEqual(len(re.findall(r'\bAsyncRequestKey\b', template)), 9)
        restored = without_local_request_key(template)
        # Exact inverse binds the complete previously reviewed template/cases,
        # not an expected source assembled from the changed implementation.
        self.assertEqual(hashlib.sha256(restored.encode('utf-8')).hexdigest(),
                         'f7ffa135b1b7973233e2b19ae64021ee3608abfec3b9e93fb1315b47a4dd6856')
        self.assertEqual(hashlib.sha256(json.dumps(
            [restored, fixture['ASYNC_CASE_SOURCES']], ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')).hexdigest(),
            '0c7e4335e2175bc500fdd4268dac5488290a08663f625cd44b83721b2ea6dc6d')

    def test_entry_failure_log_is_finite_private_stage_only(self):
        handler = routine(make_fixture()['ASYNC_TEMPLATE'], 'ПриОткрытии')
        stages = re.findall(r'ЭтапВхода = "([a-z]+)";', handler)
        self.assertEqual(stages, ['request', 'witness', 'initialize', 'entered', 'root'])
        operations = ['АсинхЗапрос = AsyncReadRequest(ЭтапВхода);',
                      'АсинхКонтекст = АсинхКонтекстПробы();',
                      'АсинхТрасса = Новый Массив;',
                      'АсинхЗаписатьВход();', 'АсинхКореньПробы();']
        for index, (stage, operation) in enumerate(zip(stages, operations)):
            start = handler.index('ЭтапВхода = "' + stage + '";')
            self.assertLess(start, handler.index(operation))
            if index + 1 < len(stages):
                self.assertLess(handler.index(operation), handler.index('ЭтапВхода = "' + stages[index + 1] + '";'))
        catch = handler.split('Исключение', 1)[1]
        self.assertEqual(re.findall(r'Сообщить\(([^\n]+)\);', catch),
                         ['"ASYNC-ENTRY-FAILURE:" + ЭтапВхода'])
        self.assertNotIn('ErrorInfo()', handler)
        self.assertNotIn('AsyncRequestKeySite', handler)
        for forbidden in ('ОписаниеОшибки(', 'ИнформацияОбОшибке(',
                          'ЗавершитьРаботуСистемы(', 'АсинхЗаписатьЗавершение('):
            self.assertNotIn(forbidden, handler)

    def test_request_substages_are_fixed_by_reference_without_semantic_changes(self):
        from test_native_async_protocol import suite
        template = without_request_end_diagnostic(without_inline_request_end(make_fixture()['ASYNC_TEMPLATE']))
        body = routine(without_request_site_diagnostic(without_local_request_key(template)), 'AsyncReadRequest')
        labels = ['request_open', 'request_object', 'request_key', 'request_value',
                  'request_end', 'request_fields', 'request_nonce', 'request_paths']
        all_labels = ['request', 'witness', 'initialize', 'entered', 'root', *labels,
                      'request_key_call', 'request_key_read', 'request_key_token',
                      'request_key_current', 'request_key_property',
                      'request_key_read_first', 'request_key_read_later',
                      'request_key_token_first', 'request_key_token_later',
                      'request_key_current_first', 'request_key_current_later',
                      'request_key_property_first', 'request_key_property_later',
                      'request_end_call', 'request_end_read', 'request_end_token',
                      'request_end_trailing', 'request_end_close']
        self.assertEqual(suite.ASYNC_ENTRY_LOG_MARKERS,
                         {'ASYNC-ENTRY-FAILURE:' + label: 13 + index
                          for index, label in enumerate(all_labels)})
        self.assertIn('Function AsyncReadRequest(ЭтапВхода)\n', template)
        self.assertEqual(re.findall(r'ЭтапВхода = "([a-z_]+)";', body), labels)
        operations = ['Reader = New JSONReader;', 'Request = New Structure;',
                      'AsyncExpectToken(Reader, JSONValueType.PropertyName);',
                      'If Key = "schema" Or Key = "version" Then',
                      'AsyncExpectToken(Reader, JSONValueType.ObjectEnd);',
                      'If Not Request.Property("schema")', 'If StrLen(Request.nonce)',
                      'If StrLen(Request.entered)']
        for index, (label, operation) in enumerate(zip(labels, operations)):
            start = body.index('ЭтапВхода = "' + label + '";')
            self.assertLess(start, body.index(operation))
            if index + 1 < len(labels):
                self.assertLess(body.index(operation), body.index('ЭтапВхода = "' + labels[index + 1] + '";'))
            self.assertEqual(suite.ASYNC_ENTRY_LOG_MARKERS['ASYNC-ENTRY-FAILURE:' + label], 18 + index)
        restored = without_request_site_diagnostic(without_local_request_key(template))
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         'b591f9eeb6690f741ef790b61df1a09774e88bdbd0a10bfe6ffe9cd3c50c4918')
        restored = re.sub(r'^\s*ЭтапВхода = "request_[a-z]+";\n', '', restored, flags=re.M)
        restored = restored.replace('Function AsyncReadRequest(ЭтапВхода)', 'Function AsyncReadRequest()')
        restored = restored.replace('АсинхЗапрос = AsyncReadRequest(ЭтапВхода);', 'АсинхЗапрос = AsyncReadRequest();')
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         'a6df293877c28a19eb70d8bdddcd784145584af874a01886e82e5ea1289c3994')
        cases = make_fixture()['ASYNC_CASE_SOURCES']
        self.assertEqual(hashlib.sha256(json.dumps(cases, ensure_ascii=False,
                         separators=(',', ':')).encode()).hexdigest(),
                         '09edb17d68c0ff7a5462498b132afa5c2b202912abdcb48e33ae1c676a39c075')

    def test_sources_are_literal_and_generator_is_fixed(self):
        fixture = make_fixture()
        assert isinstance(fixture['ASYNC_TEMPLATE'], str)
        assert type(fixture['ASYNC_CASE_SOURCES']) is tuple
        assert len(fixture['ASYNC_CASE_SOURCES']) == 8
        assert all(type(item) is str for item in fixture['ASYNC_CASE_SOURCES'])
        template = fixture['ASYNC_TEMPLATE']
        assert template.count('__ASYNC_CASE_ID__') == 1
        assert template.count('__ASYNC_CASE_SOURCE__') == 1
        hashes = set()
        for case in range(8):
            result = fixture['async_client_module'](case)
            expected = (template.replace('__ASYNC_CASE_ID__', str(case))
                        .replace('__ASYNC_CASE_SOURCE__', fixture['ASYNC_CASE_SOURCES'][case])).encode('utf-8-sig')
            assert result == expected
            assert b'__ASYNC_CASE_' not in result
            hashes.add(hashlib.sha256(result).hexdigest())
        assert len(hashes) == 8


    def test_case_selector_rejects_nonexact_integer(self):
        fixture = make_fixture()
        for invalid in [True, False, -1, 8, 1.0, '0', None, [], {}, b'1']:
            with self.assertRaises(fixture['FullError']):
                fixture['async_client_module'](invalid)


    def test_generator_rejects_mutated_placeholder_and_literal_types(self):
        fixture = make_fixture()
        original = fixture['ASYNC_TEMPLATE']
        for changed in (original + '__ASYNC_CASE_ID__', original.replace('__ASYNC_CASE_SOURCE__', ''), b'bad'):
            fixture['ASYNC_TEMPLATE'] = changed
            with self.assertRaises(fixture['FullError']):
                fixture['async_client_module'](0)
        fixture['ASYNC_TEMPLATE'] = original
        fixture['ASYNC_CASE_SOURCES'] = tuple(['__ASYNC_CASE_SOURCE__'] * 8)
        with self.assertRaises(fixture['FullError']):
            fixture['async_client_module'](0)


    def test_root_owns_completion_and_only_exit(self):
        fixture = make_fixture()
        template = fixture['ASYNC_TEMPLATE']
        on_open = routine(template, 'ПриОткрытии')
        assert 'АсинхКореньПробы();' in on_open
        assert on_open.index('АсинхЗаписатьВход();') < on_open.index('АсинхКореньПробы();')
        assert 'ЗавершитьРаботуСистемы' not in on_open
        assert 'АсинхЗаписатьЗавершение' not in on_open
        root = routine(template, 'АсинхКореньПробы')
        assert template.count('ЗавершитьРаботуСистемы(Ложь);') == 1
        assert root.index('Результат = Ждать Тест;') < root.index('АсинхСобытие(3);')
        assert root.index('Отброшено = Ждать АсинхОжидания[Индекс];') < root.index('АсинхЗаписатьЗавершение(2, 12);')
        assert root.index('АсинхСобытие(4);') < root.index('АсинхЗаписатьЗавершение(1, 0);')
        assert root.index('АсинхЗаписатьЗавершение(1, 0);') < root.index('ЗавершитьРаботуСистемы(Ложь);')
        terminal = routine(template, 'АсинхЗаписатьЗавершение')
        assert terminal.index('Если АсинхЗавершено') < terminal.index('АсинхЗавершено = Истина;')
        assert terminal.count('АсинхЗапрос.completed') == 1
        assert template.count('Запись.ОткрытьФайл(АсинхЗапрос.completed, "UTF-8", Ложь);') == 1
        assert 'Если Статус <> 1 Тогда' in terminal


    def test_no_executable_request_or_server_path(self):
        fixture = make_fixture()
        source = fixture['ASYNC_TEMPLATE'] + ''.join(fixture['ASYNC_CASE_SOURCES'])
        # Strip comments and strings before forbidden identifier scan.
        cleaned = re.sub(r'"(?:""|[^"\n])*"', '""', source)
        cleaned = re.sub(r'//[^\n]*', '', cleaned)
        assert not re.search(r'(?i)\b(?:Eval|Execute|Вычислить|Выполнить)\s*\(', cleaned)
        assert not re.search(r'(?i)&(?:НаСервере|AtServer)', cleaned)
        assert 'ExportProbeAfterCreate' not in source
        assert 'NativePostCreate' not in source
        request = routine(fixture['ASYNC_TEMPLATE'], 'AsyncReadRequest')
        assert 'For Index = 1 To 5 Do' in request
        assert 'If Request.Property(AsyncRequestKey)' in request
        assert 'JSONValueType.PropertyName' in request
        assert 'ТипЗначенияJSON.КонецОбъекта' in request
        assert 'If Reader.Read() Then Raise' in request
        assert 'AsyncRequestKey = "case"' not in request
        assert 'AsyncRequestKey = "code"' not in request
        assert 'AsyncRequestKey = "procedure"' not in request


    def test_values_are_exact_bounded_and_nonstringified(self):
        fixture = make_fixture()
        capture = routine(fixture['ASYNC_TEMPLATE'], 'АсинхСохранить')
        for type_name in ('Неопределено', 'Null', 'Булево', 'Число', 'Строка', 'Обещание'):
            assert f'Тип("{type_name}")' in capture
        assert 'Данные <> Цел(Данные)' in capture
        assert 'Данные < -999999 Или Данные > 999999' in capture
        assert 'Словарь.Найти(Данные)' in capture
        assert '7,17,11,12,21,22,31,33' in capture
        assert not re.search(r'(?i)\b(?:Строка|String|Формат|Format)\s*\(', capture)
        assert 'АсинхНесовместимо = Истина;' in capture


    def test_error_fields_are_guarded_and_keep_saved_error(self):
        fixture = make_fixture()
        capture = routine(fixture['ASYNC_TEMPLATE'], 'АсинхСохранитьОшибку')
        for field in ('Description', 'Code', 'AdditionalInformation', 'Cause', 'ModuleName', 'LineNumber', 'InitialString'):
            assert re.search(r'Попытка [^\n]*СохраненнаяОшибка\.' + field + r'[^\n]*Исключение КонецПопытки;', capture)
        assert 'ИнформацияОбОшибке()' not in capture
        assert 'ErrorInfo()' not in capture
        assert 'СохраненнаяОшибка.IsErrorOfCategory(ErrorCategory.ConfigurationError)' in capture
        assert 'Категория = АсинхПара(3, 1)' in capture
        assert 'Категория = АсинхПара(0, Неопределено)' in capture
        assert 'АсинхОшибки.Количество() >= 3' in capture
        bounded = routine(fixture['ASYNC_TEMPLATE'], 'АсинхПоле')
        assert 'СтрДлина(Данные) > 512' in bounded
        assert 'GetBinaryDataFromString(Данные, "UTF-8", Ложь).Size() > 512' in bounded
        assert 'Тип("ИнформацияОбОшибке")' in bounded
        assert not re.search(r'(?i)\b(?:Строка|String|Формат|Format)\s*\(', bounded)


    def test_fixed_event_vocab_and_slots_match_frozen_spec(self):
        fixture = make_fixture()
        import json
        spec = FROZEN_SPEC
        for case, source in enumerate(fixture['ASYNC_CASE_SOURCES']):
            events = [int(x) for x in re.findall(r'АсинхСобытие\((\d+)\)', source)]
            # Common 0,1,3,4 are emitted by the pinned template, 2 by each test.
            expected = {2, *spec['cases'][case]['required']}
            expected.update(e for choice in spec['cases'][case]['choices'] for e in choice)
            if case == 6:
                expected.update((15, 18))  # Only when the rejecting call returns.
            assert set(events) == expected
            assert len(events) == len(set(events))
            assert f"АсинхНачатьТест({spec['slots'][case]});" in source
            assert len(spec['cases'][case]['required']) + len(spec['cases'][case]['choices']) + 5 <= 24


    def test_leaves_siblings_and_inner_are_retained_and_joined(self):
        fixture = make_fixture()
        cases = fixture['ASYNC_CASE_SOURCES']
        assert 'Лист = АсинхЛист();\n    АсинхУдержать(Лист);' in cases[1]
        assert 'АсинхЛистЗначение = Ждать Лист;' in cases[1]
        siblings = cases[2]
        for branch in ('А', 'Б'):
            assert f'{branch} = АсинхВетвь{branch}();\n    АсинхУдержать({branch});' in siblings
            assert f'Значение{branch} = Ждать {branch};' in siblings
        assert siblings.count('АсинхСбой = Истина;') == 3
        assert 'ПовторА = Ждать А;' in siblings
        inner = cases[4]
        assert 'АсинхУдержать(АсинхВнутреннее);' in inner
        assert inner.index('ВнутреннийРезультат = Ждать АсинхВнутреннее;') > inner.index('АсинхСобытие(18);')
        assert 'АсинхСобытие(19);' in inner
        assert 'Пока' not in inner


    def test_scalar_and_rejection_paths_do_not_normalize_errors(self):
        fixture = make_fixture()
        scalar = fixture['ASYNC_CASE_SOURCES'][3]
        for slot, phase in enumerate((3, 4, 5)):
            assert f'АсинхСохранитьОшибку({slot}, {phase}, Ошибка);' in scalar
        reject = fixture['ASYNC_CASE_SOURCES'][6]
        assert 'Если ВызовВернулся Тогда' in reject
        for slot in range(3):
            assert f'АсинхСохранитьОшибку({slot}, {slot}, Ошибка);' in reject
        assert '"ASYNC-REJECT", КатегорияОшибки.ОшибкаКонфигурации' in reject
        assert '"ASYNC-CODE", "ASYNC-DETAIL", Неопределено' in reject


    def test_val_and_english_grammar_are_distinct(self):
        fixture = make_fixture()
        parameters = fixture['ASYNC_CASE_SOURCES'][5]
        assert 'АсинхПараметры(Первый, Знач Второй, Знач МассивДанных, ПоУмолчанию = 7)' in parameters
        assert 'АсинхСохранить(2, ПервыйФакт);' in parameters
        assert 'АсинхСохранить(3, ВторойФакт);' in parameters
        english = fixture['ASYNC_CASE_SOURCES'][7]
        assert 'AsYnC FuNcTiOn' in english
        assert 'Return AsyncAddOne((aWaIt Leaf));' in english
        handled = routine(english, 'AsyncHandledProcedure')
        assert not re.search(r'(?i)\b(?:Await|Ждать)\b', re.sub(r'//[^\n]*', '', handled))
        assert handled.index('АсинхСобытие(16);') < handled.index('АсинхСобытие(17);')
        assert 'AsyncHandledProcedure();\n    АсинхСобытие(18);' in english


    def test_every_module_declaration_is_client_only(self):
        fixture = make_fixture()
        for case, body in enumerate(fixture['ASYNC_CASE_SOURCES']):
            source = fixture['ASYNC_TEMPLATE'] + body
            # Module variables/routines need their own client directive;
            # explicitly local variables inherit their routine's context.
            previous, inside_routine, declarations = '', False, 0
            for line in source.splitlines():
                stripped = line.strip()
                declaration = re.match(r'(?i)(?:(?:Асинх|Async)\s+)?'
                    r'(Перем|Var|Функция|Процедура|Function|Procedure)\b', stripped)
                if declaration:
                    local_variable = declaration[1].casefold() in ('перем', 'var') and inside_routine
                    if not local_variable:
                        self.assertIn(previous.casefold(), ('&наклиенте', '&atclient'), (case, previous))
                        declarations += 1
                    if declaration[1].casefold() not in ('перем', 'var'):
                        inside_routine = True
                if re.match(r'(?i)(?:КонецФункции|КонецПроцедуры|EndFunction|EndProcedure)\b', stripped):
                    inside_routine = False
                if stripped:
                    previous = stripped
            self.assertGreater(declarations, 3)
            directives = re.findall(r'(?im)^\s*&([^\n]+)', source)
            self.assertTrue(all(d.casefold() in ('наклиенте', 'atclient') for d in directives))
            self.assertEqual(re.findall(r'(?im)^\s*#([^\n]+)', source),
                             ['Если Клиент Тогда', 'Иначе', 'КонецЕсли'])

    def test_all_native_calls_and_constructors_have_closed_inventory(self):
        fixture = make_fixture()
        source = fixture['ASYNC_TEMPLATE'] + ''.join(fixture['ASYNC_CASE_SOURCES'])
        # Fixed snippets have no multiline strings. Remove strings/comments in
        # one pass so quoted comment markers cannot hide executable code.
        cleaned = re.sub(r'"(?:""|[^"\n])*"|//[^\n]*', '', source)
        declared = set(re.findall(
            r'(?im)^\s*(?:(?:Асинх|Async)\s+)?'
            r'(?:Функция|Процедура|Function|Procedure)\s+(\w+)\(', cleaned))
        calls = set(re.findall(r'(?u)(?<![\w])(\w+)\s*\(', cleaned)) - declared
        calls -= {'And', 'Not'}  # Logical operators before a parenthesized expression.
        expected = {
            'Close', 'ErrorInfo', 'GetBinaryDataFromString', 'Insert',
            'IsErrorOfCategory', 'Mid', 'OpenFile', 'Property', 'Raise', 'Read',
            'Size', 'StrFind', 'StrLen', 'Type', 'TypeOf', 'ВызватьИсключение',
            'Добавить', 'Если', 'ЗавершитьРаботуСистемы', 'Закрыть', 'ЗаписатьJSON',
            'ИначеЕсли', 'ИнформацияОбОшибке', 'Количество', 'Найти', 'ОткрытьФайл',
            'Сообщить', 'СтрДлина', 'СтрРазделить', 'Структура', 'Тип', 'ТипЗнч', 'Цел',
        }
        self.assertEqual(calls, expected)
        self.assertEqual(set(re.findall(r'(?i)\b(?:Новый|New)\s+(\w+)', cleaned)),
                         {'Массив', 'Структура', 'Structure', 'JSONReader', 'ЗаписьJSON'})
        # Synchronous transport is outside the measured Async cases; no native
        # UI/network/file async producer, timer, notification or detached task.
        io_lines = [line.strip() for line in source.splitlines()
                    if re.search(r'\.(?:OpenFile|ОткрытьФайл)\(', line)]
        self.assertEqual(io_lines, [
            'Reader.OpenFile(LaunchParameter);',
            'Запись.ОткрытьФайл(АсинхЗапрос.entered, "UTF-8", Ложь);',
            'Запись.ОткрытьФайл(АсинхЗапрос.completed, "UTF-8", Ложь);',
        ])

    def test_every_created_function_promise_is_retained_and_awaited(self):
        fixture = make_fixture()
        for case, body in enumerate(fixture['ASYNC_CASE_SOURCES']):
            source = fixture['ASYNC_TEMPLATE'] + body
            names = set(re.findall(r'(?im)^\s*(?:Асинх|Async)\s+'
                                   r'(?:Функция|Function)\s+(\w+)\(', source))
            creation_count = 0
            for name in names:
                creations = list(re.finditer(
                    r'(?m)^\s*(\w+) = ' + re.escape(name) + r'\([^\n]*\);\n', source))
                self.assertEqual(len(creations), 1, (case, name))
                for creation in creations:
                    creation_count += 1
                    variable = creation.group(1)
                    self.assertTrue(source[creation.end():].lstrip().startswith(
                        f'АсинхУдержать({variable});'), (case, name, variable))
                    self.assertRegex(source, r'(?i)(?:Ждать|Await)\s+' + re.escape(variable) + r'\b')
            # The failure drain is finite: five statically unique function calls
            # at most, all earlier producers are in this retained registry.
            self.assertLessEqual(creation_count, 5)
            procedures = set(re.findall(r'(?im)^\s*(?:Асинх|Async)\s+'
                                        r'(?:Процедура|Procedure)\s+(\w+)\(', source))
            self.assertEqual(procedures, {'АсинхКореньПробы'} |
                             ({'AsyncHandledProcedure'} if case == 7 else set()))

    def test_generator_hash_pin_rejects_any_unreviewed_source_mutation(self):
        fixture = make_fixture()
        template = fixture['ASYNC_TEMPLATE']
        cases = fixture['ASYNC_CASE_SOURCES']
        fixture['ASYNC_TEMPLATE'] = template.replace('&НаКлиенте', '&НаСервере', 1)
        with self.assertRaises(fixture['FullError']):
            fixture['async_client_module'](0)
        fixture['ASYNC_TEMPLATE'] = template
        for index in range(8):
            altered = list(cases)
            altered[index] += '\n// unreviewed modification\n'
            fixture['ASYNC_CASE_SOURCES'] = tuple(altered)
            # Every requested case binds the entire fixed inventory, not only
            # the selected case's source.
            with self.assertRaises(fixture['FullError']):
                fixture['async_client_module']((index + 1) % 8)
        fixture['ASYNC_CASE_SOURCES'] = cases
        fixture['ASYNC_FIXTURE_SHA256'] = '0' * 64
        with self.assertRaises(fixture['FullError']):
            fixture['async_client_module'](0)

    def test_implementation_inventory_and_dag_match_independent_freeze(self):
        tree = ast.parse(SNIPPET.read_text(encoding='utf-8'))
        names = {'ASYNC_SLOTS', 'ASYNC_REQUIRED', 'ASYNC_EDGES'}
        values = {node.targets[0].id: ast.literal_eval(node.value)
                  for node in tree.body if isinstance(node, ast.Assign)
                  and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id in names}
        self.assertEqual(set(values), names)
        self.assertEqual(values['ASYNC_SLOTS'], tuple(FROZEN_SPEC['slots']))
        self.assertEqual(values['ASYNC_REQUIRED'],
                         tuple(tuple(case['required']) for case in FROZEN_SPEC['cases']))
        self.assertEqual(values['ASYNC_EDGES'],
                         tuple(tuple(tuple(edge) for edge in case['edges'])
                               for case in FROZEN_SPEC['cases']))


    def test_category_membership_false_is_not_unavailable(self):
        capture = routine(make_fixture()['ASYNC_TEMPLATE'], 'АсинхСохранитьОшибку')
        guarded = re.search(
            r'Попытка\s*// Category membership[^\n]*\n(.*?)Исключение КонецПопытки;',
            capture, re.DOTALL).group(1)
        expected = (
            'Если СохраненнаяОшибка.IsErrorOfCategory(ErrorCategory.ConfigurationError) Тогда\n'
            '    Категория = АсинхПара(3, 1);\n'
            'Иначе\n'
            '    Категория = АсинхПара(3, 2);\n'
            'КонецЕсли;'
        )
        self.assertEqual('\n'.join(line[8:] if line.startswith('        ') else line
                                   for line in guarded.strip('\n').splitlines()).strip(), expected)
        self.assertLess(capture.index('Категория = АсинхПара(0, Неопределено);'),
                        capture.index('СохраненнаяОшибка.IsErrorOfCategory'))
        self.assertEqual(capture.count('Категория = АсинхПара('), 3)

    def test_category_three_way_projection_keeps_exact_distinct_fingerprints(self):
        from test_native_async_protocol import full, private_error, suite
        fingerprints = set()
        for category, public_tag in (([3, 1], 1), ([3, 2], 2), ([0, None], 3)):
            with self.subTest(category=category):
                descriptor = private_error(6)
                descriptor['category'] = category
                raw = json.dumps(descriptor, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode('utf-8')
                expected = [6, 2, 2, 2, public_tag, 0, hashlib.sha256(raw).hexdigest()]
                self.assertEqual(suite._async_private_error(descriptor), expected)
                self.assertEqual(full.validate_async_private_descriptor(descriptor), expected)
                fingerprints.add(expected[-1])
        self.assertEqual(len(fingerprints), 3)

    def test_fixture_and_all_host_module_pins_match_independent_bytes(self):
        from test_native_async_protocol import full
        fixture = literal_sources()
        template, cases = fixture['ASYNC_TEMPLATE'], fixture['ASYNC_CASE_SOURCES']
        aggregate = hashlib.sha256(json.dumps([template, cases], ensure_ascii=False,
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(aggregate, fixture['ASYNC_FIXTURE_SHA256'])
        identity = {
            'template': hashlib.sha256(template.encode('utf-8')).hexdigest(),
            'modules': [hashlib.sha256(template.replace('__ASYNC_CASE_ID__', str(index))
                        .replace('__ASYNC_CASE_SOURCE__', case).encode('utf-8-sig')).hexdigest()
                        for index, case in enumerate(cases)],
        }
        self.assertEqual(identity, full.ASYNC_EXPECTED_IDENTITY)
        self.assertEqual(identity, full.async_source_identity(SNIPPET.read_bytes()))


if __name__ == "__main__":
    unittest.main()
