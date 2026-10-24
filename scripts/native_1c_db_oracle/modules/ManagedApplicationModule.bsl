// Managed-client dispatch. No measured operation runs in the SessionModule.
Процедура ПриНачалеРаботыСистемы()
    Если ТипЗнч(ПараметрЗапуска) <> Тип("Строка") Или СтрДлина(ПараметрЗапуска) <> 32 Тогда
        ВызватьИсключение "invalid_control";
    КонецЕсли;
    Для Индекс = 1 По 32 Цикл
        Если СтрНайти("0123456789abcdef", Сред(ПараметрЗапуска, Индекс, 1)) = 0 Тогда
            ВызватьИсключение "invalid_control";
        КонецЕсли;
    КонецЦикла;
    // The server reads and binds the exact fresh control to this /C token.
    NativeOracleServer.NativeВыполнить(ПараметрЗапуска);
    ЗавершитьРаботуСистемы(Ложь);
КонецПроцедуры
