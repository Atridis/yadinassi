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
Функция CRCount(Name, Ref = Неопределено)
    Q = Новый Запрос;
    Q.Текст = "ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК N ИЗ Справочник." + Name;
    Если Ref <> Неопределено Тогда
        Q.Текст = Q.Текст + " ГДЕ Ссылка = &Ref";
        Q.УстановитьПараметр("Ref", Ref);
    КонецЕсли;
    Row = Q.Выполнить().Выбрать();
    Если Не Row.Следующий() Тогда ВызватьИсключение "setup-count"; КонецЕсли;
    Возврат Row.N;
КонецФункции
Сообщить("CR-C1: [" + CRText("") + "]");
Сообщить("CR-C2: [" + CRText("A ;""😀") + "]");
Если CRCount("Cb0f3538b") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
CREmit("01", CRCount("Cb0f3538b"));
Manager = Catalogs.Cb0f3538b;
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("98261a79-1a0c-43f9-ab6c-bbd4c632dfaa")));
Object.Code = "30"; Object.Description = "Alpha"; Object.Payload = "first"; Object.Amount = 11; Object.Write();
Ghost = Manager.CreateItem(); Ghost.SetNewObjectRef(Manager.GetRef(New UUID("d298b04a-1867-4140-8a2a-2324c5022a8f"))); Ghost.Code = "40"; Ghost.Description = "Gone"; Ghost.Write();
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("fdf2a0c5-fbb5-483e-abdf-232392f99009")));
Object.Code = "10"; Object.Description = "Zulu"; Object.Payload = "second"; Object.Amount = 22; Object.Write();
Object.SetDeletionMark(True);
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")));
Object.Code = "20"; Object.Description = "Mike"; Object.Payload = "third"; Object.Amount = 33; Object.Write();
Ghost.Delete();
Reused = Manager.CreateItem(); Reused.SetNewObjectRef(Manager.GetRef(New UUID("d298b04a-1867-4140-8a2a-2324c5022a8f"))); Reused.Code = "40"; Reused.Description = "Reused"; Reused.Payload = "reused"; Reused.Amount = 44; Reused.Write();
CREmit("02", CRCount("Cb0f3538b"));
CREmit("03", CRCount("Cb0f3538b", Manager.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71"))));
CREmit("04", CRCount("Cb0f3538b", Manager.GetRef(New UUID("d298b04a-1867-4140-8a2a-2324c5022a8f"))));
CREmit("05", Manager.Metadata().Name);
CREmit("06", String(Manager.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).UUID()));
Если CRCount("Cf5758dc3") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
CREmit("07", CRCount("Cf5758dc3"));
Manager = Catalogs.Cf5758dc3;
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("98261a79-1a0c-43f9-ab6c-bbd4c632dfaa")));
Object.Code = "30"; Object.Description = "Alpha"; Object.Payload = "first"; Object.Amount = 11; Object.Write();
Ghost = Manager.CreateItem(); Ghost.SetNewObjectRef(Manager.GetRef(New UUID("d298b04a-1867-4140-8a2a-2324c5022a8f"))); Ghost.Code = "40"; Ghost.Description = "Gone"; Ghost.Write();
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("fdf2a0c5-fbb5-483e-abdf-232392f99009")));
Object.Code = "10"; Object.Description = "Zulu"; Object.Payload = "second"; Object.Amount = 22; Object.Write();
Object.SetDeletionMark(True);
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")));
Object.Code = "20"; Object.Description = "Mike"; Object.Payload = "third"; Object.Amount = 33; Object.Write();
Ghost.Delete();
Reused = Manager.CreateItem(); Reused.SetNewObjectRef(Manager.GetRef(New UUID("d298b04a-1867-4140-8a2a-2324c5022a8f"))); Reused.Code = "40"; Reused.Description = "Reused"; Reused.Payload = "reused"; Reused.Amount = 44; Reused.Write();
CREmit("08", CRCount("Cf5758dc3"));
CREmit("09", CRCount("Cf5758dc3", Manager.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71"))));
CREmit("10", CRCount("Cf5758dc3", Manager.GetRef(New UUID("d298b04a-1867-4140-8a2a-2324c5022a8f"))));
CREmit("11", Manager.Metadata().Name);
CREmit("12", String(Manager.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).UUID()));
