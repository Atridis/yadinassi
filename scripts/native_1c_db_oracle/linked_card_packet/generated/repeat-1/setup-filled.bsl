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
Если CRCount("C8011eed4") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
Если CRCount("Cfedffdf5") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
CM = Catalogs.Cfedffdf5; PM = Catalogs.C8011eed4;
C = CM.CreateItem(); C.SetNewObjectRef(CM.GetRef(New UUID("b78d8591-9426-4e66-bc30-1df6aae7f9ee"))); C.Code = "10"; C.Description = "Category"; C.Write();
P = PM.CreateItem(); P.SetNewObjectRef(PM.GetRef(New UUID("b78d8591-9426-4e66-bc30-1df6aae7f9ee"))); P.Code = "30"; P.Description = "First";
P.Acb092b78 = "hello"; P.A442761a6 = 12.50; P.Ade9513c6 = True; P.Aa312fe5e = Date(2024,2,29,12,34,56); P.A2bd85387 = CM.GetRef(New UUID("b78d8591-9426-4e66-bc30-1df6aae7f9ee")); P.Write();
P = PM.CreateItem(); P.SetNewObjectRef(PM.GetRef(New UUID("a62d520e-60bd-4796-bc0b-895e7a6cd9b8"))); P.Code = "10"; P.Description = "Second";
P.Acb092b78 = ""; P.A442761a6 = 0; P.Ade9513c6 = False; P.Aa312fe5e = Date(1,1,1); P.A2bd85387 = CM.EmptyRef(); P.Write();
P = PM.CreateItem(); P.SetNewObjectRef(PM.GetRef(New UUID("b4f505ab-2142-4ca4-9816-aadb994330a4"))); P.Code = "20"; P.Description = "Third";
P.Acb092b78 = "third"; P.A442761a6 = -7.25; P.Ade9513c6 = True; P.Aa312fe5e = Date(2001,1,1,0,0,1); P.A2bd85387 = CM.GetRef(New UUID("35827303-e5e0-4cc7-b6d1-6f67408e08b1")); P.Write();
Q = New Query; Q.Text = "SELECT Code, Acb092b78 AS Label, A442761a6 AS Price, Ade9513c6 AS Enabled, Aa312fe5e AS Stamp, A2bd85387 AS Category FROM Catalog.C8011eed4 ORDER BY Code"; W = Q.Execute().Select();
Try CREmit("01", Catalogs.C8011eed4.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.Cfedffdf5.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", CRCount("C8011eed4")); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", CRCount("Cfedffdf5")); Except Message("CR-04: [action-error]"); EndTry;
Try CREmit("05", CRCount("C8011eed4", Catalogs.C8011eed4.GetRef(New UUID("b78d8591-9426-4e66-bc30-1df6aae7f9ee")))); Except Message("CR-05: [action-error]"); EndTry;
Try CREmit("06", CRCount("C8011eed4", Catalogs.C8011eed4.GetRef(New UUID("35827303-e5e0-4cc7-b6d1-6f67408e08b1")))); Except Message("CR-06: [action-error]"); EndTry;
Try CREmit("07", CRCount("Cfedffdf5", Catalogs.Cfedffdf5.GetRef(New UUID("b78d8591-9426-4e66-bc30-1df6aae7f9ee")))); Except Message("CR-07: [action-error]"); EndTry;
Try CREmit("08", CRCount("Cfedffdf5", Catalogs.Cfedffdf5.GetRef(New UUID("35827303-e5e0-4cc7-b6d1-6f67408e08b1")))); Except Message("CR-08: [action-error]"); EndTry;
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
