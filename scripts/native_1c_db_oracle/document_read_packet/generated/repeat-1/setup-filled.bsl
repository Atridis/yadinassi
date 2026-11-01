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
Function DCCount(TableName)
Q = New Query; Q.Text = "SELECT COUNT(*) AS N FROM " + TableName;
W = Q.Execute().Select(); W.Next(); Return W.N;
EndFunction
Сообщить("CR-C1: [" + CRText("") + "]");
Сообщить("CR-C2: [" + CRText("A ;""😀") + "]");
If DCCount("Document.Dad0328ac") <> 0 Then Raise "setup-not-empty"; EndIf;
If DCCount("Catalog.C95217507") <> 0 Then Raise "setup-not-empty"; EndIf;
C = Catalogs.C95217507.CreateItem(); C.SetNewObjectRef(Catalogs.C95217507.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))); C.Code = "10"; C.Description = "Category"; C.Write();
P = Documents.Dad0328ac.CreateDocument(); P.SetNewObjectRef(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))); P.Number = "30"; P.Date = Date(2024,2,29,12,34,56);
P.A7d6294c3 = "third"; P.Aeea091ef = 12.50; P.Ac27bdff6 = True; P.A4f92e66d = Date(2024,2,29,12,34,56); P.A5449af58 = Catalogs.C95217507.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"));
P.Write(DocumentWriteMode.Posting, DocumentPostingMode.Regular);
P = Documents.Dad0328ac.CreateDocument(); P.SetNewObjectRef(Documents.Dad0328ac.GetRef(New UUID("2f548d2e-dfa7-4b96-9163-66a7934c32fc"))); P.Number = "10"; P.Date = Date(2024,3,1,1,2,3);
P.A7d6294c3 = ""; P.Aeea091ef = 0; P.Ac27bdff6 = False; P.A4f92e66d = Date(2024,3,1,1,2,3); P.A5449af58 = Catalogs.C95217507.EmptyRef();
P.Write(DocumentWriteMode.Write);
P = Documents.Dad0328ac.CreateDocument(); P.SetNewObjectRef(Documents.Dad0328ac.GetRef(New UUID("f004c11c-c6e7-4169-8560-f5e00cc00aa7"))); P.Number = "20"; P.Date = Date(2001,1,1,0,0,1);
P.A7d6294c3 = "first"; P.Aeea091ef = -7.25; P.Ac27bdff6 = True; P.A4f92e66d = Date(2001,1,1,0,0,1); P.A5449af58 = Catalogs.C95217507.GetRef(New UUID("3247a168-60b7-4bbb-901d-1601b198cfb6"));
P.Write(DocumentWriteMode.Write);
Q = New Query; Q.Text = "SELECT Number, Date, Posted, A5449af58 AS Target FROM Document.Dad0328ac ORDER BY Date"; W = Q.Execute().Select();
Try CREmit("01", Documents.Dad0328ac.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.C95217507.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", DCCount("Document.Dad0328ac")); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", DCCount("Catalog.C95217507")); Except Message("CR-04: [action-error]"); EndTry;
Try CREmit("05", W.Next()); Except Message("CR-05: [action-error]"); EndTry;
Try CREmit("06", W.Number); Except Message("CR-06: [action-error]"); EndTry;
Try CREmit("07", W.Date = Date(2001,1,1,0,0,1)); Except Message("CR-07: [action-error]"); EndTry;
Try CREmit("08", W.Posted); Except Message("CR-08: [action-error]"); EndTry;
Try CREmit("09", String(W.Target.UUID())); Except Message("CR-09: [action-error]"); EndTry;
Try CREmit("10", W.Next()); Except Message("CR-10: [action-error]"); EndTry;
Try CREmit("11", W.Number); Except Message("CR-11: [action-error]"); EndTry;
Try CREmit("12", W.Date = Date(2024,2,29,12,34,56)); Except Message("CR-12: [action-error]"); EndTry;
Try CREmit("13", W.Posted); Except Message("CR-13: [action-error]"); EndTry;
Try CREmit("14", String(W.Target.UUID())); Except Message("CR-14: [action-error]"); EndTry;
Try CREmit("15", W.Next()); Except Message("CR-15: [action-error]"); EndTry;
Try CREmit("16", W.Number); Except Message("CR-16: [action-error]"); EndTry;
Try CREmit("17", W.Date = Date(2024,3,1,1,2,3)); Except Message("CR-17: [action-error]"); EndTry;
Try CREmit("18", W.Posted); Except Message("CR-18: [action-error]"); EndTry;
Try CREmit("19", String(W.Target.UUID())); Except Message("CR-19: [action-error]"); EndTry;
Try CREmit("20", W.Next()); Except Message("CR-20: [action-error]"); EndTry;
Try CREmit("21", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
