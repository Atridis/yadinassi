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
FMObserve("05", "Format(123.45, ""ND=5;NG=0;NDS=."")"); // nd.default-fraction
FMObserve("06", "Format(123.45, ""ND=5;NFD=2;NG=0;NDS=."")"); // nd.exact
FMObserve("07", "Format(123.45, ""ND=4;NFD=2;NG=0;NDS=."")"); // nd.overflow
FMObserve("08", "Format(9.995, ""ND=3;NFD=2;NG=0;NDS=."")"); // nd.carry
FMObserve("09", "Format(1.25, ""ND=0;NFD=2;NG=0;NDS=."")"); // nd.zero
FMObserve("10", "Format(1.25, ""ND=-1;NFD=2;NG=0;NDS=."")"); // nd.negative
FMObserve("11", "Формат(123.45, ""ЧЦ=5;ЧДЦ=2;ЧГ=0;ЧРД=."")"); // nd.ru-alias
FMObserve("12", "Format(12.3, ""ND=6;NFD=2;NG=0;NDS=."")"); // nlz.absent
FMObserve("13", "Format(12.3, ""ND=6;NFD=2;NLZ=;NG=0;NDS=."")"); // nlz.empty
FMObserve("14", "Format(12.3, ""ND=6;NFD=2;NLZ=0;NG=0;NDS=."")"); // nlz.zero
FMObserve("15", "Format(12.3, ""ND=6;NFD=2;NLZ=1;NG=0;NDS=."")"); // nlz.one
FMObserve("16", "Format(-12.3, ""ND=6;NFD=2;NLZ=;NN=0;NG=0;NDS=."")"); // nlz.negative
FMObserve("17", "Format(12.3, ""ND=7;NFD=2;NLZ=;NG=3,0;NGS=_;NDS=."")"); // nlz.grouped
FMObserve("18", "Формат(12.3, ""ЧЦ=6;ЧДЦ=2;ЧВН=;ЧГ=0;ЧРД=."")"); // nlz.ru-alias
FMObserve("19", "Format(-12.3, ""NN=0;NFD=2;NG=0;NDS=."")"); // nn.zero
FMObserve("20", "Format(-12.3, ""NN=1;NFD=2;NG=0;NDS=."")"); // nn.one
FMObserve("21", "Format(-12.3, ""NN=2;NFD=2;NG=0;NDS=."")"); // nn.two
FMObserve("22", "Format(-12.3, ""NN=3;NFD=2;NG=0;NDS=."")"); // nn.three
FMObserve("23", "Format(-12.3, ""NN=4;NFD=2;NG=0;NDS=."")"); // nn.four
FMObserve("24", "Format(-0.004, ""NN=0;NFD=2;NG=0;NDS=."")"); // nn.rounded-zero
FMObserve("25", "Формат(-12.3, ""ЧО=0;ЧДЦ=2;ЧГ=0;ЧРД=."")"); // nn.ru-alias
FMObserve("26", "Format(1234.5, ""NS=1;NFD=2;NG=0;NDS=."")"); // ns.positive
FMObserve("27", "Format(1234.5, ""NS=-1;NFD=2;NG=0;NDS=."")"); // ns.negative
FMObserve("28", "Format(1234.5, ""NS=0;NFD=2;NG=0;NDS=."")"); // ns.zero
FMObserve("29", "Format(0, ""NS=2;NZ=ZERO;NFD=2;NG=0;NDS=."")"); // ns.original-zero
FMObserve("30", "Format(0.004, ""NS=1;NZ=ZERO;NFD=2;NG=0;NDS=."")"); // ns.rounded-zero
FMObserve("31", "Формат(1234.5, ""ЧС=1;ЧДЦ=2;ЧГ=0;ЧРД=."")"); // ns.ru-alias
FMObserve("32", "Format(123.45, ""NF=""""$N"""";NFD=2;NG=0;NDS=."")"); // nf.english
FMObserve("33", "Формат(123.45, ""ЧФ=""""$Ч"""";ЧДЦ=2;ЧГ=0;ЧРД=."")"); // nf.russian
FMObserve("34", "Format(123.45, ""NF=""""N' kg'"""";NFD=2;NG=0;NDS=."")"); // nf.literal-suffix
FMObserve("35", "Format(-12.3, ""NF=""""$N"""";NN=0;NFD=2;NG=0;NDS=."")"); // nf.negative
FMObserve("36", "Format(0, ""NF=""""$N"""";NFD=2;NG=0;NDS=."")"); // nf.zero-absent
FMObserve("37", "Format(0, ""NF=""""$N"""";NZ=ZERO;NFD=2;NG=0;NDS=."")"); // nf.zero-word
FMObserve("38", "Format(0, ""NF=""""$N"""";NZ=;NFD=2;NG=0;NDS=."")"); // nf.zero-empty
FMObserve("39", "Format(1234.5, ""NF=""""$N"""";NS=1;ND=6;NLZ=;NFD=2;NG=0;NDS=."")"); // nf.combined
FMObserve("40", "Format(False, ""BF=No;BT=Yes"")"); // bool.false
FMObserve("41", "Format(True, ""BF=No;BT=Yes"")"); // bool.true
FMObserve("42", "Формат(Ложь, ""БЛ=No;БИ=Yes"")"); // bool.false-ru
FMObserve("43", "Формат(Истина, ""БЛ=No;БИ=Yes"")"); // bool.true-ru
FMObserve("44", "Format(False, ""BF=;BT=Yes"")"); // bool.false-empty
FMObserve("45", "Format(True, ""BF=No;BT="")"); // bool.true-empty
FMObserve("46", "Format(False, ""BF=No;BF=Off;BT=Yes"")"); // bool.duplicate
FMObserve("47", "Format(True, ""BF=No;BT=Yes;NFD=2;NN=0"")"); // bool.numeric-mask
FMObserve("48", "Format(1, ""BF=No;BT=Yes;NFD=2;NG=0;NDS=."")"); // bool.numeric-value
