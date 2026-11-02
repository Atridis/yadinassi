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
LF = Undefined; Try LF = InformationRegisters.I641d343f.SliceLast(Date(2024,2,29,12,0,1)); Except EndTry;
FF = Undefined; Try FF = InformationRegisters.I641d343f.SliceFirst(Date(2024,2,29,12,0,1),New Structure); Except EndTry;
LP = Undefined; Try LP = InformationRegisters.I641d343f.SliceLast(Date(2024,2,29,12,0,1),New Structure("Product",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")))); Except EndTry;
FP = Undefined; Try FP = InformationRegisters.I641d343f.SliceFirst(Date(2024,2,29,12,0,1),New Structure("Product",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")))); Except EndTry;
LK = Undefined; Try LK = InformationRegisters.I641d343f.SliceLast(Date(2024,2,29,12,0,1),New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
FK = Undefined; Try FK = InformationRegisters.I641d343f.SliceFirst(Date(2024,2,29,12,0,1),New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
R0 = Undefined; Try R0 = LF.FindRows(New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
R1 = Undefined; Try R1 = LF.FindRows(New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),2)); Except EndTry;
R2 = Undefined; Try R2 = LF.FindRows(New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("506f0733-5e24-49e8-8174-5158726caae9")),1)); Except EndTry;
Try CREmit("01", Metadata.InformationRegisters.I641d343f.Name); Except Message("CR-01: [action-error]"); EndTry;
// control.register
Try CREmit("02", Catalogs.C6b515170.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", LF.Count()); Except Message("CR-03: [action-error]"); EndTry;
// LF.count
Try CREmit("04", FF.Count()); Except Message("CR-04: [action-error]"); EndTry;
// FF.count
Try CREmit("05", LP.Count()); Except Message("CR-05: [action-error]"); EndTry;
// LP.count
Try CREmit("06", FP.Count()); Except Message("CR-06: [action-error]"); EndTry;
// FP.count
Try CREmit("07", LK.Count()); Except Message("CR-07: [action-error]"); EndTry;
// LK.count
Try CREmit("08", FK.Count()); Except Message("CR-08: [action-error]"); EndTry;
// FK.count
Try CREmit("09", String(TypeOf(LF))); Except Message("CR-09: [action-error]"); EndTry;
// table.type
Try CREmit("10", LF.Columns.Count()); Except Message("CR-10: [action-error]"); EndTry;
// columns
Try CREmit("11", String(TypeOf(LK[0].Период))); Except Message("CR-11: [action-error]"); EndTry;
// period.type
Try CREmit("12", XMLString(LK[0].Период)); Except Message("CR-12: [action-error]"); EndTry;
// last.period
Try CREmit("13", XMLString(LK[0].Price)); Except Message("CR-13: [action-error]"); EndTry;
// last.price
Try CREmit("14", XMLString(FK[0].Период)); Except Message("CR-14: [action-error]"); EndTry;
// first.period
Try CREmit("15", XMLString(FK[0].Price)); Except Message("CR-15: [action-error]"); EndTry;
// first.price
Try CREmit("16", LK[0].Product.Description); Except Message("CR-16: [action-error]"); EndTry;
// target
Try CREmit("17", R0.Count()); Except Message("CR-17: [action-error]"); EndTry;
// key.0.count
Try CREmit("18", XMLString(R0[0].Период) + "|" + XMLString(R0[0].Price) + "|" + XMLString(R0[0].Available) + "|" + XMLString(R0[0].ValidUntil) + "|" + XMLString(R0[0].Note)); Except Message("CR-18: [action-error]"); EndTry;
// key.0.values
Try CREmit("19", R1.Count()); Except Message("CR-19: [action-error]"); EndTry;
// key.1.count
Try CREmit("20", XMLString(R1[0].Период) + "|" + XMLString(R1[0].Price) + "|" + XMLString(R1[0].Available) + "|" + XMLString(R1[0].ValidUntil) + "|" + XMLString(R1[0].Note)); Except Message("CR-20: [action-error]"); EndTry;
// key.1.values
Try CREmit("21", R2.Count()); Except Message("CR-21: [action-error]"); EndTry;
// key.2.count
Try CREmit("22", XMLString(R2[0].Период) + "|" + XMLString(R2[0].Price) + "|" + XMLString(R2[0].Available) + "|" + XMLString(R2[0].ValidUntil) + "|" + XMLString(R2[0].Note)); Except Message("CR-22: [action-error]"); EndTry;
// key.2.values
Try CREmit("23", String(LF.Columns[0].ValueType)); Except Message("CR-23: [action-error]"); EndTry;
// period.column.type
Try CREmit("24", LF.Columns[0].Name + "|" + LF.Columns[1].Name + "|" + LF.Columns[2].Name + "|" + LF.Columns[3].Name + "|" + LF.Columns[4].Name + "|" + LF.Columns[5].Name + "|" + LF.Columns[6].Name); Except Message("CR-24: [action-error]"); EndTry;
// column.names
