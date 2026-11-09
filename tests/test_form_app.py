"""Runnable replicated forms: owned packages, processes, HTTP and SQLite only."""
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
import http.client
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Thread
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.configuration_import import load_configuration_directory
from yadinassi.database_context import SQLiteDBContext
from yadinassi.form_replication import ReplicatedFormServer
from yadinassi.ui.form_app import (FormController, FormHandler, FormProcess,
    PROTOCOL, main, serve_runtime)
from yadinassi.ui.form_package import load_client, load_server
from yadinassi.ui.local_app import LocalUIServer, LocalTransportError
from yadinassi.ui.protocol import encode_line, decode_line, MAX_LINE_BYTES
from scripts import entrypoint

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/forms/estimate'
PRODUCT = ROOT / 'examples/forms/product-intake'


def request(method='hello', **params):
    return {'jsonrpc': '2.0', 'id': 1, 'method': 'form.' + method,
            'params': {'protocol': PROTOCOL} if method == 'hello' else params}


def pair(directory=EXAMPLE):
    package = load_server(directory)
    server = ReplicatedFormServer(package.source, package.endpoints, handlers=package.handlers,
        attributes=package.attributes, initial_values=package.initial_values, bindings=package.lifecycle)
    return FormController(load_client(directory), server.exchange), server


def state(controller, method='hello', **params):
    return controller.exchange(request(method, **params))['result']


def event(controller, event='command', control='RunButton', **params):
    args = {'event': event, 'revision': controller.session.revision, **params}
    if event != 'close': args['control'] = control
    return state(controller, 'event', **args)


class FormPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        shutil.copytree(EXAMPLE, self.directory, dirs_exist_ok=True)

    def edit(self, side, callback):
        path = self.directory / (side + '.json')
        data = json.loads(path.read_text()); callback(data)
        path.write_text(json.dumps(data))

    def test_example_loads_separate_sources_and_signatures(self):
        client, server = load_client(self.directory), load_server(self.directory)
        self.assertNotIn('&AtServer', client.source)
        self.assertNotIn('&AtClient', server.source)
        self.assertEqual(client.bindings[0].name, 'RemoteRun')
        self.assertEqual(server.endpoints, {1: 'Run'})
        self.assertEqual(server.initial_values['Price'], Decimal('20.10'))

    def test_client_does_not_read_server_files(self):
        (self.directory / 'server.json').unlink(); (self.directory / 'server.bsl').unlink()
        self.assertTrue(load_client(self.directory).source)

    def test_server_does_not_read_client_files(self):
        (self.directory / 'client.json').unlink(); (self.directory / 'client.bsl').unlink()
        self.assertTrue(load_server(self.directory).source)

    def test_unknown_keys_and_versions_reject(self):
        self.edit('client', lambda x: x.update(path='/private/server'))
        with self.assertRaises(ValueError): load_client(self.directory)
        self.edit('server', lambda x: x.update(protocol='future'))
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_duplicate_json_and_non_utf8_reject(self):
        (self.directory / 'client.json').write_bytes(b'{"protocol":1,"protocol":2}')
        with self.assertRaises(ValueError): load_client(self.directory)
        (self.directory / 'server.bsl').write_bytes(b'\xff')
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_source_and_manifest_limits(self):
        (self.directory / 'client.bsl').write_bytes(b'x' * 65537)
        with self.assertRaises(ValueError): load_client(self.directory)
        (self.directory / 'server.json').write_bytes(b' ' * (MAX_LINE_BYTES + 1))
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_duplicate_bindings_and_attribute_names_reject(self):
        self.edit('client', lambda x: x['handlers'].append(x['handlers'][0]))
        with self.assertRaises(ValueError): load_client(self.directory)
        self.edit('server', lambda x: x['attributes'].append(x['attributes'][0]))
        with self.assertRaises(ValueError): load_server(self.directory)

    def test_hostile_endpoint_and_scalar_shapes_reject(self):
        self.edit('server', lambda x: x['endpoints'][0].update(endpoint=True))
        with self.assertRaises(ValueError): load_server(self.directory)
        self.edit('client', lambda x: x['bindings'][0].update(parameters=['A', 'a']))
        with self.assertRaises(ValueError): load_client(self.directory)

    def test_handler_functions_and_unsupported_attribute_types_reject(self):
        self.edit('client', lambda x: x['handlers'][0].update(isFunction=True))
        with self.assertRaises(ValueError): load_client(self.directory)
        self.edit('server', lambda x: x['attributes'][0].update(type='CatalogRef'))
        with self.assertRaises(ValueError): load_server(self.directory)


class FormControllerTests(unittest.TestCase):
    def setUp(self): self.controller, self.server = pair()

    def test_bootstrap_projection_exposes_no_source_signatures_or_paths(self):
        result = state(self.controller)
        self.assertEqual(result['error'], None)
        self.assertEqual(result['state']['kind'], 'form')
        self.assertEqual(len(result['state']['items']), 5)
        raw = encode_line(result)
        for private in (b'Procedure', b'endpoint', b'client.bsl', b'database', b'Create(Cancel'):
            self.assertNotIn(private, raw)
        self.assertEqual(result['state']['items'][0]['value'], {'type':'Number','value':'20.10'})

    def test_edit_command_barrier_and_client_continuation(self):
        state(self.controller)
        result = event(self.controller, 'change', 'FieldPrice', value={'type':'Number','value':'7.25'})
        self.assertEqual(self.server.session.form._data['price'], Decimal('20.10'))
        result = event(self.controller)
        self.assertEqual(self.server.session.form._data['price'], Decimal('7.25'))
        total = next(x for x in result['state']['items'] if x['name'] == 'FieldTotal')
        self.assertEqual(total['value'], {'type':'Number','value':'21.75'})
        self.assertEqual(result['state']['messages'], ['Calculated on the server'])

    def test_repeat_hello_and_snapshot_do_not_reopen_or_repeat_commands(self):
        first = state(self.controller); sequence = self.controller.session.client_sequence
        self.assertEqual(state(self.controller), first)
        self.assertEqual(state(self.controller, 'snapshot'), first)
        self.assertEqual(self.controller.session.client_sequence, sequence)

    def test_duplicate_or_stale_command_does_not_cross_transport(self):
        state(self.controller); revision = self.controller.session.revision
        event(self.controller); sequence = self.controller.session.client_sequence
        result = state(self.controller, 'event', event='command', revision=revision, control='RunButton')
        self.assertEqual(result['error'], 'stale_revision')
        self.assertEqual(self.controller.session.client_sequence, sequence)

    def test_close_cancellation_then_success(self):
        state(self.controller)
        event(self.controller, 'change', 'FieldPrice', value={'type':'Number','value':'3'})
        self.assertEqual(event(self.controller, 'close')['state']['kind'], 'form')
        event(self.controller)
        self.assertEqual(event(self.controller, 'close')['state']['kind'], 'closed')
        self.assertTrue(self.server.session.closed)

    def test_renderer_cannot_select_routine_or_package(self):
        state(self.controller)
        for fields in ({'routine':'Run'}, {'endpoint':1}, {'database':'private'}, {'source':'Message(1)'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                state(self.controller, 'event', event='command', revision=1, control='RunButton', **fields)
        self.assertEqual(self.controller.session.client_sequence, 1)

    def test_hidden_readonly_or_wrong_kind_controls_cannot_mutate(self):
        state(self.controller)
        for control in ('Dirty', 'FieldTotal', 'RunButton', 'Missing'):
            result = event(self.controller, 'change', control, value={'type':'Number','value':'9'})
            self.assertEqual(result['error'], 'event_failed')
        self.assertEqual(self.server.session.form._data['total'], Decimal(0))

    def test_lost_response_locks_without_automatic_replay(self):
        state(self.controller)
        original = self.controller.session._exchange; calls=[]
        def lost(raw):
            calls.append(raw); original(raw); raise OSError('private transport details')
        self.controller.session._exchange = lost
        result = event(self.controller)
        self.assertEqual(result['error'], 'outcome_unknown')
        self.assertTrue(result['state']['uncertain'])
        self.assertEqual(event(self.controller)['error'], 'outcome_unknown')
        self.assertTrue(state(self.controller, 'snapshot')['state']['uncertain'])
        self.assertEqual(len(calls), 1)

    def test_server_error_keeps_authoritative_state_and_finite_reason(self):
        state(self.controller)
        original = self.server._routines[1]
        from yadinassi.syntax.parser import parse
        self.server._routines[1] = parse('&AtServer\nProcedure Run() ThisObject.Status="partial"; Raise "private"; EndProcedure')[0]
        result = event(self.controller)
        self.assertEqual(result['error'], 'event_failed')
        self.assertFalse(result['state']['uncertain'])
        self.assertIn({'type':'String','value':'partial'}, [x['value'] for x in result['state']['items']])
        self.assertNotIn(b'private', encode_line(result))
        self.server._routines[1] = original
        self.assertIsNone(event(self.controller)['error'])

    def test_failed_open_is_not_retried_on_reattach(self):
        calls=[]
        def failed(raw): calls.append(raw); return b'broken\n'
        controller=FormController(load_client(EXAMPLE), failed)
        result=state(controller)
        self.assertEqual(result['error'], 'outcome_unknown')
        state(controller); state(controller, 'snapshot')
        self.assertEqual(len(calls),1)

    def test_concurrent_exchange_and_prehello_snapshot_reject(self):
        with self.assertRaises(ValueError): state(self.controller,'snapshot')
        self.controller._gate.acquire()
        try:
            with self.assertRaises(LocalTransportError): state(self.controller)
        finally: self.controller._gate.release()

    def test_exact_request_and_value_admission(self):
        state(self.controller)
        for request_value in (True, 1.2, '1'):
            with self.assertRaises(ValueError):
                state(self.controller,'event',event='close',revision=request_value)
        with self.assertRaises(ValueError):
            event(self.controller,'change','FieldPrice',value={'type':'Number','value':1.2})


class FormProcessTests(unittest.TestCase):
    def process(self, directory=EXAMPLE, database=None):
        value = FormProcess(directory, database); self.addCleanup(value.close); return value

    def test_actual_separate_process_calculation_and_owned_cleanup(self):
        process=self.process(); controller=FormController(load_client(EXAMPLE),process.exchange)
        state(controller); result=event(controller)
        self.assertIsNone(result['error'])
        self.assertIsNone(controller.session.interpreter.database_context)
        self.assertEqual(next(x for x in result['state']['items'] if x['name']=='FieldTotal')['value']['value'],'60.30')
        event(controller,'close'); process.close()
        self.assertIsNotNone(process.child.poll())
        self.assertFalse(process._worker.is_alive())

    def test_sqlite_write_happens_only_in_server_and_survives_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned.sqlite'
            config=load_configuration_directory(PRODUCT/'configuration')
            context=SQLiteDBContext.create(path,config); context.close()
            process=self.process(PRODUCT,path)
            controller=FormController(load_client(PRODUCT),process.exchange); state(controller)
            for field,value in [('Code',{'type':'String','value':'P001'}),('Description',{'type':'String','value':'Owned product'}),('Amount',{'type':'Number','value':'12.75'})]:
                self.assertIsNone(event(controller,'change','Field'+field,value=value)['error'])
            result=event(controller); self.assertIsNone(result['error'])
            self.assertFalse(next(x for x in result['state']['items'] if x['name']=='RunButton')['enabled'])
            self.assertIsNone(controller.session.interpreter.database_context)
            event(controller,'close'); process.close()
            context=SQLiteDBContext(pa…8231 tokens truncated…s tests -v
python -m yadinassi basic.bsl
```

На Windows создайте окружение через `py -3 -m venv .venv` и активируйте
`.venv\Scripts\Activate.ps1` (PowerShell) или `.venv\Scripts\activate.bat` (cmd).
Установка `python -m pip install -e .` добавляет команду `yadinassi` без пакетов
для сборки. Тесты используют стандартный `unittest`.

### Ручной запуск тестов на платформе 1С

На компьютере с установленной 1С можно собрать и выполнить `.bsl` из
`integrational_tests/tests`, включая модули с процедурами и функциями:

```console
python integrational_tests/test_launcher.py --bd "C:\Bases\TestBase" --path-1c "C:\Program Files\1cv8\8.3.27.1859\bin"
```

Вывод сохраняется в `integrational_tests/output/<имя теста>.out`; новые результаты
игнорируются Git. Исторические Windows-данные для регрессионных проверок находятся
в [tests/fixtures/native_windows](tests/fixtures/native_windows).
Каталог `integrational_tests` содержит самостоятельный генератор эталонного
вывода на 1С. Его Python-проверки запускаются отдельно командой
`python integrational_tests/check_launcher.py`.
Инструкция и требования к базе: [integrational_tests/README.md](integrational_tests/README.md).

## Автономная сборка

```console
python scripts/build.py
```

Скрипт запускает PyInstaller в режиме `--onefile --console`, проверяет бинарник
вне дерева исходников и упаковывает его вместе с README, лицензией и примером.
Python, стандартная библиотека и модули интерпретатора включаются в бинарник.
При старте PyInstaller распаковывает содержимое во временный каталог.

| Цель | ОС и архитектура сборки | Бинарник | Архив |
| --- | --- | --- | --- |
| `windows` | Windows x86-64 | `dist/windows/yadinassi.exe` | `dist/yadinassi-<версия>-windows.zip` |
| `linux` | Linux x86-64 | `dist/linux/yadinassi` | `dist/yadinassi-<версия>-linux.tar.gz` |
| `mac-x86` | macOS Intel x86-64 | `dist/mac-x86/yadinassi` | `dist/yadinassi-<версия>-mac-x86.tar.gz` |
| `mac-arm` | macOS Apple Silicon arm64 | `dist/mac-arm/yadinassi` | `dist/yadinassi-<версия>-mac-arm.tar.gz` |

`python scripts/build.py --target mac-arm` дополнительно проверяет соответствие
хоста выбранной цели. PyInstaller [требует сборки на целевой ОС](https://pyinstaller.org/en/stable/),
поэтому платформы собираются отдельными заданиями GitHub Actions. Все четыре
сохраняются для tag и ручных запусков; для PR/main временное исключение описано ниже.
`mac-x86` означает 64-битный Intel, не 32-битный x86.

Linux-сборка использует Ubuntu 22.04 и требует совместимую glibc (2.35+);
это не статический musl-бинарник для Alpine. macOS-сборки в CI используют macOS
15 Intel и macOS 15 ARM. Совместимость с более старыми версиями ОС отдельно не
проверяется. Apple Developer ID / нотариализация и Authenticode-подпись Windows
в текущую сборку не входят.

## GitHub Actions и релизы

Workflow [`.github/workflows/build.yml`](.github/workflows/build.yml) работает
при push, pull request и ручном запуске через Actions → Test and build → Run workflow.
Первые попытки обычного PR workflow используют общую группу на номер PR:
новый запуск может отменить выполняющийся и заменить ожидающий запуск этой группы.
Повторные попытки, push в `main`, теги и ручные запуски изолированы по
`run_id` и `run_attempt`, поэтому не вытесняют друг друга или текущую первую
попытку PR. Это сокращает лишнюю работу, но не гарантирует ускорения очереди.
[Порядок допуска GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
не учитывает возраст SHA: запоздавшее первоначальное событие может попасть в
группу позже нового. Перед мержем обязательны успешные проверки текущего head
на всех требуемых платформах; отменённый запуск не считается успехом.

Временно обычные PR и push в `main` запускают light/heavy/package только на Linux,
Windows и macOS Intel. macOS ARM в этих запусках отсутствует: verdict явно содержит
`excluded_platforms=["mac-arm"]` и `full_coverage=false`; полнота тестов остальных
трёх платформ по-прежнему обязательна. Все tag push, включая не-`v` и теги с `/`,
и ручные запуски сохраняют ARM light/heavy/package и полное четырёхплатформенное
покрытие. Draft PR запускает только light, Ready PR также heavy и сборку.
Нативные workflow и их требования не изменяются. Подробности, проверка verdict и
задача возврата ARM: [tiered CI](docs/tiered-ci.md).

Для каждой включённой платформы при полном heavy-запуске workflow:

1. Устанавливает Python 3.12 и зависимости сборки.
2. Запускает тесты интерпретатора и CLI.
3. Собирает автономный бинарник.
4. Проверяет запуск файла, `-с`, консоли, стандартного ввода и обработку ошибок.
5. Загружает архив в артефакты задания.

Отдельный [нативный workflow](docs/native-1c-ci.md) автоматически запускает шесть
сценариев на настоящей учебной 1С в изолированном Docker для PR владельца из этого
репозитория в `main` и его push в `main`, включая Draft PR. Он создаёт свежие
результаты для текущего commit и сравнивает их с интерпретатором; ручная генерация
эталонов для этих событий не нужна. Форки исключены из этой проверки, отсутствие
нативного результата не считается успехом. Порядок пар Соответствия имеет
отдельный согласованный контракт, остальные результаты строгие. Старые Windows
fixtures сохранены отдельно в `tests/fixtures/native_windows`; теги и публикация релизов этим новым workflow не охвачены.

При push тега `v*`, после успешного завершения всех четырех сборок, workflow
создает GitHub Release с четырьмя архивами и `SHA256SUMS`. Используется встроенный
`GITHUB_TOKEN`, отдельные секреты не нужны. Право `contents: write` выдается
только заданию публикации; pull request не публикует релиз.

Перед релизом измените только `__version__` в `yadinassi/__init__.py`,
закоммитьте изменение и создайте соответствующий тег. Например, для `0.2.0`:

```console
git tag v0.2.0
git push origin v0.2.0
```

## Расширение интерпретатора

```text
исходный BSL → syntax/lexer.py → syntax/parser.py → syntax/ast.py → runtime.py → values.py
```

`syntax/lexer.py` содержит токены и словарь ключевых слов; `syntax/parser.py`
строит AST, не исполняя код; `syntax/ast.py` описывает узлы. Условная компиляция
и области исходного кода находятся в `syntax/preprocessor.py`. `runtime.py`
исполняет дерево, а `values.py` задает значения, преобразования и явно доступные
методы объектов.
`cli.py` отвечает за файлы и консоль. Код BSL не передается в Python `eval`/`exec`.

Фронтенд импортируется из `yadinassi.syntax.*`. Временные модули
`yadinassi.ast`, `yadinassi.lexer`, `yadinassi.parser` и `yadinassi.preprocessor`
удалены: это намеренное нарушение совместимости прямых Python-импортов.
Замените `import yadinassi.parser` на `import yadinassi.syntax.parser`,
`from yadinassi.parser import parse` на `from yadinassi.syntax.parser import parse`,
а `from yadinassi import ast` на `from yadinassi.syntax import ast`.
Аналогично перенесите импорты остальных модулей и обращения к их пространствам
имён; для monkeypatch используйте канонический `yadinassi.syntax.*`.
Совместимость старых Python pickle и introspection со старыми путями не
гарантируется. Публичный embedding API (`Interpreter`, `BSLError`,
`BSLRuntimeError`, `__version__`) сохраняется. Старые пути
`yadinassi.storage.*` удалены вместе с поддержкой физического формата 1С;
контекст базы и `--f` теперь используют SQLite.

Числовые реализации находятся в `yadinassi.numeric`: `math_conversion`,
`binary_exp`, `powers`, `elementary`, `bits`, `numbers` и `round_modes`.
Их прежние пути `yadinassi.<имя>` также удалены без совместимых aliases.
Например, замените `from yadinassi.numbers import round_number` на
`from yadinassi.numeric.numbers import round_number`, а
`from yadinassi import round_modes` на `from yadinassi.numeric import round_modes`.
Импорты функций, исключения `UnsupportedConversionRange`, таблиц `BUILTINS`,
классов `BSLRoundMode`, `BSLRoundModes` и singleton `ROUND_MODES` должны
использовать канонические модули. Зависимости для monkeypatch меняйте там же
(например, `Context` в `yadinassi.numeric.binary_exp`). Пакет `numeric`
не экспортирует функции поверх одноимённых подмодулей. Числовое поведение,
включая BSL-сериализацию, не изменено; старые прямые Python-импорты больше
не поддерживаются.

Для новой конструкции добавьте токены при необходимости, узел AST, правило
парсера и метод `Interpreter.visit_ИмяУзла`, затем тесты поведения и ошибок.
Новые встроенные функции и типы регистрируются без изменения парсера:

```python
from yadinassi import Interpreter

output = []
vm = Interpreter(output=output.append)
vm.register_function("Удвоить", lambda value: value * 2, "Double")
vm.execute('Сообщить(Удвоить(21));', source="example.bsl")
assert output == ["42"]
```

Для типа используйте `vm.register_type("Имя", factory)`. Объект с доступными из
BSL методами наследует `BSLObject` и реализует `get_member(name)`, возвращая
значение или `HostFunction`. Числовые результаты расширений возвращайте как
`Decimal`, логические как `bool`, неопределенное значение как `None`.
Имена функций, типов и переменных нормализуются через `casefold()`; расширение
нормализует имена своих методов в `get_member` самостоятельно.

Интерпретатор предназначен для исполнения доверенного кода: лимиты времени
и памяти не предусмотрены. Встроенные функции расширения исполняются с правами
Python-процесса.

## Лицензия

MIT, см. [LICENSE](LICENSE).

Клиентское [асинхронное ядро языка](docs/async-language.md) поддерживает
`Асинх` / `Async`, `Ждать` / `Await` и обещания с настоящим сохранением кадров.
Асинхронные семейства API платформы этим не добавляются.

### Replicated form applications

An opt-in browser form launcher runs client BSL locally and server BSL in a
separate owned process, optionally with server-only SQLite access.
See [run a replicated form application](docs/form-app.md) for a calculation
example and a persisted product-intake form. Plain BSL execution is unchanged.
