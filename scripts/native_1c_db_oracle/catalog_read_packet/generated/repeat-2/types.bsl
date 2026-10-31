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
CRObserve("01", "Catalogs.Cb0f3538b.Metadata().Name"); // control.name
CRObserve("02", "String(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).UUID())"); // control.uuid
CRObserve("03", "String(TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71""))))"); // ref.type
CRObserve("04", "TypeOf(TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))) = Type(""Type"")"); // ref.metatype
CRObserve("05", "String(TypeOf(Catalogs.Cb0f3538b.EmptyRef()))"); // empty.type
CRObserve("06", "TypeOf(TypeOf(Catalogs.Cb0f3538b.EmptyRef())) = Type(""Type"")"); // empty.metatype
CRObserve("07", "String(TypeOf(Catalogs.Cb0f3538b))"); // manager.type
CRObserve("08", "TypeOf(TypeOf(Catalogs.Cb0f3538b)) = Type(""Type"")"); // manager.metatype
CRObserve("09", "String(TypeOf(Catalogs))"); // global.type
CRObserve("10", "TypeOf(TypeOf(Catalogs)) = Type(""Type"")"); // global.metatype
CRObserve("11", "Type(""СправочникСсылка.Cb0f3538b"") = TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))"); // ru.resolve
CRObserve("12", "Type(""CatalogRef.Cb0f3538b"") = TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))"); // en.resolve
CRObserve("13", "Type(""catalogref.cb0f3538b"") = TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))"); // lower.resolve
CRObserve("14", "Type(""CATALOGREF.CB0F3538B"") = TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))"); // upper.resolve
CRObserve("15", "TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71""))) = TypeOf(Catalogs.Cb0f3538b.EmptyRef())"); // ref.empty_type
CRObserve("16", "TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71""))) = TypeOf(Catalogs.Cf5758dc3.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))"); // ref.cross_type
CRObserve("17", "Type(""CatalogManager.Cb0f3538b"") = TypeOf(Catalogs.Cb0f3538b)"); // manager.resolve
CRObserve("18", "Тип(""СправочникМенеджер.Cb0f3538b"") = ТипЗнч(Catalogs.Cb0f3538b)"); // manager.ru
CRObserve("19", "TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).UUID()) = Type(""UUID"")"); // ref.uuid_type
CRObserve("20", "String(Type(""CatalogRef.AbsentProbe""))"); // type.missing
CRObserve("21", "Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")).Метаданные() = Метаданные.Справочники.Cb0f3538b"); // ref.metadata.ru
CRObserve("22", "String(Type(1))"); // type.number
CRObserve("23", "Type(""CatalogRef.Cb0f3538b"",1) = TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID(""700628db-fab5-4377-bce2-7e47b690ce71"")))"); // type.extra
CRObserve("24", "ТипЗнч(Справочники.Cb0f3538b.ПустаяСсылка()) = TypeOf(Catalogs.Cb0f3538b.EmptyRef())"); // type.ru_en
