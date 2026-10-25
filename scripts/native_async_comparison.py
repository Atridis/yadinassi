"""Finite Async actual capture and pure host comparison, not native validation.

Host must validate same-run native provenance and whole-source/run binding.
read_pinned_sources extracts only exact pinned literals without executing Python.
execute_actual belongs in a bounded child given NO native expected rows;
compare_observations is execution-free and belongs in the host. The compare
convenience helper is for offline tests only. No test fixtures are imported here.
"""
import ast
import hashlib
import json
import re

PROFILE = 'async-language-8-v1'
SOURCE_BODIES_SHA256 = '09edb17d68c0ff7a5462498b132afa5c2b202912abdcb48e33ae1c676a39c075'
MAX_ACTUAL_BYTES = 8192
MAX_SOURCE_BYTES = 294912
SOURCE_SHA256 = '83a6e22dbb4788498985e51e06ea610d2a9bc95702852da396cb6d7779bf1c5a'
DECLARATIONS = '''Перем АсинхЛистЗначение, АсинхВнутреннее,
    АсинхЗначениеУмолчания, АсинхСбой;
'''
ROOT = '''
&НаКлиенте
Асинх Процедура ReplayRoot()
    АсинхСобытие(0);
    Тест = АсинхТестПробы();
    АсинхУдержать(Тест);
    Завершение = Ждать Тест;
    АсинхСобытие(3);
    АсинхСобытие(4);
КонецПроцедуры
ReplayRoot();
'''


class InvalidComparisonInput(ValueError):
    """Only a fixed public error is exposed, never input or source paths."""
    def __init__(self):
        super().__init__('invalid_async_comparison_input')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _require(condition):
    if not condition:
        raise InvalidComparisonInput()


def _extract_literals(sourcebytes):
    """Read only unique top-level literals, rejecting other protected bindings."""
    tree = ast.parse(sourcebytes.decode('utf-8-sig'))
    protected = {'ASYNC_TEMPLATE', 'ASYNC_CASE_SOURCES'}
    found, accepted_targets = {}, set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in protected:
                    if name.id in found or len(node.targets) != 1:
                        raise ValueError('invalid_async_literal_binding')
                    found[name.id] = ast.literal_eval(node.value)
                    accepted_targets.add(id(name))
    # Reject annotated/augmented/nested/destructured/loop/with/walrus writes,
    # deletes, and bindings that AST represents as strings rather than Names.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in protected:
            if isinstance(node.ctx, (ast.Store, ast.Del)) and id(node) not in accepted_targets:
                raise ValueError('invalid_async_literal_binding')
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in protected:
                raise ValueError('invalid_async_literal_binding')
        elif isinstance(node, ast.arg) and node.arg in protected:
            raise ValueError('invalid_async_literal_binding')
        elif isinstance(node, ast.alias):
            binding = node.asname or node.name.split('.')[0]
            if binding in protected or node.name == '*':
                raise ValueError('invalid_async_literal_binding')
        elif isinstance(node, ast.ExceptHandler) and node.name in protected:
            raise ValueError('invalid_async_literal_binding')
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and protected.intersection(node.names):
            raise ValueError('invalid_async_literal_binding')
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name in protected:
            raise ValueError('invalid_async_literal_binding')
        elif isinstance(node, ast.MatchMapping) and node.rest in protected:
            raise ValueError('invalid_async_literal_binding')
    if set(found) != protected:
        raise ValueError('missing_async_literal')
    return found['ASYNC_TEMPLATE'], found['ASYNC_CASE_SOURCES']



def read_pinned_sources(sourcebytes):
    """Extract bounded pinned literals, never import/evaluate source module code.

    Whole-file/run identity still belongs to the host's provenance validation.
    """
    _require(type(sourcebytes) is bytes and 0 < len(sourcebytes) <= MAX_SOURCE_BYTES)
    try:
        template, sources = _extract_literals(sourcebytes)
        validate_sources(template, sources)
    except Exception:
        raise InvalidComparisonInput() from None
    return template, tuple(sources)


def _validate_bodies(sources):
    _require(type(sources) in (list, tuple) and len(sources) == 8)
    _require(all(type(s) is str and len(s) <= 32768 for s in sources))
    try:
        identity = hashlib.sha256(canonical(sources)).hexdigest()
    except (UnicodeError, ValueError, TypeError):
        raise InvalidComparisonInput() from None
    _require(identity == SOURCE_BODIES_SHA256)


def validate_sources(template, sources):
    _require(type(template) is str and len(template) <= 32768)
    _require(type(sources) in (list, tuple) and len(sources) == 8)
    _require(all(type(s) is str and len(s) <= 32768 for s in sources))
    try:
        identity = hashlib.sha256(canonical([template, sources])).hexdigest()
    except (UnicodeError, ValueError, TypeError):
        raise InvalidComparisonInput() from None
    _require(identity == SOURCE_SHA256)
    _validate_bodies(sources)


def validate_inputs(template, sources, native):
    validate_sources(template, sources)
    _require(type(native) is dict and native.get('status') == 'ok')
    _require(native.get('version') == 2 and type(native.get('version')) is int)
    _require(native.get('failure_kind') == 'none')
    _require(_hash(native.get('continuity_sha256')))
    _require('marker_validation_failure' in native and native['marker_validation_failure'] is None)
    _require('failure_diagnostics' in native and native['failure_diagnostics'] is None)
    diagnostics = native.get('process_diagnostics')
    _require(type(diagnostics) is dict)
    _require(diagnostics.get('reason') == 'none' and diagnostics.get('stage') == 'after_exit')
    for name in ('unexpected_count', 'zombie_count'):
        _require(type(diagnostics.get(name)) is int and diagnostics[name] == 0)
    classes = diagnostics.get('classes')
    _require(type(classes) is dict and set(classes) ==
             {'display', 'native', 'other', 'python', 'session_bus', 'shell', 'unreadable'})
    _require(all(type(value) is int and value == 0 for value in classes.values()))
    _require(native.get('template_sha256') == hashlib.sha256(template.encode('utf-8')).hexdigest())
    rows = native.get('cases')
    _require(type(rows) is list and len(rows) == 8)
    for i, row in enumerate(rows):
        _require(type(row) is list and len(row) == 8)
        case, status, failure, modulehash, proof, trace, values, errors = row
        _require(type(case) is int and case == i)
        _require(type(status) is int and status == 1)
        _require(type(failure) is int and failure == 0)
        _require(type(proof) is int and proof == 63)
        module = template.replace('__ASYNC_CASE_ID__', str(i)).replace('__ASYNC_CASE_SOURCE__', sources[i])
        raw = module.removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8-sig')
        _require(_hash(modulehash) and modulehash == hashlib.sha256(raw).hexdigest())
        _require(type(trace) is list and 1 <= len(trace) <= 24)
        _require(all(_integer(x, 0, 255) for x in trace))
        _require(len(trace) == len(set(trace)))
        _require(type(values) is list and 1 <= len(values) <= 8)
        _require(type(errors) is list and len(errors) <= 3)
        for pair in values:
            _require(type(pair) is list and len(pair) == 2)
            tag, payload = pair
            _require(_integer(tag, 0, 7) and _integer(payload, -999999, 999999))
            _require((tag not in (0, 1, 2, 6) or payload == 0)
                     and (tag != 3 or payload in (0, 1))
                     and (tag != 5 or 0 <= payload <= 7)
                     and (tag != 7 or 0 <= payload < len(errors)))
        for error in errors:
            _require(type(error) is list and len(error) == 7)
            _require(_integer(error[0], 0, 6))
            _require(all(_integer(v, 0, 4) for v in error[1:4]))
            _require(all(_integer(v, 0, 3) for v in error[4:6]))
            _require(_hash(error[6]))
    return rows


class Capture:
    """Bounded capture only; no scheduler substitutions and no private errors."""
    def __init__(self):
        self.trace, self.values, self.errors, self.retained = [], [], [], []

    def begin(self, count):
        _require(count == int(count) and 1 <= count <= 8)
        self.values = [[0, 0] for _ in range(int(count))]
        self.event(1)

    def event(self, code):
        _require(code == int(code) and 0 <= code <= 255 and len(self.trace) < 24)
        _require(int(code) not in self.trace)
        self.trace.append(int(code))

    def retain(self, value):
        from yadinassi.type_values import type_of
        from yadinassi.values import BSLType
        if type_of(value) is BSLType.PROMISE:
            _require(len(self.retained) < 32)
            self.retained.append(value)

    def _slot(self, slot):
        _require(slot == int(slot) and 0 <= slot < len(self.values))
        return int(slot)

    def save(self, slot, value):
        from yadinassi.type_values import type_of
        from yadinassi.values import BSLType
        kind = type_of(value)
        tags = {BSLType.UNDEFINED: 1, BSLType.NULL: 2, BSLType.BOOLEAN: 3,
                BSLType.NUMBER: 4, BSLType.STRING: 5, BSLType.PROMISE: 6}
        _require(kind in tags)
        tag, payload = tags[kind], 0
        if tag == 3:
            payload = int(value)
        elif tag == 4:
            _require(value == int(value) and -999999 <= value <= 999999)
            payload = int(value)
        elif tag == 5:
            dictionary = ('7', '17', '11', '12', '21', '22', '31', '33')
            _require(value in dictionary)
            payload = dictionary.index(value)
        self.values[self._slot(slot)] = [tag, payload]

    def save_error(self, slot, phase, error):
        from yadinassi.error_info import BSLErrorCategory, BSLErrorInfo
        from yadinassi.type_values import type_of
        from yadinassi.values import BSLType
        _require(type(error) is BSLErrorInfo and len(self.errors) < 3)
        _require(phase == int(phase) and 0 <= phase <= 6)
        fields = [error.get_member(name) for name in
                  ('Description', 'Code', 'AdditionalInformation')]
        # Public tags preserve exact equality to synthetic literals, not wording,
        # substring classes or private native source-location hashes.
        tags = [2 if type(value) is str and value == literal else 0
                if type_of(value) is BSLType.UNDEFINED else 1
                if type(value) is str and value == '' else 3
                for value, literal in zip(fields, ('ASYNC-REJECT', 'ASYNC-CODE', 'ASYNC-DETAIL'))]
        category = 1 if error.is_error_of_category(BSLErrorCategory.CONFIGURATION_ERROR) else 2
        cause = 0 if type_of(error.get_member('Cause')) is BSLType.UNDEFINED else 1
        self.values[self._slot(slot)] = [7, len(self.errors)]
        self.errors.append([int(phase), *tags, category, cause])

    def install(self, vm):
        for name, callback in (('АсинхНачатьТест', self.begin),
                               ('АсинхСобытие', self.event),
                               ('АсинхУдержать', self.retain),
                               ('АсинхСохранить', self.save),
                               ('АсинхСохранитьОшибку', self.save_error)):
            vm.register_function(name, callback, returns_value=False)


def execute_actual(sources):
    """Child-only execution of eight pinned bodies; NO native rows accepted.

    The returned JSON-ready rows contain only actual bounded observations.
    """
    _validate_bodies(sources)
    actual = []
    for source in sources:
        capture, vm = Capture(), None
        failed, lifecycle = False, False
        try:
            from yadinassi import Interpreter
            from yadinassi.native_targets import LINUX_8_3_27_1508
            vm = Interpreter(output=lambda message: None, native_target=LINUX_8_3_27_1508)
            capture.install(vm)
            vm.execute(DECLARATIONS + source + ROOT)
            vm.run_until_idle()
            lifecycle = (not vm.pending_promises and bool(capture.retained)
                         and all(p.state != 'pending' for p in capture.retained)
                         and not vm.variables['асинхсбой'])
        except Exception:
            failed = True
        finally:
            if vm is not None:
                try:
                    vm.close()
                except Exception:
                    failed = True
        actual.append([capture.trace, capture.values, capture.errors, lifecycle, failed])
    validate_actual(actual)
    return actual


def validate_actual(actual):
    """Reject untrusted child payload shapes before comparing or hashing them."""
    _require(type(actual) is list and len(actual) == 8)
    for row in actual:
        _require(type(row) is list and len(row) == 5)
        trace, values, errors, lifecycle, failed = row
        _require(type(lifecycle) is bool and type(failed) is bool)
        _require(type(trace) is list and 0 <= len(trace) <= 24)
        _require(all(_integer(v, 0, 255) for v in trace))
        _require(len(trace) == len(set(trace)))
        _require(type(values) is list and 0 <= len(values) <= 8)
        _require(type(errors) is list and len(errors) <= 3)
        if not failed:
            _require(bool(trace) and bool(values))
        for pair in values:
            _require(type(pair) is list and len(pair) == 2)
            tag, payload = pair
            _require(_integer(tag, 0, 7) and _integer(payload, -999999, 999999))
            _require((tag not in (0, 1, 2, 6) or payload == 0)
                     and (tag != 3 or payload in (0, 1))
                     and (tag != 5 or 0 <= payload <= 7)
                     and (tag != 7 or 0 <= payload < len(errors)))
        for error in errors:
            _require(type(error) is list and len(error) == 6)
            _require(_integer(error[0], 0, 6))
            _require(all(_integer(v, 0, 3) for v in error[1:4]))
            _require(_integer(error[4], 1, 2) and _integer(error[5], 0, 1))
    _require(len(canonical(actual)) <= MAX_ACTUAL_BYTES)


def compare(template, sources, native):
    """Offline convenience only: validate native, run current runtime, compare."""
    validate_inputs(template, sources, native)
    return compare_observations(template, sources, native, execute_actual(sources))


def compare_observations(template, sources, native, actual):
    """Pure host comparison of validated same-run native and untrusted child rows.

    No runtime import/execution. Caller owns whole-source/run provenance and
    bounded-child integrity. Shape-valid actual input is NOT execution evidence
    by itself; never accept arbitrary caller-supplied rows as trusted results.
    """
    rows = validate_inputs(template, sources, native)
    validate_actual(actual)
    cases = []
    for row, observed in zip(rows, actual):
        trace, values, errors, lifecycle, failed = observed
        code = ('runtimeerror' if failed else 'lifecycle' if not lifecycle else
                'trace' if trace != row[5] else 'values' if values != row[6] else
                'errors' if errors != [e[:6] for e in row[7]] or
                any(e[1:] != [2, 2, 2, 1, 0] for e in errors) else 'none')
        cases.append(['matched' if code == 'none' else 'mismatched', code])
    return {'profile': PROFILE,
            'status': 'matched' if all(c[0] == 'matched' for c in cases) else 'mismatched',
            'cases': cases, 'actual_sha256': hashlib.sha256(canonical(actual)).hexdigest()}
