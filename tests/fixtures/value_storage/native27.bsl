// SOURCE ONLY. No native expectations. Run only after isolated acquisition review.
// No files, network, metadata, database writes, secrets, or unbounded input.
Перем VSPhase;

Функция VSBit(Знач B)
    Если B Тогда Возврат "1"; КонецЕсли;
    Возврат "0";
КонецФункции

// Maps the three fixed sentinel numbers losslessly; X is another number, T another type.
Функция VSMark(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Тогда Возврат "T"; КонецЕсли;
    Если V = 1 Тогда Возврат "A"; КонецЕсли;
    Если V = 2 Тогда Возврат "B"; КонецЕсли;
    Если V = 3 Тогда Возврат "C"; КонецЕсли;
    Возврат "X";
КонецФункции

Функция VSScalar(Знач V, Знач Kind)
    VSPhase = "construct";
    H = Новый ХранилищеЗначения(V);
    VSPhase = "get1";
    R = H.Получить();
    VSPhase = "inspect";
    Если ТипЗнч(R) <> ТипЗнч(V) Тогда Возврат "type"; КонецЕсли;
    Если Kind = "undefined" Или Kind = "null" Тогда Возврат "type-ok"; КонецЕсли;
    Если Kind = "binary" Тогда
        Возврат VSBit(R.Размер() = V.Размер()) + VSBit(Base64Строка(R) = Base64Строка(V));
    КонецЕсли;
    Возврат VSBit(R = V);
КонецФункции

Функция VSSequence(Знач Kind)
    VSPhase = "setup";
    Если Kind = "array" Тогда
        A = Новый Массив; A.Добавить(1);
    ИначеЕсли Kind = "structure" Тогда
        A = Новый Структура("x", 1);
    Иначе
        A = Новый Соответствие; A.Вставить("x", 1);
    КонецЕсли;
    VSPhase = "construct"; H = Новый ХранилищеЗначения(A);
    VSPhase = "mutate-original";
    Если Kind = "array" Тогда A[0] = 2;
    ИначеЕсли Kind = "structure" Тогда A.x = 2;
    Иначе A.Вставить("x", 2); КонецЕсли;
    VSPhase = "get1"; R1 = H.Получить();
    VSPhase = "inspect";
    Если ТипЗнч(R1) <> ТипЗнч(A) Тогда Возврат "type"; КонецЕсли;
    Если Kind = "array" Тогда Before = VSMark(R1[0]);
    ИначеЕсли Kind = "structure" Тогда Before = VSMark(R1.x);
    Иначе Before = VSMark(R1["x"]); КонецЕсли;
    VSPhase = "mutate-get1";
    Если Kind = "array" Тогда R1[0] = 3;
    ИначеЕсли Kind = "structure" Тогда R1.x = 3;
    Иначе R1.Вставить("x", 3); КонецЕсли;
    VSPhase = "get2"; R2 = H.Получить();
    VSPhase = "inspect";
    Если ТипЗнч(R2) <> ТипЗнч(A) Тогда Возврат "type"; КонецЕсли;
    Если Kind = "array" Тогда Возврат Before + VSMark(A[0]) + VSMark(R1[0]) + VSMark(R2[0]);
    ИначеЕсли Kind = "structure" Тогда Возврат Before + VSMark(A.x) + VSMark(R1.x) + VSMark(R2.x);
    Иначе Возврат Before + VSMark(A["x"]) + VSMark(R1["x"]) + VSMark(R2["x"]); КонецЕсли;
КонецФункции

// Two positions refer to one inner array. Mutation reveals sharing without
// relying on object equality, and the second Get is inspected independently.
Функция VSShared(Знач Kind)
    VSPhase = "setup"; Inner = Новый Массив; Inner.Добавить(1);
    Если Kind = "array" Тогда
        Root = Новый Массив; Root.Добавить(Inner); Root.Добавить(Inner);
    Иначе
        Root = Новый Структура("a,b", Inner, Inner);
    КонецЕсли;
    VSPhase = "construct"; H = Новый ХранилищеЗначения(Root);
    VSPhase = "mutate-original"; Inner[0] = 2;
    VSPhase = "get1"; R1 = H.Получить();
    VSPhase = "inspect";
    Если ТипЗнч(R1) <> ТипЗнч(Root) Тогда Возврат "type"; КонецЕсли;
    Если Kind = "array" Тогда X = R1[0]; Y = R1[1]; Иначе X = R1.a; Y = R1.b; КонецЕсли;
    Если ТипЗнч(X) <> Тип("Массив") Или ТипЗнч(Y) <> Тип("Массив") Тогда Возврат "type"; КонецЕсли;
    Before = VSMark(X[0]);
    VSPhase = "mutate-get1"; X[0] = 3;
    VSPhase = "get2"; R2 = H.Получить();
    VSPhase = "inspect";
    Если ТипЗнч(R2) <> ТипЗнч(Root) Тогда Возврат "type"; КонецЕсли;
    Если Kind = "array" Тогда Z = R2[0]; W = R2[1]; Иначе Z = R2.a; W = R2.b; КонецЕсли;
    Если ТипЗнч(Z) <> Тип("Массив") Или ТипЗнч(W) <> Тип("Массив") Тогда Возврат "type"; КонецЕсли;
    Возврат Before + VSMark(Y[0]) + VSMark(Inner[0]) + VSMark(Z[0]) + VSMark(W[0]);
КонецФункции

Функция VSFixed(Знач Kind)
    VSPhase = "setup";
    Если Kind = "array" Тогда
        A = Новый Массив; A.Добавить(1); V = Новый ФиксированныйМассив(A);
    ИначеЕсли Kind = "structure" Тогда
        V = Новый ФиксированнаяСтруктура("x", 1);
    Иначе
        A = Новый Соответствие; A.Вставить("x", 1); V = Новый ФиксированноеСоответствие(A);
    КонецЕсли;
    VSPhase = "construct"; H = Новый ХранилищеЗначения(V);
    VSPhase = "get1"; R = H.Получить();
    VSPhase = "inspect";
    Если ТипЗнч(R) <> ТипЗнч(V) Тогда Возврат "type"; КонецЕсли;
    Если Kind = "array" Тогда Возврат VSMark(R[0]); КонецЕсли;
    Если Kind = "structure" Тогда Возврат VSMark(R.x); КонецЕсли;
    Возврат VSMark(R["x"]);
КонецФункции

Функция VSCase(Знач N)
    VSPhase = "setup";
    Если N = 1 Тогда Возврат VSScalar(42.25, "number");
    ИначеЕсли N = 2 Тогда Возврат VSScalar("abc", "string");
    ИначеЕсли N = 3 Тогда Возврат VSScalar(Истина, "boolean");
    ИначеЕсли N = 4 Тогда Возврат VSScalar('20240229123456', "date");
    ИначеЕсли N = 5 Тогда Возврат VSScalar(Неопределено, "undefined");
    ИначеЕсли N = 6 Тогда Возврат VSScalar(Null, "null");
    ИначеЕсли N = 7 Тогда Возврат VSScalar(Новый УникальныйИдентификатор("00000000-0000-0000-0000-000000000001"), "uuid");
    ИначеЕсли N = 8 Тогда Возврат VSScalar(ПолучитьДвоичныеДанныеИзСтроки("abc"), "binary");
    ИначеЕсли N = 9 Тогда Возврат VSSequence("array");
    ИначеЕсли N = 10 Тогда Возврат VSSequence("structure");
    ИначеЕсли N = 11 Тогда Возврат VSSequence("map");
    ИначеЕсли N = 12 Тогда Возврат VSShared("array");
    ИначеЕсли N = 13 Тогда Возврат VSShared("structure");
    ИначеЕсли N = 14 Тогда Возврат VSFixed("array");
    ИначеЕсли N = 15 Тогда Возврат VSFixed("structure");
    ИначеЕсли N = 16 Тогда Возврат VSFixed("map");
    ИначеЕсли N = 17 Тогда
        T = Новый ТаблицаЗначений; T.Колонки.Добавить("x"); Row = T.Добавить(); Row.x = 1;
        VSPhase = "construct"; H = Новый ХранилищеЗначения(T);
        VSPhase = "mutate-original"; Row.x = 2;
        VSPhase = "get1"; R = H.Получить();
        VSPhase = "inspect"; Если ТипЗнч(R) <> Тип("ТаблицаЗначений") Тогда Возврат "type"; КонецЕсли;
        Before = VSMark(R[0].x);
        VSPhase = "mutate-get1"; R[0].x = 3;
        VSPhase = "get2"; S = H.Получить();
        VSPhase = "inspect"; Если ТипЗнч(S) <> Тип("ТаблицаЗначений") Тогда Возврат "type"; КонецЕсли;
        Возврат Before + VSMark(Row.x) + VSMark(R[0].x) + VSMark(S[0].x);
    ИначеЕсли N = 18 Тогда
        VSPhase = "setup"; Compression = Новый СжатиеДанных(0);
        VSPhase = "construct"; H = Новый ХранилищеЗначения(1, Compression);
        VSPhase = "get1"; R = H.Получить(); VSPhase = "inspect"; Возврат VSMark(R);
    ИначеЕсли N = 19 Тогда
        VSPhase = "construct"; H = Вычислить("Новый ХранилищеЗначения(1, ""bad"")");
        VSPhase = "get1"; R = H.Получить(); VSPhase = "inspect"; Возврат VSMark(R);
    ИначеЕсли N = 20 Тогда
        VSPhase = "construct"; H = Вычислить("Новый ХранилищеЗначения()");
        VSPhase = "get1"; R = H.Получить(); VSPhase = "inspect";
        Возврат VSBit(ТипЗнч(R) = Тип("Неопределено"));
    ИначеЕсли N = 21 Тогда
        VSPhase = "construct"; H = Новый ХранилищеЗначения(1);
        VSPhase = "get1"; R = Вычислить("H.Получить(1)"); VSPhase = "inspect"; Возврат VSMark(R);
    ИначеЕсли N = 22 Тогда
        V = Новый ЗаписьJSON;
        VSPhase = "construct"; H = Новый ХранилищеЗначения(V);
        VSPhase = "get1"; R = H.Получить(); VSPhase = "inspect";
        Возврат VSBit(ТипЗнч(R) = ТипЗнч(V));
    ИначеЕсли N = 23 Тогда
        VSPhase = "construct"; H = Вычислить("Новый ХранилищеЗначения(1)");
        VSPhase = "get1"; R = Вычислить("H.Получить()");
        VSPhase = "inspect"; Возврат VSMark(R);
    ИначеЕсли N = 24 Тогда
        Inner = Новый ХранилищеЗначения(1);
        VSPhase = "construct"; H = Новый ХранилищеЗначения(Inner);
        VSPhase = "get1"; R = H.Получить(); VSPhase = "inspect";
        Если ТипЗнч(R) <> Тип("ХранилищеЗначения") Тогда Возврат "type"; КонецЕсли;
        VSPhase = "get2"; V = R.Получить(); VSPhase = "inspect"; Возврат VSMark(V);
    ИначеЕсли N = 25 Тогда Возврат VSScalar(-12.5, "number");
    ИначеЕсли N = 26 Тогда Возврат VSScalar("", "string");
    ИначеЕсли N = 27 Тогда Возврат VSScalar(Ложь, "boolean");
    КонецЕсли;
    ВызватьИсключение "unreachable";
КонецФункции

Процедура VSObserve(Знач N)
    Label = Прав("0" + Строка(N), 2);
    VSPhase = "setup";
    Попытка
        Result = VSCase(N);
    Исключение
        // No raw error text: bounded phase only. inspect-error blocks acquisition.
        Сообщить("VS-" + Label + ": [" + VSPhase + "-error]");
        Возврат;
    КонецПопытки;
    Если ТипЗнч(Result) <> Тип("Строка") Или СтрДлина(Result) > 16 Тогда
        Сообщить("VS-" + Label + ": [observer-error]"); Возврат;
    КонецЕсли;
    Для P = 1 По СтрДлина(Result) Цикл
        Если Найти("01ABCXTtype-ok", Сред(Result, P, 1)) = 0 Тогда
            Сообщить("VS-" + Label + ": [observer-error]"); Возврат;
        КонецЕсли;
    КонецЦикла;
    Сообщить("VS-" + Label + ": [ok|" + Result + "]");
КонецПроцедуры

Сообщить("VS-C1: [wire-v1]");
Для N = 1 По 27 Цикл VSObserve(N); КонецЦикла;
