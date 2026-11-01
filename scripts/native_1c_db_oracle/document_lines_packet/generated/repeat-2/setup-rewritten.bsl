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
Сообщить("CR-C1: [" + CRText("") + "]");
Сообщить("CR-C2: [" + CRText("A ;""😀") + "]");
P = Documents.De777997a.FindByNumber("20").GetObject(); If P.Items.Count() <> 3 Or P.Posted Or String(P.Ref.UUID()) <> "01239298-c4c6-48fc-b24f-7a3c3ba6926b" Then Raise "rewrite-precondition"; EndIf;
P.Items.Clear();
L = P.Items.Add(); L.Product = Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360")); L.Quantity = -1; L.Price = 1.25; L.Amount = -1.25; L.Note = "last";
L = P.Items.Add(); L.Product = Catalogs.Cb27de61e.GetRef(New UUID("73d042f4-e669-4dbd-b881-741e8786f697")); L.Quantity = 4; L.Price = 2; L.Amount = 8; L.Note = "replacement";
L = P.Items.Add(); L.Product = Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360")); L.Quantity = 2; L.Price = 3.25; L.Amount = 6.50; L.Note = "first";
P.Write(DocumentWriteMode.Write);
Try CREmit("01", Documents.De777997a.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.Cb27de61e.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", Documents.De777997a.FindByNumber("30").Items.Count()); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", Documents.De777997a.FindByNumber("10").Items.Count()); Except Message("CR-04: [action-error]"); EndTry;
Try CREmit("05", Documents.De777997a.FindByNumber("20").Items.Count()); Except Message("CR-05: [action-error]"); EndTry;
Try CREmit("06", String(TypeOf(Documents.De777997a.FindByNumber("20").Items))); Except Message("CR-06: [action-error]"); EndTry;
Try CREmit("07", String(TypeOf(Documents.De777997a.FindByNumber("20").Items.Get(0)))); Except Message("CR-07: [action-error]"); EndTry;
Try CREmit("08", TypeOf(Documents.De777997a.FindByNumber("20").Items) = Type("DocumentTabularSection.De777997a.Items")); Except Message("CR-08: [action-error]"); EndTry;
Try CREmit("09", TypeOf(Documents.De777997a.FindByNumber("20").Items.Get(0)) = Type("DocumentTabularSectionRow.De777997a.Items")); Except Message("CR-09: [action-error]"); EndTry;
Try CREmit("10", Documents.De777997a.FindByNumber("20").Items.Get(0).LineNumber); Except Message("CR-10: [action-error]"); EndTry;
Try CREmit("11", Documents.De777997a.FindByNumber("10").Items.Get(0).LineNumber); Except Message("CR-11: [action-error]"); EndTry;
Try CREmit("12", Documents.De777997a.FindByNumber("20").Items[0] = Documents.De777997a.FindByNumber("20").Items.Get(0)); Except Message("CR-12: [action-error]"); EndTry;
Try CREmit("13", Documents.De777997a.FindByNumber("20").Items.Get(0) = Documents.De777997a.FindByNumber("10").Items.Get(0)); Except Message("CR-13: [action-error]"); EndTry;
Try CREmit("14", TypeOf(Documents.De777997a.FindByNumber("20").Items.Get(0).Product) = Type("CatalogRef.Cb27de61e")); Except Message("CR-14: [action-error]"); EndTry;
Try CREmit("15", Documents.De777997a.FindByNumber("20").Items.Get(0).Product.Description); Except Message("CR-15: [action-error]"); EndTry;
Try CREmit("16", Documents.De777997a.FindByNumber("10").Items.Get(0).Product.Description); Except Message("CR-16: [action-error]"); EndTry;
Try CREmit("17", Documents.De777997a.FindByNumber("20").Items = Documents.De777997a.FindByNumber("20").Items); Except Message("CR-17: [action-error]"); EndTry;
Try CREmit("18", Documents.De777997a.FindByNumber("20").Items.Get(0) = Documents.De777997a.FindByNumber("20").Items.Get(0)); Except Message("CR-18: [action-error]"); EndTry;
Try CREmit("19", Documents.De777997a.EmptyRef().Items.Count()); Except Message("CR-19: [action-error]"); EndTry;
Try CREmit("20", Documents.De777997a.GetRef(New UUID("73d042f4-e669-4dbd-b881-741e8786f697")).Items.Count()); Except Message("CR-20: [action-error]"); EndTry;
Try CREmit("21", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
