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
If DCCount("Document.D83c067c6") <> 0 Then Raise "setup-not-empty"; EndIf;
If DCCount("Catalog.C1bb732a4") <> 0 Then Raise "setup-not-empty"; EndIf;
C = Catalogs.C1bb732a4.CreateItem(); C.SetNewObjectRef(Catalogs.C1bb732a4.GetRef(New UUID("1bb270fb-e997-4ab7-9c05-fb57451c439f"))); C.Code = "10"; C.Description = "Category"; C.Write();
C = Catalogs.C1bb732a4.CreateItem(); C.SetNewObjectRef(Catalogs.C1bb732a4.GetRef(New UUID("8ccbe1ae-8da3-4a9f-8bbd-4be70a806d7f"))); C.Code = "20"; C.Description = "Second"; C.Write();
P = Documents.D83c067c6.CreateDocument(); P.SetNewObjectRef(Documents.D83c067c6.GetRef(New UUID("1bb270fb-e997-4ab7-9c05-fb57451c439f"))); P.Number = "30"; P.Date = Date(2024,2,29,12,34,56);
P.A220be581 = "third"; P.A08f3d2e5 = 12.50; P.A1616e487 = True; P.A7f952c46 = Date(2024,2,29,12,34,56); P.Ad3853bd2 = Catalogs.C1bb732a4.GetRef(New UUID("1bb270fb-e997-4ab7-9c05-fb57451c439f"));
P.Write(DocumentWriteMode.Posting, DocumentPostingMode.Regular);
P = Documents.D83c067c6.CreateDocument(); P.SetNewObjectRef(Documents.D83c067c6.GetRef(New UUID("b5197596-a5ce-4dcc-a74e-d4438bf71783"))); P.Number = "10"; P.Date = Date(2024,3,1,1,2,3);
P.A220be581 = ""; P.A08f3d2e5 = 0; P.A1616e487 = False; P.A7f952c46 = Date(2024,3,1,1,2,3); P.Ad3853bd2 = Catalogs.C1bb732a4.EmptyRef();
L = P.Items.Add(); L.Product = Catalogs.C1bb732a4.GetRef(New UUID("8ccbe1ae-8da3-4a9f-8bbd-4be70a806d7f")); L.Quantity = 1; L.Price = 2.50; L.Amount = 2.50; L.Note = "single";
P.Write(DocumentWriteMode.Write);
P = Documents.D83c067c6.CreateDocument(); P.SetNewObjectRef(Documents.D83c067c6.GetRef(New UUID("d7dc2016-f990-4e96-9599-64b7920b9609"))); P.Number = "20"; P.Date = Date(2001,1,1,0,0,1);
P.A220be581 = "first"; P.A08f3d2e5 = -7.25; P.A1616e487 = True; P.A7f952c46 = Date(2001,1,1,0,0,1); P.Ad3853bd2 = Catalogs.C1bb732a4.GetRef(New UUID("df869c3e-008d-4910-85d8-951a17332e97"));
L = P.Items.Add(); L.Product = Catalogs.C1bb732a4.GetRef(New UUID("1bb270fb-e997-4ab7-9c05-fb57451c439f")); L.Quantity = 2; L.Price = 3.25; L.Amount = 6.50; L.Note = "first";
L = P.Items.Add(); L.Product = Catalogs.C1bb732a4.GetRef(New UUID("8ccbe1ae-8da3-4a9f-8bbd-4be70a806d7f")); L.Quantity = 1; L.Price = 2; L.Amount = 2; L.Note = "second";
L = P.Items.Add(); L.Product = Catalogs.C1bb732a4.GetRef(New UUID("1bb270fb-e997-4ab7-9c05-fb57451c439f")); L.Quantity = -1; L.Price = 1.25; L.Amount = -1.25; L.Note = "last";
P.Write(DocumentWriteMode.Write);
Q = New Query; Q.Text = "SELECT Number, Date, Posted, Ad3853bd2 AS Target FROM Document.D83c067c6 ORDER BY Date"; W = Q.Execute().Select();
Try CREmit("01", Documents.D83c067c6.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.C1bb732a4.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", DCCount("Document.D83c067c6")); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", DCCount("Catalog.C1bb732a4")); Except Message("CR-04: [action-error]"); EndTry;
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
Try CREmit("21", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
