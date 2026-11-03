// Temporary NumberInWords measurement. Fixed expressions only; no predicted native answers.
Функция FMEncode(Знач Text)
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
FMObserve("01", "NumberInWords(0, ""L=ru_RU"")"); // ru.zero
FMObserve("02", "ЧислоПрописью(1, ""Л=ru_RU"", ""рубль, рубля, рублей, м"")"); // ru.one
FMObserve("03", "NumberInWords(1, ""L=en_US"", ""dollar, dollars, cent, cents, 2"")"); // en.one
FMObserve("04", "NumberInWords(2, ""L=en_US"", ""dollar, dollars, cent, cents, 2"")"); // en.two
FMObserve("05", "ЧислоПрописью(2, ""Л=ru_RU"", ""рубль, рубля, рублей, м"")"); // ru.two
FMObserve("06", "ЧислоПрописью(5, ""Л=ru_RU"", ""рубль, рубля, рублей, м"")"); // ru.five
FMObserve("07", "ЧислоПрописью(11, ""Л=ru_RU"", ""рубль, рубля, рублей, м"")"); // ru.eleven
FMObserve("08", "ЧислоПрописью(21, ""Л=ru_RU"", ""рубль, рубля, рублей, м"")"); // ru.twenty-one
FMObserve("09", "ЧислоПрописью(22, ""Л=ru_RU"", ""рубль, рубля, рублей, м"")"); // ru.twenty-two
FMObserve("10", "ЧислоПрописью(25, ""Л=ru_RU"", ""рубль, рубля, рублей, м"")"); // ru.twenty-five
FMObserve("11", "ЧислоПрописью(1000, ""Л=ru_RU"")"); // ru.thousand-one
FMObserve("12", "ЧислоПрописью(2000, ""Л=ru_RU"")"); // ru.thousand-two
FMObserve("13", "ЧислоПрописью(5000, ""Л=ru_RU"")"); // ru.thousand-five
FMObserve("14", "ЧислоПрописью(1000000, ""Л=ru_RU"")"); // ru.million
FMObserve("15", "ЧислоПрописью(-2, ""Л=ru_RU"")"); // ru.negative
FMObserve("16", "ЧислоПрописью(1.25, ""Л=ru_RU"")"); // ru.fraction-default
FMObserve("17", "ЧислоПрописью(2.25, ""Л=ru_RU;ДП=Истина"", ""рубль, рубля, рублей, м, копейка, копейки, копеек, ж, 2"")"); // ru.fraction-words-subject
FMObserve("18", "ЧислоПрописью(5.01, ""Л=ru_RU"", ""рубль, рубля, рублей, м, копейка, копейки, копеек, ж, 2"")"); // ru.fraction-subject
FMObserve("19", "ЧислоПрописью(2, ""Л=ru_RU"", ""штука, штуки, штук, ж"")"); // ru.feminine
FMObserve("20", "NumberInWords(0, ""L=en_US"")"); // en.zero
FMObserve("21", "NumberInWords(5, ""L=en_US"", ""dollar, dollars, cent, cents, 2"")"); // en.five
FMObserve("22", "NumberInWords(1000, ""L=en_US"")"); // en.thousand
FMObserve("23", "NumberInWords(1000000, ""L=en_US"")"); // en.million
FMObserve("24", "NumberInWords(-2, ""L=en_US"")"); // en.negative
FMObserve("25", "NumberInWords(1457.25, ""L=en_US"", ""dollar, dollars, cent, cents, 2"")"); // en.documented-subject
FMObserve("26", "NumberInWords()"); // arity.missing
FMObserve("27", "NumberInWords(""abc"", ""L=en_US"")"); // type.string
FMObserve("28", "NumberInWords(1, ""L=en_US"", """", 3)"); // arity.extra
FMObserve("29", "NumberInWords(1, 2)"); // type.format
