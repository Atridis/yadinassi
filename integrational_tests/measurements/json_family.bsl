// One whole-family JSON measurement. Fixed synthetic inputs only.
// !todo Date/callback/XDTO and obscure malformed-input diagnostics are deferred.
Функция JFEncode(Знач Text)
    Если ТипЗнч(Text) <> Тип("Строка") Или СтрДлина(Text) > 56 Тогда
        ВызватьИсключение "json-observer-text-bound";
    КонецЕсли;
    Record = "S" + Строка(СтрДлина(Text)) + ":";
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Если Code < 0 Или Code > 65535 Тогда ВызватьИсключение "json-observer-unit-bound"; КонецЕсли;
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
Функция JFCompact(Знач Value)
    W = Новый ЗаписьJSON;
    W.УстановитьСтроку(Новый ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет));
    ЗаписатьJSON(W, Value);
    Возврат W.Закрыть();
КонецФункции
Функция JFRead(Знач Text, Знач ToMap = Ложь)
    R = Новый ЧтениеJSON;
    R.УстановитьСтроку(Text);
    Value = ПрочитатьJSON(R, ToMap);
    R.Закрыть();
    Возврат Value;
КонецФункции
Функция JFToken(Знач R)
    T = R.ТипТекущегоЗначения;
    Если T = ТипЗначенияJSON.НачалоМассива Тогда Возврат "["; КонецЕсли;
    Если T = ТипЗначенияJSON.КонецМассива Тогда Возврат "]"; КонецЕсли;
    Если T = ТипЗначенияJSON.НачалоОбъекта Тогда Возврат "{"; КонецЕсли;
    Если T = ТипЗначенияJSON.КонецОбъекта Тогда Возврат "}"; КонецЕсли;
    Если T = ТипЗначенияJSON.ИмяСвойства Тогда Возврат "K"; КонецЕсли;
    Если T = ТипЗначенияJSON.Строка Тогда Возврат "S"; КонецЕсли;
    Если T = ТипЗначенияJSON.Число Тогда Возврат "N"; КонецЕсли;
    Если T = ТипЗначенияJSON.Булево Тогда Возврат "B"; КонецЕсли;
    Если T = ТипЗначенияJSON.Null Тогда Возврат "U"; КонецЕсли;
    Возврат "?";
КонецФункции
Функция JFFile(Знач BOM)
    Path = ПолучитьИмяВременногоФайла("json");
    W = Новый ЗаписьJSON;
    R = Новый ЧтениеJSON;
    Попытка
        W.ОткрытьФайл(Path, "UTF-8", BOM, Новый ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет));
        ЗаписатьJSON(W, Новый Структура("s", "Привет"));
        Closed = W.Закрыть();
        R.ОткрытьФайл(Path);
        Value = ПрочитатьJSON(R);
        R.Закрыть();
        УдалитьФайлы(Path);
    Исключение
        Попытка R.Закрыть(); Исключение КонецПопытки;
        Попытка W.Закрыть(); Исключение КонецПопытки;
        Попытка УдалитьФайлы(Path); Исключение КонецПопытки;
        ВызватьИсключение;
    КонецПопытки;
    Возврат Строка(СтрДлина(Closed)) + ":" + JFCompact(Value);
КонецФункции
Функция JFCase(Знач N)
    Если N = 1 Тогда
        Возврат JFCompact(JFRead("{""a"":[1.25,true,null],""s"":""я""}"));
    ИначеЕсли N = 2 Тогда
        W = Новый JSONWriter; W.SetString(); WriteJSON(W, JFRead("{""a"":[1,2]}")); Возврат W.Close();
    ИначеЕсли N = 3 Тогда
        W = Новый JSONWriter; W.SetString(Новый JSONWriterSettings(JSONLineBreak.Unix, "  "));
        WriteJSON(W, JFRead("{""a"":[1,2]}")); Возврат W.Close();
    ИначеЕсли N = 4 Тогда
        W = Новый JSONWriter; W.SetString(Новый JSONWriterSettings(JSONLineBreak.Windows, " "));
        WriteJSON(W, JFRead("{""a"":1}")); Возврат W.Close();
    ИначеЕсли N = 5 Тогда
        W = Новый ЗаписьJSON; W.УстановитьСтроку(Новый ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет));
        W.ЗаписатьНачалоОбъекта(); W.ЗаписатьИмяСвойства("a"); W.ЗаписатьНачалоМассива();
        W.ЗаписатьЗначение(Истина); W.ЗаписатьЗначение(Неопределено);
        W.ЗаписатьКонецМассива(); W.ЗаписатьКонецОбъекта(); Возврат W.Закрыть();
    ИначеЕсли N = 6 Тогда
        M = JFRead("{""bad-key"":1,"""":2}", Истина); Возврат JFCompact(M["bad-key"]) + ":" + JFCompact(M[""]);
    ИначеЕсли N = 7 Тогда
        A = Новый Массив; A.Добавить(Новый ФиксированнаяСтруктура("a", 1));
        M = Новый Соответствие; M.Вставить("b", 2); A.Добавить(Новый ФиксированноеСоответствие(M));
        Возврат JFCompact(Новый ФиксированныйМассив(A));
    ИначеЕсли N = 8 Тогда
        R = Новый JSONReader; R.SetString("{""a"":[1,true,null,""x""]}"); Result = "";
        Пока R.Read() Цикл Result = Result + JFToken(R); КонецЦикла;
        R.Close(); Возврат Result;
    ИначеЕсли N = 9 Тогда
        R = Новый JSONReader; R.SetString("1"); Возврат Строка(R.CurrentValueType);
    ИначеЕсли N = 10 Тогда
        R = Новый JSONReader; R.SetString("1"); R.Read(); R.Read(); Возврат Строка(R.CurrentValueType);
    ИначеЕсли N = 11 Тогда
        R = Новый JSONReader; R.SetString("[]"); R.Read(); Возврат Строка(R.CurrentValue);
    ИначеЕсли N = 12 Тогда
        R = Новый JSONReader; R.SetString("[{""a"":[1,2]},true]"); R.Read(); R.Read();
        Result = Строка(R.Skip()) + ":" + JFToken(R) + ":" + Строка(R.CurrentValue);
        Возврат Result;
    ИначеЕсли N = 13 Тогда
        R = Новый JSONReader; R.SetString("[{""a"":1},2]"); R.Read(); R.Read();
        V = ReadJSON(R); Result = JFCompact(V) + ":" + JFToken(R);
        R.Read(); Возврат Result + ":" + JFCompact(ReadJSON(R)) + ":" + JFToken(R);
    ИначеЕсли N = 14 Тогда
        R = Новый JSONReader; R.SetString("[1,2]"); R.Read(); R.Read();
        V = ReadJSON(R); Result = JFCompact(V) + ":" + JFToken(R);
        Возврат Result + ":" + JFCompact(ReadJSON(R));
    ИначеЕсли N = 15 Тогда
        Возврат JFCompact(JFRead("{""bad-key"":1}"));
    ИначеЕсли N = 16 Тогда
        M = Новый Соответствие; M.Вставить(1, "x"); Возврат JFCompact(M);
    ИначеЕсли N = 17 Тогда
        Возврат JFCompact(Null);
    ИначеЕсли N = 18 Тогда
        Возврат JFCompact(JFRead("[1,]"));
    ИначеЕсли N = 19 Тогда
        W = Новый JSONWriter; W.SetString(); W.WriteStartObject(); W.WriteValue(1); Возврат W.Close();
    ИначеЕсли N = 20 Тогда
        R = Новый JSONReader; R.SetString("[""\uD83D\uDE00"",-1.25e2,null]"); Result = "";
        R.Read(); Пока R.Read() Цикл
            Если R.CurrentValueType <> JSONValueType.ArrayEnd Тогда Result = Result + JFCompact(R.CurrentValue) + ";"; КонецЕсли;
        КонецЦикла; Возврат Result;
    ИначеЕсли N = 21 Тогда
        R = Новый JSONReader; R.SetString("[1]"); R.Read(); R.SetString("{""b"":2}"); Возврат JFCompact(ReadJSON(R));
    ИначеЕсли N = 22 Тогда
        W = Новый JSONWriter; W.SetString(); W.WriteValue(1); A = W.Close();
        W.SetString(); W.WriteValue(2); Возврат A + ":" + W.Close();
    ИначеЕсли N = 23 Тогда
        Возврат JFFile(Ложь);
    ИначеЕсли N = 24 Тогда
        Возврат JFFile(Истина);
    ИначеЕсли N = 25 Тогда
        Возврат JFCompact(JFRead("[12345678901234567890.125,-0.0000001]"));
    ИначеЕсли N = 26 Тогда
        A = Новый JSONReader; B = Новый JSONWriter;
        Возврат Строка(ТипЗнч(A) = Тип("JSONReader")) + ":" + Строка(ТипЗнч(B) = Тип("JSONWriter"))
            + ":" + Строка(ТипЗнч(JSONValueType.Number) = Тип("JSONValueType"));
    ИначеЕсли N = 27 Тогда
        W = Новый JSONWriter; W.SetString(Новый JSONWriterSettings(JSONLineBreak.None));
        W.WriteValue("quote""\" + Символы.ПС + "😀"); Возврат W.Close();
    ИначеЕсли N = 28 Тогда
        R = Новый JSONReader; R.SetString("1"); R.Close(); Возврат Строка(R.Read());
    ИначеЕсли N = 29 Тогда
        W = Новый JSONWriter; W.SetString(); W.WriteValue(123.45, Истина); Возврат W.Close();
    ИначеЕсли N = 30 Тогда
        W = Новый JSONWriter; W.SetString(Новый JSONWriterSettings(, "  "));
        WriteJSON(W, JFRead("{""a"":[1,2]}")); Возврат W.Close();
    ИначеЕсли N = 31 Тогда
        W = Новый JSONWriter; W.SetString(Новый JSONWriterSettings());
        WriteJSON(W, JFRead("{""a"":[1,2]}")); Возврат W.Close();
    КонецЕсли;
    ВызватьИсключение "json-case-bound";
КонецФункции
Процедура JFObserve(Знач N)
    Label = Прав("0" + Строка(N), 2);
    Попытка
        Value = JFCase(N);
    Исключение
        Сообщить("JF-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    Попытка
        Record = JFEncode(Value);
    Исключение
        Сообщить("JF-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("JF-" + Label + ": [ok|" + Record + "]");
КонецПроцедуры
Сообщить("JF-C1: [" + JFEncode("") + "]");
Сообщить("JF-C2: [" + JFEncode("A ;""😀") + "]");
Для N = 1 По 31 Цикл JFObserve(N); КонецЦикла;
