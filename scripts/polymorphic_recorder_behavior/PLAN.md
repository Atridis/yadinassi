# Авторский packet: полиморфный Recorder

Черновик, **нативно не выполнен**. Нет workflow, runtime grant или parity claim.
Отдельная будущая одноразовая установка в изолированную синтетическую базу.
Используется pinned native metadata fixture `inventory_reference_behavior`:
Receipt, Issue, Stock, Products, Warehouses. Это reuse разметки и material-redump
validator, не переименование старых Note-tag observations в Recorder evidence.
Старые observer/captures не изменяются. Information-register Recorder вне scope.

## Протокол и владение

`fixture.prepare` возвращает свежую карту; `load_saved` заменяет только отдельно
инжектируемый observer. `route.program` требует 32-hex nonce, pinned source hash,
ровно восемь нумерованных групп между entered/completed. Setup вне measured
query catches: неожиданный setup сбой оставляет неполный packet. Предварительная
попытка GetRef(UUID)/SetNewObjectRef для Receipt и Issue использует одинаковый
синтетический UUID в транзакции. Её отказ отмечается ERR, транзакция откатывается,
после чего обычный setup должен успешно создать обе записи. В группе1 отдельно
выводятся факт равенства UUID и сравнение ссылок, если попытка удалась.

Native query execute refusal записывается ERR, не считается подтверждением
поддержки. Значения только фиксированные R/I/ER/EI/RX/IX/N/X и числа; без
представлений объектов, UUID, текста исключений, private paths и nonce в
normalized report. Rows сортируются по labels, кроме observational ordering.
Limit16 rows,2048 символов на группу,32768 байт wire. Выход за row/output bounds
прерывает packet, не превращается в измеренный query refusal.

## Восемь групп

1. Same UUID у разных document types; Recorder projection и фильтр каждого типа.
2. Equality/inequality, типизированные пустые ссылки и cross-document equality.
3. IN/NOT IN смешанного массива, пустого массива, массива с NULL, подзапроса.
4. CASE с двумя document types, implicit NULL, ISNULL после LEFT JOIN.
5. UNION ALL/UNION, повторённая ветвь, типы пустых ветвей.
6. Unload.ValueType.Types/ContainsType: полный, суженный, пустой и nullable вывод.
7. GROUP BY Recorder и INNER/LEFT JOIN на Receipt.Ref.
8. ORDER BY Recorder ASC/DESC: только наблюдение, не ordering grant.

Типы выводятся bitset Receipt/Issue/NULL плюс количество других типов; важен
контракт колонки даже при нуле строк, а не только тип фактически полученных ячеек.
Generic composite TypeDescription, defaults/Add, casts, codecs/ValueStorage и
transport остаются закрытыми. Runtime singleton guards не меняются.

## Перед будущим native запуском

Нужны отдельное review packet и штатная admission-интеграция: официальный
import/UpdateDBCfg/material redump, source/host/configuration digests, pinned
isolated image, bounded execution, process/container cleanup witnesses и
проверенный provenance. Этот модуль сам ничего не запускает, не объявляет
cleanup/provenance проверенными и не сохраняет golden. Даже complete observation
не означает runtime parity. Offline tests проверяют только authored protocol.

## Состояние acquisition draft

Добавлен отдельный `native_1c_bootstrap/polymorphic_recorder_suite.py` с тем же
secure lifecycle, но своими stage schema, manifest и output names. Route adapter
принимает только полный ordered packet; неожиданные исключения дают ограниченный
failure envelope без raw text. Host profile/probe пока не подключены, поэтому
этот checkpoint не является готовым маршрутом запуска. Добавлены восемь offline
checks адаптера/неуспешного lifecycle; их static assertions не доказывают native
containment. Ранее 12 packet tests прошли normal/-O до этого слоя; суммарные20
на новом слое ещё не выполнялись.
