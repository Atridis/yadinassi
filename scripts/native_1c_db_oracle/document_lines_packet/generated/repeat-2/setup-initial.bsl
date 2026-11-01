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
If DCCount("Document.De777997a") <> 0 Then Raise "setup-not-empty"; EndIf;
If DCCount("Catalog.Cb27de61e") <> 0 Then Raise "setup-not-empty"; EndIf;
C = Catalogs.Cb27de61e.CreateItem(); C.SetNewObjectRef(Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360"))); C.Code = "10"; C.Description = "Category"; C.Write();
C = Catalogs.Cb27de61e.CreateItem(); C.SetNewObjectRef(Catalogs.Cb27de61e.GetRef(New UUID("8022f1c5-9afb-4ea4-9509-4603397bd058"))); C.Code = "20"; C.Description = "Second"; C.Write();
P = Documents.De777997a.CreateDocument(); P.SetNewObjectRef(Documents.De777997a.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360"))); P.Number = "30"; P.Date = Date(2024,2,29,12,34,56);
P.A226daa8e = "third"; P.Addc26edd = 12.50; P.A88ab03bf = True; P.A0df9bb43 = Date(2024,2,29,12,34,56); P.A3d883acc = Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360"));
P.Write(DocumentWriteMode.Posting, DocumentPostingMode.Regular);
P = Documents.De777997a.CreateDocument(); P.SetNewObjectRef(Documents.De777997a.GetRef(New UUID("4debce57-983f-4d87-88aa-393d70f469b3"))); P.Number = "10"; P.Date = Date(2024,3,1,1,2,3);
P.A226daa8e = ""; P.Addc26edd = 0; P.A88ab03bf = False; P.A0df9bb43 = Date(2024,3,1,1,2,3); P.A3d883acc = Catalogs.Cb27de61e.EmptyRef();
L = P.Items.Add(); L.Product = Catalogs.Cb27de61e.GetRef(New UUID("8022f1c5-9afb-4ea4-9509-4603397bd058")); L.Quantity = 1; L.Price = 2.50; L.Amount = 2.50; L.Note = "single";
P.Write(DocumentWriteMode.Write);
P = Documents.De777997a.CreateDocument(); P.SetNewObjectRef(Documents.De777997a.GetRef(New UUID("01239298-c4c6-48fc-b24f-7a3c3ba6926b"))); P.Number = "20"; P.Date = Date(2001,1,1,0,0,1);
P.A226daa8e = "first"; P.Addc26edd = -7.25; P.A88ab03bf = True; P.A0df9bb43 = Date(2001,1,1,0,0,1); P.A3d883acc = Catalogs.Cb27de61e.GetRef(New UUID("73d042f4-e669-4dbd-b881-741e8786f697"));
L = P.Items.Add(); L.Product = Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360")); L.Quantity = 2; L.Price = 3.25; L.Amount = 6.50; L.Note = "first";
L = P.Items.Add(); L.Product = Catalogs.Cb27de61e.GetRef(New UUID("8022f1c5-9afb-4ea4-9509-4603397bd058")); L.Quantity = 1; L.Price = 2; L.Amount = 2; L.Note = "second";
L = P.Items.Add(); L.Product = Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360")); L.Quantity = -1; L.Price = 1.25; L.Amount = -1.25; L.Note = "last";
P.Write(DocumentWriteMode.Write);
Q = New Query; Q.Text = "SELECT Number, Date, Posted, A3d883acc AS Target FROM Document.De777997a ORDER BY Date"; W = Q.Execute().Select();
Try CREmit("01", Documents.De777997a.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.Cb27de61e.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", DCCount("Document.De777997a")); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", DCCount("Catalog.Cb27de61e")); Except Message("CR-04: [action-error]"); EndTry;
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
Try CREmit("21", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
