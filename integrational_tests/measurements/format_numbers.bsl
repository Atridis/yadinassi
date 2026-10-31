// Standalone Format measurement. Fixed expressions only; no predicted native answers.
Функция FMEncode(Знач Text)
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
Процедура FMObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("FM-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    Попытка
        Record = FMEncode(Value);
    Исключение
        Сообщить("FM-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("FM-" + Label + ": [ok|" + Record + "]");
КонецПроцедуры
// Calibration covers empty text, NBSP, semicolon, quote and supplementary UTF-16.
Сообщить("FM-C1: [" + FMEncode("") + "]");
Сообщить("FM-C2: [" + FMEncode("A ;""😀") + "]");
// Fixed measurement inputs start here.
FMObserve("01", "Format(0, """")"); // zero.empty
FMObserve("02", "Format(1, """")"); // one.empty
FMObserve("03", "Format(-1, """")"); // negative.empty
FMObserve("04", "Format(1234567.89, """")"); // large.empty
FMObserve("05", "Format(0, ""NFD=2"")"); // zero.fd2
FMObserve("06", "Format(1, ""NFD=2"")"); // one.fd2
FMObserve("07", "Format(-1, ""NFD=2"")"); // negative.fd2
FMObserve("08", "Format(1.235, ""NFD=2"")"); // positive.tie
FMObserve("09", "Format(-1.235, ""NFD=2"")"); // negative.tie
FMObserve("10", "Format(9.995, ""NFD=2"")"); // carry
FMObserve("11", "Format(0.004, ""NFD=2"")"); // positive.tiny
FMObserve("12", "Format(-0.004, ""NFD=2"")"); // negative.tiny
FMObserve("13", "Format(1.5, ""NFD=0"")"); // integer.round
FMObserve("14", "Format(-1.5, ""NFD=0"")"); // integer.negative
FMObserve("15", "Format(1.2, ""NFD=4"")"); // precision.four
FMObserve("16", "Format(1234567.89, ""NFD=2;NG=0;NDS=."")"); // group.none
FMObserve("17", "Format(1234567.89, ""NFD=2;NG=3;NDS=."")"); // group.three
FMObserve("18", "Format(1234567.89, ""NFD=2;NG=3;NGS=' ';NDS=,"")"); // group.space
FMObserve("19", "Format(1234567.89, ""NFD=2;NG=3;NGS='';NDS=."")"); // group.empty
FMObserve("20", "Format(1234567.89, ""NFD=2;NG=3;NGS='_';NDS=,"")"); // group.underscore
FMObserve("21", "Format(0, ""NFD=2;NG=0;NDS=."")"); // zero.absent
FMObserve("22", "Format(0, ""NFD=2;NZ='';NG=0;NDS=."")"); // zero.empty-nz
FMObserve("23", "Format(0, ""NFD=2;NZ='ZERO';NG=0;NDS=."")"); // zero.word
FMObserve("24", "Format(0.004, ""NFD=2;NZ='ZERO';NG=0;NDS=."")"); // tiny.word
FMObserve("25", "Format(-0.004, ""NFD=2;NZ='ZERO';NG=0;NDS=."")"); // negative-tiny.word
FMObserve("26", "Формат(1234.5, ""ЧДЦ=2;ЧГ=3;ЧРГ='_';ЧРД=.;ЧН='ZERO'"")"); // alias.ru
FMObserve("27", "Формат(1234.5, ""NFD=2;NG=3;NGS='_';NDS=.;NZ='ZERO'"")"); // alias.cross
FMObserve("28", "Format(1234.5, ""ЧДЦ=2;ЧГ=3;ЧРГ='_';ЧРД=.;ЧН='ZERO'"")"); // alias.en-ru
FMObserve("29", "Format(1234.5, ""NDS=.;NZ='ZERO';NGS='_';NG=3;NFD=2"")"); // order
FMObserve("30", "Format(12.5, ""NFD=2;NG=0;NDS=';'"")"); // quoted.separator
FMObserve("31", "Format(1.2345, ""NFD=1;NFD=3;NG=0;NDS=."")"); // duplicate.forward
FMObserve("32", "Format(1.2345, ""NFD=3;NFD=1;NG=0;NDS=."")"); // duplicate.reverse
FMObserve("33", "Format(1234.5, ""L=ru;NFD=2"")"); // locale.en
FMObserve("34", "Формат(1234.5, ""Л=ru;ЧДЦ=2"")"); // locale.ru
FMObserve("35", "Format(""abc"", """")"); // string.empty
FMObserve("36", "Format(True, """")"); // true.empty
FMObserve("37", "Format(False, """")"); // false.empty
FMObserve("38", "Format('20261030123456', """")"); // date.empty
FMObserve("39", "Format(Undefined, """")"); // undefined.empty
FMObserve("40", "Format(Null, """")"); // null.empty
FMObserve("41", "Format(""abc"", ""NFD=2;NG=0;NDS=."")"); // string.number-mask
FMObserve("42", "Format(True, ""NFD=2;NG=0;NDS=."")"); // true.number-mask
FMObserve("43", "Format('20261030123456', ""NFD=2;NG=0;NDS=."")"); // date.number-mask
FMObserve("44", "Format(Undefined, ""NFD=2;NG=0;NDS=."")"); // undefined.number-mask
FMObserve("45", "Format(1)"); // arity.missing
FMObserve("46", "Format(1, """", 3)"); // arity.extra
FMObserve("47", "Format(1, 2)"); // format.number
FMObserve("48", "Format(1, ""UNKNOWN=1;NFD=2"")"); // unknown
