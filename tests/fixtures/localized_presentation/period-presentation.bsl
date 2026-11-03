// Standalone Format measurement. Fixed expressions only; no predicted native answers.
Функция FDEncode(Знач Text)
    Если ТипЗнч(Text) <> Тип("Строка") Или СтрДлина(Text) > 64 Тогда
        ВызватьИсключение "format-observer-text-bound";
    КонецЕсли;
    Record = "S" + Строка(СтрДлина(Text)) + ":";
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Если Code < 0 Или Code > 65535 Тогда ВызватьИсключение "format-observer-unit-bound"; КонецЕсли;
        Digits = "";
        Для D = 1 По 4 Цикл
            Quotient = Цел(Code / 16);
            Digits = Сред("0123456789abcdef", Code - Quotient * 16 + 1, 1) + Digits;
            Code = Quotient;
        КонецЦикла;
        Record = Record + Digits;
    КонецЦикла;
    Возврат Record;
КонецФункции
Процедура FDObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("FD-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    Попытка
        Record = FDEncode(Value);
    Исключение
        Сообщить("FD-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("FD-" + Label + ": [ok|" + Record + "]");
КонецПроцедуры
// Calibration covers empty text, NBSP, semicolon, quote and supplementary UTF-16.
Сообщить("FD-C1: [" + FDEncode("") + "]");
Сообщить("FD-C2: [" + FDEncode("A ;""😀") + "]");
// Fixed measurement inputs start here.
FDObserve("01", "Format('20261030123456', ""DF=yyyy-MM-dd HH:mm:ss"")"); // control.date
FDObserve("02", "Format(1, """")"); // control.integer
FDObserve("03", "Format(-1, """")"); // control.negative
FDObserve("04", "Format(True, """")"); // control.boolean
FDObserve("05", "ПредставлениеПериода('20260101000000', '20260101235959')"); // ru.day
FDObserve("06", "PeriodPresentation('20260101000000', '20260101235959')"); // en.alias-day
FDObserve("07", "ПредставлениеПериода('20260101000000', '20260131235959')"); // ru.month
FDObserve("08", "ПредставлениеПериода('20240201000000', '20240229235959')"); // ru.leap-month
FDObserve("09", "ПредставлениеПериода('20260101000000', '20260331235959')"); // ru.first-quarter
FDObserve("10", "ПредставлениеПериода('20260401000000', '20260630235959')"); // ru.second-quarter
FDObserve("11", "ПредставлениеПериода('20260101000000', '20261231235959')"); // ru.full-year
FDObserve("12", "ПредставлениеПериода('20260101000000', '20260228235959')"); // ru.months
FDObserve("13", "ПредставлениеПериода('20260101000000', '20260630235959')"); // ru.half-default
FDObserve("14", "ПредставлениеПериода('20260101000000', '20260630235959', ""ФП=Истина"")"); // ru.half-financial
FDObserve("15", "ПредставлениеПериода('20260101000000', '20260930235959', ""ФП=Истина"")"); // ru.nine-financial
FDObserve("16", "ПредставлениеПериода('20240101000000', '20241231235959')"); // ru.year-leap
FDObserve("17", "ПредставлениеПериода('20260101120000', '20260101140000')"); // ru.same-day-times
FDObserve("18", "ПредставлениеПериода('20260102000000', '20260115235959')"); // ru.partial-month
FDObserve("19", "ПредставлениеПериода('20251201000000', '20260131235959')"); // ru.cross-year
FDObserve("20", "ПредставлениеПериода('20260201000000', '20260101235959')"); // ru.reversed
FDObserve("21", "ПредставлениеПериода('00010101000000', '00010101000000')"); // ru.empty-both
FDObserve("22", "ПредставлениеПериода('00010101000000', '20260101235959')"); // ru.empty-start
FDObserve("23", "ПредставлениеПериода('20260101000000', '20260101235959', ""L=ru"")"); // ru.explicit-locale
FDObserve("24", "PeriodPresentation('20260101000000', '20260101235959', ""L=en_US"")"); // en.day
FDObserve("25", "PeriodPresentation('20260101000000', '20260131235959', ""L=en_US"")"); // en.month
FDObserve("26", "PeriodPresentation('20260101000000', '20260331235959', ""L=en_US"")"); // en.quarter
FDObserve("27", "PeriodPresentation('20260101000000', '20260630235959', ""L=en_US;FP=True"")"); // en.financial
FDObserve("28", "PeriodPresentation('20260101000000', '20261231235959', ""L=en_US"")"); // en.year
