// Independent RU date names acquisition. Fixed inputs, no predicted native answers.
Функция FNEncode(Знач Text)
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
Процедура FNObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("FN-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    Попытка
        Record = FNEncode(Value);
    Исключение
        Сообщить("FN-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("FN-" + Label + ": [ok|" + Record + "]");
КонецПроцедуры
// Calibration covers empty text, NBSP, semicolon, quote and supplementary UTF-16.
Сообщить("FN-C1: [" + FNEncode("") + "]");
Сообщить("FN-C2: [" + FNEncode("A ;""😀") + "]");
// Fixed measurement inputs start here.
FNObserve("01", "Format('20261030123456', ""L=ru;DF='yyyy-MM-dd HH:mm:ss'"")"); // control.en
FNObserve("02", "Формат('20260102030405', ""Л=ru;ДФ='дд.ММ.гггг ЧЧ:мм:сс'"")"); // control.ru
FNObserve("03", "Format('20240229235959', ""L=ru;DF=yyyy-MM-dd"")"); // control.leap
FNObserve("04", "Format('00010101000000', ""L=ru;DE='EMPTY'"")"); // control.empty
FNObserve("05", "Format('20260102153456', ""L=ru;DF=MMM"")"); // m01.short
FNObserve("06", "Format('20260102153456', ""L=ru;DF=MMMM"")"); // m01.long
FNObserve("07", "Format('20260102153456', ""L=ru;DF='d MMM'"")"); // m01.short-day
FNObserve("08", "Format('20260102153456', ""L=ru;DF='d MMMM'"")"); // m01.long-day
FNObserve("09", "Format('20260202153456', ""L=ru;DF=MMM"")"); // m02.short
FNObserve("10", "Format('20260202153456', ""L=ru;DF=MMMM"")"); // m02.long
FNObserve("11", "Format('20260202153456', ""L=ru;DF='d MMM'"")"); // m02.short-day
FNObserve("12", "Format('20260202153456', ""L=ru;DF='d MMMM'"")"); // m02.long-day
FNObserve("13", "Format('20260302153456', ""L=ru;DF=MMM"")"); // m03.short
FNObserve("14", "Format('20260302153456', ""L=ru;DF=MMMM"")"); // m03.long
FNObserve("15", "Format('20260302153456', ""L=ru;DF='d MMM'"")"); // m03.short-day
FNObserve("16", "Format('20260302153456', ""L=ru;DF='d MMMM'"")"); // m03.long-day
FNObserve("17", "Format('20260402153456', ""L=ru;DF=MMM"")"); // m04.short
FNObserve("18", "Format('20260402153456', ""L=ru;DF=MMMM"")"); // m04.long
FNObserve("19", "Format('20260402153456', ""L=ru;DF='d MMM'"")"); // m04.short-day
FNObserve("20", "Format('20260402153456', ""L=ru;DF='d MMMM'"")"); // m04.long-day
FNObserve("21", "Format('20260502153456', ""L=ru;DF=MMM"")"); // m05.short
FNObserve("22", "Format('20260502153456', ""L=ru;DF=MMMM"")"); // m05.long
FNObserve("23", "Format('20260502153456', ""L=ru;DF='d MMM'"")"); // m05.short-day
FNObserve("24", "Format('20260502153456', ""L=ru;DF='d MMMM'"")"); // m05.long-day
FNObserve("25", "Format('20260602153456', ""L=ru;DF=MMM"")"); // m06.short
FNObserve("26", "Format('20260602153456', ""L=ru;DF=MMMM"")"); // m06.long
FNObserve("27", "Format('20260602153456', ""L=ru;DF='d MMM'"")"); // m06.short-day
FNObserve("28", "Format('20260602153456', ""L=ru;DF='d MMMM'"")"); // m06.long-day
FNObserve("29", "Format('20260702153456', ""L=ru;DF=MMM"")"); // m07.short
FNObserve("30", "Format('20260702153456', ""L=ru;DF=MMMM"")"); // m07.long
FNObserve("31", "Format('20260702153456', ""L=ru;DF='d MMM'"")"); // m07.short-day
FNObserve("32", "Format('20260702153456', ""L=ru;DF='d MMMM'"")"); // m07.long-day
FNObserve("33", "Format('20260802153456', ""L=ru;DF=MMM"")"); // m08.short
FNObserve("34", "Format('20260802153456', ""L=ru;DF=MMMM"")"); // m08.long
FNObserve("35", "Format('20260802153456', ""L=ru;DF='d MMM'"")"); // m08.short-day
FNObserve("36", "Format('20260802153456', ""L=ru;DF='d MMMM'"")"); // m08.long-day
FNObserve("37", "Format('20260902153456', ""L=ru;DF=MMM"")"); // m09.short
FNObserve("38", "Format('20260902153456', ""L=ru;DF=MMMM"")"); // m09.long
FNObserve("39", "Format('20260902153456', ""L=ru;DF='d MMM'"")"); // m09.short-day
FNObserve("40", "Format('20260902153456', ""L=ru;DF='d MMMM'"")"); // m09.long-day
FNObserve("41", "Format('20261002153456', ""L=ru;DF=MMM"")"); // m10.short
FNObserve("42", "Format('20261002153456', ""L=ru;DF=MMMM"")"); // m10.long
FNObserve("43", "Format('20261002153456', ""L=ru;DF='d MMM'"")"); // m10.short-day
FNObserve("44", "Format('20261002153456', ""L=ru;DF='d MMMM'"")"); // m10.long-day
FNObserve("45", "Format('20261102153456', ""L=ru;DF=MMM"")"); // m11.short
FNObserve("46", "Format('20261102153456', ""L=ru;DF=MMMM"")"); // m11.long
FNObserve("47", "Format('20261102153456', ""L=ru;DF='d MMM'"")"); // m11.short-day
FNObserve("48", "Format('20261102153456', ""L=ru;DF='d MMMM'"")"); // m11.long-day
FNObserve("49", "Format('20261202153456', ""L=ru;DF=MMM"")"); // m12.short
FNObserve("50", "Format('20261202153456', ""L=ru;DF=MMMM"")"); // m12.long
FNObserve("51", "Format('20261202153456', ""L=ru;DF='d MMM'"")"); // m12.short-day
FNObserve("52", "Format('20261202153456', ""L=ru;DF='d MMMM'"")"); // m12.long-day
