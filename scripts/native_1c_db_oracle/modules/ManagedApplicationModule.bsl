// Managed-client dispatch. No measured operation runs in the SessionModule.
Процедура ПриНачалеРаботыСистемы()
    Попытка
        Если ТипЗнч(ПараметрЗапуска) <> Тип("Строка") Или СтрДлина(ПараметрЗапуска) <> 32 Тогда
            ВызватьИсключение "invalid_control";
        КонецЕсли;
        Для Индекс = 1 По 32 Цикл
            Если СтрНайти("0123456789abcdef", Сред(ПараметрЗапуска, Индекс, 1)) = 0 Тогда
                ВызватьИсключение "invalid_control";
            КонецЕсли;
        КонецЦикла;
        Завершение = Новый Структура("schema,nonce,token,operation,phase,status", 1, @@NONCE@@, ПараметрЗапуска, "dispatch", "dispatch", "error");
        Попытка
            // The server binds the exact fresh control to this /C token.
            Ответ = NativeOracleServer.NativeВыполнить(ПараметрЗапуска);
            NativeПроверитьОтвет(Ответ);
            Завершение.operation = Ответ.operation;
            Завершение.phase = Ответ.phase;
            Завершение.status = Ответ.status;
        Исключение
            // Transport/validation errors cannot preserve partial success.
            Завершение.operation = "dispatch";
            Завершение.phase = "dispatch";
            Завершение.status = "error";
        КонецПопытки;
        NativeЗаписатьЗавершение(Завершение);
    Исключение
        // Missing completion is failure, even if result.json already exists.
        // Never inspect errors, retry publication, or convert failure to success.
    КонецПопытки;
    // One attempt after either outcome; process/deadline checks remain required.
    ЗавершитьРаботуСистемы(Ложь);
КонецПроцедуры

Процедура NativeПроверитьОтвет(Ответ)
    Если ТипЗнч(Ответ) <> Тип("Структура") Тогда
        ВызватьИсключение "invalid_marker";
    КонецЕсли;
    Если Ответ.Количество() <> 3 Или ТипЗнч(Ответ.status) <> Тип("Строка")
        Или ТипЗнч(Ответ.operation) <> Тип("Строка") Или ТипЗнч(Ответ.phase) <> Тип("Строка") Тогда
        ВызватьИсключение "invalid_marker";
    КонецЕсли;
    Если Ответ.status <> "ok" И Ответ.status <> "error" Тогда
        ВызватьИсключение "invalid_marker";
    КонецЕсли;
    Если Ответ.operation <> "dispatch" И Ответ.operation <> "bootstrap" И Ответ.operation <> "audit"
        И Ответ.operation <> "observe" И Ответ.operation <> "create" И Ответ.operation <> "update"
        И Ответ.operation <> "delete" Тогда
        ВызватьИсключение "invalid_marker";
    КонецЕсли;
    ФазаИзвестна = Ложь;
    Для Каждого Фаза Из СтрРазделить("dispatch,control,marker,metadata,identity,precondition,begin,create_object,set_code,set_payload,set_amount,write,reference_capture,commit,reference_uuid,reference_write,reference_read,get_object,delete_object,readback,serialize,complete", ",") Цикл
        Если Ответ.phase = Фаза Тогда
            ФазаИзвестна = Истина;
        КонецЕсли;
    КонецЦикла;
    Если Не ФазаИзвестна Или (Ответ.status = "ok" И (Ответ.phase <> "complete" Или Ответ.operation = "dispatch"))
        Или (Ответ.status = "error" И Ответ.phase = "complete") Тогда
        ВызватьИсключение "invalid_marker";
    КонецЕсли;
КонецПроцедуры

Процедура NativeЗаписатьЗавершение(Завершение)
    Корень = @@EVIDENCE@@;
    Готовый = Новый Файл(Корень + "/completion.json");
    Временный = Новый Файл(Корень + "/completion.pending.json");
    Если Готовый.Существует() Или Временный.Существует() Тогда
        ВызватьИсключение "stale_evidence";
    КонецЕсли;
    Запись = Новый ЗаписьJSON;
    Запись.ОткрытьФайл(Временный.ПолноеИмя);
    ЗаписатьJSON(Запись, Завершение);
    Запись.Закрыть();
    // Same-directory publication only after close; never replace prior evidence.
    Если Готовый.Существует() Тогда
        ВызватьИсключение "stale_evidence";
    КонецЕсли;
    ПереместитьФайл(Временный.ПолноеИмя, Готовый.ПолноеИмя);
КонецПроцедуры
