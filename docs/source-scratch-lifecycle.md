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

### Запрос к таблице Constants

Source scratch предоставляет read-only `SELECT ... FROM Constants AS C` (также
`Константы`) для явно выбранных скалярных констант String/Number/Boolean/Date.
Например, после записи `Constants.OrganizationName.Set("Demo")`:

```bsl
Q = New Query("SELECT C.OrganizationName AS Name FROM Constants AS C");
Selection = Q.Execute().Select();
Selection.Next();
Message(Selection.Name);
```

Проекции, параметры, WHERE, поддержанные выражения/агрегаты, GROUP BY/HAVING,
ORDER BY и выгрузка результата используют существующий закрытый relational
engine. Сначала выполняется binding, затем выбранные поля читаются одним
SQLite snapshot. Внутри явной транзакции видны её записи, но Execute её не
коммитит. Уже полученный результат не изменяется после следующей записи.
Неиспользуемые unsupported или неинициализированные константы не читаются;
если они явно выбраны, возвращается ошибка, а не выдуманное значение.

Это одна строка в ограниченном source-host профиле. Нет произвольного SQL,
чужих SQLite-баз, разделителей
данных или фиктивных таблиц Catalog/Document/Register. UUID, ValueStorage,
составные и enum-поля в запросах пока отклоняются даже при поддержке их Get/Set.
Actual caller проверяется при каждом Execute: owning synchronous server,
живая source application и safe-mode policy. Объект Query не переносит
полномочия его создателя вызывающему.

[Официальное руководство](https://1c-dn.com/download-trial/files/guides/developer_guide.pdf)
описывает таблицу Constants в языке запросов. Наш ограниченный source-host
контракт без разделения данных не является новой проверкой native parity.

Ограничения выше относятся к новому источнику Constants. Ранее доступные
запросы к переданным ValueTable и их пакеты без scratch сохраняют прежний
закрытый движок и его ограничения; новый источник не выдаёт DB-полномочий.

### Композиция запросов к Constants

Один Execute поддерживает UNION/UNION ALL, self-JOIN, derived SELECT и
некоррелированный IN/NOT IN SELECT в пределах существующей query grammar.
Все физические источники должны быть Constants/Константы. Для всего дерева
запроса поля читаются одним get_many snapshot, а не отдельно на каждый SELECT.
Aliases, неоднозначные имена, типы и границы проверяет общий relational binder.
Результат остаётся отсоединённым снимком; Execute не коммитит внешнюю транзакцию.

Сначала выполняется binding всего дерева с пустыми таблицами и точными
скалярными колонками. Только после его успеха читаются реально упомянутые
константы. Предикаты не превращаются в SQL: SQLite получает только внутренние
фиксированные запросы по UUID констант. Ограничения tokenizer, AST, сравнений,
строк, ячеек и результатов сохраняются. Смешивание с Catalog/Document/Register
отклоняется, а не имитируется пустыми таблицами. Пакеты с внешними ValueTable
и временными таблицами описаны ниже. Это локальный составной
query subset, не новое измерение native parity.

### Пакеты и временные таблицы source-запросов

`ExecuteBatch` возвращает результаты всех инструкций, а `Execute` для пакета
возвращает последний. Поддержаны INTO/DESTROY и обычный TempTablesManager:

```bsl
Q = New Query("SELECT C.OrganizationName AS Name INTO Saved FROM Constants AS C;
| SELECT Name FROM Saved");
Results = Q.ExecuteBatch();
```

Каждый вызов получает один snapshot всех упомянутых констант. Типизированная
ValueTable передаётся существующему пакетному движку под внутренним именем,
исключённым из пользовательских параметров и ссылок. Поэтому отсутствующий
пользовательский параметр не может случайно прочитать этот snapshot.
Пакеты могут объединять Constants, свои временные таблицы и явно переданные
bounded ValueTable; доступ к другим persistent таблицам не предоставляется.
В пакетах, обращающихся к источнику Constants, имена Constants/Константы
нельзя использовать как INTO-цель или DESTROY. Старый no-Constants путь
не меняет свои правила именования временных таблиц.

Существующий пакетный движок публикует изменения TempTablesManager только
после полного успеха. Неуспешный пакет не оставляет новые временные таблицы
и не уничтожает прежние. Execute не коммитит внешнюю source-транзакцию.
Snapshot читается до выполнения пакета, но последовательные binding и
результаты временных таблиц проверяются уже внутри общего атомарного движка.
Лимиты таблиц, строк, ячеек и текста не увеличены. Никакого пользовательского
SQL, native temporary-table parity или автоматических defaults не добавлено.

### DefinedType в source-константах

Декларация константы может содержать единственный
`<v8:TypeSet>cfg:DefinedType.Name</v8:TypeSet>`. Resolver читает объявленный
DefinedType из того же source без вложенных DefinedType и
передаёт итоговую декларацию прежнему закрытому codec. Поддерживаются только
уже доступные scalar/composite/UUID/ValueStorage/enum типы и их qualifiers.
Неизвестная ссылка, вложенный DefinedType (включая циклы), смешивание TypeSet с
другими типами или переопределениями qualifiers остаются именованной ошибкой.
Неподдержанный DefinedType, который никто не использует, не активируется.

UUID и имя объекта DefinedType входят в schema binding. Source update
не разрешает незаметно заменить alias другим объектом, изменить его тип или
переписать alias на прямую декларацию. Значения остаются прежними при отказе.
Старый формат schema для прямых деклараций не меняется. Начальные значения
для alias не выводятся из defaults прямого типа: даже String64 сначала
требует явного Set. Это не миграция ранее unsupported деклараций и не
новая native parity.

Контракт именованных типов и qualifiers основан на
[официальных рекомендациях DefinedType](https://1c-dn.com/library/using_defined_types/).
Developer Guide §5.5.11 прямо запрещает включать DefinedType в другой DefinedType.
Resolver не загружает Python/BSL-код и не разрешает произвольные host-типы.

### Дополнительные qualifiers source-констант

Поддержаны декларации String с длиной 0, Fixed String положительной длины и
Date с частями Date или Time. Они проходят те же direct/composite/DefinedType,
менеджеры, наборы, транзакции и scalar query пути. Неизвестные/дублированные
qualifiers и лишние XML-атрибуты по-прежнему отклоняются.

Это **строгий storage subset**, не воспроизведение преобразований платформы:

- Length=0 означает отсутствие metadata-ограничения длины, но сохраняются
  локальные Unicode/resource limits и 65536 байт encoded storage record.
- Fixed принимает только уже точную длину в UTF-16 units. Нет padding,
  обрезания строки или ремонта некорректных surrogate-последовательностей.
- Date принимает уже полуночное значение; Time принимает время в базовом дне
  0001-01-01. Дробные секунды, лишняя дата/время не отбрасываются, а отвергаются.

Новые qualifiers не получают выдуманных начальных значений. Reopen снова
проверяет exact qualifiers; update не расширяет/меняет их автоматически.
Файл со старой unsupported-декларацией не мигрируется этим расширением.
[Официальное описание типов и хранения дат](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/)
различает script precision и хранение с точностью до секунды. Наш отказ от
неявных преобразований явно строже платформы; новая native parity не заявлена.

### Source Catalog/Document references

Source managers expose neutral `EmptyRef()`, explicit `GetRef(UUID)` and
`Metadata()` alongside existing exported ManagerModule routines. The references
reuse the existing Catalog/Document reference classes and one source-owned type
snapshot. Obtaining an identity does not read or create a record. Unsupported
CreateItem/CreateDocument, object reads and nonempty presentations remain errors;
manager modules are not executed merely to construct a neutral reference.

CatalogRef/DocumentRef constants (also unions and DefinedType aliases) persist
family, metadata UUID and record UUID in the same bounded, transactional scratch
store. Reopen binds values to the new application's exact type snapshot; foreign
application values are rejected. Unknown target types and incompatible source
updates are refused. No empty-reference defaults, implicit GetRef UUID generation,
reference-existence checks or native runtime parity are claimed by this block.

### Явный v4: реальные записи справочников

`--source-catalog-records` вместе с `--source-scratch-db NEW --run-startup`
создаёт отдельную v4 scratch. При открытии `--open-source-scratch-db EXISTING`
тот же флаг обязателен. Обычный v3 путь не меняется и не мигрирует файл.

V4 поддерживает закрытый профиль справочника: явный строковый Code, Description,
DeletionMark и до 64 скалярных реквизитов. CreateItem/Write, Ref.GetObject/Read,
IsNew и ограниченный Select работают с настоящими сохранёнными записями.
Code задаётся явно и уникален при точном сравнении строк в этом локальном профиле;
платформенная collation и автоматическая нумерация не заявляются. Общий предел
10000 записей и 16 MiB encoded payload, не более 64 KiB на запись. Пользовательские
реквизиты перед первой записью нужно присвоить явно. Selection читает ограниченный
снимок; изменение его полей запрещено. Иерархия, владельцы, табличные части,
Неподдержанные события ObjectModule, подписки, разделение данных и политики блокируют
операции соответствующего справочника, а не загрузку всего source.

Запись использует ту же SQLite connection и транзакцию, что константы.
Revision проверяется оптимистически: устаревший объект не перезаписывает более
новую запись. Ошибка записи откатывает текущую транзакцию. После внешнего rollback
ранее записанный buffer не означает существующую запись: повторный Write получает
stale revision, требуется заново прочитать объект или создать новый. Полная
семантика состояний объекта после rollback/native parity не заявляется.

`SourceCatalogStore.upgrade_copy(original, destination)` является явной host API
миграции v3 в новую проверенную v4-копию без запуска BSL. Исходный файл не меняется,
существующий destination не перезаписывается. При сбое частичная копия сохраняется
для диагностики и не считается готовой. Никакой migration при обычном reopen нет.
Обновление XML сохраняет записи только при неизменной схеме справочников; изменение
полей/идентичностей/политик пока отклоняется, без придуманных значений и потери данных.

### Запросы к реальным v4 справочникам

Query читает Catalog.Name/Справочник.Имя из сохранённых v4 записей: scalar поля,
типизированную Ref/Ссылка, фильтры, сортировки, агрегаты, JOIN, UNION и вложенные
SELECT через существующий закрытый AST executor. Пользовательский текст никогда
не передаётся SQLite как SQL. Неподдержанные таблицы не подменяются пустыми.

Все участвующие справочники и явно прочитанные константы собираются в один
ограниченный согласованный snapshot. Собственная транзакция запроса освобождается
после чтения; уже открытая пользователем транзакция не коммитится и не откатывается
при успехе. Result остаётся неизменным после последующих записей объектов.

Ref cursor и Unload сохраняют настоящий source-owned reference type, metadata UUID
и record UUID. Отдельный exact SourceBinding не выдаёт нейтральные ссылки за legacy
backend records, не разрешает поддельные callbacks или foreign application values.
Detached descriptor проверяет cached ownership без скрытого чтения базы. После
закрытия owning application операции со связанным report отклоняются.

Поддержка пакетов и временных таблиц описана ниже. Ref не подменяется строками
UUID; полная native Query/колляционная совместимость не заявляется.

### Связи между v4 справочниками

CatalogRef-реквизиты сохраняют exact target metadata UUID и record UUID, используя
тот же source-owned type snapshot, что константы и менеджеры. Поддерживаются ссылки
на другой справочник и на себя: циклический граф хранится как идентичности, а не
рекурсивно сериализуемые объекты. Значение реквизита перед первой записью задаётся
явно, в том числе EmptyRef; не подставляется выдуманное начальное значение.

Read/GetObject/Select/reopen возвращают настоящую типизированную ссылку текущего
приложения. Чужой source/application, неправильный target или scalar вместо ссылки
отклоняются. Ссылка не является доказательством существования записи: сохранённый
UUID допускает отсутствующую запись, а GetObject честно выдаёт not found. Новые
записи по факту хранения ссылки не создаются. DocumentRef/composite/прочие типы
реквизитов этим блоком не активируются.

Query может связывать Catalog.Items.Category с Catalog.Groups.Ref и выгружать
типизированное поле без превращения его в строку. Target должен иметь активный v4
профиль для этого query binding; unsupported target не имитируется пустой таблицей.
Изменение target identity/type по-прежнему требует отдельной схемной миграции и
отклоняется при обычном source update. Новая native parity не заявляется.


### Пакеты запросов к v4 данным и временные таблицы

ExecuteBatch/ВыполнитьПакет, INTO/ПОМЕСТИТЬ, DESTROY/УНИЧТОЖИТЬ и
TempTablesManager используют общий ограниченный исполнитель пакетов. Реальные
справочники и константы пакета читаются один раз в согласованном снимке; дальнейшие
операторы пакета работают с этим снимком и локальными временными таблицами.
Пользовательский текст не превращается в SQL, постоянные данные запрос не меняет.

Ref и ссылочные реквизиты сохраняют тип, владельца приложения и идентичность при
Unload и повторном Query. Временные таблицы можно использовать между запросами
того же открытого приложения; исходные строки не меняются вслед за новой записью
справочника. Чужие приложения, закрытые владельцы и legacy backend bindings не
смешиваются с source scope. Неподдержанные persistent families не становятся
пустыми таблицами.

Изменения набора временных таблиц публикуются только после успеха всего пакета.
Ошибка позднего оператора не оставляет таблицы от раннего и не уничтожает ранее
сохранённые. Действуют ограничения количества таблиц, строк, ячеек и текста.
Внешняя транзакция записи не коммитится пакетом; собственная транзакция снимка
закрывается после чтения. Это локальный проверяемый контракт, не результат нового
прогона пакетов на реальной 1С.

### ObjectModule справочников: ограниченный серверный жизненный цикл

Source CatalogObject исполняет собственный ObjectModule: поля объекта и
ThisObject/ЭтотОбъект, переменные экземпляра и экспортные процедуры используют
существующий серверный BSL-интерпретатор. Создание или чтение объекта не означает
выполнение произвольного Python-кода из базы: загружается только проверенный BSL
из точного source snapshot приложения.

Write вызывает BeforeWrite/ПередЗаписью с Cancel/Отказ, сохраняет запись и вызывает
OnWrite/ПриЗаписи в той же транзакции. Отмена или исключение не оставляют запись
или побочные записи констант. При успехе собственная транзакция фиксируется;
внешняя остаётся у вызывающего кода. OnWrite работает после записи: изменение
поля буфера в нём не вызывает скрытую повторную запись.

Контракт опирается на официальные описания [BeforeWrite](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Creating_and_modifying_metadata_objects/Object_event_handlers/Event_handlers_____BeforeWrite/)
и [OnWrite](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Creating_and_modifying_metadata_objects/Object_event_handlers/Event_handlers_____OnWrite/),
но не является новым результатом сравнения с реальной 1С. Асинхронные обработчики,
рекурсивная запись, управление транзакцией из обработчика, подписки, проверка
заполнения и остальные неподдержанные события отвергаются явно. Профиль хранения
v4 не меняется; пользовательские файлы автоматически не мигрируют.

Инициализатор выполняется для нового буфера; при GetObject затем накладываются
реально прочитанные поля записи, чтобы инициализатор не подменял сохранённые
значения. Прямой низкоуровневый write_record не разрешает запись объектов с
ObjectModule в обход обработчиков. Наличие модуля входит в описатель схемы:
добавление/удаление модуля требует отдельного явного перехода, тогда как изменение
его кода при том же пути сохраняет записи при обычном проверенном source update.
Для справочников без модуля каноническая запись схемы остаётся прежней.

Пойманная внутри обработчика ошибка хранилища не позволяет начать новую
транзакцию и отдельно сохранить побочные записи после отката исходной. Защита
действует и на переходы между обработчиками констант и объектами справочников.

### Поиск и чтение через source CatalogRef

FindByCode/НайтиПоКоду, FindByDescription/НайтиПоНаименованию и
FindByAttribute/НайтиПоРеквизиту читают реальные сохранённые записи v4 и возвращают
типизированную ссылку текущего приложения. При отсутствии результата возвращается
EmptyRef, а не созданная запись. Образцы этих цепочек приведены в
[официальном справочнике объектов языка](https://kb.1ci.com/1C_Enterprise_Platform/Tutorials/Practical_developer_guide_8.3/Quick_developer_reference/Catalogs/1C_Enterprise_language_objects_used_for_operations_with_catalogs/).

Локальный профиль намеренно ограничен: строковый код, точное сравнение значений,
FindByDescription только с явно заданным True. Неоднозначные результаты поиска
отклоняются вместо выбора случайной записи. Региональная collation, префиксный
поиск, иерархия и владельцы этим блоком не активируются. НайтиПоРеквизиту проверяет
тип и квалификаторы поля, включая точный target CatalogRef.

Ref.Code/Код, Description/Наименование, DeletionMark/ПометкаУдаления и реквизиты
читаются через настоящий storage lookup с проверкой приложения, серверного
контекста и safe mode. Чтение не создаёт CatalogObject и не запускает его модуль.
Поля ссылки только для чтения, в том числе при передаче по ссылке в процедуру.
Пустая или отсутствующая запись не получает выдуманных значений полей. Это
ограниченный source-host контракт, не новая проверка полной native parity.

Каждый lookup/чтение поля получает согласованный снимок своего вызова и видит
записи текущей явной транзакции. Несколько отдельных обращений к Ref не считаются
одним общим снимком: для этого используется явная транзакция или Query.

### v5: реальные непроведённые source-документы

`--source-document-records` выбирает отдельный профиль v5, включающий константы,
справочники и реальные записи документов. Создание, открытие и обновление требуют
явного флага: v3/v4 не открываются как v5 и автоматически не мигрируют. Для явного
перехода предусмотрен host `SourceDocumentStore.upgrade_copy(old_v4, new_v5)`:
исходник только читается, назначение создаётся исключительно как новый файл.
Никакие пользовательские базы этим изменением не обновляются.

Documents.Name.CreateDocument/СоздатьДокумент, Select/Выбрать, Ref.GetObject,
Read/Прочитать, Write/Записать и IsNew/ЭтоНовый работают с настоящими документными
таблицами. Number/Номер и Date/Дата задаются явно; номер строковый и уникальный в
пределах вида документа. DeletionMark/ПометкаУдаления сохраняется; Posted/Проведен
в этом профиле всегда False и только для чтения. Нет фиктивного проведения:
аргументы режима Write, движения, табличные части и ObjectModule пока отклоняются.

Поддерживаются ограниченные скалярные реквизиты и ссылки на справочники с точной
типовой идентичностью. Неподдержанные политики блокируют только соответствующий
документ. Базовый CRUD сам по себе не активирует Query; отдельный адаптер
запросов описан ниже и не возвращает пустую таблицу вместо недоступных данных. Справочники и прежние Catalog Query продолжают работать
в v5 через свои настоящие таблицы и общую connection/транзакцию.

Optimistic revision, byte/resource limits, проверка канонических payload и
Posted=False применяются на уровне хранилища. Откат общей транзакции нельзя
обойти новой записью документа из всё ещё выполняющегося обработчика. Source
update допускается только при сохранении схемы документов и существующих
справочников; нет скрытой потери реквизитов или подстановки начальных значений.
Это локальный поддерживаемый профиль, не полная документная/native parity.

Если copy-upgrade не завершился, исходный файл сохраняется; новый частичный файл
не считается готовой базой и не заменяет исходник. Повторный запуск не перезапишет
уже существующее назначение. Сравнение схемы source повторяется под транзакционной
блокировкой непосредственно перед обновлением, а не только при предварительном
чтении.

### Запросы к непроведённым документам v5

В явном профиле `--source-document-records` запросы читают реальные записи
`Document.<Имя>` / `Документ.<Имя>`: ссылку, номер, дату, пометку удаления,
`Posted` / `Проведен` (строго `False`) и поддержанные реквизиты. Документы,
справочники и константы в одном запросе или пакете материализуются в общем
снимке одной scratch-транзакции. Внешняя транзакция остаётся открытой;
результат запроса не становится живым представлением последующих изменений.

Поддержаны существующие JOIN, UNION, производные источники, выгрузка в таблицу
значений и временные таблицы пакетов. Типизированная ссылка документа сохраняет
идентичность конфигурации и владельца при выгрузке и повторном запросе, включая
пустой результат. Одноимённые справочник и документ являются разными источниками.
Ссылки не подменяются строками и не дают доступа к записям другой source-сессии.

Это локальный сквозной контракт, не результат проверки паритета с реальной 1С.
Профили v3/v4 не получают таблиц документов автоматически. Табличные части,
движения, виртуальные таблицы регистров и проведение здесь не поддержаны;
запрос их явно отклоняет. Отдельный запрос только к константам сохраняет прежние
ограничения своего адаптера. Пользовательские базы этим изменением не мигрируются.

### Табличные части непроведённых документов: отдельный v6

`--source-document-sections` выбирает отдельный профиль scratch-базы v6.
Это явный выбор при создании или открытии: v5 не переписывается и не становится
v6 при обычном запуске. База пользователя не является входом тестов реализации.

Поддерживаемый документ хранит ограниченные типизированные строки табличных
частей вместе со своими реквизитами. Запись владельца и всех секций атомарна,
с одной optimistic revision. Внешняя транзакция не коммитится методом `Write`;
ошибка записи не оставляет частично обновлённого документа. `Read` заменяет буфер
владельца и секций только после получения согласованного снимка.

Коллекция секции предоставляет Add/Get/Count/Clear/Delete, индексирование и
перебор; строка имеет типизированные поля и readonly LineNumber. Требуется явное
заполнение полей перед сохранением, неизвестные значения не подменяются нулями.
Удалённые строки и строки из заменённого буфера больше нельзя использовать как
действующие строки документа. Передача строки другой секции не даёт права её
изменять. Поддержка секций не означает проведение, движения или ObjectModule.
Сам блок хранения не добавляет запросы к секциям; отдельный query-адаптер
описан ниже. Запросы к реквизитам документа остаются доступны. Паритет с реальной 1С этим локальным блоком не заявляется.

Перенос v5 доступен только в новый файл через copy-only API: исходный файл
открывается read-only, существующее назначение не перезаписывается, копия
полностью проверяется. Частично созданный файл при ошибке не считается готовой
базой. Неявной миграции или изменения пользовательских файлов нет.

Основа модели владения: [официальный учебный материал о табличных частях](https://kb.1ci.com/1C_Enterprise_Platform/Tutorials/1C_Enterprise_Platform_Training_Course_-_Junior_Application_Developer_Level/Module_2._Main_Metadata_Classes/Episode_5._Hierarchical_data/)
описывает их как часть объекта, записываемую вместе с документом. Более строгие
ограничения типов, лимиты и инвалидирование буфера выше являются контрактом
текущего локального профиля, а не заявлением о полной семантике платформы.

### Запросы к строкам табличных частей v6

`Document.<Имя>.<ТабличнаяЧасть>` / `Документ.<Имя>.<ТабличнаяЧасть>` читает
реальные сохранённые строки профиля v6. `Ref` / `Ссылка` содержит типизированную
ссылку владельца-документа, `LineNumber` / `НомерСтроки` задаёт позицию строки,
остальные колонки берутся из объявленных типизированных полей секции.

Чтение строк, реквизитов документов, справочников и констант в одном запросе или
пакете использует один транзакционный снимок. JOIN с владельцем сравнивает
настоящие DocumentRef; выгрузка и временные таблицы сохраняют тип и владельца
ссылок, включая пустые результаты. Старый выгруженный результат не меняется
после последующей записи документа. Это не отдельная запись регистра и не
результат проведения. v5 не получает доступ к секциям автоматически.

Ограничения числа источников, строк и байтов действуют и на секции; неизвестные
секции и неподдержанные виртуальные источники отклоняются. Сведения о движениях,
проведении и native parity из этого блока не следуют. Запросы не обновляют
пользовательские базы и не меняют формат v6.

[Официальный FAQ о запросах к табличным частям](https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Queries/How_to_select_fields_from_tabular_sections_in_a_query/?language=en)
подтверждает выбор полей секции вместе со ссылкой документа-владельца и JOIN
с другими таблицами; ограничения локального адаптера перечислены выше.

### Ссылки на документы в прикладных данных

Поддержанный закрытый тип реквизита теперь может быть `DocumentRef.<Имя>`:
в справочнике, документе и строке табличной части документа. Сохранение использует
UUID вместе с объявленным типом и идентичностью метаданных, а после открытия
ссылка привязана к canonical type/snapshot новой source-сессии. Значение другого
типа, владельца или ссылка с внедрёнными callback не принимаются.

Пустые и непустые ссылки не являются доказательством существования записи.
Присваивание не создаёт документ; чтение полей/GetObject и JOIN используют
настоящие данные. Запросы с документными ссылками требуют поддержанного
документного хранилища v5/v6. v4 может хранить нейтральную ссылку, но не получает
скрытый backend документов. Проведение и ссылочная целостность удаления этим
блоком не реализованы.

DDL старых профилей не меняется. Если старая база создана с конфигурацией,
содержавшей ранее неподдержанный объект с DocumentRef, новый ожидаемый список
схем может отличаться: открытие явно откажет, не дописывая таблиц и не теряя
сохранённые данные. Для такого случая автоматическая миграция не предусмотрена;
исходный файл нужно сохранить отдельно. Изменение типа/UUID существующего поля
также не является совместимым source-update и отклоняется.
