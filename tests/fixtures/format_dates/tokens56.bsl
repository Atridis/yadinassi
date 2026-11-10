// Independent RU date tokens acquisition. Fixed inputs, no predicted native answers.
Функция FTEncode(Знач Text)
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
Процедура FTObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("FT-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    Попытка
        Record = FTEncode(Value);
    Исключение
        Сообщить("FT-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("FT-" + Label + ": [ok|" + Record + "]");
КонецПроцедуры
// Calibration covers empty text, NBSP, semicolon, quote and supplementary UTF-16.
Сообщить("FT-C1: [" + FTEncode("") + "]");
Сообщить("FT-C2: [" + FTEncode("A ;""😀") + "]");
// Fixed measurement inputs start here.
FTObserve("01", "Format('20261030123456', ""L=ru;DF='yyyy-MM-dd HH:mm:ss'"")"); // control.en
FTObserve("02", "Формат('20260102030405', ""Л=ru;ДФ='дд.ММ.гггг ЧЧ:мм:сс'"")"); // control.ru
FTObserve("03", "Format('20240229235959', ""L=ru;DF=yyyy-MM-dd"")"); // control.leap
FTObserve("04", "Format('00010101000000', ""L=ru;DE='EMPTY'"")"); // control.empty
FTObserve("05", "Format('20260105153456', ""L=ru;DF=ddd|dddd"")"); // weekday.en.1
FTObserve("06", "Format('20260106153456', ""L=ru;DF=ddd|dddd"")"); // weekday.en.2
FTObserve("07", "Format('20260107153456', ""L=ru;DF=ddd|dddd"")"); // weekday.en.3
FTObserve("08", "Format('20260108153456', ""L=ru;DF=ddd|dddd"")"); // weekday.en.4
FTObserve("09", "Format('20260109153456', ""L=ru;DF=ddd|dddd"")"); // weekday.en.5
FTObserve("10", "Format('20260110153456', ""L=ru;DF=ddd|dddd"")"); // weekday.en.6
FTObserve("11", "Format('20260111153456', ""L=ru;DF=ddd|dddd"")"); // weekday.en.7
FTObserve("12", "Format('20260105153456', ""L=ru;DF=ддд|дддд"")"); // weekday.ru.1
FTObserve("13", "Format('20260106153456', ""L=ru;DF='MMMM dd'"")"); // context.reverse-day
FTObserve("14", "Format('20260107153456', ""L=ru;DF=""""'d' MMMM"""""")"); // context.literal-day-before
FTObserve("15", "Format('20260108153456', ""L=ru;DF='dddd MMMM'"")"); // context.weekday
FTObserve("16", "Format('20260109153456', ""L=ru;DF=""""MMMM 'd'"""""")"); // context.literal-day-after
FTObserve("17", "Format('20260110153456', ""L=ru;DF=ддд|дддд"")"); // weekday.ru.6
FTObserve("18", "Format('20260111153456', ""L=ru;DF=ддд|дддд"")"); // weekday.ru.7
FTObserve("19", "Формат('20260102153456', ""Л=ru;ДФ=МММ"")"); // ru.short
FTObserve("20", "Формат('20260102153456', ""Л=ru;ДФ=ММММ"")"); // ru.long
FTObserve("21", "Формат('20260102153456', ""Л=ru;ДФ='д МММ'"")"); // ru.short-day
FTObserve("22", "Формат('20260102153456', ""Л=ru;ДФ='д ММММ'"")"); // ru.long-day
FTObserve("23", "Формат('20260102153456', ""Л=ru;ДФ=д|дд|М|ММ|г|гг|гггг|к"")"); // ru.numeric
FTObserve("24", "Format('20000102153456', ""L=ru;DF=y|yy|yyyy|q"")"); // year-quarter.200001
FTObserve("25", "Format('20010402153456', ""L=ru;DF=y|yy|yyyy|q"")"); // year-quarter.200104
FTObserve("26", "Format('20090702153456', ""L=ru;DF=y|yy|yyyy|q"")"); // year-quarter.200907
FTObserve("27", "Format('20991002153456', ""L=ru;DF=y|yy|yyyy|q"")"); // year-quarter.209910
FTObserve("28", "Format('20261030003456', ""L=ru;DF=h|hh|H|HH|tt"")"); // hour.en.00
FTObserve("29", "Format('20261030033456', ""L=ru;DF=h|hh|H|HH|tt"")"); // hour.en.03
FTObserve("30", "Format('20261030123456', ""L=ru;DF=h|hh|H|HH|tt"")"); // hour.en.12
FTObserve("31", "Format('20261030153456', ""L=ru;DF=h|hh|H|HH|tt"")"); // hour.en.15
FTObserve("32", "Format('20261030233456', ""L=ru;DF=h|hh|H|HH|tt"")"); // hour.en.23
FTObserve("33", "Format('20261030003456', ""L=ru;DF=ч|чч|Ч|ЧЧ|вв"")"); // hour.ru.00
FTObserve("34", "Format('20261030033456', ""L=ru;DF=ч|чч|Ч|ЧЧ|вв"")"); // hour.ru.03
FTObserve("35", "Format('20261030123456', ""L=ru;DF=ч|чч|Ч|ЧЧ|вв"")"); // hour.ru.12
FTObserve("36", "Format('20261030153456', ""L=ru;DF=ч|чч|Ч|ЧЧ|вв"")"); // hour.ru.15
FTObserve("37", "Format('20261030233456', ""L=ru;DF=ч|чч|Ч|ЧЧ|вв"")"); // hour.ru.23
FTObserve("38", "Format('20261030123456', ""L=ru;DLF=D"")"); // local.en.1
FTObserve("39", "Format('20261030123456', ""L=ru;DLF=DD"")"); // local.en.2
FTObserve("40", "Format('20261030123456', ""L=ru;DLF=T"")"); // local.en.3
FTObserve("41", "Format('20261030123456', ""L=ru;DLF=DT"")"); // local.en.4
FTObserve("42", "Format('20261030123456', ""L=ru;DLF=DDT"")"); // local.en.5
FTObserve("43", "Format('20261030123456', ""L=ru;ДЛФ=Д"")"); // local.ru.1
FTObserve("44", "Format('20261030123456', ""L=ru;ДЛФ=ДД"")"); // local.ru.2
FTObserve("45", "Format('20261030123456', ""L=ru;ДЛФ=В"")"); // local.ru.3
FTObserve("46", "Format('20261030123456', ""L=ru;ДЛФ=ДВ"")"); // local.ru.4
FTObserve("47", "Format('20261030123456', ""L=ru;ДЛФ=ДДВ"")"); // local.ru.5
FTObserve("48", "Format('20261030123456', ""L=ru;DLF=DD;DF=yyyy"")"); // precedence.1
FTObserve("49", "Format('20261030123456', ""L=ru;DF=yyyy;DLF=DD"")"); // precedence.2
FTObserve("50", "Format('20261030123456', ""L=ru;DLF=D;DLF=T"")"); // precedence.3
FTObserve("51", "Format('20261030123456', ""L=ru;ДЛФ=ДД;DLF=D"")"); // precedence.4
FTObserve("52", "Format('20261030123456', ""L=ru;DF='';DLF=DD"")"); // precedence.5
FTObserve("53", "Format('00010101000000', ""L=ru;DF=yyyy;DLF=DD;DE='EMPTY'"")"); // precedence.6
FTObserve("54", "Format('00010101000000', ""L=ru;DLF=DD;DF=yyyy;DE='EMPTY'"")"); // precedence.7
FTObserve("55", "Format('00010101000000', ""L=ru;DLF=DD"")"); // precedence.8
FTObserve("56", "Format('20261030123456', ""L=ru;DLF=DD;DE='EMPTY'"")"); // precedence.9
