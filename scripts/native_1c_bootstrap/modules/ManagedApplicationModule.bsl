// Disposable native smoke. Client module: no server-only user API or &НаСервере directive.

Процедура ПриНачалеРаботыСистемы()
    Если ПараметрЗапуска = @@BOOTSTRAP_TOKEN@@ Тогда
        Этап = "bootstrap";
    ИначеЕсли ПараметрЗапуска = @@VERIFY_TOKEN@@ Тогда
        Этап = "verify";
    Иначе
        // The existing EPF launcher passes request.json as /C. Do not exit it.
        Возврат;
    КонецЕсли;

    Корень = @@EVIDENCE@@;
    Результат = Новый Структура;
    Результат.Вставить("protocol", "native-bootstrap-v1");
    Результат.Вставить("run_id", @@RUN_ID@@);
    Результат.Вставить("stage", Этап);
    Результат.Вставить("hook", "managed");
    Результат.Вставить("status", "error");
    Результат.Вставить("user", @@USER@@);
    Результат.Вставить("error", "");
    Попытка
        Запрос = NativeПрочитатьJSON(Корень + "/control.json");
        Если Запрос.protocol <> "native-bootstrap-v1" Или Запрос.run_id <> @@RUN_ID@@
            Или Запрос.stage <> Этап Или Запрос.launch_token <> ПараметрЗапуска Тогда
            ВызватьИсключение "Native client: control request mismatch";
        КонецЕсли;
        Сервер = NativeПрочитатьJSON(Корень + "/" + Этап + "-session.json");
        Если Сервер.protocol <> "native-bootstrap-v1" Или Сервер.run_id <> @@RUN_ID@@
            Или Сервер.stage <> Этап Или Сервер.hook <> "session"
            Или Сервер.status <> "ok" Или Сервер.error <> ""
            Или Сервер.user <> @@USER@@ Или Сервер.persisted_user <> @@USER@@ Тогда
            ВызватьИсключение "Native client: successful matching server hook is absent";
        КонецЕсли;
        Если ТипЗнч(Сервер.persisted_protection) <> Тип("Булево")
            Или Сервер.persisted_protection <> Ложь Тогда
            ВызватьИсключение "Native client: persisted Boolean false was not verified";
        КонецЕсли;
        Если Этап = "verify" Тогда
            Если Сервер.current_user_at_start <> @@USER@@
                Или Сервер.current_protection_verified <> Истина
                Или ТипЗнч(Сервер.current_protection) <> Тип("Булево")
                Или Сервер.current_protection <> Ложь Тогда
                ВызватьИсключение "Native client: fresh named-user verification is absent";
            КонецЕсли;
        КонецЕсли;
        Информация = Новый СистемнаяИнформация;
        Версия = Информация.ВерсияПриложения;
        Если ТипЗнч(Версия) <> Тип("Строка") Или ПустаяСтрока(Версия) Тогда
            ВызватьИсключение "Native client: actual application version is unavailable";
        КонецЕсли;
        Результат.Вставить("actual_version", Версия);
        Результат.Вставить("server_hook_verified", Истина);
        Результат.status = "ok";
    Исключение
        Результат.error = ПодробноеПредставлениеОшибки(ИнформацияОбОшибке());
    КонецПопытки;

    // Even an orderly client exit is not success without BOTH valid markers.
    NativeЗаписатьJSON(Корень + "/" + Этап + "-managed.json", Результат);
    ЗавершитьРаботуСистемы(Ложь);
КонецПроцедуры


Функция NativeПрочитатьJSON(Путь)
    Чтение = Новый ЧтениеJSON;
    Чтение.ОткрытьФайл(Путь);
    Результат = ПрочитатьJSON(Чтение);
    Чтение.Закрыть();
    Возврат Результат;
КонецФункции


Процедура NativeЗаписатьJSON(Путь, Данные)
    ФайлРезультата = Новый Файл(Путь);
    Если ФайлРезультата.Существует() Тогда
        ВызватьИсключение "Native evidence already exists; refuse stale/duplicate marker";
    КонецЕсли;
    Запись = Новый ЗаписьJSON;
    Запись.ОткрытьФайл(Путь);
    ЗаписатьJSON(Запись, Данные);
    Запись.Закрыть();
КонецПроцедуры
