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
Если CRCount("C01a9a4ac") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
CREmit("01", CRCount("C01a9a4ac"));
Manager = Catalogs.C01a9a4ac;
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("364102af-be9e-4710-891b-6b740c72fdbe")));
Object.Code = "30"; Object.Description = "Alpha"; Object.Payload = "first"; Object.Amount = 11; Object.Write();
Ghost = Manager.CreateItem(); Ghost.SetNewObjectRef(Manager.GetRef(New UUID("161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4"))); Ghost.Code = "40"; Ghost.Description = "Gone"; Ghost.Write();
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846")));
Object.Code = "10"; Object.Description = "Zulu"; Object.Payload = "second"; Object.Amount = 22; Object.Write();
Object.SetDeletionMark(True);
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("2de10d96-3956-4328-acc7-6d0b2efa7a2f")));
Object.Code = "20"; Object.Description = "Mike"; Object.Payload = "third"; Object.Amount = 33; Object.Write();
Ghost.Delete();
CREmit("02", CRCount("C01a9a4ac"));
CREmit("03", CRCount("C01a9a4ac", Manager.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846"))));
CREmit("04", CRCount("C01a9a4ac", Manager.GetRef(New UUID("161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4"))));
CREmit("05", Manager.EmptyRef().Metadata().Name);
CREmit("06", String(Manager.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846")).UUID()));
Если CRCount("C992ca266") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
CREmit("07", CRCount("C992ca266"));
Manager = Catalogs.C992ca266;
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("364102af-be9e-4710-891b-6b740c72fdbe")));
Object.Code = "30"; Object.Description = "Alpha"; Object.Payload = "first"; Object.Amount = 11; Object.Write();
Ghost = Manager.CreateItem(); Ghost.SetNewObjectRef(Manager.GetRef(New UUID("161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4"))); Ghost.Code = "40"; Ghost.Description = "Gone"; Ghost.Write();
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846")));
Object.Code = "10"; Object.Description = "Zulu"; Object.Payload = "second"; Object.Amount = 22; Object.Write();
Object.SetDeletionMark(True);
Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("2de10d96-3956-4328-acc7-6d0b2efa7a2f")));
Object.Code = "20"; Object.Description = "Mike"; Object.Payload = "third"; Object.Amount = 33; Object.Write();
Ghost.Delete();
CREmit("08", CRCount("C992ca266"));
CREmit("09", CRCount("C992ca266", Manager.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846"))));
CREmit("10", CRCount("C992ca266", Manager.GetRef(New UUID("161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4"))));
CREmit("11", Manager.EmptyRef().Metadata().Name);
CREmit("12", String(Manager.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846")).UUID()));
