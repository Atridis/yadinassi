# Source-bound scratch database lifecycle

This experimental host persists admitted source files (XML, BSL and resources)
and the supported scalar constants in a private SQLite file. It is **not** a
native 1C database or activation of arbitrary configuration data objects.
Unsupported capabilities still fail explicitly when accessed.

Create once:

```sh
yadinassi --configuration-source source.zip --run-startup --source-scratch-db scratch.sqlite
```

Reopen from the saved database alone (no external XML/ZIP needed):

```sh
yadinassi --open-source-scratch-db scratch.sqlite --run-startup
```

Embedded XML/BSL/resources are read through a read-only SQLite handle and
re-admitted by the ordinary source importer. Nothing is extracted to disk and
reading source does not execute it. Startup still requires the explicit flag.
The package hash detects accidental damage, not malicious replacement by the
file owner. A source load alone does not verify stored values; normal reopen
checks all values before startup. There is no native database compatibility.

Optionally require the exact same external source package as an additional
binding check:

```sh
yadinassi --configuration-source source.zip --run-startup --open-source-scratch-db scratch.sqlite
```

Creation never overwrites a file. Reopen never creates a missing file and does
not migrate a normal database, a previous scratch format, or changed source.
The v3 format stores all source bytes for integrity checking; this does not
execute those bytes. Startup remains a separate explicit operation. Copying
source files into the DB does not imply support for their metadata or services.
No automatic configuration update is supplied. The existing `--save-source`
option can export the admitted package to a new archive; it never overwrites.

Reopen requires a cleanly closed file with no journal/WAL/SHM sidecars; it does
not perform recovery. A read-only schema preflight precedes opening a writable
handle. Reopen checks exact schema (including absence of extra triggers/views/indexes),
source identity and bytes, constant definitions and encoded values, and empty
extension state. Unsupported scalar defaults remain uninitialized except for
already measured cases. Files must be regular, non-symlinked, singly linked,
privately writable files in an approved private directory. Windows reparse
points are refused. File identity and schema/source binding are rechecked on
access. This is corruption/misuse detection, not protection against a hostile
process with the same OS account and arbitrary filesystem access.

An old v2 scratch file is deliberately refused; preserve it for inspection.
Do not rename an ordinary database to use this command. Use a new scratch file
for changed source until a separately designed migration capability exists.

## Explicit scalar transactions

Source server code can group supported constant writes using `BeginTransaction`,
`CommitTransaction`, `RollbackTransaction`, and `TransactionActive` (Russian aliases
are also available). Reads inside the transaction see pending values; other
connections see only committed data. An unhandled execution failure, unfinished
execution, or application close rolls pending writes back. A failed constant
read/write also aborts the active transaction. Caught unrelated BSL errors do not
implicitly commit; handle them with an explicit rollback.

This is a bounded local SQLite transaction contract, not native 1C parity.
Nested transactions, lock-mode arguments, async execution and client/server
transfers while active are refused. Only source-owned scalar constants participate;
catalogs, documents, registers, extension installation and external effects are
not added to the transaction. No schema migration or foreign database access is
introduced. A successful commit is durable; later execution failure cannot undo
an already completed commit.

## Наборы констант source scratch

`Constants.CreateSet("Flag, Text")` / `Константы.СоздатьНабор(...)` создаёт
буфер выбранных скалярных констант. Имена регистронезависимы; без аргумента
выбираются все объявленные константы, но неподдерживаемый тип приводит к отказу.
Поля можно заполнить явно, затем выполнить `Write()` / `Записать()`.
`Read()` / `Прочитать()` читает весь набор из одного снимка; ошибка оставляет
предыдущий буфер неизменным. Чтение видит записи текущей явной транзакции.
Запись набора атомарна; внутри явной транзакции она не выполняет её commit.
Ошибка чтения/записи хранилища откатывает активную транзакцию, как одиночные
операции констант. Изменение поля буфера само по себе не пишет в SQLite.

`Constants["Flag"]` и `For Each Manager In Constants` дают менеджеры констант,
с теми же проверками владельца, server-контекста и safe mode при каждом вызове.
Наборы тоже проверяют фактического вызывающего, включая сохранённые методы.

Это ограниченный локальный контракт, не результат native-измерения. Все поля
перед Write должны быть явно присвоены или успешно прочитаны. Неизмеренные
начальные значения и преобразование Undefined не предполагаются. Сохраняются
строгие квалификаторы и отказ на модули менеджеров значений, историю, проверку
заполнения и ограничения, которые runtime пока не исполняет. Конфликт имён
полей с Read/Write и их русскими именами, пустые/повторные имена, индексирование
набора и передача его полей по ссылке пока не поддержаны. CreateValueManager
не добавлен: его создание подразумевает исполнение модуля объекта.

Основа публичного API:
[объекты работы с константами](https://1c-dn.com/library/tutorials/practical_developer_guide_constant_script_objects/)
и [обработчики записи объектов](https://1c-dn.com/library/tutorials/practical_developer_guide_manipulating_object_data/).
Наличие CreateSet не означает реализацию этих обработчиков; записи с ними
по-прежнему явно отклоняются, а не обходят их.
