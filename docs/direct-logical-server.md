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

- `NoContext`, dual/async, серверные initializers и imports не подключены. Существующий native `client_probe.bsl` поэтому
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
