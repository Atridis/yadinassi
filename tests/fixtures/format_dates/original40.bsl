// Standalone Format measurement. Fixed expressions only; no predicted native answers.
Функция FDEncode(Знач Text)
    Если ТипЗнч(Text) <> Тип("Строка") Или СтрДлина(Text) > 32 Тогда
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
FDObserve("01", "Format('20261030123456', ""DF=yyyy-MM-dd HH:mm:ss"")"); // composite.iso
FDObserve("02", "Формат('20261030123456', ""ДФ=dd.MM.yyyy HH:mm:ss"")"); // composite.ru
FDObserve("03", "Format('20260102030405', ""DF=d.M.yyyy H:m:s"")"); // composite.single
FDObserve("04", "Format('20240229235959', ""DF=yyyy-MM-dd HH:mm:ss"")"); // composite.leap
FDObserve("05", "Format('20261030000000', ""DF=yyyy-MM-dd HH:mm:ss"")"); // composite.midnight
FDObserve("06", "Format('00010101000001', ""DF=yyyy-MM-dd HH:mm:ss"")"); // composite.year-one
FDObserve("07", "Format('99991231235959', ""DF=yyyy-MM-dd HH:mm:ss"")"); // composite.year-last
FDObserve("08", "Format('20261030123456' + 0.5, ""DF=yyyy-MM-dd HH:mm:ss"")"); // composite.fraction
FDObserve("09", "Format('20260102030405', ""DF=d"")"); // token.1
FDObserve("10", "Format('20260102030405', ""DF=dd"")"); // token.2
FDObserve("11", "Format('20260102030405', ""DF=M"")"); // token.3
FDObserve("12", "Format('20260102030405', ""DF=MM"")"); // token.4
FDObserve("13", "Format('20260102030405', ""DF=yy"")"); // token.5
FDObserve("14", "Format('20260102030405', ""DF=yyyy"")"); // token.6
FDObserve("15", "Format('20260102030405', ""DF=H"")"); // token.7
FDObserve("16", "Format('20260102030405', ""DF=HH"")"); // token.8
FDObserve("17", "Format('20260102030405', ""DF=m"")"); // token.9
FDObserve("18", "Format('20260102030405', ""DF=mm"")"); // token.10
FDObserve("19", "Format('20260102030405', ""DF=s"")"); // token.11
FDObserve("20", "Format('20260102030405', ""DF=ss"")"); // token.12
FDObserve("21", "Format('00010101000000', """")"); // empty.default
FDObserve("22", "Format('00010101000000', ""DF=yyyy-MM-dd HH:mm:ss"")"); // empty.mask
FDObserve("23", "Format('00010101000000', ""DE=''"")"); // empty.explicit-empty
FDObserve("24", "Format('00010101000000', ""DE='EMPTY'"")"); // empty.word
FDObserve("25", "Format('00010101000000', ""DF=yyyy-MM-dd;DE='EMPTY'"")"); // empty.mask-word
FDObserve("26", "Format('00010101000001', ""DF=yyyy-MM-dd HH:mm:ss;DE='EMPTY'"")"); // nonempty.word
FDObserve("27", "Format('20261030123456', ""DF='yyyy-MM-dd HH:mm:ss'"")"); // syntax.singlequote
FDObserve("28", "Format('20261030123456', ""DF=""""yyyy-MM-dd HH:mm:ss"""""")"); // syntax.doublequote
FDObserve("29", "Format('20261030123456', ""DF=""""yyyy 'year' MM"""""")"); // syntax.literal-word
FDObserve("30", "Format('20261030123456', ""DF=""""yyyy''MM"""""")"); // syntax.apostrophe
FDObserve("31", "Format('20261030123456', ""DF=""""yyyy';'MM"""""")"); // syntax.semicolon
FDObserve("32", "Формат('00010101000000', ""ДФ='dd.MM.yyyy';ДП='ПУСТО'"")"); // syntax.ru-empty
FDObserve("33", "Format('20261030123456', ""DF=yyyy;DF=MM"")"); // syntax.duplicate
FDObserve("34", "Format('20261030123456', ""df=yyyy;ДФ=MM"")"); // syntax.mixed-alias
FDObserve("35", "Format('20261030123456', ""DF=MMMM"")"); // control.month-name
FDObserve("36", "Format('20261030123456', ""DF=hh tt"")"); // control.twelve-hour
FDObserve("37", "Format('20261030123456', ""UNKNOWN=xyz;DF=yyyy-MM-dd"")"); // control.unknown
FDObserve("38", "Format(123.45, ""DF=yyyy;DE='EMPTY'"")"); // control.number
FDObserve("39", "Format(True, ""DF=yyyy;DE='EMPTY'"")"); // control.boolean
FDObserve("40", "Format(""abc"", ""DF=yyyy;DE='EMPTY'"")"); // control.string
