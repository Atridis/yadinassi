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
F = Undefined; G = Undefined; Try F = Documents.Dad0328ac.GetRef(); Except EndTry;
Try G = Documents.Dad0328ac.GetRef(Undefined); Except EndTry;
Try CREmit("01", Documents.Dad0328ac.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.document
Try CREmit("02", Catalogs.C95217507.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", String(TypeOf(Documents))); Except Message("CR-03: [action-error]"); EndTry;
// global.type
Try CREmit("04", String(TypeOf(Documents.Dad0328ac))); Except Message("CR-04: [action-error]"); EndTry;
// manager.type
Try CREmit("05", String(TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))))); Except Message("CR-05: [action-error]"); EndTry;
// ref.type
Try CREmit("06", Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).Metadata().FullName()); Except Message("CR-06: [action-error]"); EndTry;
// ref.metadata
Try CREmit("07", String(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).UUID())); Except Message("CR-07: [action-error]"); EndTry;
// uuid
Try CREmit("08", Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")) = Catalogs.C95217507.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))); Except Message("CR-08: [action-error]"); EndTry;
// cross.kind
Try CREmit("09", TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))) = Type("DocumentRef.Dad0328ac")); Except Message("CR-09: [action-error]"); EndTry;
// ref.type.identity
Try CREmit("10", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-10: [action-error]"); EndTry;
// empty
Try CREmit("11", Documents.Dad0328ac.FindByNumber("MISSING").IsEmpty()); Except Message("CR-11: [action-error]"); EndTry;
// missing
Try CREmit("12", Documents.Dad0328ac.FindByNumber("") = Undefined); Except Message("CR-12: [action-error]"); EndTry;
// empty.number
Try CREmit("13", Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).Ref = Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))); Except Message("CR-13: [action-error]"); EndTry;
// ref.ref
Try CREmit("14", String(TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).A7d6294c3))); Except Message("CR-14: [action-error]"); EndTry;
// text.type
Try CREmit("15", String(TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).Aeea091ef))); Except Message("CR-15: [action-error]"); EndTry;
// number.type
Try CREmit("16", String(TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).Ac27bdff6))); Except Message("CR-16: [action-error]"); EndTry;
// boolean.type
Try CREmit("17", String(TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).A4f92e66d))); Except Message("CR-17: [action-error]"); EndTry;
// datetime.type
Try CREmit("18", String(TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).A5449af58))); Except Message("CR-18: [action-error]"); EndTry;
// reference.type
Try CREmit("19", String(F.UUID())); Except Message("CR-19: [action-error]"); EndTry;
// fresh.omitted.uuid
Try CREmit("20", String(G.UUID())); Except Message("CR-20: [action-error]"); EndTry;
// fresh.undefined.uuid
Try CREmit("21", F <> G); Except Message("CR-21: [action-error]"); EndTry;
// fresh.distinct
Try CREmit("22", ValueIsFilled(F) And ValueIsFilled(G) And Not F.IsEmpty() And Not G.IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// fresh.filled
Try CREmit("23", String(Documents.Dad0328ac.EmptyRef().UUID())); Except Message("CR-23: [action-error]"); EndTry;
// empty.uuid
Try CREmit("24", TypeOf(Documents.Dad0328ac.EmptyRef()) = TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))) And Not ValueIsFilled(Documents.Dad0328ac.EmptyRef())); Except Message("CR-24: [action-error]"); EndTry;
// empty.type.filled
