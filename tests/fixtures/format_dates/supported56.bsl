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
FDObserve("01", "Format('20261030123456', ""DF=yyyy-MM-dd HH:mm:ss"")"); // supported.original40.01
FDObserve("02", "Формат('20261030123456', ""ДФ=dd.MM.yyyy HH:mm:ss"")"); // supported.original40.02
FDObserve("03", "Format('20260102030405', ""DF=d.M.yyyy H:m:s"")"); // supported.original40.03
FDObserve("04", "Format('20240229235959', ""DF=yyyy-MM-dd HH:mm:ss"")"); // supported.original40.04
FDObserve("05", "Format('20261030000000', ""DF=yyyy-MM-dd HH:mm:ss"")"); // supported.original40.05
FDObserve("06", "Format('00010101000001', ""DF=yyyy-MM-dd HH:mm:ss"")"); // supported.original40.06
FDObserve("07", "Format('99991231235959', ""DF=yyyy-MM-dd HH:mm:ss"")"); // supported.original40.07
FDObserve("08", "Format('20261030123456' + 0.5, ""DF=yyyy-MM-dd HH:mm:ss"")"); // supported.original40.08
FDObserve("09", "Format('20260102030405', ""DF=d"")"); // supported.original40.09
FDObserve("10", "Format('20260102030405', ""DF=dd"")"); // supported.original40.10
FDObserve("11", "Format('20260102030405', ""DF=M"")"); // supported.original40.11
FDObserve("12", "Format('20260102030405', ""DF=MM"")"); // supported.original40.12
FDObserve("13", "Format('20260102030405', ""DF=yy"")"); // supported.original40.13
FDObserve("14", "Format('20260102030405', ""DF=yyyy"")"); // supported.original40.14
FDObserve("15", "Format('20260102030405', ""DF=H"")"); // supported.original40.15
FDObserve("16", "Format('20260102030405', ""DF=HH"")"); // supported.original40.16
FDObserve("17", "Format('20260102030405', ""DF=m"")"); // supported.original40.17
FDObserve("18", "Format('20260102030405', ""DF=mm"")"); // supported.original40.18
FDObserve("19", "Format('20260102030405', ""DF=s"")"); // supported.original40.19
FDObserve("20", "Format('20260102030405', ""DF=ss"")"); // supported.original40.20
FDObserve("21", "Format('00010101000000', """")"); // supported.original40.21
FDObserve("22", "Format('00010101000000', ""DF=yyyy-MM-dd HH:mm:ss"")"); // supported.original40.22
FDObserve("23", "Format('00010101000000', ""DE=''"")"); // supported.original40.23
FDObserve("24", "Format('00010101000000', ""DE='EMPTY'"")"); // supported.original40.24
FDObserve("25", "Format('00010101000000', ""DF=yyyy-MM-dd;DE='EMPTY'"")"); // supported.original40.25
FDObserve("26", "Format('00010101000001', ""DF=yyyy-MM-dd HH:mm:ss;DE='EMPTY'"")"); // supported.original40.26
FDObserve("27", "Format('20261030123456', ""DF='yyyy-MM-dd HH:mm:ss'"")"); // supported.original40.27
FDObserve("28", "Format('20261030123456', ""DF=""""yyyy-MM-dd HH:mm:ss"""""")"); // supported.original40.28
FDObserve("29", "Format('20261030123456', ""DF=""""yyyy 'year' MM"""""")"); // supported.original40.29
FDObserve("30", "Format('20261030123456', ""DF=""""yyyy''MM"""""")"); // supported.original40.30
FDObserve("31", "Format('20261030123456', ""DF=""""yyyy';'MM"""""")"); // supported.original40.31
FDObserve("32", "Формат('00010101000000', ""ДФ='dd.MM.yyyy';ДП='ПУСТО'"")"); // supported.original40.32
FDObserve("33", "Format('20261030123456', ""DF=yyyy;DF=MM"")"); // supported.original40.33
FDObserve("34", "Format('20261030123456', ""df=yyyy;ДФ=MM"")"); // supported.original40.34
FDObserve("35", "Format('20261030123456', ""UNKNOWN=xyz;DF=yyyy-MM-dd"")"); // supported.original40.37
FDObserve("36", "Format(123.45, ""DF=yyyy;DE='EMPTY'"")"); // supported.original40.38
FDObserve("37", "Format(True, ""DF=yyyy;DE='EMPTY'"")"); // supported.original40.39
FDObserve("38", "Format(""abc"", ""DF=yyyy;DE='EMPTY'"")"); // supported.original40.40
FDObserve("39", "Format(1234.5, ""NFD=1;NG=0;nds=."")"); // supported.parser28.02
FDObserve("40", "Format(1234567.89, ""NFD=2;ng=0"")"); // supported.parser28.04
FDObserve("41", "Format(1234567.89, ""NFD=2;NG=3,0;ngs='_'"")"); // supported.parser28.06
FDObserve("42", "Format(0, ""nz='ZERO'"")"); // supported.parser28.08
FDObserve("43", "Format(1.234, ""чдц=1"")"); // supported.parser28.10
FDObserve("44", "Format(1.5, ""чрд=."")"); // supported.parser28.12
FDObserve("45", "Format(1234.5, ""чг=0"")"); // supported.parser28.14
FDObserve("46", "Format(1234567.89, ""NG=3,0;чрг='_'"")"); // supported.parser28.16
FDObserve("47", "Format(0, ""чн='ZERO'"")"); // supported.parser28.18
FDObserve("48", "Format('00010101000000', ""de='A'"")"); // supported.parser28.20
FDObserve("49", "Format('00010101000000', ""дп='A'"")"); // supported.parser28.22
FDObserve("50", "Format('00010101000000', ""DE='A';DE='B'"")"); // supported.parser28.23
FDObserve("51", "Format('00010101000000', ""DE='B';DE='A'"")"); // supported.parser28.24
FDObserve("52", "Format('00010101000000', ""DE='A';ДП='B'"")"); // supported.parser28.25
FDObserve("53", "Format('00010101000000', ""ДП='B';DE='A'"")"); // supported.parser28.26
FDObserve("54", "Format(1234.5, ""NFD=1;NG=0;l=en"")"); // supported.parser28.28
FDObserve("55", "Format('20260102030405', ""DF=MM;DF=yyyy"")"); // supported.supplement56.44
FDObserve("56", "Format('20260102030405', ""DF=yyyy;ДФ=MM"")"); // supported.supplement56.47
