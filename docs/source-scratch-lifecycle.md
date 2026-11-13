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
No automatic configuration update is supplied. Explicit additive source updates
are described below. The existing `--save-source`
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
строгие квалификаторы и отказ на неподдержанные части модулей менеджеров, историю,
проверку заполнения и ограничения, которые runtime пока не исполняет. Конфликт имён
полей с Read/Write и их русскими именами, пустые/повторные имена, индексирование
набора и передача его полей по ссылке пока не поддержаны. Поддержка CreateValueManager и её границы описаны ниже.

Основа публичного API:
[объекты работы с константами](https://1c-dn.com/library/tutorials/practical_developer_guide_constant_script_objects/)
и [обработчики записи объектов](https://1c-dn.com/library/tutorials/practical_developer_guide_manipulating_object_data/).
Наличие CreateSet не означает полной реализации этих обработчиков; неподдержанные
части жизненного цикла явно отклоняются, а не обходятся.

## Синхронные менеджеры значений и обработчики записи

`Constants.Text.CreateValueManager()` возвращает source-owned менеджер с
`Value`/`Значение`, `Read`/`Прочитать`, `Write`/`Записать` и
`Metadata`/`Метаданные`. Value нужно явно присвоить либо прочитать; начальное
значение не угадывается. Состояние переменных модуля сохраняется при повторном
использовании одного менеджера. Прямой Set и запись набора создают временные
менеджеры и используют тот же путь записи.

Поддержан синхронный `BeforeWrite(Cancel)` / `ПередЗаписью(Отказ)`, затем запись,
затем `OnWrite(Cancel)` / `ПриЗаписи(Отказ)` в одной SQLite-транзакции. Перед
записью обработчик может изменить Value; квалификаторы проверяются повторно.
Cancel должен оставаться Boolean. True или исключение откатывает все изменения
набора и активной внешней транзакции. Успех не коммитит внешнюю транзакцию.
Изменение Value в OnWrite не повторяет SQL-запись. Блок не заявляет native parity.

Модуль может содержать объявления переменных и синхронные процедуры/функции,
включая локальные помощники. Секции инициализации и Export описаны ниже.
FillCheckProcessing, подписки на события, data history и
прочие прежние write policies ещё не поддержаны и явно отклоняются. Стандартное создание менеджера 1С исполняет модуль; ограничения локальной
инициализации перечислены ниже и не выдаются за полную совместимость.

Обработчик не может перехватить управление транзакцией (Begin/Commit/Rollback),
запустить рекурсивную запись констант или перенести активную транзакцию через
async/client-server границу. Чтение констант и синхронные помощники доступны.
Safe mode и владелец проверяются на фактическом caller, в том числе для
сохранённых методов. Внешние эффекты BSL, например вывод сообщений, не являются
частью rollback SQLite.

Контракт событий основан на
[порядке событий записи констант](https://kb.1ci.com/1C_Enterprise_Platform/Tutorials/Practical_developer_guide_8.3/Quick_developer_reference/Constants/Event_sequence_for_writing_constants_from_constant_forms__save_and_close_/)
и [примерах OnWrite(Cancel) менеджера константы](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Creating_and_modifying_metadata_objects/Scheduled_jobs/Scheduled_jobs_____General_requirements/).
Это описанный локальный subset, а не подтверждение полного поведения 1С.

## UUID и сохраняемое ХранилищеЗначения

Source-константы с одиночными типами `v8:UUID` и `v8:ValueStorage` можно
записывать через обычные менеджеры, наборы и обработчики. UUID требует точного
runtime UUID, без автоматического преобразования строк. ValueStorage требует
явного `New ValueStorage(...)`, не оборачивает произвольный объект автоматически.
Неинициализированные значения по-прежнему дают ошибку, а не выдуманный default.

Хранилище сохраняет поддержанные локальным snapshot-движком значения: скаляры,
структуры/массивы/соответствия и фиксированные варианты, binary data, вложенные
хранилища, ограниченные типизированные таблицы и сжатые payloads. Повторные Get
и чтение после reopen дают независимые экземпляры; изменения извлечённого
объекта не меняют сохранённое значение до новой записи.

Используется только **собственный формат source scratch**
`yadinassi-source-storage-v1`: закрытая грамматика тегированных JSON-примитивов.
Нет pickle, загрузки классов, eval, native-десериализации или обращения к чужой
базе. Чтение проверяет версию, типы, canonical representation, глубину/размер и
полную валидность snapshot, включая таблицы и ограниченную распаковку. Порча
значения прерывает чтение/reopen; внутри транзакции ошибка чтения откатывает её.

Сохраняется прежний предел **65 536 UTF-8 байт на закодированное значение**.
Дополнительно framing ограничен 60 000 учётных единиц и глубиной 160; после
распаковки действуют прежние in-memory snapshot budgets. Большой несжатый
payload явно отклоняется; Deflation можно использовать в существующем
поддержанном срезе. Это локальные лимиты, не ограничения платформы 1С.
Составные declaration types, ссылки на объекты, автоматические конвертации,
история и неподдержанные write policies не активируются этим расширением.

Скалярные scratch-файлы с прежними поддержанными объявлениями сохраняют схему.
Если новый runtime иначе классифицирует ранее неподдержанное объявление,
source/schema binding не совпадёт: такую старую scratch-базу нужно сохранить
отдельно и создать новую. Автоматической миграции и молчаливого изменения схемы нет.

[Официальные рекомендации о ValueStorage](https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Standards/Values_and_types/)
подтверждают назначение API, но не формат этого хранилища. Native parity и
совместимость с proprietary сериализацией 1С здесь не заявляются.

## Явное совместимое обновление исходников scratch-базы

```sh
yadinassi --configuration-source changed-source.zip --update-source-scratch-db scratch.sqlite
```

Это отдельная операция без запуска BSL, создания UI или применения обычной базы.
Она сохраняет значения констант при правках модулей/ресурсов и совместимом
добавлении объявлений. После успеха новую версию можно явно запустить отдельной
командой `--open-source-scratch-db scratch.sqlite --run-startup`.

Обязательны прежний UUID конфигурации и прежние UUID, имена, виды и квалификаторы
всех уже поддержанных констант. Удаление, переименование, замена UUID, изменение
типа и даже расширение квалификатора отклоняются: сложной миграции здесь нет.
XML ранее неподдержанных констант должен оставаться неизменным. Новые объявления
допускаются, но unsupported типы от этого не получают реализацию. Новые значения
не угадываются: инициализируется только ранее измеренный String(64) default.

Сначала проверяются прежний embedded source, схема и значения. Под
`BEGIN IMMEDIATE` эти проверки повторяются и затем одним commit заменяются
исходники, binding и определения констант. Прежние закодированные значения не
переписываются. Ошибка до commit откатывает **всю** замену, включая новые default
значения. После успеха старый external source и открытые дескрипторы прежней
версии не проходят binding-проверку. Восстановление journal/WAL, работа с чужими
базами и молчаливое изменение старых форматов не выполняются.

`--run-startup`, `--save-source` и другие режимы базы несовместимы с обновлением.
Принятие XML не означает, что новый BSL компилируется или поддержан runtime:
проверка запуска остаётся явным отдельным действием. Новые write policies,
например включённая история, сохраняются в схеме и могут запретить последующие
записи; обновление не обходит эти ограничения.

Операция не заменяет резервную копию: перед намеренной сменой кода сохраняйте
чисто закрытый scratch-файл, если нужна возможность вернуться к старой версии.

## Секции инициализации и Export менеджера константы

Модуль ValueManager теперь выполняет синхронную секцию инициализации при
создании каждого экземпляра. Экспортированные переменные доступны как живые
поля, экспортированные процедуры/функции вызываются обычным BSL-dispatch с
аргументами по ссылке и значениями параметров по умолчанию. Приватные поля и
подпрограммы не становятся публичными. ThisObject/ЭтотОбъект обозначает этот
экземпляр; Value/Значение остаётся типизированным полем с прежними проверками.
Сохранение manager property по ссылке не расширяет межконтекстный перенос.

Локальная гарантия source host: инициализация и связанная запись Set/набора
проходят в одной SQLite-транзакции. Публичный CreateValueManager коммитит
успешные DB-эффекты своей инициализации только при отсутствии внешней
транзакции. При внешней транзакции commit остаётся у вызывающего. Init-код не
может выполнить Begin/Commit/Rollback; циклическое создание одного менеджера и
цепочки глубже32 отклоняются. После пойманного storage rollback никакая
последующая запись внутри initializer не может незаметно открыть новую
транзакцию. Провалившийся частично опубликованный экземпляр помечается
непригодным для дальнейшего использования.

Safe mode и реальные owner/server-права проверяются при каждом экспорте,
чтении и присваивании поля. Init имеет отдельный safe-mode frame, не выключает
ограничения вызывающего и не оставляет собственный frame после возврата.
Асинхронные и клиентские переходы через активную транзакцию запрещены прежним
механизмом. Pending-задачи запрещены до создания и вызова экспортов.

Это **локально проверенная семантика**, а не новый native результат о
транзакционной фазе инициализации 1С. Общие BSL-внешние эффекты, например
сообщения и изменение стороннего объекта в памяти, SQLite rollback не отменяет.
FillCheckProcessing, event subscriptions, data history, альтернативные режимы
записи и неподдержанные metadata policies не активированы. Стандартные имена
Value/Read/Write/Metadata и русские алиасы нельзя перекрыть объявлениями модуля;
такие конфликты дают явный отказ.

### Составные типы source-констант

Поддерживается закрытое объединение двух–32 различных уже поддержанных
типов: String, Number, Boolean, Date, UUID, ValueStorage и source-перечисления. Qualifiers каждого
типа сохраняются; значения не приводятся, не обрезаются и не округляются.
`Undefined` можно записать явно. Неинициализированное значение пока остаётся
ошибкой: новый результат измерения defaults на 1С этим блоком не заявляется.

Set, CreateSet и менеджеры используют тот же codec и транзакции. Persisted
значение содержит тег конкретного члена объединения, проверяемый при чтении;
Null, неизвестные типы, повторные типы, ссылки каталогов/документов и неизвестные qualifiers не
активируются. Обновление source не меняет состав или qualifiers существующей
константы, даже если изменение кажется расширением. Предыдущие значения
сохраняются без перекодирования. Старые scratch-файлы, где такая декларация
была unsupported, не мигрируются автоматически.

Основания: [официальное описание констант](https://1c-dn.com/download-trial/files/guides/developer_guide.pdf)
допускает compound type; [TypeDescription](https://1c-dn.com/library/specifics_of_typedescription_object/)
описывает Undefined в составных типах. Это документационно обоснованный
локальный subset, не новая native parity и не поддержка произвольных типов.

### Ссылки перечислений в source-константах

Поддерживаются `cfg:EnumRef.<Name>` для перечислений, которые source runtime
уже умеет читать, отдельно и в составном типе. Запись хранит UUID самого
перечисления и его значения, а не имя или локализованное представление.
Пустая ссылка записывается явно; default пока не выводится из декларации.

Get восстанавливает ссылку из namespace текущего приложения, поэтому сравнение
с `Enums.<Name>.<Value>` сохраняет прикладную идентичность после открытия.
Ссылка другого приложения отвергается даже при совпадении UUID. Строки и UUID
не преобразуются в ссылки. Неизвестные значения, повреждённые записи и
unsupported перечисления отвергаются целиком, в том числе внутри union.

Compatible source update не разрешает менять UUID, состав или порядок значений
перечисления, используемого константой; старое значение и файл сохраняются при
отказе. Переименование отдельного значения с сохранением его UUID не меняет
сохраняемую идентичность. Добавление enum values тоже пока требует нового
scratch, а не неявной миграции. Это локальное хранение source-ссылок,
не native database serialization и не поддержка CatalogRef/DocumentRef.

Основание enum-констант: [официальное руководство, раздел 5.9](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_8.3.23_Developer_Guide/Chapter_5._Configuration_objects/5.9._Enumerations/) прямо описывает использование перечислений в значениях констант.
