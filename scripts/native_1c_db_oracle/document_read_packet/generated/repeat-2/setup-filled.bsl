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
If DCCount("Document.D8e1d8e38") <> 0 Then Raise "setup-not-empty"; EndIf;
If DCCount("Catalog.C8730e849") <> 0 Then Raise "setup-not-empty"; EndIf;
C = Catalogs.C8730e849.CreateItem(); C.SetNewObjectRef(Catalogs.C8730e849.GetRef(New UUID("0c19a161-2292-4047-b890-d087eeef341e"))); C.Code = "10"; C.Description = "Category"; C.Write();
P = Documents.D8e1d8e38.CreateDocument(); P.SetNewObjectRef(Documents.D8e1d8e38.GetRef(New UUID("0c19a161-2292-4047-b890-d087eeef341e"))); P.Number = "30"; P.Date = Date(2024,2,29,12,34,56);
P.A1bd27738 = "third"; P.Ac0e7cd57 = 12.50; P.Acf18520d = True; P.A47fccf59 = Date(2024,2,29,12,34,56); P.Aa02f337c = Catalogs.C8730e849.GetRef(New UUID("0c19a161-2292-4047-b890-d087eeef341e"));
P.Write(DocumentWriteMode.Posting, DocumentPostingMode.Regular);
P = Documents.D8e1d8e38.CreateDocument(); P.SetNewObjectRef(Documents.D8e1d8e38.GetRef(New UUID("35b44bdb-192a-4624-a614-35d83c93b7b5"))); P.Number = "10"; P.Date = Date(2024,3,1,1,2,3);
P.A1bd27738 = ""; P.Ac0e7cd57 = 0; P.Acf18520d = False; P.A47fccf59 = Date(2024,3,1,1,2,3); P.Aa02f337c = Catalogs.C8730e849.EmptyRef();
P.Write(DocumentWriteMode.Write);
P = Documents.D8e1d8e38.CreateDocument(); P.SetNewObjectRef(Documents.D8e1d8e38.GetRef(New UUID("33183d1c-cb28-409e-9e3e-6b02d710943e"))); P.Number = "20"; P.Date = Date(2001,1,1,0,0,1);
P.A1bd27738 = "first"; P.Ac0e7cd57 = -7.25; P.Acf18520d = True; P.A47fccf59 = Date(2001,1,1,0,0,1); P.Aa02f337c = Catalogs.C8730e849.GetRef(New UUID("94c21fbb-5227-4b30-82ec-3a76dc9d8a22"));
P.Write(DocumentWriteMode.Write);
Q = New Query; Q.Text = "SELECT Number, Date, Posted, Aa02f337c AS Target FROM Document.D8e1d8e38 ORDER BY Date"; W = Q.Execute().Select();
Try CREmit("01", Documents.D8e1d8e38.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.C8730e849.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", DCCount("Document.D8e1d8e38")); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", DCCount("Catalog.C8730e849")); Except Message("CR-04: [action-error]"); EndTry;
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
Try CREmit("21", Documents.D8e1d8e38.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", Documents.D8e1d8e38.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", Documents.D8e1d8e38.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", Documents.D8e1d8e38.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
