// Disposable native smoke. Requires native compilation and runtime proof.
// Runs in privileged server context; never use this module in a real database.
// All placeholders become validated, quoted BSL literals during injection.

Процедура УстановкаПараметровСеанса(ТребуемыеПараметры)

    // Lazy session-parameter requests must not create or mutate users.
    Если ТребуемыеПараметры <> Неопределено Тогда
        Возврат;
    КонецЕсли;

    Корень = @@EVIDENCE@@;
    ФайлУправления = Новый Файл(Корень + "/control.json");
    Если Не ФайлУправления.Существует() Тогда
        // The host removes control.json before ordinary launcher /C requests.
        Возврат;
    КонецЕсли;

    // A malformed control request is a hard startup failure, never a no-op pass.
    Запрос = NativeПрочитатьJSON(ФайлУправления.ПолноеИмя);
    Если Запрос.protocol <> "native-bootstrap-v1" Или Запрос.run_id <> @@RUN_ID@@ Тогда
        ВызватьИсключение "Native bootstrap: wrong control protocol/run ID";
    КонецЕсли;
    Если Запрос.stage = "bootstrap" Тогда
        Токен = @@BOOTSTRAP_TOKEN@@;
    ИначеЕсли Запрос.stage = "verify" Тогда
        Токен = @@VERIFY_TOKEN@@;
    Иначе
        ВызватьИсключение "Native bootstrap: unsupported control stage";
    КонецЕсли;
    Если Запрос.launch_token <> Токен Тогда
        ВызватьИсключение "Native bootstrap: wrong control launch token";
    КонецЕсли;

    ПутьРезультата = Корень + "/" + Запрос.stage + "-session.json";
    Результат = Новый Структура;
    Результат.Вставить("protocol", "native-bootstrap-v1");
    Результат.Вставить("run_id", @@RUN_ID@@);
    Результат.Вставить("stage", Запрос.stage);
    Результат.Вставить("hook", "session");
    Результат.Вставить("status", "error");
    Результат.Вставить("user", @@USER@@);
    Результат.Вставить("error", "");

    Попытка
        Пользователи = ПользователиИнформационнойБазы.ПолучитьПользователей();
        Результат.Вставить("users_before", Пользователи.Количество());
        Текущий = ПользователиИнформационнойБазы.ТекущийПользователь();
        ИмяПриЗапуске = "";
        Если Текущий <> Неопределено Тогда
            ИмяПриЗапуске = Текущий.Имя;
        КонецЕсли;
        Результат.Вставить("current_user_at_start", ИмяПриЗапуске);

        Если Запрос.stage = "bootstrap" Тогда
            Если ИмяПриЗапуске <> "" Тогда
                ВызватьИсключение "Native bootstrap: anonymous startup required";
            КонецЕсли;
            Если Пользователи.Количество() <> 0 Тогда
                ВызватьИсключение "Native bootstrap: refusing a database with existing users";
            КонецЕсли;
            Пользователь = ПользователиИнформационнойБазы.СоздатьПользователя();
            Пользователь.Имя = @@USER@@;
            Пользователь.ПолноеИмя = "Disposable native integration smoke user";
            Пользователь.АутентификацияСтандартная = Истина;
            // This USER property is Boolean, not UnsafeOperationProtectionDescription.
            Если ТипЗнч(Пользователь.ЗащитаОтОпасныхДействий) <> Тип("Булево") Тогда
                ВызватьИсключение "Native bootstrap: unsupported user protection property type";
            КонецЕсли;
            Пользователь.ЗащитаОтОпасныхДействий = Ложь;
            Пользователь.Записать();
            // CurrentUser() remains the startup snapshot; do not claim it was changed.
            Результат.Вставить("current_protection_verified", Ложь);
        Иначе
            Если Пользователи.Количество() <> 1 Тогда
                ВызватьИсключение "Native verify: expected exactly one disposable user";
            КонецЕсли;
            NativeПроверитьПользователя(Текущий);
            Результат.Вставить("current_protection_verified", Истина);
            Результат.Вставить("current_protection", Текущий.ЗащитаОтОпасныхДействий);
        КонецЕсли;

        Сохраненный = ПользователиИнформационнойБазы.НайтиПоИмени(@@USER@@);
        NativeПроверитьПользователя(Сохраненный);
        Результат.Вставить("persisted_user", Сохраненный.Имя);
        Результат.Вставить("protection_type", "Boolean");
        Результат.Вставить("persisted_protection", Сохраненный.ЗащитаОтОпасныхДействий);
        Результат.Вставить("standard_authentication", Сохраненный.АутентификацияСтандартная);
        Результат.Вставить("users_after", ПользователиИнформационнойБазы.ПолучитьПользователей().Количество());
        Если Результат.users_after <> 1 Тогда
            ВызватьИсключение "Native bootstrap: unexpected final user count";
        КонецЕсли;
        Результат.status = "ok";
    Исключение
        Результат.error = ПодробноеПредставлениеОшибки(ИнформацияОбОшибке());
        NativeЗаписатьJSON(ПутьРезультата, Результат);
        ВызватьИсключение;
    КонецПопытки;
    NativeЗаписатьJSON(ПутьРезультата, Результат);

КонецПроцедуры


Процедура NativeПроверитьПользователя(Пользователь)
    Если Пользователь = Неопределено Тогда
        ВызватьИсключение "Native verify: expected user is absent";
    КонецЕсли;
    Если Пользователь.Имя <> @@USER@@ Тогда
        ВызватьИсключение "Native verify: wrong current or persisted user";
    КонецЕсли;
    Если ТипЗнч(Пользователь.ЗащитаОтОпасныхДействий) <> Тип("Булево") Тогда
        ВызватьИсключение "Native verify: user protection is not Boolean";
    КонецЕсли;
    Если Пользователь.ЗащитаОтОпасныхДействий <> Ложь Тогда
        ВызватьИсключение "Native verify: user protection was not disabled";
    КонецЕсли;
    Если Пользователь.АутентификацияСтандартная <> Истина Тогда
        ВызватьИсключение "Native verify: standard authentication is not enabled";
    КонецЕсли;
    Если Пользователь.Роли.Количество() <> 0 Тогда
        ВызватьИсключение "Native verify: unexpected user roles; do not broaden permissions";
    КонецЕсли;
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
