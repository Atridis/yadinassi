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
Function RGCount(TableName)
Q = New Query; Q.Text = "SELECT COUNT(*) AS N FROM " + TableName; W = Q.Execute().Select(); W.Next(); Return W.N;
EndFunction
Сообщить("CR-C1: [" + CRText("") + "]");
Сообщить("CR-C2: [" + CRText("A ;""😀") + "]");
If RGCount("InformationRegister.I27c9f847") <> 0 Then Raise "setup-not-empty"; EndIf;
If RGCount("Catalog.C50827504") <> 0 Then Raise "setup-not-empty"; EndIf;
C = Catalogs.C50827504.CreateItem(); C.SetNewObjectRef(Catalogs.C50827504.GetRef(New UUID("b1605ed5-bcdf-4193-911b-004a8bd3af18"))); C.Code = "10"; C.Description = "First"; C.Write();
C = Catalogs.C50827504.CreateItem(); C.SetNewObjectRef(Catalogs.C50827504.GetRef(New UUID("7b2f71d1-55b1-4812-9c0f-291a91b89f73"))); C.Code = "20"; C.Description = "Second"; C.Write();
R = InformationRegisters.I27c9f847.CreateRecordManager(); R.Product = Catalogs.C50827504.GetRef(New UUID("b1605ed5-bcdf-4193-911b-004a8bd3af18")); R.Variant = 2; R.Price = 0; R.Available = False; R.ValidUntil = Date(1,1,1); R.Note = ""; R.Write(False);
R = InformationRegisters.I27c9f847.CreateRecordManager(); R.Product = Catalogs.C50827504.GetRef(New UUID("7b2f71d1-55b1-4812-9c0f-291a91b89f73")); R.Variant = 1; R.Price = -7.25; R.Available = True; R.ValidUntil = Date(2001,1,1,0,0,1); R.Note = "second"; R.Write(False);
R = InformationRegisters.I27c9f847.CreateRecordManager(); R.Product = Catalogs.C50827504.GetRef(New UUID("b1605ed5-bcdf-4193-911b-004a8bd3af18")); R.Variant = 1; R.Price = 12.50; R.Available = True; R.ValidUntil = Date(2024,2,29,12,34,56); R.Note = "first"; R.Write(False);
Q = New Query; Q.Text = "SELECT Product, Variant, Price, Available, ValidUntil FROM InformationRegister.I27c9f847 ORDER BY Product.Code, Variant"; W = Q.Execute().Select();
Try CREmit("01", Metadata.InformationRegisters.I27c9f847.Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.C50827504.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", RGCount("InformationRegister.I27c9f847")); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", RGCount("Catalog.C50827504")); Except Message("CR-04: [action-error]"); EndTry;
Try CREmit("05", W.Next()); Except Message("CR-05: [action-error]"); EndTry;
Try CREmit("06", String(W.Product.UUID())); Except Message("CR-06: [action-error]"); EndTry;
Try CREmit("07", W.Variant); Except Message("CR-07: [action-error]"); EndTry;
Try CREmit("08", XMLString(W.Price)); Except Message("CR-08: [action-error]"); EndTry;
Try CREmit("09", W.Available); Except Message("CR-09: [action-error]"); EndTry;
Try CREmit("10", W.ValidUntil = Date(2024,2,29,12,34,56)); Except Message("CR-10: [action-error]"); EndTry;
Try CREmit("11", W.Next()); Except Message("CR-11: [action-error]"); EndTry;
Try CREmit("12", String(W.Product.UUID())); Except Message("CR-12: [action-error]"); EndTry;
Try CREmit("13", W.Variant); Except Message("CR-13: [action-error]"); EndTry;
Try CREmit("14", XMLString(W.Price)); Except Message("CR-14: [action-error]"); EndTry;
Try CREmit("15", W.Available); Except Message("CR-15: [action-error]"); EndTry;
Try CREmit("16", W.ValidUntil = Date(1,1,1)); Except Message("CR-16: [action-error]"); EndTry;
Try CREmit("17", W.Next()); Except Message("CR-17: [action-error]"); EndTry;
Try CREmit("18", String(W.Product.UUID())); Except Message("CR-18: [action-error]"); EndTry;
Try CREmit("19", W.Variant); Except Message("CR-19: [action-error]"); EndTry;
Try CREmit("20", XMLString(W.Price)); Except Message("CR-20: [action-error]"); EndTry;
Try CREmit("21", W.Available); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", W.ValidUntil = Date(2001,1,1,0,0,1)); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", W.Next()); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", Metadata.InformationRegisters.I27c9f847.Name); Except Message("CR-24: [action-error]"); EndTry;
