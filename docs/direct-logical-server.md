# Прямые логические серверные вызовы

Прямой движок исполняет синхронные `&AtServer` / `&НаСервере` функции и
процедуры с `Val` / `Знач` и именованными byref-параметрами (включая defaults) через отдельный
сгенерированный Python-код. Старые AST dispatch, `block` и `call_routine`
не используются. Это логическая сторона внутри процесса, не сетевой сервер.

При переходе с клиента создаётся новое серверное состояние. Рекурсивные и
вложенные серверные вызовы используют это состояние; после возврата оно
не сохраняется для следующего клиентского вызова. Клиентские переменные
не доступны серверному коду. Серверный вызов клиентской процедуры запрещён
до вычисления аргументов. Профиль препроцессора и текущая runtime-сторона
остаются разными понятиями.

Аргументы и результат копируются по ограниченному протоколу: скаляры,
поддержанные Date, Array и Structure (как прямые, так и canonical значения).
Общий лимит составляет 10000 узлов и глубину 64; циклы отвергаются, общие
дочерние объекты копируются по отдельности. Произвольные Python-объекты,
ресурсы и ссылки на объекты БД не получают нового допуска.

Server layout учитывает предыдущие объявления. При расширении layout старые
планы нужно переобъявить: обращение к stale плану отвергается до source effects.
Объявление серверных переменных без серверной процедуры в том же execute
пока отвергается явно. Prepared-планы не сохраняют состояние или разрешения.

## Явные ограничения

- Async и imports не подключены. Существующий native `client_probe.bsl` поэтому
  **по-прежнему не выполняется целиком**.
- DB namespace и Query на сервере не добавлены этим пакетом. Отдельные формы
  и configuration runtime сохраняют свои собственные точки входа.
- Неподдержанное имя внутри routine может дать текущий raw `NameError`
  компилятора. Полнота `ErrorDescription`/error-info не подтверждена.
- Не заявляются native parity, зелёный полный CI или улучшение скорости.

Проверки: `tests/test_python_direct_server.py` проверяет source/AST/prepared,
повторные вызовы, отдельное состояние и runtime-сторону, copied collections,
общий лимит смешанных контейнеров, cycles, закрытие владельца, отказ обратного
вызова, изменение layout и отсутствие VM dispatch.

## Именованные серверные byref-параметры

После base `2b492f54338a8ffbf77674e53204ed20f3982c7e` клиентские имена
переменных могут принимать copyback. Сохраняется адрес, а входное значение
читается после эффектов всех аргументов. Каждый формальный параметр получает
независимую копию; после успешного возврата выходы публикуются в порядке
параметров, поэтому при повторном имени выигрывает правый параметр, даже если
его значение не менялось. Same-side вызовы сохраняют обычные byref-ссылки.

Весь пакет `[result, outputs...]` проверяется и копируется с общим лимитом до
первой записи в клиент. Escaping error, cycle, общий budget failure и закрытый
владелец не публикуют частичный copyback. Result и каждый output копируются
независимо. Параметр по умолчанию без actual не создаёт клиентского output.

Имена хранят частную provenance-метку канонической Reference. Локальные
ячейки/слоты и безопасная цепочка именованных forwarded refs допускаются;
property/index и forwarded property/index не получают эту метку. Произвольная
host Reference тоже не становится copyback sink. Эту metadata нельзя получить
через BSL reflection; trusted host остаётся владельцем своих capabilities.

125 targeted tests прошли normal и -O, дополнительно 8 managed-profile tests
прошли в обоих режимах. Independent review: 85 tests -O, blockers нет. Новые
проверки: source/AST/prepared, late read, rightmost output, nested/separate-module
byref, forwarded sink refusal, общий budget обоих направлений, независимые
коллекции, escaping errors, defaults и закрытие runtime.

Неизменённый scalar-copyback блок `scripts/native_1c_bootstrap/client_probe.bsl`
между маркерами `BEGIN bounded scalar copyback measurement` и
`BEGIN bounded object transfer measurement` теперь выполняется целиком:
35 records, 33 совпадают с explicit compiled-strict control. Нулевые индексы
10 и 13 дают `{"B",0}` вместо `{"B",1}` из-за существующего пустого
ErrorDescription в direct-handler. Native fixtures не переписывались; это
документированное расхождение, а не заявление parity.

Полный неизменённый source теперь останавливается на `imports/server
initialization are not integrated` (frontend расположил initializer раньше
следующего NoContext в AST). Настоящий owned-SQLite verifier по-прежнему
возвращает `interpreter_failed`, без witness records. Отдельный неизменённый
object-transfer блок возвращает `object.runtime-error`, stage 8: TypeOf для
прямой Structure пока не поддерживается. Эти ограничения не скрыты byref-фиксом.

```sh
PYTHONPATH=tests:scripts:. python -O -m unittest test_python_direct_server_byref test_python_direct_server test_python_direct_persistent test_python_direct_prepared_admission test_python_direct_managed_profile
```

## Серверная инициализация

Срез поверх `ed6feafb30f5a1b734534b21ea5620bed92852b0` компилирует явно
выделенные frontend ServerInitializer bodies в отдельные Python-планы. При
загрузке клиентского модуля они не исполняются. При каждом новом клиентском
вызове сервера создаётся state, затем все установленные initializers исполняются
в порядке загрузки, затем вызывается процедура. Вложенные серверные вызовы
используют тот же state и повторно initialization не запускают. Initializer может
вызывать серверные процедуры через существующий direct service boundary.

Повторная загрузка, включая execute_prepared, добавляет initializer повторно,
как существующий runtime. Замена routine не удаляет ранее установленные
initializers. Хранятся code/facts, не closures или состояние. Все initializer
constructor bindings и транзитивные routine dependencies проверяются заново;
prospective metadata учитывается до клиентских source effects. Prepared layout
проверяется на текущем получателе. Init-only source допускается при существующем
server layout; отдельное объявление server Var без routine остаётся прежним gap.

При расширении server layout ранее скомпилированный initializer не получает
новые имена молча: требуется свежий Interpreter и повторная загрузка исходников.
Ошибка initialization не вызывает процедуру, не публикует byref copyback и
восстанавливает client context. Source location сохраняется; закрытие владельца
и обратный вызов client из server остаются запрещёнными.

**144 targeted normal + 144 optimized PASS**, independent review **78 optimized
PASS**, включая prepared/source-map и SQLite validator boundaries. Source-map
из audit10 сохранён без изменений. Тесты находятся в
`tests/test_python_direct_server_initializers.py`.

Из оригинального `client_probe.bsl` без изменения BSL взяты module-context
объявления, соответствующий measurement block и заключительная initialization.
Direct/control дают 10 records, 9 совпадают. Counters: client10→11; server
initial100, nested111, следующий crossing снова100. Индекс6 False вместоTrue —
старый ErrorDescription gap, не полная parity. Native fixture не изменён.

Полный original source теперь проходит initializer admission и останавливается
на `async/NoContext source routines are not integrated`. Настоящий owned-SQLite
verifier всё ещё возвращает `interpreter_failed` без witness values. NoContext,
dual и другие указанные ранее gaps не сняты этим срезом.

```sh
PYTHONPATH=tests:scripts:. python -O -m unittest test_python_direct_server_initializers test_python_direct_server test_python_direct_server_byref test_python_direct_persistent test_python_direct_prepared_admission test_python_direct_managed_profile
```

## Серверные процедуры без контекста

Срез поверх `9f7270993c0db86d4d8393d3c6bc2f9afda5df02` допускает синхронные
`&AtServerNoContext` / `&НаСервереБезКонтекста` процедуры напрямую. Их отдельный
Python-план не получает клиентских или серверных module globals. Вызов с клиента
не запускает серверные initializers; contextual server → NoContext создаёт
отдельный scope, сохраняя обычные same-side byref-ссылки. NoContext → contextual
server и NoContext → client отвергаются до вычисления аргументов.

Client crossing сохраняет существующие transfer limits и атомарную публикацию
проверенного copyback. Ошибка не публикует выходы клиенту; ошибка same-side
вызова не отменяет уже сделанную запись по ссылке. Проверяются текущий владелец,
server side и отсутствие module-context capability. Закрытие/reset runtime
в callback не повреждает новые корневые context stacks при выходе: снимается
именно захваченный stack. Pure NoContext declaration groups не зависят от
server layout и initializers; смешанные группы сохраняют прежнюю консервативную
валидацию всей группы. План не хранит состояние или долгоживущий допуск.

**159 targeted normal + 159 optimized PASS**. Independent review: blockers нет;
после исправления unwind выполнены 9 NoContext optimized tests и 4 дополнительные
close/reset probes через оба вида перехода. Тесты:
`tests/test_python_direct_nocontext.py`, соседние server/byref/initializer,
persistent/prepared, managed-profile, configuration/database и boundary suites.

Неизменённый блок между `BEGIN bounded no-context witness` и
`BEGIN bounded dual witness` исходного `client_probe.bsl` даёт все 15 records.
С explicit compiled-strict control совпадают 12; индексы 6, 8, 12 дают False
вместо True из-за прежнего ErrorDescription gap. Все state/copyback значения
совпадают. Полный original source теперь останавливается на
`async/dual source routines are not integrated`; настоящий owned-SQLite verifier
по-прежнему возвращает `interpreter_failed`. Ни native parity, ни полный зелёный
CI не заявляются; исходный fixture не менялся.

```sh
PYTHONPATH=tests:scripts:. python -O -m unittest test_python_direct_nocontext test_python_direct_server_initializers test_python_direct_server_byref test_python_direct_server test_python_direct_persistent test_python_direct_prepared_admission test_python_direct_managed_profile
```

## Общие клиент-серверные процедуры без контекста

Срез поверх `5a78cac5b34cf58cc9919b6656940365d31f8850` компилирует две версии
`&AtClientAtServerNoContext` / `&НаКлиентеНаСервереБезКонтекста` напрямую.
Frontend уже выбирает разные тела для сторон; runtime выбирает соответствующий
Python-план по текущей стороне. Клиентская версия исполняется в отдельном scope
без globals; серверная использует существующий NoContext route. Локальные и
persistent вызовы не возвращаются в VM dispatch. Same-side byref и aliasing
коллекций сохраняются, включая записи до escaping exception. Контекстные вызовы
из dual отвергаются до вычисления аргументов. NoContext client→server переход
сохраняет существующие aggregate transfer/copyback checks.

Допускается пара с общей source-token provenance и одинаковой сигнатурой;
частичные пары после условной компиляции и различающиеся default/parameter
сигнатуры пока явно отвергаются до effects. Это ограничение direct implementation,
не заявление об ограничении языка. Group replacement и prepared current-binding,
owner/side/module-context/transaction проверки сохранены. Scope не кеширует допуск
или VM; callback close/reset снимает захваченный stack.

**169 normal +169 optimized tests PASS**, independent review **58 optimized PASS**,
blockers нет. Новые проверки находятся в `tests/test_python_direct_dual.py`:
source/AST/prepared/persistent, side-specific compilation, aliasing/error writes,
context isolation, отказ до argument effects, malformed pairs и close/reset.

Неизменённые объявления dual witness теперь загружаются. Positive вызов его
оригинальной `DualProbeOperation` совпадает с explicit compiled-strict:
scalar12, aliased array32, profile mask0. Нулевые AtClient/AtServer flags внутри
dual сохраняют текущую политику препроцессора и не выводятся из runtime side.
Отдельная standalone проверка Client/Server branches даёт4/8/8 для client/server/
server-NoContext callers. Исходный `CollectDualDirectiveProbe()` доходит до
controlled failure, но его ErrorDescription guard делает rethrow из-за прежнего
пустого diagnostic description. Полного результата этого witness нет.

Полный original `client_probe.bsl` теперь проходит dual admission и останавливается
на `constructor ПараметрыЗаписиJSON`. Настоящий owned-SQLite verifier остаётся
`interpreter_failed`. Fixtures не менялись; native parity, полный CI и ускорение
не заявляются.

```sh
PYTHONPATH=tests:scripts:. python -O -m unittest test_python_direct_dual test_python_direct_nocontext test_python_direct_server_initializers test_python_direct_server_byref test_python_direct_server test_python_direct_persistent test_python_direct_prepared_admission test_python_direct_managed_profile
```

## ErrorDescription в прямых обработчиках

Срез поверх `88438f0ed93833aca5ff494ec3530ab880e64214` добавляет диагностический
scope только при входе в сгенерированный `Except`. Recoverable Python errors
нормализуются существующим source mapper; ErrorDescription/ОписаниеОшибки читает
текущее обработанное исключение. VM block/call dispatch не используется.

Состояние принадлежит activation boundary. Обычные и dual same-side вызовы
разделяют handler frames, client→server crossing получает пустой scope. Вложенный
обработчик удаляет сведения об outer error, как existing control; выход, return
и escaping exception снимают frame через finally. Bare Raise сохраняет original
error, а повторный Raise после вложенного handler отвергается вместо оживления
устаревшего исключения. Внешний Python except не становится BSL diagnostic scope.

Подменяется только сервис, привязанный к текущему VM и исходному canonical
методу: identity сохранена при загрузке runtime. Пользовательская регистрация,
class-level override, проверка арности и текущие boundary checks сохранены.
Fail-closed ошибки по-прежнему не ловятся BSL handler. ExceptionInfo и расширенные
поля ошибки этим срезом не подключены; это не полная совместимость diagnostics.

Исходные BSL fixtures не менялись. С explicit compiled-strict control теперь
полностью совпадают bounded blocks: scalar-copyback35, module-context10,
NoContext15 и dual9 records. Dual witness наконец завершается. Оригинальный
numbers checkpoint даёт421 records, как control, вместо427: шесть format-stream
ошибок распознаются, поэтому дополнительные `.error.other` записи не исполняются.
Тест сохраняет проверки всех шести true predicates и отсутствия error.other.

После объединения с JSON/regex полный original client source останавливается
на `UnsupportedNakedSyntax: statement Execute` при подготовке серверного
NoContext-плана. Настоящий owned-SQLite verifier остаётся `interpreter_failed`.
Старый `test_exact_source_errors_and_partial_effects` воспроизводимо красный и
на base3c9dde8f: Python array wording отличается от отдельного экспериментального
array helper; этот тест и его expectation не ослаблялись.

Integrated verification:203 tests PASS на Python3.12 normal и203 PASS на
Python3.10 optimized. Independent integration review:65 optimized tests PASS, включая обязательный
`regex_binding_released_without_cyclic_gc`; ServicesBoundary и omission capability
из JSON/regex сохранены. Новые lifecycle/scope/provenance regressions:
`tests/test_python_direct_error_description.py`.

```sh
PYTHONPATH=tests:scripts:. python -O -m unittest test_python_direct_error_description test_python_direct_regex_services test_python_direct_dual test_python_direct_nocontext test_python_direct_server_byref test_python_direct_server_initializers test_python_direct_managed_profile
```

## Execute в direct scope

Следующий срез поверх c8999470 подключил dynamic Execute/Выполнить через прямую
компиляцию с живыми ссылками и отдельными temporary names, включая server и dual.
Полный исходный native child теперь завершается, но сравнение ещё не проходит
из-за object-transfer и Date/Null graph observations. [Механизм, проверки и точный
отчёт](direct-execute.md).
