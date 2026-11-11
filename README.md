# yadinassi

![yadinassi logo](.github/large.png)

**Yet Another oDIN ASS Interpreter**  
Еще один интерпретатор кода BSL, написанный на Python 3.

## Mission

Только нативный синтаксис, только хардкор 🤘

## Запуск

Скачайте архив своей платформы из [GitHub Releases](https://github.com/Atridis/yadinassi/releases), распакуйте и запустите
 - `yadinassi.exe` для Windows.
 - `./yadinassi` для Linux/macOS

варианты запуска
```console
yadinassi basic.bsl                   # запуск на исполнение файла с кодом
yadinassi -c 'Сообщить("Привет")'     # запуск непосредственно кода
yadinassi                             # запуск интерактивного интерпретатора
```

`/help` выводит помощь;  
`/exit`, `/quit` или конец ввода завершают сеанс;  
`Ctrl+C` отменяет текущий ввод или исполнение. Консоль продолжает работу после
ошибки.

Дополнительные варианты:

```console
yadinassi --encoding cp1251 legacy.bsl
yadinassi - < basic.bsl
yadinassi --version
```

По умолчанию файлы читаются как UTF-8, BOM допустим. Потоки консоли используют
UTF-8. Вариант `-` читает стандартный ввод как один файл. Без аргументов
перенаправленный ввод обрабатывается как последовательность консольных команд,
без приветствия и приглашений.

Коды завершения: `0` — успех, `1` — ошибка чтения/синтаксиса/исполнения,
`2` — неверные аргументы CLI, `130` — прерывание исполнения файла через Ctrl+C.
Консоль возвращает `1`, если за сеанс возникали ошибки.

### База приложения SQLite

Без базы автономный BSL продолжает работать. `--f SQLITE_FILE` выбирает
существующий файл SQLite Yadinassi, а не файловую базу 1С:
Без `--f` ни база, ни сервер не требуются. Явный `--f` выбирает локальный
режим приложения (толстый клиент); отсутствующий файл не создаётся автоматически.
Отдельные client-only/server-only режимы — будущая работа, имена флагов не заданы.

```console
yadinassi --f "/path/to/application.sqlite" basic.bsl
yadinassi --f "/path/to/application.sqlite" -c 'Сообщить(СтрокаСоединенияИнформационнойБазы());'
```

Конфигурация поступает из официальной XML-выгрузки Designer. SQLite хранит
её исходники XML/BSL и данные поддержанного среза справочников. Сохранение
исходника не означает автоматический запуск его обработчиков: неподдержанная
семантика отклоняется явно. [Python API и ограничения](docs/file-database-context.md).

Создание базы выполняется только отдельной явной командой:

```console
yadinassi --create-db application.sqlite --import-xml /path/to/designer-xml
```

`--inactive` сохраняет исходники неподдержанной конфигурации без допуска к
исполнению. Эта архивная база не открывает чтение/запись прикладных объектов.

Чтение `.1CD`, CF/DT и внутренних CONFIG/PARAMS/DBNames удалено; прежние
эксперименты доступны в истории Git. Для новых баз доступен [ограниченный цикл непроводимых документов v7](docs/sqlite-document-lifecycle.md): создание, запись, чтение, нумерация и табличные части. Регистры и проведение не поддержаны. Для справочников и их табличных
частей доступны [ограниченные запросы с соединениями и сводными итогами](docs/relational-catalog-queries.md),
[вычисляемыми полями и условными отчётами](docs/computed-catalog-queries.md),
[пакетами и временными таблицами](docs/query-packages-temporary-tables.md),
[объединениями и типизированными внешними таблицами](docs/query-unions-external-sources.md). Реальная 1С остаётся эталоном поведения BSL через официальные
XML/BSL-интерфейсы, а не эталоном внутреннего формата хранения.

`InfoBaseConnectionString()` / `СтрокаСоединенияИнформационнойБазы()` возвращает
`SQLite=<абсолютный путь>`: это идентичность host-backend, не нативный `File=`.
Без выбранной базы DB-вызовы дают перехватываемую ошибку `db required`.
`--user` и `--psw` не поддержаны. Headless-клиент и его границы описаны
в [UI-протоколе](docs/ui-protocol-v0.md); это не GUI и не управляемые формы 1С.

### Локальный редактор справочников (экспериментальный)

```console
python -m yadinassi.ui.local_app --f "/path/to/application.sqlite"
# После установки Python-пакета: yadinassi-catalog --f application.sqlite
# Для автономного исполняемого файла (Windows: yadinassi.exe):
yadinassi --catalog-ui --f application.sqlite
```

Откройте напечатанный локальный URL: список → карточка → создание/редактирование
скалярных полей → Save → повторное открытие сохранённой базы. Ссылки пока только
для чтения; это автоформы, а не импортированные формы 1С. Выбранный файл изменяется
только реальным Save. Node и интернет при запуске не нужны; браузер не исполняет
BSL. Браузер автоматически не открывается без `--open-browser`.
[Запуск, ограничения, сохранение и безопасность](docs/catalog-editor.md).

### Мини-демо с исходными обработчиками

Из корня репозитория, после установки зависимостей Python, создайте новую
демо-базу и запустите редактор двумя командами:

```console
python -m yadinassi --create-demo-db demo.sqlite --import-xml tests/fixtures/demo_cf/source
python -m yadinassi.ui.local_app --f demo.sqlite --open-browser
```

Доступны **ВидыНоменклатуры**, **Склады** и **Номенклатура** с исходными
обработчиками демо. База изначально пустая. Для следующих запусков выполняйте
только вторую команду: создание никогда не перезаписывает существующий файл.
Это ограниченный локальный редактор, не нативные управляемые формы 1С.
[Пошаговый запуск и проверка сохранения](docs/demo-quickstart.md).

### Прикладные формы с клиентским и серверным BSL

```console
python -m yadinassi.ui.form_app examples/forms/estimate --open-browser
python -m yadinassi --create-db orders.sqlite --import-xml examples/forms/order-intake/configuration
python -m yadinassi.ui.form_app examples/forms/order-intake --f orders.sqlite --open-browser
python -m yadinassi.ui.form_app examples/forms/order-editor --f orders.sqlite --open-browser
```

Первый пример вычисляет итог, второй позволяет добавить и отредактировать строки,
выбрать и удалить строку, пересчитать суммы и сохранить шапку с табличной частью
справочника одним серверным `Write`. Третий открывает существующий заказ целиком,
сохраняет ту же запись, позволяет продолжать редактирование и явно отменять правки.
Браузер отображает форму; клиентский BSL
исполняется локально, серверный BSL и SQLite работают в отдельном процессе.
Старые скалярные пакеты совместимы. Это ограниченный host-API, не импорт форм 1С.
[Запуск и границы](docs/form-app.md), [таблицы и создание заказа](docs/form-tables.md),
[редактирование существующих заказов](docs/order-workbench.md).
Отдельный [пример заказов со ссылками](docs/reference-orders.md) добавляет выбор
контрагента и товара через подчинённую форму, с сохранением точных типизированных
ссылок. Для него создаётся новая база по отдельной конфигурации; прежние примеры
и их базы не меняются.

## Разработка

Описание новых возможностей и примеры см. в [features.md](features.md).

### Окружение и тесты

Python 3.10 или новее. Для редактирования строк консоли используется
`prompt_toolkit`, который устанавливается автоматически вместе с проектом.
При сборке редактор строки включается в бинарник вместе с остальными зависимостями.

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[build]"
python -m unittest discover -s tests -v
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
example and a persisted product-intake form. The [existing order workbench](docs/order-workbench.md)
loads full headers and lines, saves the same record, and supports explicit discard
and optimistic-conflict feedback. The separate [reference Orders workspace](docs/reference-orders.md)
adds an owned customer/product choice, then saves and reopens exact typed catalog
references. It uses a new opt-in configuration, not a migration or generic
reference wire codec. Plain BSL execution is unchanged.

### Конфигурационные управляемые формы

Явный opt-in launcher выполняет объявленные XML-формы с единым Module.bsl,
разделением клиента/сервера, OpenForm и несколькими удерживаемыми вкладками.
[Границы профиля и два разных примера](docs/configuration-forms.md).

Отдельный [application host](docs/configuration-application-host.md) объединяет
CommonModules, запуск/закрытие приложения и управляемые формы. Один browser tab
владеет вводом; повторное открытие URL требует явной передачи управления.
Закрытие последней вкладки не выполняет Save/Discard: безопасное завершение
зависит от состояния приложения и проходит через обычные обработчики закрытия.

Отдельный [профиль форм документов](docs/configuration-document-forms.md) открывает
объявленные XML-формы непроводимых документов: шапка, типизированные строки,
команды над списком, атомарная запись и повторное открытие из SQLite. Список
обновляется сразу после записи, соседние черновики сохраняются. Пример Orders
не проводит документы и не имитирует движения или события ObjectModule;
профиль включается явно для новой базы и не расширяет старые конфигурации.

[Смешанное приложение конфигурации](docs/configuration-business-application.md)
добавляет отдельный opt-in `configuration_business_v1`: общие формы и модули,
запуск приложения, скалярные справочники и непроводимые документы с табличными
частями работают в одном управляемом runtime. Пример
`examples/configuration-business-application` запускается с
`--business-application --f existing.sqlite` после явного создания новой базы.
Это не миграция, не поддержка проведения и не замена типизированных ссылок строками.


[Типизированные ссылки в приложении конфигурации](docs/configuration-reference-application.md)
включаются отдельным профилем `configuration_references_v1` для новой базы:
CatalogRef в карточке справочника, шапке документа и строках табличной части.
Выбор существующей записи, очистка типизированной пустой ссылки и отмена
работают через принадлежащий форме picker; сервер хранит настоящие ссылки,
а браузер не получает UUID записей. Generic Invocation, старые source grants,
миграция и проведение этим профилем не расширяются.

[Типизированный ввод скалярных полей](docs/typed-form-scalar-editors.md)
использует объявленные квалификаторы формы: даты отображаются и вводятся без
часовых поясов, числа и строки проверяются до отправки без скрытого округления,
обрезания или ограничения диапазона. Ошибочный черновик сохраняется для
исправления; замена поля или строки не перенаправляет его в другой объект.
Пример `examples/configuration-scalar-editors` сохраняет DateTime справочника,
шапки документа и строк в существующем явном reference-профиле. Схемы хранения,
generic Invocation, миграции и права транзакций не расширяются.
