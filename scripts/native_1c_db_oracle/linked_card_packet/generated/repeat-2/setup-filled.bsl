// LOCAL preparation: generated owned-config probe. No native answers predicted.
Функция CRText(Знач Text)
    Если СтрДлина(Text) > 64 Тогда ВызватьИсключение "metadata-observer-bound"; КонецЕсли;
    Record = "S" + Строка(СтрДлина(Text)) + ":";
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Если Code < 0 Или Code > 65535 Тогда ВызватьИсключение "metadata-observer-unit"; КонецЕсли;
        Digits = "";
        Для D = 1 По 4 Цикл
            Q = Цел(Code / 16);
            Digits = Сред("0123456789abcdef", Code - Q * 16 + 1, 1) + Digits;
            Code = Q;
        КонецЦикла;
        Record = Record + Digits;
    КонецЦикла;
    Возврат Record;
КонецФункции
Функция CRScalar(Знач Value)
    Если ТипЗнч(Value) = Тип("Строка") Тогда Возврат CRText(Value); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Булево") Тогда Возврат ?(Value, "B1", "B0"); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Неопределено") Тогда Возврат "U"; КонецЕсли;
    Если ТипЗнч(Value) = Тип("Число") Тогда
        Если Value < 0 Или Value > 64 Или Value <> Цел(Value) Тогда ВызватьИсключение "metadata-observer-number"; КонецЕсли;
        Возврат "N" + Строка(Value);
    КонецЕсли;
    ВызватьИсключение "metadata-observer-type";
КонецФункции
Процедура CREmit(Знач Label, Знач Value)
    Попытка
        Encoded = CRScalar(Value);
    Исключение
        Сообщить("CR-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("CR-" + Label + ": [ok|" + Encoded + "]");
КонецПроцедуры
Процедура CRObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("CR-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    CREmit(Label, Value);
КонецПроцедуры
Функция CRCount(Name, Ref = Неопределено)
    Q = Новый Запрос;
    Q.Текст = "ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК N ИЗ Справочник." + Name;
    Если Ref <> Неопределено Тогда
        Q.Текст = Q.Текст + " ГДЕ Ссылка = &Ref";
        Q.УстановитьПараметр("Ref", Ref);
    КонецЕсли;
    Row = Q.Выполнить().Выбрать();
    Если Не Row.Следующий() Тогда ВызватьИсключение "setup-count"; КонецЕсли;
    Возврат Row.N;
КонецФункции
Сообщить("CR-C1: [" + CRText("") + "]");
Сообщить("CR-C2: [" + CRText("A ;""😀") + "]");
Если CRCount("Cc4e0bd7a") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
Если CRCount("C3ee974be") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
CM = Catalogs.C3ee974be; PM = Catalogs.Cc4e0bd7a;
C = CM.CreateItem(); C.SetNewObjectRef(CM.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9"))); C.Code = "10"; C.Description = "Category"; C.Write();
P = PM.CreateItem(); P.SetNewObjectRef(PM.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9"))); P.Code = "30"; P.Description = "First";
P.A8d7e5a88 = "hello"; P.A785f7e4e = 12.50; P.A80493488 = True; P.Aba998999 = Date(2024,2,29,12,34,56); P.Ae089a1a5 = CM.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9")); P.Write();
P = PM.CreateItem(); P.SetNewObjectRef(PM.GetRef(New UUID("4a8a95d1-4731-4733-98c3-13f5fda3c545"))); P.Code = "10"; P.Description = "Second";
P.A8d7e5a88 = ""; P.A785f7e4e = 0; P.A80493488 = False; P.Aba998999 = Date(1,1,1); P.Ae089a1a5 = CM.EmptyRef(); P.Write();
P = PM.CreateItem(); P.SetNewObjectRef(PM.GetRef(New UUID("6a70523e-6f76-4a45-8359-fd32efc514a8"))); P.Code = "20"; P.Description = "Third";
P.A8d7e5a88 = "third"; P.A785f7e4e = -7.25; P.A80493488 = True; P.Aba998999 = Date(2001,1,1,0,0,1); P.Ae089a1a5 = CM.GetRef(New UUID("b1f3f27a-dadd-456e-a0da-48ba74976466")); P.Write();
Q = New Query; Q.Text = "SELECT Code, A8d7e5a88 AS Label, A785f7e4e AS Price, A80493488 AS Enabled, Aba998999 AS Stamp, Ae089a1a5 AS Category FROM Catalog.Cc4e0bd7a ORDER BY Code"; W = Q.Execute().Select();
Try CREmit("01", Catalogs.Cc4e0bd7a.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.C3ee974be.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", CRCount("Cc4e0bd7a")); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", CRCount("C3ee974be")); Except Message("CR-04: [action-error]"); EndTry;
Try CREmit("05", CRCount("Cc4e0bd7a", Catalogs.Cc4e0bd7a.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9")))); Except Message("CR-05: [action-error]"); EndTry;
Try CREmit("06", CRCount("Cc4e0bd7a", Catalogs.Cc4e0bd7a.GetRef(New UUID("b1f3f27a-dadd-456e-a0da-48ba74976466")))); Except Message("CR-06: [action-error]"); EndTry;
Try CREmit("07", CRCount("C3ee974be", Catalogs.C3ee974be.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9")))); Except Message("CR-07: [action-error]"); EndTry;
Try CREmit("08", CRCount("C3ee974be", Catalogs.C3ee974be.GetRef(New UUID("b1f3f27a-dadd-456e-a0da-48ba74976466")))); Except Message("CR-08: [action-error]"); EndTry;
Try CREmit("09", W.Next()); Except Message("CR-09: [action-error]"); EndTry;
Try CREmit("10", W.Code); Except Message("CR-10: [action-error]"); EndTry;
Try CREmit("11", W.Enabled); Except Message("CR-11: [action-error]"); EndTry;
Try CREmit("12", W.Stamp = Date(1,1,1)); Except Message("CR-12: [action-error]"); EndTry;
Try CREmit("13", String(W.Category.UUID())); Except Message("CR-13: [action-error]"); EndTry;
Try CREmit("14", W.Next()); Except Message("CR-14: [action-error]"); EndTry;
Try CREmit("15", W.Code); Except Message("CR-15: [action-error]"); EndTry;
Try CREmit("16", W.Enabled); Except Message("CR-16: [action-error]"); EndTry;
Try CREmit("17", W.Stamp = Date(2001,1,1,0,0,1)); Except Message("CR-17: [action-error]"); EndTry;
Try CREmit("18", String(W.Category.UUID())); Except Message("CR-18: [action-error]"); EndTry;
Try CREmit("19", W.Next()); Except Message("CR-19: [action-error]"); EndTry;
Try CREmit("20", W.Code); Except Message("CR-20: [action-error]"); EndTry;
Try CREmit("21", W.Enabled); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", W.Stamp = Date(2024,2,29,12,34,56)); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", String(W.Category.UUID())); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", W.Next()); Except Message("CR-24: [action-error]"); EndTry;
