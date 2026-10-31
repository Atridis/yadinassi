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
FDObserve("01", "Format(1234.5, ""NFD=1;NG=0;NDS=."")"); // parser28.latin.nds.upper
FDObserve("02", "Format(1234.5, ""NFD=1;NG=0;nds=."")"); // parser28.latin.nds.lower
FDObserve("03", "Format(1234567.89, ""NFD=2;NG=0"")"); // parser28.latin.ng.upper
FDObserve("04", "Format(1234567.89, ""NFD=2;ng=0"")"); // parser28.latin.ng.lower
FDObserve("05", "Format(1234567.89, ""NFD=2;NG=3,0;NGS='_'"")"); // parser28.latin.ngs.upper
FDObserve("06", "Format(1234567.89, ""NFD=2;NG=3,0;ngs='_'"")"); // parser28.latin.ngs.lower
FDObserve("07", "Format(0, ""NZ='ZERO'"")"); // parser28.latin.nz.upper
FDObserve("08", "Format(0, ""nz='ZERO'"")"); // parser28.latin.nz.lower
FDObserve("09", "Format(1.234, ""ЧДЦ=1"")"); // parser28.ru.nfd.upper
FDObserve("10", "Format(1.234, ""чдц=1"")"); // parser28.ru.nfd.lower
FDObserve("11", "Format(1.5, ""ЧРД=."")"); // parser28.ru.nds.upper
FDObserve("12", "Format(1.5, ""чрд=."")"); // parser28.ru.nds.lower
FDObserve("13", "Format(1234.5, ""ЧГ=0"")"); // parser28.ru.ng.upper
FDObserve("14", "Format(1234.5, ""чг=0"")"); // parser28.ru.ng.lower
FDObserve("15", "Format(1234567.89, ""NG=3,0;ЧРГ='_'"")"); // parser28.ru.ngs.upper
FDObserve("16", "Format(1234567.89, ""NG=3,0;чрг='_'"")"); // parser28.ru.ngs.lower
FDObserve("17", "Format(0, ""ЧН='ZERO'"")"); // parser28.ru.nz.upper
FDObserve("18", "Format(0, ""чн='ZERO'"")"); // parser28.ru.nz.lower
FDObserve("19", "Format('00010101000000', ""DE='A'"")"); // parser28.de.upper
FDObserve("20", "Format('00010101000000', ""de='A'"")"); // parser28.de.lower
FDObserve("21", "Format('00010101000000', ""ДП='A'"")"); // parser28.de.ru-upper
FDObserve("22", "Format('00010101000000', ""дп='A'"")"); // parser28.de.ru-lower
FDObserve("23", "Format('00010101000000', ""DE='A';DE='B'"")"); // parser28.de.duplicate-forward
FDObserve("24", "Format('00010101000000', ""DE='B';DE='A'"")"); // parser28.de.duplicate-reverse
FDObserve("25", "Format('00010101000000', ""DE='A';ДП='B'"")"); // parser28.de.alias-forward
FDObserve("26", "Format('00010101000000', ""ДП='B';DE='A'"")"); // parser28.de.alias-reverse
FDObserve("27", "Format(1234.5, ""NFD=1;NG=0;L=en"")"); // parser28.locale.en.upper
FDObserve("28", "Format(1234.5, ""NFD=1;NG=0;l=en"")"); // parser28.locale.en.lower
