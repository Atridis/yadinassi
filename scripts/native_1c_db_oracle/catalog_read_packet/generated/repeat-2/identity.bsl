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
CRObserve("01", "Catalogs.Cb0f3538b.EmptyRef().Metadata().Name"); // control.name
CRObserve("02", "Catalogs.Cf5758dc3.EmptyRef().Metadata().Name"); // control.other_name
CRObserve("03", "String(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).UUID())"); // ref.uuid
CRObserve("04", "String(Catalogs.Cf5758dc3.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).UUID())"); // other.uuid
CRObserve("05", "String(Catalogs.Cb0f3538b.EmptyRef().UUID())"); // empty.uuid
CRObserve("06", "Catalogs.Cb0f3538b.EmptyRef().IsEmpty()"); // empty.isempty
CRObserve("07", "ValueIsFilled(Catalogs.Cb0f3538b.EmptyRef())"); // empty.filled
CRObserve("08", "Catalogs.Cb0f3538b.GetRef(New UUID(""00000000-0000-0000-0000-000000000000"")) = Catalogs.Cb0f3538b.EmptyRef()"); // zero.empty
CRObserve("09", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).IsEmpty()"); // record.isempty
CRObserve("10", "ValueIsFilled(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))"); // record.filled
CRObserve("11", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")) = Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71""))"); // record.repeat
CRObserve("12", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")) = Catalogs.Cb0f3538b.GetRef(New UUID(""d298b04a-1867-4140-8a2a-2324c5022a8f""))"); // record.other
CRObserve("13", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")) = Catalogs.Cf5758dc3.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71""))"); // record.crosscatalog
CRObserve("14", "Catalogs.Cb0f3538b.EmptyRef() = Catalogs.Cf5758dc3.EmptyRef()"); // empty.crosscatalog
CRObserve("15", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")) = New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")"); // record.uuid_equal
CRObserve("16", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")) = Undefined"); // record.undefined
CRObserve("17", "Catalogs.Cb0f3538b.Metadata() = Metadata.Catalogs.Cb0f3538b"); // manager.metadata
CRObserve("18", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).Metadata() = Metadata.Catalogs.Cb0f3538b"); // ref.metadata
CRObserve("19", "Catalogs.Cb0f3538b.EmptyRef().Metadata() = Metadata.Catalogs.Cb0f3538b"); // empty.metadata
CRObserve("20", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).Metadata().FullName()"); // ref.fullname
CRObserve("21", "Catalogs.Cf5758dc3.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).Metadata() = Metadata.Catalogs.Cf5758dc3"); // ref.metadata.other
CRObserve("22", "String(Catalogs.Cb0f3538b.GetRef(New UUID(""d298b04a-1867-4140-8a2a-2324c5022a8f"")).UUID())"); // absent.uuid
CRObserve("23", "Catalogs.Cb0f3538b.GetRef(New UUID(""d298b04a-1867-4140-8a2a-2324c5022a8f"")).IsEmpty()"); // absent.empty
CRObserve("24", "ValueIsFilled(Catalogs.Cb0f3538b.GetRef(New UUID(""d298b04a-1867-4140-8a2a-2324c5022a8f"")))"); // absent.filled
